"""Max workbench content. UI sends local typed commands, never source strings."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QComboBox,QLineEdit,QDoubleSpinBox,QSpinBox,QTabWidget,QTreeWidget,
    QTreeWidgetItem,QAbstractItemView,QCheckBox,QFileDialog,QScrollArea,QFrame,QHeaderView,QGridLayout)


class WheelSafeSpinBox(QSpinBox):
    def wheelEvent(self,event):event.ignore()

class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self,event):event.ignore()


class RigWorkbench(QWidget):
    def __init__(self, owner):
        super().__init__();self.owner=owner;self.session=None;self.scene=None;self.nodes=[];self.profile={};self.busy=False
        root=QVBoxLayout(self);root.setContentsMargins(0,8,0,0)
        self.notice=QLabel('读取当前 Max 场景，开始绑定与蒙皮。');self.notice.setWordWrap(True);root.addWidget(self.notice)
        self.refresh=QPushButton('读取 / 刷新场景');self.refresh.clicked.connect(lambda:self.call('scene.inspect',{},self.load_scene));root.addWidget(self.refresh)
        self.cancel=QPushButton('取消尚未开始的操作');self.cancel.hide();self.cancel.clicked.connect(lambda:self.owner.command('cancel-rig',requestId=getattr(self,'request_id',None),sessionId=self.session));root.addWidget(self.cancel)
        self.body=QWidget();root.addWidget(self.body);layout=QVBoxLayout(self.body)
        form=QFormLayout();layout.addLayout(form)
        self.mesh=QComboBox();self.skin=QComboBox();form.addRow('当前模型',self.mesh);form.addRow('Skin 修改器',self.skin)
        self.actions(form,('读取当前模型权重 / 角色配置',self.read_details))
        self.mesh.currentIndexChanged.connect(self.mesh_changed)
        self.skin.currentIndexChanged.connect(self.invalidate_skin)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self.skeleton=self.page('骨骼与绑定')
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['骨骼 / 对象','类型']);self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.tree.setFixedHeight(180);self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.skeleton.addRow(self.tree)
        self.actions(self.skeleton,('同步选择到 Max',lambda:self.call('nodes.select',{'nodes':self.selected()})),('建立 Skin 绑定',lambda:self.mutate('bind.create',{'bones':self.selected()})),('添加影响骨骼',lambda:self.mutate('bind.add',{'bones':self.selected()})))
        self.name=QLineEdit('LX_Bone');self.skeleton.addRow('骨骼名称',self.name)
        self.start=QLineEdit('0, 0, 0');self.end=QLineEdit('0, 0, 10');self.skeleton.addRow('起点 X, Y, Z',self.start);self.skeleton.addRow('终点 X, Y, Z',self.end)
        self.parent=QComboBox();self.skeleton.addRow('父对象',self.parent)
        self.actions(self.skeleton,('新建骨骼',self.create_bone),('重命名选中对象',lambda:self.mutate('bone.rename',{'node':self.one(),'name':self.name.text()})),('设置父对象',lambda:self.mutate('bone.parent',{'node':self.one(),'parent':self.parent.currentData()})))
        self.actions(self.skeleton,('记录所选骨骼姿态',lambda:self.mutate('pose.capture',{'bones':self.selected()})),('恢复记录姿态',lambda:self.mutate('pose.restore')))
        self.confirm=QCheckBox('确认移除当前 Skin（完整恢复请使用 Max 撤销）');self.skeleton.addRow(self.confirm)
        self.actions(self.skeleton,('解除绑定',self.unbind))
        w=self.page('权重')
        self.info=QLabel('读取 Skin 后显示顶点和影响骨骼');self.info.setWordWrap(True);w.addRow(self.info)
        self.actions(w,('读取 Skin / 当前选择',self.read_skin))
        self.scope=QComboBox();self.scope.addItem('仅 Max 中选中的 Skin 顶点','selected');self.scope.addItem('全部顶点','all');w.addRow('作用范围',self.scope)
        self.bone=QComboBox();w.addRow('编辑影响骨骼',self.bone)
        self.value=self.number(-1,1,.5,.05);w.addRow('权重值 / 增量',self.value)
        self.actions(w,('设置权重',lambda:self.weight('set')),('增加 / 减少',lambda:self.weight('add')),('归一化',lambda:self.weight('normalize')))
        self.strength=self.number(0,1,.5,.1);self.iterations=self.integer(1,50,1);w.addRow('平滑强度',self.strength);w.addRow('平滑次数',self.iterations)
        self.limit=self.integer(1,100,4);self.threshold=self.number(0,1,.001,.001);w.addRow('最大影响数',self.limit);w.addRow('清理阈值',self.threshold)
        self.actions(w,('平滑',lambda:self.weight('smooth')),('清理小权重',lambda:self.weight('prune')))
        self.locks=QTreeWidget();self.locks.setHeaderLabels(['锁定影响骨骼（仅权重页编辑）','当前顶点权重']);w.addRow(self.locks)
        self.actions(w,('保存锁定设置',self.save_locks),('移除零权重影响',lambda:self.mutate('bind.remove',{'bone':self.bone.currentData()})))
        x=self.page('镜像与交换')
        self.pair_a=QComboBox();self.pair_b=QComboBox();x.addRow('左右骨骼 A',self.pair_a);x.addRow('左右骨骼 B',self.pair_b)
        self.pairs=QLabel('未设置左右配对；未配对骨骼保持原影响名称');self.pairs.setWordWrap(True);x.addRow(self.pairs)
        self.actions(x,('保存左右配对',self.save_pair),('清空配对',self.clear_pairs))
        self.axis=QComboBox();self.axis.addItems(['X','Y','Z']);self.direction=QComboBox();self.direction.addItem('正侧 → 负侧','positive');self.direction.addItem('负侧 → 正侧','negative');self.direction.addItem('左右交换','flip')
        self.offset=self.number(-1000000,1000000,0,1);self.tolerance=self.number(.000001,1000000,.01,.01)
        x.addRow('局部镜像轴',self.axis);x.addRow('镜像方向',self.direction);x.addRow('平面偏移',self.offset);x.addRow('匹配容差',self.tolerance)
        self.actions(x,('镜像当前作用范围',lambda:self.mutate('weights.mirror',{'axis':self.axis.currentIndex(),'direction':self.direction.currentData(),'offset':self.offset.value(),'tolerance':self.tolerance.value(),'scope':self.scope.currentData()})))
        self.source=QComboBox();self.source_skin=QComboBox();self.source.currentIndexChanged.connect(self.source_changed);self.distance=self.number(.000001,1000000,1,.1)
        x.addRow('传递来源模型',self.source);x.addRow('来源 Skin',self.source_skin);x.addRow('世界空间最大距离',self.distance)
        self.actions(x,('传递到当前模型全部顶点',lambda:self.mutate('weights.transfer',{'source':self.source.currentData(),'sourceSkin':self.source_skin.currentData() or 0,'distance':self.distance.value()})),('导出权重',lambda:self.file_action(False)),('导入同拓扑权重',lambda:self.file_action(True)))
        f=self.page('人形与表情')
        self.role_group=QComboBox();self.role_group.addItem('人形骨骼','humanoid');self.role_group.addItem('面部骨骼','face');f.addRow('适配类型',self.role_group)
        self.role=QComboBox();self.role.setEditable(True);self.role.addItems(['hips','spine','chest','neck','head','leftUpperArm','leftLowerArm','leftHand','rightUpperArm','rightLowerArm','rightHand','leftUpperLeg','leftLowerLeg','leftFoot','rightUpperLeg','rightLowerLeg','rightFoot','jaw','leftEye','rightEye','tongue','upperLip','lowerLip']);f.addRow('语义角色（可自定义）',self.role)
        self.mapping=QTreeWidget();self.mapping.setHeaderLabels(['角色','对象']);f.addRow(self.mapping)
        self.actions(f,('将骨骼页所选对象指定为角色',self.save_role),('移除当前角色',self.remove_role))
        self.morph_target=QComboBox();f.addRow('同拓扑表情目标',self.morph_target)
        self.morph_index=self.integer(1,100,1);self.morph_name=QLineEdit();f.addRow('新通道编号',self.morph_index);f.addRow('表情名称',self.morph_name)
        self.actions(f,('建立表情通道',lambda:self.mutate('morph.add',{'target':self.morph_target.currentData(),'channel':self.morph_index.value(),'name':self.morph_name.text()},self.read_morph)),('读取表情通道',self.read_morph))
        self.channel=QComboBox();self.morph_value=self.number(-100,100,0,5);f.addRow('预览通道',self.channel);f.addRow('表情值',self.morph_value)
        self.actions(f,('应用表情值',self.apply_morph),('全部表情归零',lambda:self.mutate('morph.reset',self.morph_params(),self.read_morph)))
        d=self.page('检查与恢复');self.diagnostics=QLabel('权重修改自动创建快照。快照只保存权重，不替代场景文件。');self.diagnostics.setWordWrap(True);d.addRow(self.diagnostics)
        self.snapshots=QComboBox();d.addRow('权重快照',self.snapshots)
        self.actions(d,('检查当前 Skin',lambda:self.call('skin.check',self.params(),self.checked)),('选择问题顶点',lambda:self.call('vertices.select',self.params(vertices=getattr(self,'issues',[])))),('保存快照',lambda:self.mutate('snapshot.create')),('读取快照列表',lambda:self.call('snapshot.list',self.params(),self.load_snapshots)),('恢复所选快照',lambda:self.mutate('snapshot.restore',{'snapshot':self.snapshots.currentData()})))
        self.set_target(None)

    def page(self,title):
        widget=QWidget();form=QFormLayout(widget);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(widget);self.tabs.addTab(scroll,title);return form
    def actions(self,form,*items):
        row=QGridLayout()
        for index,(title,fn) in enumerate(items):
            button=QPushButton(title);button.clicked.connect(lambda checked=False,f=fn:self.guard(f));row.addWidget(button,index//2,index%2)
        form.addRow(row)
    def guard(self,fn):
        try:fn()
        except Exception as e:self.notice.setText(str(e))
    def number(self,low,high,value,step):
        w=WheelSafeDoubleSpinBox();w.setDecimals(6);w.setRange(low,high);w.setValue(value);w.setSingleStep(step);return w
    def integer(self,low,high,value):
        w=WheelSafeSpinBox();w.setRange(low,high);w.setValue(value);return w
    def set_target(self,session):
        if session!=self.session:
            self.session=session;self.scene=None;self.nodes=[];self.mesh.clear();self.tree.clear();self.busy=False;self.notice.setText('当前场景已改变，请读取场景。')
        self.refresh.setEnabled(bool(session) and not self.busy);self.body.setEnabled(bool(self.scene) and not self.busy)
        self.cancel.setVisible(self.busy)
    def params(self,**extra):return dict(mesh=self.mesh.currentData(),skin=self.skin.currentData() or 0,skinHandle=self.skin.currentData(Qt.ItemDataRole.UserRole+1),**extra)
    def call(self,action,params=None,callback=None):
        if self.busy:raise ValueError('请等待当前操作完成')
        if not self.session:raise ValueError('当前 Max 场景尚未就绪')
        session=self.session;self.busy=True;self.set_target(session);self.notice.setText('正在执行：'+action)
        def done(result):
            if self.session!=session:return
            self.busy=False;self.set_target(session)
            if not result.get('ok'):self.notice.setText(result.get('error','操作失败'));return
            data=result.get('data',{});self.notice.setText(data.get('message','读取完成'))
            if callback:self.guard(lambda:callback(data))
        self.request_id=self.owner.rig_command({'action':action,'scene':self.scene,'params':params or {}},done)
    def mutate(self,action,extra=None,after=None):
        self.call(action,self.params(**(extra or {})),lambda data:after() if after else self.call('scene.inspect',{},self.load_scene))
    def selected(self):return [i.data(0,Qt.ItemDataRole.UserRole) for i in self.tree.selectedItems()]
    def one(self):
        ids=self.selected()
        if len(ids)!=1:raise ValueError('请在骨骼页选择一个对象')
        return ids[0]
    def create_bone(self):self.mutate('bone.create',{'name':self.name.text(),'start':[float(v) for v in self.start.text().split(',')],'end':[float(v) for v in self.end.text().split(',')],'parent':self.parent.currentData()})
    def unbind(self):
        if not self.confirm.isChecked():raise ValueError('请勾选解除绑定确认')
        self.confirm.setChecked(False);self.mutate('bind.unbind')
    def load_scene(self,data):
        previous=self.mesh.currentData();self.scene=data['scene'];self.nodes=data['nodes'];self.tree.clear();self.mesh.blockSignals(True)
        for combo in (self.mesh,self.source,self.morph_target,self.parent):combo.clear()
        self.parent.addItem('世界（无父对象）',None);items={}
        for n in self.nodes:
            item=QTreeWidgetItem([n['name'],n['class']]);item.setData(0,Qt.ItemDataRole.UserRole,n['id']);items[n['id']]=item
            self.parent.addItem(n['name'],n['id'])
            if n['geometry'] and not n.get('bone',False):
                for combo in (self.mesh,self.source,self.morph_target):combo.addItem(n['name'],n['id'])
        for n in self.nodes:
            item=items[n['id']];parent=items.get(n['parent'])
            if parent:parent.addChild(item)
            else:self.tree.addTopLevelItem(item)
            item.setSelected(n['selected'])
        self.tree.expandToDepth(1);self.mesh.setCurrentIndex(max(0,self.mesh.findData(previous)));self.mesh.blockSignals(False);self.mesh_changed();self.set_target(self.session)
    def mesh_changed(self,*args):
        self.skin.clear();self.profile={};self.bone.clear();self.locks.clear();self.mapping.clear();self.channel.clear();self.snapshots.clear();self.pair_a.clear();self.pair_b.clear();self.pairs.setText('请读取 Skin');self.info.setText('请读取当前模型 Skin')
        for n in self.nodes:
            if n['id']==self.mesh.currentData():
                for s in n['skins']:
                    self.skin.addItem(s['name'],s['index']);self.skin.setItemData(self.skin.count()-1,s.get('handle'),Qt.ItemDataRole.UserRole+1)
    def invalidate_skin(self,*args):
        self.profile={};self.bone.clear();self.locks.clear();self.pair_a.clear();self.pair_b.clear();self.pairs.setText('请重新读取 Skin');self.info.setText('请读取当前 Skin 的权重与配置')
    def source_changed(self,*args):
        self.source_skin.clear()
        for n in self.nodes:
            if n['id']==self.source.currentData():
                for s in n['skins']:self.source_skin.addItem(s['name'],s['index'])
    def read_skin(self):self.call('skin.inspect',self.params(),self.load_skin)
    def read_details(self):
        if self.skin.count():self.read_skin()
        else:self.call('profile.inspect',self.params(),self.load_profile)
    def load_profile(self,data):
        self.profile=data['profile'];self.mapping.clear();nodes={n['id']:n['name'] for n in self.nodes}
        for group in ('humanoid','face'):
            for role,ref in self.profile.get(group,{}).items():self.mapping.addTopLevelItem(QTreeWidgetItem([group+' / '+role,nodes.get(ref,'已删除')]))
    def load_skin(self,data):
        self.profile=data['profile'];self.info.setText('%d 个顶点 · 已选 %d · 当前顶点 %d'%(data['count'],data['selectedCount'],data['vertex']))
        for c in (self.bone,self.pair_a,self.pair_b):c.clear()
        self.locks.clear();names={}
        for b in data['bones']:
            names[b['id']]=b['name']
            for c in (self.bone,self.pair_a,self.pair_b):c.addItem(b['name'],b['id'])
            item=QTreeWidgetItem([b['name'],'%.6f'%data['weights'].get(b['id'],0)]);item.setData(0,Qt.ItemDataRole.UserRole,b['id']);item.setCheckState(0,Qt.CheckState.Checked if b['id'] in self.profile.get('locked',[]) else Qt.CheckState.Unchecked);self.locks.addTopLevelItem(item)
        self.pairs.setText(' / '.join(names.get(a,a)+' ↔ '+names.get(b,b) for a,b in self.profile.get('pairs',{}).items() if a<b) or '无左右配对')
        self.mapping.clear();nodes={n['id']:n['name'] for n in self.nodes}
        for group in ('humanoid','face'):
            for role,ref in self.profile.get(group,{}).items():self.mapping.addTopLevelItem(QTreeWidgetItem([group+' / '+role,nodes.get(ref,'已删除')]))
        self.load_snapshots(data)
    def weight(self,mode):self.mutate('weights.edit',{'mode':mode,'bone':self.bone.currentData(),'value':self.value.value(),'scope':self.scope.currentData(),'locked':self.profile.get('locked',[]),'strength':self.strength.value(),'iterations':self.iterations.value(),'threshold':self.threshold.value(),'limit':self.limit.value()},self.read_skin)
    def save_profile(self):
        if not self.profile:raise ValueError('请先读取模型权重 / 角色配置')
        self.mutate('profile.save',{'profile':self.profile},self.read_details)
    def save_locks(self):
        self.profile['locked']=[self.locks.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole) for i in range(self.locks.topLevelItemCount()) if self.locks.topLevelItem(i).checkState(0)==Qt.CheckState.Checked];self.save_profile()
    def save_pair(self):
        a,b=self.pair_a.currentData(),self.pair_b.currentData()
        if not a or not b or a==b:raise ValueError('请选择两个不同影响骨骼')
        pairs=self.profile.setdefault('pairs',{})
        for key in (a,b):
            old=pairs.pop(key,None)
            if old:pairs.pop(old,None)
        pairs[a]=b;pairs[b]=a;self.save_profile()
    def clear_pairs(self):self.profile['pairs']={};self.save_profile()
    def save_role(self):self.profile.setdefault(self.role_group.currentData(),{})[self.role.currentText()]=self.one();self.save_profile()
    def remove_role(self):self.profile.setdefault(self.role_group.currentData(),{}).pop(self.role.currentText(),None);self.save_profile()
    def file_action(self,importing):
        path,_=(QFileDialog.getOpenFileName if importing else QFileDialog.getSaveFileName)(self,'导入权重' if importing else '导出权重','','JSON (*.json)')
        if path:self.mutate('weights.import' if importing else 'weights.export',{'path':path,'overwrite':not importing},self.read_skin)
    def read_morph(self):self.call('morph.inspect',self.params(),self.load_morph)
    def load_morph(self,data):
        self.channel.clear()
        for m in data['morphers']:
            for c in m['channels']:self.channel.addItem(m['name']+' / '+c['name']+' (%.1f)'%c['value'],{'morpher':m['index'],'channel':c['index']})
    def morph_params(self):
        data=self.channel.currentData()
        if not data:raise ValueError('请先读取并选择表情通道')
        return dict(data)
    def apply_morph(self):self.mutate('morph.value',dict(self.morph_params(),value=self.morph_value.value()),self.read_morph)
    def load_snapshots(self,data):
        self.snapshots.clear()
        for s in data.get('snapshots',[]):self.snapshots.addItem(s['label']+' · '+s['id'][:8],s['id'])
    def checked(self,data):
        self.issues=data['vertices'];self.diagnostics.setText(data['message']+'\n'+'\n'.join(str(x['vertex'])+': '+', '.join(x['issues']) for x in data['issues'][:30]))
