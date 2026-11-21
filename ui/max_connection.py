"""Per-user Max connection installation and stable process/window identity."""
import base64
import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import uuid


def process_identity(pid):
    if os.name!='nt':return None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    kernel.GetProcessTimes.argtypes=[W.HANDLE,ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME)]
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:return None
    try:
        buf=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(buf))
        if not kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)) or Path(buf.value).name.lower()!='3dsmax.exe':return None
        birth,exit_time,cpu,user=(W.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,ctypes.byref(birth),ctypes.byref(exit_time),ctypes.byref(cpu),ctypes.byref(user)):return None
        ticks=(birth.dwHighDateTime<<32)|birth.dwLowDateTime
        return {'pid':int(pid),'birth':str(ticks),'exe':buf.value,'key':str(pid)+'-'+str(ticks)}
    finally:kernel.CloseHandle(handle)


def windows():
    if os.name!='nt':return []
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.EnumWindows.argtypes=[callback_type,W.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.IsWindowVisible.argtypes=[W.HWND]
    user.GetWindowTextLengthW.argtypes=[W.HWND];user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    found={}
    @callback_type
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd):return True
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        identity=process_identity(pid.value)
        if identity:
            size=user.GetWindowTextLengthW(hwnd);buf=ctypes.create_unicode_buffer(size+1);user.GetWindowTextW(hwnd,buf,len(buf))
            if buf.value and (pid.value not in found or '3ds Max' in buf.value):found[pid.value]=dict(identity,title=buf.value,hwnd=int(hwnd))
        return True
    user.EnumWindows(visit,0)
    return sorted(found.values(),key=lambda p:p['pid'])


def absolute_directory(value):
    if not value or not Path(value).is_absolute():
        raise ValueError('配置目录必须是有效的绝对路径')
    return Path(value).resolve()


def user_root():
    value=os.environ.get('LOCALAPPDATA')
    if value is None:
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,0x1c,None,0,buffer)!=0:
            raise ValueError('无法定位本地应用数据目录')
        value=buffer.value
    return absolute_directory(value)/'LXMaxTools'


