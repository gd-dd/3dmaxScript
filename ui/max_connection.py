"""Per-user Max connection installation and stable process/window identity."""
import os
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET


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


def install(tool_id, bootstrap):
    bootstrap=Path(bootstrap).resolve()
    if not bootstrap.is_file() or bootstrap.suffix.lower()!='.ms':raise ValueError('连接脚本不存在')
    folder=Path(os.environ['APPDATA'])/'Autodesk/ApplicationPlugins'/('LX-'+tool_id)
    folder.mkdir(parents=True,exist_ok=True)
    path=str(bootstrap).replace('"','""')
    # Only a bridge is loaded; never change or save the user's scene.
    (folder/'loader.ms').write_text('try (if doesFileExist @"'+path+'" do fileIn @"'+path+'" quiet:true) catch (format "LX connection: %\\n" (getCurrentException()))',encoding='utf-8-sig')
    code='{'+str(uuid.uuid5(uuid.NAMESPACE_URL,'lx-max-connection/'+tool_id))+'}'
    root=ET.Element('ApplicationPackage',SchemaVersion='1.0',AutodeskProduct='3ds Max',ProductType='Application',Name='LX '+tool_id+' connection',AppVersion='1.0.0',UpgradeCode=code,ProductCode=code)
    ET.SubElement(root,'CompanyDetails')
    components=ET.SubElement(root,'Components',Description='post-start-up scripts parts')
    ET.SubElement(components,'RuntimeRequirements',OS='Win64',Platform='3ds Max',SeriesMin='2024',SeriesMax='2027')
    ET.SubElement(components,'ComponentEntry',ModuleName='./loader.ms')
    ET.ElementTree(root).write(folder/'PackageContents.xml',encoding='utf-8',xml_declaration=True)
    return folder


def refresh_install(tool_id,bootstrap):
    if (Path(os.environ.get('APPDATA',''))/'Autodesk/ApplicationPlugins'/('LX-'+tool_id)/'PackageContents.xml').is_file():
        return install(tool_id,bootstrap)
