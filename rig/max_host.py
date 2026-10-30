"""Main-thread Max adapter. Only registered commands may mutate the scene."""
import os, json, uuid, math
from pathlib import Path
import pymxs
from pymxs import runtime as rt
from . import weights as W

COMMANDS={}

def command(name,write=False):
    def decorate(fn):COMMANDS[name]=(fn,write);return fn
    return decorate

def handle(node):return str(int(rt.getHandleByAnim(node)))
def node(ref):
    obj=rt.getAnimByHandle(int(ref))
    if obj is None or not rt.isValidNode(obj):raise ValueError('对象已不存在，请刷新场景')
    return obj

def vec(p):return [float(p.x),float(p.y),float(p.z)]
def matrix_rows(m):return [vec(m[i]) for i in range(4)]
def matrix_value(rows):return rt.Matrix3(*[rt.Point3(*v) for v in rows])
def cls(obj):return str(rt.classOf(obj))
def arr(values):return rt.Array(*values)

def mesh(p):
    obj=node(p['mesh'])
    if rt.superClassOf(obj)!=rt.GeometryClass:raise ValueError('请选择几何模型')
    return obj

def skin(obj,p):
    index=int(p.get('skin',0))
    if p.get('skinHandle'):
        index=next((i for i,m in enumerate(obj.modifiers) if handle(m)==str(p['skinHandle'])),-1)
    if index<0 or index>=len(obj.modifiers) or cls(obj.modifiers[index])!='Skin':raise ValueError('Skin 已变化，请重新选择修改器')
    s=obj.modifiers[index]
    if p.get('skinHandle') and p['skinHandle']!=handle(s):raise ValueError('Skin 实例已替换，请刷新场景')
    rt.select(obj);rt.execute("max modify mode");rt.modPanel.setCurrentObject(s)
    return s

def geometry(obj):
    temp=rt.snapshotAsMesh(obj)
    try:
        points=[vec(rt.getVert(temp,i)) for i in range(1,int(temp.numverts)+1)]
        faces=[]
        for i in range(1,int(temp.numfaces)+1):faces.append([int(x)-1 for x in vec(rt.getFace(temp,i))])
        return points,faces
    finally:rt.delete(temp)

def influences(s):
    result=[]
    for i in range(1,int(rt.skinOps.GetNumberBones(s))+1):
        b=rt.skinOps.GetBoneNode(s,i)
        if b is not None:result.append({'id':str(i),'node':handle(b),'name':str(b.name)})
    return result

def read_rows(s):
    return [{str(int(rt.skinOps.GetVertexWeightBoneID(s,i,j))):float(rt.skinOps.GetVertexWeight(s,i,j)) for j in range(1,int(rt.skinOps.GetVertexWeightCount(s,i))+1)} for i in range(1,int(rt.skinOps.GetNumberVertices(s))+1)]

def skin_data(obj,s):
    rt.select(obj);rt.execute('max modify mode');rt.modPanel.setCurrentObject(s)
    positions,faces=geometry(obj);rows=read_rows(s)
    if len(rows)!=len(positions):raise ValueError('Skin 顶点数与当前几何不一致，请检查修改器堆栈')
    bones=influences(s)
    data={'schema':1,'mesh':handle(obj),'meshName':str(obj.name),'scene':str(rt.LXRigSceneToken),'topology':W.topology_signature(len(rows),faces),'positions':positions,'faces':faces,'bones':bones,'weights':rows}
    if sum(cls(m)=='Skin' for m in obj.modifiers)==1:
        data['binding']={'mesh':matrix_rows(rt.skinUtils.GetMeshBindTM(obj)),
            'bones':{b['node']:{'bind':matrix_rows(rt.skinUtils.GetBoneBindTM(obj,node(b['node']))),'stretch':matrix_rows(rt.skinUtils.GetBoneStretchTM(obj,node(b['node'])))} for b in bones},
            'index':next(i for i,m in enumerate(obj.modifiers) if m==s),'name':str(s.name)}
    return data

