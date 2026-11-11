"""Offscreen workbench navigation, state and real clipping regression.

Historical fixtures are compiled in memory against retarget; the eight verified
historical test files remain read only. No pymxs, Max or network is used.
"""
from pathlib import Path
import copy
import hashlib
import io
import json
import os
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts" / "workbench_layout"
HISTORY = ROOT.parent / "LXMaxRetarget/tests/test_ui.py"
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_DISABLE_SHADER_DISK_CACHE"] = "1"
for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "XDG_CACHE_HOME"):
    location = ARTIFACTS / "environment" / key.lower()
    location.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(location)
sys.path.insert(0, str(ROOT))
from retarget import ui
from retarget.solver import CancelledError

QtCore, QtGui, QtWidgets = ui.QtCore, ui.QtGui, ui.QtWidgets
GEOMETRY = []


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


HISTORY_SHA256 = sha256(HISTORY)


def historical_fixtures():
    previous_path = list(sys.path)
    module = types.ModuleType("_retarget_workbench_verified_fixtures")
    virtual = ROOT / "retarget/tests/test_ui.py"
    module.__file__ = str(virtual)
    try:
        code = HISTORY.read_text(encoding="utf-8-sig").replace("lxmaxretarget", "retarget")
        exec(compile(code, str(virtual), "exec"), module.__dict__)
    finally:
        sys.path[:] = previous_path
    return module


FIXTURE = historical_fixtures()


def crowded_session(long_names=False):
    session = FIXTURE.FakeSession()
    for index in range(36):
        source_id, target_id = f"s-extra-{index}", f"t-extra-{index}"
        source = FIXTURE.node(source_id, f"源关节{index}", "s0")
        target = FIXTURE.node(target_id, f"目标关节{index}", "t0")
        session.source.append(source)
        session.target.append(target)
        session.chains.append(types.SimpleNamespace(
            id=f"extra-{index}", label=f"自定义链{index}", kind="custom",
            mapping_mode="auto", source=[source_id], target=[target_id]))
    if long_names:
        for side in ("source", "target"):
            for index, node in enumerate(getattr(session, side)):
                node.name = f"{side}_{index}_" + "非常长的关节显示名称_" * 32
                node.path = "/角色/" + f"{side}_完整层级/" * 90 + node.id
        for chain in session.chains:
            chain.label += "_" + "非常长的语义链标签_" * 24
    return session


class WorkbenchCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))

    def setUp(self):
        self.windows = []
        self.session = FIXTURE.FakeSession()
        self.window = self.new_window(self.session)

    def new_window(self, session):
        window = ui.RetargetWindow(session)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def tearDown(self):
        for window in reversed(self.windows):
            try:
                if hasattr(getattr(window, "session", None), "restore_error"):
                    window.session.restore_error = None
                window.close()
                window.deleteLater()
            except RuntimeError:
                pass
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.app.processEvents()

    def select_chain(self, identity, window=None):
        window = window or self.window
        for row in range(window.mapping.rowCount()):
            if window.mapping.item(row, 1).data(QtCore.Qt.UserRole) == identity:
                window.mapping.selectRow(row)
                self.app.processEvents()
                return
        self.fail("Missing mapped row: " + identity)

    def draft(self):
        window = self.window
        self.select_chain("arm_l")
        for combo, data in ((window.root_mode, "horizontal"), (window.scale_mode, "manual"),
                            (window.output_mode, "replace_range"), (window.mapping_mode, "direct")):
            combo.setCurrentIndex(combo.findData(data))
        for control, value in ((window.scale, 2.25), (window.start, -7), (window.end, 53),
                               (window.step, 3), (window.reference_frame, 5),
                               (window.rotation_weight, .37), (window.translation_weight, .12)):
            control.setValue(value)
        for control, value in zip(window.rotation_offsets, (11, -17, 29)):
            control.setValue(value)
        return copy.deepcopy(window.settings())

    def round_trip(self, window=None):
        window = window or self.window
        for callback in (lambda: window.show_nodes("source"), lambda: window.show_settings(0),
                         lambda: window.show_settings(1), window.show_report,
                         lambda: window.show_nodes("target"), window.show_mapping):
            callback()
            self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.mapping_page)

    def clipping_rect(self, widget, window):
        clip = window.rect()
        parent = widget.parentWidget()
        while parent is not None and parent is not window:
            if not parent.isVisibleTo(window):
                return QtCore.QRect()
            rect = QtCore.QRect(parent.mapTo(window, parent.rect().topLeft()),
                                parent.rect().size())
            clip = clip.intersected(rect)
            parent = parent.parentWidget()
        return clip

    def assert_fully_accessible(self, widget, window):
        self.assertTrue(widget.isVisibleTo(window), widget.objectName() or widget.text())
        rect = QtCore.QRect(widget.mapTo(window, QtCore.QPoint()), widget.size())
        self.assertFalse(rect.isEmpty())
        self.assertTrue(self.clipping_rect(widget, window).contains(rect),
                        (widget.text(), rect, self.clipping_rect(widget, window)))
        self.assertGreaterEqual(widget.width(),
                                widget.fontMetrics().horizontalAdvance(widget.text()) + 8)

    def main_actions(self, window):
        return [window.preflight_button, window.preview_button, window.restore_preview_button,
                window.restore_bake_button, window.bake_button]


