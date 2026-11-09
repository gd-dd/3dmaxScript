"""Portable scene data and conservative retarget preflight."""
from dataclasses import dataclass, field
import math
from .math3d import Transform, compose, v_length, polyline_parameters


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    parent: str | None = None
    path: str = ""
    kind: str = "bone"
    writable: bool = True
    constraints: bool = False
    animated: bool = False


@dataclass
class Chain:
    name: str
    source: list[str] = field(default_factory=list)
    target: list[str] = field(default_factory=list)
    kind: str = "custom"
    rotation_weight: float = 1.0
    translation_weight: float = 0.0
    offset: tuple = (0.0, 0.0, 0.0, 1.0)
    enabled: bool = True
    mapping_mode: str = "auto"

    @property
    def id(self):
        return self.name

    @property
    def label(self):
        return self.name


@dataclass
class Settings:
    start: int = 0
    end: int = 30
    step: int = 1
    root_mode: str = "global"
    scale_mode: str = "auto"
    scale: float = 1.0
    reference_frame: int = 0
    existing_animation: str = "reject_existing"

    def frames(self):
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (self.start, self.end, self.step)):
            raise ValueError("帧范围与采样步长必须为整数")
        if self.start > self.end or self.step <= 0:
            raise ValueError("结束帧必须不早于开始帧，采样步长必须大于零")
        if (self.end-self.start)//self.step > 100000:
            raise ValueError("单次采样不能超过 100001 帧，请拆分区间")
        result = list(range(self.start, self.end+1, self.step))
        if result[-1] != self.end:
            result.append(self.end)
        return result


@dataclass
class SessionConfig:
    source: dict[str, Node] = field(default_factory=dict)
    target: dict[str, Node] = field(default_factory=dict)
    chains: list[Chain] = field(default_factory=list)
    source_reference: dict[str, Transform] = field(default_factory=dict)
    target_reference: dict[str, Transform] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    node_id: str = ""


def topological(nodes):
    """Parents before children; explicit errors on broken graph or cycles."""
    done, order = set(), []
    for key in nodes:
        trail, seen = [], set()
        while key is not None and key not in done:
            if key in seen:
                raise ValueError(f"骨架拓扑存在环：{key}")
            if key not in nodes:
                raise ValueError(f"缺少父节点 {key}")
            trail.append(key)
            seen.add(key)
            key = nodes[key].parent
        for key in reversed(trail):
            done.add(key)
            order.append(key)
    return order


def world_transforms(nodes, locals):
    result = {}
    for key in topological(nodes):
        if key not in locals:
            raise ValueError(f"节点 {key} 缺少姿态数据")
        parent = nodes[key].parent
        result[key] = compose(result[parent], locals[key]) if parent else locals[key]
    return result


def humanoid_chains():
    return [Chain(name, kind=kind) for name, kind in (
        ("运动根", "root"), ("骨盆", "hips"), ("脊柱", "spine"),
        ("颈与头", "head"), ("左臂", "arm_l"), ("右臂", "arm_r"),
        ("左手", "hand_l"), ("右手", "hand_r"), ("左腿", "leg_l"),
        ("右腿", "leg_r"), ("左脚", "foot_l"), ("右脚", "foot_r"))]


def chain_mapping_mode(chain):
    """Resolve selection policy without silently enabling arbitrary resampling."""
    if chain.mapping_mode not in ("auto", "direct", "resample"):
        raise ValueError("链映射模式必须为 auto、direct 或 resample")
    if chain.mapping_mode == "auto":
        if len(chain.source) != len(chain.target) and chain.kind in ("spine", "neck", "head"):
            return "resample"
        return "direct"
    return chain.mapping_mode