def selected_vertices(s,p,count):
    scope=p.get('scope','selected')
    if scope=='all':return list(range(count))
    if scope=='indices':
        result=sorted(set(int(i)-1 for i in p.get('vertices',[])))
        if any(i<0 or i>=count for i in result):raise ValueError('顶点编号超出范围')
    elif scope=='selected':result=[i-1 for i in range(1,count+1) if rt.skinOps.IsVertexSelected(s,i)]
    else:raise ValueError('未知作用范围')
    if not result:raise ValueError('没有选中顶点；请从 Max 选择 Skin 顶点，或显式选择全部顶点')
    return result

def write_rows(s,rows,indices=None,record_history=True):
    bones={b['id'] for b in influences(s)}
    indices=list(range(len(rows))) if indices is None else list(indices)
    for i in indices:
        row=rows[i]
        if not row or any(k not in bones for k in row) or any(not math.isfinite(v) or v<0 for v in row.values()) or abs(sum(row.values())-1)>1e-5:raise ValueError('待写入权重无效，已阻止修改')
    if record_history:
        from . import history
        history.prepare(s,read_rows(s))
    for i in indices:
        row=rows[i];keys=sorted(row,key=int)
        rt.skinOps.ReplaceVertexWeights(s,i+1,arr([int(k) for k in keys]),arr([float(row[k]) for k in keys]))
    rt.skinOps.Invalidate(s,1);rt.completeRedraw()
    for i in indices:
        actual={str(int(rt.skinOps.GetVertexWeightBoneID(s,i+1,j))):float(rt.skinOps.GetVertexWeight(s,i+1,j)) for j in range(1,int(rt.skinOps.GetVertexWeightCount(s,i+1))+1)}
        if any(abs(actual.get(k,0)-rows[i].get(k,0))>2e-5 for k in set(actual)|set(rows[i])):raise RuntimeError('顶点 %d 权重读回不一致，将撤销本次操作：%s != %s'%(i+1,actual,rows[i]))
    if record_history:history.commit(s,read_rows(s))

def profile(obj,s=None):
    raw=rt.getUserProp(obj,'LXRigProfile')
    data=json.loads(str(raw)) if raw else {'schema':1,'humanoid':{},'face':{},'pairs':{},'locked':[]}
    if s is not None and '_boneNodes' in data:
        current={b['node']:b['id'] for b in influences(s)}
        remap={k:current[v] for k,v in data['_boneNodes'].items() if v in current}
        data['pairs']={remap[k]:remap[v] for k,v in data.get('pairs',{}).items() if k in remap and v in remap}
        data['locked']=[remap[k] for k in data.get('locked',[]) if k in remap]
    return data

def save_profile(obj,data):rt.setUserProp(obj,'LXRigProfile',json.dumps(data,ensure_ascii=True,separators=(',',':')))

def backup_root():
    p=Path(os.environ['LOCALAPPDATA'])/'LXMaxTools'/'rig-snapshots'/str(rt.LXRigSceneToken);p.mkdir(parents=True,exist_ok=True);return p

def backup(data,label):
    token=uuid.uuid4().hex;data=dict(data,label=label)
    (backup_root()/(token+'.json')).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),'utf-8');return token

