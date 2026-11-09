"""The direct child entry must ignore Max's stale shared __file__."""
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest import mock


class DirectStartTests(unittest.TestCase):
    def test_compiled_filename_routes_to_parent_bridge_and_returns_its_window(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "retarget/start.py"
        namespace = {"__file__": "E:/old-unrelated-tool/start.py", "__name__": "_direct_start_probe"}
        exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
        window = object()
        launcher = ModuleType("retarget.launcher")
        launcher._window = window
        with mock.patch.dict(sys.modules, {"retarget.launcher": launcher}), mock.patch("runpy.run_path") as route:
            self.assertIs(namespace["main"](), window)
            route.assert_called_once_with(str(root / "bridge/open_retarget.py"), run_name="_lx_maxsuite_retarget_entry")


if __name__ == "__main__":
    unittest.main()
