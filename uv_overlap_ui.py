"""Read the active Unwrap UVW modifier and preview without changing the scene."""
from pymxs import runtime as rt
import qtmax
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


def selected_vertices(mod, node, mode):
    api = mod.unwrap6
    if mode == 1:
        return {i for i,flag in enumerate(api.getSelectedVerticesByNode(node),1) if flag}
    if not any(api.getSelectedEdgesByNode(node)):
        return set()
    original = rt.copy(api.getSelectedVerticesByNode(node))
    rt.theHold.Suspend()
    try:
        mod.unwrap2.edgeToVertSelect()
        return {i for i,flag in enumerate(api.getSelectedVerticesByNode(node),1) if flag}
    finally:
        try:
            api.selectVerticesByNode(original,node)
        finally:
            rt.theHold.Resume()


def snapshot():
    if len(rt.selection)!=1:
        raise ValueError('请选择一个带有「Unwrap UVW」修改器的物件，在同一个 UV 编辑器选两个块。')
    node = rt.selection[0]
    mod = rt.modPanel.getCurrentObject()
    if mod is None or rt.classOf(mod)!=rt.Unwrap_UVW or not any(m==mod for m in node.modifiers):
        raise ValueError('请进入当前物件的「Unwrap UVW」修改器。')
    api = mod.unwrap6
    count = int(api.numberPolygonsByNode(node))
    if count>120000:
        raise ValueError('修改器面数超过 12 万，请在较小的物件上对齐。')
    mode = mod.unwrap2.getTVSubObjectMode()
    if mode not in (1,2,3):
        raise ValueError('请在 UV 编辑器使用点、边或面选择，从两个 UV 块各选任意一部分。')
    vertices, selected = set(), []
    if mode == 3:
        selected = [i for i,flag in enumerate(api.getSelectedPolygonsByNode(node),1) if flag]
    else:
        vertices = selected_vertices(mod,node,mode)
    if not selected and not vertices:
        raise ValueError('请从两个不同 UV 块各选任意点、边或面。可以只选一部分。')
    faces = {}
    for i in range(1,count+1):
        n = int(api.numberPointsInFaceByNode(i,node))
        if n>=3:
            face = tuple(int(api.getVertexIndexFromFaceByNode(i,k,node)) for k in range(1,n+1))
            if min(face)>0:
                faces[i] = face
    seeds = selected or [i for i,face in faces.items() if any(j in vertices for j in face)]
    groups = solver['islands'](faces,seeds)
    if len(groups)!=2:
        raise ValueError(f'检测到 {len(groups)} 个 UV 块。请只在两个不同块上各选一些点、边或面。')
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
        raise ValueError('UV 块、坐标或当前时间已变化，请重新读取后再应用。')
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