def snapshot_list(obj):
    result=[]
    for p in sorted(backup_root().glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            d=json.loads(p.read_text('utf-8'))
            if d['mesh']==handle(obj):result.append({'id':p.stem,'label':d.get('label','权重快照'),'time':p.stat().st_mtime})
        except (ValueError,KeyError,OSError):continue
    return result[:40]

@command('scene.inspect')
def inspect_scene(p):
    nodes=list(rt.objects)
    if len(nodes)>10000:raise ValueError('场景对象超过 10000，请在简化场景中操作')
    result=[]
    for n in nodes:
        result.append({'id':handle(n),'name':str(n.name),'class':cls(n),'parent':handle(n.parent) if n.parent else None,'position':vec(n.pos),'geometry':rt.superClassOf(n)==rt.GeometryClass and cls(n)!='BoneGeometry' and not bool(getattr(n,'isBone',False)),'bone':bool(getattr(n,'isBone',False)) or 'Bone' in cls(n) or rt.superClassOf(n)==rt.Helper,'hidden':bool(n.isHidden),'workflow':str(rt.getUserProp(n,'LXWorkflow') or ''),'selected':bool(n.isSelected),'skins':[{'index':i,'name':str(m.name),'handle':handle(m)} for i,m in enumerate(n.modifiers) if cls(m)=='Skin']})
    return {'scene':str(rt.LXRigSceneToken),'nodes':result,'capabilities':list(COMMANDS),'maxVersion':list(rt.maxVersion())[:3]}

@command('nodes.select')
def select_nodes(p):
    objects=[node(i) for i in p.get('nodes',[])];rt.select(arr(objects));return {'message':'已在 Max 选择 %d 个对象'%len(objects)}

@command('bone.create',True)
def create_bone(p):
    a=[W.finite(v) for v in p['start']];b=[W.finite(v) for v in p['end']]
    if len(a)!=3 or len(b)!=3 or sum((x-y)**2 for x,y in zip(a,b))<1e-8:raise ValueError('骨骼起终点不能重合')
    z=rt.Point3(0,0,1) if abs(b[0]-a[0])+abs(b[1]-a[1])>1e-5 else rt.Point3(0,1,0)
    bone=rt.boneSys.createBone(rt.Point3(*a),rt.Point3(*b),z);bone.name=rt.uniqueName(str(p.get('name','LX_Bone')))
    if p.get('parent'):bone.parent=node(p['parent'])
    return {'message':'骨骼已创建','node':handle(bone)}

@command('bone.rename',True)
def rename_bone(p):
    obj=node(p['node']);name=str(p['name']).strip()
    if not name or len(name)>128:raise ValueError('名称长度应为 1–128')
    if any(n!=obj and str(n.name)==name for n in rt.objects):raise ValueError('名称已存在')
    obj.name=name;return {'message':'名称已更新'}

@command('bone.parent',True)
def parent_bone(p):
    obj=node(p['node']);parent=node(p['parent']) if p.get('parent') else None;cur=parent
    while cur is not None:
        if cur==obj:raise ValueError('父子关系会形成循环')
        cur=cur.parent
    if 'Biped' in cls(obj) or 'CAT' in cls(obj):raise ValueError('Biped/CAT 层级由专用系统管理，不能按普通骨骼改写')
    tm=rt.copy(obj.transform);obj.parent=parent;obj.transform=tm
    return {'message':'层级已更新，保留当前世界变换；动画重定向不在此操作范围内'}

@command('bind.create',True)
def bind(p):
    obj=mesh(p);bones=[node(ref) for ref in p['bones']]
    if not bones:raise ValueError('请先选择影响骨骼')
    if any(b==obj for b in bones):raise ValueError('模型不能作为自身影响骨骼')
    if any(cls(m)=='Skin' for m in obj.modifiers):raise ValueError('模型已有 Skin，请选择现有 Skin 编辑')
    s=rt.Skin();rt.addModifier(obj,s);rt.select(obj);rt.execute("max modify mode");rt.modPanel.setCurrentObject(s)
    for b in bones:rt.skinOps.addBone(s,b,1)
    return {'message':'Skin 已创建；初始权重使用 Max 包络，请检查变形','skin':0}

@command('bind.unbind',True)
def unbind(p):
    obj=mesh(p);s=skin(obj,p);token=backup(skin_data(obj,s),'解除绑定前')
    rt.deleteModifier(obj,s);return {'message':'Skin 已移除；完整恢复使用 Max 撤销，快照可恢复权重和绑定矩阵','snapshot':token}

@command('bind.add',True)
def add_bones(p):
    obj=mesh(p);s=skin(obj,p);bones=[node(ref) for ref in p['bones']];known={x['node'] for x in influences(s)}
    backup(skin_data(obj,s),'增加影响骨骼前')
    for b in bones:
        if handle(b) not in known:rt.skinOps.addBone(s,b,1)
    return {'message':'影响骨骼已添加'}

@command('bind.remove',True)
def remove_bone(p):
    obj=mesh(p);s=skin(obj,p);bid=str(p['bone']);data=skin_data(obj,s)
    if any(row.get(bid,0)>W.EPS for row in data['weights']):raise ValueError('此骨骼仍影响顶点，请先转移权重再移除')
    backup(data,'移除影响骨骼前');rt.skinOps.removeBone(s,int(bid));return {'message':'零权重影响骨骼已移除'}

@command('skin.inspect')
def inspect_skin(p):
    obj=mesh(p);s=skin(obj,p);bones=influences(s);count=int(rt.skinOps.GetNumberVertices(s))
    selected=[i for i in range(1,count+1) if rt.skinOps.IsVertexSelected(s,i)]
    vertex=int(p.get('vertex',selected[0] if selected else 1))
    row={}
    if count and 1<=vertex<=count:row={str(int(rt.skinOps.GetVertexWeightBoneID(s,vertex,j))):float(rt.skinOps.GetVertexWeight(s,vertex,j)) for j in range(1,int(rt.skinOps.GetVertexWeightCount(s,vertex))+1)}
    return {'mesh':handle(obj),'count':count,'selectedCount':len(selected),'vertex':vertex,'weights':row,'bones':bones,'profile':profile(obj,s),'snapshots':snapshot_list(obj)}

@command('weights.edit',True)
def edit_weights(p):
    obj=mesh(p);s=skin(obj,p);data=skin_data(obj,s);rows=data['weights'];ids=selected_vertices(s,p,len(rows));mode=p['mode'];locked=set(profile(obj,s).get('locked',[]))|set(map(str,p.get('locked',[])))
    if mode=='smooth':out=W.smooth(rows,W.adjacency(len(rows),data['faces']),ids,p.get('strength',.5),p.get('iterations',1),locked)
    else:
        out=[dict(r) for r in rows]
        for i in ids:
            if mode in ('set','add'):out[i]=W.edit(rows[i],p['bone'],p['value'],mode,locked)
            elif mode=='normalize':out[i]=W.normalize(rows[i],locked)
            elif mode=='prune':out[i]=W.prune(rows[i],p.get('threshold',.001),p.get('limit',4),locked)
            else:raise ValueError('未知权重编辑模式')
    token=backup(data,'权重编辑前：'+mode);write_rows(s,out,ids);return {'message':'已更新 %d 个顶点；支持 Max 撤销和快照恢复'%len(ids),'snapshot':token}

@command('weights.mirror',True)
def mirror_weights(p):
    obj=mesh(p);s=skin(obj,p);data=skin_data(obj,s);ids=selected_vertices(s,p,len(data['weights']))
    pairs=profile(obj,s).get('pairs',{});out=W.mirrored(data['weights'],data['positions'],pairs,ids,int(p.get('axis',0)),W.finite(p.get('offset',0)),W.finite(p.get('tolerance',.01)),p.get('direction','positive'))
    backup(data,'镜像前');write_rows(s,out,ids);return {'message':'镜像完成（模型局部坐标），请检查变形'}

@command('weights.transfer',True)
def transfer_weights(p):
    target=mesh(p);ts=skin(target,p);source=node(p['source']);ss=skin(source,{'skin':int(p.get('sourceSkin',0))})
    src=skin_data(source,ss);dst=skin_data(target,ts)
    mapping=bone_mapping(src,dst)
    source_positions=[vec(rt.Point3(*v)*source.objectTransform) for v in src['positions']]
    target_positions=[vec(rt.Point3(*v)*target.objectTransform) for v in dst['positions']]
    out=W.transfer(src['weights'],source_positions,target_positions,W.finite(p['distance']))
    out=[{mapping[k]:v for k,v in row.items()} for row in out]
    backup(dst,'传递前');skin(target,p);write_rows(ts,out);return {'message':'已按当前世界空间最近顶点传递权重；请检查关节和薄面'}

def bone_mapping(src,dst):
    mapping={};by_name={}
    for b in dst['bones']:by_name.setdefault(b['name'],[]).append(b['id'])
    current={b['node']:b['id'] for b in dst['bones']}
    for b in src['bones']:
        if src.get('scene')==dst.get('scene') and b['node'] in current:mapping[b['id']]=current[b['node']]
        elif len(by_name.get(b['name'],[]))==1:mapping[b['id']]=by_name[b['name']][0]
        else:raise ValueError('无法唯一映射影响骨骼：'+b['name'])
    if len(set(mapping.values()))!=len(mapping):raise ValueError('影响骨骼映射发生合并，已拒绝导入')
    return mapping

@command('weights.export')
def export_weights(p):
    obj=mesh(p);s=skin(obj,p);data=skin_data(obj,s);path=Path(p['path'])
    if not path.is_absolute() or path.suffix.lower()!='.json':raise ValueError('请选择绝对路径的 JSON 文件')
    if path.exists() and not p.get('overwrite'):raise ValueError('文件已存在，请使用新的文件名')
    path.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),'utf-8');return {'message':'权重已导出：'+str(path)}

