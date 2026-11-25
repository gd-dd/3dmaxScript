"""Read the active Unwrap UVW modifier and preview without changing the scene."""
from pymxs import runtime as rt
import qtmax
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


def selected_border(mod, node):
    api = mod.unwrap6
    mode = mod.unwrap2.getTVSubObjectMode()
    if mode == 1:
        return {i for i,flag in enumerate(api.getSelectedVerticesByNode(node),1) if flag}, None
    if mode != 2:
        raise ValueError('请在 UV 编辑器切到边模式，给两个 UV 块各选一整圈外边界。')
    edges = sum(bool(flag) for flag in api.getSelectedEdgesByNode(node))
    if not edges:
        return set(), 0
    original = rt.copy(api.getSelectedVerticesByNode(node))
    rt.theHold.Suspend()
    try:
        mod.unwrap2.edgeToVertSelect()
        vertices = {i for i,flag in enumerate(api.getSelectedVerticesByNode(node),1) if flag}
    finally:
        try:
            api.selectVerticesByNode(original,node)
        finally:
            rt.theHold.Resume()
    return vertices, edges


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
    vertices, edge_count = selected_border(mod,node)
    if not vertices:
        raise ValueError('请在 UV 编辑器中给两个 UV 块各选一整圈外边界。')
    faces = {}
    for i in range(1,count+1):
        n = int(api.numberPointsInFaceByNode(i,node))
        if n>=3:
            face = tuple(int(api.getVertexIndexFromFaceByNode(i,k,node)) for k in range(1,n+1))
            if min(face)>0:
                faces[i] = face
    seeds = [i for i,face in faces.items() if any(j in vertices for j in face)]
    groups = solver['islands'](faces,seeds)
    if len(groups)!=2:
        raise ValueError(f'检测到 {len(groups)} 个 UV 块。请在两个不同块上各选一整圈外边界。')
    time = rt.currentTime
    coords = {}
    for i in {i for group in groups for face in group for i in face}:
        point = api.getVertexPositionByNode(time,i,node)
        coords[i] = (float(point.x),float(point.y),float(point.z))
    solver['boundary_selection'](groups,vertices,{i:complex(x,y) for i,(x,y,z) in coords.items()},edge_count)
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
        self.labels=[]
        self.setMinimumHeight(224)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),QColor('#f0f4ee'))
        if not self.groups:
            painter.setPen(QColor('#536450'))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'读取两圈外边界后显示预览')
            return
        original, aligned = self.groups
        panels = [('原始 A',0,.25,[original[0]]), ('原始 B',.25,.25,[original[1]]),
                  ('重叠预览',.5,.5,aligned)]
        for title,left,width,groups in panels:
            x = left*self.width()
            span = width*self.width()
            coords=[p for _,faces in groups for face in faces for p in face]
            x0=min(p.real for p in coords); x1=max(p.real for p in coords)
            y0=min(p.imag for p in coords); y1=max(p.imag for p in coords)
            scale=min(max(1,span-34)/max(x1-x0,1e-10),max(1,self.height()-72)/max(y1-y0,1e-10))
            painter.setPen(QColor('#273728'))
            painter.drawText(QPointF(x+14,23),title)
            if left:
                painter.setPen(QColor('#d5ded2'))
                painter.drawLine(QPointF(x,10),QPointF(x,self.height()-10))
            center=complex((x0+x1)/2,(y0+y1)/2)
            def project(p):
                return QPointF(x+span/2+(p-center).real*scale,
                               (self.height()+26)/2-(p-center).imag*scale)
            for color,faces in groups:
                pen=QPen(QColor(color),1.25)
                if len(groups)==2 and color=='#bd6325':
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                for face in faces:
                    points=QPolygonF([project(p) for p in face])
                    points.append(points[0])
                    painter.drawPolyline(points)
            if len(groups)==1:
                for point, color, label in self.labels:
                    if color != groups[0][0]:
                        continue
                    center_px = project(point)
                    box = painter.fontMetrics().boundingRect(label).adjusted(-5,-2,5,2)
                    box.moveCenter(center_px.toPoint())
                    painter.fillRect(box,QColor('#fbfcf9'))
                    painter.setPen(QColor(color))
                    painter.drawText(box,Qt.AlignmentFlag.AlignCenter,label)


