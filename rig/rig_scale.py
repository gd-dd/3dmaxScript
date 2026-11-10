"""World-space skeleton measurements without Max or UI dependencies.

Records contain ``id``, ``parent``, ``category`` and (for bones) ``position``
and optional ``end`` world coordinates. Optional ``rigId``, ``role``,
``biped``/``class`` and ``controller`` identify disconnected LX chains and
Biped COMs. A controller's ``anchor`` may identify its IK start joint;
``endJoint`` can check that the chain stays in the same skeleton. A decoded
``controlGroup`` tuple/list retains the group of previously created controls.

Only bone coordinates affect size. Ordinary untagged skeletons are connected
through bone ancestors, including intervening controllers. A shared world
Dummy does not merge independent bone roots. For disconnected branches, use
an explicit BodyCenter or a unique rigId; names/proximity are not identity.
Within a connected bone chain, ancestor identity takes priority over partial
tags; a new BodyCenter starts an independent hierarchy boundary.
"""
import math


def _point(value):
    try:
        result=tuple(float(v) for v in value)
    except (ValueError,TypeError):
        raise ValueError('骨架坐标必须是三个有限数值') from None
    if len(result)!=3 or not all(math.isfinite(v) for v in result):
        raise ValueError('骨架坐标必须是三个有限数值')
    return result


def display_size(height,ratio):
    """A world-unit display dimension. No arbitrary scene-unit fallback."""
    height=float(height);ratio=float(ratio)
    if not math.isfinite(height) or height<=0:
        raise ValueError('骨架尺寸为零或无效，无法自动设置显示大小')
    if not math.isfinite(ratio) or ratio<=0:
        raise ValueError('显示比例必须为大于零的有限数值')
    result=height*ratio
    if not math.isfinite(result) or result<=0:
        raise ValueError('显示尺寸超出有效范围')
    return result


def measure(records,flat_ratio=.25):
    """Measure bones only; lying rigs use their largest world-axis span.

    The returned height is a display scale, not a recovered bind-pose stature.
    For a single bone, use its actual segment length. A completely coincident
    skeleton is an error so callers can request a size instead of guessing 10.
    """
    if not math.isfinite(flat_ratio) or not 0<flat_ratio<=1:
        raise ValueError('平躺判断比例必须在 (0, 1] 内')
    bones=[r for r in records if r.get('category')=='bones']
    if not bones:raise ValueError('没有可测量的骨骼')
    points=[];lengths=[]
    for record in bones:
        start=_point(record['position']);end=_point(record.get('end',start))
        points.extend((start,end));lengths.append(math.dist(start,end))
    lo=tuple(min(p[i] for p in points) for i in range(3))
    hi=tuple(max(p[i] for p in points) for i in range(3))
    spans=tuple(hi[i]-lo[i] for i in range(3));largest=max(spans)
    if not math.isfinite(largest) or largest<=0:
        raise ValueError('骨架起终点全部重合，无法自动判断显示大小')
    if len(bones)==1 and lengths[0]>0:
        height=lengths[0];method='segment_length'
    elif spans[2]>=largest*flat_ratio:
        height=spans[2];method='world_z'
    else:
        height=largest;method='largest_axis'
    if not math.isfinite(height) or height<=0:
        raise ValueError('骨架测量尺寸超出有效范围')
    return dict(height=height,spans=spans,minimum=lo,maximum=hi,method=method)


