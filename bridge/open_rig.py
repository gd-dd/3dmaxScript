"""Fixed Max entry point; usable without the shelf or the session provider."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
loaded=sys.modules.get('rig')
if loaded and Path(loaded.__file__).resolve().parent!=root/'rig':
    raise RuntimeError('另一版本的绑定蒙皮工具已加载，请重新打开 Max 后使用此版本。')
if str(root) not in sys.path:sys.path.insert(0,str(root))
from rig.max_ui import show_workbench
show_workbench()