class Window(QDialog):
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowTitle('LX UV 重叠')
        self.resize(960,640)
        self.data=None
        self.plan=None
        self.swapped=False
        self.applied=False
        self.edge_pairs=[]
        self.pair_history=[]
        self.pending_edge=None
        self.match_notice=''
        layout=QVBoxLayout(self)
        hint=QLabel('从两个 UV 块各选任意点、边或面，再读取选区。绿色 A 固定，橙色 B 对齐到 A。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls=QHBoxLayout()
        layout.addLayout(controls)
        self.button(controls,'读取当前选区',self.read)
        self.swap=self.button(controls,'交换 A / B',self.swap_groups)
        self.mirror=QCheckBox('镜像 B')
        self.mirror.toggled.connect(lambda _:self.rebuild(preserve_holes=True))
        controls.addWidget(self.mirror)
        self.reverse=QCheckBox('反向连端点')
        self.reverse.setToolTip('交换每对边的端点方向，桥接预览会一起更新')
        self.reverse.toggled.connect(self.reverse_pair_direction)
        controls.addWidget(self.reverse)
        controls.addStretch()
        self.show_bridges=QCheckBox('显示桥接')
        self.show_bridges.setChecked(True)
        self.show_bridges.toggled.connect(self.render)
        controls.addWidget(self.show_bridges)
        self.preview=Preview()
        self.preview.edgePicked.connect(self.pick_edge)
        layout.addWidget(self.preview,1)
        pairs=QHBoxLayout()
        self.pair_hint=QLabel()
        self.pair_hint.setWordWrap(True)
        pairs.addWidget(self.pair_hint,1)
        self.remove_pair=self.button(pairs,'撤回配对',self.undo_pair)
        self.clear_pairs=self.button(pairs,'清除配对',self.reset_pairs)
        layout.addLayout(pairs)
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
        legend=QLabel('桥接仅用于预览 · 应用后可以撤销')
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
        self.preview.set_editable(False)
        self.preview.clear_scene()
        self.pair_hint.clear()
        self.remove_pair.setEnabled(False)
        self.clear_pairs.setEnabled(False)
        self.reverse.setEnabled(False)
        self.apply.setEnabled(False)
        self.phase.setEnabled(False)
        self.reset.setEnabled(False)
        self.swap.setEnabled(self.data is not None)
        self.holes.hide()
        self.status.setText(str(error))

    def read(self):
        self.data=None
        self.plan=None
        self.swapped=False
        self.applied=False
        self.edge_pairs.clear()
        self.pair_history.clear()
        self.pending_edge=None
        self.match_notice=''
        self.reverse.setChecked(False)
        self.mirror.setEnabled(True)
        self.show_bridges.setEnabled(True)
        try:
            self.data=snapshot()
            self.rebuild()
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def swap_groups(self):
        self.swapped=not self.swapped
        self.edge_pairs=[(b,a) for a,b in self.edge_pairs]
        self.pair_history=[[(b,a) for a,b in pairs] for pairs in self.pair_history]
        self.pending_edge=None
        self.match_notice=''
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
            self.preview.set_editable(True)
            self.setup_holes(preserve_holes)
            self.swap.setEnabled(True)
            self.phase.setEnabled(True)
            self.reset.setEnabled(True)
            self.render()
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def pick_edge(self, side, index):
        if self.plan is None or self.applied:
            return
        if side not in ('a','b') or not 0 <= index < len(getattr(self.plan,side)):
            return
        clicked=(side,index)
        self.match_notice=''
        if self.pending_edge is None or self.pending_edge[0]==side:
            self.pending_edge=None if self.pending_edge==clicked else clicked
        else:
            other=self.pending_edge[1]
            pair=(index,other) if side=='a' else (other,index)
            pairs=[(a,b) for a,b in self.edge_pairs if a!=pair[0] and b!=pair[1]]
            try:
                self.plan.validate_edge_pairs([*pairs,pair],flip_pairs=self.reverse.isChecked())
            except ValueError as error:
                self.match_notice=str(error)
            else:
                self.pair_history.append(self.edge_pairs)
                self.edge_pairs=[*pairs,pair]
                self.pending_edge=None
        self.render()

    def reverse_pair_direction(self):
        self.match_notice=''
        self.render()

    def undo_pair(self):
        self.match_notice=''
        if self.pending_edge is not None:
            self.pending_edge=None
        elif self.pair_history:
            self.edge_pairs=self.pair_history.pop()
        self.render()

    def reset_pairs(self):
        self.match_notice=''
        self.pending_edge=None
        self.edge_pairs.clear()
        self.pair_history.clear()
        self.reverse.setChecked(False)
        self.render()

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

    def preview_links(self, phase):
        outer=self.plan.boundary
        direction=outer.direction
        if self.edge_pairs:
            if self.reverse.isChecked():
                direction=-direction
            return [(a,b,direction) for a,b in self.edge_pairs]
        if not self.plan.equal:
            return []
        count=len(self.plan.b)
        start=(outer.start+phase)%count
        step=max(1,(count+7)//8)
        return [((start+direction*i+(direction-1)//2)%count,i,direction)
                for i in range(0,count,step)]

    def update_preview(self, phase, result):
        a,b=self.groups
        def layer(faces,points):
            return [[points[i] for i in face] for face in faces]
        labels=[(p,color,f'{name}{i+1}')
                for points,color,name in ((self.plan.a_centers,'#4b782b','A'),
                                          (self.plan.b_centers,'#bd6325','B'))
                for i,p in enumerate(points)]
        self.preview.set_scene(layer(a,self.points),layer(b,self.points),
                               [self.points[i] for i in self.plan.a],
                               [self.points[i] for i in self.plan.b],
                               layer(b,result) if result else None,
                               self.preview_links(phase),pending=self.pending_edge,labels=labels,
                               show_bridges=self.show_bridges.isChecked())

    def render(self,*_):
        if self.plan is None or self.applied:
            return
        phase=self.phase.value()
        manual=bool(self.edge_pairs)
        self.phase.setEnabled(not manual)
        self.reset.setEnabled(not manual)
        self.reverse.setEnabled(manual)
        self.phase_text.setText('手动配对' if manual else f'相位 {phase:+d}' if phase else '相位 0')
        self.remove_pair.setEnabled(bool(self.pending_edge or self.pair_history))
        self.clear_pairs.setEnabled(bool(self.pending_edge or manual))
        needs_pair=not self.plan.equal or self.plan.ambiguous
        if self.pending_edge:
            side,index=self.pending_edge
            other='B' if side=='a' else 'A'
            guide=f'已选 {side.upper()} 的第 {index+1} 条边。请点 {other} 的对应边。'
        elif manual:
            guide=f'已配对 {len(self.edge_pairs)} 组。可继续点选边，或反向连接端点。'
        elif not self.plan.equal:
            guide='外圈边数不同。请在 A、B 各点一条对应的外边，添加临时桥接。'
        elif self.plan.ambiguous:
            guide='检测到多种相近的匹配。请在 A、B 各点一条对应的外边确认。'
        else:
            guide='已自动匹配。点选 A、B 的对应边可以手动调整。'
        self.pair_hint.setText(self.match_notice or guide)
        overrides={}
        for a in range(self.hole_table.rowCount()):
            choice=self.hole_table.cellWidget(a,1).currentData()
            if choice!=-1:
                overrides[a]=None if choice==-2 else choice
        try:
            self.result,mode=self.plan.result(phase,overrides,edge_pairs=self.edge_pairs,
                                              flip_pairs=self.reverse.isChecked())
        except ValueError as error:
            self.result=None
            self.update_preview(phase,None)
            self.apply.setEnabled(False)
            self.status.setText(str(error))
            return
        pairs=self.plan.matched
        for a in range(self.hole_table.rowCount()):
            choice=self.hole_table.cellWidget(a,1)
            choice.setItemText(0,f'自动（B{pairs[a]+1}）' if a in pairs and a not in overrides else '自动')
        self.hole_summary.setText(f'A 有 {len(self.plan.a_holes)} 孔 · B 有 {len(self.plan.b_holes)} 孔 · 已配对 {len(pairs)} 组。未配对的孔随 B 一起移动。')
        self.update_preview(phase,self.result)
        self.apply.setEnabled(not self.pending_edge and (manual or not needs_pair))
        self.status.setText(f'A 外圈 {len(self.plan.a)} 边 · B 外圈 {len(self.plan.b)} 边 · {mode}')

    def commit(self):
        if not self.apply.isEnabled():
            return
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
        self.reverse.setEnabled(False)
        self.show_bridges.setEnabled(False)
        self.hole_table.setEnabled(False)
        self.applied=True
        self.preview.set_editable(False)
        self.remove_pair.setEnabled(False)
        self.clear_pairs.setEnabled(False)
        self.pair_hint.setText('预览已应用。如需继续编辑，请重新读取选区。')
        self.status.setText('已应用到 B。可用 Max 撤销。')


def show():
    window=Window(qtmax.GetQMaxMainWindow())
    window.show()
    return window
