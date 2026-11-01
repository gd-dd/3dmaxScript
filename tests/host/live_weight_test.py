"""Brush overlay refresh, restored selection and two-pane object browser."""
import sys,json,traceback,importlib
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rig import max_host as H,workflow_host as F,batch_host as B,weight_view as V,brush,selection_ui,workflow_ui,max_ui
for m in (B,V,brush,selection_ui,workflow_ui,max_ui):importlib.reload(m)
r={'passed':[]};dock=None
def finish(error=None):
 r['ok']=error is None
 if error:r['error']=error
 (ROOT/'tests/host/live-weight-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),'utf-8')
 if dock:dock.close()
def start():
 global dock,w,a,b,first,second
 try:
  a=rt.getNodeByName('Translated_A');b=rt.getNodeByName('Translated_B');assert a is not None and b is not None
  s=B.get_skin(a);first=H.influences(s)[0]['node'];second=H.influences(s)[1]['node']
  V.update([H.handle(a),H.handle(b)],[first],True)
  params=dict(mesh=H.handle(a),skinHandle=H.handle(s),bones=['1'],mode='set',value=.25,radius=100,strength=1)
  brush.start(params);active=brush._active;before=H.read_rows(s)
  active.begin();active.dab([100,200,305]);active.end()
  assert H.read_rows(s)!=before
  colors=rt.LXWeightViewData[0][2];assert float(colors[0].g)>float(colors[0].r)
  brush.stop();rt.execute('max undo');rt.completeRedraw()
  assert all(abs(before[i].get(k,0)-H.read_rows(s)[i].get(k,0))<2e-5 for i in range(len(before)) for k in before[i])
  r['passed'].append('brush updates summed overlay during dab; one-step undo restores weights')
  dock=max_ui.show_workbench();w=dock.workbench;dock.resize(1450,900);w.load_scene(H.inspect_scene({}));w.steps.setCurrentIndex(6)
  for item in selection_ui.items(w.category_trees['models']):item.setSelected(item.data(0,Qt.ItemDataRole.UserRole) in {H.handle(a),H.handle(b)})
  w.choose_bone_nodes({first});QTimer.singleShot(1500,layout_done)
 except Exception:finish(traceback.format_exc())
def layout_done():
 try:
  assert w.category_split.count()==2 and w.category_split.height()<=w.shared_scene.height()
  w.refresh_weight_view();assert len(rt.LXWeightViewData)==2
  dock.grab().save(str(ROOT/'tests/usability-preview.png'))
  rt.select(H.arr([a,b]));rt.execute('max zoomext sel');rt.completeRedraw()
  bmp=rt.gw.getViewportDib();bmp.filename=str(ROOT/'tests/weight-colors-preview.png');rt.save(bmp);rt.close(bmp)
  r['passed'].append('two object panes fit viewport; two models show different selected-bone weights')
  # Automatic mode processes both models without any confirmation callbacks.
  w.steps.setCurrentIndex(5);w.choose_bone_nodes({first,second});w.start_bind_queue(True);QTimer.singleShot(1000,auto_done)
 except Exception:finish(traceback.format_exc())
attempts=0
def auto_done():
 global attempts
 try:
  if w.busy:
   attempts+=1;assert attempts<120,w.notice.text();QTimer.singleShot(250,auto_done);return
  assert not w._bind_queue and w._bind_done==2,(w.notice.text(),w._bind_queue)
  r['passed'].append('automatic batch processes two selected models')
  finish()
 except Exception:finish(traceback.format_exc())
QTimer.singleShot(0,start)
