"""Seven-stage Max workflow, with shared scene and visibility controls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,QLineEdit,QTreeWidget,QTreeWidgetItem,QAbstractItemView,QTabWidget,QCheckBox,QSplitter,QSizePolicy,QScrollArea,QFrame
from .workbench import RigWorkbench
from .selection_ui import SelectionMixin

class WorkflowWorkbench(SelectionMixin,RigWorkbench):
    def __init__(self,owner):
        super().__init__(owner)
        # Preserve all mature editing/exchange/facial/recovery widgets; reorganize them into stages.
        old=[]
        while self.tabs.count():
            widget=self.tabs.widget(0);title=self.tabs.tabText(0);self.tabs.removeTab(0);old.append((widget,title))
        self.visibility_buttons={};self.box_buttons={}
        layout=self.layout();bar=QHBoxLayout();layout.insertLayout(1,bar)
        for title,category in [('模型','models'),('骨骼','bones'),('控制器','controls')]:
            button=QPushButton(title+' 显示');button.setCheckable(True);button.setChecked(True)
            button.toggled.connect(lambda visible,c=category,b=button,t=title:self.guard(lambda:self.visibility(c,visible,b,t)));bar.addWidget(button);self.visibility_buttons[category]=(button,title)
            box=QPushButton('包围框');box.setCheckable(True);box.setToolTip(title+'类别的包围框显示，不影响其他类别');box.toggled.connect(lambda on,c=category:self.guard(lambda:self.call('workflow.boxes',{'category':c,'enabled':on,'nodes':self.category_nodes(c)})));bar.addWidget(box);self.box_buttons[category]=box
        self.steps=QComboBox();self.steps.setObjectName('WorkflowSteps');layout.insertWidget(2,self.steps)
        self.steps.currentIndexChanged.connect(self.change_step);self.tabs.tabBar().hide()
        one=self.page('01  导入与整理')
        intro=QLabel('读取场景即可使用已有模型、Bone、Biped 和控制器。\n可选：将视口选择加入工作集，便于单独筛选；不复制对象。');intro.setWordWrap(True);one.addRow(intro)
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
        self.actions(two,('摆正选中的骨盆',lambda:self.mutate('pelvis.straighten',{'bones':self.selected_bones()})))
        self.actions(two,('在视口拖出人体高度',lambda:self.call('humanoid.drag',self.humanoid_options())),('按数值在原点创建',lambda:self.mutate('humanoid.create',self.humanoid_options())))
        note=QLabel('参照 Biped 比例与放松姿态，包含独立肩 / 锁骨与骨盆，BodyCenter 为质心。Z 轴向上，面向 -Y。普通 Bone，无 IK、不锁长度；可移动旋转。');note.setWordWrap(True);two.addRow(note)
        # Existing skeleton controls become the detailed stage, with viewport operations first.
        self.tabs.addTab(old[0][0],'03  自定义与定位')
        self.child_name=QLineEdit('LX_Custom');self.child_length=self.number(.001,100000,10,1)
        child_box=QWidget();child_form=QFormLayout(child_box);child_form.setContentsMargins(0,0,0,0)
        self.child_parent=None;self.child_parent_scene=None;self.child_parent_label=QLabel('未记住父骨骼：使用骨骼栏单选或视口单选 Bone');self.child_parent_label.setWordWrap(True)
        child_form.addRow(self.child_parent_label)
        self.actions(child_form,('记住骨骼栏所选父骨骼',lambda:self.remember_child_parent(True)),('记住视口所选父骨骼',lambda:self.remember_child_parent(False)))
        child_form.addRow('新子骨骼名称',self.child_name);child_form.addRow('长度（世界单位）',self.child_length)
        self.child_start=QLineEdit();self.child_direction=QLineEdit()
        self.child_start.setPlaceholderText('留空：父骨骼末端；或输入 X, Y, Z')
        self.child_direction.setPlaceholderText('留空：继承父骨骼方向；或输入 X, Y, Z')
        for key,title,field in [('start','起点',self.child_start),('direction','方向点（只定方向）',self.child_direction)]:
            child_form.addRow(title,field)
            label='起点' if key=='start' else '方向'
            self.actions(child_form,(label+' · 对象轴心',lambda k=key:self.capture_child_point(k,'pivot')),(label+' · 顶点中心',lambda k=key:self.capture_child_point(k,'vertex')))
        tip=QLabel('先记住父骨骼，再选参考对象取点。支持无修改器的可编辑多边形，或当前 Edit Poly 的顶点；多选取平均中心。取点只读、不改堆栈。方向点远近不影响长度。');tip.setWordWrap(True);child_form.addRow(tip)
        self.actions(child_form,('按起点 / 方向点添加',lambda:self.add_child(False)),('从父骨骼末端顺延添加',lambda:self.add_child(True)))
        self.actions(child_form,('清空取点（恢复继承）',lambda:(self.child_start.clear(),self.child_direction.clear())))
        self.skeleton.insertRow(0,'添加普通 Bone',child_box)
        symmetry=QWidget();symmetry_form=QVBoxLayout(symmetry);symmetry_form.setContentsMargins(0,0,0,0)
        self.symmetry_side=QComboBox();self.symmetry_side.addItem('左 → 右','L');self.symmetry_side.addItem('右 → 左','R')
        self.symmetry_whole=QCheckBox('选中骨架整侧（关闭则为选中骨骼及子骨骼）');self.symmetry_whole.setChecked(True)
        self.symmetry_auto_center=QCheckBox('以身体质心为中线（世界 X）');self.symmetry_auto_center.setChecked(True)
        self.symmetry_center=self.number(-100000,100000,0,1);self.symmetry_center.setEnabled(False)
        self.symmetry_auto_center.toggled.connect(lambda on:self.symmetry_center.setEnabled(not on))
        self.symmetry_live=QCheckBox('自动同步：编辑源侧后更新另一侧')
        self.symmetry_live.toggled.connect(lambda on:self.guard(lambda:self.toggle_symmetry(on)))
        row=QHBoxLayout();row.addWidget(self.symmetry_side);row.addWidget(QLabel('中线 X'));row.addWidget(self.symmetry_center);symmetry_form.addLayout(row)
        for widget in (self.symmetry_whole,self.symmetry_auto_center,self.symmetry_live):symmetry_form.addWidget(widget)
        run=QPushButton('对称选中骨架');run.clicked.connect(lambda:self.guard(self.mirror_bones));symmetry_form.addWidget(run)
        tip=QLabel('先在视口选骨骼。中线为世界 X；自定义骨骼用 L_ / R_ 配对。\n自动同步等待当前拖动完成，避免打断 Max 撤销；每次同步可单独撤销。');tip.setWordWrap(True);symmetry_form.addWidget(tip)
        self.skeleton.insertRow(0,'骨架对称',symmetry)
        self.guide_level=QComboBox()
        for title,key in [('顶点','vertex'),('边 / 循环边','edge'),('面','face')]:self.guide_level.addItem(title,key)
        self.skeleton.addRow('中心点来源',self.guide_level)
        self.actions(self.skeleton,('切换视口子对象选择',lambda:self.call('selection.mode',self.params(level=self.guide_level.currentData()))),('循环边',lambda:self.call('selection.expand',self.params(level='edge',operation='loop'))),('在选择平均中心打点',lambda:self.mutate('guide.center',{'level':self.guide_level.currentData()})))
        self.align_target=QComboBox();self.skeleton.addRow('已有骨骼端点对齐（改变长度）',self.align_target)
        self.actions(self.skeleton,('起点对齐目标',lambda:self.align('start')),('终点对齐目标',lambda:self.align('end')))
        four=self.page('04  IK 与长度定型')
        hint=QLabel('先调整骨架到模型内部。定型会固定 Bone 长度，为生成的人体手臂、腿创建 HI IK；脊柱、颈部、手指保持 FK。可使用 Max 撤销回退。');hint.setWordWrap(True);four.addRow(hint)
        self.bend_segments=QCheckBox('允许大小臂 / 大小腿中间分段参与弯曲（默认关闭）');four.addRow(self.bend_segments)
        self.ik_size=self.number(.05,20,1,.1);four.addRow('IK 显示倍率（按骨架高度）',self.ik_size)
        self.actions(four,('一键添加 IK 并固定长度',lambda:self.mutate('rig.finalize',{'bones':self.selected_bones(),'bendSegments':self.bend_segments.isChecked(),'displayScale':self.ik_size.value()})))
        five=self.page('05  控制器')
        self.control_shape=QComboBox()
        for label,key in [('圆环','circle'),('方框','rectangle'),('Point 虚拟体','point')]:self.control_shape.addItem(label,key)
        self.control_size=self.number(.05,20,1,.1);five.addRow('控制器形状',self.control_shape);five.addRow('显示倍率（按骨架高度）',self.control_size)
        hint=QLabel('默认 1 倍：圆环半径 / Point 尺寸为骨架高度的 3%，Root 为 5%。同场多套骨架分别计算；已有 Bone 按实际层级识别。仅调整显示大小，不缩放骨架。');hint.setWordWrap(True);five.addRow(hint)
        self.actions(five,('创建 IK 控制器与 Root',lambda:self.mutate('controls.create',{'shape':self.control_shape.currentData(),'displayScale':self.control_size.value()})),('为列表所选对象创建控制器',lambda:self.mutate('controls.create',{'nodes':self.selected(),'shape':self.control_shape.currentData(),'displayScale':self.control_size.value()})))
        self.actions(five,('按当前骨架重新适配显示尺寸',lambda:self.mutate('controls.resize',{'nodes':self.selected(),'displayScale':self.control_size.value(),'ikScale':self.ik_size.value()})))
        six=self.page('06  自动蒙皮')
        self.bind_method=QComboBox()
        for label,key in [('骨骼线段距离（快速）','segment'),('体素内部距离场','voxel'),('Max 原生包络','envelope')]:self.bind_method.addItem(label,key)
        self.bind_limit=self.integer(1,64,4);self.falloff=self.number(.1,16,2,.1);self.resolution=self.integer(8,64,32)
        six.addRow('初始权重算法',self.bind_method);six.addRow('每点最多影响数',self.bind_limit);six.addRow('距离衰减',self.falloff);six.addRow('体素最长轴分辨率',self.resolution)
        note=QLabel('在模型栏多选目标。分步模式逐个推荐影响骨骼，调整骨骼栏后确认下一步。批量模式自动采用推荐范围。体素模式要求封闭模型；外部骨骼不会再中断整次计算。');note.setWordWrap(True);six.addRow(note)
        self.bind_progress=QLabel('尚未开始蒙皮队列');self.bind_progress.setWordWrap(True);six.addRow(self.bind_progress)
        self.actions(six,('开始分步蒙皮',lambda:self.start_bind_queue(False)),('自动批量蒙皮',lambda:self.start_bind_queue(True)))
        self.actions(six,('确认此模型并下一步',self.confirm_bind_model),('跳过此模型',self.skip_bind_model),('停止队列',self.stop_bind_queue))
        w=self.page('07  权重与笔刷');w.addRow(self.info);self.actions(w,('读取 Skin 与当前选择',self.read_skin));w.addRow('作用范围',self.scope)
        self.color_view=QCheckBox('持续显示所选骨骼合计权重颜色');self.color_view.setChecked(True);w.addRow(self.color_view)
        legend=QLabel('蓝 0 → 青 → 绿 0.5 → 黄 → 红 1 · 多骨骼显示总和');legend.setWordWrap(True);w.addRow(legend)
        self.vertex_values=QTreeWidget();self.vertex_values.setHeaderLabels(['模型','顶点','合计影响']);self.vertex_values.setMaximumHeight(150);self.vertex_values.setToolTip('每模型显示前 200 个所选 Skin 顶点；未选点时显示模型顶点。');w.addRow(self.vertex_values)
        w.addRow('所选骨骼合计权重 / 增量',self.value);w.addRow('保留影响数 N',self.limit)
        self.actions(w,('仅当前选中骨骼影响',lambda:self.call('weights.restrict',{'meshes':self.selected_models(),'boneNodes':self.selected_bones()},lambda _:self.read_skin())))
        self.actions(w,('多骨骼赋值',lambda:self.multi('set')),('多骨骼加值',lambda:self.multi('add')),('多骨骼减值',lambda:self.multi('subtract')),('逐点仅保留 N 个影响',lambda:self.mutate('weights.edit',{'mode':'prune','threshold':0,'limit':self.limit.value(),'scope':self.scope.currentData()},self.read_skin)))
        w.addRow('选点平滑强度',self.strength);w.addRow('平滑次数',self.iterations);self.actions(w,('平滑选点',lambda:self.weight('smooth')),('归一化',lambda:self.weight('normalize')))
        self.component=QComboBox()
        for label,key in [('顶点','vertex'),('边','edge'),('面','face'),('混合点 / 边 / 面','mixed')]:self.component.addItem(label,key)
        w.addRow('视口选择模式',self.component)
        self.actions(w,('进入点线面选择',lambda:self.call('selection.mode',self.params(level=self.component.currentData()))),('转换为 Skin 顶点',lambda:self.call('selection.to_skin',self.params(level=self.component.currentData()),lambda _:self.read_skin())))
        self.actions(w,*[(title,lambda op=op:self.call('selection.expand',self.params(level=self.component.currentData(),operation=op))) for title,op in [('循环（点 / 边 / 面）','loop'),('环形（点 / 边 / 面）','ring'),('扩大选择','grow'),('收缩选择','shrink')]])
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
        self.actions(self.diagnostics.parentWidget().layout(),('保存完整 Max 场景副本',lambda:self.call('scene.backup')),('检查骨骼关节连接',lambda:self.call('bone.connections')))
        self.tabs.addTab(extra,'辅助  表情 / 交换 / 恢复')
        for i in range(self.tabs.count()):self.steps.addItem(self.tabs.tabText(i))
        self.tabs.setCurrentIndex(0)
        self.build_shared_scene(two,w)
    def remember_child_parent(self,from_list):
        refs=self.selected_bones()
        if from_list and len(refs)!=1:raise ValueError('请在骨骼栏只选一根普通 Bone')
        self.call('bone.parent_capture',{'node':refs[0]} if from_list else {},self.set_child_parent)
    def set_child_parent(self,data):
        self.child_parent=data['node'];self.child_parent_scene=self.scene
        self.child_parent_label.setText('当前父骨骼：'+data['name']+'（添加成功后自动改为新骨骼）')
    def capture_child_point(self,key,mode):
        def done(data):
            field=self.child_start if key=='start' else self.child_direction
            field.setText(', '.join(format(v,'.9g') for v in data['position']))
            field.setToolTip(data['message'])
        self.call('point.capture',{'mode':mode},done)
    def add_child(self,extend):
        refs=self.selected_bones();parent=self.child_parent if self.child_parent_scene==self.scene else None
        if not parent and len(refs)==1:parent=refs[0]
        params={'name':self.child_name.text(),'length':self.child_length.value(),'parent':parent,'extend':extend}
        if len(refs)==1 and refs[0]!=parent:params['fallbackParent']=refs[0]
        if not extend:
            for key,field in [('start',self.child_start),('direction',self.child_direction)]:
                if field.text().strip():
                    from .bone_creation import point
                    params[key]=point(field.text().replace('，',',').split(','))
        def done(data):
            self.set_child_parent(data)
            def refreshed(scene):self.load_scene(scene);self.choose_bone_nodes([data['node']])
            self.call('scene.inspect',{},refreshed)
        self.call('bone.child',params,done)
    def symmetry_options(self):
        return dict(bones=self.selected_bones(),side=self.symmetry_side.currentData(),wholeRig=self.symmetry_whole.isChecked(),autoCenter=self.symmetry_auto_center.isChecked(),center=self.symmetry_center.value())
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
    def build_shared_scene(self,two,weights_form):
        from .scene_ui import prepare_tree,split_form
        # Reuse the same model target, Skin selector and hierarchy in every step.
        body_layout=self.body.layout();target_form=body_layout.takeAt(0).layout();target_form.removeRow(2)
        body_layout.removeWidget(self.tabs)
        self.skeleton.takeRow(self.tree);prepare_tree(self.tree)
        self.shared_scene=QWidget();left=QVBoxLayout(self.shared_scene);left.setContentsMargins(0,0,8,0)
        title=QLabel('场景工作集 · 全流程共用');title.setStyleSheet('font-size:14px;font-weight:600;color:#507522');left.addWidget(title)
        self.layout().removeWidget(self.refresh);left.addWidget(self.refresh)
        self.scene_search=QLineEdit();self.scene_search.setPlaceholderText('搜索名称、肩、骨盆、左 / 右…');left.addWidget(self.scene_search)
        self.workflow_only=QCheckBox('仅显示已导入 / 本工具生成的对象');self.workflow_only.setChecked(False);left.addWidget(self.workflow_only)
        self.build_categories(left)
        row=QHBoxLayout()
        for label,fn in [('展开',lambda:[t.expandAll() for t in self.category_trees.values()]),('折叠',lambda:[t.collapseAll() for t in self.category_trees.values()]),('选中到 Max',lambda:self.call('nodes.select',{'nodes':self.selected()}))]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,f=fn:self.guard(f));row.addWidget(button)
        left.addLayout(row);weights_form.insertRow(0,target_form)
        self.context_summary=QLabel('读取一次场景，各步骤共用对象和当前模型。');self.context_summary.setWordWrap(True);left.addWidget(self.context_summary)
        self.scene_search.textChanged.connect(self.filter_scene_tree);self.workflow_only.toggled.connect(self.filter_scene_tree)
        # Object roles keep independent selection sets.
        self.splitter=QSplitter(Qt.Orientation.Horizontal);self.splitter.addWidget(self.shared_scene);self.splitter.addWidget(self.tabs)
        self.splitter.setChildrenCollapsible(False);self.splitter.setStretchFactor(0,0);self.splitter.setStretchFactor(1,1);self.splitter.setSizes([330,720]);body_layout.addWidget(self.splitter,1)
        self.layout().setStretchFactor(self.body,1)
        self.shared_scene.setMinimumWidth(260);self.tabs.setMinimumWidth(340)
        self.form_columns=[split_form(two,8),split_form(self.skeleton,max(1,self.skeleton.rowCount()//2)),split_form(weights_form,weights_form.getWidgetPosition(self.component)[0])]
        self.layout_mode=QComboBox();self.layout_mode.addItem('左右分区','horizontal');self.layout_mode.addItem('上下分区','vertical')
        self.layout_mode.currentIndexChanged.connect(lambda _:self.splitter.setOrientation(Qt.Orientation.Horizontal if self.layout_mode.currentData()=='horizontal' else Qt.Orientation.Vertical))
        view_row=QHBoxLayout();view_row.addWidget(self.layout_mode);view_row.addWidget(QLabel('当前视口'))
        self.view_buttons={}
        for title,key in [('线框','wireframe'),('边面','edges'),('选择外框','brackets')]:
            button=QPushButton(title);button.setCheckable(True);button.toggled.connect(lambda on,k=key:self.guard(lambda:self.call('viewport.display',{k:on},lambda data:self.load_viewport(data.get('viewport',{})))));view_row.addWidget(button);self.view_buttons[key]=button
        self.link_button=QPushButton('骨骼连接线');self.link_button.setCheckable(True);self.link_button.setToolTip('显示工作集骨骼的父子层级连线，保留骨骼实体');self.link_button.toggled.connect(lambda on:self.guard(lambda:self.call('workflow.links',{'enabled':on})));view_row.addWidget(self.link_button)
        self.layout().insertLayout(3,view_row)
    def load_viewport(self,data):
        for key,button in getattr(self,'view_buttons',{}).items():
            button.blockSignals(True);button.setChecked(bool(data.get(key,False)));button.blockSignals(False)
    def choose_tree_model(self):
        chosen=set(self.selected())
        models=[n for n in self.nodes if n['id'] in chosen and n.get('geometry') and not n.get('bone')]
        if len(models)==1:self.mesh.setCurrentIndex(self.mesh.findData(models[0]['id']))
    def filter_scene_tree(self,*_):
        if not hasattr(self,'scene_search'):return
        from .scene_ui import filter_tree
        filter_tree(self.tree,self.nodes,self.scene_search.text(),self.workflow_only.isChecked());self.filter_categories()
    def change_step(self,index):self.tabs.setCurrentIndex(index);self.invalidate_preview()
    def category_nodes(self,kind):
        from .selection_ui import category
        return [n['id'] for n in self.nodes if category(n)==kind]
    def visibility(self,category,visible,button,title):
        from .selection_ui import category as node_category
        nodes=[n['id'] for n in self.nodes if node_category(n)==category]
        button.blockSignals(True);button.setChecked(not visible);button.blockSignals(False)
        def done(data):
            button.blockSignals(True);button.setChecked(visible);button.blockSignals(False)
            button.setText(title+(' 显示' if visible else ' 隐藏'))
            for n in self.nodes:
                if n['id'] in nodes:n['hidden']=not visible
        self.call('workflow.visibility',{'category':category,'visible':visible,'nodes':nodes},done)
    def humanoid_options(self):return dict(height=self.rig_height.value(),prefix=self.rig_prefix.text(),**{k:v.value() for k,v in self.chain_counts.items()})
    def align(self,endpoint):self.mutate('bone.align',{'node':self.one(),'target':self.align_target.currentData(),'endpoint':endpoint})
    def multi(self,mode):
        self.edit_influences(lambda:self.mutate('weights.multi',{'bones':self.selected_influences(),'value':abs(self.value.value()),'mode':mode,'scope':self.scope.currentData()},self.read_skin))
    def begin_brush(self):
        self.edit_influences(lambda:self.call('brush.start',self.params(bones=self.selected_influences(),mode=self.brush_mode.currentData(),radius=self.brush_radius.value(),strength=self.brush_strength.value(),value=abs(self.value.value()),selectedOnly=self.brush_selected.isChecked())))
    def load_scene(self,data):
        if hasattr(self,'child_parent_scene') and (self.child_parent_scene!=data['scene'] or self.child_parent not in {n['id'] for n in data['nodes']}):
            self.child_parent=None;self.child_parent_scene=None
            self.child_parent_label.setText('未记住父骨骼：使用骨骼栏单选或视口单选 Bone')
            self.child_start.clear();self.child_direction.clear()
        previous_skin=self.skin.currentData(Qt.ItemDataRole.UserRole+1)
        self.tree.blockSignals(True)
        super().load_scene(data)
        self.tree.blockSignals(False)
        if previous_skin is not None:
            for i in range(self.skin.count()):
                if self.skin.itemData(i,Qt.ItemDataRole.UserRole+1)==previous_skin:self.skin.setCurrentIndex(i);break
        if hasattr(self,'context_summary'):
            from .scene_ui import decorate_tree
            from .selection_ui import category as node_category
            decorate_tree(self.tree,self.nodes);self.filter_scene_tree()
            self.context_summary.setText('共用工作集：%d 模型 · %d 骨骼 · %d 控制器'%tuple(sum(node_category(n)==c for n in self.nodes) for c in ('models','bones','controls')))
        if not hasattr(self,'roster'):return
        self.roster.clear();previous=self.align_target.currentData();self.align_target.clear();self.load_viewport(data.get('viewport',{}))
        for category,(button,title) in self.visibility_buttons.items():
            group=[n for n in self.nodes if n['id'] in self.category_nodes(category)];visible=not group or any(not n.get('hidden') for n in group)
            button.blockSignals(True);button.setChecked(visible);button.setText(title+(' 显示' if visible else ' 隐藏'));button.blockSignals(False)
            box=self.box_buttons[category];box.blockSignals(True);box.setChecked(bool(group) and all(n.get('boxMode') for n in group));box.blockSignals(False)
        bones=[n for n in self.nodes if n.get('workflow')=='bones']
        self.link_button.blockSignals(True);self.link_button.setChecked(bool(bones) and all(n.get('showLinks') for n in bones));self.link_button.blockSignals(False)
        for n in self.nodes:
            self.align_target.addItem(n['name'],n['id'])
            if n.get('workflow'):self.roster.addTopLevelItem(QTreeWidgetItem([n['name'],{'models':'模型','bones':'骨骼','controls':'控制器'}.get(n['workflow'],n['workflow'])]))
        self.align_target.setCurrentIndex(max(0,self.align_target.findData(previous)));self.rebuild_categories()
    def load_skin(self,data):
        super().load_skin(data)
        self._skin_bones={b['node']:b['id'] for b in data['bones']}
