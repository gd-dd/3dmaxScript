"""Stage commands. Nodes carry membership/role metadata in the Max scene."""
import json,math,uuid
from . import max_host as H
from . import humanoid,binding,weight_edit
rt=H.rt

def prop(n,key):return str(rt.getUserProp(n,key) or '')
def mark(n,category,role=''):
    rt.setUserProp(n,'LXWorkflow',category)
    if role:rt.setUserProp(n,'LXRole',role)
    return n

def members(category=None):return [n for n in rt.objects if prop(n,'LXWorkflow') and (category is None or prop(n,'LXWorkflow')==category)]
def bit(ids):return rt.execute('#{'+','.join(str(int(i)) for i in ids)+'}')
def ids(bits):return [int(i) for i in rt.execute('fn LXBitIds b = b as array')(bits)]
def free_bone(b):
    b.setBoneEnable(True,rt.currentTime);b.boneAutoAlign=True;b.boneFreezeLength=False;b.boneScaleType=rt.Name("scale")

def endpoint(b):return b.objectTransform.row4+b.objectTransform.row1*float(b.length) if H.cls(b)=='BoneGeometry' else b.pos

def set_segment(b,a,z):
    delta=z-a;length=float(rt.length(delta))
    if length<1e-5:raise ValueError('起终点不能重合')
    children=[(c,rt.copy(c.transform)) for c in b.children]
    x=rt.normalize(delta);up=rt.Point3(0,0,1) if abs(float(x.z))<.95 else rt.Point3(0,1,0)
    y=rt.normalize(rt.cross(up,x));zz=rt.normalize(rt.cross(x,y))
    b.transform=rt.Matrix3(x,y,zz,a);b.length=length
    for c,tm in children:c.transform=tm

@H.command('workflow.import',True)
def import_selected(p):
    selected=list(rt.selection)
    if not selected:raise ValueError('请先在 Max 选择模型、骨骼或控制器')
    for n in selected:
        kind=p.get('category','auto')
        if kind=='auto':kind='bones' if H.cls(n)=='BoneGeometry' or bool(getattr(n,'isBone',False)) else 'models' if rt.superClassOf(n)==rt.GeometryClass else 'controls'
        mark(n,kind)
    return {'message':'已纳入工作流 %d 个对象（不复制、不改变层级）'%len(selected)}

@H.command('workflow.visibility',True)
def visibility(p):
    nodes=members(p['category'])
    for n in nodes:n.isHidden=not bool(p['visible'])
    return {'message':'已%s %d 个对象'%('显示' if p['visible'] else '隐藏',len(nodes))}

@H.command('workflow.boxes',True)
def boxes(p):
    nodes=members(p['category']);on=bool(p['enabled'])
    for n in nodes:
        if on:
            if not prop(n,'LXPreviousDisplayByLayer'):rt.setUserProp(n,'LXPreviousDisplayByLayer','true' if n.displayByLayer else 'false')
            n.displayByLayer=False;n.boxMode=True
        else:
            n.boxMode=False
            previous=prop(n,'LXPreviousDisplayByLayer')
            if previous:n.displayByLayer=previous=='true';rt.setUserProp(n,'LXPreviousDisplayByLayer','')
    return {'message':'%d 个对象%s包围框显示'%(len(nodes),'开启' if on else '关闭')}

def viewport_state():
    if not rt.NitrousGraphicsManager.IsEnabled():return {}
    settings=rt.NitrousGraphicsManager.GetActiveViewportSetting()
    return {'wireframe':str(settings.VisualStyleMode).lower()=='wireframe','edges':bool(settings.ShowEdgedFacesEnabled),'brackets':bool(settings.ShowSelectionBracketsEnabled)}

@H.command('viewport.display')
def viewport_display(p):
    if not rt.NitrousGraphicsManager.IsEnabled():raise ValueError('此显示控制需要 Nitrous 视口')
    settings=rt.NitrousGraphicsManager.GetActiveViewportSetting()
    if 'wireframe' in p:settings.VisualStyleMode=rt.Name('Wireframe' if p['wireframe'] else 'Realistic')
    if 'edges' in p:settings.ShowEdgedFacesEnabled=bool(p['edges'])
    if 'brackets' in p:settings.ShowSelectionBracketsEnabled=bool(p['brackets'])
    rt.completeRedraw()
    return {'message':'已更新当前视口显示；不改变模型、材质或渲染设置','viewport':viewport_state()}

