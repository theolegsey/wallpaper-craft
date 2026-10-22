"""
LiveWall - бесплатные живые обои для Windows.
Установка:  pip install PyQt6 PyQt6-WebEngine
Запуск:     pythonw livewall.py   (или python livewall.py)
Поддержка:  .mp4 .webm .mkv .avi .mov (видео), .gif, .html/.htm (веб-обои)
"""
import sys, json, ctypes, traceback, faulthandler, datetime
from ctypes import wintypes
from pathlib import Path

LOG = Path.home() / "livewall.log"


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass


def show_error(text):
    ctypes.windll.user32.MessageBoxW(
        0, text + f"\n\nПодробности в файле:\n{LOG}", "LiveWall - ошибка", 0x10)


def excepthook(t, e, tb):
    text = "".join(traceback.format_exception(t, e, tb))
    log(text)
    show_error(text[-900:])


sys.excepthook = excepthook
try:
    faulthandler.enable(open(LOG, "a"))
except Exception:
    pass
log("=== запуск ===")

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
H = wintypes.HWND
user32.FindWindowW.restype = H
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = H
user32.FindWindowExW.argtypes = [H, H, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetForegroundWindow.restype = H
user32.SetParent.restype = H
user32.SetParent.argtypes = [H, H]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [H, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [H, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_POPUP, WS_CHILD = 0x80000000, 0x40000000
WS_EX_NOREDIRECTIONBITMAP = 0x00200000
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOACTIVATE|FRAMECHANGED
HWND_BOTTOM = 1


def attach_behind_icons(hwnd):
    """Прячет окно за иконки рабочего стола (Win10 и Win11, включая 24H2+)."""
    hwnd = int(hwnd)
    progman = user32.FindWindowW("Progman", None)
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, None)
    raised = user32.GetWindowLongPtrW(progman, GWL_EXSTYLE) & WS_EX_NOREDIRECTIONBITMAP

    if raised:
        # Win11 24H2+: окно становится дочерним для Progman, ниже слоя с иконками
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF
        style = (style & ~WS_POPUP) | WS_CHILD
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        user32.SetParent(hwnd, progman)
        defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        user32.SetWindowPos(hwnd, defview or HWND_BOTTOM, 0, 0, 0, 0, SWP_FLAGS)
        shell_worker = user32.FindWindowExW(progman, None, "WorkerW", None)
        if shell_worker:
            user32.SetWindowPos(shell_worker, HWND_BOTTOM, 0, 0, 0, 0, SWP_FLAGS)
        log("attach: режим 24H2+ (Progman)")
        return

    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(h, _):
        if user32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
            w = user32.FindWindowExW(None, h, "WorkerW", None)
            if w:
                found.append(w)
        return True

    user32.EnumWindows(enum_cb, 0)
    target = found[0] if found else progman
    user32.SetParent(hwnd, target)
    log(f"attach: классический режим, parent={target}")


class Wallpaper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setStyleSheet("background:black")
        self.inner = None
        self.player = None
        self.muted = True
        self.paused = False
        scr = QApplication.primaryScreen().geometry()
        virt = QApplication.primaryScreen().virtualGeometry()
        self._geom = (scr.x() - virt.x(), scr.y() - virt.y(),
                      scr.width(), scr.height())
        self.setGeometry(*self._geom)
        self.hwnd = int(self.winId())   # окно создано, но пока не показано
        attach_behind_icons(self.hwnd)

    def showEvent(self, e):
        super().showEvent(e)
        # повторно закрепляем после показа: Qt мог сбросить стиль окна
        QTimer.singleShot(150, self._reattach)

    def _reattach(self):
        attach_behind_icons(self.hwnd)
        self.setGeometry(*self._geom)
        if self.inner:
            self.inner.setGeometry(self.rect())

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
        if not self.isVisible():
            self.show()

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

    log("создаю окно обоев")
    wall = Wallpaper()
    log("окно создано")
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
                lib_menu.addAction(f.name, lambda checked=False, p=f: apply(p))

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
    log("трей показан")
    rebuild_library()

    if cfg.get("current") and Path(cfg["current"]).exists():
        wall.load(cfg["current"])

    timer = QTimer()
    timer.timeout.connect(lambda: wall.set_paused(fullscreen_app_active()))
    timer.start(2000)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        excepthook(*sys.exc_info())
