"""Hidden Max entry verification; call check(root) from a dedicated batch.

One package root per Max process, matching the production mixed-version guard.
No scene fixture is created here and no foreground/native tool window is shown.
"""
import hashlib
import importlib
import os
from pathlib import Path
import sys
import time


def check(root):
    if os.environ.get('LX_RIG_SIZE_BATCH') != '1':
        raise RuntimeError('Rig entry acceptance requires the dedicated hidden rig_size batch')
    root = Path(root).resolve()
    entry = root / 'LX_RigSkin.ms'
    if not entry.is_file():
        raise ValueError('Missing standalone rig entry: ' + str(entry))
    loaded = sys.modules.get('rig')
    if loaded is not None and Path(loaded.__file__).resolve().parent != root / 'rig':
        raise RuntimeError('Use a fresh hidden Max for each package root; production forbids mixed rig versions')

    from pymxs import runtime as rt
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
    from PySide6.QtWidgets import QApplication, QDockWidget, QPushButton
    from shiboken6 import isValid
    import qtmax

    app = QApplication.instance()
    if app is None:
        raise RuntimeError('Max Qt application is unavailable')
    original_path = list(sys.path)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    ui = importlib.import_module('rig.max_ui')
    package = importlib.import_module('rig')
    H = importlib.import_module('rig.max_host')
    assert Path(package.__file__).resolve().parent == root / 'rig'
    assert Path(ui.__file__).resolve() == root / 'rig/max_ui.py'
    assert Path(ui.ROOT).resolve() == root
    previous_dock = getattr(ui, '_dock', None)
    if previous_dock is not None and isValid(previous_dock) and not previous_dock.closed:
        sys.path[:] = original_path
        raise RuntimeError('A rig dock is already open; this check must own both test instances')

    # Exact algorithm from bridge/open_rig.py. Its hot reload must not replace
    # the test-only constructor guard before setFloating creates a native window.
    digest = hashlib.sha256(b''.join(path.read_bytes() for path in sorted((root / 'rig').iterdir())
                                  if path.suffix in ('.py', '.ms'))).hexdigest()
    had_digest = hasattr(ui, '_code_digest')
    previous_digest = getattr(ui, '_code_digest', None)
    ui._code_digest = digest
    original_init = ui.RigDock.__init__
    original_show, original_raise = QDockWidget.show, QDockWidget.raise_
    made = []
    suppressed = {'show': 0, 'raise': 0}
    main = qtmax.GetQMaxMainWindow()

    def scene_state():
        result = {}
        for node in rt.objects:
            tm = node.transform
            result[H.handle(node)] = dict(
                parent=H.handle(node.parent) if node.parent else None,
                matrix=[H.vec(row) for row in (tm.row1, tm.row2, tm.row3, tm.row4)],
                hidden=bool(node.isHidden), properties=str(rt.getUserPropBuffer(node)))
        return dict(nodes=result, selection=[H.handle(node) for node in rt.selection])

    before = scene_state()
    expected_ids = set(before['nodes'])

    def quiet_init(self, parent):
        original_init(self, parent)
        # __init__ does not show. This executes before addDockWidget/setFloating.
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        made.append(self)
        # Leave queued scene reads intact but prevent preview/tick side effects.
        for timer in self.findChildren(QTimer):
            timer.stop()

    def quiet_show(self):
        assert self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        suppressed['show'] += 1

    def quiet_raise(self):
        assert self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        suppressed['raise'] += 1

    def pump_until(predicate, description, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
            if predicate():
                return
        raise AssertionError('Timed out: ' + description)

    def assert_ready(dock):
        assert dock is not None and isValid(dock) and not dock.closed
        assert dock.isFloating(), 'First invocation must float'
        assert dock.parentWidget() is main, 'Rig dock must belong to Max'
        assert dock.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        assert ui.RigDock.__init__ is quiet_init, 'Entry reload replaced the no-window guard'
        assert ui._code_digest == digest
        workbench = dock.workbench
        pump_until(lambda: workbench.scene == str(rt.LXRigSceneToken)
                   and not workbench.busy and not dock.queue
                   and {node['id'] for node in workbench.nodes} == expected_ids,
                   'real queued scene read; notice=' + workbench.notice.text())
        # Exercise the actual refresh button's bound scene.inspect command.
        workbench.refresh.click()
        pump_until(lambda: not workbench.busy and not dock.queue, 'refresh button scene read')
        assert {node['id'] for node in workbench.nodes} == expected_ids
        for field in ('child_name', 'child_length', 'child_parent_label', 'child_start',
                      'child_direction', 'ik_size', 'control_size'):
            assert hasattr(workbench, field) and isValid(getattr(workbench, field)), field
            assert getattr(workbench, field).parentWidget() is not None, field + ' detached from UI'
        assert workbench.child_length.minimum() == .001
        assert workbench.child_length.value() > 0
        assert workbench.child_start.text() == workbench.child_direction.text() == ''
        labels = {button.text() for button in workbench.findChildren(QPushButton)}
        expected_buttons = {'记住骨骼栏所选父骨骼', '记住视口所选父骨骼',
                            '起点 · 对象轴心', '起点 · 顶点中心',
                            '方向 · 对象轴心', '方向 · 顶点中心',
                            '按起点 / 方向点添加', '从父骨骼末端顺延添加',
                            '按当前骨架重新适配显示尺寸'}
        assert expected_buttons <= labels, sorted(expected_buttons - labels)

    try:
        ui.RigDock.__init__ = quiet_init
        QDockWidget.show, QDockWidget.raise_ = quiet_show, quiet_raise
        rt.fileIn(str(entry), quiet=True)
        first = ui._dock
        assert_ready(first)
        assert len(made) == 1
        rt.fileIn(str(entry), quiet=True)
        assert ui._dock is first and len(made) == 1, 'Repeat call did not reuse the same dock'
        assert_ready(first)
        first.close()
        pump_until(lambda: not isValid(first) or first.closed, 'first dock closing')
        rt.fileIn(str(entry), quiet=True)
        reopened = ui._dock
        assert reopened is not first and len(made) == 2, 'Closed dock was not replaced'
        assert_ready(reopened)
        assert scene_state() == before, 'Entry/refresh changed scene objects, transforms, properties or selection'
        assert suppressed['show'] == 3 and suppressed['raise'] == 3, suppressed
        result = dict(root=str(root), entry=str(entry), codeDigest=digest,
                      standaloneFileIn=True, floating=True, samePathReuse=True,
                      reopenAfterClose=True, sceneRead=True, sceneObjects=len(expected_ids),
                      childParametersAndButtons=True, noNativeToolWindow=True,
                      sceneUnchanged=True, constructions=len(made), suppressed=dict(suppressed),
                      scope='Dedicated hidden Max; real entry/Qt construction; presentation suppressed')
    finally:
        # Keep suppression installed through all close/delete callbacks.
        try:
            for dock in made:
                if not isValid(dock):
                    continue
                for timer in dock.findChildren(QTimer):
                    timer.stop()
                if not dock.closed:
                    dock.close()
                if isValid(dock):
                    for timer in dock.findChildren(QTimer):
                        assert not timer.isActive(), 'Owned timer still active after close'
                    dock.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
            ui._dock = None
        finally:
            ui.RigDock.__init__ = original_init
            QDockWidget.show, QDockWidget.raise_ = original_show, original_raise
            if had_digest:
                ui._code_digest = previous_digest
            elif hasattr(ui, '_code_digest'):
                del ui._code_digest
            sys.path[:] = original_path
    return result