def mxs_string(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'


def connection_text(bootstrap):
    bootstrap=Path(bootstrap).resolve()
    if not bootstrap.is_file() or bootstrap.suffix.lower()!='.ms':
        raise ValueError('连接脚本不存在')
    return ('global LXMaxBridgeRequestedUserRoot = '+mxs_string(user_root())+'\n'
            'fileIn '+mxs_string(bootstrap)+' quiet:true\n')


def connection_script(tool_id,bootstrap):
    folder=user_root()/'connections';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(str(uuid.uuid5(uuid.NAMESPACE_URL,str(Path(bootstrap).resolve())))+'.ms')
    path.write_text(connection_text(bootstrap),encoding='utf-8-sig')
    return path


def write_if_changed(path, payload):
    if path.is_file() and path.read_bytes()==payload:
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(payload)
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def install(tool_id, bootstrap, dispatcher=None):
    bootstrap=Path(bootstrap).resolve()
    if not bootstrap.is_file() or bootstrap.suffix.lower()!='.ms':
        raise ValueError('连接组件缺失，请重新安装工具。')
    folder=absolute_directory(os.environ.get('APPDATA'))/'Autodesk/ApplicationPlugins'/('LX-'+tool_id)
    if dispatcher is None:
        loader=connection_text(bootstrap)
    else:
        root=user_root()
        loader=('global LXMaxAutoConnectRoot = '+mxs_string(root)+'\n'
                '(local lxAutoLoader = '+mxs_string(dispatcher)+'\n'
                'if doesFileExist lxAutoLoader do fileIn lxAutoLoader quiet:true)\n')
    write_if_changed(folder/'loader.ms',loader.encode('utf-8-sig'))
    code='{'+str(uuid.uuid5(uuid.NAMESPACE_URL,'lx-max-connection/'+tool_id))+'}'
    write_if_changed(folder/'PackageContents.xml',package_xml(tool_id,code).encode('utf-8'))
    return folder


ENTRIES={
    'max-tools':('bridge/LXMaxBridge.ms','bridge/auto_connect.ms',None),
    'max-animation':('max/bootstrap.ms','max/auto_connect.ms','max/bridge.py'),
}


def register(tool_id, context):
    entry_path,dispatcher_path,worker=ENTRIES[tool_id]
    entry=context.resource(entry_path)
    dispatcher=context.resource(dispatcher_path)
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    payload=base64.b64encode(str(Path(context.package_root).resolve()).encode('utf-8')).decode('ascii')
    recorded=[payload,digest(entry),digest(context.resource(worker)) if worker else '-']
    write_if_changed(user_root()/'auto-connect'/(tool_id+'.txt'),'\n'.join(recorded).encode('ascii'))
    return install(tool_id,entry,dispatcher)


def xml_attribute(value):
    """Escape an XML 1.0 attribute without optional frozen-host libraries."""
    value=str(value)
    if any(not (c in '\t\n\r' or 0x20<=ord(c)<=0xD7FF or 0xE000<=ord(c)<=0xFFFD or 0x10000<=ord(c)<=0x10FFFF) for c in value):
        raise ValueError('连接包属性包含无效 XML 字符')
    return (value.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            .replace('"','&quot;').replace("'",'&apos;')
            .replace('\t','&#9;').replace('\n','&#10;').replace('\r','&#13;'))


def package_xml(tool_id,code):
    # Fixed Autodesk schema only; this is not a general XML serializer.
    name=xml_attribute('LX '+tool_id+' connection');code=xml_attribute(code)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="3ds Max" '
            'ProductType="Application" Name="'+name+'" AppVersion="1.0.0" '
            'UpgradeCode="'+code+'" ProductCode="'+code+'">\n'
            '  <CompanyDetails />\n'
            '  <Components Description="post-start-up scripts parts">\n'
            '    <RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="2023" SeriesMax="2027" />\n'
            '    <ComponentEntry ModuleName="./loader.ms" />\n'
            '  </Components>\n</ApplicationPackage>\n')


class GuiThreadInfo(ctypes.Structure):
    _fields_=[('size',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),
              ('capture',W.HWND),('menu',W.HWND),('move',W.HWND),('caret',W.HWND),('rect',W.RECT)]


def attach_window(window, dispatcher, expected_digest, data_root):
    """Load only the verified LX connector through the Max mini listener."""
    pid=window['pid']
    identity=process_identity(pid)
    if not identity or identity['birth']!=window['birth']:
        return False
    if hashlib.sha256(dispatcher.read_bytes()).hexdigest()!=expected_digest:
        return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,W.BOOL,W.LPCWSTR]
    kernel.CreateMutexW.restype=W.HANDLE
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
    kernel.WaitForSingleObject.restype=W.DWORD
    kernel.ReleaseMutex.argtypes=[W.HANDLE]
    kernel.CloseHandle.argtypes=[W.HANDLE]
    gate=kernel.CreateMutexW(None,False,'Local\\LXMaxAttach-'+identity['key'])
    if not gate:
        return False
    locked=False
    try:
        locked=kernel.WaitForSingleObject(gate,0) in (0,0x80)
        return locked and load_dispatcher(window,dispatcher,data_root)
    finally:
        if locked:kernel.ReleaseMutex(gate)
        kernel.CloseHandle(gate)


