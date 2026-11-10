"""Transient viewport weight overlay. Never edits materials or mesh channels."""
import json
from pathlib import Path
from . import max_host as H,batch_host
rt=H.rt
_loaded=False
_models=[]
_refs=[]
_bones=set()
_geometry_cache={}

def signature(meshes,bones,step,enabled):
    """Cheap invalidation probe: no SkinOps, mesh snapshots or redraw calls."""
    state=[]
    for ref in meshes:
        obj=H.node(ref);skin=batch_host.get_skin(obj)
        revision=str(skin.lxWeightRevision) if skin is not None and rt.isProperty(skin,'lxWeightRevision') else ''
        state.append((ref,H.handle(skin) if skin is not None else None,revision,str(obj.objectTransform),bool(obj.isHidden)))
    return (str(rt.LXRigSceneToken),str(rt.currentTime),tuple(state),tuple(bones),step,enabled)

def suspend(on):
    if _loaded:rt.LXWeightViewSuspended=bool(on)

def color(value):
    t=max(0,min(1,value))*4;i=min(3,int(t));f=t-i
    stops=((30,65,210),(0,190,240),(60,210,70),(250,210,20),(240,45,30))
    return rt.Color(*[stops[i][j]*(1-f)+stops[i+1][j]*f for j in range(3)])

def clear():
    global _models,_refs
    had_models=bool(_models);_models=[];_refs=[];_geometry_cache.clear()
    if _loaded:
        rt.LXWeightViewData=rt.Array()
        if had_models:rt.redrawViews()

def update(meshes,bones,enabled=True):
    global _loaded,_models,_refs,_bones
    if not _loaded:
        rt.fileIn(str(Path(__file__).with_suffix('.ms')));_loaded=True
    result=batch_host.inspect_weights(meshes,bones);models=[];refs=[];_bones=set(bones)
    if enabled:
        for row in result:
            obj=H.node(row['mesh'])
            if not row['bound'] or obj.isHidden:continue
            hidden_raw=str(rt.getUserProp(obj,'LXHiddenVertices') or '[]')
            stamp=(str(rt.LXRigSceneToken),str(rt.currentTime),str(obj.objectTransform),row['count'],hidden_raw)
            cached=_geometry_cache.get(row['mesh'])
            if cached is None or cached[0]!=stamp:
                points,faces=H.geometry(obj)
                if len(points)!=row['count']:continue
                hidden=set(int(x)-1 for x in json.loads(hidden_raw))
                cached=(stamp,H.arr([rt.Point3(*p)*obj.objectTransform for p in points]),
                        H.arr([H.arr([i+1 for i in f]) for f in faces if not hidden.intersection(f)]))
                _geometry_cache[row['mesh']]=cached
            models.append(H.arr([cached[1],cached[2],H.arr([color(v) for v in row['values']])]))
            refs.append(row['mesh'])
    _models=models;_refs=refs;rt.LXWeightViewData=H.arr(models);rt.redrawViews()
    return result

def brush_changed(brush):
    ref=H.handle(brush.obj)
    if ref not in _refs:return
    keys={b['id'] for b in brush.data['bones'] if b['node'] in _bones}
    _models[_refs.index(ref)][2]=H.arr([color(sum(row.get(k,0) for k in keys)) for row in brush.rows])
    rt.LXWeightViewData=H.arr(_models)
