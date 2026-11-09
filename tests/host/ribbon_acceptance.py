"""Run ONLY in a disposable 3dsmaxbatch process; never in an open user scene.

Exercises the integrated Max-tool-suite ribbon entry without displaying windows.
All evidence goes to the E-drive acceptance directory, not this source checkout.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = Path('E:/project/LXTools/acceptance/ribbon-2026-11-09')
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
REPORT = {'ok': False, 'scope': 'integrated-source + byte-identical local package',
          'pid': os.getpid(), 'source': str(ROOT), 'checks': [], 'not_verified': [
              'user running Max PID 89944', 'mouse/keyboard interaction',
              'real skinned ribbon visual quality', 'public Release / installed snapshot']}


def save():
    (OUT / 'host-report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')


def check(name, fn):
    try:
        evidence = fn()
        REPORT['checks'].append({'name': name, 'ok': True, 'evidence': evidence})
        print('RIBBON_ACCEPTANCE_PASS', name, flush=True)
    except Exception:
        REPORT['checks'].append({'name': name, 'ok': False, 'error': traceback.format_exc()})
        print('RIBBON_ACCEPTANCE_FAIL', name, flush=True)
    save()


assert os.getpid() != 89944, 'Refuse to operate the user Max process'
assert os.environ.get('LX_RIBBON_ISOLATED_BATCH') == '1', 'Explicit isolated-batch launch required'
for name in ('TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'ADSK_3DSMAX_USERSETTINGS_DIR'):
    value = os.environ.get(name, '')
    assert value.replace('\\', '/').lower().startswith('e:/project/lxtools/'), (name, value)
REPORT['environment'] = {name: os.environ.get(name) for name in (
    'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE',
    'ADSK_3DSMAX_USERSETTINGS_DIR', 'PYTHONDONTWRITEBYTECODE')}
save()

import pymxs
from pymxs import runtime as rt
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid
from ribbon import plugin

REPORT['maxVersion'] = list(rt.maxVersion())
REPORT['pluginFile'] = str(Path(plugin.__file__).resolve())
assert Path(plugin.__file__).resolve() == (ROOT / 'ribbon/plugin.py').resolve()
rt.resetMaxFile(rt.Name('noPrompt'))
rt.animationRange = rt.interval(0, 20)
rt.frameRate = 30
SETTINGS = dict(gravity=980, inertia=.95, mass=1, influence=1, damping=3)


def package_check():
    manifest = json.loads((ROOT / '.lxtool/manifest.json').read_text('utf-8-sig'))
    package = ROOT / 'dist/LXTool-package.zip'
    with zipfile.ZipFile(package) as z:
        assert json.loads(z.read('.lxtool/manifest.json')) == manifest
        for relative, digest in manifest['files'].items():
            data = z.read(relative)
            assert hashlib.sha256(data).hexdigest() == digest, relative
            assert data == (ROOT / relative).read_bytes(), ('source/package mismatch', relative)
        expected = set(manifest['files']) | {'.lxtool/manifest.json'}
        assert {name for name in z.namelist() if not name.endswith('/')} == expected
        for relative in ('LX_Ribbon.ms', 'bridge/open_ribbon.py', 'ribbon/plugin.py', 'ribbon/solver.py'):
            assert relative in manifest['files'], relative
        tools = json.loads(z.read('ui/tools.json'))['tools']
        assert len([tool for tool in tools if tool['id'] == 'ribbon']) == 1
        assert '"ribbon": "LX_Ribbon.ms"' in z.read('bridge/LXMaxBridge.ms').decode('utf-8-sig')
    return {'declaredFiles': len(manifest['files']), 'version': manifest['version'],
            'zip': str(package), 'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
            'all_declared_bytes_match_source': True}


def make_chain(label, moving=False):
    rt.resetMaxFile(rt.Name('noPrompt'))
    rt.animationRange = rt.interval(0, 20)
    nodes = []
    # Fixture creation must never become part of the transaction under test.
    with pymxs.undo(False):
        for i in range(4):
            node = rt.boneSys.createBone(rt.Point3(i*10, 0, 30), rt.Point3((i+1)*10, 0, 30), rt.Point3(0, 0, 1))
            node.name = label + '_' + str(i)
            if nodes:
                node.parent = nodes[-1]
            nodes.append(node)
        if moving:
            with pymxs.animate(True):
                with pymxs.attime(0):
                    nodes[0].position = rt.Point3(0, 0, 30)
                with pymxs.attime(20):
                    nodes[0].position = rt.Point3(12, 3, 30)
        rt.select(nodes[0])
    rt.clearUndoBuffer()
    return nodes


def matrices(nodes):
    result = []
    for frame in range(21):
        with pymxs.attime(frame):
            result.append([[list(plugin.vec(row)) for row in (node.transform.row1,
                node.transform.row2, node.transform.row3, node.transform.row4)] for node in nodes])
    return result


def key_tracks(nodes):
    tracks = {}
    def walk(anim, path, depth=0):
        if depth > 3:
            return
        try:
            count = int(rt.numKeys(anim))
            if count > 0:
                tracks[path] = [float(rt.getKeyTime(anim, i).frame) for i in range(1, count+1)]
        except Exception:
            pass
        try:
            properties = list(rt.getPropNames(anim))
        except Exception:
            return
        for prop in properties:
            try:
                controller = rt.getPropertyController(anim, prop)
                if controller is not None:
                    walk(controller, path + '/' + str(prop), depth+1)
            except Exception:
                pass
    for node in nodes:
        walk(node.controller, str(node.name))
    return tracks


def max_delta(a, b):
    return max(abs(x-y) for af,bf in zip(a,b) for an,bn in zip(af,bf)
               for ar,br in zip(an,bn) for x,y in zip(ar,br))


def direct_entry():
    rt.fileIn(str(ROOT / 'LX_Ribbon.ms'), quiet=True)
    window = plugin.window
    assert isValid(window) and not window.isVisible()
    assert len(window.fields) == 5 and window.end.value() == 20
    assert len(window.findChildren(QtWidgets.QPushButton)) == 2
    return {'title': window.windowTitle(), 'visible': window.isVisible(), 'parameters': list(window.fields)}


def bridge_entry():
    rt.fileIn(str(ROOT / 'bridge/LXMaxBridge.ms'), quiet=True)
    rt.LXMaxBridgeRun('ribbon')
    assert isValid(plugin.window) and not plugin.window.isVisible()
    session = str(rt.LXMaxBridgeSession)
    assert session.replace('\\', '/').lower().startswith(str(OUT).replace('\\', '/').lower())
    rt.LXMaxBridgeTimer.Stop()
    return {'bridgeSession': session, 'targetPid': os.getpid(), 'visible': plugin.window.isVisible()}


def no_chain():
    rt.clearSelection()
    window = plugin.window
    window.read()
    assert not window.chain
    read_error = window.status.text()
    window.solve()
    assert '失败' in window.status.text() and '先读取' in window.status.text()
    assert window.run.isEnabled()
    return {'read': read_error, 'solve': window.status.text(), 'buttonReenabled': True}


def bake_success():
    nodes = make_chain('success', moving=True)
    window = plugin.window
    window.read()
    assert len(window.chain) == 4
    baseline = matrices(nodes)
    base_keys = key_tracks(nodes)
    window.start.setValue(0)
    window.end.setValue(20)
    window.solve()
    assert '完成：已烘焙 21 帧' in window.status.text(), window.status.text()
    result = matrices(nodes)
    lengths = []
    for values in result:
        positions = [node[3] for node in values]
        lengths.extend(math.dist(a,b) for a,b in zip(positions, positions[1:]))
    error = max(abs(length-10) for length in lengths)
    assert error < .01, error
    actual_keys = key_tracks(nodes)
    assert len(actual_keys) > len(base_keys), actual_keys
    assert any(len(times) >= 21 and 0 in times and 20 in times for times in actual_keys.values()), actual_keys
    assert result[-1][-1][3][2] < baseline[-1][-1][3][2] - 1
    assert math.dist(result[-1][0][3], baseline[-1][0][3]) < .01
    (OUT / 'baked-keys.json').write_text(json.dumps(actual_keys, ensure_ascii=False, indent=2), encoding='utf-8')
    REPORT['bakeMetricsBeforeUndo'] = {'maxLengthError': error, 'keyTracks': len(actual_keys),
        'endPosition': result[-1][-1][3], 'holdActive': bool(rt.theHold.Holding())}
    save()
    pymxs.run_undo()
    restored = matrices(nodes)
    undo_delta = max_delta(baseline, restored)
    assert undo_delta < .001, ('undo matrix delta', undo_delta)
    assert key_tracks(nodes) == base_keys, ('undo keys', key_tracks(nodes), base_keys)
    pymxs.run_redo()
    assert max_delta(result, matrices(nodes)) < .001, 'redo did not restore baked transforms'
    rt.saveMaxFile(str(OUT / 'ribbon-baked.max'), quiet=True)
    return {'frames': 21, 'boneCount': len(nodes), 'rootMotion': True, 'maxLengthError': error,
            'keyTracks': len(actual_keys), 'endPosition': result[-1][-1][3],
            'undoMaxMatrixDelta': undo_delta, 'undoRestoresKeyTracks': True,
            'scene': str(OUT / 'ribbon-baked.max')}


def hierarchy_rejection():
    nodes = make_chain('hierarchy')
    window = plugin.window
    window.read()
    nodes[2].parent = nodes[0]
    before = matrices(nodes)
    before_keys = key_tracks(nodes)
    window.solve()
    assert '失败' in window.status.text() and '层级已改变' in window.status.text(), window.status.text()
    assert matrices(nodes) == before and key_tracks(nodes) == before_keys
    assert window.run.isEnabled()
    rt.clearSelection()
    window.read()
    assert window.chain == []
    return {'status': '解算失败：骨骼层级已改变，请重新读取', 'noSceneChanges': True, 'staleChainCleared': True}


def injected_failure_rollback():
    nodes = make_chain('fault', moving=True)
    window = plugin.window
    window.read()
    before = matrices(nodes)
    before_keys = key_tracks(nodes)
    class RuntimeFault:
        count = 0
        def __getattr__(self, name):
            return getattr(rt, name)
        def matrix3(self, *args):
            self.count += 1
            if self.count == 5:
                raise RuntimeError('RIBBON_QA_INJECTED_WRITE_FAILURE')
            return rt.matrix3(*args)
    fault = RuntimeFault()
    original = plugin.rt
    try:
        plugin.rt = fault
        window.solve()
    finally:
        plugin.rt = original
    assert fault.count == 5
    assert '失败' in window.status.text() and 'RIBBON_QA_INJECTED_WRITE_FAILURE' in window.status.text(), window.status.text()
    assert window.run.isEnabled()
    delta = max_delta(before, matrices(nodes))
    assert delta < .001, ('failed operation left transforms', delta)
    assert key_tracks(nodes) == before_keys, ('failed operation left keys', before_keys, key_tracks(nodes))
    return {'failureAfterMatrixCalls': fault.count, 'status': window.status.text(),
            'maxMatrixDelta': delta, 'keyTracksRestored': True, 'buttonReenabled': True}


def reopen():
    window = plugin.window
    window.close()
    rt.fileIn(str(ROOT / 'LX_Ribbon.ms'), quiet=True)
    assert plugin.window is window and isValid(window) and not window.isVisible()
    window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert not isValid(window)
    rt.fileIn(str(ROOT / 'LX_Ribbon.ms'), quiet=True)
    assert isValid(plugin.window) and plugin.window is not window and not plugin.window.isVisible()
    return {'closeReopenReusesValidWindow': True, 'destroyReopenCreatesWindow': True, 'visible': False}


def contaminated_execute_file_context():
    """A real direct entry must not depend on the test's preloaded imports."""
    import __main__
    original_path = list(sys.path)
    original_cwd = os.getcwd()
    original_main_file = getattr(__main__, '__file__', None)
    original_modules = {name: module for name, module in sys.modules.items()
                        if name in ('rig', 'ribbon') or name.startswith(('rig.', 'ribbon.'))}
    for name in list(original_modules):
        sys.modules.pop(name, None)
    new_window = None
    try:
        sys.path[:] = [entry for entry in original_path
                       if not str(entry).replace('\\', '/').lower().startswith(str(ROOT).replace('\\', '/').lower())]
        os.chdir(str(OUT / 'temp'))
        stale_file = str(OUT / 'stale-unrelated-python-context.py')
        __main__.__file__ = stale_file
        rt.fileIn(str(ROOT / 'LX_Ribbon.ms'), quiet=True)
        loaded = sys.modules.get('ribbon.plugin')
        assert loaded is not None, 'Entry failed to import ribbon.plugin without preloaded project path'
        assert Path(loaded.__file__).resolve() == (ROOT / 'ribbon/plugin.py').resolve(), loaded.__file__
        new_window = loaded.window
        assert isValid(new_window) and not new_window.isVisible()
        return {'preexistingMainFile': stale_file, 'workingDirectory': str(OUT / 'temp'),
                'loadedPluginFile': loaded.__file__, 'preloadedProjectImportsRemoved': True,
                'visible': False}
    finally:
        if new_window is not None and isValid(new_window):
            new_window.close()
        os.chdir(original_cwd)
        sys.path[:] = original_path
        if original_main_file is None:
            __main__.__dict__.pop('__file__', None)
        else:
            __main__.__file__ = original_main_file
        for name in list(sys.modules):
            if name in ('rig', 'ribbon') or name.startswith(('rig.', 'ribbon.')):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)