class WorkbenchStateTests(WorkbenchCase):
    def test_secondary_round_trip_preserves_mapping_selected_chain_and_unsaved_draft(self):
        expected = self.draft()
        table = self.window.mapping
        settings_widgets = (self.window.scale, self.window.rotation_weight,
                            tuple(self.window.rotation_offsets))
        chains = copy.deepcopy(self.session.chains)
        self.assertEqual(self.session.settings, {})
        self.round_trip()
        self.assertIs(self.window.mapping, table)
        self.assertEqual((self.window.scale, self.window.rotation_weight,
                          tuple(self.window.rotation_offsets)), settings_widgets)
        self.assertEqual(self.window.current_chain().id, "arm_l")
        self.assertEqual(self.window.settings(), expected)
        self.assertEqual([vars(c) for c in self.session.chains], [vars(c) for c in chains])
        self.assertEqual(self.session.settings, {}, "Navigation must not silently save drafts")

    def test_per_chain_drafts_survive_other_chain_navigation_and_refresh(self):
        left = self.draft()["chain_overrides"]["arm_l"]
        self.select_chain("arm_r")
        self.window.rotation_weight.setValue(.81)
        self.window.rotation_offsets[1].setValue(43)
        right = copy.deepcopy(self.window.settings()["chain_overrides"]["arm_r"])
        self.round_trip()
        self.window.refresh()
        self.assertEqual(self.window.current_chain().id, "arm_r")
        self.assertEqual(self.window.settings()["chain_overrides"]["arm_r"], right)
        self.select_chain("arm_l")
        self.assertEqual(self.window.settings()["chain_overrides"]["arm_l"], left)
        self.assertEqual(self.window.rotation_weight.value(), .37)
        for control, expected in zip(self.window.rotation_offsets, (11, -17, 29)):
            self.assertAlmostEqual(control.value(), expected, places=2)

    def test_mapping_filter_node_selection_scroll_and_splitter_survive_return(self):
        self.window = self.new_window(crowded_session())
        window = self.window
        self.select_chain("extra-25")
        window.mapping.scrollToItem(window.mapping.item(28, 0))
        window.show_nodes()
        for side in ("source", "target"):
            panel = window.side_panels[side]
            panel.search.setText("extra")
            panel.nodes.item(30).setSelected(True)
            panel.nodes.scrollToItem(panel.nodes.item(30))
        window.splitter.setSizes([270, 410])
        self.app.processEvents()
        selections = {side: panel.selected_ids() for side, panel in window.side_panels.items()}
        scrolls = {side: panel.nodes.verticalScrollBar().value()
                   for side, panel in window.side_panels.items()}
        sizes = window.splitter.sizes()
        window.show_mapping()
        window.chain_filter.setText("自定义")
        map_scroll = window.mapping.verticalScrollBar().value()
        self.round_trip(window)
        self.assertEqual(window.current_chain().id, "extra-25")
        self.assertEqual(window.chain_filter.text(), "自定义")
        self.assertEqual(window.mapping.verticalScrollBar().value(), map_scroll)
        window.show_nodes()
        self.app.processEvents()
        self.assertEqual(window.splitter.sizes(), sizes)
        for side, panel in window.side_panels.items():
            self.assertEqual(panel.search.text(), "extra")
            self.assertEqual(panel.selected_ids(), selections[side])
            self.assertEqual(panel.nodes.verticalScrollBar().value(), scrolls[side])

    def test_page_navigation_keeps_live_preview_without_host_mutation(self):
        self.draft()
        self.window.preview()
        self.assertTrue(self.window._preview_valid)
        self.session.events.clear()
        self.round_trip()
        self.assertTrue(self.window._preview_valid)
        self.assertEqual(self.session.events, [])

    def test_visibility_uses_selected_chain_and_restores_preview_before_hiding(self):
        expected = self.draft()
        self.window.preview()
        self.round_trip()
        self.session.events.clear()
        self.window.visibility("only_chain")
        self.assertEqual(self.session.events[:2],
                         [("restore_preview",), ("visibility", "only_chain", "arm_l")])
        self.assertFalse(self.window._preview_valid)
        self.window.restore_visibility()
        self.assertEqual(self.session.events[-1], ("restore_visibility",))
        self.assertEqual(self.window.settings(), expected)
        self.assertEqual(self.window.current_chain().id, "arm_l")

    def test_preflight_opens_report_and_synchronizes_draft_without_losing_selection(self):
        expected = self.draft()
        self.window.preflight_button.click()
        self.app.processEvents()
        self.assertIs(self.window.pages.currentWidget(), self.window.settings_page)
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertTrue(self.window.report.isVisibleTo(self.window))
        self.assertIn("未映射右臂", self.window.report.toPlainText())
        self.assertEqual(self.session.settings, expected)
        self.window.show_mapping()
        self.assertEqual(self.window.current_chain().id, "arm_l")
        self.assertEqual(self.window.settings(), expected)

    def test_busy_disables_navigation_actions_and_close_requests_cancel(self):
        expected = self.draft()
        self.session.events.clear()
        with self.window.busy():
            self.assertTrue(self.window._busy)
            for control in self.main_actions(self.window) + list(self.window.navigation_buttons.values()):
                self.assertFalse(control.isEnabled(), control.text())
                control.click()
            event = QtGui.QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertTrue(self.window._cancel)
            self.assertEqual(self.session.events, [])
        self.assertFalse(self.window._busy)
        self.assertTrue(self.window.content.isEnabled())
        self.assertEqual(self.window.settings(), expected)
        self.assertEqual(self.window.current_chain().id, "arm_l")

    def test_cancel_during_event_pumping_preserves_draft_and_reenables_workbench(self):
        expected = self.draft()
        def cancel_during_bake(start, end, step, settings, progress, cancelled):
            self.assertTrue(self.window._busy)
            self.assertEqual(settings, expected)
            progress(1, 3, "采样")
            event = QtGui.QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertTrue(cancelled())
            raise CancelledError("目标已恢复")
        self.session.bake = cancel_during_bake
        self.window.bake_button.click()
        self.assertIn("烘焙已取消", self.window.status.text())
        self.assertNotIn("成功", self.window.status.text())
        self.assertFalse(self.window._busy)
        self.assertTrue(self.window.content.isEnabled())
        self.round_trip()
        self.assertEqual(self.window.settings(), expected)
        self.assertEqual(self.window.current_chain().id, "arm_l")

    def test_failed_restore_keeps_preview_and_draft_and_blocks_capture_and_close(self):
        expected = self.draft()
        self.window.preview()
        self.session.events.clear()
        self.session.restore_error = "恢复失败保留现场"
        self.window.capture("target")
        self.assertTrue(self.window._preview_valid)
        self.assertEqual(self.session.events, [])
        self.assertIn("恢复失败保留现场", self.window.status.text())
        self.assertIs(self.window.pages.currentWidget(), self.window.settings_page)
        self.round_trip()
        self.assertEqual(self.window.settings(), expected)
        event = QtGui.QCloseEvent()
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.window._preview_valid)

    def test_failed_bake_opens_report_and_keeps_existing_draft(self):
        expected = self.draft()
        self.session.bake_error = "宿主写入失败并已恢复"
        self.window.bake_button.click()
        self.app.processEvents()
        self.assertIn("烘焙未完成", self.window.status.text())
        self.assertNotIn("成功", self.window.status.text())
        self.assertIs(self.window.pages.currentWidget(), self.window.settings_page)
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertTrue(self.window.report.isVisibleTo(self.window))
        self.round_trip()
        self.assertEqual(self.window.settings(), expected)

    def test_cancelled_preset_dialogs_do_not_save_or_discard_workbench_draft(self):
        expected = self.draft()
        self.session.events.clear()
        with mock.patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")):
            self.window.load_preset()
        with mock.patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")):
            self.window.save_preset()
        self.round_trip()
        self.assertEqual(self.window.settings(), expected)
        self.assertEqual(self.session.settings, {})
        self.assertEqual(self.session.events, [])

    def test_actual_session_preview_bake_recovery_and_visibility_survive_pages(self):
        session, host = FIXTURE.real_facade()
        window = self.new_window(session)
        source_before = copy.deepcopy(host.controllers["source"])
        target_before = host.controllers["target"]
        hidden_before = dict(host.hidden)
        window.output_mode.setCurrentIndex(window.output_mode.findData("replace_range"))
        window.preview()
        active_preview = host.controllers["target"]
        self.assertIsNot(active_preview, target_before)
        self.round_trip(window)
        self.assertIs(host.controllers["target"], active_preview)
        self.assertIsNotNone(session._preview)
        window.restore_preview()
        self.assertIs(host.controllers["target"], target_before)
        window.bake()
        self.assertIn("烘焙成功", window.status.text())
        self.round_trip(window)
        window.restore_last_bake()
        self.assertIs(host.controllers["target"], target_before)
        window.visibility("only_source")
        self.round_trip(window)
        window.restore_visibility()
        self.assertEqual(host.hidden, hidden_before)
        self.assertEqual(host.controllers["source"], source_before)


    def test_mapping_capture_buttons_keep_source_and_target_routing_after_return(self):
        self.round_trip()
        self.session.events.clear()
        self.window.capture_buttons["source"].click()
        self.window.capture_buttons["target"].click()
        self.assertEqual([event for event in self.session.events if event[0] == "capture"],
                         [("capture", "source", True), ("capture", "target", True)])

    def test_mapping_summary_keeps_full_updated_range_root_and_output_hint(self):
        self.draft()
        self.round_trip()
        summary = self.window.range_summary
        text = summary.text()
        for expected in ("-7", "53", "水平", "覆盖"):
            self.assertIn(expected, text)
        self.assertIn(text, summary.toolTip())

    def test_wheel_over_unfocused_settings_keeps_values_and_page_still_scrolls(self):
        window = self.window
        window.resize(760, 460)
        window.show_settings(0)
        self.app.processEvents()
        scroll = window.basic_scroll
        window.tabs.tabBar().setFocus()
        values = (window.reference_frame.value(), window.scale.value(),
                  window.start.value(), window.output_mode.currentData())
        for control in (window.reference_frame, window.scale, window.start, window.output_mode):
            scroll.ensureWidgetVisible(control)
            self.app.processEvents()
            self.assertFalse(control.hasFocus())
            center = control.rect().center()
            event = QtGui.QWheelEvent(QtCore.QPointF(center),
                                     QtCore.QPointF(control.mapToGlobal(center)),
                                     QtCore.QPoint(), QtCore.QPoint(0, -120),
                                     QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
                                     QtCore.Qt.NoScrollPhase, False)
            self.app.sendEvent(control, event)
            self.app.processEvents()
            self.assertEqual((window.reference_frame.value(), window.scale.value(),
                              window.start.value(), window.output_mode.currentData()), values)
        bar = scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        viewport = scroll.viewport()
        center = viewport.rect().center()
        event = QtGui.QWheelEvent(QtCore.QPointF(center),
                                 QtCore.QPointF(viewport.mapToGlobal(center)),
                                 QtCore.QPoint(), QtCore.QPoint(0, -120),
                                 QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
                                 QtCore.Qt.NoScrollPhase, False)
        self.app.sendEvent(viewport, event)
        self.app.processEvents()
        self.assertGreater(bar.value(), 0, "Wheel must still scroll the settings page")
        scroll.ensureWidgetVisible(window.output_mode)
        self.app.processEvents()
        rect = QtCore.QRect(window.output_mode.mapTo(window, QtCore.QPoint()),
                            window.output_mode.size())
        self.assertTrue(self.clipping_rect(window.output_mode, window).contains(rect))

