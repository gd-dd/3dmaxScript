"""Dedicated fresh test Max only: exercise the actual in-Max dock and UI commands."""
import sys,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer,Qt
from pymxs import runtime as rt
from rig.max_ui import show_workbench
from rig.max_host import handle
report={'passed':[]};dock=None

def finish(error=None):
    report['ok']=error is None
    if error:report['error']=str(error)
    if dock:report['notice']=dock.workbench.notice.text()
    (ROOT/'tests/host/max-ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')

def after_idle(fn):
    if dock.workbench.busy:QTimer.singleShot(100,lambda:after_idle(fn))
    else:fn()

def start():
    global dock
    try:
        import qtmax
        qtmax.GetQMaxMainWindow().showMaximized()
        dock=show_workbench();assert show_workbench() is dock
        qtmax.GetQMaxMainWindow().addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dock)
        dock.setFloating(False)
        assert not dock.isFloating();assert dock.parent() is not None
        report['passed'].append('Max-owned dock and repeated-open singleton')
        rt.resetMaxFile(rt.Name('noPrompt'));dock.check_scene()
        rt.Box(name='LXDockTestMesh',length=10,width=10,height=10)
        dock.workbench.call('scene.inspect',{},loaded)
    except Exception:finish(traceback.format_exc())

def loaded(data):
    try:
        w=dock.workbench;w.load_scene(data)
        assert w.mesh.count()>0;report['passed'].append('actual scene rendered without shelf connection')
        w.name.setText('LXDockBone');w.start.setText('0,0,0');w.end.setText('0,0,20')
        w.create_bone()
        QTimer.singleShot(100,lambda:after_idle(bind_test))
    except Exception:finish(traceback.format_exc())

def bind_test():
    try:
        w=dock.workbench
        bones=[n for n in rt.objects if str(n.name).startswith('LXDockBone')];assert len(bones)==1
        report['passed'].append('bone created from Max UI command')
        w.mutate('bind.create',{'bones':[handle(bones[0])]})
        QTimer.singleShot(100,lambda:after_idle(weight_test))
    except Exception:finish(traceback.format_exc())

def weight_test():
    try:
        w=dock.workbench;assert w.skin.count()==1;w.read_skin()
        QTimer.singleShot(100,lambda:after_idle(edit_test))
    except Exception:finish(traceback.format_exc())

def edit_test():
    try:
        w=dock.workbench;assert w.bone.count()==1
        w.scope.setCurrentIndex(1);w.value.setValue(1);w.weight('set')
        QTimer.singleShot(100,lambda:after_idle(reopen_test))
    except Exception:finish(traceback.format_exc())

def reopen_test():
    global dock
    try:
        assert not dock.workbench.busy;assert '1.000000'==dock.workbench.locks.topLevelItem(0).text(1)
        report['passed'].append('Skin bind and weight edit/readback through Max UI')
        dock.grab().save(str(ROOT/'tests/max-dock-preview.png'))
        import qtmax
        qtmax.GetQMaxMainWindow().grab().save(str(ROOT/'tests/max-inapp-preview.png'))
        old=dock;token=dock.scene_token;old.close();dock=show_workbench();assert dock is not old
        assert dock.scene_token==token,'reopening must preserve scene snapshots'
        report['passed'].append('close and reopen creates a fresh functional dock')
        QTimer.singleShot(500,scene_test)
    except Exception:finish(traceback.format_exc())

def scene_test():
    try:
        token=dock.scene_token;rt.resetMaxFile(rt.Name('noPrompt'));dock.check_scene()
        assert token!=dock.scene_token;assert dock.workbench.scene is None
        assert not dock.workbench.body.isEnabled()
        report['passed'].append('scene reset invalidates all cached editing targets')
        finish()
    except Exception:finish(traceback.format_exc())

QTimer.singleShot(1000,start)
