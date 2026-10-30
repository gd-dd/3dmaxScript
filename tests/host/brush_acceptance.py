import json
from pathlib import Path
from rig import max_host as H,brush
from PySide6.QtCore import QTimer
rt=H.rt;root=Path(__file__).resolve().parents[2]
obj=rt.getNodeByName('Box001');skin=next(m for m in obj.modifiers if H.cls(m)=='Skin')
params=dict(mesh=H.handle(obj),skinHandle=H.handle(skin),bones=['1'],mode='set',radius=6,strength=.5,value=.25)
brush.stop();baseline=H.read_rows(skin);H.dispatch({'action':'brush.start','scene':str(rt.LXRigSceneToken),'params':params})
import qtmax
watch=QTimer(qtmax.GetQMaxMainWindow());watch.setInterval(300)
def check():
 if brush._active is None:watch.stop();return
 if brush._active.holding:return
 rows=H.read_rows(skin)
 if rows!=baseline:
  (root/'tests/host/brush-native-report.json').write_text(json.dumps({'ok':True,'changed':sum(a!=b for a,b in zip(rows,baseline))}),'utf-8');watch.stop();brush.stop()
watch.timeout.connect(check);watch.start();qtmax.GetQMaxMainWindow()._lx_brush_watch=watch
