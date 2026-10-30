"""Pure sparse-weight algorithms. No Qt, Max or file-system dependencies."""
import math
import hashlib
import json

EPS=1e-8

def finite(value):
    value=float(value)
    if not math.isfinite(value):raise ValueError('数值必须有限')
    return value

def normalize(row, locked=()):
    row={str(k):finite(v) for k,v in row.items()}
    if any(v<0 for v in row.values()):raise ValueError('权重不能为负数')
    locked=set(map(str,locked));fixed={k:v for k,v in row.items() if k in locked}
    total=sum(fixed.values())
    if total>1+EPS:raise ValueError('锁定权重之和超过 1')
    free={k:v for k,v in row.items() if k not in locked and v>EPS}
    remaining=max(0,1-total);subtotal=sum(free.values())
    if remaining>EPS and subtotal<EPS:raise ValueError('没有可分配剩余权重的未锁定骨骼')
    result={**fixed,**{k:v*remaining/subtotal for k,v in free.items()}} if subtotal else fixed
    return {k:v for k,v in result.items() if v>EPS or (k in locked and v>0)}

def edit(row,bone,value,mode='set',locked=()):
    bone=str(bone);locked=set(map(str,locked));value=finite(value)
    if bone in locked:raise ValueError('目标骨骼已锁定')
    row={str(k):finite(v) for k,v in row.items()}
    if any(v<0 for v in row.values()):raise ValueError('权重不能为负数')
    if mode=='add':value=row.get(bone,0)+value
    elif mode!='set':raise ValueError('未知权重编辑方式')
    fixed=sum(v for k,v in row.items() if k in locked)
    if fixed>1+EPS:raise ValueError('锁定权重之和超过 1')
    if not 0<=value<=1-fixed+EPS:raise ValueError('目标权重超出剩余可分配范围')
    remaining=max(0,1-fixed-value)
    other={k:v for k,v in row.items() if k!=bone and k not in locked and v>EPS}
    if remaining>EPS and not other:raise ValueError('没有其他未锁定骨骼接收剩余权重；请先添加权重或设为 1')
    out={k:v for k,v in row.items() if k in locked};out[bone]=value
    if other:
        total=sum(other.values());out.update({k:v*remaining/total for k,v in other.items()})
    return {k:v for k,v in out.items() if v>EPS or (k in locked and v>0)}

def prune(row,threshold=0.001,limit=4,locked=()):
    row={str(k):finite(v) for k,v in row.items()}
    if any(v<0 for v in row.values()):raise ValueError('权重不能为负数')
    threshold=finite(threshold);limit=int(limit);locked=set(map(str,locked))
    if not 0<=threshold<=1 or limit<1:raise ValueError('清理阈值或影响数无效')
    fixed={str(k):v for k,v in row.items() if str(k) in locked and v>0}
    if len(fixed)>limit:raise ValueError('锁定影响数已超过上限')
    free=sorted(((str(k),v) for k,v in row.items() if str(k) not in locked and v>EPS),key=lambda x:(-x[1],x[0]))
    kept=[x for x in free if x[1]>=threshold][:max(0,limit-len(fixed))]
    if not kept and sum(fixed.values())<1-EPS and free and len(fixed)<limit:kept=free[:1]
    return normalize({**fixed,**dict(kept)},locked)

def adjacency(count,faces):
    graph=[set() for _ in range(count)]
    for face in faces:
        for a,b in zip(face,face[1:]+face[:1]):
            if not(0<=a<count and 0<=b<count):raise ValueError('拓扑索引越界')
            if a!=b:graph[a].add(b);graph[b].add(a)
    return graph

