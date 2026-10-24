"""Package the exact committed tool files; compilation happens before tagging."""
import hashlib,json,re,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
m=json.loads((root/'.lxtool/manifest.json').read_text('utf-8-sig'))
if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',m['version']):raise ValueError('Invalid release version')
for path,digest in m['files'].items():
    p=(root/path).resolve()
    if not p.is_relative_to(root) or not p.is_file():raise ValueError('Missing or unsafe file: '+path)
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('File changed after manifest was prepared: '+path)
out=root/'dist';out.mkdir(exist_ok=True)
with zipfile.ZipFile(out/'LXTool-package.zip','w',zipfile.ZIP_DEFLATED) as z:
    for path in ['.lxtool/manifest.json',*sorted(m['files'])]:z.write(root/path,path)
h=hashlib.sha256((out/'LXTool-package.zip').read_bytes()).hexdigest()
(out/'SHA256SUMS.txt').write_text(h+'  LXTool-package.zip\n',encoding='ascii')
print('Prepared v'+m['version']+'; SHA256 '+h)
