"""Per-model suggestions, explicit influence restriction and read-only inspection."""
from . import max_host as H,workflow_host as F,binding
from contextlib import contextmanager
rt=H.rt
_read_cache={}

@contextmanager
def read_context(obj,s):
    """SkinOps requires the modifier panel. Restore the user's exact context."""
    selection=list(rt.selection);mode=rt.getCommandPanelTaskMode();current=rt.modPanel.getCurrentObject();level=rt.subObjectLevel
    with H.pymxs.redraw(False),H.pymxs.undo(False):
        try:
            rt.select(obj);rt.setCommandPanelTaskMode(mode=rt.Name('modify'));rt.modPanel.setCurrentObject(s)
            yield
        finally:
            rt.select(H.arr([n for n in selection if rt.isValidNode(n)]))
            if str(mode).lower()=='modify' and current is not None:rt.modPanel.setCurrentObject(current)
            rt.setCommandPanelTaskMode(mode=mode);rt.subObjectLevel=level

def get_skin(obj):
    return next((s for s in obj.modifiers if H.cls(s)=='Skin'),None)

@H.command('bind.suggest')
def suggest(p):
    obj=H.mesh(p);points,_=H.geometry(obj)
    points=[H.vec(rt.Point3(*v)*obj.objectTransform) for v in points]
    pool=[H.node(x) for x in p.get('pool',[])] or F.members('bones')
    pool=[n for n in pool if n!=obj and not F.prop(n,'LXRole').endswith('_End')]
    if not pool:raise ValueError('请先将骨骼导入骨骼栏')
    segments=[(H.handle(n),H.vec(n.pos),H.vec(F.endpoint(n))) for n in pool]
    votes={};sample=points[::max(1,len(points)//512)];limit=max(1,int(p.get('limit',4)))
    for point in sample:
        ranked=sorted((binding.segment_distance(point,a,b),key) for key,a,b in segments)
        cutoff=max(ranked[0][0]*1.75,1e-5)
        for distance,key in ranked[:limit]:
            if distance<=cutoff:votes[key]=votes.get(key,0)+1
    chosen=sorted(votes,key=lambda k:(-votes[k],k))
    return {'mesh':H.handle(obj),'bones':chosen,'message':'候选 %d 根骨骼；请在骨骼栏调整，确认后才会蒙皮'%len(chosen)}

@H.command('bind.influences')
def select_influences(p):
    found=set()
    for ref in p.get('meshes',[]):
        s=get_skin(H.node(ref))
        if s:
            with read_context(H.node(ref),s):found.update(b['node'] for b in H.influences(s))
    return {'bones':sorted(found),'message':'已选出 %d 根模型影响骨骼'%len(found)}

@H.command('weights.restrict',True)
def restrict(p):
    refs=set(map(str,p.get('boneNodes',[])))
    if not refs:raise ValueError('请在骨骼栏保留至少一根骨骼')
    # Preflight all targets before writing any of them.
    pending=[]
    for ref in p.get('meshes',[]):
        obj=H.node(ref);s=get_skin(obj)
        if s is None:raise ValueError(str(obj.name)+' 尚未蒙皮')
        rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(s)
        data=H.skin_data(obj,s);chosen=[b for b in data['bones'] if b['node'] in refs]
        if not chosen:raise ValueError(str(obj.name)+' 与所选骨骼没有影响关系')
        allowed={b['id'] for b in chosen};locked=set(H.profile(obj,s).get('locked',[]))
        if any(r.get(k,0)>1e-8 for r in data['weights'] for k in locked-allowed):raise ValueError('未选骨骼含锁定权重，请先解除锁定')
        out=[]
        for point,row in zip(data['positions'],data['weights']):
            values={k:v for k,v in row.items() if k in allowed and v>0};total=sum(values.values())
            if total<=1e-8:
                world=H.vec(rt.Point3(*point)*obj.objectTransform)
                nearest=min(chosen,key=lambda b:binding.segment_distance(world,H.vec(H.node(b['node']).pos),H.vec(F.endpoint(H.node(b['node'])))))
                values={nearest['id']:1};total=1
            out.append({k:v/total for k,v in values.items()})
        pending.append((obj,s,data,out))
    if not pending:raise ValueError('请在模型栏选择模型')
    for obj,s,data,out in pending:
        rt.select(obj);rt.modPanel.setCurrentObject(s);H.backup(data,'仅保留选中骨骼前');H.write_rows(s,out)
    return {'message':'已对 %d 个模型移除未选骨骼权重并归一化；原来无选中影响的顶点分配给最近选中骨骼'%len(pending)}

def inspect_weights(meshes,bones):
    """Restore Max selection/stack after reads; never switch away during a stroke."""
    results=[];chosen=set(bones)
    scene=str(rt.LXRigSceneToken)
    for key in list(_read_cache):
        if key[0]!=scene:_read_cache.pop(key,None)
    for ref in meshes:
        obj=H.node(ref);s=get_skin(obj)
        if s is None:
            results.append({'mesh':ref,'name':str(obj.name),'bound':False});continue
        from . import brush
        key=(str(rt.LXRigSceneToken),ref,H.handle(s))
        if brush._active is not None:
            if brush._active.obj==obj:
                influences=H.influences(s);rows=H.read_rows(s)
                selected=[i for i in range(len(rows)) if rt.skinOps.IsVertexSelected(s,i+1)]
                _read_cache[key]=(influences,rows,selected)
            elif key in _read_cache:influences,rows,selected=_read_cache[key]
            else:continue
        else:
            with read_context(obj,s):
                influences=H.influences(s);rows=H.read_rows(s)
                selected=[i for i in range(len(rows)) if rt.skinOps.IsVertexSelected(s,i+1)]
            _read_cache[key]=(influences,rows,selected)
        ids={b['id'] for b in influences if b['node'] in chosen}
        values=[sum(r.get(k,0) for k in ids) for r in rows]
        if not selected:selected=list(range(len(rows)))
        per_bone={b['node']:sum(rows[i].get(b['id'],0) for i in selected)/max(1,len(selected)) for b in influences}
        results.append({'mesh':ref,'name':str(obj.name),'bound':True,'count':len(rows),'values':values,
                        'mean':sum(values[i] for i in selected)/max(1,len(selected)),
                        'bones':per_bone,'vertices':[(i+1,values[i]) for i in selected[:200]],'sampleCount':len(selected)})
    return results

@H.command('pelvis.straighten',True)
def straighten(p):
    bones=[H.node(x) for x in p.get('bones',[])] or F.members('bones')
    targets=[n for n in bones if F.prop(n,'LXRole')=='Pelvis']
    if not targets:raise ValueError('没有选中的 Pelvis 骨盆')
    for b in targets:
        if F.prop(b,'LXFinalized'):raise ValueError('请在 IK 定型前摆正骨盆')
        b.boneAutoAlign=False
        F.set_segment(b,b.pos,b.pos+rt.Point3(0,-float(b.length),0))
    return {'message':'骨盆已摆正；子骨骼世界位置保持不变'}
