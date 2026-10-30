"""Fixed bridge entry; request JSON is data, never executable source."""
import sys,json,base64,os,uuid
from pathlib import Path
from pymxs import runtime as rt
from PySide6.QtCore import QTimer
root=Path(str(rt.LXMaxBridgeRoot))
if str(root) not in sys.path:sys.path.insert(0,str(root))
from rig.max_host import dispatch

def schedule(payload,destination):
    request=json.loads(base64.b64decode(payload).decode('utf-8'));path=Path(destination)
    def execute():
        try:result={'ok':True,'data':dispatch(request)}
        except Exception as error:result={'ok':False,'error':str(error)}
        encoded=base64.b64encode(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')).decode('ascii')
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        temp.write_text('DATA\n'+encoded,'utf-8');os.replace(temp,path)
    QTimer.singleShot(0,execute)

schedule(str(rt.LXRigPayload),str(rt.LXRigResultPath))
rt.LXRigResponse='scheduled'