def load_dispatcher(window,dispatcher,data_root):
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.GetWindowThreadProcessId.restype=W.DWORD
    user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    user.GetParent.argtypes=[W.HWND]
    user.GetParent.restype=W.HWND
    user.GetDlgCtrlID.argtypes=[W.HWND]
    user.IsWindowEnabled.argtypes=[W.HWND]
    user.GetGUIThreadInfo.argtypes=[W.DWORD,ctypes.POINTER(GuiThreadInfo)]
    callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.EnumChildWindows.argtypes=[W.HWND,callback_type,W.LPARAM]
    user.SendMessageTimeoutW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=W.LPARAM

    def owner(hwnd):
        pid=W.DWORD()
        thread=user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        return pid.value,thread

    def class_name(hwnd):
        name=ctypes.create_unicode_buffer(128)
        user.GetClassNameW(hwnd,name,len(name))
        return name.value

    def send(hwnd,message,wparam=0,lparam=0):
        answer=ctypes.c_size_t()
        if user.SendMessageTimeoutW(hwnd,message,wparam,lparam,0x23,600,ctypes.byref(answer)):
            return answer.value
        return None

    hwnd=window['hwnd']
    pid,thread=owner(hwnd)
    if pid!=window['pid'] or not user.IsWindowEnabled(hwnd):
        return False
    info=GuiThreadInfo()
    info.size=ctypes.sizeof(info)
    if not user.GetGUIThreadInfo(thread,ctypes.byref(info)) or info.flags & 0x1E:
        return False
    candidates=[]
    @callback_type
    def visit(child,_):
        if (user.GetDlgCtrlID(child)==1002 and class_name(child)=='MXS_Scintilla'
                and class_name(user.GetParent(user.GetParent(child)))=='StatusPanel'):
            candidates.append(child)
        return True

    user.EnumChildWindows(hwnd,visit,0)
    if len(candidates)!=1:
        return False
    listener=candidates[0]
    # Leave drafts and the user's active listener alone. Only use a blank mini listener.
    if listener==info.focus or owner(listener)[0]!=pid or send(listener,14)!=0:
        return False
    command='(global LXMaxAutoConnectRoot = '+mxs_string(data_root)+'; fileIn '+mxs_string(dispatcher)+' quiet:true)\r\n'
    buffer=ctypes.create_unicode_buffer(command)
    if send(listener,12,0,ctypes.addressof(buffer))!=1:
        return False
    result=send(listener,0x102,13)
    echo=ctypes.create_unicode_buffer(len(command)+2)
    if send(listener,13,len(echo),ctypes.addressof(echo)) is not None and echo.value==command:
        send(listener,12,0,ctypes.addressof(ctypes.create_unicode_buffer('')))
    return result is not None


class AutoAttach:
    def __init__(self,tool_id,context):
        _,path,worker=ENTRIES[tool_id]
        self.minimum_year=2024 if worker else 2023
        self.dispatcher=context.resource(path)
        self.digest=hashlib.sha256(self.dispatcher.read_bytes()).hexdigest()
        bridge_path=context.resource(worker) if worker else None
        self.bridge_digest=hashlib.sha256(bridge_path.read_bytes()).hexdigest() if bridge_path else None
        self.root=user_root()
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='LXMaxConnect')
        self.job=None
        self.attempts={}
        self.next_scan=0
        self.connecting=False
        self.windows_count=0

    def poll(self,ready):
        if self.job is not None and not self.job.done():
            return
        now=time.monotonic()
        if now<self.next_scan:
            return
        self.next_scan=now+1.5
        active=[w for w in windows()
                if (year:=re.search(r'3ds Max (202[3-7])\b',w['title'],re.I)) and int(year[1])>=self.minimum_year]
        self.windows_count=len(active)
        identities={(w['pid'],str(w['birth'])) for w in active}
        self.attempts={key:retry for key,retry in self.attempts.items() if key in identities}
        self.connecting=False
        for window in active:
            key=(window['pid'],str(window['birth']))
            if key in ready:
                continue
            self.connecting=True
            if now<self.attempts.get(key,0):
                continue
            self.attempts[key]=now+12
            self.job=self.pool.submit(attach_window,window,self.dispatcher,self.digest,self.root)
            break

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)