@H.command('humanoid.create',True)
def create_humanoid(p):
    specs=humanoid.plan(p);created={};rig_id=uuid.uuid4().hex
    pelvis=specs[0];prefix=str(p.get('prefix','LX')).strip().rstrip('_')
    center=mark(rt.Point(name=rt.uniqueName((prefix+'_' if prefix else '')+'BodyCenter'),pos=rt.Point3(*pelvis['start']),size=float(p.get('height',170))*.035,box=True,cross=True),'controls','BodyCenter')
    rt.setUserProp(center,'LXRigId',rig_id);center.wireColor=rt.Color(134,184,61)
    for spec in specs:
        result=H.create_bone(dict(spec,parent=None));b=H.node(result['node']);b.width,b.height=humanoid.dimensions(spec['role'],float(p.get('height',170)));b.taper=0 if spec['role']=='Pelvis' else .15
        free_bone(b);mark(b,'bones',spec['role']);rt.setUserProp(b,'LXRigId',rig_id)
        if spec['chain']:rt.setUserProp(b,'LXChain',spec['chain'])
        b.parent=created[spec['parent']] if spec['parent'] else center
        free_bone(b);created[spec['role']]=b
    # Set final segments after parenting: Max can update Bone stretch while links are attached.
    for spec in specs:
        b=created[spec['role']];free_bone(b)
        set_segment(b,rt.Point3(*spec['start']),rt.Point3(*spec['end']))
    for spec in specs:
        parent=next((s for s in specs if s['role']==spec['parent']),None)
        if parent and binding.distance(parent['end'],spec['start'])<float(p.get('height',170))*1e-8:
            if float(rt.distance(endpoint(created[parent['role']]),created[spec['role']].pos))>float(p.get('height',170))*1e-5:
                raise RuntimeError('骨骼关节未连接：'+spec['role'])
    rt.select(H.arr(list(created.values())))
    return {'message':'已创建 %d 根自由 Bone；无 IK，可移动旋转，长度未锁定'%len(created),'nodes':[H.handle(b) for b in created.values()],'center':H.handle(center)}

@H.command('bone.child',True)
def child(p):
    chosen=list(rt.selection)
    parent=H.node(p['parent']) if p.get('parent') else chosen[0] if len(chosen)==1 else None
    if parent is None:raise ValueError('请在视口选择一个父骨骼')
    if H.cls(parent)!='BoneGeometry':raise ValueError('自由子骨骼要求 Bone 父骨骼')
    start=endpoint(parent);end=start+rt.Point3(float(p.get('length',10)),0,0)
    result=H.create_bone({'start':H.vec(start),'end':H.vec(end),'name':p.get('name','LX_Custom'),'parent':H.handle(parent)})
    b=H.node(result['node']);free_bone(b);mark(b,'bones');rt.setUserProp(b,'LXRigId',prop(parent,'LXRigId'));rt.select(b)
    return result

@H.command('bone.align',True)
def align_endpoint(p):
    b=H.node(p['node']);target=H.node(p['target'])
    if H.cls(b)!='BoneGeometry':raise ValueError('请选择 Bone 骨骼')
    if prop(b,'LXFinalized'):raise ValueError('骨骼已定型，请在添加 IK 前调整端点')
    set_segment(b,target.pos if p['endpoint']=='start' else b.pos,target.pos if p['endpoint']=='end' else endpoint(b))
    return {'message':'骨骼端点已对齐；子对象世界位置保持'}

def poly(obj):
    """Select above Skin; never expose the base topology under a live binding."""
    existing=[m for m in obj.modifiers if H.cls(m)=='Edit_Poly' and str(m.name)=='LX_Selection']
    if existing:return existing[0]
    if not any(H.cls(m)=='Skin' for m in obj.modifiers) and H.cls(obj.baseObject)=='Editable_Poly':return obj.baseObject
    mod=rt.Edit_Poly();mod.name='LX_Selection';rt.addModifier(obj,mod);rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(mod);rt.completeRedraw()
    return mod

