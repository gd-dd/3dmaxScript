"""Focused flat-retarget launcher handoff tests; never imports or connects pymxs.

Run explicitly with unittest discover -s tests/retarget. This directory is not a
package: naming a test package 'retarget' would shadow the production package.
Only the local artifacts directory is used for Qt/cache/temp output.
"""
from contextlib import ExitStack
import importlib
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
sys.dont_write_bytecode = True
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class FakeHost:
    instance_label = "offscreen launcher test; no Max connection"

    @staticmethod
    def check_thread():
        return None

    def current_frame(self):
        return 0

    def frame_range(self):
        return (0, 60)

    def selection_ids(self):
        return []


class FakeSession:
    def __init__(self, label="session", events=None):
        self.label = label
        self.events = [] if events is None else events
        self.host = FakeHost()
        self.source = []
        self.target = []
        self.chains = []
        self.settings = {}
        self.fail_preview = False
        self.fail_visibility = False

    def restore_preview(self):
        self.events.append((self.label, "restore_preview"))
        if self.fail_preview:
            raise RuntimeError("injected preview recovery failure")

    def restore_visibility(self):
        self.events.append((self.label, "restore_visibility"))
        if self.fail_visibility:
            raise RuntimeError("injected visibility recovery failure")


class LauncherIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_env = {key: os.environ.get(key) for key in
                            ("QT_QPA_PLATFORM", "PYTHONDONTWRITEBYTECODE", "TEMP", "TMP",
                             "APPDATA", "LOCALAPPDATA", "XDG_CACHE_HOME")}
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        for key, suffix in (("TEMP", "temp"), ("TMP", "temp"), ("APPDATA", "appdata"),
                            ("LOCALAPPDATA", "localappdata"), ("XDG_CACHE_HOME", "cache")):
            directory = ARTIFACTS / suffix
            directory.mkdir(parents=True, exist_ok=True)
            os.environ[key] = str(directory)
        from PySide6 import QtCore, QtWidgets
        import shiboken6
        cls.QtCore, cls.QtWidgets, cls.shiboken = QtCore, QtWidgets, shiboken6
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.app.processEvents()
        for key, previous in cls.previous_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous

    def setUp(self):
        self.package = importlib.import_module("retarget")
        self.launcher = importlib.import_module("retarget.launcher")
        self.ui = importlib.import_module("retarget.ui")
        self.host_module = importlib.import_module("retarget.host")
        self.session_module = importlib.import_module("retarget.session")
        self.assertEqual(Path(self.package.__file__).resolve().parent, (REPO / "retarget").resolve())
        self.stack = ExitStack()
        self.events, self.windows, self.legacy_widgets = [], [], []
        for module in (self.package, self.launcher, self.ui):
            self.stack.enter_context(mock.patch.object(module, "_window", None, create=True))
        # Keep a real Qt window and real production closeEvent; replace only
        # scene access and factory boundaries that would instantiate pymxs.
        real_window = self.ui.RetargetWindow

        def construct(session, parent=None):
            self.events.append((session.label, "construct"))
            window = real_window(session, parent=parent)
            self.windows.append(window)
            return window

        self.window_factory = self.stack.enter_context(mock.patch.object(self.ui, "RetargetWindow", side_effect=construct))
        self.stack.enter_context(mock.patch.object(self.host_module, "MaxHost", FakeHost))
        self.default_session = FakeSession("default", self.events)
        self.default_factory = self.stack.enter_context(mock.patch.object(
            self.session_module, "Session", side_effect=lambda host: self.default_session))
        qtmax = ModuleType("qtmax")
        qtmax.GetQMaxMainWindow = lambda: None
        self.stack.enter_context(mock.patch.dict(sys.modules, {"qtmax": qtmax}))
        self.legacy_root = ModuleType("lxmaxretarget")
        self.legacy_root.__version__ = "0.0.1"
        self.legacy_launcher = ModuleType("lxmaxretarget.launcher")
        self.legacy_ui = ModuleType("lxmaxretarget.ui")
        self.legacy_launcher._window = self.legacy_ui._window = None
        self.stack.enter_context(mock.patch.dict(sys.modules, {
            "lxmaxretarget": self.legacy_root,
            "lxmaxretarget.launcher": self.legacy_launcher,
            "lxmaxretarget.ui": self.legacy_ui,
        }))

    def tearDown(self):
        for window in reversed(self.windows + self.legacy_widgets):
            if not self.shiboken.isValid(window):
                continue
            if hasattr(window, "_busy"):
                window._busy = False
                window.session.fail_preview = False
                window.session.fail_visibility = False
            window.close()
            window.deleteLater()
        self.flush_deletes()
        self.stack.close()

    def flush_deletes(self):
        self.QtCore.QCoreApplication.sendPostedEvents(None, self.QtCore.QEvent.DeferredDelete)
        self.app.processEvents()

    def session(self, label):
        return FakeSession(label, self.events)

    def assert_aliases(self, expected):
        for module in (self.package, self.launcher, self.ui):
            self.assertIs(getattr(module, "_window", None), expected, module.__name__)

    def legacy_window(self):
        events = self.events
        class LegacyWindow(self.QtWidgets.QDialog):
            def close(self):
                events.append(("legacy", "close"))
                return super().close()
        window = LegacyWindow()
        window.show()  # Offscreen only; make the 'alive old window' condition explicit.
        self.legacy_widgets.append(window)
        return window

    def test_import_is_inert_and_cannot_import_pymxs(self):
        # A fresh process avoids false passes caused by already imported modules.
        code = """
import importlib, pathlib, sys
sys.path.insert(0, REPO)
class RejectMaxImport:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pymxs" or fullname.startswith("pymxs."):
            raise AssertionError("product import attempted to load pymxs")
sys.meta_path.insert(0, RejectMaxImport())
from PySide6 import QtWidgets
shows = []
QtWidgets.QWidget.show = lambda widget: shows.append(type(widget).__name__)
QtWidgets.QDialog.show = lambda widget: shows.append(type(widget).__name__)
for name in ("retarget", "retarget.launcher", "retarget.ui"):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(REPO)/"retarget")
assert not shows, shows
assert "pymxs" not in sys.modules
print("PASS inert retarget import")
"""
        code = "REPO = " + repr(str(REPO)) + "\n" + code
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ARTIFACTS,
                                env=dict(os.environ), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS inert retarget import", result.stdout)

    def test_old_standalone_launcher_or_ui_registry_refuses_without_touching_old_state(self):
        for slot in ("launcher", "ui", "both"):
            with self.subTest(slot=slot):
                old = self.legacy_window()
                self.legacy_launcher._window = old if slot in ("launcher", "both") else None
                self.legacy_ui._window = old if slot in ("ui", "both") else None
                before_path = list(sys.path)
                before_modules = {name: sys.modules[name] for name in
                                  ("lxmaxretarget", "lxmaxretarget.launcher", "lxmaxretarget.ui")}
                with self.assertRaises((RuntimeError, ValueError)) as raised:
                    self.launcher.show(self.session("integrated"))
                self.assertRegex(str(raised.exception), "关闭|独立|旧")
                self.assertEqual(self.window_factory.call_count, 0)
                self.assertNotIn(("legacy", "close"), self.events)
                self.assertEqual(sys.path, before_path)
                for name, module in before_modules.items():
                    self.assertIs(sys.modules[name], module)
                self.assertIs(self.legacy_launcher._window, old if slot in ("launcher", "both") else None)
                self.assertIs(self.legacy_ui._window, old if slot in ("ui", "both") else None)
                self.assertTrue(self.shiboken.isValid(old))
                self.legacy_launcher._window = self.legacy_ui._window = None
                old.hide()
                self.shiboken.delete(old)

    def test_same_or_default_session_reuses_one_window_and_all_aliases(self):
        first_session = self.session("first")
        first = self.launcher.show(first_session)
        self.assert_aliases(first)
        self.assertIs(first.session, first_session)
        self.assertIs(self.launcher.show(), first)
        self.assertIs(self.launcher.show(first_session), first)
        self.assertEqual(self.window_factory.call_count, 1)
        self.default_factory.assert_not_called()
        self.assertNotIn(("first", "restore_preview"), self.events)
        self.assert_aliases(first)

    def test_first_default_session_is_constructed_once_and_reused(self):
        first = self.launcher.show()
        self.assertIs(first.session, self.default_session)
        self.assertIs(self.launcher.show(), first)
        self.assertEqual(self.default_factory.call_count, 1)
        self.assertEqual(self.window_factory.call_count, 1)
        self.assert_aliases(first)

    def test_new_explicit_session_restores_old_before_replacement_and_deferred_delete_is_safe(self):
        first = self.launcher.show(self.session("first"))
        self.events.clear()
        second_session = self.session("second")
        second = self.launcher.show(second_session)
        self.assertIsNot(first, second)
        self.assertIs(second.session, second_session)
        self.assertEqual(self.events, [("first", "restore_preview"), ("first", "restore_visibility"),
                                      ("second", "construct")])
        self.assert_aliases(second)
        self.flush_deletes()
        self.assertFalse(self.shiboken.isValid(first))
        self.assertTrue(self.shiboken.isValid(second))
        self.assert_aliases(second)

    def test_busy_close_false_keeps_existing_window_and_rejects_replacement(self):
        first = self.launcher.show(self.session("first"))
        first._busy = True
        self.events.clear()
        with self.assertRaises((RuntimeError, ValueError)):
            self.launcher.show(self.session("second"))
        self.assertEqual(self.events, [])
        self.assertEqual(self.window_factory.call_count, 1)
        self.assert_aliases(first)
        self.assertTrue(self.shiboken.isValid(first))

    def test_explicit_close_false_rejects_without_constructing_a_replacement(self):
        first = self.launcher.show(self.session("first"))
        self.events.clear()
        with mock.patch.object(first, "close", return_value=False) as close:
            with self.assertRaises((RuntimeError, ValueError)):
                self.launcher.show(self.session("second"))
        close.assert_called_once_with()
        self.assertEqual(self.events, [])
        self.assertEqual(self.window_factory.call_count, 1)
        self.assert_aliases(first)

    def test_unexpected_close_exception_is_not_mistaken_for_an_invalid_wrapper(self):
        first = self.launcher.show(self.session("first"))
        self.events.clear()
        with mock.patch.object(first, "close", side_effect=RuntimeError("injected outer close failure")):
            with self.assertRaisesRegex(RuntimeError, "injected outer close failure"):
                self.launcher.show(self.session("second"))
        self.assertEqual(self.events, [])
        self.assertEqual(self.window_factory.call_count, 1)
        self.assert_aliases(first)
        self.assertTrue(self.shiboken.isValid(first))

    def test_recovery_failure_cannot_replace_or_forget_existing_session(self):
        for failure in ("fail_preview", "fail_visibility"):
            with self.subTest(failure=failure):
                first_session = self.session(failure)
                first = self.launcher.show(first_session)
                setattr(first_session, failure, True)
                self.events.clear()
                previous_count = self.window_factory.call_count
                with self.assertRaises((RuntimeError, ValueError)):
                    self.launcher.show(self.session("rejected"))
                self.assertEqual(self.window_factory.call_count, previous_count)
                self.assert_aliases(first)
                self.assertIs(first.session, first_session)
                self.assertNotIn(("rejected", "construct"), self.events)
                setattr(first_session, failure, False)
                first.close()
                self.flush_deletes()

    def test_deleted_qt_wrapper_is_discarded_and_new_session_can_open(self):
        first = self.launcher.show(self.session("first"))
        first.close()
        self.flush_deletes()
        self.assertFalse(self.shiboken.isValid(first))
        # Simulate a stale reference left by an earlier caller; do not ask a
        # deleted wrapper to close or show itself.
        for module in (self.package, self.launcher, self.ui):
            module._window = first
        second = self.launcher.show(self.session("second"))
        self.assertIsNot(first, second)
        self.assertTrue(self.shiboken.isValid(second))
        self.assert_aliases(second)

    def test_deleted_standalone_wrapper_does_not_block_or_mutate_legacy_modules(self):
        old = self.legacy_window()
        self.shiboken.delete(old)
        self.legacy_launcher._window = self.legacy_ui._window = old
        second = self.launcher.show(self.session("integrated"))
        self.assertTrue(self.shiboken.isValid(second))
        self.assertIs(self.legacy_launcher._window, old)
        self.assertIs(self.legacy_ui._window, old)

    def test_component_launch_does_not_create_a_second_store_marker(self):
        forbidden = [REPO / "retarget" / ".lxtool" / name for name in ("manifest.json", "panel.json")]
        for path in forbidden:
            self.assertFalse(path.exists(), str(path))
        first = self.launcher.show(self.session("retarget"))
        self.assertIs(self.launcher.show(), first)
        for path in forbidden:
            self.assertFalse(path.exists(), str(path))
        self.assertEqual(self.window_factory.call_count, 1)

    def test_rig_ribbon_and_other_module_windows_are_unchanged(self):
        names = ("rig", "ribbon", "ui", "lxmaxretarget_extra")
        sentinels = {name: ModuleType(name) for name in names}
        for module in sentinels.values():
            module._window = object()
        before_windows = {name: module._window for name, module in sentinels.items()}
        with mock.patch.dict(sys.modules, sentinels):
            first = self.launcher.show(self.session("retarget"))
            self.assertIs(self.launcher.show(), first)
            for name, module in sentinels.items():
                self.assertIs(sys.modules[name], module)
                self.assertIs(module._window, before_windows[name])
        self.assertEqual(self.window_factory.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

