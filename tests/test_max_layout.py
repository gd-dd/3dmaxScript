"""Native source-loader regressions for target-safe, narrow Max launch panels.

No Max/provider launch, installation, credential read, or user profile access.
The fixture refreshes only an in-memory resource map while owners edit sources.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / 'acceptance/maxsuite-ui-2026-11-12'
for key in ('TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA'):
    directory = OUT / 'qa-environment' / key
    directory.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(directory)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT.parent / 'LXTools/src'))

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from native_panels import NativePanelHandle

PANEL_RESOURCES = ('ui/panel.py', 'ui/tools.json', 'ui/transport.py',
                   'ui/max_connection.py', 'bridge/LXMaxBridge.ms',
                   'bin/LXMaxSession.exe', '.lxtool/icon.png')
LONG_DETAIL = ('E:/角色资产/人形与表情/项目版本/长文件夹名称/' * 9
               + '英雄角色_测试场景_最终.max · PID 10001')
SESSIONS = [dict(id='max-one', title='3ds Max 2026 · 英雄角色长名称',
                 state='ready', detail=LONG_DETAIL),
            dict(id='max-two', title='3ds Max 2026 · 独立动画场景',
                 state='ready', detail='动画试验.max · PID 10002'),
            dict(id='max-unconnected', title='3ds Max 2026 · 已有未连接窗口',
                 state='unconnected', detail='已有角色.max · PID 10003')]


def source_tool(root=ROOT):
    manifest = json.loads((ROOT / '.lxtool/manifest.json').read_text('utf-8-sig'))
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
             for name in PANEL_RESOURCES}
    return dict(manifest, id='repo-1342543761', root=root, files=files,
                panelData=dict(type='native', apiVersion=1, entry='ui/panel.py'))


def select(panel, identity):
    for index in range(panel.list.topLevelItemCount()):
        item = panel.list.topLevelItem(index)
        if item.data(0, Qt.ItemDataRole.UserRole) == identity:
            panel.list.setCurrentItem(item)
            return
    raise AssertionError('Missing fixture target ' + identity)


def settle():
    app = QApplication.instance()
    for _ in range(4):
        app.processEvents()


def load_readonly_fonts(app):
    """Offscreen Qt does not always enumerate the Windows font registry."""
    loaded = []
    for name in ('msyh.ttc', 'msyhbd.ttc', 'msyhl.ttc', 'segoeui.ttf', 'seguisym.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.is_file():
            identity = QFontDatabase.addApplicationFont(str(path))
            assert identity >= 0, str(path)
            loaded.append(dict(path=str(path), families=QFontDatabase.applicationFontFamilies(identity)))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    assert QFontMetrics(app.font()).inFontUcs4(ord('骨')), 'CJK font missing'
    return loaded


class MaxLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        load_readonly_fonts(cls.app)

    def setUp(self):
        self.parent = QWidget()
        self.layout = QVBoxLayout(self.parent)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.handle = NativePanelHandle(source_tool(), OUT / 'unit-profile', self.parent)
        self.panel = self.handle.widget
        self.layout.addWidget(self.panel)
        self.panel.apply_response(dict(sessions=SESSIONS))
        select(self.panel, 'max-one')
        self.parent.resize(620, 640)
        self.parent.show()
        settle()

    def tearDown(self):
        self.handle.shutdown()
        self.parent.close()
        self.parent.deleteLater()
        settle()

    def test_native_construction_and_connection_navigation_are_idle(self):
        self.assertIsNone(self.panel.process.child)
        self.assertEqual(self.panel.process.state().value, 0)
        target = self.panel.active_id
        self.panel.connection_toggle.setFocus()
        QTest.keyClick(self.panel.connection_toggle, Qt.Key.Key_Space)
        settle()
        self.assertTrue(self.panel.connection_options.isVisible())
        QTest.keyClick(self.panel.connection_toggle, Qt.Key.Key_Space)
        settle()
        self.assertFalse(self.panel.connection_options.isVisible())
        self.assertEqual(self.panel.active_id, target)
        self.assertTrue(all(button.isEnabled() for button in self.panel.buttons.values()))
        self.assertIsNone(QApplication.activeModalWidget())
        self.assertIsNone(self.panel.process.child)

    def test_target_disappearance_unconnected_and_pending_never_redirect(self):
        self.panel.apply_response(dict(sessions=SESSIONS,
                                      pending=[dict(sessionId='max-one', toolId='retarget')]))
        self.assertFalse(self.panel.buttons['retarget'].isEnabled())
        self.assertTrue(self.panel.buttons['ribbon'].isEnabled())
        self.panel.apply_response(dict(sessions=SESSIONS[1:]))
        self.assertIsNone(self.panel.active_id)
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))
        select(self.panel, 'max-unconnected')
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))
        self.assertIn('首次连接', self.panel.target.text())
        self.panel.command = mock.Mock()
        self.panel.run_tool('retarget')
        self.panel.command.assert_not_called()

    def test_open_tool_passes_explicit_selected_target(self):
        self.panel.command = mock.Mock()
        self.panel.buttons['retarget'].click()
        self.panel.command.assert_called_once_with('run', sessionId='max-one', toolId='retarget')
        self.assertFalse(self.panel.buttons['retarget'].isEnabled())

    def test_primary_combo_and_secondary_details_keep_one_explicit_target(self):
        choice = self.panel.session_choice
        choice.setFocus()
        QTest.keyClick(choice, Qt.Key.Key_End)
        settle()
        self.assertEqual(choice.currentData(), 'max-unconnected')
        self.assertEqual(self.panel.active_id, 'max-unconnected')
        self.assertEqual(self.panel.list.currentItem().data(0, Qt.ItemDataRole.UserRole), 'max-unconnected')
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))
        choice.setCurrentIndex(choice.findData('max-two'))
        self.assertEqual(self.panel.active_id, 'max-two')
        self.panel.connection_toggle.click()
        select(self.panel, 'max-one')
        self.assertEqual(choice.currentData(), 'max-one')
        self.panel.connection_toggle.click()
        self.panel.apply_response(dict(sessions=SESSIONS[1:]))
        self.assertIsNone(choice.currentData())
        self.assertIsNone(self.panel.active_id)
        self.assertIsNone(self.panel.list.currentItem())
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))

    def test_inline_connection_results_preserve_target_without_modal(self):
        module = sys.modules[type(self.panel).__module__]
        self.panel.connection_toggle.click()
        with mock.patch.object(module.max_connection, 'connection_script',
                               return_value=OUT / 'fake-connection.ms') as script, \
             mock.patch.object(module.QApplication, 'clipboard') as clipboard:
            self.panel.connection_help()
            script.assert_called_once()
            clipboard.return_value.setText.assert_called_once()
        with mock.patch.object(module.max_connection, 'install', return_value=OUT / 'fake-plugin'):
            self.panel.install_connection()
        self.assertIn('已安装', self.panel.connection_note.text())
        self.assertEqual(self.panel.active_id, 'max-one')
        self.assertIsNone(QApplication.activeModalWidget())

    def test_scrolling_over_instance_choice_never_changes_command_target(self):
        choice = self.panel.session_choice
        for focused in (False, True):
            if focused:
                choice.setFocus()
            else:
                self.panel.connection_toggle.setFocus()
            settle()
            point = QPointF(choice.rect().center())
            event = QWheelEvent(point, QPointF(choice.mapToGlobal(point.toPoint())),
                                QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(choice, event)
            settle()
            self.assertEqual(choice.currentData(), 'max-one')
            self.assertEqual(self.panel.active_id, 'max-one')

    def test_narrow_and_large_sizes_keep_all_nine_tools_reachable(self):
        self.assertEqual(len(self.panel.buttons), 9)
        for width, height in ((380, 450), (620, 640), (980, 800)):
            self.parent.resize(width, height)
            settle()
            scroll = self.panel.scroll
            self.assertLessEqual(scroll.widget().width(), scroll.viewport().width() + 1)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            for identity, button in self.panel.buttons.items():
                scroll.ensureWidgetVisible(button, 0, 4)
                settle()
                rect = button.rect().translated(button.mapTo(scroll.viewport(), QPoint(0, 0)))
                self.assertTrue(scroll.viewport().rect().contains(rect), (width, identity, rect))
                self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()) + 24)
            self.assertEqual(self.panel.active_id, 'max-one')
            self.assertTrue(all(button.isEnabled() for button in self.panel.buttons.values()))
            self.assertIn(LONG_DETAIL, self.panel.target.toolTip())
            self.assertIn(LONG_DETAIL, self.panel.target.accessibleDescription())
            for _, buttons, label in self.panel.tool_grids:
                label_rect = label.rect().translated(label.mapTo(scroll.widget(), QPoint()))
                self.assertGreaterEqual(label.width(), label.fontMetrics().horizontalAdvance(label.text()))
                for button in buttons:
                    button_rect = button.rect().translated(button.mapTo(scroll.widget(), QPoint()))
                    self.assertFalse(label_rect.intersects(button_rect), (width, label.text(), button.text()))


if __name__ == '__main__':
    unittest.main()