def is_modifier(value):return H.cls(value)=='Edit_Poly'
def selected_poly_vertices(obj,level):
    base=poly(obj)
    if is_modifier(base):
        if level!='vertex':base.ConvertSelection(rt.Name(level),rt.Name('vertex'),requireAll=False)
        return ids(base.GetSelection(rt.Name('vertex'),node=obj))
    if level=='edge':return ids(rt.polyop.getVertsUsingEdge(base,rt.polyop.getEdgeSelection(base)))
    if level=='face':return ids(rt.polyop.getVertsUsingFace(base,rt.polyop.getFaceSelection(base)))
    return ids(rt.polyop.getVertSelection(base))

@H.command('guide.center',True)
def guide(p):
    obj=H.mesh(p);selected=selected_poly_vertices(obj,p.get('level','vertex'))
    if not selected:raise ValueError('请先选择顶点、边或面')
    base=poly(obj);points=[base.GetVertex(i,node=obj)*obj.objectTransform if is_modifier(base) else rt.polyop.getVert(obj,i) for i in selected];center=sum(points,rt.Point3(0,0,0))/len(points)
    helper=rt.Point(name=rt.uniqueName('LX_Guide'),pos=center,size=float(p.get('size',2)),cross=True,box=False)
    mark(helper,'controls','Guide');return {'message':'已在 %d 个顶点平均中心创建 Point 辅助体'%len(selected),'node':H.handle(helper)}

@H.command('rig.finalize',True)
def finalize(p):
    chosen=[H.node(i) for i in p.get('bones',[])] or members('bones')
    if not chosen:raise ValueError('请先导入或创建骨架')
    rigs={prop(n,'LXRigId') for n in chosen if prop(n,'LXRigId')}
    bones=[n for n in members('bones') if prop(n,'LXRigId') in rigs] if rigs else chosen
    if any(prop(n,'LXFinalized') for n in bones):raise ValueError('骨架已定型；如需返回调整，请使用 Max 撤销')
    chains={}
    for b in bones:
        if H.cls(b)!='BoneGeometry':continue
        key=(prop(b,'LXRigId'),prop(b,'LXChain'))
        if key[1]:chains.setdefault(key,[]).append(b)
    goals=[]
    for (rig_id,name),links in chains.items():
        starts=[n for n in links if n.parent not in links]
        if len(starts)!=1:raise ValueError('肢体链层级不完整：'+name)
        start=starts[0];end=start
        while True:
            children=[c for c in end.children if c in links]
            if not children:break
            if len(children)!=1:raise ValueError('肢体链存在分叉：'+name)
            end=children[0]
        terminal=[c for c in end.children if c in bones and prop(c,'LXChain')!=name]
        if len(terminal)!=1:raise ValueError('手或脚末端不完整：'+name)
        goal=rt.IKSys.ikChain(start,terminal[0],'IKHISolver')
        if goal is None:raise ValueError('Max 未能创建 IK：'+name)
        goal.name=rt.uniqueName('LX_'+name+'_IK');mark(goal,'controls','IK');rt.setUserProp(goal,'LXRigId',rig_id);goals.append(goal)
    for b in bones:
        if H.cls(b)=='BoneGeometry':b.setBoneEnable(True,rt.currentTime);b.boneFreezeLength=True;b.boneAutoAlign=True;rt.setUserProp(b,'LXFinalized','true')
    return {'message':'已固定 %d 根骨骼长度，建立 %d 条肢体 HI IK；脊柱/手指保留 FK'%(len(bones),len(goals)),'goals':[H.handle(n) for n in goals]}

