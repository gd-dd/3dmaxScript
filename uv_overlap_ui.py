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
        self.resize(980,680)
        self.data=None
        self.plan=None
        self.swapped=False
        self.applied=False
        self.contour_edges={}
        self.reversed_pairs=set()
        self.edge_history={}
        self.contour_phases={}
        self.reviewed=set()
        self.pending_edge=None
        self.match_notice=''
        self.initial_focus=True
        self.unconfirmed=[]
        self.unmatched_a=[]
        self.unmatched_b=[]
        self.result=None

        layout=QVBoxLayout(self)
        hint=QLabel('在 UV 编辑器里从两个块各选任意点、边或面。A 固定，B 对齐到 A。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls=QHBoxLayout()
        layout.addLayout(controls)
        self.button(controls,'读取当前选区',self.read)
        self.swap=self.button(controls,'交换 A / B',self.swap_groups)
        self.mirror=QCheckBox('镜像 B')
        self.mirror.toggled.connect(self.mirror_changed)
        controls.addWidget(self.mirror)
        self.reverse=QCheckBox('反向连端点')
        self.reverse.toggled.connect(self.reverse_pair_direction)
        controls.addWidget(self.reverse)
        controls.addStretch()
        self.show_bridges=QCheckBox('显示桥接')
        self.show_bridges.setChecked(True)
        self.show_bridges.toggled.connect(self.refresh_preview)
        controls.addWidget(self.show_bridges)

        viewing=QHBoxLayout()
        viewing.addWidget(QLabel('查看轮廓'))
        self.contour_view=QComboBox()
        self.contour_view.setAccessibleName('查看轮廓')
        self.contour_view.addItem('完整 UV 块',None)
        self.contour_view.currentIndexChanged.connect(self.contour_view_changed)
        viewing.addWidget(self.contour_view,1)
        layout.addLayout(viewing)
        self.preview=Preview()
        self.preview.edgePicked.connect(self.pick_edge)
        layout.addWidget(self.preview,1)

        actions=QHBoxLayout()
        self.pair_hint=QLabel()
        self.pair_hint.setWordWrap(True)
        actions.addWidget(self.pair_hint,1)
        self.accept_contour=self.button(actions,'确认当前匹配',self.confirm_current_contour)
        self.remove_pair=self.button(actions,'撤回边配对',self.undo_pair)
        self.clear_pairs=self.button(actions,'清除边配对',self.reset_pairs)
        layout.addLayout(actions)
        tuning=QHBoxLayout()
        self.phase_text=QLabel('相位')
        tuning.addWidget(self.phase_text)
        self.phase=QSlider(Qt.Orientation.Horizontal)
        self.phase.valueChanged.connect(self.phase_changed)
        tuning.addWidget(self.phase,1)
        self.reset=self.button(tuning,'恢复自动相位',lambda:self.phase.setValue(0))
        layout.addLayout(tuning)

        self.contour_table=QTableWidget(0,3)
        self.contour_table.setHorizontalHeaderLabels(['A 固定轮廓','B 对应轮廓','匹配状态'])
        self.contour_table.horizontalHeader().setStretchLastSection(True)
        self.contour_table.verticalHeader().hide()
        self.contour_table.verticalHeader().setDefaultSectionSize(28)
        self.contour_table.setColumnWidth(0,132)
        self.contour_table.setColumnWidth(1,228)
        self.contour_table.cellClicked.connect(self.focus_table_contour)
        layout.addWidget(self.contour_table)
        self.force_unmatched=QCheckBox('将未配对轮廓按内部顶点处理')
        self.force_unmatched.toggled.connect(self.render)
        layout.addWidget(self.force_unmatched)
        self.status=QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bottom=QHBoxLayout()
        bottom.addWidget(QLabel('按住拖动预览块，松开复位'),1)
        self.button(bottom,'关闭',self.close)
        self.apply=self.button(bottom,'应用到 UV 编辑器',self.commit)
        layout.addLayout(bottom)
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
        self.contour_table.setRowCount(0)
        self.contour_table.hide()
        self.force_unmatched.hide()
        self.contour_view.setEnabled(False)
        for widget in (self.accept_contour,self.remove_pair,self.clear_pairs,self.reverse,
                       self.apply,self.phase,self.reset):
            widget.setEnabled(False)
        self.swap.setEnabled(False)
        self.status.setText(str(error))

    def read(self):
        self.data=None
        self.plan=None
        self.swapped=False
        self.applied=False
        self.contour_edges.clear()
        self.reversed_pairs.clear()
        self.edge_history.clear()
        self.contour_phases.clear()
        self.reviewed.clear()
        self.pending_edge=None
        self.match_notice=''
        self.initial_focus=True
        self.force_unmatched.setEnabled(True)
        self.force_unmatched.setChecked(False)
        self.mirror.setEnabled(True)
        try:
            self.data=snapshot()
            self.rebuild({},None)
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def contour_choices(self):
        choices={}
        for i in range(self.contour_table.rowCount()):
            choice=self.contour_table.cellWidget(i,1).currentData()
            if choice!=-1:
                choices[i]=None if choice==-2 else choice
        return choices

    def swap_groups(self):
        if self.plan is None:
            return
        selected=self.contour_view.currentData()
        previous=self.contour_choices()
        explicit={} if not previous else {i:None for i in range(len(self.plan.contours_b))}
        if previous:
            explicit.update({b:a for a,b in self.plan.matched.items()})
        self.swapped=not self.swapped
        self.contour_edges={(b,a):[(j,i) for i,j in edges] for (a,b),edges in self.contour_edges.items()}
        self.reversed_pairs={(b,a) for a,b in self.reversed_pairs}
        self.edge_history.clear()
        self.contour_phases.clear()
        self.reviewed.clear()
        self.pending_edge=None
        self.match_notice=''
        self.clear_force_choice()
        self.rebuild(explicit,selected[::-1] if selected else None)

    def mirror_changed(self,*_):
        if self.plan is None:
            return
        self.pending_edge=None
        self.match_notice=''
        self.reviewed.clear()
        self.clear_force_choice()
        self.rebuild(self.contour_choices(),self.contour_view.currentData())

    def rebuild(self,choices,selection):
        if self.data is None:
            return
        try:
            self.groups=self.data[3][::-1] if self.swapped else self.data[3]
            self.points={i:complex(x,y) for i,(x,y,z) in self.data[4].items()}
            self.plan=solver['Alignment'](self.points,*self.groups,mirror=self.mirror.isChecked())
            self.display_b=dict(self.points)
            if self.mirror.isChecked():
                values=[self.points[i].imag for i in self.plan.nb]
                center=min(values)+max(values)
                self.display_b.update({i:self.points[i].conjugate()+1j*center for i in self.plan.nb})
            self.setup_contours(choices)
            self.contour_view.setEnabled(True)
            self.swap.setEnabled(True)
            self.render(selection=selection)
        except (RuntimeError,ValueError) as error:
            self.failed(error)

    def setup_contours(self,choices):
        self.contour_table.show()
        self.contour_table.setEnabled(True)
        self.contour_table.setRowCount(0)
        self.contour_table.setRowCount(len(self.plan.contours_a))
        header=self.contour_table.horizontalHeader().sizeHint().height()
        count=len(self.plan.contours_a)
        self.contour_table.setFixedHeight(min(145,header+28*count+2*self.contour_table.frameWidth()))
        for a,loop in enumerate(self.plan.contours_a):
            label=QTableWidgetItem(f'A{a+1} · {len(loop)} 边')
            label.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
            self.contour_table.setItem(a,0,label)
            choice=QComboBox()
            choice.addItem('自动',-1)
            choice.addItem('不配对',-2)
            for b,outline in enumerate(self.plan.contours_b):
                choice.addItem(f'B{b+1} · {len(outline)} 边',b)
            value=choices.get(a,-1)
            choice.setCurrentIndex(max(0,choice.findData(-2 if value is None else value)))
            choice.currentIndexChanged.connect(lambda _,row=a:self.change_contour(row))
            self.contour_table.setCellWidget(a,1,choice)
            status=QTableWidgetItem()
            status.setFlags(label.flags())
            self.contour_table.setItem(a,2,status)

    def change_contour(self,a):
        choice=self.contour_table.cellWidget(a,1).currentData()
        if choice>=0:
            for row in range(self.contour_table.rowCount()):
                other=self.contour_table.cellWidget(row,1)
                if row!=a and other.currentData()==choice:
                    other.blockSignals(True)
                    other.setCurrentIndex(0)
                    other.blockSignals(False)
        self.pending_edge=None
        self.match_notice=''
        self.reviewed.clear()
        self.clear_force_choice()
        self.render(selection=(a,choice if choice>=0 else None))

    def clear_force_choice(self):
        self.force_unmatched.blockSignals(True)
        self.force_unmatched.setChecked(False)
        self.force_unmatched.blockSignals(False)

    def focus_table_contour(self,a,_):
        self.select_contour((a,self.plan.matched.get(a)))

    def select_contour(self,focus):
        for i in range(self.contour_view.count()):
            if self.contour_view.itemData(i)==focus:
                self.contour_view.setCurrentIndex(i)
                return

    def contour_view_changed(self,*_):
        self.pending_edge=None
        self.match_notice=''
        if self.plan is not None:
            self.update_controls()
            self.refresh_preview()

    def active_pair(self):
        focus=self.contour_view.currentData()
        return focus if focus and None not in focus else None

    def validate_current_edges(self,pair,edges,reverse=None):
        flip=pair in self.reversed_pairs if reverse is None else reverse
        self.plan.validate_contour_edges(*pair,edges,flip)

    def pick_edge(self,side,index):
        pair=self.active_pair()
        if self.plan is None or self.applied or pair not in self.plan.contour_boundaries:
            return
        loops=self.plan.contours_a if side=='a' else self.plan.contours_b
        if side not in ('a','b') or not 0<=index<len(loops[pair[0 if side=='a' else 1]]):
            return
        clicked=(side,index)
        self.match_notice=''
        if self.pending_edge is None or self.pending_edge[0]==side:
            self.pending_edge=None if self.pending_edge==clicked else clicked
        else:
            other=self.pending_edge[1]
            edge=(index,other) if side=='a' else (other,index)
            old=self.contour_edges.get(pair,[])
            edges=[(a,b) for a,b in old if a!=edge[0] and b!=edge[1]]+[edge]
            try:
                self.validate_current_edges(pair,edges)
            except ValueError as error:
                self.match_notice=str(error)
            else:
                self.edge_history.setdefault(pair,[]).append(old)
                self.contour_edges[pair]=edges
                self.pending_edge=None
                self.reviewed.discard(pair)
        self.render()

    def reverse_pair_direction(self,checked):
        pair=self.active_pair()
        if pair is None or not self.contour_edges.get(pair):
            return
        self.match_notice=''
        try:
            self.validate_current_edges(pair,self.contour_edges[pair],checked)
        except ValueError as error:
            self.match_notice=str(error)
        else:
            if checked:
                self.reversed_pairs.add(pair)
            else:
                self.reversed_pairs.discard(pair)
        self.render()

    def phase_changed(self,phase):
        pair=self.active_pair()
        if pair is not None:
            self.contour_phases[pair]=phase
            self.reviewed.discard(pair)
            self.render()

    def confirm_current_contour(self):
        pair=self.active_pair()
        if pair:
            self.reviewed.add(pair)
            self.render()

    def undo_pair(self):
        self.match_notice=''
        pair=self.active_pair()
        if self.pending_edge is not None:
            self.pending_edge=None
        elif pair and self.edge_history.get(pair):
            old=self.edge_history[pair].pop()
            if old:
                self.contour_edges[pair]=old
            else:
                self.contour_edges.pop(pair,None)
                self.reversed_pairs.discard(pair)
        self.render()

    def reset_pairs(self):
        self.match_notice=''
        self.pending_edge=None
        pair=self.active_pair()
        self.contour_edges.pop(pair,None)
        self.edge_history.pop(pair,None)
        self.reversed_pairs.discard(pair)
        self.reviewed.discard(pair)
        self.render()

    def refresh_contour_views(self,selection):
        focus=selection if selection is not None else self.contour_view.currentData()
        pairs=self.plan.matched
        values=[]
        for a in range(len(self.plan.contours_a)):
            b=pairs.get(a)
            label=f'A{a+1} ↔ B{b+1}' if b is not None else f'A{a+1} · 未配对'
            values.append((label,(a,b)))
        for b in self.unmatched_b:
            values.append((f'B{b+1} · 未配对',(None,b)))
        if self.initial_focus:
            needs=(self.unconfirmed+[item for _,item in values if None in item])
            focus=needs[0] if needs else values[0][1] if len(values)==1 else None
            self.initial_focus=False
        self.contour_view.blockSignals(True)
        try:
            self.contour_view.clear()
            self.contour_view.addItem('完整 UV 块',None)
            selected=0
            for label,pair in values:
                self.contour_view.addItem(label,pair)
                if focus and (pair==focus or
                    (focus[0] is not None and focus[0]==pair[0]) or
                    (focus[0] is None and focus[1]==pair[1])):
                    selected=self.contour_view.count()-1
            self.contour_view.setCurrentIndex(selected)
        finally:
            self.contour_view.blockSignals(False)

    def update_controls(self):
        focus=self.contour_view.currentData()
        pair=self.active_pair()
        boundary=self.plan.contour_boundaries.get(pair)
        manual=bool(self.contour_edges.get(pair))
        enabled=not self.applied
        self.phase.blockSignals(True)
        if boundary:
            count=boundary.phases
            self.phase.setRange(-(count//2),(count-1)//2)
            self.phase.setValue(self.contour_phases.get(pair,0))
        else:
            self.phase.setRange(0,0)
        self.phase.blockSignals(False)
        self.phase.setEnabled(enabled and boundary is not None and not manual)
        self.reset.setEnabled(self.phase.isEnabled())
        self.phase_text.setText('手动配边' if manual else f'相位 {self.phase.value():+d}' if boundary else '相位')
        self.reverse.blockSignals(True)
        self.reverse.setChecked(pair in self.reversed_pairs)
        self.reverse.blockSignals(False)
        self.reverse.setEnabled(enabled and manual)
        self.remove_pair.setEnabled(enabled and bool(self.pending_edge or self.edge_history.get(pair)))
        self.clear_pairs.setEnabled(enabled and bool(self.pending_edge or manual))
        self.accept_contour.setEnabled(enabled and pair in self.unconfirmed and not self.pending_edge)
        if self.applied:
            guide='已应用到 B。仍可查看轮廓和拖动预览。'
        elif self.pending_edge:
            side,index=self.pending_edge
            guide=f"已选 {side.upper()} 第 {index+1} 边。请点 {'B' if side=='a' else 'A'} 的对应边。"
        elif not focus:
            guide='选择一对轮廓，可单独查看和点击对应边。'
        elif not pair:
            guide='此轮廓尚未配对。可在列表中更换对应轮廓，或按内部顶点处理。'
        elif pair in self.unconfirmed:
            reason='边数不同' if not boundary.equal else '有多种相近的匹配'
            guide=f'{reason}。可点击两侧对应边，或确认当前预览的匹配。'
        else:
            guide='点选两侧对应边可调整配对。'
        self.pair_hint.setText(self.match_notice or guide)
        self.apply.setEnabled(enabled and self.result is not None and not self.unconfirmed
                              and not self.pending_edge and (self.force_unmatched.isChecked()
                              or not (self.unmatched_a or self.unmatched_b)))

    def refresh_preview(self,*_):
        if self.plan is None:
            return
        focus=self.contour_view.currentData()
        a_title='A 固定块'
        b_title='B 镜像移动块' if self.mirror.isChecked() else 'B 移动块'
        show=self.show_bridges.isChecked()
        editable=self.active_pair() in self.plan.contour_boundaries and not self.applied
        self.preview.set_editable(editable)
        if focus is None:
            def layers(faces,points):
                return [[points[i] for i in face] for face in faces]
            outline_a=layers(self.plan.contours_a,self.points)
            outline_b=layers(self.plan.contours_b,self.display_b)
            labels=[(loop[0],color,f'{side}{i+1}')
                    for loops,side,color in ((outline_a,'A','#4b782b'),(outline_b,'B','#bd6325'))
                    for i,loop in enumerate(loops)]
            a,b=self.groups
            self.preview.set_scene(layers(a,self.points),layers(b,self.display_b),[],[],
                                   layers(b,self.result) if self.result else None,(),
                                   titles=(a_title,b_title,'重叠预览'),labels=labels,show_bridges=show,
                                   overview_loops=(outline_a,outline_b))
            return
        a,b=focus
        a_ids=self.plan.contours_a[a] if a is not None else []
        b_ids=self.plan.contours_b[b] if b is not None else []
        a_loop=[self.points[i] for i in a_ids]
        b_loop=[self.display_b[i] for i in b_ids]
        moved=[self.result[i] for i in b_ids] if self.result else []
        pair=self.active_pair()
        boundary=self.plan.contour_boundaries.get(pair)
        edges=self.contour_edges.get(pair,[])
        links=[]
        point_links=[]
        if edges and boundary:
            direction=-boundary.direction if pair in self.reversed_pairs else boundary.direction
            links=[(i,j,direction) for i,j in edges]
        elif boundary and moved:
            for i in range(0,len(b_loop),max(1,(len(b_loop)+7)//8)):
                j=(i+1)%len(b_loop)
                point_links.append(((moved[i],moved[j]),(b_loop[i],b_loop[j])))
        titles=(f'A{a+1} 固定轮廓' if a is not None else 'A 无对应轮廓',
                f"B{b+1} {'镜像' if self.mirror.isChecked() else '移动'}轮廓" if b is not None else 'B 无对应轮廓',
                '轮廓重叠预览')
        self.preview.set_scene([a_loop] if a_loop else [],[b_loop] if b_loop else [],a_loop,b_loop,
                               [moved] if moved else None,links,pending=self.pending_edge,
                               titles=titles,point_links=point_links,show_bridges=show)

    def render(self,*_,selection=None):
        if self.plan is None or self.applied:
            return
        edits={pair:(edges,pair in self.reversed_pairs) for pair,edges in self.contour_edges.items()}
        try:
            self.result,mode=self.plan.result(0,self.contour_choices(),contour_edges=edits,
                                              contour_phases=self.contour_phases)
        except ValueError as error:
            self.result=None
            self.apply.setEnabled(False)
            self.status.setText(str(error))
            self.update_controls()
            self.refresh_preview()
            return
        matched=self.plan.matched
        self.unconfirmed=[pair for pair,boundary in self.plan.contour_boundaries.items()
                          if (not boundary.equal or boundary.ambiguous)
                          and not self.contour_edges.get(pair) and pair not in self.reviewed]
        self.unmatched_a=[a for a in range(len(self.plan.contours_a)) if a not in matched]
        used=set(matched.values())
        self.unmatched_b=[b for b in range(len(self.plan.contours_b)) if b not in used]
        self.refresh_contour_views(selection)
        for a in range(self.contour_table.rowCount()):
            b=matched.get(a)
            choice=self.contour_table.cellWidget(a,1)
            choice.setItemText(0,f'自动（B{b+1}）' if choice.currentData()==-1 and b is not None else '自动')
            pair=(a,b)
            text='未配对' if b is None else '需确认' if pair in self.unconfirmed else '已配对'
            self.contour_table.item(a,2).setText(text)
        names=[f'A{i+1}' for i in self.unmatched_a]+[f'B{i+1}' for i in self.unmatched_b]
        self.force_unmatched.setVisible(bool(names))
        if names:
            label='、'.join(names[:6])+('…' if len(names)>6 else '')
            fallback=' · 将按内部顶点处理' if self.force_unmatched.isChecked() else ''
            summary=f'未配对 {len(names)} 圈（{label}）{fallback}'
        else:
            summary=f'已配对 {len(matched)} 圈'
        if self.unconfirmed:
            summary+=f' · 待确认 {len(self.unconfirmed)} 圈'
        self.status.setText(summary+f' · {mode}')
        self.status.setToolTip('、'.join(names+[f'A{a+1} ↔ B{b+1} 待确认' for a,b in self.unconfirmed]))
        self.update_controls()
        self.refresh_preview()

    def commit(self):
        if not self.apply.isEnabled():
            return
        try:
            write_result(self.data,self.result)
        except (RuntimeError,ValueError) as error:
            self.failed(error)
            return
        self.applied=True
        self.swap.setEnabled(False)
        self.mirror.setEnabled(False)
        self.force_unmatched.setEnabled(False)
        self.contour_table.setEnabled(False)
        self.update_controls()
        self.refresh_preview()
        self.status.setText('可用 Max 撤销。')


def show():
    window=Window(qtmax.GetQMaxMainWindow())
    window.show()
    return window
