"""Conservative anatomical/name candidates; no scene or mapping mutations."""
from dataclasses import dataclass
import re
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Suggestion:
    source_id: str
    target_id: str
    confidence: float
    reason: str


_PARTS = (
    ("upperarm", ("upperarm", "uparm", "上臂", "大臂", "arm")),
    ("forearm", ("forearm", "lowerarm", "前臂", "小臂", "elbow")),
    ("clavicle", ("clavicle", "collar", "肩", "shoulder")),
    ("thigh", ("thigh", "upleg", "upperleg", "大腿")),
    ("calf", ("calf", "lowerleg", "小腿", "shin", "leg", "knee")),
    ("finger", ("finger", "thumb", "index", "middle", "ring", "pinky", "手指", "拇", "食指", "中指", "无名", "小指")),
    ("toe", ("toebase", "toe", "脚趾", "足趾")),
    ("hand", ("hand", "wrist", "手掌", "手腕")),
    ("foot", ("foot", "ankle", "脚", "足", "踝")),
    ("hips", ("pelvis", "hips", "hip", "骨盆", "胯")),
    ("spine", ("spine", "chest", "torso", "脊", "胸", "腰")),
    ("neck", ("neck", "颈", "脖")),
    ("head", ("head", "头")),
    ("root", ("root", "com", "global", "master", "根")),
)


def _identity(name):
    text = str(name).rsplit(":", 1)[-1].strip()
    # Bip001 itself is the Biped COM; Bip001 Pelvis is distinct.
    bip_root = re.fullmatch(r"bip(?:ed)?[\s_\-]*\d*", text, re.I) is not None
    text = re.sub(r"^bip(?:ed)?[\s_\-]*\d*[\s_\-]*", "", text, flags=re.I)
    text = re.sub(r"^(?:source|target|src|tgt|rig|bone|armature)[\s_\-]+", "", text, flags=re.I)
    low = text.lower()
    side = "l" if "left" in low or "左" in low else "r" if "right" in low or "右" in low else ""
    if not side:
        match = re.search(r"(?:^|[\s_.\-])([lr])(?:$|[\s_.\-])", low)
        if match:
            side = match[1]
        elif re.match(r"^[LR](?:Upper|Lower|Arm|Hand|Leg|Foot|Thigh|Calf|Clavicle|Shoulder)", text):
            side = text[0].lower()
    stripped = re.sub(r"left|right|左|右", "", low)
    stripped = re.sub(r"(?:^|[\s_.\-])([lr])(?=$|[\s_.\-])", "", stripped)
    compact = re.sub(r"[\s_.\-]", "", stripped)
    if bip_root:
        return "root", "", "", "root"
    # More specific patterns need priority over their suffixes (forearm before arm).
    parts = sorted(_PARTS, key=lambda row: max(len(a) for a in row[1]), reverse=True)
    candidates = [(len(alias), part, alias) for part, aliases in parts for alias in aliases if alias in compact]
    if candidates:
        _, part, alias = max(candidates, key=lambda x: x[0])
        number = "".join(re.findall(r"\d+", compact))
        # Preserve finger identity; index and ring must never share an auto candidate.
        detail = alias if part == "finger" else ""
        return part, side, number+detail, compact
    return "", side, "", compact


def chain_role(name):
    part, side, _, _ = _identity(name)
    if part == "root":
        return "运动根"
    if part == "hips":
        return "骨盆"
    if part == "spine":
        return "脊柱"
    if part in ("head", "neck"):
        return "颈与头"
    prefix = {"l": "左", "r": "右"}.get(side)
    if not prefix:
        return None
    if part in ("upperarm", "forearm", "clavicle"):
        return prefix+"臂"
    if part == "hand":
        return prefix+"手"
    if part in ("thigh", "calf"):
        return prefix+"腿"
    if part in ("foot", "toe"):
        return prefix+"脚"
    return None


def suggest(source_nodes, target_nodes):
    result = []
    for sid, source in source_nodes.items():
        sp, ss, sn, sc = _identity(source.name)
        candidates = []
        for tid, target in target_nodes.items():
            tp, ts, tn, tc = _identity(target.name)
            if ss != ts and (ss or ts):
                continue
            if sp and tp and sp != tp:
                continue
            if sp == "finger" and re.sub(r"\d", "", sn) != re.sub(r"\d", "", tn):
                continue
            score, reason = 0.0, ""
            if sc and sc == tc:
                score, reason = .98, "去命名空间/骨架前缀后的名称一致"
            elif sp and sp == tp and sn == tn:
                score, reason = .90, "解剖部位、左右侧与序号一致"
            elif sp and sp == tp:
                score, reason = .64, "部位和左右侧一致，序号不同，需确认链段"
            elif not sp and not tp:
                similarity = SequenceMatcher(None, sc, tc).ratio()
                if similarity >= .75:
                    score, reason = similarity*.65, "名称相似，缺少解剖依据，需人工确认"
            if score:
                candidates.append(Suggestion(sid, tid, score, reason))
        candidates.sort(key=lambda x: (-x.confidence, target_nodes[x.target_id].name, x.target_id))
        for candidate in candidates[:4]:
            tied = sum(abs(x.confidence-candidate.confidence) < 1e-9 for x in candidates) > 1
            if tied:
                candidate = Suggestion(candidate.source_id, candidate.target_id,
                                       candidate.confidence*.8, candidate.reason+"；存在同分候选")
            result.append(candidate)
    return result


def mirror_name(name):
    """Swap recognizable side markers without modifying a mapping."""
    for left, right in (("Left", "Right"), ("left", "right"), ("LEFT", "RIGHT"), ("左", "右")):
        if left in name or right in name:
            return name.replace(left, "\0").replace(right, left).replace("\0", right)
    return re.sub(r"(^|[\s_.\-])([lLrR])(?=$|[\s_.\-])",
                  lambda m: m[1]+{"l": "r", "r": "l", "L": "R", "R": "L"}[m[2]], name)
