def _lx_open_ribbon():
    # ExecuteFile shares __main__: __file__ may belong to an earlier script.
    # The executing code object's filename identifies this compiled entry.
    from pathlib import Path
    import sys
    root = Path(sys._getframe().f_code.co_filename).resolve().parents[1]
    for name in ('ribbon', 'rig'):
        module = sys.modules.get(name)
        if module is not None:
            origin = getattr(module, '__file__', None)
            if not origin or Path(origin).resolve().parent != root / name:
                raise RuntimeError(
                    '已加载其他目录的 ' + name + ' 模块。请保存场景后重启 Max，'
                    '再从当前完整工具包打开飘带，避免混用版本。')
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    from ribbon.plugin import show
    show()


_lx_open_ribbon()
