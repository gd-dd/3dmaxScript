"""Read the active Unwrap UVW modifier and preview without changing the scene."""
from pymxs import runtime as rt
import qtmax
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)


def snapshot():
    if len(rt.selection)!=1:
        raise ValueError('请选择一个带有「Unwrap UVW」修改器的物件。')
    node = rt.selection[0]
    mod = rt.modPanel.getCurrentObject()
    if mod is None or rt.classOf(mod)!=rt.Unwrap_UVW or not any(m==mod for m in node.modifiers):
        raise ValueError('请进入当前物件的「Unwrap UVW」修改器。')
    api = mod.unwrap6
    count = int(api.numberPolygonsByNode(node))
    if count>120000:
        raise ValueError('修改器面数超过 12 万，请在较小的物件上对齐。')
    selected = [i for i, flag in enumerate(api.getSelectedPolygonsByNode(node),1) if flag]
    if not selected:
        raise ValueError('请在 UV 编辑器切到面模式，选中两个不同 UV 块上的面。')
    faces = {}
    for i in range(1,count+1):
        n = int(api.numberPointsInFaceByNode(i,node))
        if n>=3:
            face = tuple(int(api.getVertexIndexFromFaceByNode(i,k,node)) for k in range(1,n+1))
            if min(face)>0:
                faces[i] = face
    groups = solver['islands'](faces,selected)
    if len(groups)!=2:
        raise ValueError(f'检测到 {len(groups)} 个 UV 块。请在面模式选中两个不同块，不必选整块。')
    time = rt.currentTime
    coords = {}
    for i in {i for group in groups for face in group for i in face}:
        point = api.getVertexPositionByNode(time,i,node)
        coords[i] = (float(point.x),float(point.y),float(point.z))
    return (node,mod,time,groups,coords)


def write_result(snapshot_data, result):
    node,mod,time,groups,coords = snapshot_data
    current = snapshot()
    if current!=snapshot_data:
        raise ValueError('UV 选择、坐标或当前时间已变化，请重新读取后再应用。')
    if rt.theHold.Holding():
        raise ValueError('Max 正在编辑，结束当前操作后再试。')
    api=mod.unwrap6
    rt.theHold.Begin()
    try:
        for i,point in result.items():
            api.setVertexPosition2ByNode(time,i,rt.Point3(point.real,point.imag,coords[i][2]),True,False,node)
        rt.theHold.Accept('UV 重叠')
    except Exception:
        rt.theHold.Cancel()
        raise
    try:
        mod.unwrap.updateView()
    except RuntimeError:
        pass
    rt.redrawViews()


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.groups=[]
        self.setMinimumHeight(250)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),QColor('#f0f4ee'))
        if not self.groups:
            painter.setPen(QColor('#536450'))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'读取两个 UV 块后显示预览')
            return
        for side,groups in enumerate(self.groups):
            half=self.width()/2
            coords=[p for _,faces in groups for face in faces for p in face]
            x0=min(p.real for p in coords); x1=max(p.real for p in coords)
            y0=min(p.imag for p in coords); y1=max(p.imag for p in coords)
            scale=min(max(1,half-40)/max(x1-x0,1e-10),max(1,self.height()-72)/max(y1-y0,1e-10))
            painter.setPen(QColor('#273728'))
            painter.drawText(QPointF(side*half+14,23),('原始 UV','重叠预览')[side])
            center=complex((x0+x1)/2,(y0+y1)/2)
            for color,faces in groups:
                pen=QPen(QColor(color),1.25)
                if side and color=='#bd6325':
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                for face in faces:
                    points=QPolygonF([QPointF((side+.5)*half+(p-center).real*scale,
                        (self.height()+26)/2-(p-center).imag*scale) for p in face])
                    points.append(points[0])
                    painter.drawPolyline(points)


