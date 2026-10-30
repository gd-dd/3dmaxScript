"""Shared workflow context, adaptive layout and display controls in disposable Max."""
import sys,json,traceback,importlib
from pathlib import Path
from pymxs import runtime as rt
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QBoxLayout
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rig import max_host as H,workflow_host as F,symmetry as S,brush,scene_io,workflow_ui as UI,max_ui
S.stop()
for module in (H,F,S,brush,scene_io,UI,max_ui):importlib.reload(module)
report={'passed':[]};dock=None
def call(action,**params):return H.dispatch({'action':action,'scene':str(rt.LXRigSceneToken),'params':params})
def finish(error=None):
    report['ok']=error is None
    if error:report['error']=error
    (ROOT/'tests/host/workspace-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    if dock:dock.close()
def start():
    global dock,w,model,rig,skin_handle
    try:
        rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
        rig=call('humanoid.create',height=170,fingers=2,toes=1)
        continuity=call('bone.connections');assert not continuity['broken'],continuity
        report['passed'].append('all intended arm/leg/spine joints connected at creation')
        model=rt.Box(name='BodyMesh',length=20,width=20,height=30);rt.convertToPoly(model)
        other=rt.Box(name='OutsideWorkflow',pos=rt.Point3(100,0,0));rt.select(model);call('workflow.import')
        call('bind.create',mesh=H.handle(model),bones=rig['nodes'])
        call('workflow.boxes',category='models',enabled=True);assert model.boxMode and not other.boxMode
        call('workflow.visibility',category='models',visible=False);assert model.isHidden and not other.isHidden
        call('workflow.visibility',category='models',visible=True);call('workflow.boxes',category='models',enabled=False);assert not model.boxMode
        for category in ('bones','controls'):
            call('workflow.boxes',category=category,enabled=True);assert all(n.boxMode for n in F.members(category))
            call('workflow.boxes',category=category,enabled=False)
        report['passed'].append('category visibility and bounding boxes isolated from unrelated objects')
        for mode in ('wireframe','edges','brackets'):
            for enabled in (True,False):
                result=call('viewport.display',**{mode:enabled});assert result['viewport'][mode]==enabled,(mode,result)
        report['passed'].append('actual Nitrous wireframe, edged faces, selection brackets readback')
        dock=max_ui.show_workbench();w=dock.workbench;dock.resize(1450,800)
        w.load_scene(call('scene.inspect'));w.mesh.setCurrentIndex(w.mesh.findData(H.handle(model)));skin_handle=w.skin.currentData(Qt.ItemDataRole.UserRole+1)
        w.load_skin(call('skin.inspect',**w.params()))
        count=len(w.nodes)
        for i in range(w.steps.count()):
            w.steps.setCurrentIndex(i)
            assert w.mesh.currentData()==H.handle(model) and w.skin.currentData(Qt.ItemDataRole.UserRole+1)==skin_handle
            assert len(w.nodes)==count and w.tree.parentWidget().isAncestorOf(w.tree)
        w.load_scene(call('scene.inspect'));assert w.skin.currentData(Qt.ItemDataRole.UserRole+1)==skin_handle
        labels=[]
        def visit(item):
            labels.append(item.text(1))
            for i in range(item.childCount()):visit(item.child(i))
        for i in range(w.tree.topLevelItemCount()):visit(w.tree.topLevelItem(i))
        assert any('骨盆 / 摆胯' in x for x in labels) and any('身体质心' in x for x in labels)
        assert any('肩 / 锁骨' in x for x in labels)
        report['passed'].append('shared model/Skin and scene reused across all steps; readable anatomical hierarchy')
        w.steps.setCurrentIndex(2);QTimer.singleShot(400,wide)
    except Exception:finish(traceback.format_exc())
def wide():
    try:
        assert w.form_columns[1].box.direction()==QBoxLayout.Direction.LeftToRight
        dock.grab().save(str(ROOT/'tests/workspace-wide-preview.png'))
        dock.resize(820,650);QTimer.singleShot(300,narrow)
    except Exception:finish(traceback.format_exc())
def narrow():
    try:
        assert dock.width()<1000 and dock.height()<720,('minimum size prevents resizing',dock.width(),dock.height())
        assert w.form_columns[1].box.direction()==QBoxLayout.Direction.TopToBottom
        dock.grab().save(str(ROOT/'tests/workspace-narrow-preview.png'))
        w.layout_mode.setCurrentIndex(1);assert w.splitter.orientation()==Qt.Orientation.Vertical
        report['passed'].append('wide columns, narrow reflow, resizable split and vertical alternative')
        # Exercise the actual UI button route and queued Max dispatch.
        w.view_buttons['edges'].click();QTimer.singleShot(400,ui_done)
    except Exception:finish(traceback.format_exc())
def ui_done():
    try:
        assert F.viewport_state()['edges']==w.view_buttons['edges'].isChecked()
        assert F.viewport_state()['edges']
        report['passed'].append('display button executes through actual workbench command queue')
        backup=call('scene.backup');assert Path(backup['path']).is_file() and backup['bytes']>0
        report['passed'].append('full Max recovery copy written and verified')
        finish()
    except Exception:finish(traceback.format_exc())
QTimer.singleShot(0,start)