class WorkbenchLayoutTests(WorkbenchCase):
    def test_narrow_mapping_keeps_primary_actions_and_usable_mapping_viewport(self):
        window = self.new_window(crowded_session())
        window.show_mapping()
        for width, height in ((760, 460), (800, 500)):
            with self.subTest(size=(width, height)):
                window.resize(width, height)
                self.app.processEvents()
                self.assertEqual((window.width(), window.height()), (width, height))
                self.assertLessEqual(window.minimumSizeHint().width(), width)
                self.assertLessEqual(window.minimumSizeHint().height(), height)
                for action in self.main_actions(window):
                    self.assert_fully_accessible(action, window)
                viewport = window.mapping.viewport()
                self.assertTrue(viewport.isVisibleTo(window))
                full_rows = sum(not window.mapping.isRowHidden(row) and viewport.rect().contains(
                    window.mapping.visualRect(window.mapping.model().index(row, 0)))
                    for row in range(window.mapping.rowCount()))
                self.assertGreaterEqual(full_rows, 2, "Mapping needs at least two complete rows")
                self.assertGreaterEqual(viewport.width(), 300)
                GEOMETRY.append({"page": "mapping", "size": [width, height],
                                 "viewport": [viewport.width(), viewport.height()],
                                 "completeRows": full_rows})

    def test_all_secondary_pages_keep_primary_actions_inside_real_ancestor_clip(self):
        window = self.window
        for width, height in ((760, 460), (800, 500)):
            window.resize(width, height)
            for label, callback in (
                ("mapping", window.show_mapping), ("nodes", window.show_nodes),
                ("basic", lambda: window.show_settings(0)),
                ("advanced", lambda: window.show_settings(1)), ("report", window.show_report)):
                with self.subTest(size=(width, height), page=label):
                    callback()
                    self.app.processEvents()
                    self.assertEqual((window.width(), window.height()), (width, height))
                    for action in self.main_actions(window):
                        self.assert_fully_accessible(action, window)
                    if label == "nodes":
                        for panel in window.side_panels.values():
                            self.assertGreaterEqual(panel.nodes.viewport().width(), 160)
                            self.assertGreaterEqual(panel.nodes.viewport().height(), 90)

    def test_long_names_and_paths_do_not_inflate_window_and_keep_full_tooltips(self):
        session = crowded_session(long_names=True)
        window = self.new_window(session)
        for width, height in ((760, 460), (800, 500)):
            window.show_mapping()
            window.resize(width, height)
            self.app.processEvents()
            self.assertEqual((window.width(), window.height()), (width, height))
            self.assertLessEqual(window.minimumSizeHint().width(), width)
            for action in self.main_actions(window):
                self.assert_fully_accessible(action, window)
            for row, chain in enumerate(session.chains):
                for column, side in ((0, "source"), (2, "target")):
                    nodes = {node.id: node for node in getattr(session, side)}
                    for identity in getattr(chain, side):
                        self.assertIn(nodes[identity].name, window.mapping.item(row, column).toolTip())
                self.assertIn(chain.label, window.mapping.item(row, 1).toolTip())
            window.show_nodes()
            self.app.processEvents()
            for side, panel in window.side_panels.items():
                self.assertGreaterEqual(panel.nodes.viewport().width(), 160)
                for index, node in enumerate(getattr(session, side)):
                    self.assertIn(node.path, panel.nodes.item(index).toolTip())
                    self.assertEqual(panel.nodes.item(index).data(QtCore.Qt.UserRole), node.id)
            self.assertLessEqual(window.minimumSizeHint().width(), width)


    def test_secondary_settings_can_scroll_each_control_fully_into_view(self):
        window = self.window
        for width, height in ((760, 460), (800, 500)):
            window.resize(width, height)
            for tab, scroll, controls in (
                (0, window.basic_scroll, (window.reference_frame, window.source_ref, window.target_ref,
                                         window.root_mode, window.scale_mode, window.scale,
                                         window.start, window.end, window.step, window.output_mode)),
                (1, window.advanced_scroll, (window.mapping_mode, window.rotation_weight,
                                            window.translation_weight, *window.rotation_offsets))):
                window.show_settings(tab)
                self.app.processEvents()
                self.assertTrue(scroll.widgetResizable())
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                for control in controls:
                    with self.subTest(size=(width, height), tab=tab, control=type(control).__name__):
                        scroll.ensureWidgetVisible(control)
                        self.app.processEvents()
                        rect = QtCore.QRect(control.mapTo(window, QtCore.QPoint()), control.size())
                        self.assertTrue(control.isVisibleTo(window))
                        self.assertTrue(self.clipping_rect(control, window).contains(rect),
                                        (rect, self.clipping_rect(control, window)))
                for action in self.main_actions(window):
                    self.assert_fully_accessible(action, window)