@command('weights.import',True)
def import_weights(p):
    obj=mesh(p);s=skin(obj,p);dst=skin_data(obj,s);path=Path(p['path'])
    if not path.is_absolute() or path.stat().st_size>128*1024*1024:raise ValueError('路径无效或文件超过 128 MiB')
    src=json.loads(path.read_text('utf-8-sig'))
    if src.get('schema')!=1 or src.get('topology')!=dst['topology'] or len(src.get('weights',[]))!=len(dst['weights']):raise ValueError('文件版本或拓扑不匹配；不同拓扑请使用传递工具')
    mapping=bone_mapping(src,dst);out=[{mapping[k]:W.finite(v) for k,v in row.items()} for row in src['weights']]
    backup(dst,'导入前');write_rows(s,out);return {'message':'导入完成，骨骼与拓扑匹配、权重读回通过'}

@command('snapshot.create')
def create_snapshot(p):
    obj=mesh(p);s=skin(obj,p);token=backup(skin_data(obj,s),str(p.get('label','手动快照'))[:100]);return {'message':'快照已保存','snapshot':token}

@command('snapshot.list')
def list_snapshots(p):return {'snapshots':snapshot_list(mesh(p))}

@command('snapshot.restore',True)
def restore_snapshot(p):
    obj=mesh(p);token=str(p['snapshot'])
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('快照标识无效')
    src=json.loads((backup_root()/(token+'.json')).read_text('utf-8'))
    positions,faces=geometry(obj)
    if src['mesh']!=handle(obj) or src['scene']!=str(rt.LXRigSceneToken) or src['topology']!=W.topology_signature(len(positions),faces):raise ValueError('快照目标或拓扑已变化')
    if any(cls(m)=='Skin' for m in obj.modifiers):s=skin(obj,p);backup(skin_data(obj,s),'恢复快照前')
    else:
        binding=src.get('binding')
        if not binding:raise ValueError('此快照未记录唯一 Skin 的绑定矩阵，不能重建绑定；请使用 Max 撤销')
        bones=[node(b['node']) for b in src['bones']];s=rt.Skin();rt.addModifier(obj,s,before=int(binding['index']));s.name=binding['name'];rt.select(obj);rt.execute("max modify mode");rt.modPanel.setCurrentObject(s)
        for b in bones:rt.skinOps.addBone(s,b,1)
        rt.skinUtils.SetMeshBindTM(obj,matrix_value(binding['mesh']))
        for ref,data in binding['bones'].items():
            rt.skinUtils.SetBoneBindTM(obj,node(ref),matrix_value(data['bind']));rt.skinUtils.SetBoneStretchTM(obj,node(ref),matrix_value(data['stretch']))
    dst=skin_data(obj,s);mapping=bone_mapping(src,dst);out=[{mapping[k]:v for k,v in row.items()} for row in src['weights']];write_rows(s,out)
    return {'message':'快照权重已恢复；新建 Skin 的其他参数使用默认值'}

