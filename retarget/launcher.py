"""Max toolkit routing; core/UI remain the verified 0.0.1 implementation.

Importing is inert. The parent bridge owns target selection and code reload;
this entry owns one live business window and never changes the standalone copy.
"""
import sys
from pathlib import Path

_window = None


def _is_live(window):
    if window is None:
        return False
    try:
        import shiboken6 as shiboken
    except ImportError:
        try:
            import shiboken2 as shiboken
        except ImportError:
            return True
    try:
        return bool(shiboken.isValid(window))
    except (RuntimeError, TypeError):
        return False


def _standalone_windows():
    result = []
    for name in ("lxmaxretarget", "lxmaxretarget.launcher", "lxmaxretarget.ui"):
        window = getattr(sys.modules.get(name), "_window", None)
        if _is_live(window) and all(window is not item for item in result):
            result.append(window)
    return result


def _integrated_windows():
    result = []
    for window in (_window, getattr(sys.modules.get(__package__), "_window", None),
                   getattr(sys.modules.get(__package__ + ".ui"), "_window", None)):
        if _is_live(window) and all(window is not item for item in result):
            result.append(window)
    return result


def _register_window(window):
    global _window
    _window = window
    for name in (__package__, __package__ + ".ui"):
        module = sys.modules.get(name)
        if module is not None:
            module._window = window


def _unregister_window(window):
    global _window
    if _window is window:
        _window = None
    for name in (__package__, __package__ + ".ui"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "_window", None) is window:
            module._window = None


def show(session=None):
    """Open/reuse this Max's window; an explicit new Session replaces it safely."""
    from .host import MaxHost
    MaxHost.check_thread()
    # Read-only inspection: do not close, purge or mutate a historical install.
    if _standalone_windows():
        raise RuntimeError("独立版重定向窗口仍打开。请先关闭独立版并完成预览/显隐恢复，再从 Max 工具集打开；不会自动修改旧窗口。")
    windows = _integrated_windows()
    if len(windows) > 1:
        raise RuntimeError("检测到多个重定向窗口，请先关闭多余窗口再打开，避免恢复备份相互覆盖。")
    from . import ui
    if windows:
        old = windows[0]
        if session is None or getattr(old, "session", None) is session:
            _register_window(old)
            old.show()
            return old
        if getattr(old, "_busy", False):
            raise RuntimeError("旧重定向窗口正忙，不能切换会话。")
        app = ui.QtWidgets.QApplication.instance()
        modal = app.activeModalWidget() if app is not None else None
        if modal is not None and (modal is old or old.isAncestorOf(modal)):
            raise RuntimeError("请先应用或取消整链编辑，再切换重定向会话。")
        if old.close() is False:
            raise RuntimeError("旧重定向窗口正忙或恢复未完成，不能切换会话。")
        _unregister_window(old)
        # Deliver deletion only to our closed window, not arbitrary Max events.
        if isinstance(old, ui.QtCore.QObject):
            ui.QtCore.QCoreApplication.sendPostedEvents(old, ui.QtCore.QEvent.DeferredDelete)
    from .session import Session
    try:
        import qtmax
        parent = qtmax.GetQMaxMainWindow()
    except ImportError:
        parent = None
    window = ui.RetargetWindow(session if session is not None else Session(MaxHost()), parent=parent)
    icon = Path(show.__code__.co_filename).resolve().parent / "icon.png"
    if icon.is_file():
        window.setWindowIcon(ui.QtGui.QIcon(str(icon)))
    _register_window(window)
    window.destroyed.connect(lambda *_: _unregister_window(window))
    window.show()
    return window
