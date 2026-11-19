"""Real bridge handshake checks, only in this runner's disposable Max batch.

No UI, existing-process attachment, scene reset, or business tool entry is used.
One owned provider child verifies hello/status against the disposable session.
The alternate package is a minimal three-file bridge fixture.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from queue import Empty, Queue


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.dont_write_bytecode = True
    source = Path(main.__code__.co_filename).resolve().parents[2]
    if os.environ.get('LX_CONNECT_BATCH') != '1':
        raise RuntimeError('Use run_connection_batch.py; never run in a user Max')
    root = Path(os.environ['LX_CONNECT_ROOT']).resolve()
    run = Path(os.environ['LX_CONNECT_RUN']).resolve()
    allowed = source.parent / 'acceptance/max-connect-2026-11-19/host'
    if root.drive.casefold() != 'e:' or not run.is_relative_to(allowed) or not run.is_dir():
        raise RuntimeError('Package and unique batch output must stay on E:')
    for key in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
                'ADSK_3DSMAX_APPDATA_DIR', 'ADSK_3DSMAX_USERSETTINGS_DIR'):
        value = os.environ.get(key, '')
        if not value or not Path(value).resolve().is_relative_to(run):
            raise RuntimeError('Environment escaped the isolated run: ' + key)
    from pymxs import runtime as rt
    process = rt.dotNetClass('System.Diagnostics.Process').GetCurrentProcess()
    command = str(rt.dotNetClass('System.Environment').CommandLine)
    normalized = command.replace('\\', '/').casefold()
    ini = run / 'profile/3dsmax.ini'
    if (not re.search(r'(?:^|\s)-batch(?:\s|$)', command, re.I)
            or ini.as_posix().casefold() not in normalized
            or Path(main.__code__.co_filename).resolve().as_posix().casefold() not in normalized):
        raise RuntimeError('Only this entry in the new dedicated batch is permitted')
    receipt_path = run / 'launch.json'
    deadline = time.monotonic() + 5
    while not receipt_path.is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    launch = json.loads(receipt_path.read_text('utf-8'))
    if launch.get('nonce') != os.environ.get('LX_CONNECT_NONCE') or not launch.get('nonce'):
        raise RuntimeError('Unique launcher receipt does not match this worker')
    if Path(launch['root']).resolve() != root or Path(launch['run']).resolve() != run:
        raise RuntimeError('Launcher package/output does not match worker')
    if Path(str(process.MainModule.FileName)).resolve() != Path(launch['workerExecutable']).resolve():
        raise RuntimeError('Unexpected worker executable')
    year = int(rt.maxVersion()[0]) // 1000 + 1998
    if year != 2026:
        raise RuntimeError('This host fixture is scheduled for Max 2026 only')
    convert = rt.dotNetClass('System.Convert')
    birth = str(convert.ToString(process.StartTime.ToUniversalTime().Ticks))
    report = dict(ok=False, pid=os.getpid(), entryIsolatedPID=True,
                  workerBirthUTC=str(process.StartTime.ToUniversalTime().ToString('o')),
                  workerBirthFileTime=str(convert.ToString(process.StartTime.ToUniversalTime().ToFileTimeUtc())),
                  workerBirthDotNetTicks=birth, command=command,
                  executable=str(process.MainModule.FileName), root=str(root), output=str(run),
                  nonce=launch['nonce'], year=year, checks=[],
                  scope='Dedicated hidden Max; real bridge/provider handshake with synthetic scene; no visible UI acceptance',
                  currentUserWindowVerified=False, providerHelloVerified=False,
                  fullAlternatePackageVerified=False)
    report['initializationFaultInjected'] = os.environ.get('LX_CONNECT_INIT_FAULT') == '1'

    def write_report():
        temporary = run / 'report.json.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temporary, run / 'report.json')

    write_report()  # Publish worker PID/birth before any scene/bridge mutation.
    startup_holds = 0
    created = []
    test_hold = False
    baseline = None
    original_selection = list(rt.selection)

    def scene(token=False):
        nodes = []
        for node in rt.objects:
            tm = node.transform
            nodes.append(dict(id=int(rt.getHandleByAnim(node)), name=str(node.name),
                              parent=int(rt.getHandleByAnim(node.parent)) if node.parent else None,
                              matrix=[[float(v.x), float(v.y), float(v.z)]
                                      for v in (tm.row1, tm.row2, tm.row3, tm.row4)],
                              hidden=bool(node.isNodeHidden)))
        value = dict(nodes=sorted(nodes, key=lambda n: n['id']),
                     selection=[int(rt.getHandleByAnim(n)) for n in rt.selection],
                     time=str(rt.currentTime), range=str(rt.animationRange),
                     file=str(rt.maxFilePath) + str(rt.maxFileName))
        if token:
            value['sceneToken'] = str(rt.LXRigSceneToken)
        return value

    initial = scene()
    files = ('bridge/LXMaxBridge.ms', 'bridge/rig_context.ms', '.lxtool/manifest.json')

    def heartbeat(expected_root):
        rows = (session / 'info').read_text('utf-8').splitlines()
        assert len(rows) == 4 and rows[0] == '2', rows
        decoded_root = Path(base64.b64decode(rows[1], validate=True).decode('utf-8')).resolve()
        decoded_scene = base64.b64decode(rows[2], validate=True).decode('utf-8')
        assert decoded_root == expected_root.resolve(), (decoded_root, expected_root)
        assert decoded_scene == (baseline['file'] or 'Untitled'), decoded_scene
        assert rows[3] == '2026', rows
        assert Path(str(rt.LXMaxBridgeSession)).resolve() == session
        return dict(protocol=2, root=str(decoded_root), year=int(rows[3]), session=str(session))

    def request(target_root, **overrides):
        values = dict(pid=str(os.getpid()), birth=birth,
                      expires=str(convert.ToString(rt.dotNetClass('System.DateTime').UtcNow.AddSeconds(30).Ticks)),
                      target=base64.b64encode(str(target_root).encode('utf-8')).decode('ascii'),
                      sha256=digest(target_root / 'bridge/LXMaxBridge.ms'))
        values.update(overrides)
        rows = ['LXCONNECT1'] + [values[k] for k in ('pid', 'birth', 'expires', 'target', 'sha256')]
        path = session / (uuid.uuid4().hex + '.connect')
        temporary = path.with_suffix('.tmp')
        temporary.write_text('\n'.join(rows), 'utf-8')
        os.replace(temporary, path)
        return path

    def invoke():
        try:
            return bool(rt.LXMaxBridgeConnect())
        finally:
            rt.LXMaxBridgeTimer.Stop()  # New loader starts its own timer.

    def reject(target_root, expected='', **overrides):
        previous = Path(str(rt.LXMaxBridgeRoot)).resolve()
        path = request(target_root, **overrides)
        assert not invoke(), 'Invalid request was accepted'
        assert not path.exists(), 'Invalid request was left pending'
        result = Path(str(path) + '.result')
        assert result.is_file() and result.read_text('utf-8-sig').strip(), 'No rejection receipt'
        if expected:assert expected in result.read_text('utf-8-sig'),result.read_text('utf-8-sig')
        assert Path(str(rt.LXMaxBridgeRoot)).resolve() == previous
        heartbeat(previous)
        return dict(rejected=True, error=result.read_text('utf-8-sig'), request=str(path))

    def check(name, function):
        item = dict(name=name, ok=False)
        report['checks'].append(item)
        report['activeCase'] = name
        write_report()
        try:
            item.update(function() or {})
            assert scene(True) == baseline, 'Handshake changed the scene, hierarchy, transforms or selection'
            item.update(ok=True, sceneUnchanged=True)
        except Exception:
            item['error'] = traceback.format_exc()
        write_report()

    try:
        for name in launch['sourceDigests']:
            assert digest(root / name) == launch['sourceDigests'][name], 'Resource changed after launch: ' + name
        # Only this verified disposable batch's startup transaction is balanced.
        while rt.theHold.Holding() and startup_holds < 8:
            rt.theHold.Accept('LX isolated connection batch entry')
            startup_holds += 1
        assert not rt.theHold.Holding(), 'Unexpected nested startup hold'
        report['batchStartupHolds'] = startup_holds
        user_root = run / 'session-root/LXMaxTools'
        rt.LXMaxBridgeRequestedUserRoot = str(user_root)
        rt.fileIn(str(root / 'bridge/LXMaxBridge.ms'), quiet=True)
        rt.LXMaxBridgeTimer.Stop()
        session = user_root / 'sessions' / (str(os.getpid()) + '-' + birth)
        assert Path(str(rt.LXMaxBridgeSession)).resolve() == session
        report['sessionRoot'] = str(user_root)
        alternate = run / 'alternate-package'
        for name in files:
            target = alternate / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        incomplete = run / 'missing-manifest-package'
        (incomplete / 'bridge').mkdir(parents=True)
        for name in files[:2]:
            shutil.copyfile(root / name, incomplete / name)
        broken = run / 'broken-context-package'
        for name in files:
            target = broken / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        (broken / 'bridge/rig_context.ms').write_text('throw "LX handshake broken context fixture"', 'utf-8')
        report['alternateRoot'] = str(alternate)
        report['fixtureFiles'] = list(files)
        box = rt.Box(name='LX_ConnectionFixture_Box', width=7, length=9, height=11, pos=rt.Point3(3, 5, 7))
        created.append(box)
        bone = rt.boneSys.createBone(rt.Point3(0, 0, 0), rt.Point3(0, 0,20), rt.Point3(0, 1, 0))
        created.append(bone)
        bone.name = 'LX_ConnectionFixture_Bone'
        box.parent = bone
        rt.select(rt.Array(box, bone))
        baseline = scene(True)
        report['fixtureScene'] = baseline
        check('source_heartbeat', lambda: heartbeat(root))

        def switch():
            path = request(alternate)
            assert invoke(), 'Valid reconnect was not accepted'
            assert not path.exists() and not Path(str(path) + '.result').exists()
            assert Path(str(rt.LXMaxBridgeRoot)).resolve() == alternate
            return heartbeat(alternate)

        check('switch_package_root', switch)

        def provider_hello():
            assert Path(str(rt.LXMaxBridgeRoot)).resolve() == alternate
            assert not list(user_root.rglob('*.connect')), 'Unexpected pre-existing connection request'
            messages = Queue()
            environment = dict(os.environ, LOCALAPPDATA=str(user_root.parent))
            outcome = dict(providerPid=None, providerExitCode=None)
            with (run / 'provider-stderr.log').open('w', encoding='utf-8') as errors:
                child = subprocess.Popen([str(root / 'bin/LXMaxSession.exe')], cwd=root, env=environment,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                         text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
                outcome['providerPid'] = child.pid
                report['provider'] = outcome
                write_report()

                def read_output():
                    try:
                        for line in child.stdout:
                            messages.put(('line', line))
                    except Exception as error:
                        messages.put(('error', str(error)))
                    finally:
                        messages.put(('eof', None))

                reader = threading.Thread(target=read_output, daemon=True)
                reader.start()

                def send(op):
                    identity = uuid.uuid4().hex
                    child.stdin.write(json.dumps(dict(op=op, id=identity)) + '\n')
                    child.stdin.flush()
                    try:
                        kind, value = messages.get(timeout=10)
                    except Empty:
                        raise AssertionError('Provider response timed out: ' + op) from None
                    assert kind == 'line', ('Provider exited or failed', kind, value)
                    data = json.loads(value)
                    assert data.get('protocol') == 1 and data.get('id') == identity and data.get('ok'), data
                    assert Path(data['sessionRoot']).resolve() == user_root.resolve()
                    return data

                try:
                    hello = send('hello')
                    own = next(s for s in hello['sessions'] if s['id'] == session.name)
                    assert own['state'] == 'connecting' and own['version'] == '2026', own
                    assert not any(s['state'] == 'connecting' and s['id'] != session.name for s in hello['sessions'])
                    requests = list(user_root.rglob('*.connect'))
                    assert len(requests) == 1 and requests[0].parent.resolve() == session.resolve(), requests
                    assert scene(True) == baseline
                    try:
                        rt.LXMaxBridgeTick()
                    finally:
                        rt.LXMaxBridgeTimer.Stop()
                    status = send('status')
                    ready = next(s for s in status['sessions'] if s['id'] == session.name)
                    assert ready['state'] == 'ready', ready
                    assert Path(str(rt.LXMaxBridgeRoot)).resolve() == root
                    assert not list(user_root.rglob('*.connect')), 'Provider request was not consumed'
                    heartbeat(root)
                    assert scene(True) == baseline
                    outcome.update(helloState=own['state'], statusState=ready['state'],
                                   scannedProcesses=len(hello['sessions']), onlyOwnSessionRequested=True,
                                   unchangedHostLocalAppData=os.environ['LOCALAPPDATA'] != environment['LOCALAPPDATA'])
                finally:
                    child.stdin.close()
                    try:
                        outcome['providerExitCode'] = child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        # Only this Popen child; never enumerate/terminate Max.
                        outcome['providerNormalExit'] = False
                        child.kill()
                        outcome['providerExitCode'] = child.wait(timeout=5)
                        raise AssertionError('Owned provider did not exit after stdin close') from None
                    finally:
                        reader.join(timeout=2)
                        child.stdout.close()
                        write_report()
                assert outcome['providerExitCode'] == 0, outcome
                outcome['providerNormalExit'] = True
                report['providerHelloVerified'] = True
                return outcome

        check('provider_hello_automatic_reconnect', provider_hello)
        check('reject_wrong_pid', lambda: reject(root, expected='连接目标已变化',pid=str(os.getpid() + 1)))
        check('reject_wrong_birth', lambda: reject(root, expected='连接目标已变化',birth=str(int(birth) + 1)))
        check('reject_expired', lambda: reject(root, expected='连接请求已过期',expires='0'))
        check('reject_hash', lambda: reject(root, expected='目标连接脚本摘要不符',sha256='0' * 64))
        check('reject_missing_manifest', lambda: reject(incomplete,expected='目标不是完整工具包'))
        check('reject_malformed_root', lambda: reject(root, target='not-base64!'))

        def recover_initialization_failure():
            outcome = reject(broken, expected='LX handshake broken context fixture')
            assert Path(str(rt.LXMaxBridgeRoot)).resolve() == root
            rt.LXMaxBridgeTimer.Start()
            assert rt.LXMaxBridgeTimer.Enabled, 'Restored bridge timer cannot resume'
            rt.LXMaxBridgeTick()
            rt.LXMaxBridgeTimer.Stop()
            heartbeat(root)
            return dict(restoredOriginalConnection=True, **outcome)

        if report['initializationFaultInjected']:
            # A failing fileIn may also set the batch handled-exception exit
            # status. Keep fault diagnostics separate from the normal gate.
            check('recover_failed_package_initialization', recover_initialization_failure)

        def hold_then_retry():
            nonlocal test_hold
            previous = Path(str(rt.LXMaxBridgeRoot)).resolve()
            path = request(alternate)
            rt.theHold.Begin()
            test_hold = True
            try:
                assert rt.theHold.Holding()
                assert not invoke(), 'Reconnect entered an active undo transaction'
                assert path.exists() and not Path(str(path) + '.result').exists(), 'Busy request was consumed'
                assert Path(str(rt.LXMaxBridgeRoot)).resolve() == previous
                assert scene(True) == baseline
                rt.theHold.Accept('LX isolated handshake hold test')
                test_hold = False
                assert not rt.theHold.Holding()
                assert invoke(), 'Deferred request did not connect after Accept'
                assert not path.exists()
                return dict(deferredWhileHolding=True, acceptedAfterHold=True, **heartbeat(alternate))
            finally:
                if test_hold and rt.theHold.Holding():
                    rt.theHold.Cancel()
                test_hold = False

        check('defer_during_undo_then_reconnect', hold_then_retry)
        report['resourcesUnchanged'] = all(digest(root / name) == value for name, value in launch['sourceDigests'].items())
        report['sceneUnchanged'] = scene(True) == baseline
        expected_checks = 11 if report['initializationFaultInjected'] else 10
        report['ok'] = (len(report['checks']) == expected_checks and all(item['ok'] for item in report['checks'])
                        and report['sceneUnchanged'] and report['resourcesUnchanged'])
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        try:
            previous_timer = rt.LXMaxBridgeTimer
            previous_timer.Stop()
            rt.dotNet.removeAllEventHandlers(previous_timer)
            previous_timer.Dispose()
            report['bridgeTimerDisposed'] = True
        except Exception:
            pass
        try:
            if test_hold and rt.theHold.Holding():
                rt.theHold.Cancel()
            for node in reversed(created):
                if rt.isValidNode(node):
                    rt.delete(node)
            rt.select(rt.Array(*[n for n in original_selection if rt.isValidNode(n)]))
            report['fixturesRemoved'] = scene() == initial
            if not report['fixturesRemoved']:
                report['ok'] = False
        except Exception:
            report.update(ok=False, cleanupError=traceback.format_exc())
        for _ in range(startup_holds):
            rt.theHold.Begin()
        report.pop('activeCase', None)
        write_report()
    print(json.dumps(dict(ok=report['ok'], pid=report['pid'], report=str(run / 'report.json'),
                          checksPassed=sum(item['ok'] for item in report['checks'])), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
