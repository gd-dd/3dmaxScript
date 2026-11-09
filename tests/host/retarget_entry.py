"""Parent entry integration in a disposable hidden Max, including exact ZIP."""
from pathlib import Path
import os, sys, json, traceback, zipfile
from pymxs import runtime as rt
from PySide6.QtWidgets import QDialog

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent / 'acceptance/maxsuite-retarget-entry-2026-11-10'
report = dict(pid=os.getpid(), checks=[])
original_show, original_raise = QDialog.show, QDialog.raise_
QDialog.show = lambda self: None
QDialog.raise_ = lambda self: None
try:
    package = OUT / 'package'
    with zipfile.ZipFile(ROOT / 'dist/LXTool-package.zip') as archive:
        archive.extractall(package)
    # Max ExecuteFile shares globals; only compiled filename is authoritative.
    rt.python.Execute("__file__ = 'E:/not-the-tool/foreign.py'")
    for label, root in [('source', ROOT), ('exact-zip', package)]:
        rt.fileIn(str(root / 'LX_Retarget.ms'), quiet=True)
        import retarget
        from retarget import launcher
        assert Path(retarget.__file__).resolve().parent == root / 'retarget'
        window = launcher._window
        assert window is not None
        session = window.session
        rt.fileIn(str(root / 'LX_Retarget.ms'), quiet=True)
        assert launcher._window is window and window.session is session
        assert window.parent() is not None, 'window must belong to Max'
        rt.LXMaxBridgeRequestedUserRoot = str(OUT / 'connections' / label)
        rt.fileIn(str(root / 'bridge/LXMaxBridge.ms'), quiet=True)
        rt.LXMaxBridgeRun('retarget')
        assert launcher._window is window
        rt.LXMaxBridgeTimer.Stop()
        report['checks'].append(dict(root=str(root), standalone=True,
                                    repeatSameSession=True, bridge=True))
    report['ok'] = True
except Exception:
    report.update(ok=False, error=traceback.format_exc())
finally:
    QDialog.show, QDialog.raise_ = original_show, original_raise
    try: rt.LXMaxBridgeTimer.Stop()
    except Exception: pass
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
