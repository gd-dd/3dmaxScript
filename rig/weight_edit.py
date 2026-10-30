"""Multi-influence editing with explicit aggregate target semantics."""
from .weights import normalize,finite,EPS

def edit_many(row,bones,value,mode='set',locked=(),available_bones=()):
    bones=set(map(str,bones));locked=set(map(str,locked));value=finite(value)
    if not bones:raise ValueError('请至少选择一个影响骨骼')
    if bones & locked:raise ValueError('所选骨骼包含锁定影响，请先解除锁定')
    fixed={k:v for k,v in row.items() if k in locked};available=max(0,1-sum(fixed.values()))
    current=sum(row.get(k,0) for k in bones)
    if mode=='add':target=current+value
    elif mode=='subtract':target=current-abs(value)
    elif mode=='set':target=value
    else:raise ValueError('未知多骨骼编辑方式')
    target=min(available,max(0,target));others={k:v for k,v in row.items() if k not in bones|locked and v>EPS}
    if available-target>EPS and not others:
        others={str(k):1.0 for k in available_bones if str(k) not in bones|locked}
        if not others:target=available
    result=dict(fixed)
    for k in bones:result[k]=target*(row.get(k,0)/current if current>EPS else 1/len(bones))
    rest=sum(others.values())
    if rest>EPS:result.update({k:v/rest*(available-target) for k,v in others.items()})
    return normalize(result,locked)
