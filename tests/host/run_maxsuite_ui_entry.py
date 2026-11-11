"""Run all nine parent tools in one new hidden Max, after owner scheduling.

Usage: python -B tests/host/run_maxsuite_ui_entry.py RUN_NAME PACKAGE_ROOT
Run source and extracted ZIP roots sequentially in separate invocations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def process_birth(process):
    """Read creation time from this Popen handle only; never enumerate processes."""
    import ctypes
    from ctypes import wintypes
    from datetime import timedelta
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    creation, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(wintypes.HANDLE(int(process._handle)), ctypes.byref(creation),
                                  ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    stamp = epoch + timedelta(seconds=ticks // 10000000)
    birth = stamp.strftime('%Y-%m-%dT%H:%M:%S') + '.' + format(ticks % 10000000, '07d') + 'Z'
    return dict(launcherBirthUTC=birth, launcherBirthFileTime=str(ticks))


class OwnedWorkerProbe:
    """Hold only the PID/birth identified in this unique run's worker report."""
    def __init__(self, report_path):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.report_path, self.handle = report_path, None
        self.record = dict(workerIdentityMatched=False, actualWorkerExitCode=None)

    def capture(self):
        if self.handle is not None or not self.report_path.is_file(): return False
        try:
            report = json.loads(self.report_path.read_text('utf-8'))
        except (OSError, ValueError):
            return False  # The worker can be atomically between report writes.
        if not all(k in report for k in ('pid', 'workerBirthFileTime')): return False
        pid, expected = int(report['pid']), str(report['workerBirthFileTime'])
        if pid <= 0 or not expected.isdigit():
            raise RuntimeError('Worker report has an invalid process identity')
        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION; no terminate access.
        handle = self.kernel.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            self.record['workerOpenError'] = self.ctypes.get_last_error()
            return False
        creation, exited, kernel_time, user_time = (self.wintypes.FILETIME() for _ in range(4))
        try:
            if not self.kernel.GetProcessTimes(handle, self.ctypes.byref(creation), self.ctypes.byref(exited),
                                               self.ctypes.byref(kernel_time), self.ctypes.byref(user_time)):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            actual = str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            if actual != expected:
                raise RuntimeError('Worker PID birth mismatches the unique run report')
            self.record.update(workerPid=pid, workerBirthUTC=report.get('workerBirthUTC'),
                               workerBirthFileTime=actual, workerIdentityMatched=True)
            self.handle = handle
            return True
        finally:
            if self.handle is None: self.kernel.CloseHandle(handle)

    def finish(self):
        if self.handle is None: return self.record
        try:
            wait = self.kernel.WaitForSingleObject(self.handle, 10000)
            code = self.wintypes.DWORD()
            if not self.kernel.GetExitCodeProcess(self.handle, self.ctypes.byref(code)):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            self.record.update(actualWorkerExitCode=int(code.value), workerWaitResult=int(wait),
                               workerExitObserved=wait == 0)
            return self.record
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_name')
    parser.add_argument('package_root', type=Path)
    parser.add_argument('--probe', choices=('noqt', 'qt-import-only', 'qt-pump', 'qt-global-deferred'))
    parser.add_argument('--profile-mode', choices=('original', 'split', 'align-settings', 'align-both'), default='align-settings')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_name):
        parser.error('run_name must be a safe, unique name')
    source = Path(main.__code__.co_filename).resolve().parents[2]
    root = args.package_root.resolve()
    if root.drive.casefold() != 'e:':
        parser.error('package_root must be on E:')
    for name in ('.lxtool/manifest.json', 'LX_RigSkin.ms', 'LX_Ribbon.ms', 'LX_Retarget.ms'):
        if not (root / name).is_file():
            parser.error('complete parent package required: ' + name)
    manifest = json.loads((root / '.lxtool/manifest.json').read_text('utf-8-sig'))
    for name, digest in manifest['files'].items():
        resource = (root / name).resolve()
        if not resource.is_relative_to(root) or not resource.is_file():
            parser.error('unsafe or missing package resource: ' + name)
        if hashlib.sha256(resource.read_bytes()).hexdigest() != digest:
            parser.error('package resource changed before launch: ' + name)
    out = source.parent / 'acceptance/maxsuite-ui-2026-11-12/host-runs'
    run = out / args.run_name
    run.mkdir(parents=True, exist_ok=False)  # An old report can never pass a new run.
    profile = run / 'profile'
    profile.mkdir()
    template = source.parent / 'acceptance/ribbon-2026-11-09/profile/3dsmax.ini'
    previous = str(template.parent.parent)
    ini = template.read_text('utf-16').replace(previous, str(run))
    ini = ini.replace(previous.replace('\\', '/'), str(run).replace('\\', '/'))
    if 'ribbon-2026-11-09' in ini:
        raise RuntimeError('INI still points to the historical acceptance directory')
    (profile / '3dsmax.ini').write_text(ini, encoding='utf-16')
    ini_paths = {}
    for line in ini.splitlines():
        if '=' not in line: continue
        key, value = line.split('=', 1)
        if key.strip().lower() in ('maxdata', 'user settings'):
            path = Path(value.strip().rstrip('\\/')).resolve()
            if not path.is_relative_to(run):
                raise RuntimeError('INI data/settings path escaped the unique E run')
            ini_paths[key.strip().lower()] = path
    if not {'maxdata', 'user settings'} <= set(ini_paths):
        raise RuntimeError('INI must explicitly define MaxData and User Settings')
    env = dict(os.environ)
    paths = {'USERPROFILE': 'profile', 'APPDATA': 'profile/AppData/Roaming',
             'LOCALAPPDATA': 'profile/AppData/Local', 'TEMP': 'temp', 'TMP': 'temp',
             'ADSK_3DSMAX_APPDATA_DIR': 'profile/MaxAppData',
             'ADSK_3DSMAX_USERSETTINGS_DIR': 'profile/MaxSettings'}
    if args.profile_mode in ('align-settings', 'align-both'):
        paths['ADSK_3DSMAX_USERSETTINGS_DIR'] = str(ini_paths['user settings'])
    if args.profile_mode == 'align-both':
        paths['ADSK_3DSMAX_APPDATA_DIR'] = str(ini_paths['maxdata'])
    for key, relative in paths.items():
        folder = (run / relative).resolve()
        if not folder.is_relative_to(run):
            raise RuntimeError('Fixture environment path escaped the unique E run: ' + key)
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               LX_MAXSUITE_UI_ENTRY='1', LX_MAXSUITE_UI_ROOT=str(root),
               LX_MAXSUITE_UI_RUN=str(run))
    if args.probe:
        env['LX_MAXSUITE_EXIT_PROBE_MODE'] = args.probe
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH',
                'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    max_home = Path('E:/Ruanjian/3DSmax/3ds Max 2026')
    script = source / ('tests/host/maxsuite_exit_probe.py' if args.probe else 'tests/host/maxsuite_ui_entry.py')
    command = [str(max_home / '3dsmaxbatch.exe'), str(script),
               '-i', str(profile / '3dsmax.ini'), '-p', str(max_home / 'zh-CN/plugin.ini'),
               '-v', '5', '-listenerlog', str(run / 'listener.log'),
               '-log', str(run / 'max.log')]
    launch = dict(root=str(root), run=str(run), script=str(script), command=command,
                  createdAtUTC=datetime.now(timezone.utc).isoformat(),
                  verbosity=5,
                  mode=args.probe or 'full-nine-entry',
                  profileMode=args.profile_mode,
                  safeEnvironment={key: env[key] for key in paths},
                  iniDataPaths={key: str(value) for key, value in ini_paths.items()},
                  iniSha256=hashlib.sha256((profile / '3dsmax.ini').read_bytes()).hexdigest(),
                  scope='New dedicated hidden batch; never attach to an existing Max')
    with (run / 'stdout.log').open('w', encoding='utf-8') as stdout, (run / 'stderr.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        launch['launcherPid'] = process.pid
        try:
            launch.update(process_birth(process))
        except Exception as error:
            launch['birthReadError'] = str(error)
            launch['exitCode'] = process.wait()
            (run / 'launch.json').write_text(json.dumps(launch, indent=2), 'utf-8')
            raise
        (run / 'launch.json').write_text(json.dumps(launch, indent=2), 'utf-8')
        print('Dedicated parent UI launcher PID', process.pid, 'birth', launch['launcherBirthUTC'],
              'report', run / 'report.json', flush=True)
        probe = OwnedWorkerProbe(run / 'report.json')
        while process.poll() is None:
            if probe.capture():
                launch.update(probe.record)
                (run / 'launch.json').write_text(json.dumps(launch, indent=2), 'utf-8')
                print('Matched worker PID', probe.record['workerPid'], 'birth', probe.record['workerBirthUTC'], flush=True)
            time.sleep(.2)
        launch['launcherExitCode'] = process.wait()
        launch['exitCode'] = launch['launcherExitCode']  # Preserve the existing receipt field.
        probe.capture()
        launch.update(probe.finish())
    (run / 'launch.json').write_text(json.dumps(launch, indent=2), 'utf-8')
    report_path = run / 'report.json'
    if not report_path.is_file():
        raise RuntimeError('The new batch did not produce its report; exit=' + str(launch['exitCode']))
    report = json.loads(report_path.read_text('utf-8'))
    print(json.dumps(dict(report=str(report_path), ok=report.get('ok'),
                          checksPassed=sum(item['ok'] for item in report.get('checks', [])),
                          screenshots=len(report.get('screenshots', [])),
                          launcherExitCode=launch['launcherExitCode'],
                          actualWorkerExitCode=launch['actualWorkerExitCode'],
                          workerIdentityMatched=launch['workerIdentityMatched']), ensure_ascii=False), flush=True)
    return 0 if (launch['launcherExitCode'] == 0 and launch['workerIdentityMatched']
                 and launch['actualWorkerExitCode'] == 0 and report.get('ok')) else 1


if __name__ == '__main__':
    sys.exit(main())