@command('skin.check')
def check_skin(p):
    obj=mesh(p);s=skin(obj,p);data=skin_data(obj,s);issues=W.validate_rows(data['weights'],[b['id'] for b in data['bones']],int(p.get('limit',4)))
    return {'message':'检查完成：%d 个问题顶点'%len(issues),'issues':issues[:1000],'issueCount':len(issues),'vertices':[x['vertex'] for x in issues]}

@command('vertices.select')
def select_vertices(p):
    obj=mesh(p);s=skin(obj,p);count=int(rt.skinOps.GetNumberVertices(s));ids=sorted(set(int(i) for i in p['vertices']))
    if any(i<1 or i>count for i in ids):raise ValueError('顶点编号越界')
    rt.subObjectLevel=1;rt.skinOps.SelectVertices(s,arr(ids));return {'message':'已选择 %d 个顶点'%len(ids)}

@command('profile.save',True)
def set_profile(p):
    obj=mesh(p);data=p['profile']
    if not isinstance(data,dict) or data.get('schema')!=1:raise ValueError('配置格式无效')
    for key in ('humanoid','face'):
        if not isinstance(data.get(key,{}),dict):raise ValueError('骨骼映射格式无效')
        for role,ref in data.get(key,{}).items():
            if len(role)>100:raise ValueError('映射名称过长')
            node(ref)
    pairs=data.get('pairs',{});s=skin(obj,p) if any(cls(m)=='Skin' for m in obj.modifiers) else None;bone_info=influences(s) if s is not None else [];known={b['id'] for b in bone_info}
    if any(k not in known or v not in known or pairs.get(v)!=k for k,v in pairs.items()):raise ValueError('左右影响映射必须双向且存在于当前 Skin')
    if any(k not in known for k in data.get('locked',[])):raise ValueError('锁定骨骼不在当前 Skin 中')
    data['_boneNodes']={b['id']:b['node'] for b in bone_info}
    save_profile(obj,data);return {'message':'角色映射与锁定设置已保存到模型'}

