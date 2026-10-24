"""Publish validated build assets using GitHub Actions' short-lived token."""
import hashlib,json,os,urllib.request,urllib.error,urllib.parse
from pathlib import Path

def api(method,path,data=None,binary=False):
    url=path if path.startswith('https://') else 'https://api.github.com'+path
    headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'User-Agent':'LX-release','Accept':'application/vnd.github+json'}
    if binary:headers['Content-Type']='application/octet-stream';body=data
    else:headers['Content-Type']='application/json';body=json.dumps(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers,method=method),timeout=180) as response:
        raw=response.read();return json.loads(raw) if raw else None

repo=os.environ['GITHUB_REPOSITORY'];sha=os.environ['GITHUB_SHA']
if repo=='gd-dd/LXTools':
    import re
    version=re.search(r"^VERSION = '([^']+)'",Path('src/updater.py').read_text(),re.M)[1]
    names=[f'LXTools-Setup-{version}-windows-x64.exe','LXTool-windows-x64.zip','SHA256SUMS.txt']
    title='LXTools v'+version
    notes='首次正式发行。工具架与工具均通过 GitHub Releases 管理版本。\n\n普通用户下载 Setup EXE 安装；ZIP 用于免安装及自更新。旧 0.5.0 为首次发布编号更正，已安装旧版需手动重装 0.0.1，之后按递增版本更新。'
else:
    manifest=json.loads(Path('.lxtool/manifest.json').read_text('utf-8-sig'));version=manifest['version']
    names=['LXTool-package.zip','SHA256SUMS.txt'];title=manifest['name']+' v'+version
    notes=manifest.get('releaseNotes','')+'\n\n通过 LXTools 商店安装，宿主兼容性待实测。'
assets=[Path('dist')/n for n in names]
for asset in assets:
    if not asset.is_file():raise RuntimeError('Missing asset: '+str(asset))
tag='v'+version
try:
    ref=api('GET',f'/repos/{repo}/git/ref/tags/{tag}')
    if ref['object']['sha']!=sha:raise RuntimeError('Tag already points to another commit; refusing to move it')
except urllib.error.HTTPError as error:
    if error.code!=404:raise
    api('POST',f'/repos/{repo}/git/refs',{'ref':'refs/tags/'+tag,'sha':sha})
releases=api('GET',f'/repos/{repo}/releases?per_page=100')
release=next((r for r in releases if r['tag_name']==tag),None)
if release and release['tag_name']==tag and not release['draft']:
    raise RuntimeError('Version is already published; never overwrite published assets')
fields={'tag_name':tag,'target_commitish':sha,'name':title,'body':notes,'draft':True,'prerelease':False}
if release:
    release=api('PATCH',f"/repos/{repo}/releases/{release['id']}",fields)
    for asset in release['assets']:api('DELETE',f"/repos/{repo}/releases/assets/{asset['id']}")
else:release=api('POST',f'/repos/{repo}/releases',fields)
for path in assets:
    data=path.read_bytes();digest='sha256:'+hashlib.sha256(data).hexdigest()
    uploaded=api('POST',release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(path.name),data,True)
    if uploaded.get('digest')!=digest:raise RuntimeError('Uploaded digest differs: '+path.name)
api('PATCH',f"/repos/{repo}/releases/{release['id']}",{'draft':False,'make_latest':'true'})
print('Published:',release['html_url'])
