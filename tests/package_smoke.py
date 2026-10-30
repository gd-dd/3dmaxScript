"""Load the exact ZIP through the real shelf workspace without installation."""
import sys,json,hashlib,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'LXTools'/'src'))
from PySide6.QtWidgets import QApplication
from repository_panels import RepositoryWorkspace
app=QApplication([])
with tempfile.TemporaryDirectory(prefix='lx-rig-package-') as temp:
    base=Path(temp);root=base/'package'
    with zipfile.ZipFile(ROOT/'dist/LXTool-package.zip') as z:z.extractall(root)
    manifest=json.loads((root/'.lxtool/manifest.json').read_text('utf-8-sig'))
    assert set(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())==set(manifest['files'])|{'.lxtool/manifest.json'}
    for path,digest in manifest['files'].items():assert hashlib.sha256((root/path).read_bytes()).hexdigest()==digest,path
    tool=dict(manifest,root=root,id='repo-1342543761',panelData=json.loads((root/'.lxtool/panel.json').read_text('utf-8')))
    workspace=RepositoryWorkspace(base/'tools',base/'config');workspace.display(tool)
    panel=workspace.native_panel.widget
    assert panel.rig.tabs.count()==5
    assert panel.process.state().value==0,'rendering started a process'
    workspace.shutdown();workspace.shutdown()
print('PASS: exact ZIP hashes, shelf RepositoryWorkspace, five embedded tabs, idle construction, repeated shutdown')
