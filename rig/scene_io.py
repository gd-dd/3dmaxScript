"""Full-scene recovery copies and read-only joint continuity diagnostics."""
import json,os,uuid
from datetime import datetime
from pathlib import Path
from . import max_host as H
rt=H.rt

@H.command('scene.backup')
def backup(p):
    folder=Path(os.environ['LOCALAPPDATA'])/'LXMaxTools'/'scene-backups';folder.mkdir(parents=True,exist_ok=True)
    path=folder/('Max-%s-%d-%s.max'%(datetime.now().strftime('%Y%m%d-%H%M%S'),os.getpid(),uuid.uuid4().hex[:8]))
    original=str(rt.maxFilePath)+str(rt.maxFileName)
    adopt=bool(p.get('adopt',False))
    if not rt.saveMaxFile(str(path),quiet=True,useNewFile=adopt,clearNeedSaveFlag=adopt):raise RuntimeError('完整场景副本保存失败')
    if not path.is_file() or path.stat().st_size==0:raise RuntimeError('场景副本没有写入磁盘')
    meta={'path':str(path),'original':original,'pid':os.getpid(),'bytes':path.stat().st_size,'nodes':len(list(rt.objects))}
    path.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(meta,message='完整场景副本已保存：'+str(path))

@H.command('bone.connections')
def connections(p):
    pairs=[]
    for n in rt.objects:
        if H.cls(n)!='BoneGeometry' or n.parent is None or H.cls(n.parent)!='BoneGeometry':continue
        role=str(rt.getUserProp(n,'LXRole') or '');part=role[2:] if role.startswith(('L_','R_')) else role
        if not part or part.startswith(('Clavicle','Thigh')):continue
        if part.startswith(('Finger','Toe')) and not str(rt.getUserProp(n.parent,'LXRole') or '').startswith(role.split('_')[0]+'_'+part.split('_')[0]):continue
        parent=n.parent;end=parent.objectTransform.row4+parent.objectTransform.row1*float(parent.length)
        distance=float(rt.distance(end,n.pos))
        pairs.append({'parent':str(parent.name),'child':str(n.name),'distance':distance,'parentEnd':H.vec(end),'childStart':H.vec(n.pos)})
    threshold=float(p.get('tolerance',.001));broken=[v for v in pairs if v['distance']>threshold]
    return {'message':'检查 %d 处连续关节，%d 处断开'%(len(pairs),len(broken)),'pairs':pairs,'broken':broken}
