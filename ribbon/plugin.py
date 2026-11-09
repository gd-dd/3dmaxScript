from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
from .solver import Solver
from rig.theme import STYLE
from pymxs import runtime as rt
import pymxs
from PySide6 import QtWidgets, QtCore, QtGui

def chain_from_selection():
    if rt.selection.count!=1: raise ValueError('请选择一条骨骼链的根骨骼')
    chain=[]; node=rt.selection[0]
    while True:
        if str(rt.classOf(node))!='BoneGeometry': raise ValueError('仅支持普通骨骼，不支持辅助物、CAT 或 Biped')
        chain.append(node)
        children=list(node.children)
        if len(children)>1: raise ValueError('骨骼链存在分叉，请选择单链根骨骼')
        if not children: break
        node=children[0]
    if len(chain)<2: raise ValueError('至少需要两节骨骼，最后一节作为末端定位')
    return chain

def vec(p): return (float(p.x),float(p.y),float(p.z))
def point(v): return rt.Point3(*v)

def bake(chain,start,end,settings,substeps=8):
    if end<=start: raise ValueError('结束帧必须大于开始帧')
    for n in chain:
        if not rt.isValidNode(n): raise ValueError('骨骼已删除，请重新读取')
        if rt.classOf(rt.getPropertyController(n.controller,rt.Name('rotation'))) not in (rt.Euler_XYZ,rt.TCB_Rotation,rt.Bezier_Rotation):
            raise ValueError('骨骼旋转含约束或列表控制器，请先转换为普通旋转控制器')
    if substeps<1: raise ValueError('子步数必须为正')
    if any(chain[i].parent!=chain[i-1] for i in range(1,len(chain))): raise ValueError('骨骼层级已改变，请重新读取')
    samples=[]
    for f in range(start,end+1):
        with pymxs.attime(f): samples.append([rt.copy(n.transform) for n in chain])
    solver=Solver([vec(m.row4) for m in samples[0]],**settings)
    results=[list(solver.p)]
    dt=1.0/(float(rt.frameRate)*substeps)
    for index in range(1,len(samples)):
        a=vec(samples[index-1][0].row4); b=vec(samples[index][0].row4)
        for s in range(substeps):
            root=tuple(x+(y-x)*(s+1)/substeps for x,y in zip(a,b))
            positions=solver.step(root,dt)
        results.append(positions)
    failure=None
    with pymxs.undo(True,'LX 飘带解算'):
        try:
            with pymxs.animate(True):
                for index,positions in enumerate(results):
                    with pymxs.attime(start+index):
                        for j,node in enumerate(chain[:-1]):
                            x=rt.normalize(point(positions[j+1])-point(positions[j]))
                            z=samples[index][j].row3
                            if abs(float(rt.dot(rt.normalize(z),x)))>0.99: z=rt.Point3(0,1,0)
                            if abs(float(rt.dot(rt.normalize(z),x)))>0.99: z=rt.Point3(0,0,1)
                            y=rt.normalize(rt.cross(z,x)); z=rt.normalize(rt.cross(x,y))
                            target=rt.matrix3(x,y,z,point(positions[j]))
                            node.transform=target
                        end_tm=rt.copy(samples[index][-1])
                        end_tm.row4=point(positions[-1])
                        chain[-1].transform=end_tm
        except Exception as error:
            failure=error
            raise
    if failure is not None: raise failure
    rt.redrawViews()
    return len(results)

class RibbonWindow(QtWidgets.QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.chain=[]
        self.setWindowTitle('LX 飘带 · 骨骼动力学'); self.resize(390,560)
        self.setStyleSheet(STYLE)
        layout=QtWidgets.QVBoxLayout(self)
        icon=QtWidgets.QLabel(); icon.setPixmap(QtGui.QPixmap(str(ROOT.parent/'.lxtool/icon.png')).scaled(56,56,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)); layout.addWidget(icon)
        title=QtWidgets.QLabel('飘带解算'); title.setStyleSheet('font-size:26px;color:#507522;font-weight:bold'); layout.addWidget(title)
        tip=QtWidgets.QLabel('选择根骨骼，读取单链，再烘焙动画。\n最后一节骨骼用于末端定位，不单独解算。'); tip.setWordWrap(True); layout.addWidget(tip)
        read=QtWidgets.QPushButton('读取选中的骨骼链'); read.clicked.connect(self.read); layout.addWidget(read)
        self.info=QtWidgets.QLabel('尚未读取骨骼'); layout.addWidget(self.info)
        box=QtWidgets.QGroupBox('动力学参数'); form=QtWidgets.QFormLayout(box); layout.addWidget(box); self.fields={}
        for key,label,value,lo,hi,tip in [('gravity','重力（场景单位/秒²）',980,-100000,100000,'正数向下，负数向上；厘米场景通常使用 980'),('inertia','惯性',0.95,0,1,'越大越保留世界空间运动；越小越跟随根骨骼'),('mass','质量',1,0.01,1000,'越大越不容易被阻尼减速；不会改变重力加速度'),('influence','长度影响系数',1,0,3,'零表示统一阻尼；增大后长骨段保留更多运动'),('damping','阻尼',3,0,50,'越大越快停止摆动')]:
            control=QtWidgets.QDoubleSpinBox(); control.setRange(lo,hi); control.setDecimals(3); control.setValue(value); control.setToolTip(tip); form.addRow(label,control); self.fields[key]=control
        group=QtWidgets.QGroupBox('烘焙范围'); form=QtWidgets.QFormLayout(group); layout.addWidget(group)
        self.start=QtWidgets.QSpinBox(); self.end=QtWidgets.QSpinBox()
        for c in (self.start,self.end): c.setRange(-100000,100000)
        self.start.setValue(int(rt.animationRange.start.frame)); self.end.setValue(int(rt.animationRange.end.frame))
        form.addRow('开始帧',self.start); form.addRow('结束帧',self.end)
        for control in [*self.fields.values(),self.start,self.end]: control.installEventFilter(self)
        self.run=QtWidgets.QPushButton('解算并烘焙'); self.run.clicked.connect(self.solve); layout.addWidget(self.run)
        self.status=QtWidgets.QLabel('烘焙写入变换关键帧，可用 Max 撤销。\n运行前请保存场景；暂不包含碰撞。'); self.status.setWordWrap(True); layout.addWidget(self.status)
    def eventFilter(self,obj,event):
        if event.type()==QtCore.QEvent.Wheel: event.ignore(); return True
        return super().eventFilter(obj,event)
    def read(self):
        try:
            self.chain=chain_from_selection(); self.info.setText('已读取 %d 节：%s'%(len(self.chain),self.chain[0].name))
        except Exception as e:
            self.chain=[]; self.info.setText('读取失败，请重新选择单链根骨骼'); self.status.setText(str(e))
    def solve(self):
        self.run.setEnabled(False)
        try:
            if not self.chain: raise ValueError('请先读取骨骼链')
            count=bake(self.chain,self.start.value(),self.end.value(),{k:v.value() for k,v in self.fields.items()})
            self.status.setText('完成：已烘焙 %d 帧。可用 Max 撤销恢复。'%count)
        except Exception as e: self.status.setText('解算失败：'+str(e))
        finally: self.run.setEnabled(True)

def show():
    global window
    import qtmax
    from shiboken6 import isValid
    if 'window' in globals() and isValid(window):
        window.show(); window.raise_(); return window
    window=RibbonWindow(qtmax.GetQMaxMainWindow()); window.show()
if __name__=='__main__': show()






