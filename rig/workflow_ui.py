"""Seven-stage Max workflow, with shared scene and visibility controls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QTabWidget,QCheckBox
from .workbench import RigWorkbench

class WorkflowWorkbench(RigWorkbench):
    def __init__(self,owner):
        super().__init__(owner)
        # Preserve all mature editing/exchange/facial/recovery widgets; reorganize them into stages.
        old=[]
        while self.tabs.count():
            widget=self.tabs.widget(0);title=self.tabs.tabText(0);self.tabs.removeTab(0);old.append((widget,title))
        self.visibility_buttons={}
        layout=self.layout();bar=QHBoxLayout();layout.insertLayout(1,bar)
        for title,category in [('模型','models'),('骨骼','bones'),('控制器','controls')]:
            button=QPushButton(title+' 显示');button.setCheckable(True);button.setChecked(True)
            button.toggled.connect(lambda visible,c=category,b=button,t=title:self.guard(lambda:self.visibility(c,visible,b,t)));bar.addWidget(button);self.visibility_buttons[category]=(button,title)
        self.steps=QComboBox();self.steps.setObjectName('WorkflowSteps');layout.insertWidget(2,self.steps)
        self.steps.currentIndexChanged.connect(self.change_step);self.tabs.tabBar().hide()
        one=self.page('01  导入与整理')
        intro=QLabel('在视口选中模型、骨骼、控制器，再加入当前工作流。\n不复制场景对象，不改变原有层级。');intro.setWordWrap(True);one.addRow(intro)
        self.import_type=QComboBox()
        for label,key in [('自动分类','auto'),('模型','models'),('骨骼','bones'),('控制器 / 辅助体','controls')]:self.import_type.addItem(label,key)
        one.addRow('导入类别',self.import_type)
        self.actions(one,('导入视口选中对象',lambda:self.mutate('workflow.import',{'category':self.import_type.currentData()})),('刷新场景列表',lambda:self.call('scene.inspect',{},self.load_scene)))
        self.roster=QTreeWidget();self.roster.setHeaderLabels(['已导入对象','类别']);one.addRow(self.roster)
        two=self.page('02  自由人体骨架')
        self.rig_prefix=QLineEdit('LX');self.rig_height=self.number(.01,100000,170,1)
        self.rig_prefix.setPlaceholderText('留空：不加前缀或开头下划线')
        two.addRow('命名前缀',self.rig_prefix);two.addRow('高度（场景单位）',self.rig_height)
        self.chain_counts={}
        for key,title,value,low,high in [('spine','脊柱节数',3,1,12),('neck','颈部节数',1,1,12),('upperArm','上臂节数',1,1,12),('forearm','前臂节数',1,1,12),('thigh','大腿节数',1,1,12),('calf','小腿节数',1,1,12),('fingers','每手手指数',5,0,5),('fingerLinks','每指节数',3,1,12),('toes','每脚脚趾数',1,0,5),('toeLinks','每趾节数',2,1,12)]:
            field=self.integer(low,high,value);self.chain_counts[key]=field;two.addRow(title,field)
        self.actions(two,('在视口拖出人体高度',lambda:self.call('humanoid.drag',self.humanoid_options())),('按数值在原点创建',lambda:self.mutate('humanoid.create',self.humanoid_options())))
        note=QLabel('参照 Biped 比例与放松姿态，包含独立肩 / 锁骨。Z 轴向上，面向 -Y。普通 Bone，无 IK、不锁长度；可移动旋转。');note.setWordWrap(True);two.addRow(note)
        # Existing skeleton controls become the detailed stage, with viewport operations first.
        self.tabs.addTab(old[0][0],'03  自定义与定位')
        self.child_name=QLineEdit('LX_Custom');self.child_length=self.number(.001,100000,10,1)
        self.skeleton.insertRow(0,'新子骨骼名称',self.child_name);self.skeleton.insertRow(1,'子骨骼长度',self.child_length)
        symmetry=QWidget();symmetry_form=QVBoxLayout(symmetry);symmetry_form.setContentsMargins(0,0,0,0)
        self.symmetry_side=QComboBox();self.symmetry_side.addItem('左 → 右','L');self.symmetry_side.addItem('右 → 左','R')
        self.symmetry_whole=QCheckBox('选中骨架整侧（关闭则为选中骨骼及子骨骼）');self.symmetry_whole.setChecked(True)
        self.symmetry_auto_center=QCheckBox('以骨盆位置为中线（世界 X）');self.symmetry_auto_center.setChecked(True)
        self.symmetry_center=self.number(-100000,100000,0,1);self.symmetry_center.setEnabled(False)
        self.symmetry_auto_center.toggled.connect(lambda on:self.symmetry_center.setEnabled(not on))
        self.symmetry_live=QCheckBox('自动同步：编辑源侧后更新另一侧')
        self.symmetry_live.toggled.connect(lambda on:self.guard(lambda:self.toggle_symmetry(on)))
        row=QHBoxLayout();row.addWidget(self.symmetry_side);row.addWidget(QLabel('中线 X'));row.addWidget(self.symmetry_center);symmetry_form.addLayout(row)
        for widget in (self.symmetry_whole,self.symmetry_auto_center,self.symmetry_live):symmetry_form.addWidget(widget)
        run=QPushButton('对称选中骨架');run.clicked.connect(lambda:self.guard(self.mirror_bones));symmetry_form.addWidget(run)
        tip=QLabel('先在视口选骨骼。中线为世界 X；自定义骨骼用 L_ / R_ 配对。\n自动同步等待当前拖动完成，避免打断 Max 撤销；每次同步可单独撤销。');tip.setWordWrap(True);symmetry_form.addWidget(tip)
        self.skeleton.insertRow(0,'骨架对称',symmetry)
        self.actions(self.skeleton,('为视口选中骨骼加子骨骼',lambda:self.mutate('bone.child',{'name':self.child_name.text(),'length':self.child_length.value()})))
        self.guide_level=QComboBox()
        for title,key in [('顶点','vertex'),('边 / 循环边','edge'),('面','face')]:self.guide_level.addItem(title,key)
        self.skeleton.addRow('中心点来源',self.guide_level)
        self.actions(self.skeleton,('切换视口子对象选择',lambda:self.call('selection.mode',self.params(level=self.guide_level.currentData()))),('循环边',lambda:self.call('selection.expand',self.params(level='edge',operation='loop'))),('在选择平均中心打点',lambda:self.mutate('guide.center',{'level':self.guide_level.currentData()})))
        self.align_target=QComboBox();self.skeleton.addRow('端点对齐目标',self.align_target)
        self.actions(self.skeleton,('起点对齐目标',lambda:self.align('start')),('终点对齐目标',lambda:self.align('end')))
        four=self.page('04  IK 与长度定型')
        hint=QLabel('先调整骨架到模型内部。定型会固定 Bone 长度，为生成的人体手臂、腿创建 HI IK；脊柱、颈部、手指保持 FK。可使用 Max 撤销回退。');hint.setWordWrap(True);four.addRow(hint)
        self.actions(four,('一键添加 IK 并固定长度',lambda:self.mutate('rig.finalize',{'bones':self.selected_bones()})))
        five=self.page('05  控制器')
        self.control_shape=QComboBox()
        for label,key in [('圆环','circle'),('方框','rectangle'),('Point 虚拟体','point')]:self.control_shape.addItem(label,key)
        self.control_size=self.number(.001,100000,10,1);five.addRow('控制器形状',self.control_shape);five.addRow('尺寸',self.control_size)
        self.actions(five,('创建 IK 控制器与 Root',lambda:self.mutate('controls.create',{'shape':self.control_shape.currentData(),'size':self.control_size.value()})),('为列表所选对象创建控制器',lambda:self.mutate('controls.create',{'nodes':self.selected(),'shape':self.control_shape.currentData(),'size':self.control_size.value()})))
        six=self.page('06  自动蒙皮')
        self.bind_method=QComboBox()
        for label,key in [('骨骼线段距离（快速）','segment'),('体素内部距离场','voxel'),('Max 原生包络','envelope')]:self.bind_method.addItem(label,key)
        self.bind_limit=self.integer(1,64,4);self.falloff=self.number(.1,16,2,.1);self.resolution=self.integer(8,64,32)
        six.addRow('初始权重算法',self.bind_method);six.addRow('每点最多影响数',self.bind_limit);six.addRow('距离衰减',self.falloff);six.addRow('体素最长轴分辨率',self.resolution)
        note=QLabel('未选骨骼时使用工作流内全部骨骼。体素模式沿封闭模型内部传播距离；要求骨骼位于体积内，细小部位应提高分辨率。已有 Skin 会先保存权重快照再重算。');note.setWordWrap(True);six.addRow(note)
        self.actions(six,('创建 Skin / 计算初始权重',lambda:self.mutate('bind.auto',{'bones':self.selected_bones(),'method':self.bind_method.currentData(),'limit':self.bind_limit.value(),'falloff':self.falloff.value(),'resolution':self.resolution.value()})))
        w=self.page('07  权重与笔刷');w.addRow(self.info);self.actions(w,('读取 Skin 与当前选择',self.read_skin));w.addRow('作用范围',self.scope)
        self.multi_bones=QTreeWidget();self.multi_bones.setHeaderLabels(['多选影响骨骼']);self.multi_bones.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.multi_bones.setMinimumHeight(140)
        w.addRow(self.multi_bones);w.addRow('所选骨骼合计权重 / 增量',self.value);w.addRow('保留影响数 N',self.limit)
        self.actions(w,('多骨骼赋值',lambda:self.multi('set')),('多骨骼加值',lambda:self.multi('add')),('多骨骼减值',lambda:self.multi('subtract')),('逐点仅保留 N 个影响',lambda:self.mutate('weights.edit',{'mode':'prune','threshold':0,'limit':self.limit.value(),'scope':self.scope.currentData()},self.read_skin)))
        w.addRow('选点平滑强度',self.strength);w.addRow('平滑次数',self.iterations);self.actions(w,('平滑选点',lambda:self.weight('smooth')),('归一化',lambda:self.weight('normalize')))
        self.component=QComboBox()
        for label,key in [('顶点','vertex'),('边','edge'),('面','face')]:self.component.addItem(label,key)
        w.addRow('视口选择模式',self.component)
        self.actions(w,('进入点线面选择',lambda:self.call('selection.mode',self.params(level=self.component.currentData()))),('转换为 Skin 顶点',lambda:self.call('selection.to_skin',self.params(level=self.component.currentData()),lambda _:self.read_skin())))
        self.actions(w,*[(title,lambda op=op:self.call('selection.expand',self.params(level=self.component.currentData(),operation=op))) for title,op in [('循环边','loop'),('环形边','ring'),('扩大选择','grow'),('收缩选择','shrink')]])
        self.actions(w,*[(title,lambda op=op:self.call('selection.visibility',self.params(level=self.component.currentData(),operation=op))) for title,op in [('隐藏选择','hide'),('仅显示选择','isolate'),('显示全部子对象','show')]])
        self.brush_mode=QComboBox()
        for label,key in [('加值','add'),('减值','subtract'),('赋值','set'),('平滑','smooth')]:self.brush_mode.addItem(label,key)
        self.brush_radius=self.number(.001,100000,5,.5);self.brush_strength=self.number(.001,1,.2,.05);self.brush_selected=QCheckBox('仅绘制选中的 Skin 顶点')
        w.addRow('笔刷模式',self.brush_mode);w.addRow('笔刷半径（世界单位）',self.brush_radius);w.addRow('笔刷强度',self.brush_strength);w.addRow(self.brush_selected)
        self.actions(w,('开始视口绘制',self.begin_brush),('退出笔刷',lambda:self.call('brush.stop')))
        tip=QLabel('多骨骼编辑的值表示所选骨骼合计权重，内部保持原比例。\n笔刷：Shift 临时平滑，Ctrl 临时减值，右键退出，每笔支持撤销。');tip.setWordWrap(True);w.addRow(tip)
        extra=QTabWidget()
        extra.addTab(old[1][0],'逐骨骼 / 锁定')
        for widget,title in old[2:]:extra.addTab(widget,title)
        self.tabs.addTab(extra,'辅助  表情 / 交换 / 恢复')
        for i in range(self.tabs.count()):self.steps.addItem(self.tabs.tabText(i))
        self.tabs.setCurrentIndex(0)
    def selected_bones(self):
        selected=set(self.selected());return [n['id'] for n in self.nodes if n['id'] in selected and (n.get('workflow')=='bones' or n.get('bone'))]
    def symmetry_options(self):
        return dict(side=self.symmetry_side.currentData(),wholeRig=self.symmetry_whole.isChecked(),autoCenter=self.symmetry_auto_center.isChecked(),center=self.symmetry_center.value())
    def mirror_bones(self):
        self.stop_symmetry();self.call('symmetry.apply',self.symmetry_options())
    def toggle_symmetry(self,on):
        from . import symmetry
        if not on:symmetry.stop()
        else:
            try:symmetry.start(self.symmetry_options(),self,self.symmetry_notice)
            except Exception:self.stop_symmetry();raise
            self.notice.setText('自动对称已开启；请编辑选定源侧骨骼。修改范围或方向前先关闭。')
        for widget in (self.symmetry_side,self.symmetry_whole,self.symmetry_auto_center):widget.setEnabled(not on)
        self.symmetry_center.setEnabled(not on and not self.symmetry_auto_center.isChecked())
    def symmetry_notice(self,message):
        from . import symmetry
        if symmetry._live is None:self.stop_symmetry()
        self.notice.setText(message)
    def stop_symmetry(self):
        from . import symmetry
        symmetry.stop()
        self.symmetry_live.blockSignals(True);self.symmetry_live.setChecked(False);self.symmetry_live.blockSignals(False)
        for widget in (self.symmetry_side,self.symmetry_whole,self.symmetry_auto_center):widget.setEnabled(True)
        self.symmetry_center.setEnabled(not self.symmetry_auto_center.isChecked())
    def change_step(self,index):
        self.tabs.setCurrentIndex(index)
        def show_items(layout,visible):
            for i in range(layout.count()):
                item=layout.itemAt(i)
                if item.widget():item.widget().setVisible(visible)
                elif item.layout():show_items(item.layout(),visible)
        show_items(self.body.layout().itemAt(0).layout(),index in (0,2,5,6,7))
    def visibility(self,category,visible,button,title):
        button.setText(title+(' 显示' if visible else ' 隐藏'));self.call('workflow.visibility',{'category':category,'visible':visible})
    def humanoid_options(self):return dict(height=self.rig_height.value(),prefix=self.rig_prefix.text(),**{k:v.value() for k,v in self.chain_counts.items()})
    def align(self,endpoint):self.mutate('bone.align',{'node':self.one(),'target':self.align_target.currentData(),'endpoint':endpoint})
    def selected_influences(self):return [i.data(0,Qt.ItemDataRole.UserRole) for i in self.multi_bones.selectedItems()]
    def multi(self,mode):self.mutate('weights.multi',{'bones':self.selected_influences(),'value':abs(self.value.value()),'mode':mode,'scope':self.scope.currentData()},self.read_skin)
    def begin_brush(self):self.call('brush.start',self.params(bones=self.selected_influences(),mode=self.brush_mode.currentData(),radius=self.brush_radius.value(),strength=self.brush_strength.value(),value=abs(self.value.value()),selectedOnly=self.brush_selected.isChecked()))
    def load_scene(self,data):
        super().load_scene(data)
        if not hasattr(self,'roster'):return
        self.roster.clear();previous=self.align_target.currentData();self.align_target.clear()
        for category,(button,title) in self.visibility_buttons.items():
            group=[n for n in self.nodes if n.get('workflow')==category];visible=not group or any(not n.get('hidden') for n in group)
            button.blockSignals(True);button.setChecked(visible);button.setText(title+(' 显示' if visible else ' 隐藏'));button.blockSignals(False)
        for n in self.nodes:
            self.align_target.addItem(n['name'],n['id'])
            if n.get('workflow'):self.roster.addTopLevelItem(QTreeWidgetItem([n['name'],{'models':'模型','bones':'骨骼','controls':'控制器'}.get(n['workflow'],n['workflow'])]))
        self.align_target.setCurrentIndex(max(0,self.align_target.findData(previous)))
    def load_skin(self,data):
        super().load_skin(data)
        selected=set(self.selected_influences());self.multi_bones.clear()
        for b in data['bones']:
            item=QTreeWidgetItem([b['name']]);item.setData(0,Qt.ItemDataRole.UserRole,b['id']);self.multi_bones.addTopLevelItem(item);item.setSelected(b['id'] in selected)