class Window(QDialog):
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowTitle('LX UV 重叠')
        self.resize(680,440)
        self.data=None
        self.plan=None
        self.swapped=False
        layout=QVBoxLayout(self)
        hint=QLabel('在 UV 编辑器的面模式中选中两个块上的面。A 保持原位，B 对齐到 A。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls=QHBoxLayout()
        layout.addLayout(controls)
        self.button(controls,'读取当前选区',self.read)
        self.swap=self.button(controls,'交换 A / B',self.swap_groups)
        self.mirror=QCheckBox('镜像 B')
        self.mirror.toggled.connect(self.rebuild)
        controls.addWidget(self.mirror)
        controls.addStretch()
        self.preview=Preview()
        layout.addWidget(self.preview,1)
        tuning=QHBoxLayout()
        layout.addLayout(tuning)
        self.phase_text=QLabel('相位 0')
        tuning.addWidget(self.phase_text)
        self.phase=QSlider(Qt.Orientation.Horizontal)
        self.phase.valueChanged.connect(self.render)
        tuning.addWidget(self.phase,1)
        self.reset=self.button(tuning,'恢复自动相位',lambda:self.phase.setValue(0))
        self.status=QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bottom=QHBoxLayout()
        layout.addLayout(bottom)
        legend=QLabel('绿色 A 固定　橙色 B 移动')
        bottom.addWidget(legend,1)
        self.button(bottom,'关闭',self.close)
        self.apply=self.button(bottom,'应用到 UV 编辑器',self.commit)
        self.read()

    def button(self,layout,title,action):
        widget=QPushButton(title)
        widget.clicked.connect(action)
        layout.addWidget(widget)
        return widget

    def failed(self,error):
        self.plan=None
        self.preview.groups=[]
        self.preview.update()
        self.apply.setEnabled(False)
        self.phase.setEnabled(False)
        self.reset.setEnabled(False)
        self.swap.setEnabled(self.data is not None)
        self.status.setText(str(error))

    def read(self):
        self.data=None
        self.swapped=False
        self.mirror.setEnabled(True)
        try:
            self.data=snapshot()
            self.rebuild()
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def swap_groups(self):
        self.swapped=not self.swapped
        self.rebuild()

    def rebuild(self,*_):
        if self.data is None:
            return
        try:
            groups=self.data[3]
            self.groups=groups[::-1] if self.swapped else groups
            self.points={i:complex(x,y) for i,(x,y,z) in self.data[4].items()}
            self.plan=solver['Alignment'](self.points,*self.groups,mirror=self.mirror.isChecked())
            self.phase.blockSignals(True)
            self.phase.setRange(-(self.plan.phases//2),(self.plan.phases-1)//2)
            self.phase.setValue(0)
            self.phase.blockSignals(False)
            self.swap.setEnabled(True)
            self.phase.setEnabled(True)
            self.reset.setEnabled(True)
            self.render()
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def render(self,*_):
        if self.plan is None:
            return
        phase=self.phase.value()
        self.phase_text.setText(f'相位 {phase:+d}' if phase else '相位 0')
        self.result,mode=self.plan.result(phase)
        a,b=self.groups
        def layer(color,faces,points):
            return color,[[points[i] for i in face] for face in faces]
        fixed=layer('#4b782b',a,self.points)
        self.preview.groups=[[fixed,layer('#bd6325',b,self.points)],[fixed,layer('#bd6325',b,self.result)]]
        self.preview.update()
        self.apply.setEnabled(True)
        self.status.setText(f'A 边界 {len(self.plan.a)} 点 · B 边界 {len(self.plan.b)} 点 · {mode}。拖动相位可更换对应位置。')

    def commit(self):
        try:
            write_result(self.data,self.result)
        except (RuntimeError,ValueError) as error:
            self.failed(error)
            return
        self.apply.setEnabled(False)
        self.phase.setEnabled(False)
        self.reset.setEnabled(False)
        self.swap.setEnabled(False)
        self.mirror.setEnabled(False)
        self.status.setText('已应用到 B。可用 Max 撤销，再读取选区重新调整。')


def show():
    window=Window(qtmax.GetQMaxMainWindow())
    window.show()
    return window
