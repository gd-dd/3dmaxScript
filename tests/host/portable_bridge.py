"""Disposable Max whose birth LOCALAPPDATA differs from the shelf root."""
from pathlib import Path
import sys,os,json,subprocess,traceback
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'acceptance/maxsuite-portable-2026-11-10'
fixture=json.loads((OUT/'provider-report.json').read_text('utf-8'))
expected=Path(fixture['sessionRoot'])
born=os.environ['LOCALAPPDATA']
assert Path(born)/'LXMaxTools'!=expected
report=dict(pid=os.getpid(),birthLocalData=born,expected=str(expected),checks=[])
from PySide6.QtWidgets import QDialog
original=QDialog.show;original_raise=QDialog.raise_
QDialog.show=lambda self:None;QDialog.raise_=lambda self:None
try:
    for mode in ('launch','attach','auto'):
        rt.fileIn(fixture[mode],quiet=True)
        assert Path(str(rt.LXMaxBridgeSession)).is_relative_to(expected)
        assert os.environ['LOCALAPPDATA']==born
        rt.LXMaxBridgeHeartbeat()
        env=dict(os.environ,LOCALAPPDATA=str(expected.parent))
        process=subprocess.Popen([str(ROOT/'bin/LXMaxSession.exe')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env)
        def request(payload):
            process.stdin.write(json.dumps(payload)+'\n');process.stdin.flush();return json.loads(process.stdout.readline())
        hello=request(dict(op='hello'))
        session=next(x for x in hello['sessions'] if x['id'].startswith(str(os.getpid())+'-'))
        assert session['state']=='ready',session
        queued=request(dict(op='run',sessionId=session['id'],toolId='ribbon'));assert queued['ok'],queued
        rt.LXMaxBridgeTick()
        answer=request(dict(op='status'))
        assert any('已打开' in e for e in answer['events']),answer
        process.stdin.close();process.wait(timeout=10)
        rt.LXMaxBridgeTimer.Stop()
        report['checks'].append(dict(mode=mode,session=session['id'],events=answer['events']))
    report['ok']=True
except Exception:
    report.update(ok=False,error=traceback.format_exc())
finally:
    QDialog.show=original;QDialog.raise_=original_raise
    try:rt.LXMaxBridgeTimer.Stop()
    except Exception:pass
    (OUT/'bridge-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