class SecondaryDialogTests(WorkbenchCase):
    def rebind_fixture(self):
        session = crowded_session(long_names=True)
        issues = [
            {"side": "source", "preset_id": "old-source", "name": "原预设源骨名_" * 70,
             "candidates": ["s1"], "reason": "名称相似但完整层级不同，必须明确确认_" * 15},
            {"side": "target", "preset_id": "old-target", "name": "原预设目标骨名_" * 70,
             "candidates": ["t1"], "reason": "节点重命名，需要人工重绑定_" * 15},
        ]
        dialog = ui.RebindDialog(session, issues)
        self.windows.append(dialog)
        dialog.show()
        self.app.processEvents()
        return session, issues, dialog

    def test_rebind_long_names_paths_and_candidate_popups_stay_bounded_with_tooltips(self):
        session, issues, dialog = self.rebind_fixture()
        self.assertEqual(dialog.bindings(), ({}, {}))
        for width, height in ((760, 460), (800, 500)):
            with self.subTest(size=(width, height)):
                dialog.resize(width, height)
                self.app.processEvents()
                self.assertEqual((dialog.width(), dialog.height()), (width, height))
                self.assertLessEqual(dialog.minimumSizeHint().width(), width)
                for action in dialog.findChildren(QtWidgets.QPushButton):
                    self.assert_fully_accessible(action, dialog)
                for row, (issue, combo) in enumerate(zip(issues, dialog.combos)):
                    self.assertEqual(dialog.table.item(row, 1).toolTip(), issue["name"])
                    self.assertEqual(dialog.table.item(row, 3).toolTip(), issue["reason"])
                    self.assertGreaterEqual(combo.width(), 160)
                    rect = QtCore.QRect(combo.mapTo(dialog, QtCore.QPoint()), combo.size())
                    self.assertTrue(self.clipping_rect(combo, dialog).contains(rect))
                    for index, node in enumerate(getattr(session, issue["side"]), 1):
                        self.assertEqual(combo.itemData(index), node.id)
                        tooltip = combo.itemData(index, QtCore.Qt.ToolTipRole)
                        self.assertIn(node.name, tooltip)
                        self.assertIn(node.path, tooltip)
                    combo.setCurrentIndex(2)
                    self.assertIn(getattr(session, issue["side"])[1].path, combo.toolTip())
                    self.assertEqual(combo.lineEdit().toolTip(), combo.toolTip())
                    combo.showPopup()
                    self.app.processEvents()
                    self.assertLessEqual(combo.view().window().width(), combo.width())
                    combo.hidePopup()
                    combo.completer().setCompletionPrefix(issue["side"] + "_完整层级")
                    self.assertGreater(combo.completer().completionCount(), 0)

    def test_rebind_editable_search_never_applies_stale_current_data(self):
        session, issues, dialog = self.rebind_fixture()
        combo = dialog.combos[0]
        combo.setCurrentIndex(combo.findData("s1"))
        self.assertEqual(dialog.bindings(), ({"old-source": "s1"}, {}))
        combo.lineEdit().setText("仅用于搜索的名称_尚未选择候选")
        self.app.processEvents()
        self.assertEqual(combo.currentData(), "s1", "Exercise Qt's retained old selection")
        self.assertEqual(dialog.bindings(), ({}, {}), "Typed search text is not an identity")
        combo.setCurrentIndex(combo.findData("s2"))
        self.assertEqual(dialog.bindings(), ({"old-source": "s2"}, {}))
        self.assertEqual(session.events, [])

    def test_suggestion_and_rebind_are_readable_without_inherited_light_parent(self):
        saved = self.app.palette()
        dark = QtGui.QPalette(saved)
        for role in (QtGui.QPalette.Window, QtGui.QPalette.Base, QtGui.QPalette.Button):
            dark.setColor(role, QtGui.QColor("#303030"))
        for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
            dark.setColor(role, QtGui.QColor("#d5d5d5"))
        self.app.setPalette(dark)
        try:
            session, issues, rebind = self.rebind_fixture()
            reason = "完整候选原因_" * 50
            suggestions = [{"chain_id": "arm_l", "source": ["s1"], "target": ["t1"],
                            "confidence": .95, "reason": reason}]
            def lookup(side, identity):
                return next(node.name for node in getattr(session, side) if node.id == identity)
            suggestion = ui.SuggestionDialog(suggestions, session.chains, lookup)
            self.windows.append(suggestion)
            suggestion.show()
            self.app.processEvents()
            for dialog in (rebind, suggestion):
                self.assertGreater(dialog.grab().toImage().pixelColor(3, 3).lightness(), 220)
                self.assertGreater(dialog.table.palette().color(QtGui.QPalette.Base).lightness(), 220)
                for action in dialog.findChildren(QtWidgets.QPushButton):
                    self.assert_fully_accessible(action, dialog)
            self.assertEqual(suggestion.table.item(0, 5).toolTip(), reason)
            self.assertEqual(suggestion.table.item(0, 2).toolTip(), lookup("source", "s1"))
            self.assertEqual(suggestion.chosen(), [])
        finally:
            self.app.setPalette(saved)

