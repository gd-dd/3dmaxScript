"""Shared scene navigation and forms that adapt to a wide floating window."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QBoxLayout,QFormLayout,QSizePolicy,QHeaderView

def role_label(node):
    role=node.get('role','');side=''
    if role.startswith(('L_','R_')):side='左 · ' if role[0]=='L' else '右 · ';role=role[2:]
    part=role.split('_')[0]
    names={'BodyCenter':'身体质心','Root':'世界根控制器','Pelvis':'骨盆 / 摆胯','Spine':'脊柱','Neck':'颈部','Head':'头部',
           'Clavicle':'肩 / 锁骨','UpperArm':'上臂','Forearm':'前臂','Hand':'手掌','Thigh':'大腿','Calf':'小腿','Foot':'脚掌','Controller':'控制器','Guide':'定位点','IK':'IK 目标'}
    if part.startswith('Finger'):label='手指 '+part[6:]
    elif part.startswith('Toe'):label='脚趾 '+part[3:]
    else:label=names.get(part,'')
    if label:
        suffix=role[len(part):].strip('_');return side+label+(' · '+suffix if suffix else '')
    return {'models':'模型','bones':'骨骼','controls':'控制器 / 辅助体'}.get(node.get('workflow')) or ('骨骼' if node.get('bone') else '模型' if node.get('geometry') else node.get('class','对象'))

class Columns(QWidget):
    def __init__(self,rows,split,parent=None):
        super().__init__(parent);self.box=QBoxLayout(QBoxLayout.Direction.LeftToRight,self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(18)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        for group in (rows[:split],rows[split:]):
            column=QWidget();form=QFormLayout(column);form.setContentsMargins(0,0,0,0)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            for label,field in group:
                if label is not None:form.addRow(label,field)
                elif field is not None:form.addRow(field)
            self.box.addWidget(column,1)
    def resizeEvent(self,event):
        self.box.setDirection(QBoxLayout.Direction.LeftToRight if self.width()>=690 else QBoxLayout.Direction.TopToBottom)
        super().resizeEvent(event)

def split_form(form,split):
    rows=[]
    while form.rowCount():
        row=form.takeRow(0)
        def content(item):return (item.widget() or item.layout()) if item else None
        rows.append((content(row.labelItem),content(row.fieldItem)))
    columns=Columns(rows,split);form.addRow(columns);return columns

def prepare_tree(tree):
    tree.setMinimumHeight(100);tree.setMaximumHeight(16777215);tree.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    tree.setHeaderLabels(['对象层级','部位 / 类型']);tree.setIndentation(18);tree.setUniformRowHeights(True)
    tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Interactive);tree.setColumnWidth(0,215)
    tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)

def decorate_tree(tree,nodes):
    by_id={n['id']:n for n in nodes}
    def visit(item):
        n=by_id.get(item.data(0,Qt.ItemDataRole.UserRole))
        if n:
            item.setText(1,role_label(n));item.setToolTip(0,n['name']+'\n'+role_label(n));item.setToolTip(1,n.get('class',''))
        for i in range(item.childCount()):visit(item.child(i))
    for i in range(tree.topLevelItemCount()):visit(tree.topLevelItem(i))

def filter_tree(tree,nodes,text,workflow_only):
    by_id={n['id']:n for n in nodes};needle=text.strip().casefold()
    has_members=any(n.get('workflow') for n in nodes)
    def visit(item):
        n=by_id.get(item.data(0,Qt.ItemDataRole.UserRole),{})
        direct=(not workflow_only or not has_members or bool(n.get('workflow'))) and (not needle or needle in (n.get('name','')+' '+role_label(n)).casefold())
        descendant=False
        for i in range(item.childCount()):descendant=visit(item.child(i)) or descendant
        show=direct or descendant;item.setHidden(not show)
        if needle and descendant:item.setExpanded(True)
        return show
    for i in range(tree.topLevelItemCount()):visit(tree.topLevelItem(i))
