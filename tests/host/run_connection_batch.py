"""Prepare and run one new isolated hidden Max 2026 bridge handshake test.

Usage: python -B tests/host/run_connection_batch.py RUN_NAME [PACKAGE_ROOT]
Use --prepare-only to validate/copy E-only fixture configuration without Max.
Never attaches to, sends input to, or terminates an existing Max process.
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
import uuid


def main():
    sys.dont_write_bytecode = True
    sys.stdout.reconfigure(encoding='utf-8')
    source = Path(main.__code__.co_filename).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_name')
    parser.add_argument('package_root', nargs='?', type=Path, default=source)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--fault-initialization', action='store_true',
                        help='Separate failing-fileIn diagnostic; process exit gates remain strict')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_name):
        parser.error('run_name must be safe and unique')
    if not 30 <= args.timeout <= 900:
        parser.error('timeout must be between 30 and 900 seconds')
    root = args.package_root.resolve()
    if root.drive.casefold() != 'e:':
        parser.error('package_root must be on E:')
    files = ('bridge/LXMaxBridge.ms', 'bridge/rig_context.ms', '.lxtool/manifest.json', 'bin/LXMaxSession.exe')
    source_digests = {}
    for name in files:
        resource = (root / name).resolve()
        if not resource.is_relative_to(root) or not resource.is_file():
            parser.error('Missing/unsafe bridge resource: ' + name)
        source_digests[name] = hashlib.sha256(resource.read_bytes()).hexdigest()
    json.loads((root / '.lxtool/manifest.json').read_text('utf-8-sig'))
    run = source.parent / 'acceptance/max-connect-2026-11-19/host' / args.run_name
    run.mkdir(parents=True, exist_ok=False)
    profile = run / 'profile'
    profile.mkdir()
    template = source.parent / 'acceptance/ribbon-2026-11-09/profile/3dsmax.ini'
    previous = str(template.parent.parent)
    ini = template.read_text('utf-16').replace(previous, str(run))
    ini = ini.replace(previous.replace('\\', '/'), str(run).replace('\\', '/'))
    if 'ribbon-2026-11-09' in ini:
        raise RuntimeError('INI still references the historical acceptance directory')
    ini_paths = {}
    for line in ini.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.strip().lower() in ('maxdata', 'user settings'):
            path = Path(value.strip().rstrip('\\/')).resolve()
            if not path.is_relative_to(run):
                raise RuntimeError('INI data/settings directory escaped this run')
            ini_paths[key.strip().lower()] = path
    if not {'maxdata', 'user settings'} <= set(ini_paths):
        raise RuntimeError('INI must specify isolated MaxData and User Settings')
    ini_file = profile / '3dsmax.ini'
    ini_file.write_text(ini, 'utf-16')
    env = dict(os.environ)
    paths = dict(USERPROFILE=profile, APPDATA=profile / 'AppData/Roaming',
                 LOCALAPPDATA=profile / 'AppData/Local', TEMP=run / 'temp', TMP=run / 'temp',
                 ADSK_3DSMAX_APPDATA_DIR=ini_paths['maxdata'],
                 ADSK_3DSMAX_USERSETTINGS_DIR=ini_paths['user settings'],
                 ADSK_3DSMAX_AUTOBACKUP_DIR=run / 'temp',
                 ADSK_3DSMAX_USERTOOLS_DIR=profile / 'UserTools',
                 ADSK_APPLICATION_PLUGINS=run / 'empty-application-plugins',
                 ADSK_3DSMAX_STARTUPSCRIPTS_ADDON_DIR=run / 'empty-startup-scripts',
                 PYTHONUSERBASE=profile / 'PythonUser', XDG_CACHE_HOME=run / 'cache')
    for key, folder in paths.items():
        folder = folder.resolve()
        if not folder.is_relative_to(run):
            raise RuntimeError('Environment directory escaped this run: ' + key)
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    nonce = uuid.uuid4().hex
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONIOENCODING='utf-8',
               LX_CONNECT_BATCH='1', LX_CONNECT_ROOT=str(root), LX_CONNECT_RUN=str(run), LX_CONNECT_NONCE=nonce)
    env['LX_CONNECT_INIT_FAULT'] = '1' if args.fault_initialization else '0'
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    max_root = Path('E:/Ruanjian/3DSmax/3ds Max 2026')
    script = source / 'tests/host/connection_handshake.py'
    command = [str(max_root / '3dsmaxbatch.exe'), str(script), '-i', str(ini_file),
               '-p', str(max_root / 'zh-CN/plugin.ini'), '-v', '5',
               '-listenerlog', str(run / 'listener.log'), '-log', str(run / 'max.log')]
    launch = dict(root=str(root), run=str(run), nonce=nonce, command=command, script=str(script),
                  workerExecutable=str(max_root / '3dsmax.exe'), sourceDigests=source_digests,
                  createdAtUTC=datetime.now(timezone.utc).isoformat(),
                  safeEnvironment={key: env[key] for key in paths},
                  iniDataPaths={key: str(value) for key, value in ini_paths.items()},
                  iniSha256=hashlib.sha256(ini_file.read_bytes()).hexdigest(),
                  prepareOnly=args.prepare_only, scope='New dedicated hidden batch; no existing Max attachment')

    def receipt():
        temporary = run / 'launch.json.tmp'
        temporary.write_text(json.dumps(launch, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temporary, run / 'launch.json')

    receipt()
    if args.prepare_only:
        print(json.dumps(dict(prepared=True, launched=False, receipt=str(run / 'launch.json')), ensure_ascii=False))
        return 0
    # Reuse only the existing handle-based PID/birth observer, never its main().
    from run_maxsuite_ui_entry import process_birth, OwnedWorkerProbe
    probe = OwnedWorkerProbe(run / 'report.json')
    with (run / 'stdout.log').open('w', encoding='utf-8') as stdout, (run / 'stderr.log').open('w', encoding='utf-8') as stderr:
        worker = subprocess.Popen(command, cwd=run, env=env, stdout=stdout, stderr=stderr,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        launch['launcherPid'] = worker.pid
        launch.update(process_birth(worker))
        receipt()
        print('Dedicated connection launcher PID', worker.pid, 'report', run / 'report.json', flush=True)
        deadline = time.monotonic() + args.timeout
        while worker.poll() is None and time.monotonic() < deadline:
            if probe.capture():
                launch.update(probe.record)
                receipt()
            time.sleep(.2)
        launch['launcherExitCode'] = worker.poll()
        launch['timedOut'] = launch['launcherExitCode'] is None
        probe.capture()
        launch.update(probe.finish())
    receipt()
    report_path = run / 'report.json'
    if not report_path.is_file():
        print(json.dumps(dict(ok=False, error='No worker report', receipt=str(run / 'launch.json'))), flush=True)
        return 1
    report = json.loads(report_path.read_text('utf-8'))
    ok = (not launch['timedOut'] and launch['launcherExitCode'] == 0
          and launch.get('workerIdentityMatched') and launch.get('actualWorkerExitCode') == 0
          and report.get('entryIsolatedPID') and report.get('nonce') == nonce and report.get('ok'))
    print(json.dumps(dict(ok=bool(ok), report=str(report_path), receipt=str(run / 'launch.json'),
                          checksPassed=sum(item['ok'] for item in report.get('checks', [])),
                          timedOut=launch['timedOut'], workerPid=launch.get('workerPid'),
                          launcherExitCode=launch['launcherExitCode'],
                          actualWorkerExitCode=launch.get('actualWorkerExitCode')), ensure_ascii=False), flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
