"""Protocol checks against an already tool-managed test Max; no external scan."""
import subprocess,json,time,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=subprocess.Popen([str(root/'bin/LXMaxSession.exe')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
def request(op,**kwargs):
    identity=uuid.uuid4().hex;p.stdin.write(json.dumps(dict(id=identity,op=op,**kwargs))+'\n');p.stdin.flush()
    response=json.loads(p.stdout.readline());assert response['id']==identity;return response
def result_for(identity,initial):
    for _ in range(80):
        for item in initial.get('results',[]):
            if item['requestId']==identity:return item['result']
        time.sleep(.1);initial=request('status')
    raise AssertionError('no result')
try:
    state=request('hello');session=next(s['id'] for s in state['sessions'] if s['state']=='ready')
    bad=request('rig',sessionId='not-managed',request={'action':'scene.inspect','params':{}});assert not bad['ok']
    sent=request('rig',sessionId=session,request={'action':'bone.rename','scene':'stale','params':{}})
    result=result_for(sent['id'],sent);assert not result['ok'] and '场景' in result['error']
    sent=request('rig',sessionId=session,request={'action':'scene.inspect','params':{}})
    cancelled=request('cancel-rig',sessionId=session,requestId=sent['id'])
    result=result_for(sent['id'],cancelled)
    if cancelled['ok']:assert not result['ok'] and '取消' in result['error']
    else:assert result['ok']
    report={'ok':True,'unmanagedRejected':True,'staleSceneRejected':True,'cancelledBeforeStart':cancelled['ok']}
    (root/'tests/provider-live-report.json').write_text(json.dumps(report,indent=2),'utf-8');print(report)
finally:
    p.stdin.close();p.wait(timeout=10)
