"""CPU bind solvers. Voxel mode propagates distances ONLY through interior cells."""
import math,heapq
from collections import Counter
from .weights import PointIndex

def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
def segment_distance(p,a,b):
    ab=[y-x for x,y in zip(a,b)];den=sum(v*v for v in ab)
    t=max(0,min(1,sum((p[i]-a[i])*ab[i] for i in range(3))/den)) if den>1e-16 else 0
    return distance(p,[a[i]+t*ab[i] for i in range(3)])
def row(distances,limit,falloff):
    nearest=sorted(distances.items(),key=lambda item:(item[1],item[0]))[:limit]
    if not nearest:raise ValueError('没有可到达的骨骼')
    epsilon=1e-7;minimum=max(epsilon,nearest[0][1])
    values={key:(minimum/max(epsilon,d))**falloff for key,d in nearest};total=sum(values.values())
    return {key:v/total for key,v in values.items() if v/total>1e-8}
def solve(points,faces,segments,method='segment',limit=4,falloff=2,resolution=32,progress=None):
    if not points or not segments:raise ValueError('需要模型顶点与影响骨骼')
    if not 1<=int(limit)<=64 or not .1<=float(falloff)<=16:raise ValueError('影响数或衰减无效')
    limit=int(limit)
    if method=='segment':
        return [row({str(k):segment_distance(p,a,b) for k,a,b in segments},limit,falloff) for p in points],{'method':'segment'}
    if method!='voxel':raise ValueError('未知自动蒙皮方法')
    resolution=int(resolution)
    if not 8<=resolution<=64:raise ValueError('体素分辨率范围 8–64')
    edges=Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
    if any(n!=2 for n in edges.values()):raise ValueError('体素距离场需要封闭流形网格；请补洞或选择线段距离')
    lower=[min(p[i] for p in points) for i in range(3)];upper=[max(p[i] for p in points) for i in range(3)]
    step=max(upper[i]-lower[i] for i in range(3))/resolution
    if step<=1e-10:raise ValueError('模型没有有效体积')
    dims=[max(1,math.ceil((upper[i]-lower[i])/step)) for i in range(3)]
    # Ray/triangle crossings batched into YZ columns; parity filling avoids exterior bridges.
    columns={}
    for face in faces:
        a,b,c=(points[i] for i in face)
        den=(b[2]-c[2])*(a[1]-c[1])+(c[1]-b[1])*(a[2]-c[2])
        if abs(den)<1e-14:continue
        ranges=[range(max(0,math.ceil((min(a[j],b[j],c[j])-lower[j])/step-.5)),min(dims[j]-1,math.floor((max(a[j],b[j],c[j])-lower[j])/step-.5))+1) for j in (1,2)]
        for y in ranges[0]:
            py=lower[1]+(y+.5)*step
            for z in ranges[1]:
                pz=lower[2]+(z+.5)*step
                u=((b[2]-c[2])*(py-c[1])+(c[1]-b[1])*(pz-c[2]))/den
                v=((c[2]-a[2])*(py-c[1])+(a[1]-c[1])*(pz-c[2]))/den
                if u>=-1e-9 and v>=-1e-9 and u+v<=1+1e-9:columns.setdefault((y,z),[]).append(u*a[0]+v*b[0]+(1-u-v)*c[0])
    cells=[];coords=[]
    for (y,z),crossings in columns.items():
        ordered=[]
        for x in sorted(crossings):
            if not ordered or x-ordered[-1]>step*1e-7:ordered.append(x)
        if len(ordered)%2:raise ValueError('体素射线遇到不稳定交点；检查自交或调整分辨率')
        for start,end in zip(ordered[::2],ordered[1::2]):
            for x in range(max(0,math.ceil((start-lower[0])/step-.5)),min(dims[0]-1,math.floor((end-lower[0])/step-.5))+1):
                cells.append((x,y,z));coords.append([lower[j]+(v+.5)*step for j,v in enumerate((x,y,z))])
    if not cells:raise ValueError('未找到内部体素，请提高分辨率或修复网格')
    lookup={c:i for i,c in enumerate(cells)};index=PointIndex(coords);queue=[];best=[{} for _ in cells]
    # Use each bone segment, not just its pivot, as a source through the volume.
    for key,a,b in segments:
        n=max(1,math.ceil(distance(a,b)/(step*.5)))
        seeds={}
        for i in range(n+1):
            p=[a[j]+(b[j]-a[j])*i/n for j in range(3)];near,dist2=index.nearest(p)
            if dist2>step*2:raise ValueError('骨骼位于网格体积外或部位太薄：'+str(key))
            seeds[near]=min(seeds.get(near,float('inf')),dist2)
        for cell,d in seeds.items():heapq.heappush(queue,(d,str(key),cell))
    while queue:
        d,key,cell=heapq.heappop(queue)
        if key in best[cell] or len(best[cell])>=limit:continue
        best[cell][key]=d
        x,y,z=cells[cell]
        for other in ((x-1,y,z),(x+1,y,z),(x,y-1,z),(x,y+1,z),(x,y,z-1),(x,y,z+1)):
            nxt=lookup.get(other)
            if nxt is not None and key not in best[nxt] and len(best[nxt])<limit:heapq.heappush(queue,(d+step,key,nxt))
    output=[]
    for p in points:
        cell,d2=index.nearest(p)
        if not best[cell]:raise ValueError('存在没有骨骼源的独立体积，请为该部分添加骨骼')
        output.append(row({k:d+d2 for k,d in best[cell].items()},limit,falloff))
    return output,{'method':'voxel','resolution':resolution,'cells':len(cells),'cellSize':step}

