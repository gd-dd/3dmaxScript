"""Host-free layout fixtures and geometric checks for the real rig workbench.

The render harness imports these helpers from an independent DPI process.
Fixtures describe synthetic scene/Skin data; no Max module is imported.
"""
import copy
import os
from pathlib import Path
import sys
import unittest

OUT = Path('E:/project/LXTools/acceptance/rigskin-ui-2026-11-12')
for key in ('TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE'):
    path = Path(os.environ.get('LX_RIG_LAYOUT_ENV', str(OUT / 'unit-env'))) / key
    path.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(path)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.dont_write_bytecode = True

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QLabel,
    QLineEdit, QScrollArea, QStyle, QStyleOptionButton, QTreeWidgetItem)


def node(identity, name, category, parent=None, role='', skins=None):
    return dict(id=identity, name=name, category=category, workflow=category,
                role=role, parent=parent, geometry=category == 'models', bone=category == 'bones',
                hidden=False, boxMode=False, showLinks=False, selected=False,
                skins=skins or [], **{'class': 'Editable_Poly' if category == 'models' else
                                     'BoneGeometry' if category == 'bones' else 'Point'})


def scene_fixture():
    skins = [dict(index=i, handle='skin-' + str(i), name='Skin_%d__最终角色身体与服装权重_ProductionCharacter_Body_Clothes_Deformation_EditableCopy' % i) for i in range(2)]
    nodes = [node('model-' + str(i), '角色_%02d_最终身体服装模型_Character_Body_Costume_HighDetail_RenderMesh_左右对称检查' % i,
                  'models', skins=copy.deepcopy(skins)) for i in range(6)]
    nodes.append(node('root', '总控制器_MasterRoot_角色整体移动旋转缩放_ProductionCharacter_Master_Control', 'controls', role='Root'))
    for i in range(24):
        nodes.append(node('bone-' + str(i), '角色骨骼_%02d_Left_UpperArm_Finger_Deformation_ExtraLongProductionJointName' % i,
                          'bones', 'bone-' + str(i - 1) if i % 6 else 'root', 'L_UpperArm_%02d' % (i + 1)))
    nodes += [node('control-' + str(i), '控制器_%02d_左手IK与肘部方向辅助_L_Hand_IK_ProductionCharacter_Controller' % i,
                   'controls', 'root', 'Controller') for i in range(8)]
    return dict(scene='layout-fixture-scene', nodes=nodes,
                viewport=dict(wireframe=False, edges=True, brackets=True))


def skin_fixture():
    scene = scene_fixture()
    bones = [n for n in scene['nodes'] if n['category'] == 'bones'][:10]
    values = [.32, .23, .17, .10, .07, .04, .03, .02, .015, .005]
    return dict(profile=dict(schema=1, locked=['1'], pairs={'1': '2', '2': '1'},
                             humanoid={'leftUpperArm': 'bone-0', 'leftLowerArm': 'bone-1'},
                             face={'jaw': 'bone-5'}), count=98342, selectedCount=128, vertex=42817,
                bones=[dict(id=str(i + 1), node=n['id'], name=n['name']) for i, n in enumerate(bones)],
                weights={str(i + 1): v for i, v in enumerate(values)},
                snapshots=[dict(id='fixture-snapshot-' + str(i), label='蒙皮备份_第%d次平滑前_角色身体与衣服的权重检查' % i) for i in range(3)])


class Owner:
    """Only readonly callbacks. Unexpected UI mutations fail the test."""
    def __init__(self):
        self.requests = []

    def rig_command(self, request, callback):
        self.requests.append(copy.deepcopy(request))
        action = request['action']
        if action == 'scene.inspect': data = scene_fixture()
        elif action == 'skin.inspect': data = skin_fixture()
        elif action == 'profile.inspect': data = {'profile': skin_fixture()['profile']}
        else: raise AssertionError('Layout fixture unexpectedly requested host mutation: ' + action)
        callback(dict(ok=True, data=data))
        return 'fixture-request-' + str(len(self.requests))