def smooth(rows,graph,vertices,strength=0.5,iterations=1,locked=()):
    strength=finite(strength);iterations=int(iterations)
    if not 0<=strength<=1 or not 1<=iterations<=50:raise ValueError('平滑参数无效')
    out=[dict(r) for r in rows];locked=set(map(str,locked))
    for _ in range(iterations):
        before=out;out=[dict(r) for r in before]
        for i in vertices:
            neighbors=graph[i]
            if not neighbors:continue
            avg={}
            for j in neighbors:
                for k,v in before[j].items():avg[k]=avg.get(k,0)+v/len(neighbors)
            mixed={k:before[i].get(k,0)*(1-strength)+avg.get(k,0)*strength for k in set(before[i])|set(avg)}
            for k in locked:mixed[k]=before[i].get(k,0)
            out[i]=normalize(mixed,locked)
    return out

def topology_signature(count,faces):
    return hashlib.sha256(json.dumps([count,faces],separators=(',',':')).encode()).hexdigest()

class PointIndex:
    """Balanced k-d tree; deterministic nearest point with squared distance."""
    def __init__(self,points):
        self.points=points
        def build(ids,depth=0):
            if not ids:return None
            axis=depth%3;ids.sort(key=lambda i:(points[i][axis],i));mid=len(ids)//2
            return ids[mid],axis,build(ids[:mid],depth+1),build(ids[mid+1:],depth+1)
        self.root=build(list(range(len(points))))
    def nearest(self,point):
        best=[float('inf'),-1]
        def visit(node):
            if node is None:return
            i,axis,left,right=node;p=self.points[i];d=sum((a-b)**2 for a,b in zip(p,point))
            if (d,i)<tuple(best):best[:]=[d,i]
            delta=point[axis]-p[axis];first,second=(left,right) if delta<0 else (right,left)
            visit(first)
            if delta*delta<=best[0]:visit(second)
        visit(self.root);return best[1],math.sqrt(best[0])

def mirrored(rows,positions,bone_pairs,vertices,axis=0,offset=0,tolerance=.01,direction='positive'):
    if axis not in (0,1,2) or tolerance<=0:raise ValueError('镜像轴或容差无效')
    if direction not in ('positive','negative','flip'):raise ValueError('镜像方向无效')
    pairs={str(k):str(v) for k,v in bone_pairs.items()}
    if any(pairs.get(v)!=k for k,v in pairs.items()):raise ValueError('骨骼镜像映射必须双向一一对应')
    index=PointIndex(positions);out=[dict(r) for r in rows];used=set();changed=0
    for i in vertices:
        side=positions[i][axis]-offset
        if direction=='positive' and side>=-tolerance:continue
        if direction=='negative' and side<=tolerance:continue
        point=list(positions[i]);point[axis]=2*offset-point[axis];j,d=index.nearest(point)
        if d>tolerance:raise ValueError('顶点 %d 找不到容差内的镜像点，未写入任何权重'%(i+1))
        if j in used:raise ValueError('镜像点重复匹配，请减小容差或修复拓扑')
        used.add(j)
        out[i]={}
        for k,v in rows[j].items():
            dest=pairs.get(k,k);out[i][dest]=out[i].get(dest,0)+v
        out[i]=normalize(out[i]);changed+=1
    if not changed:raise ValueError('所选范围内没有需要镜像的目标侧顶点')
    return out

def transfer(source,source_positions,target_positions,max_distance):
    max_distance=finite(max_distance)
    if max_distance<=0:raise ValueError('传递距离必须大于零')
    index=PointIndex(source_positions);out=[]
    for i,p in enumerate(target_positions):
        j,d=index.nearest(p)
        if d>max_distance:raise ValueError('目标顶点 %d 超过最大传递距离'%(i+1))
        out.append(normalize(source[j]))
    return out

def validate_rows(rows,bones,limit=4):
    issues=[];bones=set(map(str,bones))
    for i,row in enumerate(rows):
        reasons=[]
        if any(k not in bones for k in row):reasons.append('缺失骨骼')
        if any(not math.isfinite(v) or v<0 for v in row.values()):reasons.append('非法权重')
        if not row or abs(sum(row.values())-1)>1e-5:reasons.append('未归一化/无权重')
        if sum(v>EPS for v in row.values())>limit:reasons.append('影响数超限')
        if reasons:issues.append({'vertex':i+1,'issues':reasons})
    return issues
