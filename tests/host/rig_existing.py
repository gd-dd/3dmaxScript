"""Existing Bone/Biped/Skin read and visibility in a disposable batch scene."""
import sys,os,json,traceback,time
from pathlib import Path
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT.parent/'acceptance/rigskin-existing-2026-11-10'
report={'pid':os.getpid(),'checks':[]}
try:
    from rig import max_host as H,workflow_host as F,batch_host as B
    rt.fileIn(str(ROOT/'bridge/rig_context.ms'))
    com=rt.biped.createNew(170,-90,rt.Point3(0,0,0),arms=True,fingers=5,fingerLinks=3,toes=1,toeLinks=2)
    bips=[n for n in rt.objects if H.is_biped(n)]
    parts=[n for n in bips if H.node_category(n)=='bones']
    assert len(parts)>30 and H.node_category(com)=='controls'
    body=rt.Box(name='ExistingBody',length=12,width=12,height=120);rt.convertToPoly(body)
    helper=rt.Point(name='ExistingHelper');curve=rt.Circle(name='ExistingControl')
    bone=rt.boneSys.createBone(rt.Point3(40,0,0),rt.Point3(40,0,30),rt.Point3(0,1,0))
    F.mark(bone,'bones')  # Mixed scene: this must not hide all the unmarked nodes.
    before=[(H.handle(n),str(n.transform),H.handle(n.parent) if n.parent else None) for n in bips]
    rt.select(body);selection=[H.handle(n) for n in rt.selection]
    data=H.inspect_scene({});nodes={n['id']:n for n in data['nodes']}
    assert nodes[H.handle(body)]['category']=='models'
    assert all(nodes[H.handle(n)]['category']=='bones' and not nodes[H.handle(n)]['geometry'] for n in parts)
    assert nodes[H.handle(helper)]['category']==nodes[H.handle(curve)]['category']=='controls'
    assert selection==[H.handle(n) for n in rt.selection]
    assert before==[(H.handle(n),str(n.transform),H.handle(n.parent) if n.parent else None) for n in bips]
    report['checks'].append({'existingSceneRead':True,'bipedParts':len(parts),'maxVersion':list(rt.maxVersion())[:3]})
    from rig.workflow_ui import WorkflowWorkbench
    class Owner:pass
    w=WorkflowWorkbench(Owner());w.set_target(str(rt.LXRigSceneToken));w.load_scene(data)
    assert not w.workflow_only.isChecked()
    assert set(w.category_nodes('bones'))=={H.handle(n) for n in parts+[bone]}
    assert H.handle(com) in w.category_nodes('controls')
    for category in ('models','bones','controls'):
        refs=w.category_nodes(category)
        F.visibility({'category':category,'nodes':refs,'visible':False})
        assert all(H.node(ref).isHidden for ref in refs),category
        F.visibility({'category':category,'nodes':refs,'visible':True})
        assert all(not H.node(ref).isHidden for ref in refs),category
    report['checks'].append({'unmarkedListsAndVisibility':True})
    chosen=parts[:3]
    H.bind({'mesh':H.handle(body),'bones':[H.handle(n) for n in chosen]})
    skin=B.get_skin(body);rows=H.skin_data(body,skin)
    assert {b['node'] for b in rows['bones']}=={H.handle(n) for n in chosen}
    calls=[];read=H.read_rows
    def counted(s):calls.append(1);return read(s)
    H.read_rows=counted;B._read_cache.clear()
    for n in chosen:B.inspect_weights([H.handle(body)],[H.handle(n)])
    H.read_rows=read
    assert len(calls)==1,calls
    assert rt.distance(H.position(parts[0]),F.endpoint(parts[0]))>0
    rt.select(H.arr(parts));F.import_selected({'category':'auto'})
    assert all(F.prop(n,'LXWorkflow')=='bones' for n in parts)
    assert before==[(H.handle(n),str(n.transform),H.handle(n.parent) if n.parent else None) for n in bips]
    try:H.mesh({'mesh':H.handle(parts[0])});raise AssertionError('Biped accepted as mesh')
    except ValueError:pass
    try:F.finalize({'bones':[H.handle(parts[0])]});raise AssertionError('Biped accepted for Bone IK')
    except ValueError:pass
    suggested=B.suggest({'mesh':H.handle(body),'pool':[H.handle(n) for n in parts]})
    assert suggested['bones']
    F.auto_bind({'mesh':H.handle(body),'bones':[H.handle(n) for n in chosen],'method':'segment','limit':3})
    report['checks'].append({'existingSkinRead':True,'boneSwitchSkinReads':len(calls),'importPreservesBiped':True,'boneOnlyOperationsGuarded':True})
    report['ok']=True
except Exception:report.update(ok=False,error=traceback.format_exc())
finally:
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
