"""Run only through the harness in a disposable test Max."""
import sys,json,traceback,importlib
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rig import max_host as H,workflow_host as F,humanoid,symmetry as S
from rig import max_ui
S.stop()
from rig import brush
for module in (H,humanoid,F,S,brush):importlib.reload(module)
import rig.workflow_ui as UI
importlib.reload(UI);importlib.reload(max_ui)
report={'passed':[]}

def finish(error=None):
    S.stop();report['ok']=error is None
    if error:report['error']=error
    (ROOT/'tests/host/symmetry-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')

def call(action,**params):return H.dispatch({'action':action,'scene':str(rt.LXRigSceneToken),'params':params})
def close(a,b):return float(rt.distance(a,b))<.002
def mirrored(a,b):
    x=float(nodes['Pelvis'].pos.x);pos=a.pos
    assert close(b.pos,rt.Point3(2*x-pos.x,pos.y,pos.z)),(a.name,b.name,'start')
    pos=F.endpoint(a)
    assert close(F.endpoint(b),rt.Point3(2*x-pos.x,pos.y,pos.z)),(a.name,b.name,'end')
    rows=S.reflect_rows(S.state(a)[:4],x)
    for row,target in zip((b.transform.row1,b.transform.row2,b.transform.row3),rows[:3]):assert close(row,rt.Point3(*target))
    assert abs(float(a.length)-float(b.length))<.002

def start():
    global dock,nodes,options,source,target,before
    try:
        rt.resetMaxFile(rt.Name('noPrompt'));rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
        options=dict(prefix='',height=170,origin=[30,10,0],fingers=5,toes=1,upperArm=2,forearm=3)
        result=call('humanoid.create',**options);nodes={F.prop(H.node(i),'LXRole'):H.node(i) for i in result['nodes']}
        center=H.node(result['center']);assert H.cls(center)=='Point'
        bounds=rt.nodeGetBoundingBox(nodes['Pelvis'],rt.Matrix3(1));size=bounds[1]-bounds[0]
        assert float(size.x)>float(size.z),'pelvis must look wider than tall'
        assert nodes['Pelvis'].parent==center and nodes['Spine_01'].parent==center
        assert nodes['L_Thigh_01'].parent==nodes['Pelvis'] and nodes['R_Thigh_01'].parent==nodes['Pelvis']
        spine_tm=rt.copy(nodes['Spine_01'].transform);leg_tm=rt.copy(nodes['L_Thigh_01'].transform);hip_tm=rt.copy(nodes['Pelvis'].transform)
        rt.rotate(nodes['Pelvis'],rt.Quat(20,rt.Point3(0,0,1)))
        assert close(nodes['Spine_01'].pos,spine_tm.row4) and close(nodes['Spine_01'].transform.row1,spine_tm.row1)
        assert not close(nodes['L_Thigh_01'].pos,leg_tm.row4)
        nodes['Pelvis'].transform=hip_tm
        report['passed'].append('separate BodyCenter and wide Pelvis; hips rotate legs without spine')
        for spec in humanoid.plan(options):
            n=nodes[spec['role']];assert not str(n.name).startswith('_');assert close(n.pos,rt.Point3(*spec['start']))
            assert close(F.endpoint(n),rt.Point3(*spec['end'])),(spec['role'],str(F.endpoint(n)),spec['end'])
        report['armMesh']={}
        for key in ('L_UpperArm_01','L_Forearm_01'):
            n=nodes[key];mesh=rt.snapshotAsMesh(n);points=[rt.getVert(mesh,i) for i in range(1,int(rt.getNumVerts(mesh))+1)]
            report['armMesh'][key]={'length':float(n.length),'localMin':[min(float(v[j]) for v in points) for j in range(3)],'localMax':[max(float(v[j]) for v in points) for j in range(3)],'start':H.vec(n.pos),'end':H.vec(F.endpoint(n)),'transform':[H.vec(n.objectTransform.row1),H.vec(n.objectTransform.row2),H.vec(n.objectTransform.row3)]}
        for side in ('L','R'):
            assert nodes[side+'_UpperArm_01'].parent==nodes[side+'_Clavicle']
            assert float(nodes[side+'_Forearm_01'].pos.y)>float(nodes[side+'_UpperArm_01'].pos.y)
        report['passed'].append('actual Bone endpoints, shoulders, elbow direction, empty prefix')
        rt.select(H.arr(list(nodes.values())));rt.viewport.setType(rt.Name('view_front'));rt.execute('max zoomext sel all');rt.clearSelection();rt.completeRedraw()
        bitmap=rt.gw.getViewportDib();bitmap.filename=str(ROOT/'tests/humanoid-preview.png');rt.save(bitmap);rt.close(bitmap)
        rt.select(nodes['Pelvis']);source=nodes['L_Forearm_01'];target=nodes['R_Forearm_01']
        source.pos+=rt.Point3(3,4,5);source.length*=1.15;before=rt.copy(target.transform)
        call('symmetry.apply',side='L',wholeRig=True);mirrored(source,target)
        rt.execute('max undo');assert close(target.pos,before.row4),(str(target.pos),str(before.row4))
        rt.execute('max redo');mirrored(source,target)
        report['passed'].append('left to right, rotation/length, undo redo')
        target.pos+=rt.Point3(-2,3,1)
        call('symmetry.apply',side='R',wholeRig=True);mirrored(target,source)
        report['passed'].append('right to left')
        # Select a chain and leave its sibling alone.
        before=rt.copy(nodes['R_Thigh_01'].transform);rt.select(source)
        call('symmetry.apply',side='L',wholeRig=False);assert close(nodes['R_Thigh_01'].pos,before.row4)
        report['passed'].append('selected subtree isolation')
        dock=max_ui.show_workbench();assert dock.isFloating();assert max_ui.show_workbench() is dock
        import qtmax
        qtmax.GetQMaxMainWindow().addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dock);dock.setFloating(False)
        assert not max_ui.show_workbench().isFloating();dock.setFloating(True)
        dock.workbench.steps.setCurrentIndex(2)
        report['passed'].append('first open floats; repeated open preserves user docking')
        rt.select(nodes['Pelvis']);S.start(dict(side='L',wholeRig=True),dock,lambda message:None)
        source.pos+=rt.Point3(0,3,0)
        QTimer.singleShot(600,check_live)
    except Exception:finish(traceback.format_exc())

def check_live():
    try:
        mirrored(source,target);report['passed'].append('automatic symmetry after source edit')
        rt.execute('max undo');QTimer.singleShot(600,check_undo)
    except Exception:finish(traceback.format_exc())

def check_undo():
    try:
        assert not close(target.pos,rt.Point3(60-source.pos.x,source.pos.y,source.pos.z))
        report['passed'].append('automatic symmetry does not fight undo')
        S.stop();rt.select(nodes['Pelvis']);call('rig.finalize',bones=[H.handle(nodes['Pelvis'])])
        try:call('symmetry.apply',side='L',wholeRig=True)
        except ValueError:pass
        else:raise AssertionError('must reject finalized IK rig')
        report['passed'].append('finalized rig protection')
        result=call('controls.create',shape='point',size=4)
        assert nodes['Pelvis'].parent.parent==H.node(result['root'])
        report['passed'].append('world Root carries BodyCenter and both upper/lower body')
        dock.grab().save(str(ROOT/'tests/symmetry-preview.png'));dock.close();assert S._live is None
        finish()
    except Exception:finish(traceback.format_exc())

QTimer.singleShot(0,start)
