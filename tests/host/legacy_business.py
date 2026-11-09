"""Disposable batch only. Synthetic assets; no current user scene access."""
from pathlib import Path
import json,os,traceback,struct
import pymxs
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'acceptance/legacy-six-2026-11-10'
OUT.mkdir(exist_ok=True)
report={'pid':os.getpid(),'checks':[],'scope':'synthetic isolated batch; UI message and selection adapters'}
def save():
    report['ok']=len(report['checks'])==6 and all(c['ok'] for c in report['checks'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def check(name,fn):
    try:rt.resetMaxFile(rt.Name('noPrompt'));result=fn();report['checks'].append(dict(name=name,ok=True,evidence=result))
    except Exception:report['checks'].append(dict(name=name,ok=False,error=traceback.format_exc()))
    save();print(name,report['checks'][-1]['ok'],flush=True)
def mx(code):
    with pymxs.undo(False):return rt.execute(code)
def load(name,roll):
    s=(ROOT/name).read_text('utf-8-sig')
    s=s.replace('getFilenamePath (getSourceFileName())','@"'+str(ROOT)+'\\"')
    s=s.replace('messageBox','LXTestMessage').replace('local tv = trackviews.current','local tv = LXTestTracks')
    s=s.replace('createDialog '+roll+' width:420','createDialog '+roll+' pos:[-32000,-32000] width:420')
    mx('global LXMessages=#(); fn LXTestMessage msg title:"" = (append LXMessages msg; true)')
    mx(s);return getattr(rt,roll)
def click(roll,button='btnExecute'):
    rt.clearUndoBuffer()
    getattr(getattr(rt,roll),button).PerformClick()
def near(a,b):assert abs(a-b)<1e-3,(a,b)
def animation():
    mx('global QAObj=box name:"QA07"; with animate on (at time 0 QAObj.pos=[0,0,0]; at time 4 QAObj.pos=[40,20,0]); select QAObj')
def sample(node):
    result=[]
    for f in range(5):
        with pymxs.attime(f):result.append(tuple(rt.biped.getTransform(node,rt.Name('pos')) if str(rt.classOf(node))=='Biped_Object' else node.position))
    return result
def bake():
    animation();expected=sample(rt.QAObj);r=load('动画烘焙工具.ms','AnimBakeRollout');r.spnStart.value=0;r.spnEnd.value=4
    old=mx('numKeys QAObj.position.controller');click('AnimBakeRollout')
    assert sample(rt.QAObj)==expected
    assert mx('numKeys QAObj.position.controller')>=5
    pymxs.run_undo();assert mx('numKeys QAObj.position.controller')==old
    r.chkPos.checked=False;r.chkRot.checked=False;r.chkScale.checked=False;click('AnimBakeRollout');assert '至少' in str(rt.LXMessages[-1])
    return 'samples, keys, undo and no-channel rejection'
def parent():
    animation();mx('global QAParent=box name:"Parent"; with animate on (at time 0 QAParent.pos=[10,0,0]; at time 4 QAParent.pos=[20,0,0]); select #(QAObj,QAParent)')
    expected=sample(rt.QAObj);r=load('保持位移建立父子.ms','ReparentBakeRollout');r.spnStart.value=0;r.spnEnd.value=4
    click('ReparentBakeRollout');assert rt.QAObj.parent==rt.QAParent
    for a,b in zip(sample(rt.QAObj),expected):
        for x,y in zip(a,b):near(x,y)
    pymxs.run_undo();assert rt.QAObj.parent is None,'single undo did not restore parent'
    r.spnStart.value=4;r.spnEnd.value=0;click('ReparentBakeRollout');assert rt.QAObj.parent is None
    assert '起始帧' in str(rt.LXMessages[-1])
    return 'world animation, one-step hierarchy undo, reversed range rejected'
def split():
    mx('global QAMesh=mesh vertices:#([0,0,0],[10,0,0],[0,10,0],[10,10,0]) faces:#([1,2,3],[2,4,3]); setFaceMatID QAMesh 1 1; setFaceMatID QAMesh 2 2; QAMesh.material=multiMaterial numsubs:2; QAMesh.material[1]=standardMaterial name:"Red"; QAMesh.material[2]=standardMaterial name:"Blue"; select QAMesh')
    load('按材质ID拆分模型.ms','MatIDSplitRollout');click('MatIDSplitRollout')
    nodes=list(rt.selection);assert len(nodes)==2
    assert all(n.numfaces==1 for n in nodes);assert {str(n.material.name) for n in nodes}=={'Red','Blue'}
    assert len(list(rt.objects))==3
    assert '完成' in str(rt.LXMessages[-1])
    pymxs.run_undo();assert len(list(rt.objects))==1
    mx('clearSelection()');load('按材质ID拆分模型.ms','MatIDSplitRollout');click('MatIDSplitRollout');assert len(list(rt.objects))==1
    assert '先选择' in str(rt.LXMessages[-1])
    return 'two material outputs, source preserved, undo, empty source rejected'
def root():
    mx('global QABip=biped.createNew 100 -90 [0,0,0]; global QARoot=QABip; QARoot.name="Bip001"; global QADummy=dummy pos:[9,8,7]; with animate on (at time 0 biped.setTransform QARoot #pos [0,0,100] true; at time 4 biped.setTransform QARoot #pos [40,20,100] true); select QADummy')
    expected=sample(rt.QARoot);r=load('清理根骨骼.ms','RootBoneBakeRollout');r.spnStart.value=0;r.spnEnd.value=4;click('RootBoneBakeRollout')
    for a,b in zip(sample(rt.QADummy),expected):near(a[0],9);near(a[1],b[1]);near(a[2],7)
    pymxs.run_undo();assert tuple(rt.QADummy.position)==(9,8,7)
    r.chkAxisY.checked=False;click('RootBoneBakeRollout');assert '至少' in str(rt.LXMessages[-1])
    return 'Biped Y motion, other axes retained, undo, no-axis rejected'
def formula():
    animation();mx('global QACtrl=QAObj.position.controller.x_position.controller; selectKeys QACtrl; struct LXTracks (fn numSelTracks=1, fn getSelected i=QACtrl); global LXTestTracks=LXTracks()')
    r=load('自定义公式关键帧.ms','CustomFormulaRollout');r.edtFormula.text='v + sin(90)';before=mx('QACtrl.keys[1].value');click('CustomFormulaRollout','btnApply');near(mx('QACtrl.keys[1].value'),before+1)
    pymxs.run_undo();near(mx('QACtrl.keys[1].value'),before)
    r.edtFormula.text='v +';click('CustomFormulaRollout','btnApply');near(mx('QACtrl.keys[1].value'),before)
    assert '出错' in str(rt.LXMessages[-1])
    return 'selected actual float keys, degree sine, undo, invalid formula unchanged'
def pmx_fixture(path):
    b=bytearray(b'PMX '+struct.pack('<f',2.0)+bytes([8,1,0,1,1,1,1,1,1]))
    def pack(fmt,*v):b.extend(struct.pack('<'+fmt,*v))
    def text(s):d=s.encode('utf-8');pack('i',len(d));b.extend(d)
    for s in ['合成PMX','Synthetic','','']:text(s)
    pack('i',3)
    for i,p in enumerate([(0,0,0),(10,0,0),(0,10,0)]):
        pack('3f3f2fB',*p,0,0,1,i/2,0,i)
        if i==0:pack('b',0)
        elif i==1:pack('bbf',0,1,.25)
        else:pack('4b4f',0,1,-1,-1,.4,.6,0,0)
        pack('f',1)
    pack('i3B',3,0,1,2);pack('i',0);pack('i',1)
    text('材质');text('material');pack('4f3ff3fB4ff',1,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1,1)
    pack('bbBB',-1,-1,0,1);pack('B',0);text('');pack('i',3)
    pack('i',2)
    for i in range(2):
        text('骨'+str(i));text('bone'+str(i));pack('3fbiH',0,0,i*10,i-1,0,0);pack('3f',0,0,10)
    for _ in range(4):pack('i',0)
    path.write_bytes(b)
def pmx():
    p=OUT/'synthetic.pmx';pmx_fixture(p);load('PMX导入.ms','PMXImportRollout')
    node=rt.importPMXFile(str(p))
    assert node is not None
    assert node.numverts==3 and node.numfaces==1
    assert len(list(rt.objects))==3
    assert len(list(node.modifiers))==1
    rt.select(node);rt.modPanel.setCurrentObject(node.modifiers[0]);rt.completeRedraw()
    for v,expected in enumerate([[1],[.25,.75],[.4,.6]],1):
        count=rt.skinOps.GetVertexWeightCount(node.modifiers[0],v)
        actual=sorted(rt.skinOps.GetVertexWeight(node.modifiers[0],v,i) for i in range(1,count+1))
        assert len(actual)==len(expected),(actual,expected)
        for a,b in zip(actual,expected):near(a,b)
    assert rt.getNodeByName('骨1').parent==rt.getNodeByName('骨0')
    near(rt.getTVert(node,3).x,1)
    assert str(node.material[0].name)=='材质'
    pymxs.run_undo();assert len(list(rt.objects))==0
    bad=OUT/'truncated.pmx';bad.write_bytes(p.read_bytes()[:40])
    try:rt.importPMXFile(str(bad))
    except RuntimeError:pass
    else:raise AssertionError('truncated file accepted')
    assert len(list(rt.objects))==0
    mx('global originalPMXBuild=pmxBuildScene; fn pmxBuildScene data dir = (box(); throw "injected failure")')
    try:rt.importPMXFile(str(p))
    except RuntimeError:pass
    else:raise AssertionError('injected failure not reported')
    finally:mx('pmxBuildScene=originalPMXBuild')
    assert len(list(rt.objects))==0
    return 'valid PMX triangle/material/UV/bone hierarchy/BDEF1+2+4 weights/undo; truncation and partial-build cleanup'
for name,fn in [('animation',bake),('parent',parent),('split',split),('root',root),('formula',formula),('pmx',pmx)]:check(name,fn)
