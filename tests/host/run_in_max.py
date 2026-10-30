"""Run only in a fresh test Max. Never loaded by the shipping bridge."""
import sys,json,traceback,uuid
import importlib
import pymxs
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pymxs import runtime as rt
import rig.max_host
importlib.reload(rig.max_host)
from rig.max_host import dispatch,handle
from PySide6.QtCore import QTimer
def run():
    report={'passed':[]}
    def call(action,**params):
        result=dispatch({'action':action,'scene':str(rt.LXRigSceneToken),'params':params})
        report['passed'].append(action);return result
    try:
        rt.resetMaxFile(rt.Name('noPrompt'))
        rt.LXRigSceneToken=str(uuid.uuid4())
        with pymxs.undo(True,'Box probe'):boxprobe=rt.Box()
        pymxs.run_undo()
        report['boxUndo']=not rt.isValidNode(boxprobe)
        temp=call('bone.create',name='LXUndoProbe',start=[0,0,0],end=[0,0,1])['node']
        report['holdAfterCreate']=str(rt.theHold.Holding())
        pymxs.run_undo()
        report['objectsAfterUndo']=[str(n.name) for n in rt.objects]
        assert not rt.isValidNode(rt.getAnimByHandle(int(temp))), 'undo did not remove created bone'
        report['passed'].append('undo create')
        @rig.max_host.command('test.rollback',True)
        def fail_after_create(p):
            rt.Box();raise ValueError('expected rollback')
        count=len(list(rt.objects))
        try:call('test.rollback')
        except ValueError:pass
        else:raise AssertionError('exception suppressed')
        assert len(list(rt.objects))==count,'failed transaction left scene changes'
        del rig.max_host.COMMANDS['test.rollback'];report['passed'].append('rollback after mutation')
        a=call('bone.create',name='LXTest_L',start=[-5,0,0],end=[-5,0,10])['node']
        b=call('bone.create',name='LXTest_R',start=[5,0,0],end=[5,0,10])['node']
        obj=rt.Plane(length=10,width=10,lengthsegs=2,widthsegs=2);obj.name='LXTestMesh';rt.convertToMesh(obj);mid=handle(obj)
        call('scene.inspect');call('bind.create',mesh=mid,bones=[a,b])
        data=call('skin.inspect',mesh=mid);ids=[x['id'] for x in data['bones']]
        call('weights.edit',mesh=mid,scope='all',mode='set',bone=ids[0],value=1)
        call('weights.edit',mesh=mid,scope='all',mode='set',bone=ids[1],value=.25)
        call('weights.edit',mesh=mid,scope='all',mode='normalize')
        call('weights.edit',mesh=mid,scope='all',mode='smooth',iterations=2)
        call('weights.edit',mesh=mid,scope='all',mode='prune',limit=2)
        call('profile.save',mesh=mid,profile={'schema':1,'humanoid':{'hips':a},'face':{'jaw':b},'locked':[],'pairs':{ids[0]:ids[1],ids[1]:ids[0]}})
        call('weights.mirror',mesh=mid,scope='all',axis=0,tolerance=.01)
        call('pose.capture',mesh=mid,bones=[a,b]);call('pose.restore',mesh=mid)
        snap=call('snapshot.create',mesh=mid)['snapshot'];call('snapshot.restore',mesh=mid,snapshot=snap)
        path=str(ROOT/'tests/host/weights.json');call('weights.export',mesh=mid,path=path,overwrite=True);call('weights.import',mesh=mid,path=path)
        check=call('skin.check',mesh=mid);assert check['issueCount']==0,check
        call('vertices.select',mesh=mid,vertices=[1,2]);assert call('skin.inspect',mesh=mid)['selectedCount']==2
        dst=rt.Plane(length=10,width=10,lengthsegs=2,widthsegs=2);rt.convertToMesh(dst);did=handle(dst)
        call('bind.create',mesh=did,bones=[a,b]);call('weights.transfer',mesh=did,source=mid,distance=.01)
        bone=rig.max_host.node(a);oldpos=rt.copy(bone.pos);bone.pos=oldpos+rt.Point3(0,0,3);rt.completeRedraw()
        before_restore=rig.max_host.geometry(dst)[0]
        removed=call('bind.unbind',mesh=did);call('snapshot.list',mesh=did)
        call('snapshot.restore',mesh=did,snapshot=removed['snapshot'])
        after_restore=rig.max_host.geometry(dst)[0]
        assert max(abs(a-b) for p,q in zip(before_restore,after_restore) for a,b in zip(p,q))<1e-4,'binding transforms were not restored'
        report['passed'].append('deformed mesh snapshot restore positions')
        call('bind.unbind',mesh=did);bone.pos=oldpos;rt.completeRedraw()
        target=rt.copy(dst);target.name='LXTestExpression';rt.setVert(target,1,rt.Point3(-5,-5,1));rt.update(target)
        call('morph.add',mesh=did,target=handle(target),channel=1,name='Smile')
        call('morph.inspect',mesh=did);call('morph.value',mesh=did,channel=1,value=25);call('morph.reset',mesh=did)
        call('morph.add',mesh=mid,target=handle(target),channel=1,name='SkinSmile')
        assert [str(rt.classOf(m)) for m in obj.modifiers]==['Skin','Morpher'],'Morpher should be before Skin evaluation'
        report['passed'].append('Morpher inserted below Skin')
        call('bone.rename',node=a,name='LXTest_Left');call('bone.parent',node=b,parent=a)
        c=call('bone.create',name='LXTest_Extra',start=[0,0,0],end=[0,0,10])['node']
        call('bind.add',mesh=mid,bones=[c]);call('weights.edit',mesh=mid,scope='all',mode='set',bone=ids[0],value=1)
        call('bind.remove',mesh=mid,bone=ids[1])
        remaining=call('skin.inspect',mesh=mid)
        assert {x['node'] for x in remaining['bones']}=={a,c},remaining
        report['passed'].append('influence removal preserves remaining node identities')
        try:dispatch({'action':'bone.rename','scene':'stale','params':{'node':a,'name':'bad'}})
        except ValueError:report['passed'].append('stale scene rejected')
        else:raise AssertionError('stale scene accepted')
        report['ok']=True
    except BaseException:
        report['ok']=False;report['error']=traceback.format_exc()
        try:
            s=obj.modifiers[0];rt.LXTestSkin=s
            report['array']=str(rt.Array(.75,.25))
            rt.execute('skinOps.ReplaceVertexWeights LXTestSkin 1 #(1,2) #(0.75,0.25)')
            report['nativeWeights']=[float(rt.skinOps.GetVertexWeight(s,1,j)) for j in (1,2)]
            report['nativeRead']=str(rt.execute('for j=1 to 2 collect (skinOps.GetVertexWeight LXTestSkin 1 j)'))
            report['boneInfo']=str(rt.execute('for j=1 to 2 collect #(skinOps.GetBoneName LXTestSkin j 0, skinOps.GetBoneNode LXTestSkin j)'))
            report['limits']={str(k):str(rt.getProperty(s,k)) for k in rt.getPropNames(s) if 'limit' in str(k).lower() or 'rigid' in str(k).lower()}
        except Exception as error:report['probeError']=str(error)
    (ROOT/'tests/host/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')

QTimer.singleShot(0,run)