@command('profile.inspect')
def inspect_profile(p):return {'profile':profile(mesh(p))}

@command('pose.capture',True)
def capture_pose(p):
    obj=mesh(p);bones=[node(i) for i in p['bones']]
    data=[{'node':handle(b),'matrix':[vec(b.transform[i]) for i in range(4)]} for b in bones]
    rt.setUserProp(obj,'LXRigPose',json.dumps(data));return {'message':'当前骨骼姿态已记录；不改变 Skin 绑定矩阵'}

@command('pose.restore',True)
def restore_pose(p):
    obj=mesh(p);raw=rt.getUserProp(obj,'LXRigPose')
    if not raw:raise ValueError('尚未记录姿态')
    data=json.loads(str(raw));targets=[(node(x['node']),x['matrix']) for x in data]
    for b,m in targets:b.transform=rt.Matrix3(*[rt.Point3(*v) for v in m])
    return {'message':'已恢复记录姿态；未重定义 Skin 绑定姿态'}

def morpher(obj,p,create=False):
    mods=[(i,m) for i,m in enumerate(obj.modifiers) if cls(m)=='Morpher']
    index=p.get('morpher')
    if index is not None:
        match=next((m for i,m in mods if i==int(index)),None)
        if match is None:raise ValueError('Morpher 已变化，请刷新')
        return match
    if len(mods)>1:raise ValueError('存在多个 Morpher，请指定修改器')
    if mods:return mods[0][1]
    if create:
        m=rt.Morpher();skins=[i for i,mod in enumerate(obj.modifiers) if cls(mod)=='Skin']
        rt.addModifier(obj,m,before=max(skins)+1 if skins else 0);return m
    raise ValueError('模型还没有 Morpher')

