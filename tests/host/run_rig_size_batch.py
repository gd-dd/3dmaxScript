"""Launch a dedicated hidden Max for rig_size.py, entirely in E isolation.

Usage: python -B tests/host/run_rig_size_batch.py [unique-attempt-name]
Never launches an interactive Max or cleans up unrelated processes.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent / 'acceptance/rigskin-size-2026-11-11'
attempt = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', attempt):
    raise ValueError('Attempt must be a safe unique name')
run = OUT / 'runs' / attempt
run.mkdir(parents=True, exist_ok=False)  # Never accept an old report as this run.
profile = run / 'profile'
profile.mkdir()
template = ROOT.parent / 'acceptance/ribbon-2026-11-09/profile/3dsmax.ini'
old_root = str(template.parent.parent)
ini = template.read_text('utf-16').replace(old_root, str(run))
ini = ini.replace(old_root.replace('\\', '/'), str(run).replace('\\', '/'))
if 'ribbon-2026-11-09' in ini:
    raise ValueError('INI template still points to historical acceptance directory')
(profile / '3dsmax.ini').write_text(ini, encoding='utf-16')
env = dict(os.environ)
for key, relative in [('USERPROFILE', 'profile'), ('APPDATA', 'profile/AppData/Roaming'),
                      ('LOCALAPPDATA', 'profile/AppData/Local'), ('TEMP', 'temp'), ('TMP', 'temp')]:
    path = run / relative
    path.mkdir(parents=True, exist_ok=True)
    env[key] = str(path)
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', LX_RIG_SIZE_BATCH='1', LX_RIG_SIZE_RUN=str(run))
if len(sys.argv)>2:env['LX_RIG_RUNTIME_ROOT']=str(Path(sys.argv[2]).resolve())
for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
    env.pop(key, None)
exe = Path('E:/Ruanjian/3DSmax/3ds Max 2026')
script = ROOT / 'tests/host/rig_size.py'
args = [str(exe / '3dsmaxbatch.exe'), str(script), '-i', str(profile / '3dsmax.ini'),
        '-p', str(exe / 'zh-CN/plugin.ini'), '-v', '4',
        '-listenerlog', str(run / 'listener.log'), '-log', str(run / 'max.log')]
with (run / 'stdout.log').open('w', encoding='utf-8') as stdout, (run / 'stderr.log').open('w', encoding='utf-8') as stderr:
    process = subprocess.Popen(args, env=env, cwd=run, stdout=stdout, stderr=stderr,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    launch = dict(pid=process.pid, args=args, script=str(script), report=str(run / 'report.json'))
    (run / 'launch.json').write_text(json.dumps(launch, indent=2), encoding='utf-8')
    print('Dedicated rig_size launcher PID', process.pid, 'report', run / 'report.json', flush=True)
    code = process.wait()
    launch['exitCode'] = code
    (run / 'launch.json').write_text(json.dumps(launch, indent=2), encoding='utf-8')
report_path = run / 'report.json'
if not report_path.exists():
    raise RuntimeError('Dedicated Max did not write its new rig_size report; exit=' + str(code))
report = json.loads(report_path.read_text('utf-8'))
(OUT / (attempt + '-report.json')).write_bytes(report_path.read_bytes())
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
sys.exit(0 if code == 0 and report.get('ok') else 1)