@H.command('controls.create',True)
def controls(p):
    roots=[n for n in members('controls') if prop(n,'LXRole')=='Root']
    root=roots[0] if roots else mark(rt.Point(name=rt.uniqueName('LX_Root'),pos=rt.Point3(0,0,0),size=float(p.get('size',10)),box=True,cross=True),'controls','Root')
    targets=[H.node(i) for i in p.get('nodes',[])] or [n for n in members('controls') if prop(n,'LXRole')=='IK']
    count=0
    for target in targets:
        if target==root or prop(target,'LXControl'):continue
        kind=p.get('shape','circle');size=float(p.get('size',10))
        if kind=='circle':ctrl=rt.Circle(radius=size)
        elif kind=='rectangle':ctrl=rt.Rectangle(length=size*2,width=size*2)
        elif kind=='point':ctrl=rt.Point(size=size,cross=True,box=True)
        else:raise ValueError('未知控制器形状')
        ctrl.name=rt.uniqueName(str(target.name)+'_CTRL');ctrl.transform=rt.copy(target.transform);ctrl.parent=root
        mark(ctrl,'controls','Controller');rt.setUserProp(target,'LXControl',H.handle(ctrl))
        if prop(target,'LXRole')=='IK':target.parent=ctrl
        else:
            # Insert a control parent preserving world transforms; no controller overwrite.
            old=target.parent;ctrl.parent=old if old else root;tm=rt.copy(target.transform);target.parent=ctrl;target.transform=tm
        count+=1
    # Root motion should carry skeleton roots as well as IK goals.
    for b in members('bones')+[n for n in members('controls') if prop(n,'LXRole')=='BodyCenter']:
        if b.parent is None:
            tm=rt.copy(b.transform);b.parent=root;b.transform=tm
    return {'message':'世界中心 Root 就绪，创建 %d 个控制器'%count,'root':H.handle(root)}

@H.command('bind.auto',True)
def auto_bind(p):
    obj=H.mesh(p)
    if not any(H.cls(m)=='Skin' for m in obj.modifiers):
        bones=p.get('bones') or [H.handle(n) for n in members('bones')]
        H.bind(dict(p,bones=bones));p=dict(p,skin=0,skinHandle=None)
    s=H.skin(obj,p)
    if p.get('method')=='envelope':return {'message':'Skin 包络绑定完成'}
    data=H.skin_data(obj,s);points=[H.vec(rt.Point3(*v)*obj.objectTransform) for v in data['positions']]
    segments=[]
    for b in data['bones']:
        bone=H.node(b['node']);segments.append((b['id'],H.vec(bone.pos),H.vec(endpoint(bone))))
    rows,stats=binding.solve(points,data['faces'],segments,p.get('method','segment'),int(p.get('limit',4)),float(p.get('falloff',2)),int(p.get('resolution',32)))
    H.backup(data,'自动蒙皮前');s.bone_Limit=int(p.get('limit',4));H.write_rows(s,rows)
    return {'message':'自动蒙皮完成：%d 顶点 / %s'%(len(rows),'体素内部距离场' if p.get('method')=='voxel' else '骨骼线段距离'),'stats':stats}

@H.command('weights.multi',True)
def multi(p):
    obj=H.mesh(p);s=H.skin(obj,p);data=H.skin_data(obj,s);rows=data['weights'];selected=H.selected_vertices(s,p,len(rows))
    locked=H.profile(obj,s).get('locked',[]);bones=list(map(str,p.get('bones',[])))
    if not set(bones)<={b['id'] for b in data['bones']}:raise ValueError('影响骨骼已变化，请重新读取 Skin')
    out=[dict(r) for r in rows]
    for i in selected:out[i]=weight_edit.edit_many(rows[i],bones,p['value'],p['mode'],locked,[b['id'] for b in data['bones']])
    H.backup(data,'多骨骼编辑前');H.write_rows(s,out,selected)
    return {'message':'已更新 %d 个顶点；所选骨骼合计权重按原比例分配'%len(selected)}

@H.command('selection.mode',True)
def selection_mode(p):
    obj=H.mesh(p);base=poly(obj);rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(base);rt.showEndResult=True
    rt.subObjectLevel={'vertex':1,'edge':2,'face':4}[p['level']]
    if is_modifier(base):base.SetEPolySelLevel(rt.Name(p['level']))
    return {'message':'在视口选择'+{'vertex':'顶点','edge':'边','face':'面'}[p['level']]}

@H.command('selection.expand',True)
def expand_selection(p):
    obj=H.mesh(p);base=poly(obj);rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(base)
    op=p['operation'];level=p.get('level','edge');rt.subObjectLevel={'vertex':1,'edge':2,'face':4}[level]
    if op in ('loop','ring'):
        if level!='edge':raise ValueError('循环/环选请先切到边模式')
        base.ButtonOp(rt.Name('SelectEdgeLoop' if op=='loop' else 'SelectEdgeRing'))
    elif op in ('grow','shrink'):base.ButtonOp(rt.Name('GrowSelection' if op=='grow' else 'ShrinkSelection'))
    else:raise ValueError('未知扩展选择')
    return {'message':'选择范围已更新'}

