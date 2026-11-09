import os,sys,types
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r))
time=types.SimpleNamespace(start=types.SimpleNamespace(frame=0),end=types.SimpleNamespace(frame=100))
sys.modules['pymxs']=types.SimpleNamespace(runtime=types.SimpleNamespace(animationRange=time))
from PySide6.QtWidgets import QApplication
app=QApplication([])
from PySide6.QtGui import QFontDatabase
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
from ribbon import plugin
w=plugin.RibbonWindow();w.show();app.processEvents()
assert w.end.value()==100
assert len(w.fields)==5
w.grab().save(str(r/'tests/ribbon-panel.png'))
w.close()
print('PASS offscreen widget construction and frame range')

