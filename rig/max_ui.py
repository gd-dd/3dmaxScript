"""Max-owned dock and local command queue. Never starts another process."""
import uuid
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSize
from PySide6.QtGui import QIcon,QPixmap,QFont
from PySide6.QtWidgets import QDockWidget,QWidget,QVBoxLayout,QHBoxLayout,QLabel
from pymxs import runtime as rt
import qtmax
from .max_host import dispatch
from .workbench import RigWorkbench

ROOT=Path(__file__).resolve().parents[1]
_dock=None

class RigDock(QDockWidget):
    def __init__(self,parent):
        super().__init__('LX 绑定蒙皮',parent)
        self.setObjectName('LXRigSkinDock');self.setWindowIcon(QIcon(str(ROOT/'.lxtool/icon.png')))
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea|Qt.DockWidgetArea.RightDockWidgetArea)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        self.queue={};self.closed=False;self.scene_token=str(rt.LXRigSceneToken)
        content=QWidget();content.setFont(QFont('Microsoft YaHei UI',9));self.setWidget(content)
        layout=QVBoxLayout(content);layout.setContentsMargins(10,10,10,10)
        header=QHBoxLayout();icon=QLabel();icon.setPixmap(QPixmap(str(ROOT/'.lxtool/icon.png')).scaled(52,52,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));header.addWidget(icon)
        title=QLabel('LX 绑定蒙皮\n骨骼 · 权重 · 人形 · 表情');title.setStyleSheet('font-size:15px;font-weight:600;color:#bddc93');header.addWidget(title,1);layout.addLayout(header)
        self.workbench=RigWorkbench(self);layout.addWidget(self.workbench,1)
        self.workbench.set_target(self.scene_token);self.workbench.notice.setText('直接操作当前 Max 场景。请读取场景并选择模型。')
        content.setStyleSheet('QWidget {color:#e5e9e0;} QLabel {background:transparent;} QPushButton {background:#394437;border:1px solid #57674e;border-radius:5px;padding:7px;} QPushButton:hover {background:#4b603d;} QPushButton:disabled {color:#858c80;} QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {background:#30342e;border:1px solid #515a48;border-radius:3px;padding:4px;} QTreeWidget {background:#2c302a;alternate-background-color:#343a30;} QTreeWidget::item:selected {background:#506b3b;} QTabWidget::pane {border:1px solid #515a48;} QTabBar::tab {padding:7px;background:#30362c;} QTabBar::tab:selected {background:#506b3b;}')
        content.setAutoFillBackground(True)
        palette=content.palette();palette.setColor(content.backgroundRole(),'#272c25');content.setPalette(palette)
        self.setMinimumWidth(520)
        qtmax.DisableMaxAcceleratorsOnFocus(self,True)
        self.scene_timer=QTimer(self);self.scene_timer.setInterval(500);self.scene_timer.timeout.connect(self.check_scene);self.scene_timer.start()
        QTimer.singleShot(0,self.refresh_scene)

    def sizeHint(self):return QSize(650,780)
    def check_scene(self):
        token=str(rt.LXRigSceneToken)
        if token!=self.scene_token:
            self.scene_token=token;self.queue.clear();self.workbench.set_target(token)
            self.workbench.notice.setText('Max 场景已切换，请重新读取场景。')
    def refresh_scene(self):
        if not self.closed:
            self.check_scene();self.workbench.guard(lambda:self.workbench.call('scene.inspect',{},self.workbench.load_scene))
    def rig_command(self,request,callback):
        identity=uuid.uuid4().hex;self.queue[identity]=(request,callback)
        def execute():
            item=self.queue.pop(identity,None)
            if self.closed or item is None:return
            req,done=item
            # Leave the MAXScript startup evaluation before enabling undo.
            try:result={'ok':True,'data':dispatch(req)}
            except Exception as error:result={'ok':False,'error':str(error)}
            if not self.closed:done(result)
        QTimer.singleShot(0,execute)
        return identity
    def command(self,op,**params):
        if op!='cancel-rig':return
        item=self.queue.pop(params.get('requestId'),None)
        if item:item[1]({'ok':False,'error':'尚未开始的操作已取消。'})
    def closeEvent(self,event):
        self.closed=True;self.queue.clear();self.scene_timer.stop();super().closeEvent(event)

def show_workbench():
    global _dock
    from shiboken6 import isValid
    if _dock is not None and isValid(_dock) and not _dock.closed:
        _dock.show();_dock.raise_();return _dock
    # Standalone callers do not need to install the session connection bridge.
    rt.fileIn(str(ROOT/'bridge/rig_context.ms'),quiet=True)
    main=qtmax.GetQMaxMainWindow();_dock=RigDock(main)
    main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,_dock)
    _dock.show();_dock.raise_();return _dock
