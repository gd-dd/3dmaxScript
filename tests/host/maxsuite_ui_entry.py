"""Parent nine-tool UI entry gate, invoked only by a new isolated Max batch.

This verifies complete-package routes and UI lifetime, not baking algorithms,
frozen shelf installation, user desktop presentation or a production character.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import time
import traceback


def main():
    if os.environ.get('LX_MAXSUITE_UI_ENTRY') != '1':
        raise RuntimeError('Use run_maxsuite_ui_entry.py after the parent owner schedules Max')
    source = Path(main.__code__.co_filename).resolve().parents[2]
    root = Path(os.environ['LX_MAXSUITE_UI_ROOT']).resolve()
    out = Path(os.environ['LX_MAXSUITE_UI_RUN']).resolve()
    expected_out = source.parent / 'acceptance/maxsuite-ui-2026-11-12/host-runs'
    if root.drive.casefold() != 'e:' or not out.is_relative_to(expected_out):
        raise RuntimeError('Package and unique run must remain in the E workspace')
    for key in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
                'ADSK_3DSMAX_APPDATA_DIR', 'ADSK_3DSMAX_USERSETTINGS_DIR'):
        value = os.environ.get(key, '')
        if not value or not Path(value).resolve().is_relative_to(out):
            raise RuntimeError('Isolated run directory required for ' + key)
    sys.dont_write_bytecode = True
    from pymxs import runtime as rt
    import pymxs
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QDockWidget
    from shiboken6 import isValid
    import qtmax
    process = rt.dotNetClass('System.Diagnostics.Process').GetCurrentProcess()
    command = str(rt.dotNetClass('System.Environment').CommandLine)
    if not re.search(r'(?:^|\s)-batch(?:\s|$)', command, re.I):
        raise RuntimeError('This test may run only in a new 3dsmax.exe -batch process')
    app = QApplication.instance()
    main_window = qtmax.GetQMaxMainWindow()
    if app is None or main_window is None:
        raise RuntimeError('Max Qt application and main window are required')
    report = dict(ok=False, root=str(root), pid=os.getpid(), command=command,
                  executable=str(process.MainModule.FileName), checks=[], screenshots=[],
                  workerBirthUTC=str(process.StartTime.ToUniversalTime().ToString('o')),
                  workerBirthFileTime=str(rt.dotNetClass('System.Convert').ToString(
                      process.StartTime.ToUniversalTime().ToFileTimeUtc())),
                  scope='Legacy native rollouts rendered offscreen; L3 .ms/bridge routes with Qt presentation suppressed',
                  currentUserWindowVerified=False, frozenClientVerified=False,
                  providerOrPublicInstallationVerified=False)
    originals = []
    windows = []
    created = []
    previous_path = list(sys.path)

    def write_report():
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')

    def lifecycle(stage, **data):
        report.setdefault('lifecycleTrace', []).append(dict(stage=stage, monotonic=time.monotonic(),
                                                          cleanupPhase=report.get('cleanupPhase', 'checks'), **data))
        write_report()

    def dock_identities():
        return [dict(identity=id(dock), valid=isValid(dock), closed=getattr(dock, 'closed', None),
                     parentIsMax=dock.parentWidget() is main_window)
                for dock in main_window.findChildren(QDockWidget, 'LXRigSkinDock') if isValid(dock)]

    def window_identity(window):
        valid = window is not None and isValid(window)
        return dict(identity=id(window), valid=valid,
                    closed=getattr(window, 'closed', None) if valid else None,
                    parentIsMax=window.parentWidget() is main_window if valid else None)

    def destroy_owned_window(window, reason):
        assert any(window is owned for owned in windows), 'Deletion receiver is not owned by this run'
        record = dict(reason=reason, before=window_identity(window), sent=False)
        report.setdefault('targetedDeferredDeletes', []).append(record)
        lifecycle('owned-deferred.begin', receiver=record['before'], reason=reason)
        if isValid(window):
            record['sent'] = True
            QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        record['after'] = window_identity(window)
        lifecycle('owned-deferred.end', receiver=record['after'], reason=reason)
        assert not isValid(window), 'Owned window was not truly destroyed after its DeferredDelete'

    def about_to_quit():
        lifecycle('signal.aboutToQuit')

    def last_window_closed():
        lifecycle('signal.lastWindowClosed')

    report['quitOnLastWindowClosed'] = app.quitOnLastWindowClosed()
    app.aboutToQuit.connect(about_to_quit)
    app.lastWindowClosed.connect(last_window_closed)

    def pump_until(predicate, description, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
            if predicate():
                return
        raise AssertionError('Timed out: ' + description)

    def scene():
        rows = []
        for node in rt.objects:
            tm = node.transform
            rows.append(dict(id=int(rt.getHandleByAnim(node)), name=str(node.name),
                             parent=int(rt.getHandleByAnim(node.parent)) if node.parent else None,
                             matrix=[[float(v.x), float(v.y), float(v.z)]
                                     for v in (tm.row1, tm.row2, tm.row3, tm.row4)],
                             hidden=bool(node.isNodeHidden)))
        return dict(nodes=sorted(rows, key=lambda item: item['id']),
                    selection=[int(rt.getHandleByAnim(n)) for n in rt.selection],
                    time=str(rt.currentTime), range=str(rt.animationRange),
                    file=str(rt.maxFilePath) + str(rt.maxFileName))

    def resources():
        manifest = json.loads((root / '.lxtool/manifest.json').read_text('utf-8-sig'))
        for relative, digest in manifest['files'].items():
            path = (root / relative).resolve()
            assert path.is_relative_to(root), relative
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, relative
        return manifest

    def remember(owner, method, replacement):
        originals.append((owner, method, getattr(owner, method)))
        setattr(owner, method, replacement)

    def suppress_show(window):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        if all(window is not item for item in windows):
            windows.append(window)
        report.setdefault('suppressed', []).append(type(window).__name__ + '.show')

    def suppress_raise(window):
        assert window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        report.setdefault('suppressed', []).append(type(window).__name__ + '.raise')

    def screenshot(window, name, size):
        assert window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        # QDockWidget.setFloating may set Qt's logical visible flag internally,
        # without calling Python show() and without exposing a native surface.
        # Enforce actual non-exposure before and after rendering. Do not hide
        # first, which could conceal an exposure failure from the assertion.
        logical_visible = window.isVisible()
        handle = window.windowHandle()
        exposed_before = bool(handle is not None and handle.isExposed())
        assert not exposed_before, 'A native tool surface was exposed'
        window.resize(*size)
        window.ensurePolished()
        if window.layout() is not None:
            window.layout().activate()
        app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
        image = window.grab()
        handle = window.windowHandle()
        exposed_after = bool(handle is not None and handle.isExposed())
        assert not exposed_after, 'Hidden render exposed a native tool surface'
        assert window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        path = out / (name + '.png')
        assert not image.isNull() and image.save(str(path)), name
        report['screenshots'].append(dict(path=str(path), widget=type(window).__name__,
                                          requestedSize=list(size), actualSize=[window.width(), window.height()],
                                          logicalVisibleBeforeGrab=logical_visible,
                                          nativeExposedBefore=exposed_before, nativeExposedAfter=exposed_after,
                                          method='QWidget.grab of hidden real Max-owned UI; not desktop screenshot'))

    def route(entry):
        rt.fileIn(str(root / entry), quiet=True)

    def origin(package):
        module = importlib.import_module(package)
        assert Path(module.__file__).resolve().parent == root / package, package

    def run_check(name, callback):
        item = dict(name=name, ok=False)
        report['checks'].append(item)
        write_report()
        try:
            item.update(callback())
            item['ok'] = True
        except Exception:
            item['error'] = traceback.format_exc()
        write_report()

    initial = scene()
    write_report()  # Publish worker PID/birth before any entry or layout check.
    try:
        manifest = resources()
        report.update(version=manifest['version'], declaredResources=len(manifest['files']))
        sys.path[:] = [str(root)] + [p for p in sys.path if p != str(root)]
        # Exercise ExecuteFile's actual shared globals without trusting __file__.
        rt.python.Execute("__file__ = 'E:/foreign-test-script/not-the-parent.py'")
        rt.LXMaxBridgeRequestedUserRoot = str(out / 'bridge-root/LXMaxTools')
        route('bridge/LXMaxBridge.ms')
        rt.LXMaxBridgeTimer.Stop()
        assert Path(str(rt.LXMaxBridgeRoot)).resolve() == root
        assert Path(str(rt.LXMaxBridgeSession)).resolve().is_relative_to(out / 'bridge-root/LXMaxTools')
        report['bridgeRoot'] = str(rt.LXMaxBridgeSession)
        for owner in (QDialog,):
            remember(owner, 'show', suppress_show)
            remember(owner, 'raise_', suppress_raise)

        # The six rollouts run in this same already-owned Max. Only their source
        # root and offscreen position are adapted by the existing native UI QA;
        # LEGACY_UI_ONLY skips its separate business/reset stage.
        legacy_out = out / 'legacy'
        legacy_names = [('动画烘焙工具.ms', 'AnimBakeRollout'),
                        ('保持位移建立父子.ms', 'ReparentBakeRollout'),
                        ('清理根骨骼.ms', 'RootBoneBakeRollout'),
                        ('按材质ID拆分模型.ms', 'MatIDSplitRollout'),
                        ('PMX导入.ms', 'PMXImportRollout'),
                        ('自定义公式关键帧.ms', 'CustomFormulaRollout')]
        before_legacy = scene()
        legacy_report = {}
        legacy_error = None
        try:
            legacy = runpy.run_path(str(source / 'tests/host/legacy_ui_acceptance.py'),
                                   init_globals={'LEGACY_UI_ROOT': root,
                                                 'LEGACY_UI_OUT': legacy_out,
                                                 'LEGACY_UI_ONLY': True})
            legacy_report = legacy['report']
            assert legacy_report['ok'], legacy_report.get('error', 'Legacy native UI gate failed')
            assert scene() == before_legacy, 'Legacy UI-only stage changed scene state'
        except Exception:
            legacy_error = traceback.format_exc()
        report['legacyNativeReport'] = str(legacy_out / 'ui-report.json')
        report['legacySameHost'] = legacy_report.get('pid') == os.getpid()
        for filename, rollout in legacy_names:
            matches = [item for item in legacy_report.get('windows', []) if item['name'] == filename]
            item = dict(name='legacy:' + filename,
                        ok=legacy_error is None and len(matches) == 1 and report['legacySameHost'])
            if item['ok']:
                item.update(size=matches[0]['size'], nativeOpenHandler=True,
                            controlBounds=True, primaryCaption=True, userImage=True)
                report['screenshots'].append(dict(path=str(legacy_out / (rollout + '.png')),
                                                  method='PrintWindow of offscreen original native rollout; not desktop screenshot'))
                if matches[0].get('collapsePreservesFormula'):
                    item['collapsePreservesFormula'] = True
                    report['screenshots'].append(dict(path=str(legacy_out / (rollout + '-reference.png')),
                                                      method='PrintWindow of expanded offscreen formula reference'))
            else:
                item['error'] = legacy_error or 'Native window record missing or worker PID mismatched'
            report['checks'].append(item)
        write_report()

        def rig_gate():
            origin('rig')
            ui = importlib.import_module('rig.max_ui')
            digest = hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root / 'rig').iterdir())
                                            if p.suffix in ('.py', '.ms'))).hexdigest()
            ui._code_digest = digest
            original_init = ui.RigDock.__init__
            original_refresh = ui.RigDock.refresh_scene
            original_dispatch = ui.dispatch
            diagnostics = dict(events=[])
            report['rigDiagnostics'] = diagnostics

            def dock_state(window):
                if window is None or not isValid(window):
                    return dict(valid=False)
                workbench = window.workbench
                return dict(valid=True, notice=workbench.notice.text(),
                            scene=workbench.scene, sceneToken=str(rt.LXRigSceneToken),
                            busy=workbench.busy, queue=list(window.queue),
                            target=workbench.session, closed=window.closed,
                            startupHold=bool(rt.theHold.Holding()),
                            timers=[dict(name=timer.objectName(), active=timer.isActive(),
                                         interval=timer.interval(), singleShot=timer.isSingleShot())
                                    for timer in window.findChildren(QTimer)])

            def traced_refresh(window):
                diagnostics['events'].append(dict(stage='refresh.begin', state=dock_state(window)))
                try:
                    return original_refresh(window)
                finally:
                    diagnostics['events'].append(dict(stage='refresh.end', state=dock_state(window)))

            def traced_dispatch(request):
                record = dict(stage='dispatch', action=request.get('action'))
                diagnostics['events'].append(record)
                try:
                    result = original_dispatch(request)
                    record.update(ok=True, scene=result.get('scene') if isinstance(result, dict) else None)
                    return result
                except Exception:
                    record.update(ok=False, error=traceback.format_exc())
                    raise

            def quiet_init(window, parent):
                original_init(window, parent)
                window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                windows.append(window)
                diagnostics['beforeTimerSuppression'] = dock_state(window)
                for timer in window.findChildren(QTimer):
                    timer.stop()

            remember(ui.RigDock, '__init__', quiet_init)
            remember(ui.RigDock, 'refresh_scene', traced_refresh)
            remember(ui, 'dispatch', traced_dispatch)
            remember(QDockWidget, 'show', suppress_show)
            remember(QDockWidget, 'raise_', suppress_raise)

            def ready(dock):
                assert dock is not None and isValid(dock) and not dock.closed
                assert dock.parentWidget() is main_window and dock.isFloating()
                try:
                    pump_until(lambda: dock.workbench.scene == str(rt.LXRigSceneToken)
                               and not dock.workbench.busy and not dock.queue, 'Rig real queued scene read')
                except Exception:
                    diagnostics['failureState'] = dock_state(dock)
                    write_report()
                    raise

            before = scene()
            route('LX_RigSkin.ms')
            first = ui._dock
            ready(first)
            rt.LXMaxBridgeRun('rig-workbench')
            assert ui._dock is first
            ready(first)
            screenshot(first, 'rig-wide', (1100, 760))
            screenshot(first, 'rig-compact', (760, 560))
            lifecycle('rig.first.close.begin', old=window_identity(first), namedDocks=dock_identities())
            assert first.close() is not False
            pump_until(lambda: not isValid(first) or first.closed, 'Rig dock closed')
            if isValid(first): destroy_owned_window(first, 'first Rig close before reopen')
            assert not isValid(first), 'Old Rig dock must be destroyed before reopening'
            lifecycle('rig.first.close.end', old=window_identity(first), namedDocks=dock_identities())
            lifecycle('rig.reopen.begin', old=window_identity(first), namedDocks=dock_identities())
            route('LX_RigSkin.ms')
            reopened = ui._dock
            lifecycle('rig.reopen.constructed', old=window_identity(first), new=window_identity(reopened),
                      namedDocks=dock_identities())
            assert reopened is not first
            ready(reopened)
            lifecycle('rig.reopen.ready', old=window_identity(first), new=window_identity(reopened),
                      namedDocks=dock_identities())
            lifecycle('rig.second.close.begin', new=window_identity(reopened), namedDocks=dock_identities())
            assert reopened.close() is not False
            if isValid(reopened): destroy_owned_window(reopened, 'second Rig close')
            assert not isValid(reopened), 'Reopened Rig dock did not truly close'
            lifecycle('rig.second.close.end', new=window_identity(reopened), namedDocks=dock_identities())
            assert scene() == before, 'Rig entry/refresh changed scene state'
            return dict(fileIn=True, bridge=True, sameWindow=True, reopen=True,
                        realQueuedSceneRead=True, parentIsMax=True, sceneUnchanged=True)

        def ribbon_gate():
            before = scene()
            with pymxs.undo(False):
                a = rt.boneSys.createBone(rt.Point3(0, 0, 0), rt.Point3(0, 0, 15), rt.Point3(1, 0, 0))
                b = rt.boneSys.createBone(rt.Point3(0, 0, 15), rt.Point3(0, 0, 30), rt.Point3(1, 0, 0))
                b.parent = a
                a.name = '验收飘带骨链_源节点_长名称'; b.name = '验收飘带骨链_末端定位_长名称'
                created.extend((a, b))
                rt.select(a)
            route('LX_Ribbon.ms')
            origin('ribbon')
            module = importlib.import_module('ribbon.plugin')
            first = module.window
            assert first.parentWidget() is main_window
            first.read()
            assert len(first.chain) == 2
            chain = first.chain
            rt.LXMaxBridgeRun('ribbon')
            assert module.window is first and first.chain is chain
            screenshot(first, 'ribbon-wide', (720, 680))
            screenshot(first, 'ribbon-compact', (460, 500))
            assert first.close() is not False
            with pymxs.undo(False):
                for node in reversed((a, b)):
                    if rt.isValidNode(node): rt.delete(node)
                created[:] = [node for node in created if rt.isValidNode(node)]
                rt.clearSelection()
            assert scene() == before, 'Ribbon entry/read/close changed unrelated state'
            return dict(fileIn=True, bridge=True, sameWindow=True, sameChain=True,
                        realBoneChainRead=True, parentIsMax=True, fixturesRemoved=True)

        def retarget_gate():
            before = scene()
            with pymxs.undo(False):
                source_node = rt.Point(name='验收源骨架_世界中心_长名称', pos=rt.Point3(3, 5, 7))
                target_node = rt.Point(name='验收目标骨架_世界中心_长名称', pos=rt.Point3(-3, 5, 7))
                created.extend((source_node, target_node))
            route('LX_Retarget.ms')
            origin('retarget')
            launcher = importlib.import_module('retarget.launcher')
            first = launcher._window
            assert first.parentWidget() is main_window
            session = first.session
            rt.select(source_node); first.capture('source')
            rt.select(target_node); first.capture('target')
            assert len(session.source) == len(session.target) == 1
            rt.LXMaxBridgeRun('retarget')
            assert launcher._window is first and first.session is session
            screenshot(first, 'retarget-wide', (1100, 760))
            screenshot(first, 'retarget-compact', (780, 560))
            before_hide = scene()
            session.visibility('hide_source')
            assert bool(source_node.isNodeHidden)
            assert first.close() is not False
            assert scene() == before_hide and not session._visibility, 'Retarget close did not restore visibility'
            with pymxs.undo(False):
                for node in reversed((source_node, target_node)):
                    if rt.isValidNode(node): rt.delete(node)
                created[:] = [node for node in created if rt.isValidNode(node)]
                rt.clearSelection()
            assert scene() == before, 'Retarget entry/close changed unrelated state'
            return dict(fileIn=True, bridge=True, sameWindow=True, sameSession=True,
                        realCapture=True, closeRestoresVisibility=True, parentIsMax=True,
                        fixturesRemoved=True)

        for name, callback in (('rig-entry', rig_gate), ('ribbon-entry', ribbon_gate), ('retarget-entry', retarget_gate)):
            run_check(name, callback)
        report['resourcesUnchangedDuringRun'] = resources() == manifest
        report['sceneUnchanged'] = scene() == initial
        report['maxVersion'] = list(rt.maxVersion())[:3]
        report['entryCount'] = len(report['checks'])
        report['ok'] = len(report['checks']) == 9 and all(item['ok'] for item in report['checks']) and report['sceneUnchanged']
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        report['cleanupPhase'] = 'begin'
        lifecycle('cleanup.begin', namedDocks=dock_identities())
        try:
            rt.LXMaxBridgeTimer.Stop()
        except Exception:
            pass
        for window in reversed(windows):
            if not isValid(window): continue
            try:
                report['cleanupPhase'] = 'window.close'
                lifecycle('cleanup.window.close.begin', widget=type(window).__name__,
                          window=window_identity(window), namedDocks=dock_identities())
                for timer in window.findChildren(QTimer): timer.stop()
                assert window.close() is not False, 'Owned window refused to close safely'
                if isValid(window): window.deleteLater()
                lifecycle('cleanup.window.close.end', widget=type(window).__name__,
                          window=window_identity(window), namedDocks=dock_identities())
            except Exception:
                report['ok'] = False
                report.setdefault('cleanupErrors', []).append(traceback.format_exc())
        try:
            report['cleanupPhase'] = 'fixtures'
            lifecycle('cleanup.fixtures.begin')
            with pymxs.undo(False):
                for node in reversed(created):
                    if rt.isValidNode(node): rt.delete(node)
            report['cleanupPhase'] = 'deferred-delete'
            lifecycle('cleanup.deferred-delete.begin', namedDocks=dock_identities())
            for window in reversed(windows):
                if isValid(window): destroy_owned_window(window, 'final owned-window cleanup')
            assert all(not isValid(window) for window in windows), 'An owned tool window remains alive'
            app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
            lifecycle('cleanup.deferred-delete.end', namedDocks=dock_identities())
        except Exception:
            report['ok'] = False
            report.setdefault('cleanupErrors', []).append(traceback.format_exc())
        for owner, method, original in reversed(originals):
            setattr(owner, method, original)
        sys.path[:] = previous_path
        report['cleanupPhase'] = 'restored'
        lifecycle('cleanup.methods-restored')
        app.aboutToQuit.disconnect(about_to_quit)
        app.lastWindowClosed.disconnect(last_window_closed)
        report['cleanupPhase'] = 'final'
        report['scriptBodyCompleted'] = True
        lifecycle('cleanup.final-signals-disconnected')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
