"""Real provider EXE, isolated E profile, harmless launcher fixture (not Max)."""
from pathlib import Path
import sys,os,json,subprocess,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'acceptance/maxsuite-portable-2026-11-10'
OUT.mkdir(exist_ok=True)
env=dict(os.environ)
for key in ('LOCALAPPDATA','APPDATA','USERPROFILE','TEMP','TMP'):
    p=OUT/key;p.mkdir(exist_ok=True);env[key]=str(p)
local=Path(env['LOCALAPPDATA']);expected=local/'LXMaxTools'
proof=OUT/'launcher.json';env['LX_TEST_OUTPUT']=str(proof)
source=OUT/'launcher.cs';exe=OUT/'3dsmax.exe'
source.write_text('''using System; using System.IO; using System.Threading;
class TestLauncher {static void Main(string[] args) {
 File.WriteAllText(Environment.GetEnvironmentVariable("LX_TEST_OUTPUT"),String.Join("\\n",args)+"\\n"+Environment.GetEnvironmentVariable("LOCALAPPDATA"));
 Thread.Sleep(3000);
}}''',encoding='utf-8')
csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(csc),'/nologo','/target:winexe','/out:'+str(exe),str(source)],env=env,check=True,capture_output=True)
config=expected/'max-path.txt';config.parent.mkdir(exist_ok=True);config.write_text(str(exe),encoding='utf-8')
def exchange(requests,environment):
    result=subprocess.run([str(ROOT/'bin/LXMaxSession.exe')],input=''.join(json.dumps(r)+'\n' for r in requests),text=True,encoding='utf-8',capture_output=True,env=environment,timeout=25)
    return result,[json.loads(l) for l in result.stdout.splitlines() if l.strip()]
result,responses=exchange([dict(op='hello'),dict(op='launch',applicationPath=str(exe))],env)
assert result.returncode==0,(result.returncode,result.stderr)
assert all(r['ok'] for r in responses),responses
assert Path(responses[0]['sessionRoot'])==expected
assert Path(responses[0]['applicationPath'])==exe
managed=list((expected/'managed').glob('*.json'));assert managed
for _ in range(30):
    if proof.exists():break
    time.sleep(.1)
args=proof.read_text().splitlines();assert args[:2]==['-U','MAXScript']
wrapper=Path(args[2]);assert wrapper.is_relative_to(expected)
assert 'LXMaxBridgeRequestedUserRoot' in wrapper.read_text('utf-8-sig')
assert Path(args[3])==local
config.unlink()
shelf=local/'LXTool/repository-tools-v2.json';shelf.parent.mkdir(exist_ok=True)
shelf.write_text(json.dumps({'applications':{'repo-1342543761':{'max':{'path':str(exe)}}}}),encoding='utf-8')
_,reply=exchange([dict(op='hello')],env);assert Path(reply[0]['applicationPath'])==exe
for value in ('relative/path','E:relative','\\relative',''):
    invalid=dict(env,LOCALAPPDATA=value)
    failure,_=exchange([dict(op='hello')],invalid)
    assert failure.returncode!=0,value
sys.path.insert(0,str(ROOT));os.environ.update({k:env[k] for k in ('LOCALAPPDATA','APPDATA','USERPROFILE','TEMP','TMP')})
from ui.max_connection import connection_script,install
attach=connection_script('max-tools',ROOT/'bridge/LXMaxBridge.ms')
auto=install('max-tools',ROOT/'bridge/LXMaxBridge.ms')
assert attach.is_relative_to(expected)
assert 'LXMaxBridgeRequestedUserRoot' in (auto/'loader.ms').read_text('utf-8-sig')
data=dict(ok=True,sessionRoot=str(expected),attach=str(attach),launch=str(wrapper),auto=str(auto/'loader.ms'),managed=str(managed[0]),scope='real provider EXE and harmless launcher fixture; actual Max attachment tested separately')
(OUT/'provider-report.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data))