@command('morph.inspect')
def inspect_morph(p):
    obj=mesh(p);mods=[(i,m) for i,m in enumerate(obj.modifiers) if cls(m)=='Morpher'];result=[]
    for i,m in mods:
        channels=[{'index':c,'name':str(rt.WM3_MC_GetName(m,c)),'value':float(rt.WM3_MC_GetValue(m,c))} for c in range(1,int(rt.WM3_NumberOfChannels(m))+1) if rt.WM3_MC_HasData(m,c)]
        result.append({'index':i,'name':str(m.name),'channels':channels})
    return {'morphers':result}

@command('morph.add',True)
def add_morph(p):
    obj=mesh(p);target=node(p['target']);a,af=geometry(obj);b,bf=geometry(target)
    if obj==target or W.topology_signature(len(a),af)!=W.topology_signature(len(b),bf):raise ValueError('表情目标必须是同拓扑的其他模型')
    m=morpher(obj,p,True);c=int(p['channel'])
    if not 1<=c<=100:raise ValueError('首版支持通道 1–100')
    if rt.WM3_MC_HasData(m,c):raise ValueError('通道已占用，不能覆盖')
    if not rt.WM3_MC_BuildFromNode(m,c,target):raise RuntimeError('Max 未能建立表情通道')
    rt.WM3_MC_SetName(m,c,str(p.get('name',target.name)));return {'message':'表情通道已建立；请检查 Morpher 在修改器堆栈的位置'}

@command('morph.value',True)
def set_morph_value(p):
    m=morpher(mesh(p),p);c=int(p['channel']);value=W.finite(p['value'])
    if not -100<=value<=100:raise ValueError('表情预览范围为 -100 到 100')
    if not rt.WM3_MC_HasData(m,c):raise ValueError('通道不存在')
    rt.WM3_MC_SetValue(m,c,float(value))
    if abs(float(rt.WM3_MC_GetValue(m,c))-value)>1e-4:raise RuntimeError('表情值受限，读回不一致')
    rt.redrawViews();return {'message':'表情值已更新（未自动打关键帧）'}

@command('morph.reset',True)
def reset_morph(p):
    m=morpher(mesh(p),p)
    for c in range(1,int(rt.WM3_NumberOfChannels(m))+1):
        if rt.WM3_MC_HasData(m,c):rt.WM3_MC_SetValue(m,c,0.0)
    rt.redrawViews();return {'message':'当前 Morpher 全部通道已归零'}

def dispatch(request):
    action=request.get('action');params=request.get('params',{})
    if action not in COMMANDS or not isinstance(params,dict):raise ValueError('不支持的工作台命令')
    fn,write=COMMANDS[action]
    if action!='scene.inspect' and request.get('scene')!=str(rt.LXRigSceneToken):raise ValueError('场景已切换，请刷新后重试')
    if action not in ('brush.stop','scene.inspect'):
        from . import brush
        if brush._active is not None:raise ValueError('请先退出权重笔刷再执行其他操作')
    if not write:return fn(params)
    if rt.theHold.Holding():raise ValueError('Max 正在处理其他撤销事务，请稍后重试')
    failure=None;result=None
    # pymxs.undo rolls back on exceptions but suppresses them. Preserve the
    # exception explicitly and report it after the context has rolled back.
    with pymxs.undo(True,'LX Rig: '+action):
        try:
            with pymxs.animate(False):result=fn(params)
        except BaseException as error:
            failure=error
            raise
    if failure is not None:raise failure
    rt.redrawViews();return result

# Extensions register typed commands without coupling the original adapter to UI.
from . import workflow_host
from . import brush
from . import symmetry
