"""Replay verified historical tests against the parent-owned retarget package.

The historical repository is read only. Only module names and virtual filenames
change in memory; no historical file is edited or imported as lxmaxretarget.
Run explicitly with the E-drive Python and -B after the source copy is ready.
"""
from pathlib import Path
import hashlib
import importlib
import io
import json
import os
import sys
import traceback
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT.parent / "LXMaxRetarget"
ARTIFACTS = ROOT / "tests/retarget/artifacts"
CASES = (
    ("test_core.py", 36),
    ("test_resampling.py", 23),
    ("test_preset_v2.py", 6),
    ("test_session.py", 22),
    ("test_session_resampling.py", 4),
    ("test_host_biped_balance.py", 9),
    ("test_ui.py", 33),
    ("test_chain_editor_layout.py", 4),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_origins():
    result = {}
    for name, module in list(sys.modules.items()):
        if name == "retarget" or name.startswith("retarget."):
            origin = getattr(module, "__file__", None)
            if origin:
                resolved = Path(origin).resolve()
                if not resolved.is_relative_to((ROOT / "retarget").resolve()):
                    raise RuntimeError("retarget was imported from another root: " + str(resolved))
                result[name] = str(resolved)
    return result


def main():
    if ROOT != Path("E:/project/LXTools/3dmaxScript").resolve():
        raise RuntimeError("Run this local replay only from the canonical parent repository")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_DISABLE_SHADER_DISK_CACHE"] = "1"
    for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        directory = ARTIFACTS / "replay_environment" / key.lower()
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(directory)
    # The historical tests compute evidence relative to their virtual __file__.
    (ROOT / "retarget/evidence").mkdir(parents=True, exist_ok=True)
    previous_path = list(sys.path)
    previous_aliases = {}
    original_hashes = {}
    log = io.StringIO()
    report = {
        "status": "failed", "scope": "137 verified tests replayed against parent retarget",
        "parentRoot": str(ROOT), "historicalTestsRoot": str(HISTORY / "tests"),
        "historicalFilesModified": False, "tests": [], "checks": [],
        "bytecodeWritesDisabled": True, "qtPlatform": "offscreen",
        "environment": {key: os.environ[key] for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE")},
        "maxStarted": False, "providerOrPublicInstallationVerified": False,
    }
    result = None
    try:
        sys.path[:] = [str(ROOT)] + [p for p in sys.path if p != str(ROOT)]
        package = importlib.import_module("retarget")
        if Path(package.__file__).resolve().parent != (ROOT / "retarget").resolve():
            raise RuntimeError("The parent repository's retarget package must be imported")
        report["packageFile"] = str(Path(package.__file__).resolve())
        report["componentVersion"] = getattr(package, "__version__", None)
        suite = unittest.TestSuite()
        for filename, expected_count in CASES:
            source = HISTORY / "tests" / filename
            original_hashes[str(source)] = digest(source)
            code = source.read_text(encoding="utf-8-sig").replace("lxmaxretarget", "retarget")
            virtual = ROOT / "retarget/tests" / filename
            module_name = "_retarget_verified_" + source.stem
            previous_aliases[module_name] = sys.modules.get(module_name)
            module = types.ModuleType(module_name)
            module.__file__ = str(virtual)
            module.__package__ = ""
            sys.modules[module_name] = module
            exec(compile(code, str(virtual), "exec"), module.__dict__)
            # Several original tests insert their own root; retain the parent as
            # the first search path without modifying those historical files.
            sys.path[:] = [str(ROOT)] + [p for p in sys.path if p != str(ROOT)]
            if source.stem == "test_session":
                previous_aliases["test_session"] = sys.modules.get("test_session")
                sys.modules["test_session"] = module
            tests = unittest.defaultTestLoader.loadTestsFromModule(module)
            count = tests.countTestCases()
            if count != expected_count:
                raise RuntimeError(filename + " changed its verified case count: " + str(count))
            report["tests"].append({"source": str(source), "sourceSha256": original_hashes[str(source)],
                                    "virtualFile": str(virtual), "count": count})
            suite.addTests(tests)
        if suite.countTestCases() != 137:
            raise RuntimeError("The verified replay must contain exactly 137 cases")
        report["checks"].append("eight historical modules compiled only in memory with virtual child filenames")
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report["testsRun"] = result.testsRun
        report["failures"] = [{"test": str(test), "traceback": details} for test, details in result.failures]
        report["errors"] = [{"test": str(test), "traceback": details} for test, details in result.errors]
        report["moduleOrigins"] = package_origins()
        if not result.wasSuccessful() or result.testsRun != 137:
            raise RuntimeError("The parent retarget replay did not pass all 137 cases")
        report["checks"].append("all 137 core, session and offscreen UI cases passed against parent modules")
        report["status"] = "passed"
    except BaseException:
        report["error"] = traceback.format_exc()
    finally:
        # Restore the shared alias and private module names even if a test failed.
        for name, previous in previous_aliases.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        sys.path[:] = previous_path
        report["testSessionAliasRestored"] = True
        changed = [name for name, before in original_hashes.items() if digest(Path(name)) != before]
        report["historicalFilesModified"] = bool(changed)
        if changed:
            report["status"] = "failed"
            report["historicalChangedFiles"] = changed
        (ARTIFACTS / "replay.log").write_text(log.getvalue(), encoding="utf-8")
        (ARTIFACTS / "replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RETARGET_VERIFIED_REPLAY", report["status"], report.get("testsRun", 0), str(ARTIFACTS / "replay.json"))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