@H.command('selection.to_skin')
def to_skin(p):
    obj=H.mesh(p);base=poly(obj);selected=selected_poly_vertices(obj,p.get('level','vertex'))
    if not selected:raise ValueError('没有选中子对象')
    s=H.skin(obj,p)
    if int(base.GetNumVertices(node=obj) if is_modifier(base) else rt.polyop.getNumVerts(base))!=int(rt.skinOps.GetNumberVertices(s)):raise ValueError('基础模型与 Skin 顶点数不一致，不能安全转换选择')
    rt.skinOps.SelectVertices(s,bit(selected));s.filter_vertices=True;rt.subObjectLevel=1
    return {'message':'已将选择转换为 %d 个 Skin 顶点'%len(selected),'vertices':selected}

@H.command('selection.visibility',True)
def component_visibility(p):
    obj=H.mesh(p);base=poly(obj);level=p.get('level','vertex');operation=p['operation']
    if is_modifier(base):
        rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(base)
        if operation=='show':
            base.ButtonOp(rt.Name('UnhideAllVertex'));base.ButtonOp(rt.Name('UnhideAllFace'))
        else:
            chosen=selected_poly_vertices(obj,level)
            if not chosen:raise ValueError('请先选择需要隐藏或仅显示的子对象')
            base.SetEPolySelLevel(rt.Name('face' if level=='face' else 'vertex'))
            base.ButtonOp(rt.Name(('Hide' if operation=='hide' else 'HideUnselected')+('Face' if level=='face' else 'Vertex')))
    elif operation=='show':
        rt.polyop.setHiddenVerts(base,bit([]));rt.polyop.setHiddenFaces(base,bit([]))
    else:
        chosen=set(selected_poly_vertices(obj,level))
        if not chosen:raise ValueError('请先选择需要隐藏或仅显示的子对象')
        hidden=chosen if operation=='hide' else set(range(1,int(rt.polyop.getNumVerts(base))+1))-chosen
        rt.polyop.setHiddenVerts(base,bit(hidden))
        face_sel=set(ids(rt.polyop.getFaceSelection(base))) if level=='face' else set(ids(rt.polyop.getFacesUsingVert(base,bit(chosen))))
        all_faces=set(range(1,int(rt.polyop.getNumFaces(base))+1))
        rt.polyop.setHiddenFaces(base,bit(face_sel if operation=='hide' else all_faces-face_sel))
    count=int(base.GetNumVertices(node=obj) if is_modifier(base) else rt.polyop.getNumVerts(base))
    hidden=[] if operation=='show' else list(set(chosen) if operation=='hide' else set(range(1,count+1))-set(chosen))
    rt.setUserProp(obj,'LXHiddenVertices',json.dumps(hidden))
    rt.update(obj)
    return {'message':'子对象可见性已更新；显示全部可恢复'}

_DRAG=None
@H.command('humanoid.drag')
def drag_humanoid(p):
    global _DRAG
    _DRAG=(dict(p),str(rt.LXRigSceneToken))
    from pathlib import Path
    rt.fileIn(str(Path(__file__).parent/'viewport_tools.ms'))
    rt.execute('startTool LXHumanoidPlacement')
    return {'message':'在视口按下并拖出人物高度；右键取消。生成后可自由调整骨架。'}

def complete_drag():
    from PySide6.QtCore import QTimer
    pending=_DRAG
    if pending is None:return
    p,scene=pending;a=H.vec(rt.LXPlacementStart);b=H.vec(rt.LXPlacementEnd)
    p=dict(p,origin=a,height=binding.distance(a,b))
    def finish():
        try:result=H.dispatch({'action':'humanoid.create','scene':scene,'params':p});notify(result['message'])
        except Exception as e:notify(str(e))
    QTimer.singleShot(0,finish)

def notify(message):
    from . import max_ui
    dock=max_ui._dock
    if dock is not None and not dock.closed:dock.workbench.notice.setText(message)


