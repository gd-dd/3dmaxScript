"""Offscreen ribbon workflow, reachability and scale checks; no Max scene access.

Set QT_SCALE_FACTOR before launching. All artifacts and runtime folders live on E.
"""
import os
import sys
import types
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('RIBBON_UI_OUTPUT','E:/project/LXTools/acceptance/ribbon-ui-2026-11-12'))
OUT.mkdir(parents=True,exist_ok=True)
for key,folder in [('TEMP','temp'),('TMP','temp'),('APPDATA','profile'),('LOCALAPPDATA','local-profile')]:
    path=OUT/folder; path.mkdir(exist_ok=True); os.environ[key]=str(path)
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
time=types.SimpleNamespace(start=types.SimpleNamespace(frame=0),end=types.SimpleNamespace(frame=100))
sys.modules['pymxs']=types.SimpleNamespace(runtime=types.SimpleNamespace(animationRange=time,isValidNode=lambda n:True))
from PySide6 import QtCore, QtGui, QtWidgets
app=QtWidgets.QApplication([])
QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
from ribbon import plugin

scale=os.environ.get('QT_SCALE_FACTOR','1')
result={'scale':scale,'scenarios':[]}

def flush():
    for _ in range(4): app.processEvents()

def wheel(target):
    event=QtGui.QWheelEvent(QtCore.QPointF(5,5),QtCore.QPointF(5,5),QtCore.QPoint(),QtCore.QPoint(0,-120),QtCore.Qt.NoButton,QtCore.Qt.NoModifier,QtCore.Qt.NoScrollPhase,False)
    app.sendEvent(target,event); flush()

def inside(w,child):
    rect=QtCore.QRect(child.mapTo(w,QtCore.QPoint(0,0)),child.size())
    assert w.rect().contains(rect), (child.objectName(),rect,w.rect())
    assert child.isVisible(),child.objectName()

def assert_reachable(w,control):
    w.config_scroll.ensureWidgetVisible(control,0,4); flush()
    bottom=control.mapTo(w.config_scroll.widget(),QtCore.QPoint(0,control.height())).y()
    w.config_scroll.ensureVisible(0,bottom,0,4); flush()
    v=w.config_scroll.viewport()
    rect=QtCore.QRect(control.mapTo(v,QtCore.QPoint()),control.size())
    assert v.rect().contains(rect), (control.accessibleName(),rect,v.rect())
    assert w.config_scroll.horizontalScrollBar().maximum()==0

w=plugin.RibbonWindow(); w.show(); flush()
assert w.end.value()==100 and len(w.fields)==5
assert len(w.findChildren(QtWidgets.QPushButton))==2
expected={'gravity':(980,-100000,100000),'inertia':(.95,0,1),'mass':(1,.01,1000),'influence':(1,0,3),'damping':(3,0,50)}
for k,(value,lo,hi) in expected.items():
    c=w.fields[k]
    assert (c.value(),c.minimum(),c.maximum())==(value,lo,hi)
    assert c.decimals()==3
