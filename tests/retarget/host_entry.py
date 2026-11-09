"""Real parent entries, in a root-launched private Max batch only.

This verifies LX_Retarget.ms and bridge/open_retarget.py, not the shelf provider,
public installation or a user Max. No host is launched by this script.
"""
from pathlib import Path
import importlib
import json
import os
import re
import sys
import traceback


def main():
    root = Path(main.__code__.co_filename).resolve().parents[2]
    if root != Path("E:/project/LXTools/3dmaxScript").resolve():
        raise RuntimeError("Parent entry QA must run from the canonical E repository")
    artifacts = root / "tests/retarget/artifacts"
    if os.environ.get("LXMAXRETARGET_PARENT_QA") != "1":
        raise RuntimeError("LXMAXRETARGET_PARENT_QA=1 is required")
    for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
                "ADSK_3DSMAX_APPDATA_DIR", "ADSK_3DSMAX_USERSETTINGS_DIR"):
        raw = os.environ.get(key)
        if not raw or not Path(raw).is_absolute():
            raise RuntimeError("An isolated absolute E path is required: " + key)
        if not Path(raw).resolve().is_relative_to(artifacts.resolve()):
            raise RuntimeError(key + " must remain inside tests/retarget/artifacts")
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    import pymxs
    from pymxs import runtime as rt
    process = rt.dotNetClass("System.Diagnostics.Process").GetCurrentProcess()
    executable = str(process.MainModule.FileName)
    command = str(rt.dotNetClass("System.Environment").CommandLine)
    if Path(executable).name.lower() != "3dsmax.exe" or not re.search(r"(?:^|\s)-batch(?:\s|$)", command, re.I):
        raise RuntimeError("Only a separately launched 3dsmax.exe -batch may run this entry QA")
    artifacts.mkdir(parents=True, exist_ok=True)
    report = {"status": "failed", "pid": os.getpid(), "parentRoot": str(root),
              "processExecutable": executable, "processCommandLine": command,
              "scope": "real parent MaxScript and Python entries only",
              "providerOrPublicInstallationVerified": False, "maxLaunchedByScript": False,
              "userMaxAttached": False, "checks": [], "routes": [], "suppressedQtCalls": []}
    originals = []
    created = []
    window = None
    previous_path = list(sys.path)

    def matrix(node):
        value = node.transform
        return [[float(row.x), float(row.y), float(row.z)] for row in (value.row1, value.row2, value.row3, value.row4)]

    def scene():
        rows = []
        for node in rt.objects:
            rows.append({"id": int(rt.getHandleByAnim(node)), "name": str(node.name),
                         "parent": int(rt.getHandleByAnim(node.parent)) if node.parent else None,
                         "matrix": matrix(node), "hidden": bool(node.isNodeHidden)})
        return {"nodes": sorted(rows, key=lambda row: row["id"]),
                "selection": [int(rt.getHandleByAnim(n)) for n in rt.selection],
                "time": str(rt.currentTime), "range": str(rt.animationRange),
                "file": str(rt.maxFilePath) + str(rt.maxFileName)}

    def origins():
        if any(name == "lxmaxretarget" or name.startswith("lxmaxretarget.") for name in sys.modules):
            raise RuntimeError("An independent lxmaxretarget module was loaded")
        rows = {}
        for name, module in list(sys.modules.items()):
            if name == "retarget" or name.startswith("retarget."):
                origin = getattr(module, "__file__", None)
                if origin:
                    path = Path(origin).resolve()
                    if not path.is_relative_to((root / "retarget").resolve()):
                        raise RuntimeError("Wrong retarget module root: " + str(path))
                    rows[name] = str(path)
        return rows

    def current_window():
        module = sys.modules["retarget.launcher"]
        found = module._window
        if found is None or found.__class__.__module__ != "retarget.ui":
            raise RuntimeError("The entry did not construct the real retarget UI")
        if found.isVisible():
            raise RuntimeError("An entry displayed a tool window")
        return found

    try:
        if list(rt.objects):
            raise RuntimeError("Entry QA requires a fresh empty disposable batch scene")
        initial = scene()
        source = rt.Point(name="RetargetParentQA_Source", pos=rt.Point3(3, 5, 7))
        created.append(source)
        unrelated = rt.Point(name="RetargetParentQA_Unrelated", pos=rt.Point3(-7, 2, 1))
        created.append(unrelated)
        unrelated.isNodeHidden = True
        baseline = scene()
        sys.path[:] = [str(root)] + [p for p in sys.path if p != str(root)]
        importlib.import_module("retarget")
        for name in ("host", "session", "model", "solver", "preset", "matching", "ui", "launcher"):
            importlib.import_module("retarget." + name)
        report["moduleOriginsAfterImport"] = origins()
        if scene() != baseline:
            raise RuntimeError("Importing the parent component changed the scene")
        report["checks"].append("plain parent package, UI and host imports leave scene state unchanged")
        from PySide6 import QtWidgets
        for owner in (QtWidgets.QWidget, QtWidgets.QDialog):
            for method in ("show", "raise_", "activateWindow"):
                original = getattr(owner, method)
                originals.append((owner, method, original))
                def suppressed(widget, _method=method, _owner=owner.__name__):
                    report["suppressedQtCalls"].append({"method": _owner + "." + _method,
                                                       "widget": type(widget).__name__})
                setattr(owner, method, suppressed)
        for route in ("MaxScript", "MaxScript", "Python", "Python"):
            if route == "MaxScript":
                rt.fileIn(str(root / "LX_Retarget.ms"), quiet=True)
            else:
                rt.python.ExecuteFile(str(root / "bridge/open_retarget.py"))
            opened = current_window()
            if window is None:
                window = opened
                session = opened.session
            elif opened is not window or opened.session is not session:
                raise RuntimeError("Repeating a parent entry replaced the window or Session")
            if scene() != baseline:
                raise RuntimeError("Opening a parent entry changed the private scene")
            package = sys.modules["retarget"]
            bootstrap = Path(package._entry_bootstrap_file).resolve()
            if bootstrap != (root / "bridge/open_retarget.py").resolve():
                raise RuntimeError("The public entry resolved a different bootstrap")
            report["routes"].append({"route": route, "windowId": id(opened), "sessionId": id(session),
                                     "bootstrap": str(bootstrap), "shown": opened.isVisible()})
            report["moduleOrigins"] = origins()
        report["checks"].append("real parent .ms and Python entries each run twice with one real hidden UI and Session")
        rt.select(source)
        session.capture("source", include_children=False)
        before_hide = scene()
        session.visibility("hide_source")
        if not bool(source.isNodeHidden):
            raise RuntimeError("The close restoration fixture did not hide its captured source")
        if window.close() is False:
            raise RuntimeError("The entry window could not close safely")
        if scene() != before_hide or session._visibility:
            raise RuntimeError("Closing the entry failed to restore the captured visibility")
        report["checks"].append("real Session visibility mutation is restored by safe window close; unrelated node unchanged")
        rt.clearSelection()
        for node in reversed(created):
            rt.delete(node)
        created.clear()
        if scene() != initial:
            raise RuntimeError("Disposable entry QA failed to return to its initial scene")
        report["componentVersion"] = getattr(sys.modules["retarget"], "__version__", None)
        manifest = json.loads((root / ".lxtool/manifest.json").read_text(encoding="utf-8-sig"))
        report["parentPackageVersion"] = manifest["version"]
        report["checks"].append("no independent module loaded, no scene loaded/saved, disposable fixtures removed")
        report["status"] = "passed"
    except BaseException:
        report["error"] = traceback.format_exc()
    finally:
        try:
            if window is not None:
                window.session.close()
                window.close()
            for node in reversed(created):
                if rt.isValidNode(node):
                    rt.delete(node)
        except BaseException:
            report["cleanupError"] = traceback.format_exc()
            report["status"] = "failed"
        for owner, method, original in reversed(originals):
            setattr(owner, method, original)
        sys.path[:] = previous_path
        output = artifacts / "host_entry.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RETARGET_PARENT_HOST_ENTRY", report["status"], str(output))
    if report["status"] != "passed":
        raise RuntimeError(report.get("error", report.get("cleanupError", "parent entry failed")))


if __name__ == "__main__":
    main()
