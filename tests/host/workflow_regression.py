"""Workflow regression in a disposable Max. Never run in a user production scene."""
import sys,json,traceback,importlib
from pathlib import Path
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
from rig import max_host as H
from rig import workflow_host as F
importlib.reload(H);importlib.reload(F)
from rig import history
importlib.reload(history)
report={'passed':[]}
def call(action,**params):
 (ROOT/'tests/host/progress-report.json').write_text(json.dumps({'action':action,'passed':report['passed']}),'utf-8')
 r=H.dispatch({'action':action,'params':params,'scene':str(rt.LXRigSceneToken)});report['passed'].append(action);return r
try:
 result=call('humanoid.create',height=170,fingers=5,toes=5,upperArm=2,forearm=2)
 bones=[H.node(i) for i in result['nodes']]
 report["boneCount"]=len(bones);report["frozen"]=[str(b.name) for b in bones if b.boneFreezeLength]
 assert len(bones)>70 and all(not b.boneFreezeLength for b in bones)
 report['free']=str(bones[0].boneEnable);report['lengthFlag']=str(bones[0].boneFreezeLength)
 child=call('bone.child',parent=result['nodes'][0],length=8)
 guide_target=rt.Point(pos=rt.Point3(20,0,100))
 call('bone.align',node=child['node'],target=H.handle(guide_target),endpoint='end')
 assert float(rt.distance(F.endpoint(H.node(child['node'])),guide_target.pos))<.001
 call('rig.finalize',bones=result['nodes'])
 call('controls.create',shape='circle',size=5)
 obj=rt.Box(length=20,width=20,height=20);rt.convertToPoly(obj);rt.select(obj)
 call('workflow.import');call('workflow.visibility',category='models',visible=False);assert obj.isHidden
 call('workflow.visibility',category='models',visible=True)
 rt.polyop.setVertSelection(obj,F.bit([1,2]))
 call('guide.center',mesh=H.handle(obj),level='vertex')
 call('selection.mode',mesh=H.handle(obj),level='edge');rt.polyop.setEdgeSelection(obj,F.bit([1]))
 call('selection.expand',mesh=H.handle(obj),level='edge',operation='ring')
 from rig import brush
 importlib.reload(brush)
 rt.resetMaxFile(rt.Name('noPrompt'))
 obj=rt.Box(length=20,width=20,height=20,lengthsegs=3,widthsegs=3,heightsegs=3);rt.convertToPoly(obj)
 a=call('bone.create',name='Test_A',start=[-5,0,5],end=[-5,0,15])['node'];b=call('bone.create',name='Test_B',start=[5,0,5],end=[5,0,15])['node']
 params=dict(mesh=H.handle(obj),skin=0)
 call('bind.auto',**params,bones=[a,b],method='segment',limit=2)
 call('bind.auto',**params,method='voxel',limit=2,resolution=16)
 params['skinHandle']=H.handle(next(m for m in obj.modifiers if H.cls(m)=='Skin'))
 call('selection.mode',**params,level='vertex');rt.execute('fn LXTestSelect m n = (local bits=#{1,2,3}; m.SetEPolySelLevel #Vertex; m.Select #vertex &bits node:n)')(F.poly(obj),obj)
 call('selection.to_skin',**params,level='vertex')
 call('weights.multi',**params,bones=['1'],value=.5,mode='set',scope='selected')
 call('selection.visibility',**params,level='vertex',operation='hide')
 call('selection.visibility',**params,level='vertex',operation='show')
 call('brush.start',**params,bones=['1'],mode='add',radius=100,strength=.2)
 current=brush._active;before=H.read_rows(current.skin)
 current.begin();current.dab([0,0,10]);current.end()
 after=H.read_rows(current.skin);assert before!=after
 report['undoProbe']=[]
 call('brush.stop');assert H.read_rows(current.skin)==after
 for attempt in range(3):
  rt.execute('max undo');rt.skinOps.Invalidate(current.skin,1);rt.completeRedraw()
  restored=H.read_rows(current.skin)
  report['undoProbe'].append({'attempt':attempt,'before':before[0],'after':after[0],'restored':restored[0]})
  if all(abs(before[i].get(k,0)-restored[i].get(k,0))<2e-5 for i in range(len(before)) for k in before[i]):break
 assert attempt==0,report['undoProbe']
 rt.execute('max redo');rt.skinOps.Invalidate(current.skin,1);rt.completeRedraw();assert H.read_rows(current.skin)==after
 call('brush.start',**params,bones=['1'],mode='set',radius=100,strength=.2,value=.4)
 canceled=brush._active;original=H.read_rows(canceled.skin);canceled.begin();canceled.dab([0,0,10]);canceled.cancel();assert H.read_rows(canceled.skin)==original;call('brush.stop')
 report['passed'].append('brush redo and canceled stroke restore')
 rt.fileIn(str(ROOT/'rig/viewport_tools.ms'));report['passed'].append('viewport placement tool compiles')
 report['passed'].append('brush changes weights and one-step undo restores')
 from rig import max_ui,workflow_ui,workbench
 if max_ui._dock is not None:max_ui._dock.close()
 importlib.reload(workbench);importlib.reload(workflow_ui);importlib.reload(max_ui)
 dock=max_ui.show_workbench();dock.workbench.load_scene(H.inspect_scene({}));dock.workbench.steps.setCurrentIndex(1)
 import qtmax
 from PySide6.QtCore import Qt
 qtmax.GetQMaxMainWindow().showMaximized();qtmax.GetQMaxMainWindow().resizeDocks([dock],[620],Qt.Orientation.Horizontal);rt.completeRedraw()
 from PySide6.QtCore import QTimer
 QTimer.singleShot(800,lambda:dock.grab().save(str(ROOT/'tests/workflow-preview.png')))
 report['ok']=True
except Exception:
 report['ok']=False;report['error']=traceback.format_exc()
 try:
  from rig import brush
  brush.stop()
 except Exception:pass
(ROOT/'tests/host/workflow-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')





