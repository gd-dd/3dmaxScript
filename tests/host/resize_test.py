"""Disposable Max regression for resize feedback and idle Skin polling."""
import json,sys,time,traceback,runpy
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
runpy.run_path(str(ROOT/'bridge/open_rig.py'))
from rig import max_ui,max_host as H,workflow_host as F,weight_view as V,selection_ui
r={'passed':[]};dock=max_ui._dock;w=dock.workbench;original=V.update;reads=0
def counted(*args,**kwargs):
 global reads
 reads+=1;return original(*args,**kwargs)
V.update=counted
def finish(error=None):
 V.update=original;r['ok']=error is None
 if error:r['error']=error
 (ROOT/'tests/host/resize-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),'utf-8')
 dock.close()
def start():
 global model,bone,control,started,index
 try:
  rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'));dock.check_scene()
  model=rt.Box(name='ResizeMesh',lengthsegs=12,widthsegs=12,heightsegs=12);rt.convertToPoly(model);F.mark(model,'models')
  bone=rt.boneSys.createBone(rt.Point3(0,0,0),rt.Point3(0,0,30),rt.Point3(0,1,0));F.mark(bone,'bones')
  control=rt.Point(name='ResizeControl');F.mark(control,'controls')
  H.dispatch({'action':'bind.auto','scene':str(rt.LXRigSceneToken),'params':{'mesh':H.handle(model),'bones':[H.handle(bone)],'method':'segment','limit':4,'falloff':2}})
  w.load_scene(H.inspect_scene({}));w.steps.setCurrentIndex(6)
  for tree in w.category_trees.values():tree.topLevelItem(0).setSelected(True)
  started=time.perf_counter();index=0;resize()
 except Exception:finish(traceback.format_exc())
def resize():
 global index
 try:
  dock.resize(1000+(index%4)*150,600+(index%5)*140);index+=1
  if index<30:QTimer.singleShot(25,resize);return
  r['resizeSeconds']=round(time.perf_counter()-started,3)
  assert r['resizeSeconds']<10,r
  QTimer.singleShot(1300,settled)
 except Exception:finish(traceback.format_exc())
def settled():
 global baseline
 try:
  assert not dock._preview_resizing and not rt.LXWeightViewSuspended
  assert w.category_split.count()==2
  assert w.selected_models()==[H.handle(model)] and w.selected_bones()==[H.handle(bone)]
  w.role_tabs.setCurrentIndex(1);assert H.handle(control) in w.selected()
  w.role_tabs.setCurrentIndex(0);assert w.selected_bones()==[H.handle(bone)]
  assert len(rt.LXWeightViewData)==1
  baseline=reads;QTimer.singleShot(2500,idle)
 except Exception:finish(traceback.format_exc())
def idle():
 try:
  assert reads==baseline,(reads,baseline)
  r['idleWeightReads']=reads-baseline;r['vertices']=int(rt.polyop.getNumVerts(model))
  r['passed']=['30 consecutive tall/wide resizes settle without feedback','model, bone and controller selections survive resizing and tab changes','weight overlay restored after resizing; idle performs zero full weight reads']
  dock.grab().save(str(ROOT/'tests/resize-preview.png'));finish()
 except Exception:finish(traceback.format_exc())
QTimer.singleShot(1200,start)
