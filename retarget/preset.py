"""Versioned portable JSON; runtime handles are replaced by preset-only IDs."""
from dataclasses import asdict, dataclass, replace
import json
import math
import os
from pathlib import Path
import tempfile
from .math3d import Transform
from .model import Node, Chain, Settings, SessionConfig

SCHEMA_VERSION = 2
MAPPING_MODES = {"auto", "direct", "resample"}


def dumps(config):
    ids = {side: {old: f"{side}:{i}" for i, old in enumerate(nodes)}
           for side, nodes in (("source", config.source), ("target", config.target))}
    data = {"schemaVersion": SCHEMA_VERSION, "producer": "LXMaxRetarget",
            "settings": asdict(config.settings), "chains": [], "source": [], "target": [],
            "source_reference": {}, "target_reference": {}}
    for side in ("source", "target"):
        nodes, ref = getattr(config, side), getattr(config, side+"_reference")
        for old, node in nodes.items():
            row = asdict(node)
            row["id"] = ids[side][old]
            row["parent"] = ids[side].get(node.parent)
            data[side].append(row)
        data[side+"_reference"] = {ids[side][k]: asdict(v) for k, v in ref.items() if k in ids[side]}
    for chain in config.chains:
        row = asdict(chain)
        row.setdefault("mapping_mode", "auto")
        try:
            row["source"] = [ids["source"][key] for key in chain.source]
            row["target"] = [ids["target"][key] for key in chain.target]
        except KeyError as exc:
            raise ValueError(f"映射含失效节点，保存前请修复：{exc}") from exc
        data["chains"].append(row)
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def _object(value, allowed, name, required=()):
    if not isinstance(value, dict):
        raise ValueError(f"{name}必须为 JSON 对象")
    unknown = set(value)-set(allowed)
    if unknown:
        raise ValueError(f"{name}含未知字段：{', '.join(sorted(unknown))}")
    missing = set(required)-set(value)
    if missing:
        raise ValueError(f"{name}缺少字段：{', '.join(sorted(missing))}")


def _str(value, name, empty=False):
    if not isinstance(value, str) or (not empty and not value) or len(value) > 4096:
        raise ValueError(f"{name}必须是有效字符串")
    return value


def _bool(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name}必须是布尔值")
    return value


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}必须是有限数字")
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 含重复字段：{key}")
        result[key] = value
    return result


def loads(text):
    if not isinstance(text, str) or len(text) > 8*1024*1024:
        raise ValueError("预设必须是小于 8 MiB 的 UTF-8 JSON 文本")
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"不允许 {v}")))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"预设 JSON 损坏：{exc}") from exc
    fields = {"schemaVersion", "producer", "source", "target", "chains", "settings",
              "source_reference", "target_reference"}
    _object(data, fields, "预设", fields-{"producer"})
    version = data["schemaVersion"]
    if type(version) is not int or version not in (1, SCHEMA_VERSION):
        raise ValueError(f"不支持预设 schemaVersion {version}；当前可读取版本 1 和 2，原文件未修改")
    sides, refs = {}, {}
    node_fields = {"id", "name", "parent", "path", "kind", "writable", "constraints", "animated"}
    for side in ("source", "target"):
        if not isinstance(data[side], list) or len(data[side]) > 20000:
            raise ValueError(f"{side}节点必须是最多 20000 项的数组")
        nodes = {}
        for row in data[side]:
            _object(row, node_fields, f"{side}节点", ("id", "name"))
            key = _str(row["id"], "节点ID")
            if key in nodes:
                raise ValueError(f"{side}节点ID重复：{key}")
            _str(row["name"], "节点名称")
            for attr in ("path", "kind"):
                if attr in row:
                    _str(row[attr], attr, empty=attr == "path")
            if row.get("parent") is not None:
                _str(row["parent"], "父节点ID")
            for attr in ("writable", "constraints", "animated"):
                if attr in row:
                    _bool(row[attr], attr)
            nodes[key] = Node(**row)
        for node in nodes.values():
            if node.parent is not None and node.parent not in nodes:
                raise ValueError(f"{side}预设缺少父节点 {node.parent}")
        sides[side] = nodes
        transforms = data[side+"_reference"]
        if not isinstance(transforms, dict) or set(transforms)-set(nodes):
            raise ValueError(f"{side}参考姿态含未知节点或格式错误")
        refs[side] = {}
        for key, value in transforms.items():
            _object(value, {"position", "rotation", "scale"}, "参考姿态", ("position", "rotation", "scale"))
            refs[side][key] = Transform(**value)
    settings_row = data["settings"]
    _object(settings_row, Settings.__dataclass_fields__, "设置")
    for attr in ("start", "end", "step", "reference_frame"):
        if attr in settings_row and (isinstance(settings_row[attr], bool) or not isinstance(settings_row[attr], int)):
            raise ValueError(f"{attr}必须是整数")
    for attr in ("root_mode", "scale_mode", "existing_animation"):
        if attr in settings_row:
            _str(settings_row[attr], attr)
    if "scale" in settings_row:
        _number(settings_row["scale"], "scale")
    settings = Settings(**settings_row)
    settings.frames()
    if settings.root_mode not in ("global", "in_place", "horizontal") or settings.scale_mode not in ("auto", "manual", "none"):
        raise ValueError("预设含不支持的根运动或尺度策略")
    if settings.scale <= 0 or settings.existing_animation not in ("reject", "reject_existing", "replace_range", "new_layer"):
        raise ValueError("预设尺度或已有动画策略无效")
    if not isinstance(data["chains"], list) or len(data["chains"]) > 2000:
        raise ValueError("chains必须是最多 2000 项的数组")
    chains, names = [], set()
    for row in data["chains"]:
        # Legacy presets always retain their original direct correspondence.
        # A schema migration must never silently enable anatomical resampling.
        allowed = set(Chain.__dataclass_fields__)
        required = {"name", "source", "target"}
        if version == 1:
            allowed.discard("mapping_mode")
        else:
            required.add("mapping_mode")
        _object(row, allowed, "映射链", required)
        row = dict(row)
        if version == 1:
            row["mapping_mode"] = "direct"
        mode = row.get("mapping_mode")
        if not isinstance(mode, str) or mode not in MAPPING_MODES:
            raise ValueError("映射模式必须为 auto、direct 或 resample")
        name = _str(row["name"], "链名")
        if name in names:
            raise ValueError(f"映射链名称重复：{name}")
        names.add(name)
        for side in ("source", "target"):
            if not isinstance(row[side], list) or any(not isinstance(k, str) or k not in sides[side] for k in row[side]):
                raise ValueError(f"{name}的{side}节点列表格式错误或引用失效")
        if "kind" in row:
            _str(row["kind"], "链类型")
        for attr in ("rotation_weight", "translation_weight"):
            if attr in row and not 0 <= _number(row[attr], attr) <= 1:
                raise ValueError(f"{name}权重必须在 0 到 1 之间")
        if "enabled" in row:
            _bool(row["enabled"], "enabled")
        if "offset" in row:
            row["offset"] = Transform(rotation=row["offset"]).rotation
        chains.append(Chain(**row))
    return SessionConfig(sides["source"], sides["target"], chains, refs["source"], refs["target"], settings)


