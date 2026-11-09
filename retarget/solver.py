"""Reference-space FK solver. Produces data only, never reads/writes a host."""
import math
import statistics
from .math3d import (Transform, compose, relative, q_inv, q_mul, q_slerp,
                     q_yaw, v_add, v_sub, v_mul, v_length,
                     polyline_parameters, q_curve_sample)
from .model import preflight, topological, world_transforms, chain_mapping_mode


class CancelledError(Exception):
    pass


def effective_scale(config):
    s = config.settings
    if s.scale_mode == "none":
        return 1.0
    if s.scale_mode == "manual":
        if not math.isfinite(s.scale) or s.scale <= 0:
            raise ValueError("平移尺度必须为大于零的有限数字")
        return float(s.scale)
    if s.scale_mode != "auto":
        raise ValueError("未知尺度策略")
    try:
        sw = world_transforms(config.source, config.source_reference)
        tw = world_transforms(config.target, config.target_reference)
    except ValueError:
        return 1.0  # preflight reports the incomplete/invalid reference separately.
    ratios, pairs = [], {}
    for chain in config.chains:
        if not chain.enabled or not chain.source or not chain.target:
            continue
        try:
            mode = chain_mapping_mode(chain)
            if mode == "resample":
                _, sl = polyline_parameters([sw[key].position for key in chain.source])
                _, tl = polyline_parameters([tw[key].position for key in chain.target])
                ratios.append(tl/sl)
            else:
                if len(chain.source) == len(chain.target):
                    pairs.update({tid:sid for sid,tid in zip(chain.source,chain.target)})
        except (KeyError, ValueError):
            continue  # preflight supplies the actionable validation error.
    for tid, sid in pairs.items():
        if tid not in config.target or sid not in config.source:
            continue
        sp, tp = config.source[sid].parent, config.target[tid].parent
        # Only compare corresponding actual edges; a world root offset is not a bone length.
        if not sp or not tp or pairs.get(tp) != sp:
            continue
        if sid not in config.source_reference or tid not in config.target_reference:
            continue
        sl = v_length(v_sub(sw[sid].position, sw[sp].position))
        tl = v_length(v_sub(tw[tid].position, tw[tp].position))
        if sl > 1e-7 and tl > 1e-7:
            ratios.append(tl/sl)
    return float(statistics.median(ratios)) if ratios else 1.0