def build_fixture():
    from rig.workflow_ui import WorkflowWorkbench
    from rig.theme import STYLE, apply_popup_palette
    from rig.selection_ui import items
    app = QApplication.instance() or QApplication([])
    # Offscreen Qt does not always enumerate Windows fonts. Read installed C:
    # fonts only; registration is in this process and creates no font files.
    if not getattr(app, '_lx_layout_fonts', False):
        for font_path in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/msyhbd.ttc'):
            if Path(font_path).is_file(): QFontDatabase.addApplicationFont(font_path)
        app._lx_layout_fonts = True
    widget = WorkflowWorkbench(Owner())
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.setFont(QFont('Microsoft YaHei UI', 9))
    widget.setStyleSheet(STYLE)
    apply_popup_palette(widget)
    widget.set_target('layout-fixture-scene')
    widget.load_scene(scene_fixture())
    widget.mesh.setCurrentIndex(widget.mesh.findData('model-0'))
    widget.skin.setCurrentIndex(1)
    for key, refs in [('models', {'model-0', 'model-1'}), ('bones', {'bone-0', 'bone-1'}), ('controls', {'control-0'})]:
        tree = widget.category_trees[key]
        tree.blockSignals(True)
        for item in items(tree): item.setSelected(item.data(0, Qt.ItemDataRole.UserRole) in refs)
        tree.blockSignals(False)
    widget.load_skin(skin_fixture())
    widget.set_child_parent(dict(node='bone-0', name=scene_fixture()['nodes'][7]['name']))
    widget.child_name.setText('自定义骨骼_Custom_Finger_Extra_Long_Name')
    widget.child_start.setText('12.5, -8.25, 134.125')
    widget.child_direction.setText('20.0, -10.0, 145.0')
    widget.child_length.setValue(7.25)
    weights = {b['node']: skin_fixture()['weights'][b['id']] for b in skin_fixture()['bones']}
    for item in items(widget.category_trees['bones']):
        item.setText(2, '%.3f' % weights.get(item.data(0, Qt.ItemDataRole.UserRole), 0))
    for item in items(widget.category_trees['models']):
        item.setText(2, '0.550' if item.data(0, Qt.ItemDataRole.UserRole) in ('model-0', 'model-1') else '—')
    widget.vertex_values.clear()
    for index in range(32):
        widget.vertex_values.addTopLevelItem(QTreeWidgetItem([scene_fixture()['nodes'][index % 2]['name'], str(42817 + index), '%.6f' % (.55 + (index % 5) * .035)]))
    widget.weight_summary.setText('角色身体：所选骨骼合计 0.550（128 顶点均值）\n角色服装：所选骨骼合计 0.625（64 顶点均值）')
    for timer in widget.findChildren(QTimer): timer.stop()
    widget.show()  # offscreen platform + WA_DontShowOnScreen, never a native UI.
    settle(widget)
    return widget


def settle(widget, count=3):
    app = QApplication.instance()
    for _ in range(count):
        widget.ensurePolished()
        if widget.layout(): widget.layout().activate()
        app.processEvents()


def visible_rect(widget, root):
    rect = QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())
    parent = widget.parentWidget()
    while parent is not None:
        rect = rect.intersected(QRect(parent.mapTo(root, QPoint(0, 0)), parent.size()))
        if parent is root: break
        parent = parent.parentWidget()
    return rect


def widget_rect(widget, root):
    point = widget.mapTo(root, QPoint(0, 0))
    return [point.x(), point.y(), widget.width(), widget.height()]


