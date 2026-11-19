"""Real Qt combo popup, long session identities, and target-safe refresh tests."""
import json
import sys
import unittest
from unittest import mock
from test_max_layout import (QApplication, QWidget, QVBoxLayout, Qt, OUT, NativePanelHandle,
                             source_tool, load_readonly_fonts, select, settle, SESSIONS)
from PySide6.QtCore import QRect, QPoint
from PySide6.QtTest import QTest


class SessionChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion');load_readonly_fonts(cls.app)

    def setUp(self):
        self.host = QWidget();self.host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        layout = QVBoxLayout(self.host);layout.setContentsMargins(0, 0, 0, 0)
        self.handle = NativePanelHandle(source_tool(), OUT / 'choice-profile', self.host)
        self.panel = self.handle.widget;layout.addWidget(self.panel)
        self.sessions = [dict(id='instance-' + str(i), title='英雄角色_身体服装与表情_%02d.max' % i,
                             detail='PID %d · 场景窗口_%02d - Autodesk 3ds Max 2026' % (10000+i, i),
                             scene='E:/角色项目/非常长的目录与多个版本/' * 5 + '英雄角色_身体服装与表情_%02d.max' % i,
                             pid=10000+i, version='2026', state='ready') for i in range(16)]
        self.panel.apply_response(dict(sessions=self.sessions));select(self.panel, 'instance-0')
        self.host.resize(380, 500);self.host.show();settle()
        self.choice = self.panel.session_choice
        self.panel.scroll.ensureWidgetVisible(self.choice);settle()

    def tearDown(self):
        self.choice.hidePopup();self.handle.shutdown();self.host.close();self.host.deleteLater();settle()

    def popup(self):
        self.choice.view().window().setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.choice.showPopup();settle()
        return self.choice.view().window()

    def test_closed_choice_has_two_readable_identity_lines_and_full_description(self):
        self.assertGreaterEqual(self.choice.width(), 280)
        self.assertGreaterEqual(self.choice.height(), self.choice.fontMetrics().height()*2 + 16)
        lines = self.choice.currentData(Qt.ItemDataRole.UserRole+1)
        self.assertEqual(lines[0], self.sessions[0]['title'])
        for text in ('3ds Max 2026', 'PID 10000', '已连接'): self.assertIn(text, lines[1])
        self.assertIn(self.sessions[0]['scene'], self.choice.toolTip())
        self.assertIn('PID 10000', self.choice.accessibleDescription())
        self.assertEqual(self.panel.process.state().value, 0)

    def test_popup_has_screen_bounded_width_and_scrollable_multiline_rows(self):
        for width in (380, 620, 980, 380):
            self.host.resize(width, 600);settle()
            popup = self.popup();view = self.choice.view()
            self.assertGreaterEqual(popup.width(), min(460, self.choice.screen().availableGeometry().width()-16))
            self.assertTrue(self.choice.screen().availableGeometry().contains(popup.geometry()))
            self.assertGreaterEqual(view.viewport().width(), 400)
            index = self.choice.model().index(1, 0)
            self.assertGreaterEqual(view.visualRect(index).height(), self.choice.fontMetrics().height()*3+16)
            self.assertGreater(view.verticalScrollBar().maximum(), 0)
            last = self.choice.model().index(self.choice.count()-1, 0)
            view.scrollTo(last);settle()
            self.assertTrue(view.viewport().rect().contains(view.visualRect(last).center()))
            QTest.keyClick(view, Qt.Key.Key_Escape);settle()
            self.assertEqual(self.panel.active_id, 'instance-0')

    def test_popup_geometry_handles_small_and_negative_origin_screens(self):
        for area in (QRect(-1280, 0, 1280, 720), QRect(0, 0, 320, 240), QRect(100, -900, 600, 900)):
            bounds = self.choice.popup_geometry(area)
            self.assertTrue(area.adjusted(8,8,-8,-8).contains(bounds), (area,bounds))

    def test_popup_commit_and_refresh_never_redirect_a_missing_target(self):
        self.popup();view = self.choice.view()
        index = self.choice.model().index(3,0);view.scrollTo(index);settle()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center());settle()
        self.assertEqual(self.panel.active_id, 'instance-2')
        self.panel.apply_response(dict(sessions=self.sessions[3:]));settle()
        self.assertIsNone(self.panel.active_id)
        self.assertIsNone(self.choice.currentData())
        self.assertFalse(any(button.isEnabled() for button in self.panel.buttons.values()))
        self.popup();self.choice.hidePopup();settle()
        self.assertIsNone(self.panel.active_id)

    def test_old_provider_records_and_explicit_refresh_remain_compatible(self):
        self.panel.apply_response(dict(sessions=SESSIONS));select(self.panel,'max-one')
        lines = self.choice.currentData(Qt.ItemDataRole.UserRole+1)
        self.assertIn('2026', lines[1]);self.assertIn('PID 10001', lines[1])
        self.panel.command = mock.Mock()
        self.panel.connect_button.click()
        self.panel.command.assert_called_once_with('hello')
        self.assertIn('自动连接', self.panel.status.text())
        self.assertEqual(self.panel.active_id, 'max-one')

    def test_per_instance_version_is_independent_of_new_max_executable(self):
        self.panel.path.setText('E:/Applications/3ds Max 2026/3dsmax.exe')
        current=dict(self.sessions[0], version='2023', pid=14567)
        self.panel.apply_response(dict(sessions=[current]))
        lines=self.choice.currentData(Qt.ItemDataRole.UserRole+1)
        self.assertIn('3ds Max 2023', lines[1])
        self.assertIn('PID 14567', lines[1])
        self.assertNotIn('2026', lines[1])
        self.assertEqual(self.panel.active_id, 'instance-0')

    def test_capture_offscreen_popup_and_closed_choice(self):
        evidence = []
        for width in (380, 620):
            self.host.resize(width, 640);settle()
            self.panel.scroll.verticalScrollBar().setValue(0);settle()
            self.assertTrue(self.host.grab().save(str(OUT / ('choice-closed-%d.png' % width))))
            popup = self.popup()
            self.assertTrue(popup.grab().save(str(OUT / ('choice-popup-%d.png' % width))))
            evidence.append(dict(hostWidth=width, choiceWidth=self.choice.width(), choiceHeight=self.choice.height(),
                                 popup=[popup.x(),popup.y(),popup.width(),popup.height()],
                                 rowHeight=self.choice.view().sizeHintForRow(1),
                                 scrollMaximum=self.choice.view().verticalScrollBar().maximum(),
                                 activeId=self.panel.active_id, scope='Qt offscreen; synthetic sessions; no provider or Max started'))
            self.choice.hidePopup();settle()
        (OUT / 'session-choice-layout.json').write_text(json.dumps(evidence,indent=2),'utf-8')


if __name__=='__main__':unittest.main()
