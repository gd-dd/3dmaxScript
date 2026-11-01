"""Disposable Max acceptance: geometry, selection, bind queue and color overlay."""
import sys,json,traceback,importlib,time
from pathlib import Path
from pymxs import runtime as rt
from PySide6.QtCore import QTimer,Qt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rig import max_host as H,workflow_host as F,batch_host as B,weight_view as V,selection_ui,workflow_ui,max_ui,brush,symmetry,scene_io
brush.stop();symmetry.stop()
for m in (H,F,B,V,brush,symmetry,scene_io,selection_ui,workflow_ui,max_ui):importlib.reload(m)
report={'passed':[]};dock=None
def call(action,**params):return H.dispatch({'action':action,'scene':str(rt.LXRigSceneToken),'params':params})
def finish(error=None):
 report['ok']=error is None
 if error:report['error']=error
 (ROOT/'tests/host/usability-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
 if dock:dock.close()
def start():
 global dock,w,a,b,bone1,bone2,deadline
 try:
  rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
  human=call('humanoid.create',height=170,upperArm=3,forearm=2,fingers=0,toes=0)
  pelvis=next(n for n in F.members('bones') if F.prop(n,'LXRole')=='Pelvis')
  rt.completeRedraw();assert not pelvis.boneAutoAlign
  assert abs(float(pelvis.transform.row1.x))<1e-5 and abs(float(pelvis.transform.row1.z))<1e-5,H.vec(pelvis.transform.row1)
  call('rig.finalize',bones=human['nodes'])
  for n in F.members('bones'):
   if F.prop(n,'LXRole') in ('L_UpperArm_02','L_UpperArm_03','L_Forearm_02'):
    assert not any(rt.getProperty(n.controller,rt.Name('Rot'+axis+'Active')) for axis in 'XYZ')
  report['passed'].append('pelvis stable after redraw; intermediate limb IK rotations disabled by default')
  rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
  human=call('humanoid.create',height=170,upperArm=2,fingers=0,toes=0)
  call('rig.finalize',bones=human['nodes'],bendSegments=True)
  n=next(n for n in F.members('bones') if F.prop(n,'LXRole')=='L_UpperArm_02')
  assert all(rt.getProperty(n.controller,rt.Name('Rot'+axis+'Active')) for axis in 'XYZ')
  report['passed'].append('segment IK bending can be explicitly enabled')
  rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
  a=rt.Box(name='Translated_A',pos=rt.Point3(100,200,300),width=10,length=10,height=10);rt.convertToPoly(a);F.mark(a,'models')
  b=rt.Box(name='Translated_B',pos=rt.Point3(125,200,300),width=10,length=10,height=10);rt.convertToPoly(b);F.mark(b,'models')
  points,_=H.geometry(a);assert max(abs(p[0]) for p in points)<=5.001,points
  bone1=H.node(call('bone.create',name='Near_A',start=[100,200,295],end=[100,200,315])['node']);F.mark(bone1,'bones')
  bone2=H.node(call('bone.create',name='Near_B',start=[125,200,295],end=[125,200,315])['node']);F.mark(bone2,'bones')
  suggestion=call('bind.suggest',mesh=H.handle(a),limit=4);assert H.handle(bone1) in suggestion['bones'] and H.handle(bone2) not in suggestion['bones'],suggestion
  call('bind.auto',mesh=H.handle(a),bones=[H.handle(bone1),H.handle(bone2)],method='voxel',resolution=16)
  rows=H.read_rows(B.get_skin(a));assert all(r.get('1',0)>.99 for r in rows),rows
  report['passed'].append('translated mesh local geometry, candidate inference, exterior-bone voxel binding')
  result=V.update([H.handle(a)],[H.handle(bone1)],True);assert result[0]['mean']>.99 and len(rt.LXWeightViewData)==1
  rt.completeRedraw();V.clear()
  report['passed'].append('summed weight readback and persistent overlay callback executes')
  call('weights.restrict',meshes=[H.handle(a)],boneNodes=[H.handle(bone2)])
  assert all(r.get('2',0)>.99 for r in H.read_rows(B.get_skin(a)))
  report['passed'].append('restrict removes all unselected weights; zero-share vertices assign nearest retained bone')
  # Native polygon selection supports two seeds and mixed selection above Skin.
  grid=rt.Plane(name='SelectionGrid',length=40,width=40,lengthsegs=4,widthsegs=4);rt.convertToPoly(grid)
  for level,seeds in [('vertex',[7,8]),('face',[6,7])]:
   call('selection.mode',mesh=H.handle(grid),level=level)
   for op in ('loop','ring'):
    if level=='vertex':rt.polyop.setVertSelection(grid,F.bit(seeds))
    else:rt.polyop.setFaceSelection(grid,F.bit(seeds))
    call('selection.expand',mesh=H.handle(grid),level=level,operation=op)
    selected=F.ids(rt.polyop.getVertSelection(grid) if level=='vertex' else rt.polyop.getFaceSelection(grid))
    assert len(selected)>2,(level,op,selected)
  call('selection.mode',mesh=H.handle(a),level='mixed');assert F.poly(a).selectMode==2
  report['passed'].append('two-seed vertex/face loops and rings; mixed selector on selection modifier')
  dock=max_ui.show_workbench();w=dock.workbench;dock.resize(1450,900)
  w.load_scene(call('scene.inspect'))
  for item in selection_ui.items(w.category_trees['models']):item.setSelected(item.data(0,Qt.ItemDataRole.UserRole) in {H.handle(a),H.handle(b)})
  w.bind_method.setCurrentIndex(w.bind_method.findData('voxel'));w.resolution.setValue(16);w.steps.setCurrentIndex(5)
  deadline=time.monotonic()+45
  w.start_bind_queue(False);QTimer.singleShot(1000,queue_first)
 except Exception:finish(traceback.format_exc())
def queue_first():
 try:
  if w.busy:
   assert time.monotonic()<deadline,w.notice.text()
   QTimer.singleShot(200,queue_first);return
  assert len(w._bind_queue)==2 and not w.busy
  assert B.get_skin(b) is None
  w.choose_bone_nodes({H.handle(bone1)});w.confirm_bind_model();QTimer.singleShot(1000,queue_second)
 except Exception:finish(traceback.format_exc())
def queue_second():
 try:
  if w.busy:
   assert time.monotonic()<deadline,w.notice.text()
   QTimer.singleShot(200,queue_second);return
  assert len(w._bind_queue)==1 and not w.busy and B.get_skin(b) is None,(w._bind_queue,w.busy,w.notice.text(),w.bind_progress.text())
  w.choose_bone_nodes({H.handle(bone2)});w.confirm_bind_model();QTimer.singleShot(1000,queue_done)
 except Exception:finish(traceback.format_exc())
def queue_done():
 try:
  if w.busy:
   assert time.monotonic()<deadline,w.notice.text()
   QTimer.singleShot(200,queue_done);return
  assert not w._bind_queue and B.get_skin(b) is not None
  assert set(w.selected_models())=={H.handle(a),H.handle(b)}
  report['passed'].append('two-model queue pauses before each bind and honors edited independent bone selection')
  w.choose_bone_nodes({H.handle(bone1),H.handle(bone2)});w.steps.setCurrentIndex(6);w.refresh_weight_view()
  assert len(rt.LXWeightViewData)==2,(w.weight_summary.text(),w.steps.currentIndex(),w.selected_models(),w.busy)
  before_selection=[H.handle(n) for n in rt.selection];current=rt.modPanel.getCurrentObject();level=rt.subObjectLevel
  w.refresh_weight_view();assert before_selection==[H.handle(n) for n in rt.selection] and rt.modPanel.getCurrentObject()==current and rt.subObjectLevel==level
  report['passed'].append('multi-model inspection restores Max selection, current modifier and subobject level')
  dock.grab().save(str(ROOT/'tests/usability-preview.png'))
  rt.select(H.arr([a,b]));rt.execute('max zoomext sel');rt.completeRedraw()
  bitmap=rt.gw.getViewportDib();bitmap.filename=str(ROOT/'tests/weight-colors-preview.png');rt.save(bitmap);rt.close(bitmap)
  rt.fileIn(str(ROOT/'rig/viewport_tools.ms'));assert rt.LXHumanoidPlacement is not None
  report['passed'].append('three independent columns, multi-model color view and drag preview tool compile')
  finish()
 except Exception:finish(traceback.format_exc())
QTimer.singleShot(0,start)
