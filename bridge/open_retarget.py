"""Explicit Max-only entry; do not trust ExecuteFile's shared __file__."""
def _lx_open_retarget():
    from pathlib import Path
    import hashlib
    import sys
    bootstrap=Path(sys._getframe().f_code.co_filename).resolve()
    root=bootstrap.parents[1]
    package_dir=root/'retarget'
    if not (package_dir/'launcher.py').is_file():
        raise RuntimeError('重定向组件不完整，请重新安装完整 Max 工具集。')
    digest=hashlib.sha256(str(root).casefold().encode('utf-8'))
    for path in sorted(package_dir.rglob('*.py')):
        digest.update(path.relative_to(root).as_posix().encode('utf-8'))
        digest.update(path.read_bytes())
    signature=digest.hexdigest()
    old=sys.modules.get('retarget')
    if old is not None:
        origin=getattr(old,'__file__',None)
        if not getattr(old,'_lx_toolkit_entry',False) and (not origin or Path(origin).resolve().parent!=package_dir):
            raise RuntimeError('已加载其他来源的 retarget 模块，请保存场景后重启 Max 再打开。')
        if getattr(old,'_entry_signature',None)!=signature:
            windows=[]
            for module_name in ('retarget.launcher','retarget.ui','retarget'):
                window=getattr(sys.modules.get(module_name),'_window',None)
                if window is not None and all(window is not item for item in windows):
                    windows.append(window)
            from shiboken6 import isValid
            for window in windows:
                if isValid(window) and window.close() is False:
                    raise RuntimeError('旧重定向窗口正忙或恢复未完成，暂不能切换版本。')
            for name in list(sys.modules):
                if name=='retarget' or name.startswith('retarget.'):
                    del sys.modules[name]
    if str(root) in sys.path:sys.path.remove(str(root))
    sys.path.insert(0,str(root))
    import retarget
    retarget._lx_toolkit_entry=True
    retarget._entry_signature=signature
    retarget._entry_bootstrap_file=str(bootstrap)
    from retarget.launcher import show
    return show()


_lx_open_retarget()
