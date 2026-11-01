"""Independent object roles and a resumable, per-model binding queue."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem,QHeaderView,QAbstractItemView,QSplitter,QWidget,QVBoxLayout,QLabel,QPushButton,QFrame,QTabWidget
from .scene_ui import role_label,prepare_tree

def category(node):
    return node.get('workflow') or ('bones' if node.get('bone') and node.get('class') not in ('Point','Dummy') else 'models' if node.get('geometry') else 'controls')

def ids(tree):return [i.data(0,Qt.ItemDataRole.UserRole) for i in tree.selectedItems()]

def items(tree):
    def walk(item):
        yield item
        for i in range(item.childCount()):yield from walk(item.child(i))
    for i in range(tree.topLevelItemCount()):yield from walk(tree.topLevelItem(i))

class SelectionMixin:
    def build_categories(self,layout):
        self.tree.hide();self.category_trees={}
        self.object_frame=QFrame();self.object_frame.setObjectName('objectBrowser')
        self.object_frame.setStyleSheet('''#objectBrowser {border:1px solid #dbe5c9; border-radius:5px; background:white;}
            #objectBrowser QTreeWidget {border:0; background:white;}
            #objectBrowser QTabWidget::pane {border:0; background:white;}
            #objectBrowser QTabBar {background:white;}
            #objectBrowser QTabBar::tab {background:white; color:#507522; padding:6px 12px; border:0;}
            #objectBrowser QTabBar::tab:selected {background:#edf5df; border-bottom:2px solid #86b83d;}''')
        frame_layout=QVBoxLayout(self.object_frame);frame_layout.setContentsMargins(0,0,0,0);frame_layout.setSpacing(0)
        self.category_split=QSplitter(Qt.Orientation.Vertical);self.category_split.setChildrenCollapsible(False);self.category_split.setHandleWidth(5)
        self.category_split.setStyleSheet('QSplitter::handle {background:#dbe5c9;}')
        self.role_tabs=QTabWidget();self.role_tabs.setDocumentMode(True)
        for key,title in [('models','模型 · 多选处理目标'),('bones','骨骼'),('controls','控制器')]:
            tree=QTreeWidget();prepare_tree(tree);tree.setMinimumHeight(65);tree.setFrameShape(QFrame.Shape.NoFrame)
            tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            tree.setHeaderLabels(['名称 / 层级','部位','影响值']);tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
            self.category_trees[key]=tree
            if key=='models':
                box=QWidget();v=QVBoxLayout(box);v.setContentsMargins(0,4,0,0);v.addWidget(QLabel(title));v.addWidget(tree)
                self.category_split.addWidget(box)
            else:self.role_tabs.addTab(tree,title)
            tree.itemSelectionChanged.connect(lambda c=key:self.category_changed(c))
        self.category_split.addWidget(self.role_tabs);self.category_split.setSizes([180,300])
        frame_layout.addWidget(self.category_split);layout.addWidget(self.object_frame,1)
        self.influence_button=QPushButton('选出所选模型的影响骨骼');self.influence_button.clicked.connect(lambda:self.guard(self.select_model_influences));layout.addWidget(self.influence_button)
        self.weight_summary=QLabel('模型选择与骨骼选择互不覆盖。');self.weight_summary.setWordWrap(True);layout.addWidget(self.weight_summary)
        self._preview_dirty=True;self._preview_signature=None
        self._bind_queue=[];self._bind_pool=[];self._bind_done=0;self._batch_auto=False;self._skin_bones={}
        self.preview_timer=QTimer(self);self.preview_timer.setInterval(600);self.preview_timer.timeout.connect(self.refresh_weight_view)
        if hasattr(self.owner,'scene_token'):self.preview_timer.start()

    def invalidate_preview(self,*_):self._preview_dirty=True

    def call(self,action,params=None,callback=None):
        def done(data):
            self.invalidate_preview()
            if callback:callback(data)
        return super().call(action,params,done)

    def selected_models(self):return ids(self.category_trees['models']) if hasattr(self,'category_trees') else []
    def selected_bones(self):
        if hasattr(self,'category_trees'):return ids(self.category_trees['bones'])
        return []
    def selected(self):
        if hasattr(self,'category_trees'):return self.selected_bones()+ids(self.category_trees['controls'])
        return super().selected()
    def selected_influences(self):return [self._skin_bones[n] for n in self.selected_bones() if n in self._skin_bones]
    def category_changed(self,key):
        if getattr(self,'_loading_categories',False):return
        if key=='models':
            chosen=self.selected_models();current=self.category_trees[key].currentItem()
            ref=current.data(0,Qt.ItemDataRole.UserRole) if current else (chosen[0] if chosen else None)
            if ref in chosen:self.mesh.setCurrentIndex(self.mesh.findData(ref))
        self._skin_bones={};self.invalidate_preview()
        if hasattr(self.owner,'scene_token'):
            from . import brush,max_host as H
            active=brush._active
            if active is not None and not active.holding:
                keys=[b['id'] for b in active.data['bones'] if b['node'] in self.selected_bones()]
                if key=='models' or not keys or set(keys)&set(active.locked):
                    brush.stop();self.notice.setText('编辑目标已改变，笔刷已停止；可重新开始绘制。')
                else:active.bones=keys
        # Read lazily on edit; the live summary does not change Max selection.
    def rebuild_categories(self):
        if not hasattr(self,'category_trees'):return
        self._loading_categories=True
        try:
            for key,tree in self.category_trees.items():
                selected=set(ids(tree));expanded={i.data(0,Qt.ItemDataRole.UserRole) for i in items(tree) if i.isExpanded()}
                tree.blockSignals(True);tree.clear();nodes=[n for n in self.nodes if category(n)==key];lookup={}
                for n in nodes:
                    i=QTreeWidgetItem([n['name'],role_label(n),'']);i.setData(0,Qt.ItemDataRole.UserRole,n['id']);lookup[n['id']]=i
                for n in nodes:
                    i=lookup[n['id']];parent=lookup.get(n['parent'])
                    if parent:parent.addChild(i)
                    else:tree.addTopLevelItem(i)
                    i.setSelected(n['id'] in selected);i.setExpanded(n['id'] in expanded or not expanded)
                tree.blockSignals(False)
            self.filter_categories()
        finally:self._loading_categories=False;self.invalidate_preview()
    def filter_categories(self):
        from .scene_ui import filter_tree
        for tree in getattr(self,'category_trees',{}).values():filter_tree(tree,self.nodes,self.scene_search.text(),self.workflow_only.isChecked())
    def choose_bone_nodes(self,refs):
        tree=self.category_trees['bones'];tree.blockSignals(True)
        for item in items(tree):item.setSelected(item.data(0,Qt.ItemDataRole.UserRole) in refs)
        tree.blockSignals(False);self.category_changed('bones')
    def select_model_influences(self):
        meshes=self.selected_models()
        if not meshes:raise ValueError('请在模型栏多选一个或多个模型')
        self.call('bind.influences',{'meshes':meshes},lambda d:self.choose_bone_nodes(set(d['bones'])))
    def refresh_weight_view(self):
        if self.busy or getattr(self,'_preview_running',False) or getattr(self.owner,'_preview_resizing',False) or not self.scene or not hasattr(self,'color_view') or not self.isVisible():return
        from . import weight_view,max_host as H
        if H.rt.theHold.Holding():return
        self._preview_running=True
        enabled=self.color_view.isChecked() and self.steps.currentIndex()==6
        signature=None
        try:
            signature=weight_view.signature(self.selected_models(),self.selected_bones(),self.steps.currentIndex(),self.color_view.isChecked())
            if not self._preview_dirty and signature==self._preview_signature:return
            rows=weight_view.update(self.selected_models(),self.selected_bones(),enabled)
            self._preview_signature=signature;self._preview_dirty=False
            means={};summary=[];self.vertex_values.clear()
            for row in rows:
                if not row['bound']:summary.append(row['name']+'：未蒙皮');continue
                summary.append('%s：所选骨骼合计 %.3f（%d 顶点均值）'%(row['name'],row['mean'],row['sampleCount']))
                for bone,v in row['bones'].items():means.setdefault(bone,[]).append(v)
                if enabled:
                    for vertex,value in row['vertices']:self.vertex_values.addTopLevelItem(QTreeWidgetItem([row['name'],str(vertex),'%.6f'%value]))
            self.weight_summary.setText('\n'.join(summary) or '先在模型栏选择目标，在骨骼栏选择影响骨骼。')
            for i in items(self.category_trees['bones']):
                values=means.get(i.data(0,Qt.ItemDataRole.UserRole),[]);i.setText(2,'%.3f'%(sum(values)/max(1,sum(r['bound'] for r in rows))) if values else '—')
            for i in items(self.category_trees['models']):
                row=next((r for r in rows if r['mesh']==i.data(0,Qt.ItemDataRole.UserRole)),None)
                i.setText(2,'%.3f'%row['mean'] if row and row['bound'] else '')
        except Exception as e:
            self._preview_signature=signature;self._preview_dirty=False
            weight_view.clear();self.weight_summary.setText('权重预览：'+str(e))
        finally:self._preview_running=False
    def bind_options(self):return dict(method=self.bind_method.currentData(),limit=self.bind_limit.value(),falloff=self.falloff.value(),resolution=self.resolution.value())
    def start_bind_queue(self,automatic=False):
        if self._bind_queue:raise ValueError('当前队列尚未结束，请完成或停止后再开始')
        models=self.selected_models()
        if not models:raise ValueError('请在模型栏选择要蒙皮的模型，可 Ctrl / Shift 多选')
        self._bind_queue=list(models);self._bind_pool=self.selected_bones();self._bind_done=0;self._batch_auto=automatic
        self.prepare_bind_model()
    def prepare_bind_model(self):
        if not self._bind_queue:
            self.bind_progress.setText('队列完成：已蒙皮 %d 个模型'%self._bind_done);self.call('scene.inspect',{},self.load_scene);return
        ref=self._bind_queue[0];self.mesh.setCurrentIndex(self.mesh.findData(ref))
        self.bind_progress.setText('当前：%s · 剩余 %d 个；正在推荐影响骨骼'%(self.mesh.currentText(),len(self._bind_queue)))
        self.call('bind.suggest',{'mesh':ref,'pool':self._bind_pool,'limit':self.bind_limit.value()},self.bind_suggested)
    def bind_suggested(self,data):
        if not self._bind_queue:return
        self.choose_bone_nodes(set(data['bones']));self.bind_progress.setText('当前：%s · 请调整骨骼栏多选，然后点「确认此模型并下一步」'%self.mesh.currentText())
        if self._batch_auto:self.confirm_bind_model()
    def confirm_bind_model(self):
        if not self._bind_queue:raise ValueError('请先开始分步或批量蒙皮')
        bones=self.selected_bones()
        if not bones:raise ValueError('当前模型至少需要一根影响骨骼')
        ref=self._bind_queue[0]
        def done(data):
            self._bind_queue.pop(0);self._bind_done+=1;self.prepare_bind_model()
        self.call('bind.auto',dict(self.bind_options(),mesh=ref,bones=bones),done)
    def skip_bind_model(self):
        if self._bind_queue:self._bind_queue.pop(0);self.prepare_bind_model()
    def stop_bind_queue(self):
        self._bind_queue=[];self.bind_progress.setText('队列已停止；已完成模型保留，可分别撤销。')
    def edit_influences(self,callback):
        if not self.selected_bones():raise ValueError('请在骨骼栏选择影响骨骼')
        def loaded(data):
            self.load_skin(data)
            if not self.selected_influences():raise ValueError('所选骨骼尚未影响当前模型')
            callback()
        self.call('skin.inspect',self.params(),loaded)