def save(path, config):
    """Validate before atomically replacing; failed save leaves previous file intact."""
    text = dumps(config)
    loads(text)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def load(path):
    if Path(path).stat().st_size > 8*1024*1024:
        raise ValueError("预设不能超过 8 MiB")
    return loads(Path(path).read_text(encoding="utf-8-sig"))


@dataclass(frozen=True)
class BindingIssue:
    side: str
    preset_id: str
    name: str
    candidates: list[str]
    reason: str


def _binding_candidates(saved, nodes):
    exact = [k for k, node in nodes.items() if saved.path and node.path == saved.path]
    if exact:
        return exact, "全路径相同" if len(exact) == 1 else "全路径重名，需确认"
    names = [k for k, node in nodes.items() if node.name == saved.name]
    if names:
        return names, "名称相同但路径变化，需确认"
    leaf = saved.name.rsplit(":", 1)[-1].lower()
    hints = [k for k, node in nodes.items() if node.name.rsplit(":", 1)[-1].lower() == leaf]
    return hints, "命名空间或名称变化，需确认" if hints else "场景中找不到节点，请手动指定"


def rebind(config, source_nodes, target_nodes):
    bindings, issues = {"source": {}, "target": {}}, []
    for side, nodes in (("source", source_nodes), ("target", target_nodes)):
        for key, saved in getattr(config, side).items():
            candidates, reason = _binding_candidates(saved, nodes)
            if saved.path and len(candidates) == 1 and nodes[candidates[0]].path == saved.path:
                bindings[side][key] = candidates[0]
            else:
                issues.append(BindingIssue(side, key, saved.name, candidates, reason))
        # Deleted duplicate-name nodes can make two saved identities point at
        # one surviving path. Keep both unresolved instead of arbitrarily merging.
        collisions = {target for target in bindings[side].values()
                      if list(bindings[side].values()).count(target) > 1}
        for key, target in list(bindings[side].items()):
            if target in collisions:
                issues.append(BindingIssue(side, key, getattr(config, side)[key].name,
                                           [target], "多个预设节点对应同一场景路径，需确认"))
                del bindings[side][key]
    return apply_bindings(config, source_nodes, target_nodes, bindings["source"], bindings["target"]), issues


def apply_bindings(config, source_nodes, target_nodes, source_bindings, target_bindings):
    """Apply explicit bindings; unresolved placeholders block host preflight."""
    sides, refs, maps = {}, {}, {}
    for side, current, bindings in (("source", source_nodes, source_bindings), ("target", target_nodes, target_bindings)):
        saved = getattr(config, side)
        if set(bindings)-set(saved) or any(k not in current for k in bindings.values()):
            raise ValueError(f"{side}重绑定引用不存在的节点")
        if len(set(bindings.values())) != len(bindings):
            raise ValueError(f"{side}不能将多个预设节点重绑定到同一节点")
        maps[side] = {key: bindings.get(key, f"unbound:{side}:{key}") for key in saved}
        sides[side] = dict(current)
        for key, node in saved.items():
            if key not in bindings:
                placeholder = maps[side][key]
                sides[side][placeholder] = replace(node, id=placeholder,
                    parent=maps[side].get(node.parent), kind="unbound", writable=False)
        refs[side] = {maps[side][key]: value for key, value in getattr(config, side+"_reference").items()}
    chains = [replace(c, source=[maps["source"][k] for k in c.source],
                      target=[maps["target"][k] for k in c.target]) for c in config.chains]
    return SessionConfig(sides["source"], sides["target"], chains, refs["source"], refs["target"], replace(config.settings))
