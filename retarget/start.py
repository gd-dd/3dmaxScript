"""Optional direct Max entry inside the complete Max toolkit package."""
from pathlib import Path
import runpy
import sys


def main():
    root = Path(main.__code__.co_filename).resolve().parents[1]
    bridge = root / "bridge" / "open_retarget.py"
    if not bridge.is_file():
        raise RuntimeError("请保留完整 Max 工具集目录；重定向需要父包的 bridge/open_retarget.py。")
    runpy.run_path(str(bridge), run_name="_lx_maxsuite_retarget_entry")
    launcher = sys.modules.get("retarget.launcher")
    window = getattr(launcher, "_window", None)
    if window is None:
        raise RuntimeError("Max 工具集入口未返回重定向窗口，请检查宿主回执。")
    return window


if __name__ == "__main__":
    main()
