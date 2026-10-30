from rig import max_host as H,workflow_host as F
from PySide6.QtCore import QTimer
from pathlib import Path
import json,qtmax
rt=H.rt
qtmax.GetQMaxMainWindow().showMaximized()
rt.viewport.setType(rt.Name('view_front'))
rt.execute('max zoomext sel')
root=Path(__file__).resolve().parents[2]
before=len(list(rt.objects))
def begin():
 H.dispatch({'action':'humanoid.drag','scene':str(rt.LXRigSceneToken),'params':{'prefix':'PlacementTest','fingers':0,'toes':0}})
 def report():
  created=[n for n in rt.objects if str(n.name).startswith('PlacementTest')]
  (root/'tests/host/placement-report.json').write_text(json.dumps({'before':before,'created':len(created),'ok':len(created)>15}),'utf-8')
 QTimer.singleShot(500,report)
QTimer.singleShot(300,begin)
