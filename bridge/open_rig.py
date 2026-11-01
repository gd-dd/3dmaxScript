"""Fixed Max entry point; usable without the shelf or the session provider."""
import sys,hashlib,importlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
loaded=sys.modules.get('rig')
if loaded and Path(loaded.__file__).resolve().parent!=root/'rig':
    raise RuntimeError('另一版本的绑定蒙皮工具已加载，请重新打开 Max 后使用此版本。')
if str(root) not in sys.path:sys.path.insert(0,str(root))
digest=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root/'rig').iterdir()) if p.suffix in ('.py','.ms'))).hexdigest()
ui=sys.modules.get('rig.max_ui')
if ui is not None and getattr(ui,'_code_digest',None)!=digest:
    from pymxs import runtime as rt
    from shiboken6 import isValid
    if rt.theHold.Holding():raise RuntimeError('请先结束当前拖动或笔划，再重新呼出工具。')
    dock=getattr(ui,'_dock',None)
    if dock is not None and isValid(dock):dock.close()
    for name in ('rig.brush','rig.symmetry'):
        module=sys.modules.get(name)
        if module:module.stop()
    view=sys.modules.get('rig.weight_view')
    if view:view.clear()
    # Keep history.py and its undo callbacks alive. Reload only implementation/UI.
    for name in ('weights','binding','weight_edit','humanoid','theme','scene_ui','workbench',
                 'max_host','workflow_host','brush','symmetry','scene_io','batch_host',
                 'weight_view','selection_ui','workflow_ui','max_ui'):
        key='rig.'+name
        if key in sys.modules:importlib.reload(sys.modules[key])
        else:importlib.import_module(key)
from rig import max_ui
max_ui._code_digest=digest
max_ui.show_workbench()
