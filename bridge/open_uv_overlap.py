def open_uv_overlap():
    from pathlib import Path
    import builtins
    import runpy
    import sys
    from shiboken6 import isValid

    root = Path(sys._getframe().f_code.co_filename).resolve().parents[1]
    previous = getattr(builtins, '_lx_uv_overlap', None)
    if previous is not None and isValid(previous):
        previous.close()
    model = runpy.run_path(str(root/'uv_overlap.py'))
    ui = runpy.run_path(str(root/'uv_overlap_ui.py'), init_globals={'solver': model})
    builtins._lx_uv_overlap = ui['show']()


open_uv_overlap()