def main():
    before = sha256(ROOT / "retarget/ui.py")
    log = io.StringIO()
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(case)
        for case in (WorkbenchStateTests, WorkbenchLayoutTests, SecondaryDialogTests))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    tag = scale.replace(".", "_")
    report = {
        "status": "passed" if result.wasSuccessful() else "failed",
        "scope": "real Qt offscreen workbench state and clipping; no Max or screen control",
        "testsRun": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "qtScaleFactor": scale, "qtPlatform": os.environ["QT_QPA_PLATFORM"],
        "devicePixelRatio": QtWidgets.QApplication.instance().devicePixelRatio(),
        "uiSha256Before": before, "uiSha256After": sha256(ROOT / "retarget/ui.py"),
        "historicalFixtureSha256": HISTORY_SHA256,
        "historicalFixtureUnchanged": HISTORY_SHA256 == sha256(HISTORY),
        "geometry": GEOMETRY, "python": sys.executable,
        "environment": {key: os.environ[key] for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE")},
        "maxStarted": False, "screenControlled": False,
    }
    (ARTIFACTS / f"workbench-{tag}.log").write_text(log.getvalue(), encoding="utf-8")
    (ARTIFACTS / f"workbench-{tag}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(log.getvalue())
    print("WORKBENCH_LAYOUT", report["status"], result.testsRun, scale)
    return 0 if result.wasSuccessful() and report["historicalFixtureUnchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
