"""Open all six original Max tools and check their restyled real controls."""
import json,traceback,sys
from pathlib import Path
from pymxs import runtime as rt
from PySide6.QtCore import QTimer
ROOT=Path(__file__).resolve().parents[2]
TOOLS=[('动画烘焙工具.ms','AnimBakeRollout','btnExecute'),('保持位移建立父子.ms','ReparentBakeRollout','btnExecute'),('按材质ID拆分模型.ms','MatIDSplitRollout','btnExecute'),('清理根骨骼.ms','RootBoneBakeRollout','btnExecute'),('自定义公式关键帧.ms','CustomFormulaRollout','btnApply'),('PMX导入.ms','PMXImportRollout','btnImport')]
report={'passed':[],'errors':[]}
index=0
def save():
    report['ok']=not report['errors']
    (ROOT/'tests/host/legacy-ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
def next_tool():
    global index
    if index>=len(TOOLS):save();return
    file,roll,button=TOOLS[index];index+=1
    try:
        rt.fileIn(str(ROOT/file),quiet=True)
        report['legacyRoot']=str(rt.LXLegacyRoot)
        report['iconExists']=bool(rt.doesFileExist(str(rt.LXLegacyRoot)+'.lxtool\\icon.png'))
        obj=getattr(rt,roll)
        assert int(obj.hwnd)>0
        assert int(obj.lxHeader.Controls.Count)==3
        assert rt.execute(roll+'.lxHeader.Controls.Item[0].Image != undefined'), 'header image missing'
        primary=getattr(obj,button);assert str(primary.Text)
        assert int(primary.BackColor.G)==148
        if roll=='PMXImportRollout':assert not primary.Enabled
        if roll in ('AnimBakeRollout','ReparentBakeRollout','RootBoneBakeRollout'):
            obj.spnStart.value=-999
            obj.btnGetRange.PerformClick()
            assert int(obj.spnStart.value)==int(rt.animationRange.start.frame)
            report['passed'].append(file+' range button event works')
        report['passed'].append(file+' opens with image, theme and action')
        def capture():
            try:
                bitmap=rt.windows.snapshot(int(obj.hwnd))
                bitmap.filename=str(ROOT/'tests'/('legacy-'+roll+'.png'));rt.save(bitmap);rt.close(bitmap)
                # Reloading should close and replace the previous window cleanly.
                rt.fileIn(str(ROOT/file),quiet=True)
                assert int(getattr(rt,roll).hwnd)>0
                rt.destroyDialog(getattr(rt,roll))
                report['passed'].append(file+' reopens and closes')
            except Exception:report['errors'].append({'tool':file,'error':traceback.format_exc()})
            save();QTimer.singleShot(100,next_tool)
        QTimer.singleShot(500,capture)
    except Exception:
        report['errors'].append({'tool':file,'error':traceback.format_exc()});save();QTimer.singleShot(100,next_tool)
QTimer.singleShot(0,next_tool)