# Keep the real business window and entry code; suppress only presentation to
# avoid foreground UI. This does not claim mouse-driven/window layout testing.
show_calls = []
original_show = QtWidgets.QDialog.show
original_raise = QtWidgets.QDialog.raise_
QtWidgets.QDialog.show = lambda self: show_calls.append(self.windowTitle())
QtWidgets.QDialog.raise_ = lambda self: None
try:
    for name, fn in [('local_package_exactness', package_check),
                     ('direct_maxscript_entry', direct_entry),
                     ('native_bridge_entry', bridge_entry),
                     ('no_selection_failure', no_chain),
                     ('moving_root_bake_length_keys_and_undo', bake_success),
                     ('changed_hierarchy_rejected_without_changes', hierarchy_rejection),
                     ('partial_write_failure_rolls_back_and_reports_error', injected_failure_rollback),
                     ('close_and_reopen', reopen),
                     ('entry_from_clean_path_and_stale_main_file', contaminated_execute_file_context)]:
        check(name, fn)
finally:
    QtWidgets.QDialog.show = original_show
    QtWidgets.QDialog.raise_ = original_raise
    try:
        rt.LXMaxBridgeTimer.Stop()
    except Exception:
        pass
    if hasattr(plugin, 'window') and isValid(plugin.window):
        plugin.window.close()
REPORT['suppressedShowCalls'] = len(show_calls)
REPORT['ok'] = bool(REPORT['checks']) and all(item['ok'] for item in REPORT['checks'])
save()
print('RIBBON_ACCEPTANCE_DONE', REPORT['ok'], str(OUT / 'host-report.json'), flush=True)