def skeleton_scales(records,targets=None):
    """Return node-id -> measurement for each unambiguous skeleton member.

    Group identifiers are tuples, stable for the provided hierarchy. Controls
    can inherit a group via rigId, IK anchor, bone ancestor, or uniquely grouped
    descendants. Models and ambiguous shared world roots never get a mapping.
    If targets is provided, only their groups are measured; the entire groups
    still contribute, including unselected bones. This excludes unrelated
    degenerate skeletons without inventing a size. Unknown targets raise.
    No record or host object is modified.
    """
    records=list(records);by_id={str(r['id']):r for r in records}
    if len(by_id)!=len(records):raise ValueError('骨架对象标识重复')
    bones={k:r for k,r in by_id.items() if r.get('category')=='bones'}
    if not bones:return {}
    parents={k:str(r['parent']) if r.get('parent') is not None else None for k,r in by_id.items()}
    ancestry={}
    def ancestors(key):
        if key not in ancestry:
            chain=[];seen={key};parent=parents[key]
            while parent in by_id:
                if parent in seen:raise ValueError('骨架父子层级包含循环')
                seen.add(parent);chain.append(parent);parent=parents[parent]
            ancestry[key]=tuple(chain)
        return ancestry[key]
    def is_biped(r):return bool(r.get('biped')) or str(r.get('class','')).lower()=='biped_object'
    def rig_id(r):return str(r.get('rigId') or '')
    def body_center(key):
        return next((a for a in (key,*ancestors(key)) if by_id[a].get('role')=='BodyCenter'),None)
    def biped_group(key):
        bip_chain=[a for a in (key,*ancestors(key)) if is_biped(by_id[a])]
        com=next((a for a in bip_chain if str(by_id[a].get('controller','')).lower()=='vertical_horizontal_turn'),None)
        return ('biped',com or bip_chain[-1])
    def bone_group(key):
        if is_biped(by_id[key]):return biped_group(key)
        connected=[key]
        # Resolve connected ancestors BEFORE a child's own metadata fallback.
        # A BodyCenter is an explicit boundary; generic helpers are not.
        for a in ancestors(key):
            parent=by_id[a]
            if parent.get('category') not in ('bones','controls') or parent.get('role')=='BodyCenter':break
            if a in bones:connected.append(a)
        biped=next((a for a in connected if is_biped(by_id[a])),None)
        if biped:return biped_group(biped)
        tags={rig_id(by_id[a]) for a in connected if rig_id(by_id[a])}
        if len(tags)>1:raise ValueError('同一骨骼链的骨架标记不一致，请先修复 rigId')
        top=connected[-1];center=body_center(top)
        if rig_id(by_id[top]):return ('rig',rig_id(by_id[top]),center or '')
        if center:return ('center',center)
        return ('tree',top)
    groups={};keys={}
    for key in bones:
        group=bone_group(key);keys[key]=group;groups.setdefault(group,[]).append(key)
    node_groups=dict(keys)
    for key,r in by_id.items():
        if r.get('category')!='controls':continue
        candidates=set()
        saved=r.get('controlGroup')
        if isinstance(saved,(tuple,list)) and all(isinstance(v,str) for v in saved):
            saved=tuple(saved)
            if saved in groups:candidates.add(saved)
        anchors=[str(r[field]) for field in ('anchor','endJoint') if r.get(field) is not None]
        for anchor in anchors:
            if anchor in keys:candidates.add(keys[anchor])
        if len(candidates)>1:raise ValueError('控制器标记或 IK 起止关节属于不同骨架')
        if not candidates and r.get('role')=='BodyCenter' and not is_biped(r):
            # Its own skeleton wins over any external bone it is parented to.
            candidates={keys[b] for b in bones if body_center(b)==key}
            if len(candidates)==1:node_groups[key]=next(iter(candidates))
            continue
        if not candidates and is_biped(r):
            candidates={g for g in groups if g[0]=='biped' and g[1]==key}
            if not candidates:
                candidates={keys[a] for a in ancestors(key) if a in keys}
                if not candidates:
                    candidates={g for g in groups if g[0]=='biped' and g[1] in ancestors(key)}
        if not candidates and rig_id(r):
            candidates={g for g in groups if g[0]=='rig' and g[1]==rig_id(r) and (not body_center(key) or g[2]==body_center(key))}
        if not candidates:
            nearest=next((a for a in ancestors(key) if a in keys),None)
            if nearest:candidates={keys[nearest]}
        if not candidates:
            candidates={keys[b] for b in bones if key in ancestors(b)}
        if len(candidates)==1:node_groups[key]=next(iter(candidates))
    if targets is None:wanted=set(groups)
    else:
        targets=[str(key) for key in targets]
        if any(key not in node_groups for key in targets):
            raise ValueError('所选对象无法唯一对应一套骨架')
        wanted={node_groups[key] for key in targets}
    sizes={}
    for group in wanted:
        ids=groups[group]
        sizes[group]=dict(measure([bones[k] for k in ids]),group=group,bones=tuple(ids))
    return {key:sizes[group] for key,group in node_groups.items() if group in sizes}
