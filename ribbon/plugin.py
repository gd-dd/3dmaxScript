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

class StatusBox(QtWidgets.QPlainTextEdit):
    """Scrollable feedback with the existing status.text()/setText() interface."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(48)
        self.setMaximumHeight(64)
        self.setAccessibleName('操作反馈')

    def setText(self, text):
        self.setPlainText(text)
        self.verticalScrollBar().setValue(0)

    def text(self):
        return self.toPlainText()


class RibbonWindow(QtWidgets.QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.chain=[]
        self.setWindowTitle('LX 飘带 · 骨骼动力学')
        self.resize(440,660)
        self.setMinimumSize(300,400)
        self.setStyleSheet(STYLE + '\nQPushButton#RibbonBake {background:#507522;color:#FFFFFF;border-color:#507522;font-weight:600;} QToolButton#RibbonAdvanced {color:#507522;background:#FFFFFF;border:0;padding:8px 0;text-align:left;}')
        layout=QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12); layout.setSpacing(8)
        header=QtWidgets.QHBoxLayout()
        icon=QtWidgets.QLabel()
        icon.setPixmap(QtGui.QPixmap(str(ROOT.parent/'.lxtool/icon.png')).scaled(36,36,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
        header.addWidget(icon)
        title=QtWidgets.QLabel('飘带解算')
        title.setStyleSheet('font-size:22px;color:#507522;font-weight:bold;')
        header.addWidget(title); header.addStretch()
        layout.addLayout(header)
        self.read_button=QtWidgets.QPushButton('读取选中的根骨骼')
        self.read_button.clicked.connect(self.read); layout.addWidget(self.read_button)
        self.info=QtWidgets.QLabel('尚未读取骨骼 · 请先在场景中选择根骨骼')
        self.info.setWordWrap(True)
        self.info.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(self.info)

        self.pages=QtWidgets.QTabWidget()
        self.pages.setObjectName('RibbonWorkflow')
        self.pages.setMinimumSize(0,0)
        self.pages.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Expanding)
        self.pages.tabBar().setExpanding(True)
        self.pages.tabBar().setUsesScrollButtons(True)
        layout.addWidget(self.pages,1)

        chain_page=QtWidgets.QWidget()
        chain_layout=QtWidgets.QVBoxLayout(chain_page)
        chain_layout.setContentsMargins(0,8,0,0)
        chain_tip=QtWidgets.QLabel('读取普通父子骨骼单链。最后一节仅作末端定位。')
        chain_tip.setWordWrap(True)
        chain_tip.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
        chain_layout.addWidget(chain_tip)
        self.chain_list=QtWidgets.QListWidget()
        self.chain_list.setAccessibleName('已读取的骨骼链')
        self.chain_list.setMinimumSize(0,0)
        self.chain_list.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Expanding)
        self.chain_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.chain_list.setWordWrap(True)
        self.chain_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.chain_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        chain_layout.addWidget(self.chain_list,1)
        self.pages.addTab(chain_page,'骨骼链')

        self.config_scroll=QtWidgets.QScrollArea()
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.config_scroll.setMinimumSize(0,0)
        config=QtWidgets.QWidget()
        config.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
        config_layout=QtWidgets.QVBoxLayout(config)
        config_layout.setContentsMargins(0,8,8,8); config_layout.setSpacing(8)
        self.fields={}
        common=QtWidgets.QGroupBox('常用动力学')
        common_form=self._form(common)
        advanced=QtWidgets.QWidget()
        advanced_form=self._form(advanced)
        for key,label,value,lo,hi,tip in [('gravity','重力（场景单位/秒²）',980,-100000,100000,'正数向下，负数向上；厘米场景通常使用 980'),('inertia','惯性',0.95,0,1,'越大越保留世界空间运动；越小越跟随根骨骼'),('mass','质量',1,0.01,1000,'越大越不容易被阻尼减速；不会改变重力加速度'),('influence','长度影响系数',1,0,3,'零表示统一阻尼；增大后长骨段保留更多运动'),('damping','阻尼',3,0,50,'越大越快停止摆动')]:
            control=QtWidgets.QDoubleSpinBox()
            control.setRange(lo,hi); control.setDecimals(3); control.setValue(value)
            control.setToolTip(tip); control.setAccessibleName(label)
            control.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Fixed)
            (common_form if key in ('gravity','inertia','mass') else advanced_form).addRow(label,control)
            self.fields[key]=control
        config_layout.addWidget(common)
        group=QtWidgets.QGroupBox('烘焙范围')
        form=self._form(group)
        self.start=QtWidgets.QSpinBox(); self.end=QtWidgets.QSpinBox()
        for c in (self.start,self.end):
            c.setRange(-100000,100000)
            c.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Fixed)
        self.start.setValue(int(rt.animationRange.start.frame)); self.end.setValue(int(rt.animationRange.end.frame))
        self.start.setAccessibleName('开始帧'); self.end.setAccessibleName('结束帧')
        form.addRow('开始帧',self.start); form.addRow('结束帧',self.end)
        config_layout.addWidget(group)
        self.advanced_button=QtWidgets.QToolButton()
        self.advanced_button.setObjectName('RibbonAdvanced')
        self.advanced_button.setText('高级参数 · 长度影响与阻尼')
        self.advanced_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.advanced_button.setArrowType(QtCore.Qt.RightArrow)
        self.advanced_button.setCheckable(True)
        self.advanced_button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,QtWidgets.QSizePolicy.Fixed)
        self.advanced_panel=advanced
        advanced.setVisible(False)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        config_layout.addWidget(self.advanced_button); config_layout.addWidget(advanced)
        help_text=QtWidgets.QLabel('质量影响阻尼响应，不改变重力加速度。参数说明可将鼠标停在输入框上查看。')
        help_text.setWordWrap(True)
        help_text.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
        config_layout.addWidget(help_text); config_layout.addStretch()
        self.config_scroll.setWidget(config)
        self.pages.addTab(self.config_scroll,'参数配置')

        preview_page=QtWidgets.QWidget()
        preview_layout=QtWidgets.QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(0,8,0,0)
        preview_tip=QtWidgets.QLabel('核对骨骼与参数后烘焙。此页仅预览配置，不修改场景。')
        preview_tip.setWordWrap(True)
        preview_tip.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Preferred)
        preview_layout.addWidget(preview_tip)
        self.preview=QtWidgets.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('烘焙配置预览')
        self.preview.setMinimumSize(0,0)
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Ignored,QtWidgets.QSizePolicy.Expanding)
        self.preview.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        preview_layout.addWidget(self.preview,1)
        self.pages.addTab(preview_page,'烘焙预览')

        for control in [*self.fields.values(),self.start,self.end]:
            control.installEventFilter(self)
            control.valueChanged.connect(self._refresh_preview)
        self.pages.currentChanged.connect(self._refresh_preview)
        self.run=QtWidgets.QPushButton('解算并烘焙')
        self.run.setObjectName('RibbonBake')
        self.run.clicked.connect(self.solve); layout.addWidget(self.run)
        self.status=StatusBox()
        self.status.setText('烘焙写入变换关键帧，可用 Max 撤销。\n运行前请保存场景；暂不包含碰撞。')
        layout.addWidget(self.status)
        self._refresh_preview()

    @staticmethod
    def _form(parent):
        form=QtWidgets.QFormLayout(parent)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setContentsMargins(10,12,10,10)
        form.setVerticalSpacing(6)
        return form

    def _toggle_advanced(self,expanded):
        self.advanced_panel.setVisible(expanded)
        self.advanced_button.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)

    def _refresh_preview(self,*args):
        names=[str(n.name) for n in self.chain if rt.isValidNode(n)] if self.chain else []
        lines=['骨骼链：'+('已读取普通单链' if names else '尚未读取'),
               '骨骼数量：%d（最后一节作末端定位）'%len(names),
               '烘焙范围：%d → %d 帧'%(self.start.value(),self.end.value())]
        if self.end.value()<=self.start.value(): lines.append('请将结束帧设为大于开始帧。')
        labels={'gravity':'重力（场景单位/秒²）','inertia':'惯性','mass':'质量','influence':'长度影响系数','damping':'阻尼'}
        lines.extend('%s：%g'%(labels[k],c.value()) for k,c in self.fields.items())
        lines.extend(['','根骨骼：'+(names[0] if names else '尚未读取'),'逐帧写入变换关键帧；根骨骼旋转由解算覆盖。','请保存场景后运行。撤销在 Max 中执行；本工具不含碰撞。'])
        self.preview.setPlainText('\n'.join(lines))

    def eventFilter(self,obj,event):
        if event.type()==QtCore.QEvent.Wheel:
            event.ignore()
            # Ignoring an editor wheel must still let the configuration page scroll.
            if self.config_scroll.isAncestorOf(obj):
                bar=self.config_scroll.verticalScrollBar()
                if event.pixelDelta().y(): bar.setValue(bar.value()-event.pixelDelta().y())
                else: bar.setValue(bar.value()-round(event.angleDelta().y()/120*bar.singleStep()*3))
            return True
        return super().eventFilter(obj,event)

    def read(self):
        try:
            self.chain=chain_from_selection()
            self.info.setText('已读取 %d 节骨骼 · 在骨骼链页核对顺序'%len(self.chain))
            self.info.setToolTip(str(self.chain[0].name))
            self.chain_list.clear()
            for i,node in enumerate(self.chain):
                item=QtWidgets.QListWidgetItem('%d. %s%s'%(i+1,node.name,'（末端定位）' if i==len(self.chain)-1 else ''))
                item.setToolTip(str(node.name)); self.chain_list.addItem(item)
        except Exception as e:
            self.chain=[]; self.chain_list.clear()
            self.info.setText('读取失败，请重新选择单链根骨骼'); self.status.setText(str(e))
        self._refresh_preview()

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