def measure_reachability(widget):
    """Try normal scroll navigation, not visibility overrides or button clicks."""
    scrolls = widget.findChildren(QScrollArea)
    saved = [(s, s.horizontalScrollBar().value(), s.verticalScrollBar().value()) for s in scrolls]
    buttons = [b for b in widget.findChildren(QAbstractButton) if b.text() and b.isVisibleTo(widget)]
    result = []
    try:
        for button in buttons:
            parent = button.parentWidget()
            ancestors = []
            while parent is not None and parent is not widget:
                if isinstance(parent, QScrollArea): ancestors.append(parent)
                parent = parent.parentWidget()
            for scroll in ancestors:
                scroll.ensureWidgetVisible(button, 3, 3)
            settle(widget, 1)
            visible = visible_rect(button, widget)
            whole = visible.width() >= button.width() - 2 and visible.height() >= button.height() - 2
            center = button.mapTo(widget, button.rect().center())
            result.append(dict(text=button.text(), fullyReachable=whole,
                               centerReachable=visible.contains(center), rect=widget_rect(button, widget),
                               visible=[visible.x(), visible.y(), visible.width(), visible.height()],
                               scrollAncestors=[dict(viewport=widget_rect(s.viewport(), widget),
                                  position=s.verticalScrollBar().value(), maximum=s.verticalScrollBar().maximum()) for s in ancestors]))
    finally:
        for scroll, x, y in saved:
            scroll.horizontalScrollBar().setValue(x)
            scroll.verticalScrollBar().setValue(y)
        settle(widget, 1)
    return result


def measure_layout(widget, requested=None):
    result = dict(actual=[widget.width(), widget.height()], requested=requested,
                  minimumHint=[widget.minimumSizeHint().width(), widget.minimumSizeHint().height()],
                  dpi=float(widget.devicePixelRatioF()), step=widget.steps.currentIndex(),
                  clippedButtonText=[], clippedLabels=[], regions={}, combos=[], treeColumns=[])
    for name in ('body', 'tabs', 'shared_scene', 'object_frame', 'category_split', 'vertex_values'):
        target = getattr(widget, name, None)
        if target is not None and target.isVisibleTo(widget): result['regions'][name] = widget_rect(target, widget)
    page = widget.tabs.currentWidget()
    if isinstance(page, QScrollArea): result['regions']['activeViewport'] = widget_rect(page.viewport(), widget)
    for index, scroll in enumerate(s for s in widget.findChildren(QScrollArea) if s.isVisibleTo(widget)):
        result['regions']['scrollViewport' + str(index)] = widget_rect(scroll.viewport(), widget)
    for button in widget.findChildren(QAbstractButton):
        if not button.text() or not button.isVisibleTo(widget): continue
        text = button.text().replace('&', '')
        if button.inherits('QPushButton'):
            option = QStyleOptionButton(); button.initStyleOption(option)
            content = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
            width = content.width()
        else:
            option = QStyleOptionButton(); button.initStyleOption(option)
            content = button.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, button)
            width = content.width()
        wrapped = type(button).__name__ in ('WrapButton', 'WrapCheckBox')
        needed = max(button.fontMetrics().horizontalAdvance(line) for line in text.splitlines())
        if wrapped:
            painted = content.adjusted(4, 2, -4, -2) if type(button).__name__ == 'WrapButton' else content
            bounds = button.fontMetrics().boundingRect(QRect(0, 0, max(1, painted.width()), 10000),
                int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter), text)
            if bounds.height() > painted.height() + 2:
                result['clippedButtonText'].append(dict(text=text, availableHeight=painted.height(), neededHeight=bounds.height()))
        elif needed > width + 2:
            result['clippedButtonText'].append(dict(text=text, available=width, needed=needed))
    for label in widget.findChildren(QLabel):
        if not label.text() or not label.isVisibleTo(widget): continue
        available = label.contentsRect()
        flags = int(Qt.TextFlag.TextWordWrap) if label.wordWrap() else 0
        if type(label).__name__ == 'WrapLabel': flags |= int(Qt.TextFlag.TextWrapAnywhere)
        bounds = label.fontMetrics().boundingRect(QRect(0, 0, max(1, available.width()), 10000), flags, label.text())
        if bounds.height() > available.height() + 2 or bounds.width() > available.width() + 2:
            result['clippedLabels'].append(dict(text=label.text(), actual=[available.width(), available.height()], needed=[bounds.width(), bounds.height()]))
    for combo in widget.findChildren(QComboBox):
        if combo.isVisibleTo(widget):
            result['combos'].append(dict(text=combo.currentText(), width=combo.width(),
                                         minimum=combo.minimumSizeHint().width(), tooltip=combo.toolTip()))
    for key, tree in widget.category_trees.items():
        if not tree.isVisibleTo(widget): continue
        result['treeColumns'].append(dict(category=key, viewport=tree.viewport().width(),
            widths=[tree.columnWidth(i) for i in range(tree.columnCount())],
            horizontalMax=tree.horizontalScrollBar().maximum()))
    result['buttons'] = measure_reachability(widget)
    result['unreachableButtons'] = [b for b in result['buttons'] if not b['centerReachable']]
    result['partlyClippedButtons'] = [b for b in result['buttons'] if not b['fullyReachable']]
    return result


class RigLayoutFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self): self.widget = build_fixture()
    def tearDown(self): self.widget.close(); self.widget.deleteLater(); self.app.processEvents()

    def test_fixture_uses_real_skin_rows_and_independent_multiselections(self):
        self.assertEqual(self.widget.locks.topLevelItemCount(), 10)
        self.assertEqual(self.widget.vertex_values.topLevelItemCount(), 32)
        self.assertAlmostEqual(sum(skin_fixture()['weights'].values()), 1)
        self.assertEqual(set(self.widget.selected_models()), {'model-0', 'model-1'})
        self.assertEqual(set(self.widget.selected_bones()), {'bone-0', 'bone-1'})
        self.assertEqual(self.widget.skin.currentData(Qt.ItemDataRole.UserRole + 1), 'skin-1')

    def test_step_navigation_preserves_child_draft_and_targets(self):
        w = self.widget
        expected = (w.child_parent, w.child_name.text(), w.child_start.text(), w.child_direction.text(), w.child_length.value())
        for index in range(w.steps.count()):
            w.steps.setCurrentIndex(index); settle(w)
            self.assertEqual((w.child_parent, w.child_name.text(), w.child_start.text(), w.child_direction.text(), w.child_length.value()), expected)
            self.assertEqual(set(w.selected_models()), {'model-0', 'model-1'})
            self.assertEqual(set(w.selected_bones()), {'bone-0', 'bone-1'})
        self.assertEqual(w.owner.requests, [])

    def test_no_native_window_or_host_process_in_fixture(self):
        self.assertEqual(QApplication.platformName(), 'offscreen')
        self.assertTrue(self.widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))

    def test_deferred_page_deletion_keeps_scene_adapter_tree_alive(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        from shiboken6 import isValid
        w=self.widget
        # Max returns to its event loop before the queued scene result arrives.
        # processEvents alone does not reliably deliver DeferredDelete events.
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertTrue(isValid(w.tree),'Retired page deleted the retained scene adapter tree')
        original=w.owner.rig_command
        def queued(request,callback):
            QTimer.singleShot(0,lambda:original(request,callback))
            return 'deferred-scene-read'
        w.owner.rig_command=queued
        draft=(w.child_parent,w.child_name.text(),w.child_start.text(),w.child_direction.text(),w.child_length.value())
        w.scene=None
        w.refresh.click();self.assertTrue(w.busy);settle(w,4)
        self.assertFalse(w.busy)
        self.assertEqual(w.scene,'layout-fixture-scene')
        self.assertEqual(w.tree.topLevelItemCount(),7)
        self.assertEqual(set(w.selected_models()),{'model-0','model-1'})
        self.assertEqual(set(w.selected_bones()),{'bone-0','bone-1'})
        self.assertEqual((w.child_parent,w.child_name.text(),w.child_start.text(),w.child_direction.text(),w.child_length.value()),draft)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        w.refresh.click();settle(w,4)
        self.assertFalse(w.busy);self.assertTrue(isValid(w.tree))
        self.assertNotIn('pymxs', sys.modules)

    def test_sections_keep_child_draft_and_selections_across_details_resize_and_display(self):
        w = self.widget
        self.assertIn(2, w.stage_panels); self.assertIn(6, w.stage_panels)
        expected = (w.child_parent, w.child_name.text(), w.child_start.text(), w.child_direction.text(), w.child_length.value())
        for width, height in ((680, 600), (1120, 760), (900, 800)):
            w.resize(width, height); settle(w)
            for stage in (2, 6):
                w.steps.setCurrentIndex(stage)
                panel = w.stage_panels[stage]
                panel.back(); settle(w)
                for title, page in panel.details.items():
                    panel.open_detail(title); settle(w)
                    self.assertIs(panel.stack.currentWidget(), page)
                    panel.back(); settle(w)
                    self.assertEqual(panel.stack.currentIndex(), 0)
                    self.assertEqual((w.child_parent, w.child_name.text(), w.child_start.text(), w.child_direction.text(), w.child_length.value()), expected)
                    self.assertEqual(set(w.selected_models()), {'model-0', 'model-1'})
                    self.assertEqual(set(w.selected_bones()), {'bone-0', 'bone-1'})
            w.display_button.click(); settle(w)
            self.assertIs(w.right_stack.currentWidget(), w.display_panel)
            w.steps.setCurrentIndex(2); settle(w)
            self.assertIs(w.right_stack.currentWidget(), w.tabs)
        self.assertEqual(w.owner.requests, [])

    def test_child_fields_and_weight_modes_are_primary_tasks(self):
        w = self.widget
        w.steps.setCurrentIndex(2); panel = w.stage_panels[2]; panel.back(); settle(w)
        for name in ('child_name', 'child_length', 'child_start', 'child_direction'):
            self.assertTrue(panel.overview.isAncestorOf(getattr(w, name)), name)
        self.assertFalse(w.symmetry_side.isVisibleTo(w))
        w.steps.setCurrentIndex(6); w.stage_panels[6].back(); settle(w)
        for index in range(w.weight_mode.count()):
            w.weight_mode.setCurrentIndex(index); settle(w)
            self.assertEqual(w.weight_tasks.currentIndex(), index)
        self.assertFalse(w.vertex_values.isVisibleTo(w))

    def test_minimum_supported_window_keeps_actions_wholly_reachable(self):
        w = self.widget
        w.resize(680, 600); settle(w)
        self.assertLessEqual(w.width(), 682)
        self.assertLessEqual(w.height(), 602)
        for stage in (2, 6):
            w.steps.setCurrentIndex(stage); panel = w.stage_panels[stage]
            for title in [None, *panel.details]:
                panel.back() if title is None else panel.open_detail(title)
                settle(w)
                metrics = measure_layout(w, [680, 600])
                self.assertEqual(metrics['partlyClippedButtons'], [],
                                 'Action unreachable in stage %s / %s' % (stage, title))
                self.assertEqual(metrics['clippedButtonText'], [])
                self.assertEqual(metrics['clippedLabels'], [])
            panel.back()
        w.weight_mode.setCurrentIndex(1); settle(w)
        self.assertEqual(measure_layout(w)['partlyClippedButtons'], [])
        w.display_button.click(); settle(w)
        self.assertEqual(measure_layout(w)['partlyClippedButtons'], [])

    def test_long_model_skin_and_bone_names_do_not_enlarge_window(self):
        w = self.widget
        w.steps.setCurrentIndex(6); w.resize(680, 600); settle(w)
        for field in (w.mesh, w.skin, w.source, w.parent):
            if field.count(): field.setCurrentIndex(field.count() - 1)
            settle(w)
            self.assertLessEqual(w.width(), 682)
            self.assertLessEqual(w.height(), 602)

    def test_scrolling_does_not_change_unfocused_parameters_or_disable_lists(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QWheelEvent
        w=self.widget;w.resize(680,600);settle(w)
        def wheel(target):
            event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,-120),
                Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
            QApplication.sendEvent(target,event)
            return event
        for combo in (w.steps,w.bind_method,w.component,w.control_shape,w.weight_mode):
            combo.clearFocus();before=combo.currentIndex();event=wheel(combo)
            self.assertEqual(combo.currentIndex(),before);self.assertFalse(event.isAccepted())
        for field in (w.child_length,w.rig_height,w.brush_radius,w.chain_counts['spine']):
            before=field.value();wheel(field);self.assertEqual(field.value(),before)
        tree=w.category_trees['bones'];bar=tree.verticalScrollBar();bar.setValue(0)
        wheel(tree.viewport());self.assertGreater(bar.value(),0)


if __name__ == '__main__': unittest.main()
