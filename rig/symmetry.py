"""Bone symmetry for the free-placement stage; never edits an IK rig."""
import json
from . import max_host as H
from . import workflow_host as F
rt=H.rt
_live=None

def reflect_rows(rows,center):
    # Reflection on both sides of a matrix keeps a right-handed bone frame.
    x,y,z,p=rows
    return [[-x[0],x[1],x[2]],[y[0],-y[1],-y[2]],[-z[0],z[1],z[2]],[2*center-p[0],p[1],p[2]]]

def role(n):return F.prop(n,'LXRole') or str(n.name)
def opposite(name,source):
    target='R' if source=='L' else 'L'
    if name.startswith(source+'_'):return target+name[1:]
    marker='_'+source+'_'
    if marker in name:return name.replace(marker,'_'+target+'_',1)
    return None

def resolve(p):
    side=p.get('side','L')
    if side not in ('L','R'):raise ValueError('请选择左到右或右到左')
    roots=[H.node(i) for i in p.get('bones',[])] or list(rt.selection)
    if not roots:raise ValueError('请在视口选择要对称的骨骼或骨架根部')
    chosen=set()
    def visit(n):
        key=H.handle(n)
        if key in chosen:return
        chosen.add(key)
        for child in n.children:visit(child)
    if p.get('wholeRig',False):
        rigs={F.prop(n,'LXRigId') for n in roots if F.prop(n,'LXRigId')}
        if not rigs:raise ValueError('整侧模式需要选择工具创建的骨架')
        for n in F.members('bones'):
            if F.prop(n,'LXRigId') in rigs:chosen.add(H.handle(n))
    else:
        for n in roots:visit(n)
    nodes=[n for n in rt.objects if H.cls(n)=='BoneGeometry']
    pairs=[]
    for a in nodes:
        if H.handle(a) not in chosen:continue
        other=opposite(role(a),side)
        if other is None:continue
        rig=F.prop(a,'LXRigId')
        matches=[n for n in nodes if role(n)==other and F.prop(n,'LXRigId')==rig]
        if len(matches)!=1:raise ValueError(str(a.name)+' 缺少唯一的对侧骨骼；自定义骨骼请用 L_ / R_ 或 _L_ / _R_ 命名')
        b=matches[0]
        if any(F.prop(n,'LXFinalized') or bool(n.boneFreezeLength) for n in (a,b)):
            raise ValueError('对称仅用于自由骨架阶段；请先撤销 IK / 长度定型')
        pairs.append((a,b))
    if not pairs:raise ValueError('选择中没有对应方向的骨骼，请检查左右命名或改用整侧模式')
    return pairs

def center_for(n,p):
    if not p.get('autoCenter',True):return H.W.finite(p.get('center',0))
    rig=F.prop(n,'LXRigId')
    pelvis=[b for b in F.members('bones') if rig and F.prop(b,'LXRigId')==rig and F.prop(b,'LXRole')=='Pelvis']
    if len(pelvis)!=1:raise ValueError('找不到骨架中线，请关闭自动中线并填写世界 X 坐标')
    return float(pelvis[0].pos.x)

def state(n):
    tm=n.transform
    return [H.vec(tm.row1),H.vec(tm.row2),H.vec(tm.row3),H.vec(tm.row4),float(n.length),float(n.width),float(n.height)]

def apply(p,pairs):
    # Capture all targets before changing parents, then restore unaffected descendants.
    targets={H.handle(b) for _,b in pairs};saved={}
    def descend(n):
        for c in n.children:
            if H.handle(c) not in targets:saved[H.handle(c)]=(c,rt.copy(c.transform))
            descend(c)
    for _,b in pairs:descend(b)
    changes=[]
    for a,b in pairs:
        before=state(a);rows=reflect_rows(before[:4],center_for(a,p))
        changes.append((b,rt.Matrix3(*[rt.Point3(*r) for r in rows]),before[4:]))
    def depth(n):
        d=0
        while n.parent is not None:d+=1;n=n.parent
        return d
    for b,tm,size in sorted(changes,key=lambda item:depth(item[0])):
        b.transform=tm;b.length,b.width,b.height=size;F.free_bone(b)
    for c,tm in sorted(saved.values(),key=lambda item:depth(item[0])):c.transform=tm
    return {'message':'已对称 %d 根骨骼（世界 X 中线）'%len(pairs),'count':len(pairs)}

@H.command('symmetry.apply',True)
def mirror(p):return apply(p,resolve(p))

class Live:
    def __init__(self,p,parent,notice):
        from PySide6.QtCore import QTimer
        self.p=dict(p);self.pairs=resolve(p);self.scene=str(rt.LXRigSceneToken);self.notice=notice
        self.p['bones']=[H.handle(a) for a,_ in self.pairs];self.p['wholeRig']=False
        self.signature=self.capture();self.paused=False
        self.timer=QTimer(parent);self.timer.setInterval(150);self.timer.timeout.connect(self.tick);self.timer.start()
        for event in ('sceneUndo','sceneRedo'):
            rt.callbacks.addScript(rt.Name(event),'python.execute "from rig import symmetry; symmetry.after_history()"',id=rt.Name('LXBoneSymmetry'))
    def capture(self):return json.dumps([(H.handle(a),state(a),center_for(a,self.p)) for a,b in self.pairs])
    def tick(self):
        if self.paused:return
        try:
            if self.scene!=str(rt.LXRigSceneToken):stop();return
            from . import brush
            if rt.theHold.Holding() or brush._active is not None:return
            now=self.capture()
            if now==self.signature:return
            # Use normal validated dispatch and undo. Never write inside Max's active drag transaction.
            result=H.dispatch({'action':'symmetry.apply','scene':self.scene,'params':self.p})
            self.signature=self.capture();self.notice(result['message'])
        except Exception as error:
            stop();self.notice('自动对称已停止：'+str(error))
    def shutdown(self):
        self.timer.stop();self.timer.deleteLater();rt.callbacks.removeScripts(id=rt.Name('LXBoneSymmetry'))

def start(p,parent,notice):
    global _live
    stop();_live=Live(p,parent,notice)

def stop():
    global _live
    current,_live=_live,None
    if current:current.shutdown()

def after_history():
    if _live:
        from PySide6.QtCore import QTimer
        current=_live;current.paused=True
        def resume():
            if _live is current:
                try:current.signature=current.capture();current.paused=False
                except Exception:stop()
        QTimer.singleShot(0,resume)
