"""Launch only our disposable hidden Max; no broad process cleanup."""
from pathlib import Path
import os,sys,subprocess,json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'acceptance/rigskin-existing-2026-11-10'
attempt=sys.argv[1] if len(sys.argv)>1 else '1'
profile=OUT/'profile';profile.mkdir(parents=True,exist_ok=True)
source=ROOT.parent/'acceptance/ribbon-2026-11-09/profile/3dsmax.ini'
ini=source.read_text('utf-16').replace('ribbon-2026-11-09','rigskin-existing-2026-11-10')
(profile/'3dsmax.ini').write_text(ini,encoding='utf-16')
env=dict(os.environ)
for key,relative in [('USERPROFILE','profile'),('APPDATA','profile/AppData/Roaming'),('LOCALAPPDATA','profile/AppData/Local'),('TEMP','temp'),('TMP','temp')]:
    p=OUT/relative;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
env['PYTHONDONTWRITEBYTECODE']='1'
for key in ('PYTHONHOME','PYTHONPATH','QT_QPA_PLATFORM','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key,None)
exe=Path('E:/Ruanjian/3DSmax/3ds Max 2026')
args=[str(exe/'3dsmaxbatch.exe'),str(ROOT/'tests/host/rig_existing.py'),'-i',str(profile/'3dsmax.ini'),'-p',str(exe/'zh-CN/plugin.ini'),'-v','4','-listenerlog',str(OUT/f'{attempt}-listener.log'),'-log',str(OUT/f'{attempt}-max.log')]
with (OUT/f'{attempt}-stdout.log').open('w',encoding='utf-8') as stdout,(OUT/f'{attempt}-stderr.log').open('w',encoding='utf-8') as stderr:
    process=subprocess.Popen(args,env=env,cwd=OUT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    (OUT/f'{attempt}-launch.json').write_text(json.dumps(dict(pid=process.pid,args=args),indent=2),encoding='utf-8')
    print('dedicated launcher PID',process.pid,flush=True)
    code=process.wait();print('exit',code,flush=True)
if (OUT/'report.json').exists():
    (OUT/f'{attempt}-report.json').write_bytes((OUT/'report.json').read_bytes())
    print((OUT/'report.json').read_text('utf-8'))


