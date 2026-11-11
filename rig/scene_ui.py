"""Shared scene navigation and forms that adapt to a wide floating window."""
from PySide6.QtCore import Qt,QSize,QRect
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QWidget,QBoxLayout,QFormLayout,QSizePolicy,QHeaderView,
    QPushButton,QGridLayout,QVBoxLayout,QHBoxLayout,QLabel,QScrollArea,QFrame,
    QStackedWidget,QStylePainter,QStyleOptionButton,QStyle,QCheckBox)


class WrapButton(QPushButton):
    """Keep the full action name readable at narrow panel widths."""
    def __init__(self,text,parent=None):
        super().__init__(text,parent);self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        policy=self.sizePolicy();policy.setHeightForWidth(True);self.setSizePolicy(policy)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):
        rect=self.fontMetrics().boundingRect(QRect(0,0,max(20,width-28),10000),int(Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignCenter),self.text())
        return max(34,rect.height()+20)
    def sizeHint(self):return QSize(180,self.heightForWidth(180))
    def minimumSizeHint(self):return QSize(72,self.heightForWidth(100))
    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option);option.text=''
        painter=QStylePainter(self);painter.drawControl(QStyle.ControlElement.CE_PushButton,option)
        rect=self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents,option,self)
        group=QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group,QPalette.ColorRole.ButtonText))
        painter.drawText(rect.adjusted(4,2,-4,-2),int(Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignCenter),self.text())


class ActionRow(QWidget):
    def __init__(self,items,guard,parent=None):
        super().__init__(parent);self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0)
        self.buttons=[];self.columns=0
        policy=self.sizePolicy();policy.setHeightForWidth(True);self.setSizePolicy(policy)
        for title,callback in items:
            button=WrapButton(title);button.clicked.connect(lambda checked=False,f=callback:guard(f));self.buttons.append(button)
        self.arrange(1)
    def arrange(self,columns):
        if columns==self.columns:return
        self.columns=columns
        for button in self.buttons:self.grid.removeWidget(button)
        for i,button in enumerate(self.buttons):self.grid.addWidget(button,i//columns,i%columns)
        self.grid.invalidate();self.updateGeometry()
    def heightForWidth(self,width):
        columns=2 if width>=360 else 1;gap=self.grid.verticalSpacing()
        button_width=max(20,(width-self.grid.horizontalSpacing()*(columns-1))//columns)
        heights=[max(b.heightForWidth(button_width) for b in self.buttons[i:i+columns]) for i in range(0,len(self.buttons),columns)]
        return sum(heights)+max(0,len(heights)-1)*gap
    def minimumSizeHint(self):return QSize(72,0)
    def sizeHint(self):return QSize(360,self.heightForWidth(360))
    def resizeEvent(self,event):
        self.arrange(2 if self.width()>=360 else 1)
        height=self.heightForWidth(self.width())
        if self.minimumHeight()!=height:self.setMinimumHeight(height);self.updateGeometry()
        super().resizeEvent(event)


class WrapCheckBox(QCheckBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        policy=self.sizePolicy();policy.setHeightForWidth(True);self.setSizePolicy(policy)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):
        rect=self.fontMetrics().boundingRect(QRect(0,0,max(20,width-38),10000),int(Qt.TextFlag.TextWordWrap),self.text())
        return max(28,rect.height()+12)
    def sizeHint(self):return QSize(220,self.heightForWidth(220))
    def minimumSizeHint(self):return QSize(72,self.heightForWidth(100))
    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option);option.text=''
        painter=QStylePainter(self);painter.drawControl(QStyle.ControlElement.CE_CheckBox,option)
        rect=self.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents,option,self)
        group=QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group,QPalette.ColorRole.WindowText))
        painter.drawText(rect,int(Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignVCenter),self.text())
    def hitButton(self,point):return self.rect().contains(point)


class WrapLabel(QLabel):
    """Long scene identifiers wrap as well as Chinese prose, without widening a page."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setWordWrap(True)
        policy=self.sizePolicy();policy.setHeightForWidth(True);self.setSizePolicy(policy)
    def minimumSizeHint(self):return QSize(0,self.fontMetrics().height())
    def sizeHint(self):return QSize(280,self.heightForWidth(280))
    def heightForWidth(self,width):
        flags=int(Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere)
        return self.fontMetrics().boundingRect(QRect(0,0,max(20,width),10000),flags,self.text()).height()+4
    def paintEvent(self,event):
        painter=QStylePainter(self);painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.drawText(self.contentsRect(),int(Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere|Qt.AlignmentFlag.AlignVCenter),self.text())


def take_rows(form):
    rows=[]
    while form.rowCount():
        row=form.takeRow(0)
        def value(item):return (item.widget() or item.layout()) if item else None
        rows.append((value(row.labelItem),value(row.fieldItem)))
    return rows


def add_rows(form,rows):
    for label,field in rows:
        if label is not None:form.addRow(label,field)
        elif field is not None:form.addRow(field)


def scroll_form(rows=()):
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumSize(0,0);scroll.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
    widget=QWidget();form=QFormLayout(widget);form.setContentsMargins(4,4,10,8)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    add_rows(form,rows);scroll.setWidget(widget)
    return scroll,form


class WorkspaceStack(QStackedWidget):
    def minimumSizeHint(self):return QSize(0,0)
    def sizeHint(self):return QSize(400,400)


class SectionNavigator(QWidget):
    """In-panel task pages. Reparent existing fields; retain drafts/signals."""
    def __init__(self,rows=(),parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.stack=WorkspaceStack();layout.addWidget(self.stack)
        self.overview,self.overview_form=scroll_form(rows);self.stack.addWidget(self.overview)
        self.details={};self.detail_buttons={}
    def add_detail(self,title,rows):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0)
        bar=QHBoxLayout();back=WrapButton('‹ 返回当前步骤');back.setObjectName('detailBack');back.clicked.connect(self.back)
        label=QLabel(title);label.setWordWrap(True);bar.addWidget(back);bar.addWidget(label,1);layout.addLayout(bar)
        scroll,form=scroll_form(rows);layout.addWidget(scroll,1)
        self.stack.addWidget(page);self.details[title]=page
        button=WrapButton(title+' ›');button.setObjectName('detailLink');button.clicked.connect(lambda:self.open_detail(title))
        self.detail_buttons[title]=button;self.overview_form.addRow(button)
        return form
    def open_detail(self,title):self.stack.setCurrentWidget(self.details[title])
    def back(self):self.stack.setCurrentIndex(0)

def role_label(node):
    if str(node.get('class','')).lower()=='biped_object':
        return 'Biped 骨骼' if node.get('category')=='bones' else 'Biped 控制器'
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
        direction=QBoxLayout.Direction.LeftToRight if self.width()>=690 else QBoxLayout.Direction.TopToBottom
        if self.box.direction()!=direction:self.box.setDirection(direction)
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
