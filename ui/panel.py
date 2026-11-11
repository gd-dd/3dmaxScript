"""Declarative session controls backed by a tool-owned, opt-in stdio provider."""
import json
import uuid
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QLineEdit, QFileDialog, QTreeWidget, QTreeWidgetItem, QHeaderView)
from PySide6.QtWidgets import QPushButton, QScrollArea, QSizePolicy, QComboBox
from PySide6.QtGui import QPixmap, QFont
from .transport import HiddenProcess
from . import max_connection
from PySide6.QtWidgets import QApplication


def plain(text, style=''):
    label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    if style:label.setStyleSheet(style)
    return label


class SessionChoice(QComboBox):
    def wheelEvent(self,event):
        # Scrolling the panel must not silently change the command target.
        event.ignore()


class TargetLabel(QLabel):
    """Keep a long scene path from consuming the tool area; retain its full text."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self._full_text=''
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)

    def setText(self,text):
        self._full_text=text
        self.setToolTip(text)
        self.setAccessibleDescription(text)
        self._render()

    def _render(self):
        width=max(1,self.contentsRect().width())
        super().setText('\n'.join(self.fontMetrics().elidedText(line,Qt.TextElideMode.ElideMiddle,width)
                                 for line in self._full_text.split('\n')))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._render()


class MaxPanel(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.setFont(QFont('Microsoft YaHei UI',10))
        self.context=context
        max_connection.refresh_install("max-tools",context.resource("bridge/LXMaxBridge.ms"))
        spec=json.loads(context.resource('ui/tools.json').read_text('utf-8'))
        tool={'root':context.package_root,'name':'Max 工作台','panelData':{'title':'Max 工作台'},'applications':{'max':{'name':'3ds Max','executable':'3dsmax.exe'}}}
        settings=context.load_settings()
        self.tool,self.spec,self.settings,self.save_settings=tool,spec,settings,context.save_settings
        self.setStyleSheet("""
            QWidget {color:#30442c;}
            QFrame#card {background:white;border:1px solid #dfe8d9;border-radius:10px;}
            QPushButton {background:#f6f9f0;border:1px solid #d9e4cc;border-radius:7px;padding:7px 12px;color:#35532d;}
            QPushButton:hover {background:#eaf2d9;border-color:#9ab970;}
            QPushButton:focus {border:2px solid #6f943f;}
            QPushButton:disabled {color:#889181;background:#f5f6f2;}
            QPushButton#primary {background:#50752f;color:white;font-weight:600;}
            QPushButton#tool {text-align:left;font-weight:600;padding:10px 12px;}
            QLineEdit {border:1px solid #dfe5d8;border-radius:5px;padding:6px;background:white;}
            QComboBox {border:1px solid #dfe5d8;border-radius:5px;padding:6px;background:white;}
            QTreeWidget {border:1px solid #e1e8d9;border-radius:5px;background:white;}
            QTreeWidget::item {padding:6px;}
            QTreeWidget::item:selected {background:#e7f0d8;color:#304927;}
        """)
        self.process=HiddenProcess(self);self.buffer=bytearray();self.requests={};self.queued=[]
        self.sessions={};self.pending=set();self.buttons={};self.active_id=None
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.provider_started)
        self.process.finished.connect(self.provider_finished)
        self.process.errorOccurred.connect(lambda error:self.fail('后台连接无法启动，请检查工具文件。'))
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.poll)
        self.watchdog=QTimer(self);self.watchdog.setSingleShot(True);self.watchdog.setInterval(15000)
        self.watchdog.timeout.connect(self.timed_out)
        shell=QVBoxLayout(self);shell.setContentsMargins(0,0,0,0)
        self.scroll=QScrollArea(self);self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        shell.addWidget(self.scroll)
        content=QWidget();content.setMinimumWidth(0);self.scroll.setWidget(content)
        outer=QVBoxLayout(content);outer.setContentsMargins(12,10,12,12);outer.setSpacing(10)
        header=QHBoxLayout();header.setSpacing(10)
        icon=QLabel();icon.setPixmap(QPixmap(str(context.resource('.lxtool/icon.png'))).scaled(44,44,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));header.addWidget(icon)
        title=QVBoxLayout();title.setSpacing(2)
        title.addWidget(plain('Max 工具集','font-size:21px;font-weight:700;color:#304927'))
        title.addWidget(plain('打开 Max → 连接窗口 → 打开工具','color:#68775d;font-size:12px'))
        header.addLayout(title,1);outer.addLayout(header)

        launch,box=self.section('01','打开 Max');outer.addWidget(launch)
        box.itemAt(0).widget().hide()
        row=QHBoxLayout()
        self.launch_button=self.button('01  打开新 Max',self.launch,True);row.addWidget(self.launch_button)
        row.addWidget(plain('可同时打开多个实例，分别运行工具。','color:#68775d;font-size:12px'),1)
        box.addLayout(row)

        connections,box=self.section('02','连接并选择窗口');outer.addWidget(connections)
        box.itemAt(0).widget().hide()
        row=QHBoxLayout();self.counter=plain('02  连接并选择窗口','color:#507522;font-weight:600');row.addWidget(self.counter,1)
        self.connect_button=self.button('连接 / 刷新',lambda:self.command('hello'));row.addWidget(self.connect_button)
        box.addLayout(row)
        self.empty=plain('新开的 Max 自动连接；已有窗口可刷新后选择。','color:#68775d;padding:4px 0')
        box.addWidget(self.empty)
        self.list=QTreeWidget();self.list.setHeaderLabels(['Max 窗口','状态']);self.list.setRootIsDecorated(False)
        self.list.setMinimumWidth(0);self.list.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.list.setFixedHeight(116);self.list.setColumnCount(2)
        self.list.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.list.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.session_choice=SessionChoice();self.session_choice.setMinimumWidth(0)
        self.session_choice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.session_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.session_choice.setMinimumContentsLength(1);self.session_choice.setMinimumHeight(32)
        self.session_choice.addItem('请选择 Max 窗口',None)
        self.session_choice.currentIndexChanged.connect(self.choose_session);box.addWidget(self.session_choice)
        self.connection_toggle=self.button('连接设置与首次连接 · 展开',self.toggle_connection)
        self.connection_toggle.setCheckable(True);self.connection_toggle.setStyleSheet('padding:3px 6px;text-align:left;');box.addWidget(self.connection_toggle,alignment=Qt.AlignmentFlag.AlignLeft)
        self.connection_options=QWidget();options=QVBoxLayout(self.connection_options)
        options.setContentsMargins(0,4,0,0);options.setSpacing(8)
        options.addWidget(plain('Max 程序','font-weight:600'))
        self.path=QLineEdit(settings.get(spec['application'],{}).get('path',''));self.path.setReadOnly(True)
        self.path.setToolTip(self.path.text())
        self.path.setMinimumWidth(0);self.path.setPlaceholderText('尚未指定 3dsmax.exe')
        self.path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        options.addWidget(self.path)
        options.addWidget(self.button('选择 Max 程序…',self.pick_application),alignment=Qt.AlignmentFlag.AlignLeft)
        options.addWidget(plain('首次接入已有 Max：复制连接脚本路径，在目标 Max 的「脚本 → 运行脚本」执行一次，然后刷新列表。','color:#68775d;font-size:12px'))
        options.addWidget(self.button('复制首次连接脚本',self.connection_help))
        options.addWidget(self.button('以后启动时自动连接',self.install_connection))
        self.connection_note=plain('','color:#507522;font-size:12px');self.connection_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        options.addWidget(self.connection_note)
        options.addWidget(plain('全部窗口详情','font-weight:600'));options.addWidget(self.list)
        box.addWidget(self.connection_options);self.connection_options.hide()

        tools,box=self.section('03','在选中 Max 中打开工具');outer.addWidget(tools)
        self.target=TargetLabel();self.target.setStyleSheet('color:#507522')
        self.target.setText('请先选择一个已连接窗口。');box.addWidget(self.target)
        self.tool_grids=[]
        groups=[('角色与绑定',('rig-workbench','retarget','ribbon')),
                ('动画处理',('animation-bake','keyframe-formula','parent-keep-world','root-cleanup')),
                ('模型与导入',('material-split','pmx-import'))]
        by_id={item['id']:item for item in spec['tools']}
        grouped={identity for _,ids in groups for identity in ids}
        extras=tuple(identity for identity in by_id if identity not in grouped)
        if extras:groups.append(('其他工具',extras))
        for title,ids in groups:
            group_label=plain(title,'font-size:12px;font-weight:600;color:#68775d')
            grid=QGridLayout();grid.setSpacing(7);items=[]
            for identity in ids:
                item=by_id[identity]
                button=self.button(item['label'],lambda key=identity:self.run_tool(key))
                button.setObjectName('tool');button.setMinimumSize(0,42)
                button.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
                button.setAccessibleDescription(item.get('description',''))
                button.setToolTip(item.get('description',item['label']));button.setEnabled(False)
                self.buttons[identity]=button;items.append(button)
            self.tool_grids.append((grid,items,group_label));box.addLayout(grid)
        self.status=plain('准备就绪。工具将在你选中的 Max 内打开。','color:#68775d;padding:4px 0')
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.status);outer.addStretch()
        self._tool_columns=None;self.reflow_tools()
        # Rendering never launches the provider or Max.

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.reflow_tools()

    def reflow_tools(self):
        if not hasattr(self,'tool_grids'):return
        columns=4 if self.width()>=780 else (2 if self.width()>=380 else 1)
        if columns==self._tool_columns:return
        self._tool_columns=columns
        for grid,buttons,label in self.tool_grids:
            while grid.count():grid.takeAt(0)
            for col in range(5):
                grid.setColumnStretch(col,0)
                grid.setColumnMinimumWidth(col,0)
            if columns==4:
                label.setFixedWidth(76);grid.setColumnMinimumWidth(0,76);grid.addWidget(label,0,0)
                for col in range(1,5):grid.setColumnStretch(col,1)
                for index,button in enumerate(buttons):grid.addWidget(button,index//4,index%4+1)
            else:
                label.setMinimumWidth(0);label.setMaximumWidth(16777215)
                grid.addWidget(label,0,0,1,columns)
                for col in range(columns):grid.setColumnStretch(col,1)
                for index,button in enumerate(buttons):grid.addWidget(button,1+index//columns,index%columns)

    def toggle_connection(self):
        opened=self.connection_toggle.isChecked()
        self.connection_options.setVisible(opened)
        self.connection_toggle.setText('连接设置与首次连接 · 收起' if opened else '连接设置与首次连接 · 展开')

    def section(self, number, title):
        frame=QFrame();frame.setObjectName('card');layout=QVBoxLayout(frame);layout.setContentsMargins(12,10,12,12);layout.setSpacing(8)
        layout.addWidget(plain(number+'   '+title,'font-size:16px;font-weight:600;color:#304927'))
        return frame,layout

    def button(self,title,callback,primary=False):
        button=QPushButton(title);button.clicked.connect(lambda checked=False:callback())
        if primary:button.setObjectName('primary')
        return button

    def pick_application(self):
        app=self.tool['applications'][self.spec['application']]
        path,_=QFileDialog.getOpenFileName(self,'选择 '+app['name'],self.path.text(),'程序 ('+app['executable']+')')
        if path:
            if Path(path).name.lower()!=app['executable'].lower():self.fail('请选择 '+app['executable']);return
            self.set_path(path)

    def set_path(self,path):
        self.path.setText(path);self.path.setToolTip(path);self.settings.setdefault(self.spec['application'],{})['path']=path
        self.save_settings(self.settings)

    def launch(self):
        if not self.path.text():self.pick_application()
        if not self.path.text():return
        self.command('launch',applicationPath=self.path.text())

    def verify(self):
        self.context.resource('bin/LXMaxSession.exe')
        self.context.resource('bridge/LXMaxBridge.ms')

    def command(self,op,**data):
        try:
            if op!='status':self.verify()
            payload=dict(op=op,id=uuid.uuid4().hex,**data)
            if self.process.state()==QProcess.ProcessState.NotRunning:
                if op=='status':return
                self.queued.append(payload)
                self.process.setWorkingDirectory(str(self.context.package_root))
                self.process.setProgram(str(self.context.resource('bin/LXMaxSession.exe')))
                self.process.setArguments([]);self.process.start();self.watchdog.start()
                self.status.setText('正在连接工具后台…')
            elif self.process.state()==QProcess.ProcessState.Starting:self.queued.append(payload)
            else:self.send(payload)
            return payload['id']
        except Exception as error:self.fail(str(error))

    def send(self,payload):
        self.requests[payload['id']]=payload['op']
        self.process.write((json.dumps(payload,ensure_ascii=False)+'\n').encode('utf-8'))
        if not self.watchdog.isActive():self.watchdog.start()

    def provider_started(self):
        for payload in self.queued:self.send(payload)
        self.queued.clear();self.timer.start()

    def poll(self):
        if 'status' not in self.requests.values():self.command('status')

    def read_error(self):
        message=bytes(self.process.readAllStandardError()).decode('utf-8',errors='replace').strip()
        # Max may inherit stderr and emit ordinary assembly diagnostics.
        # Keep those separate from the structured operation result.
        if message:self.last_backend_diagnostic=message[-2000:]

    def read_output(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer)>32*1024*1024:self.fail('后台响应超过限制');self.shutdown();return
        while b'\n' in self.buffer:
            line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            try:
                value=json.loads(line)
                if not isinstance(value,dict) or value.get('protocol')!=1 or value.get('id') not in self.requests:raise ValueError('后台响应协议无效')
                op=self.requests.pop(value['id'])
                if not self.requests:self.watchdog.stop()
                if not value.get('ok'):
                    self.fail(str(value.get('error','操作失败')))
                    continue
                self.apply_response(value)
                if op=='hello' and not value.get('events'):self.status.setText('连接列表已刷新。')
            except (ValueError,KeyError,TypeError) as error:self.fail(str(error))

    def apply_response(self,value):
        sessions=value.get('sessions',[])
        if not isinstance(sessions,list) or len(sessions)>100:raise ValueError('后台会话列表无效')
        seen=set()
        for item in sessions:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in seen or item.get('state') not in ('ready','connecting','busy','unconnected'):raise ValueError('后台会话无效')
            seen.add(item['id'])
            if any(not isinstance(item.get(k,''),str) or len(item.get(k,''))>4096 for k in ('id','title','detail','status')):raise ValueError('后台会话文字无效')
        pending=value.get('pending',[])
        if not isinstance(pending,list) or len(pending)>100:raise ValueError('后台待处理列表无效')
        if any(not isinstance(p,dict) or not isinstance(p.get('sessionId'),str) or p.get('toolId') not in (*self.buttons,'rig') for p in pending):raise ValueError('后台待处理操作无效')
        self.pending={(p['sessionId'],p['toolId']) for p in pending}
        self.sessions={s['id']:s for s in sessions};selected=self.active_id
        self.list.blockSignals(True);self.list.clear()
        self.session_choice.blockSignals(True);self.session_choice.clear();self.session_choice.addItem('请选择 Max 窗口',None)
        for s in sessions:
            state={'ready':'● 已连接','connecting':'◌ 正在连接','busy':'○ 忙碌 / 未响应','unconnected':'○ 尚未连接'}[s['state']]
            item=QTreeWidgetItem([s.get('title','窗口')+'\n'+s.get('detail',''),state]);item.setData(0,Qt.ItemDataRole.UserRole,s['id'])
            item.setToolTip(0,s.get('title','')+'\n'+s.get('detail',''));self.list.addTopLevelItem(item)
            self.session_choice.addItem(state+' · '+s.get('title','Max')+' · '+s.get('detail',''),s['id'])
            self.session_choice.setItemData(self.session_choice.count()-1,item.toolTip(0),Qt.ItemDataRole.ToolTipRole)
            if s['id']==selected:self.list.setCurrentItem(item)
        self.session_choice.blockSignals(False)
        self.list.blockSignals(False);self.selection_changed(self.list.currentItem())
        self.list.setVisible(bool(sessions));self.empty.setVisible(not sessions)
        self.counter.setText('02  '+str(len(sessions))+' 个窗口 · '+str(sum(s['state']=='ready' for s in sessions))+' 个已连接')
        app_path=value.get('applicationPath')
        if not self.path.text() and isinstance(app_path,str) and Path(app_path).is_file():self.set_path(app_path)
        events=value.get('events',[])
        if not isinstance(events,list) or any(not isinstance(e,str) for e in events):raise ValueError('后台事件无效')
        if events:self.status.setText('\n'.join(events[-3:])[:2000])

    def install_connection(self):
        try:
            folder=max_connection.install('max-tools',self.context.resource('bridge/LXMaxBridge.ms'))
            self.connection_note.setText('已安装自动连接。以后启动 Max 会自动连接；当前已打开的窗口需运行一次连接脚本。\n'+str(folder))
        except Exception as error:self.fail(str(error))

    def connection_help(self):
        try:script=str(max_connection.connection_script('max-tools',self.context.resource('bridge/LXMaxBridge.ms')))
        except Exception as error:self.fail(str(error));return
        QApplication.clipboard().setText(script)
        self.connection_note.setText('路径已复制。在目标 Max 的「脚本 → 运行脚本」中执行，再点击连接 / 刷新。\n'+script)

    def choose_session(self,index):
        identity=self.session_choice.itemData(index)
        selected=None
        for row in range(self.list.topLevelItemCount()):
            item=self.list.topLevelItem(row)
            if item.data(0,Qt.ItemDataRole.UserRole)==identity:selected=item;break
        self.list.setCurrentItem(selected)
        self.selection_changed(selected)

    def selection_changed(self,item,*_):
        self.active_id=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        session=self.sessions.get(self.active_id,{})
        self.session_choice.blockSignals(True)
        self.session_choice.setCurrentIndex(max(0,self.session_choice.findData(self.active_id)))
        self.session_choice.setToolTip((session.get('title','')+'\n'+session.get('detail','')).strip())
        self.session_choice.blockSignals(False)
        if not session:target='请先选择一个已连接窗口。'
        else:
            target='目标：'+(session.get('detail') or session.get('title','Max'))
            if session.get('state')=='unconnected':target+='\n尚未连接，请展开连接设置运行首次连接脚本。'
            elif session.get('state')!='ready':target+='\n等待窗口恢复连接后即可打开工具。'
        self.target.setText(target)
        for identity,button in self.buttons.items():button.setEnabled(session.get('state')=='ready' and (self.active_id,identity) not in self.pending)

    def run_tool(self,identity):
        if self.sessions.get(self.active_id,{}).get('state')!='ready':self.fail('请先选择已连接窗口。');return
        self.buttons[identity].setEnabled(False)
        self.command('run',sessionId=self.active_id,toolId=identity)

    def fail(self,message):self.status.setText(message)

    def timed_out(self):
        self.fail('工具后台未响应。请点击“连接 / 刷新”重连；已打开的应用不会被关闭。')
        self.shutdown()

    def provider_finished(self,*_):
        self.timer.stop();self.watchdog.stop();self.requests.clear();self.queued.clear();self.buffer.clear()
        self.sessions={};self.pending=set();self.list.clear();self.list.hide();self.empty.show();self.counter.setText('02  连接并选择窗口');self.session_choice.clear();self.session_choice.addItem('请选择 Max 窗口',None);self.selection_changed(None)
        if _ and _[0]:self.fail(getattr(self,'last_backend_diagnostic','工具后台已退出，请重新连接。'))

    def shutdown(self):
        self.timer.stop();self.watchdog.stop();self.queued.clear();self.process.closeWriteChannel()
        if self.process.state()!=QProcess.ProcessState.NotRunning:
            if not self.process.waitForFinished(700):self.process.kill();self.process.waitForFinished(700)


def create_panel(context, parent):
    return MaxPanel(context, parent)