def preflight(config):
    issues = []

    def add(sev, code, msg, node=""):
        issues.append(Issue(sev, code, msg, node))

    s = config.settings
    try:
        s.frames()
    except ValueError as exc:
        add("error", "range", str(exc))
    if s.root_mode not in ("global", "in_place", "horizontal"):
        add("error", "root_mode", "根运动模式不受支持")
    if s.scale_mode not in ("auto", "manual", "none"):
        add("error", "scale_mode", "尺度策略不受支持")
    if isinstance(s.scale, bool) or not isinstance(s.scale, (int, float)) or not math.isfinite(s.scale) or s.scale <= 0:
        add("error", "scale", "平移尺度必须是大于零的有限数字")
    if s.existing_animation not in ("replace_range", "reject", "reject_existing", "new_layer"):
        add("error", "animation_mode", "目标动画策略必须为区间覆盖、拒绝已有动画或专用新层")
    if set(config.source) & set(config.target):
        add("error", "overlap", "源骨架与目标骨架有交叉归属，请分开选取")
    for side, nodes, ref in (("源", config.source, config.source_reference), ("目标", config.target, config.target_reference)):
        if not nodes:
            add("error", "empty_skeleton", f"尚未读取{side}骨架")
        try:
            topological(nodes)
        except ValueError as exc:
            add("error", "topology", f"{side}：{exc}")
        if len({n.path for n in nodes.values() if n.path}) < len([n for n in nodes.values() if n.path]):
            add("warning", "duplicate_path", f"{side}存在同路径节点，保存后需要人工重绑定")
        for key, node in nodes.items():
            if node.kind == "unbound":
                add("error", "unbound", f"{side}节点尚未重绑定：{node.name}", key)
            if key != node.id:
                add("error", "node_id", f"{side}节点标识不一致：{node.name}", key)
            if key not in ref:
                add("error", "reference_missing", f"{side}节点未捕获参考姿态：{node.name}", key)
                continue
            scale = ref[key].scale
            if min(scale) <= 0:
                add("error", "negative_scale", f"{side}节点有零或负缩放：{node.name}", key)
            elif max(scale)-min(scale) > 1e-5:
                add("error", "nonuniform_scale", f"{side}节点有非均匀缩放：{node.name}；当前 FK 不写入该骨架", key)
            if node.parent and v_length(ref[key].position) < 1e-7:
                add("warning", "zero_length", f"{side}节点与父节点重合：{node.name}；不能用作比例测量", key)
    used, active = {}, 0
    roots = 0
    reference_worlds = {}
    for side in ("source", "target"):
        try:
            reference_worlds[side] = world_transforms(getattr(config,side),getattr(config,side+"_reference"))
        except ValueError:
            reference_worlds[side] = {}  # Missing references/topology are reported above.
    if len({c.name for c in config.chains}) != len(config.chains):
        add("error", "chain_name", "映射链名称必须唯一")
    for chain in config.chains:
        if not chain.enabled:
            continue
        if not chain.source and not chain.target:
            add("warning", "empty_chain", f"{chain.name}未映射，将保持目标原状态")
            continue
        active += 1
        if not chain.source or not chain.target:
            add("error", "incomplete_chain", f"{chain.name}缺少一侧节点")
        try:
            mapping_mode = chain_mapping_mode(chain)
        except ValueError as exc:
            mapping_mode = None
            add("error", "mapping_mode", f"{chain.name}：{exc}")
        unequal = len(chain.source) != len(chain.target)
        if mapping_mode == "direct" and unequal:
            add("error", "chain_length", f"{chain.name}逐节点映射需要相同节点数；自动异数重采样仅适用于脊柱/颈/头，其他连续链需明确选择语义重采样")
        if chain.kind == "root":
            roots += 1
            if len(chain.source) != 1 or len(chain.target) != 1:
                add("error", "root_length", "运动根需要且只能一对节点；骨盆请使用独立链")
        if chain.kind == "hips" and (len(chain.source) != 1 or len(chain.target) != 1):
            add("error", "hips_length", "骨盆需要且只能一对节点；脊柱请使用独立语义链")
        if mapping_mode == "resample":
            if chain.kind in ("root", "hips"):
                add("error", "root_hips_resample", f"{chain.name}运动根/骨盆不允许语义重采样，必须单节点对应")
            else:
                for side, keys in (("source", chain.source),("target",chain.target)):
                    if len(keys) < 2:
                        add("error", "resample_span", f"{chain.name}{'源' if side=='source' else '目标'}语义链至少需要两个不同位置的节点")
                    elif all(key in reference_worlds[side] for key in keys):
                        try:
                            polyline_parameters([reference_worlds[side][key].position for key in keys])
                        except ValueError as exc:
                            add("error", "resample_span", f"{chain.name}{'源' if side=='source' else '目标'}：{exc}")
                if chain.translation_weight != 0:
                    add("error", "resample_translation", f"{chain.name}语义重采样只转移旋转；平移权重必须为零，根/骨盆平移请单独映射")
        for weight, label in ((chain.rotation_weight, "旋转"), (chain.translation_weight, "平移")):
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 1:
                add("error", "weight", f"{chain.name}{label}权重必须在 0 到 1 之间")
        try:
            Transform(rotation=chain.offset)
        except (ValueError, TypeError):
            add("error", "offset", f"{chain.name}旋转偏移无效")
        for side, keys, nodes in (("源", chain.source, config.source), ("目标", chain.target, config.target)):
            if len(keys) != len(set(keys)):
                add("error", "duplicate_chain_node", f"{chain.name}{side}链包含重复节点")
            previous = None
            for key in keys:
                if key not in nodes:
                    add("error", "missing_node", f"{chain.name}{side}节点已失效：{key}", key)
                    continue
                node = nodes[key]
                if previous and node.parent != previous:
                    add("error", "chain_order", f"{chain.name}{side}链需按直接父子顺序排列：{node.name}", key)
                previous = key
                if side == "目标":
                    if key in used:
                        add("error", "duplicate_target", f"目标 {node.name} 同时分配到 {used[key]} 和 {chain.name}", key)
                    used[key] = chain.name
                    if not node.writable or node.kind.lower() in ("cat", "unsupported") or node.constraints:
                        add("error", "controller", f"目标 {node.name} 的 {node.kind} 控制器未通过普通 PRS 写入验证或有约束；需要专用适配", key)
                    if node.animated:
                        add("error" if s.existing_animation in ("reject", "reject_existing") else "warning", "existing_animation", f"目标 {node.name} 已有动画；区间覆盖须保留区间外数据和未映射轨道", key)
        if chain.translation_weight:
            add("warning", "translation", f"{chain.name}已启用局部平移权重，可能改变骨长")
    if not active:
        add("error", "no_mapping", "至少建立一条有效映射链")
    if roots > 1:
        add("error", "multiple_roots", "只能指定一条运动根链")
    if roots == 0:
        add("warning", "no_root", "尚未指定运动根；仅转移旋转和明确启用的局部平移")
    return issues
