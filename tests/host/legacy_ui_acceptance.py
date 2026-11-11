"""Disposable native rollouts rendered offscreen; original business harness follows."""
from pathlib import Path
import ctypes, json, os, re, traceback
from ctypes import wintypes as W
from pymxs import runtime as rt
ROOT=Path(globals().get('LEGACY_UI_ROOT', Path(__file__).resolve().parents[2])).resolve()
OUT=Path(globals().get('LEGACY_UI_OUT', ROOT.parent/'acceptance/legacy-ui-2026-11-12')).resolve()
OUT.mkdir(parents=True,exist_ok=True)
report=dict(pid=os.getpid(),scope='hidden Max; native PrintWindow; no user input',windows=[])
u=ctypes.WinDLL('user32');g=ctypes.WinDLL('gdi32')
u.GetClientRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
u.GetDC.restype=W.HDC;u.GetDC.argtypes=[W.HWND]
g.CreateCompatibleDC.restype=W.HDC;g.CreateCompatibleDC.argtypes=[W.HDC]
g.CreateCompatibleBitmap.restype=W.HBITMAP;g.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int]
g.SelectObject.restype=W.HANDLE;g.SelectObject.argtypes=[W.HDC,W.HANDLE]
u.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]
g.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.c_void_p,W.UINT]
g.DeleteObject.argtypes=[W.HANDLE];g.DeleteDC.argtypes=[W.HDC];u.ReleaseDC.argtypes=[W.HWND,W.HDC]
class Header(ctypes.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('image',W.DWORD),('x',W.LONG),('y',W.LONG),('used',W.DWORD),('important',W.DWORD)]
def render(roll,name):
    from PySide6.QtGui import QImage
    hwnd=int(roll.hwnd);rect=W.RECT();u.GetClientRect(hwnd,ctypes.byref(rect));w,h=rect.right,rect.bottom
    dc=u.GetDC(hwnd);mem=g.CreateCompatibleDC(dc);bm=g.CreateCompatibleBitmap(dc,w,h);old=g.SelectObject(mem,bm)
    try:
        assert u.PrintWindow(hwnd,mem,1),'PrintWindow failed'
        g.SelectObject(mem,old)
        header=Header(ctypes.sizeof(Header),w,-h,1,32,0,w*h*4,0,0,0,0);buf=ctypes.create_string_buffer(w*h*4)
        assert g.GetDIBits(dc,bm,0,h,buf,ctypes.byref(header),0)==h
        img=QImage(buf.raw,w,h,w*4,QImage.Format.Format_RGB32).copy()
        assert img.save(str(OUT/(name+'.png')))
    finally:g.SelectObject(mem,old);g.DeleteObject(bm);g.DeleteDC(mem);u.ReleaseDC(hwnd,dc)
    return [w,h]
rolls=[('动画烘焙工具.ms','AnimBakeRollout'),('保持位移建立父子.ms','ReparentBakeRollout'),('清理根骨骼.ms','RootBoneBakeRollout'),('按材质ID拆分模型.ms','MatIDSplitRollout'),('PMX导入.ms','PMXImportRollout'),('自定义公式关键帧.ms','CustomFormulaRollout')]
try:
    for name,roll in rolls:
        s=(ROOT/name).read_text('utf-8-sig').replace('getFilenamePath (getSourceFileName())','@"'+str(ROOT)+'\\"')
        s=s.replace('createDialog '+roll+' width:420','createDialog '+roll+' pos:[-32000,-32000] width:420')
        rt.execute(s);r=getattr(rt,roll)
        primary=r.btnApply if roll=='CustomFormulaRollout' else r.btnImport if roll=='PMXImportRollout' else r.btnExecute
        assert primary.Text, 'open handler did not initialize primary caption'
        assert r.lxHeader.Controls.Count==3, 'image/title/subtitle missing'
        assert rt.execute('('+roll+'.lxHeader.Controls.Item 0).Image != undefined'), 'user image missing'
        record=dict(name=name,size=render(r,roll),controls=[])
        if roll=='RootBoneBakeRollout':assert rt.getDialogSize(r).y<=440
        if roll=='CustomFormulaRollout':assert rt.getDialogSize(r).y==290
        for control in r.controls:
            try:
                if not control.visible:continue
                p=control.pos;size=[int(control.width),int(control.height)]
                assert p.x>=0 and p.y>=0 and p.x+size[0]<=420 and p.y+size[1]<=int(rt.getDialogSize(r).y),(str(control),p,size)
                record['controls'].append(dict(name=str(control),pos=[p.x,p.y],size=size))
            except AttributeError:pass
        if roll=='CustomFormulaRollout':
            r.edtFormula.text='v + sin(90)';r.btnHelp.PerformClick()
            assert r.lblEx3.visible and r.edtFormula.text=='v + sin(90)'
            record['expanded']=render(r,roll+'-reference')
            assert rt.getDialogSize(r).y<=440
            r.btnHelp.PerformClick();assert not r.lblEx3.visible and r.edtFormula.text=='v + sin(90)'
            record['collapsePreservesFormula']=True
        report['windows'].append(record);rt.destroyDialog(r)
    report['ok']=True
except Exception:
    report.update(ok=False,error=traceback.format_exc())
    try:rt.destroyDialog(r)
    except Exception:pass
(OUT/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
# Execute unmodified business logic with output-directory redirection only.
if not (globals().get("LEGACY_UI_ONLY", False) or os.environ.get("LX_LEGACY_UI_ONLY")):
    source=(ROOT/'tests/host/legacy_business.py').read_text('utf-8-sig')
    source=source.replace("OUT=ROOT.parent/'acceptance/legacy-six-2026-11-10'","OUT=ROOT.parent/'acceptance/legacy-ui-2026-11-12/business'")
    exec(compile(source,str(ROOT/'tests/host/legacy_business.py'),'exec'),{'__file__':str(ROOT/'tests/host/legacy_business.py')})
