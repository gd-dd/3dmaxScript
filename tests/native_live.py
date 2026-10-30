"""Exercise the real shelf loader, stdio provider and a tool-launched Max."""
import sys,json,time,traceback,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHELF=ROOT.parent/'LXTools'
sys.path.insert(0,str(SHELF/'src'))
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QTabWidget
from PySide6.QtCore import QTimer
from native_panels import NativePanelHandle
app=QApplication([]);parent=QWidget();parent.resize(1100,1200);layout=QVBoxLayout(parent)
manifest=json.loads((ROOT/'.lxtool/manifest.json').read_text('utf-8-sig'))
tool=dict(manifest,id='repo-1342543761',root=ROOT,panelData=json.loads((ROOT/'.lxtool/panel.json').read_text('utf-8')))
config=tempfile.TemporaryDirectory(prefix='lx-rig-test-')
handle=NativePanelHandle(tool,Path(config.name),parent);panel=handle.widget;layout.addWidget(panel)
report={'checks':[]};started=time.monotonic();stage=0
def finish(error=None):
    report['ok']=error is None
    if error:report['error']=str(error)
    report['status']=panel.status.text();report['sessions']=list(panel.sessions.values())
    (ROOT/'tests/native-live-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    handle.shutdown();app.quit()
def inspect_done(data):
    report['checks'].append('scene.inspect round trip')
    panel.rig.load_scene(data)
    panel.rig.call('bone.create',{'name':'LXLiveTestBone','start':[0,0,0],'end':[0,0,10]},created)
def created(data):
    report['checks'].append('bone.create round trip')
    panel.rig.call('scene.inspect',{},loaded)
def loaded(data):
    try:
        assert any(n['name'].startswith('LXLiveTestBone') for n in data['nodes'])
        panel.rig.load_scene(data)
        for tabs in panel.findChildren(QTabWidget):
            if tabs.count()==2:tabs.setCurrentIndex(1)
        parent.show();app.processEvents();panel.grab().save(str(ROOT/'tests/native-live-preview.png'));parent.hide()
        report['checks'].append('real Max data rendered in shelf native loader')
        finish()
    except Exception as e:finish(traceback.format_exc())
def tick():
    global stage
    if time.monotonic()-started>300:finish('Timed out: '+panel.rig.notice.text());return
    if stage==0:
        stage=1
        if '--reuse' in sys.argv:panel.command('hello')
        else:panel.set_path('E:/Ruanjian/3DSmax/3ds Max 2026/3dsmax.exe');panel.launch()
    elif stage==1 and panel.active_id and panel.sessions.get(panel.active_id,{}).get('state')=='ready':
        stage=2;report['checks'].append('managed Max launched and connected')
        panel.rig.call('scene.inspect',{},inspect_done)
    elif stage==2 and not panel.rig.busy and panel.rig.notice.text().startswith(('Max','命令','场景','操作')):
        finish(panel.rig.notice.text())
timer=QTimer();timer.timeout.connect(tick);timer.start(1000)
sys.exit(app.exec())
