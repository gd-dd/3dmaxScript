"""Declarative session controls backed by a tool-owned, opt-in stdio provider."""
import json
import uuid
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QLineEdit, QFileDialog, QTreeWidget, QTreeWidgetItem, QHeaderView)
from PySide6.QtWidgets import QPushButton, QScrollArea
from PySide6.QtGui import QPixmap
from .transport import HiddenProcess


def plain(text, style=''):
    label=QLabel(text);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True)
    if style:label.setStyleSheet(style)
    return label


class MaxPanel(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context=context
        spec=json.loads(context.resource('ui/tools.json').read_text('utf-8'))
        tool={'root':context.package_root,'name':'Max 工作台','panelData':{'title':'Max 工作台'},'applications':{'max':{'name':'3ds Max','executable':'3dsmax.exe'}}}
        settings=context.load_settings()
        self.tool,self.spec,self.settings,self.save_settings=tool,spec,settings,context.save_settings
        self.setStyleSheet('QFrame#card {background:#ffffff;border:1px solid #e2e9d8;border-radius:14px;} QPushButton {background:#f6f9ef;border:1px solid #dfe8d0;border-radius:9px;padding:10px 16px;color:#35532d;} QPushButton:hover {background:#eaf2d9;border-color:#a6bf7a;} QPushButton:disabled {color:#a0a69a;background:#f5f5f1;} QPushButton#primary {background:#89b851;color:white;font-weight:600;border:0;} QLineEdit {border:1px solid #e0e6d8;border-radius:6px;padding:7px;background:#fafbf7;} QTreeWidget {border:0;background:#ffffff;} QTreeWidget::item {padding:9px;} QTreeWidget::item:selected {background:#e7f0d8;color:#304927;}')
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
        scroll=QScrollArea(self);scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);shell.addWidget(scroll)
        content=QWidget();scroll.setWidget(content)
        outer=QVBoxLayout(content);outer.setContentsMargins(16,12,16,16);outer.setSpacing(14)
        header=QHBoxLayout()
        icon=QLabel();icon.setPixmap(QPixmap(str(context.resource('.lxtool/icon.png'))).scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));header.addWidget(icon)
        title=QVBoxLayout();title.addWidget(plain(tool['panelData'].get('title',tool['name']), 'font-size:25px;font-weight:700;color:#304927'))
        title.addWidget(plain(spec.get('subtitle','打开应用，选择连接，再运行工具。'),'color:#777777'))
        header.addLayout(title,1);self.counter=plain('尚未连接','color:#507522;font-weight:600');header.addWidget(self.counter);outer.addLayout(header)
        launch,box=self.section('01','打开 Max');outer.addWidget(launch)
        row=QHBoxLayout();self.path=QLineEdit(settings.get(spec['application'],{}).get('path',''))
        self.path.setReadOnly(True);self.path.setPlaceholderText('先选择 '+tool['applications'][spec['application']]['executable'])
        self.path.setMinimumWidth(200);row.addWidget(self.path,1)
        row.addWidget(self.button('更改程序',self.pick_application));box.addLayout(row)
        row=QHBoxLayout();self.launch_button=self.button(spec.get('launchLabel','打开应用'),self.launch,True)
        row.addWidget(self.launch_button);self.connect_button=self.button('连接 / 刷新',lambda:self.command('hello'))
        row.addWidget(self.connect_button);row.addStretch();box.addLayout(row)
        connections,box=self.section('02','选择已连接窗口');outer.addWidget(connections)
        self.empty=plain('还没有连接的窗口。点击上方“打开”，就绪后会自动出现在这里。','color:#777777;padding:12px 0')
        box.addWidget(self.empty)
        self.list=QTreeWidget();self.list.setHeaderLabels(['窗口','连接状态']);self.list.setRootIsDecorated(False)
        self.list.setMinimumHeight(100);self.list.setMaximumHeight(170);self.list.setColumnCount(2)
        self.list.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.list.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.list.currentItemChanged.connect(self.selection_changed);box.addWidget(self.list);self.list.hide()
        box.addWidget(plain('仅显示由此工具打开的窗口。连接列表可在工具架重启后恢复。','color:#777777;font-size:12px'))
        tools,box=self.section('03','在选中窗口中打开工具');outer.addWidget(tools)
        self.target=plain('先选择一个已连接窗口','color:#507522');box.addWidget(self.target)
        grid=QGridLayout();grid.setSpacing(10)
        for index,item in enumerate(spec['tools']):
            button=self.button(item['label']+'\n'+item.get('description',''),lambda key=item['id']:self.run_tool(key))
            button.setMinimumHeight(72);button.setStyleSheet('text-align:left;padding:12px 16px;')
            button.setToolTip(item.get('group','')+' · '+item.get('description',item['label']));button.setEnabled(False)
            self.buttons[item['id']]=button;grid.addWidget(button,index//2,index%2)
        box.addLayout(grid)
        self.status=plain('准备就绪。打开应用后，连接将自动建立。','color:#777777;padding:8px 0')
        outer.addWidget(self.status);outer.addStretch()
        # Merely rendering a panel must never launch provider or host processes.

    def section(self, number, title):
        frame=QFrame();frame.setObjectName('card');layout=QVBoxLayout(frame);layout.setContentsMargins(18,14,18,16);layout.setSpacing(10)
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
        self.path.setText(path);self.settings.setdefault(self.spec['application'],{})['path']=path
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
        if message:self.fail(message[:2000])

    def read_output(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer)>1024*1024:self.fail('后台响应超过限制');self.shutdown();return
        while b'\n' in self.buffer:
            line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            try:
                value=json.loads(line)
                if not isinstance(value,dict) or value.get('protocol')!=1 or value.get('id') not in self.requests:raise ValueError('后台响应协议无效')
                op=self.requests.pop(value['id'])
                if not self.requests:self.watchdog.stop()
                if not value.get('ok'):self.fail(str(value.get('error','操作失败')));continue
                self.apply_response(value)
                if op=='hello' and not value.get('events'):self.status.setText('连接列表已刷新。')
            except (ValueError,KeyError,TypeError) as error:self.fail(str(error))

    def apply_response(self,value):
        sessions=value.get('sessions',[])
        if not isinstance(sessions,list) or len(sessions)>100:raise ValueError('后台会话列表无效')
        seen=set()
        for item in sessions:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in seen or item.get('state') not in ('ready','connecting','busy'):raise ValueError('后台会话无效')
            seen.add(item['id'])
            if any(not isinstance(item.get(k,''),str) or len(item.get(k,''))>4096 for k in ('id','title','detail','status')):raise ValueError('后台会话文字无效')
        pending=value.get('pending',[])
        if not isinstance(pending,list) or len(pending)>100:raise ValueError('后台待处理列表无效')
        if any(not isinstance(p,dict) or not isinstance(p.get('sessionId'),str) or p.get('toolId') not in self.buttons for p in pending):raise ValueError('后台待处理操作无效')
        self.pending={(p['sessionId'],p['toolId']) for p in pending}
        self.sessions={s['id']:s for s in sessions};selected=self.active_id
        self.list.blockSignals(True);self.list.clear()
        for s in sessions:
            state={'ready':'● 已连接','connecting':'◌ 正在连接','busy':'○ 忙碌 / 未响应'}[s['state']]
            item=QTreeWidgetItem([s.get('title','窗口')+'\n'+s.get('detail',''),state]);item.setData(0,Qt.ItemDataRole.UserRole,s['id'])
            item.setToolTip(0,s.get('detail',''));self.list.addTopLevelItem(item)
            if s['id']==selected:self.list.setCurrentItem(item)
        if self.list.currentItem() is None:
            ready=next((self.list.topLevelItem(i) for i,s in enumerate(sessions) if s['state']=='ready'),None)
            if ready:self.list.setCurrentItem(ready)
        self.list.blockSignals(False);self.selection_changed(self.list.currentItem())
        self.list.setVisible(bool(sessions));self.empty.setVisible(not sessions)
        self.counter.setText(str(len(sessions))+' 个窗口 · '+str(sum(s['state']=='ready' for s in sessions))+' 个已连接')
        app_path=value.get('applicationPath')
        if not self.path.text() and isinstance(app_path,str) and Path(app_path).is_file():self.set_path(app_path)
        events=value.get('events',[])
        if not isinstance(events,list) or any(not isinstance(e,str) for e in events):raise ValueError('后台事件无效')
        if events:self.status.setText('\n'.join(events[-3:])[:2000])

    def selection_changed(self,item,*_):
        self.active_id=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        session=self.sessions.get(self.active_id,{})
        self.target.setText('目标：'+session.get('detail','') if session else '先选择一个已连接窗口')
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
        self.sessions={};self.pending=set();self.list.clear();self.list.hide();self.empty.show();self.counter.setText('尚未连接');self.selection_changed(None)

    def shutdown(self):
        self.timer.stop();self.watchdog.stop();self.queued.clear();self.process.closeWriteChannel()
        if self.process.state()!=QProcess.ProcessState.NotRunning:
            if not self.process.waitForFinished(700):self.process.kill();self.process.waitForFinished(700)


def create_panel(context, parent):
    return MaxPanel(context, parent)
