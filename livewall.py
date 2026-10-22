"""
LiveWall - бесплатные живые обои для Windows.
Установка:  pip install PyQt6 PyQt6-WebEngine
Запуск:     pythonw livewall.py   (или python livewall.py)
Поддержка:  .mp4 .webm .mkv .avi .mov (видео), .gif, .html/.htm (веб-обои)
"""
import sys, json, ctypes
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QFileDialog,
                             QWidget, QLabel)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QColor, QMovie
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

VIDEO = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
HTML = {".html", ".htm"}
ALL = VIDEO | HTML | {".gif"}
CONFIG = Path.home() / ".livewall.json"

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND


# ---------- встраивание окна за иконки рабочего стола ----------
def get_workerw():
    progman = user32.FindWindowW("Progman", None)
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, _):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            w = user32.FindWindowExW(None, hwnd, "WorkerW", None)
            if w:
                found.append(w)
        return True

    user32.EnumWindows(enum_cb, 0)
    if found:                       # классическая схема (Win10 / ранние Win11)
        return found[0]
    child = user32.FindWindowExW(progman, None, "WorkerW", None)
    return child or progman        # Win11 24H2+


class Wallpaper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background:black")
        self.inner = None
        self.player = None
        self.muted = True
        self.paused = False
        self.show()
        scr = QApplication.primaryScreen().geometry()
        virt = QApplication.primaryScreen().virtualGeometry()
        user32.SetParent(int(self.winId()), get_workerw())
        self.setGeometry(scr.x() - virt.x(), scr.y() - virt.y(),
                         scr.width(), scr.height())

    def clear(self):
        if self.player:
            self.player.stop()
            self.player = None
        if self.inner:
            self.inner.hide()
            self.inner.deleteLater()
            self.inner = None

    def load(self, path):
        p = Path(path)
        ext = p.suffix.lower()
        self.clear()
        if ext in VIDEO:
            w = QVideoWidget(self)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setMuted(self.muted)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(w)
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
            self.player.setSource(QUrl.fromLocalFile(str(p)))
            self.player.play()
        elif ext in HTML:
            w = QWebEngineView(self)
            w.setUrl(QUrl.fromLocalFile(str(p)))
        elif ext == ".gif":
            w = QLabel(self)
            w.setScaledContents(True)
            self.movie = QMovie(str(p))
            w.setMovie(self.movie)
            self.movie.start()
        else:
            return
        w.setGeometry(self.rect())
        w.show()
        self.inner = w

    def set_paused(self, value):
        if value == self.paused or not self.inner:
            return
        self.paused = value
        if self.player:
            self.player.pause() if value else self.player.play()
        elif isinstance(self.inner, QWebEngineView):
            self.inner.page().setLifecycleState(
                QWebEnginePage.LifecycleState.Frozen if value
                else QWebEnginePage.LifecycleState.Active)
        elif isinstance(self.inner, QLabel):
            self.movie.setPaused(value)

    def set_muted(self, value):
        self.muted = value
        if self.player:
            self.audio.setMuted(value)


# ---------- пауза, когда поверх открыто полноэкранное приложение ----------
def fullscreen_app_active():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    s = QApplication.primaryScreen().geometry()
    dpr = QApplication.primaryScreen().devicePixelRatio()
    return (r.right - r.left >= s.width() * dpr - 2 and
            r.bottom - r.top >= s.height() * dpr - 2)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    save = lambda: CONFIG.write_text(json.dumps(cfg))

    wall = Wallpaper()
    wall.muted = cfg.get("muted", True)

    def apply(path):
        cfg["current"] = str(path)
        save()
        wall.load(path)

    pix = QPixmap(32, 32)
    pix.fill(QColor("#7c5cff"))
    tray = QSystemTrayIcon(QIcon(pix))
    menu = QMenu()
    lib_menu = menu.addMenu("Библиотека")

    def rebuild_library():
        lib_menu.clear()
        folder = cfg.get("library")
        if not folder or not Path(folder).is_dir():
            lib_menu.addAction("(папка не выбрана)").setEnabled(False)
            return
        for f in sorted(Path(folder).iterdir()):
            if f.suffix.lower() in ALL:
                lib_menu.addAction(f.name, lambda p=f: apply(p))

    def pick_file():
        f, _ = QFileDialog.getOpenFileName(
            None, "Выбери обои", cfg.get("library", ""),
            "Обои (*" + " *".join(sorted(ALL)) + ")")
        if f:
            apply(f)

    def pick_folder():
        d = QFileDialog.getExistingDirectory(None, "Папка с обоями")
        if d:
            cfg["library"] = d
            save()
            rebuild_library()

    def toggle_mute(checked):
        cfg["muted"] = checked
        save()
        wall.set_muted(checked)

    menu.addAction("Выбрать файл…", pick_file)
    menu.addAction("Папка библиотеки…", pick_folder)
    mute = QAction("Без звука", checked=wall.muted)
    mute.setCheckable(True)
    mute.toggled.connect(toggle_mute)
    menu.addAction(mute)
    menu.addSeparator()
    menu.addAction("Выход", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("LiveWall")
    tray.show()
    rebuild_library()

    if cfg.get("current") and Path(cfg["current"]).exists():
        wall.load(cfg["current"])

    timer = QTimer()
    timer.timeout.connect(lambda: wall.set_paused(fullscreen_app_active()))
    timer.start(2000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
