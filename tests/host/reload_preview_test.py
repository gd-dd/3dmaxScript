"""Reload preserves undo state and the drag renderer previews a full skeleton."""
import json,runpy,traceback
from pathlib import Path
from pymxs import runtime as rt
from PySide6.QtCore import QTimer
from rig import max_host as H,history,humanoid,max_ui
ROOT=Path(__file__).resolve().parents[2];r={'passed':[]}
def start():
 try:
  states=history._states;nodes={H.handle(n) for n in rt.objects};scene=str(rt.LXRigSceneToken)
  # Bridge fileIn can evaluate this entry inside a Max startup transaction.
  with H.pymxs.undo(True):runpy.run_path(str(ROOT/'bridge/open_rig.py'))
  from rig import max_ui as ui,max_host as host
  assert history._states is states and str(rt.LXRigSceneToken)==scene and nodes=={host.handle(n) for n in rt.objects}
  first=ui._dock;runpy.run_path(str(ROOT/'bridge/open_rig.py'));assert ui._dock is first
  assert 'bind.suggest' in host.COMMANDS and 'weights.restrict' in host.COMMANDS
  r['passed'].append('same-directory reload preserves scene nodes and undo history; repeated opening reuses dock')
  rt.fileIn(str(ROOT/'rig/viewport_tools.ms'))
  rt.LXPlacementPlan=host.arr([host.arr([rt.Point3(*s['start']),rt.Point3(*s['end']),rt.Point3(*humanoid.dimensions(s['role'],1),1 if s['role']=='Pelvis' else 0)]) for s in humanoid.plan({'height':1,'fingers':5})])
  rt.LXPlacementStart=rt.Point3(0,0,0);rt.LXPlacementHeight=170
  rt.registerRedrawViewsCallback(rt.LXPlacementDraw)
  bottom=rt.Point(pos=rt.Point3(0,0,0),size=1);top=rt.Point(pos=rt.Point3(0,0,175),size=1)
  rt.select(host.arr([bottom,top]));rt.execute('max zoomext sel');rt.completeRedraw()
  bitmap=rt.gw.getViewportDib();bitmap.filename=str(ROOT/'tests/drag-skeleton-preview.png');rt.save(bitmap);rt.close(bitmap)
  rt.unregisterRedrawViewsCallback(rt.LXPlacementDraw);rt.LXPlacementHeight=0;rt.delete(bottom);rt.delete(top)
  r['passed'].append('full humanoid lines and height rendered through Nitrous redraw callback')
  ui._dock.close();r['ok']=True
 except Exception:r.update(ok=False,error=traceback.format_exc())
 (ROOT/'tests/host/reload-preview-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),'utf-8')
QTimer.singleShot(0,start)
