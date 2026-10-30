"""Development-only harness for a freshly launched test Max. Not packaged."""
import json,runpy,traceback
from pathlib import Path
from PySide6.QtCore import QTimer
import qtmax
ROOT=Path(__file__).resolve().parents[2]
main=qtmax.GetQMaxMainWindow();main.showMaximized()
timer=QTimer(main);timer.setInterval(250)
def tick():
    job=ROOT/'tests/host/job.json'
    if not job.exists():return
    task=json.loads(job.read_text('utf-8-sig'));job.unlink()
    try:
        if task['script'] not in ('max_ui_test.py','legacy_ui_test.py','run_in_max.py'):raise ValueError('unknown test')
        runpy.run_path(str(ROOT/'tests/host'/task['script']))
    except Exception:
        (ROOT/'tests/host/harness-report.json').write_text(json.dumps({'ok':False,'error':traceback.format_exc()}),'utf-8')
timer.timeout.connect(tick);timer.start();main._lx_test_timer=timer