class Window(QDialog):
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowTitle('LX UV 重叠')
        self.resize(760,580)
        self.data=None
        self.plan=None
        self.swapped=False
        layout=QVBoxLayout(self)
        hint=QLabel('在 UV 编辑器的边模式中，给两个 UV 块各选一整圈外边界。也可在点模式选中整圈外边界点。孔洞会自动配对。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls=QHBoxLayout()
        layout.addLayout(controls)
        self.button(controls,'读取当前选区',self.read)
        self.swap=self.button(controls,'交换 A / B',self.swap_groups)
        self.mirror=QCheckBox('镜像 B')
        self.mirror.toggled.connect(lambda _:self.rebuild(preserve_holes=True))
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
        self.holes=QWidget()
        hole_layout=QVBoxLayout(self.holes)
        hole_layout.setContentsMargins(0,0,0,0)
        hole_layout.addWidget(QLabel('孔洞配对 · 按左侧预览编号选择，默认自动'))
        self.hole_table=QTableWidget(0,2)
        self.hole_table.setHorizontalHeaderLabels(['A 固定孔','B 对应孔'])
        self.hole_table.horizontalHeader().setStretchLastSection(True)
        self.hole_table.verticalHeader().hide()
        self.hole_table.verticalHeader().setDefaultSectionSize(30)
        self.hole_table.setMaximumHeight(160)
        hole_layout.addWidget(self.hole_table)
        self.hole_summary=QLabel()
        self.hole_summary.setWordWrap(True)
        hole_layout.addWidget(self.hole_summary)
        layout.addWidget(self.holes)
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
        self.holes.hide()
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

    def rebuild(self,preserve_holes=False):
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
            self.setup_holes(preserve_holes)
            self.swap.setEnabled(True)
            self.phase.setEnabled(True)
            self.reset.setEnabled(True)
            self.render()
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def setup_holes(self,preserve_holes):
        previous = ([self.hole_table.cellWidget(a,1).currentData()
                     for a in range(self.hole_table.rowCount())] if preserve_holes else [])
        a_count=len(self.plan.a_holes)
        b_count=len(self.plan.b_holes)
        self.holes.setVisible(bool(a_count or b_count))
        self.hole_table.setVisible(bool(a_count and b_count))
        self.hole_table.setEnabled(True)
        self.hole_table.setRowCount(0)
        if not a_count or not b_count:
            return
        self.hole_table.setRowCount(a_count)
        header = self.hole_table.horizontalHeader().sizeHint().height()
        self.hole_table.setFixedHeight(min(160,header+30*a_count+2*self.hole_table.frameWidth()))
        for a in range(a_count):
            item=QTableWidgetItem(f'A{a+1}')
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.hole_table.setItem(a,0,item)
            choice=QComboBox()
            choice.addItem('自动',-1)
            choice.addItem('不配对',-2)
            for b in range(b_count):
                choice.addItem(f'B{b+1}',b)
            if a < len(previous):
                choice.setCurrentIndex(choice.findData(previous[a]))
            choice.currentIndexChanged.connect(lambda _,row=a:self.change_hole(row))
            self.hole_table.setCellWidget(a,1,choice)

    def change_hole(self, row):
        chosen=self.hole_table.cellWidget(row,1).currentData()
        if chosen>=0:
            for a in range(self.hole_table.rowCount()):
                other=self.hole_table.cellWidget(a,1)
                if a!=row and other.currentData()==chosen:
                    other.blockSignals(True)
                    other.setCurrentIndex(0)
                    other.blockSignals(False)
        self.render()

    def render(self,*_):
        if self.plan is None:
            return
        phase=self.phase.value()
        self.phase_text.setText(f'相位 {phase:+d}' if phase else '相位 0')
        overrides={}
        for a in range(self.hole_table.rowCount()):
            choice=self.hole_table.cellWidget(a,1).currentData()
            if choice!=-1:
                overrides[a]=None if choice==-2 else choice
        try:
            self.result,mode=self.plan.result(phase,overrides)
        except ValueError as error:
            self.apply.setEnabled(False)
            self.status.setText(str(error))
            return
        pairs=self.plan.matched
        for a in range(self.hole_table.rowCount()):
            choice=self.hole_table.cellWidget(a,1)
            choice.setItemText(0,f'自动（B{pairs[a]+1}）' if a in pairs and a not in overrides else '自动')
        self.hole_summary.setText(f'A 有 {len(self.plan.a_holes)} 孔 · B 有 {len(self.plan.b_holes)} 孔 · 已配对 {len(pairs)} 组。未配对的孔随 B 一起移动。')
        a,b=self.groups
        def layer(color,faces,points):
            return color,[[points[i] for i in face] for face in faces]
        fixed=layer('#4b782b',a,self.points)
        self.preview.groups=[[fixed,layer('#bd6325',b,self.points)],[fixed,layer('#bd6325',b,self.result)]]
        self.preview.labels=[(p,color,f'{name}{i+1}')
                             for points,color,name in ((self.plan.a_centers,'#4b782b','A'),
                                                       (self.plan.b_centers,'#bd6325','B'))
                             for i,p in enumerate(points)]
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
        self.hole_table.setEnabled(False)
        self.status.setText('已应用到 B。可用 Max 撤销，再读取选区重新调整。')


def show():
    window=Window(qtmax.GetQMaxMainWindow())
    window.show()
    return window