# A failed read must clear the previously valid chain.
nodes=[types.SimpleNamespace(name='Ribbon_'+str(i)+'_非常长的骨骼名称'*6) for i in range(80)]
original_read=plugin.chain_from_selection
plugin.chain_from_selection=lambda:nodes
w.read(); assert len(w.chain)==80 and w.chain_list.count()==80
w.fields['mass'].setValue(2.25); w.fields['influence'].setValue(1.8)
w.start.setValue(-10); w.end.setValue(130)
for width,height in [(320,480),(390,560),(720,640)]:
    w.resize(width,height); flush()
    assert w.size()==QtCore.QSize(width,height),(w.size(),w.minimumSizeHint())
    for tab in range(w.pages.count()):
        w.pages.setCurrentIndex(tab); flush()
        inside(w,w.read_button); inside(w,w.run); inside(w,w.status)
        assert w.fields['mass'].value()==2.25 and w.fields['influence'].value()==1.8
        if tab==0:
            w.chain_list.scrollToBottom(); flush()
            assert w.chain_list.verticalScrollBar().value()>0
            last=w.chain_list.visualItemRect(w.chain_list.item(79))
            assert last.intersects(w.chain_list.viewport().rect())
            w.chain_list.scrollToTop(); flush()
            wheel(w.chain_list.viewport())
            assert w.chain_list.verticalScrollBar().value()>0
            w.chain_list.scrollToTop(); flush()
        elif tab==1:
            for expanded in [False,True]:
                w.advanced_button.setChecked(expanded); flush()
                assert w.advanced_panel.isVisible()==expanded
                fields=list(w.fields.values()) if expanded else [w.fields[k] for k in ('gravity','inertia','mass')]
                for control in fields+[w.start,w.end]: assert_reachable(w,control)
                # Wheel over a spin box scrolls the page without changing its value.
                bar=w.config_scroll.verticalScrollBar()
                for focused in (False,True):
                    if focused: w.fields['gravity'].setFocus()
                    else: w.run.setFocus()
                    flush(); bar.setValue(0)
                    before=w.fields['gravity'].value()
                    wheel(w.fields['gravity'])
                    assert w.fields['gravity'].value()==before
                    if bar.maximum()>0: assert bar.value()>0
                w.config_scroll.verticalScrollBar().setValue(w.config_scroll.verticalScrollBar().maximum()); flush()
                w.grab().save(str(OUT/f'ui-{scale}-{width}x{height}-config-{expanded}-bottom.png'))
                w.config_scroll.verticalScrollBar().setValue(0); flush()
                w.grab().save(str(OUT/f'ui-{scale}-{width}x{height}-config-{expanded}.png'))
        elif tab==2:
            text=w.preview.toPlainText()
            assert '2.25' in text and '1.8' in text and '-10 → 130' in text
            assert '不修改场景' in w.pages.widget(2).findChildren(QtWidgets.QLabel)[0].text()
        w.grab().save(str(OUT/f'ui-{scale}-{width}x{height}-tab{tab}.png'))
        result['scenarios'].append({'size':[width,height],'tab':tab,'actual':[w.width(),w.height()],'primaryVisible':True})
# The config preview must never invoke bake.
calls=[]
def fake_bake(chain,start,end,settings,substeps=8):
    calls.append((chain,start,end,settings)); return end-start+1
plugin.bake=fake_bake
w.pages.setCurrentIndex(2); flush(); assert not calls
w.solve()
assert len(calls)==1 and calls[0][0]==nodes and calls[0][1:3]==(-10,130)
assert calls[0][3]=={k:c.value() for k,c in w.fields.items()}
assert '完成：已烘焙 141 帧' in w.status.text() and w.run.isEnabled()
def fail_read(): raise ValueError('QA：请选择普通骨骼单链')
plugin.chain_from_selection=fail_read
w.read(); assert w.chain==[] and w.chain_list.count()==0
w.solve(); assert '失败' in w.status.text() and '先读取' in w.status.text() and w.run.isEnabled()
def fail_bake(*args,**kwargs): raise RuntimeError('长错误消息_'*120)
plugin.chain_from_selection=lambda:nodes
plugin.bake=fail_bake
w.read(); w.solve(); flush()
assert '长错误消息_'*120 in w.status.text() and w.run.isEnabled()
inside(w,w.status); inside(w,w.run)
assert w.status.verticalScrollBar().maximum()>0
for text_box in (w.preview,w.status):
    text_box.setPlainText('滚动检查\n'*120)
    text_box.verticalScrollBar().setValue(0); flush()
    wheel(text_box.viewport())
    assert text_box.verticalScrollBar().value()>0
w.status.setText('解算失败：'+'长错误消息_'*120)
w.grab().save(str(OUT/f'ui-{scale}-long-error.png'))
w.close()
# show() reuses the same live instance and preserves workflow settings.
sys.modules['qtmax']=types.SimpleNamespace(GetQMaxMainWindow=lambda:None)
plugin.show(); first=plugin.window; first.fields['mass'].setValue(4.25); first.pages.setCurrentIndex(2)
first.close(); second=plugin.show(); flush()
assert first is second and second.fields['mass'].value()==4.25 and second.pages.currentIndex()==2
second.close()
result.update(ok=True,checks=['reachability','long-chain-scroll','advanced-retains-values','focused-and-unfocused-wheel-scroll-without-edit','list-and-text-wheel-scroll','read-failure-clears-chain','solve-args-and-error-feedback','preview-does-not-bake','reopen-retains-values'])
(OUT/f'report-{scale}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'scale':scale,'ok':True,'scenarios':len(result['scenarios'])}))
