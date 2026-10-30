"""Development-only harness for a freshly launched test Max. Not packaged."""
import json,runpy,traceback,os
from pathlib import Path
from PySide6.QtCore import QTimer
import qtmax
ROOT=Path(__file__).resolve().parents[2]
main=qtmax.GetQMaxMainWindow();main.showMaximized()
timer=QTimer(main);timer.setInterval(250)
def tick():
    job=ROOT/('tests/host/job-%d.json'%os.getpid())
    if not job.exists():job=ROOT/'tests/host/job.json'
    if not job.exists():return
    task=json.loads(job.read_text('utf-8-sig'));job.unlink()
    try:
        if task['script'] not in ('max_ui_test.py','legacy_ui_test.py','run_in_max.py','workflow_test.py','workflow_regression.py','symmetry_test.py'):raise ValueError('unknown test')
        runpy.run_path(str(ROOT/'tests/host'/task['script']))
    except Exception:
        (ROOT/'tests/host/harness-report.json').write_text(json.dumps({'ok':False,'error':traceback.format_exc()}),'utf-8')
timer.timeout.connect(tick);timer.start();main._lx_test_timer=timer
(ROOT/('tests/host/harness-%d-report.json'%os.getpid())).write_text(json.dumps({'pid':os.getpid(),'ready':True}),'utf-8')