def solve(config, samples, cancelled=None, target_samples=None):
    """Return mapped target LOCAL transforms for each supplied sampled frame.

    Ordinary nodes retain their reference local position and scale. Rotation is
    source world rotation delta from the captured reference, applied to target
    reference world rotation, then converted to the newly solved parent space.
    This compensates bone-axis rest differences, including unmapped ancestors.
    Resampled semantic chains interpolate source world motion deltas over their
    own reference arc coordinates; listed start/end joints remain exact anchors.
    """
    errors = [i.message for i in preflight(config) if i.severity == "error"]
    if errors:
        raise ValueError("预检未通过：\n" + "\n".join(errors))
    if not samples:
        raise ValueError("没有源动画采样")
    srw = world_transforms(config.source, config.source_reference)
    trw = world_transforms(config.target, config.target_reference)
    scale = effective_scale(config)
    order = topological(config.target)
    pairs, curves = {}, []
    for chain in config.chains:
        if not chain.enabled or (not chain.source and not chain.target):
            continue
        if chain_mapping_mode(chain) == "resample":
            source_t, _ = polyline_parameters([srw[key].position for key in chain.source])
            target_t, _ = polyline_parameters([trw[key].position for key in chain.target])
            curves.append((chain,source_t,target_t))
            for tid in chain.target:
                # A resampled target has a semantic coordinate, never a guessed
                # one-to-one source ID. Translation is prohibited by preflight.
                pairs[tid] = (None,chain)
        else:
            for sid,tid in zip(chain.source,chain.target):
                pairs[tid] = (sid,chain)
    result, last = {}, {}

    def check_cancel():
        if cancelled is not None and cancelled():
            raise CancelledError("重定向已取消；尚未写入宿主")

    for frame in sorted(samples):
        check_cancel()
        locals_src = samples[frame]
        for key in config.source:
            if key not in locals_src:
                raise ValueError(f"第 {frame} 帧缺少源节点采样：{config.source[key].name}")
            if any(abs(x-y) > 1e-5 for x, y in zip(locals_src[key].scale, config.source_reference[key].scale)):
                raise ValueError(f"第 {frame} 帧源节点 {config.source[key].name} 存在动态缩放，当前 FK 不支持")
        sw = world_transforms(config.source, locals_src)
        resampled_deltas = {}
        for chain, source_t, target_t in curves:
            check_cancel()
            deltas = [q_mul(sw[key].rotation,q_inv(srw[key].rotation)) for key in chain.source]
            for tid,t in zip(chain.target,target_t):
                check_cancel()
                resampled_deltas[tid] = q_curve_sample(source_t,deltas,t)
        target_local = config.target_reference
        if target_samples is not None:
            if frame not in target_samples or set(config.target)-set(target_samples[frame]):
                raise ValueError(f"第 {frame} 帧目标父空间采样不完整")
            target_local = target_samples[frame]
            for key in config.target:
                if any(abs(x-y) > 1e-5 for x, y in zip(target_local[key].scale, config.target_reference[key].scale)):
                    raise ValueError(f"第 {frame} 帧目标节点 {config.target[key].name} 存在动态缩放，当前 FK 不支持")
        elif any(n.animated and k not in pairs for k, n in config.target.items()):
            raise ValueError("未映射目标节点已有动画；求解时必须提供完整 target_samples 以确定真实父空间")
        worlds, out = {}, {}
        for tid in order:
            check_cancel()
            ref = config.target_reference[tid]
            parent = config.target[tid].parent
            pw = worlds.get(parent)
            if tid not in pairs:
                actual = target_local[tid]
                worlds[tid] = compose(pw, actual) if pw else actual
                continue
            sid, chain = pairs[tid]
            delta = (resampled_deltas[tid] if tid in resampled_deltas else
                     q_mul(sw[sid].rotation, q_inv(srw[sid].rotation)))
            if chain.kind == "root" and config.settings.root_mode == "in_place":
                delta = (0, 0, 0, 1)
            elif chain.kind == "root" and config.settings.root_mode == "horizontal":
                delta = q_yaw(delta)
            desired_world_q = q_mul(delta, trw[tid].rotation)
            desired_local_q = q_mul(q_inv(pw.rotation), desired_world_q) if pw else desired_world_q
            local_q = q_mul(q_slerp(ref.rotation, desired_local_q, chain.rotation_weight), chain.offset)
            pos = target_local[tid].position
            if chain.kind == "root":
                motion = v_mul(v_sub(sw[sid].position, srw[sid].position), scale)
                mode = config.settings.root_mode
                if mode == "in_place":
                    motion = (0, 0, 0)
                elif mode == "horizontal":
                    motion = (motion[0], motion[1], 0)
                desired_pos = v_add(trw[tid].position, motion)
                if pw:
                    pos = relative(pw, Transform(desired_pos, desired_world_q, trw[tid].scale)).position
                else:
                    pos = desired_pos
            elif chain.translation_weight:
                local_delta = v_sub(locals_src[sid].position, config.source_reference[sid].position)
                # Anchor to the captured reference, not a previously baked target
                # frame; repeated pelvis/chain translation must be idempotent.
                pos = v_add(ref.position, v_mul(local_delta, scale*chain.translation_weight))
            # q and -q are identical rotations; keep a continuous component branch.
            if tid in last and sum(x*y for x, y in zip(local_q, last[tid])) < 0:
                local_q = tuple(-x for x in local_q)
            local = Transform(pos, local_q, ref.scale)
            out[tid] = local
            last[tid] = local.rotation
            worlds[tid] = compose(pw, local) if pw else local
        result[frame] = out
    return result
