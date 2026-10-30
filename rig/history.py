"""Undo bridge for SkinOps, whose direct writes do not reliably create restores."""
import uuid,json,zlib
from . import max_host as H
rt=H.rt
_states={};_tracked={};_restoring=False

def setup(s):
    if not rt.isProperty(s,'lxWeightRevision'):
        definition=rt.execute('attributes LXWeightUndo attribID:#(0x58a14001,0x11223344) (parameters state (lxWeightRevision type:#string default:""))')
        with H.pymxs.undo(False):rt.custAttributes.add(s,definition)
    rt.callbacks.removeScripts(id=rt.Name('LXWeightUndo'))
    for event in ('sceneUndo','sceneRedo'):
        rt.callbacks.addScript(rt.Name(event),'python.Execute "from rig.history import restore; restore()"',id=rt.Name('LXWeightUndo'))

def token(s,rows):
    value=uuid.uuid4().hex
    _states[value]=(str(rt.LXRigSceneToken),H.handle(s),zlib.compress(json.dumps(rows,separators=(',',':')).encode()),[(b['id'],b['node']) for b in H.influences(s)])
    return value

def prepare(s,rows):
    setup(s);value=token(s,rows)
    with H.pymxs.undo(False):s.lxWeightRevision=value
    _tracked[H.handle(s)]=(s,value)

def commit(s,rows):
    value=token(s,rows);s.lxWeightRevision=value;_tracked[H.handle(s)]=(s,value)

def restore():
    global _restoring
    if _restoring:return
    _restoring=True
    try:
        for key,(s,last) in list(_tracked.items()):
            if rt.getAnimByHandle(int(key)) is None:continue
            current=str(s.lxWeightRevision)
            if current==last or current not in _states:continue
            scene,identity,packed,bones=_states[current]
            rows=json.loads(zlib.decompress(packed))
            if scene!=str(rt.LXRigSceneToken) or identity!=key:continue
            current_bones={b['node']:b['id'] for b in H.influences(s)}
            if any(node not in current_bones for _,node in bones) or len(rows)!=int(rt.skinOps.GetNumberVertices(s)):continue
            mapping={bid:current_bones[node] for bid,node in bones}
            with H.pymxs.undo(False):H.write_rows(s,[{mapping[k]:v for k,v in row.items()} for row in rows],record_history=False)
            _tracked[key]=(s,current)
    finally:_restoring=False
