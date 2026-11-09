"""Dependency-free rigid transform math; Hamilton xyzw, active column vectors."""
from dataclasses import dataclass
from bisect import bisect_right
import math

EPS = 1e-9


def v_add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def v_sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def v_mul(a, f):
    return tuple(x * f for x in a)


def v_length(a):
    return math.sqrt(sum(x * x for x in a))


def q_normalize(q):
    n = math.sqrt(sum(x * x for x in q))
    if n < EPS or not math.isfinite(n):
        raise ValueError("旋转四元数不能为零或非有限值")
    return tuple(x / n for x in q)


def q_mul(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return (w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z)


def q_inv(q):
    n = sum(x*x for x in q)
    if n < EPS:
        raise ValueError("旋转四元数不能为零")
    return (-q[0]/n, -q[1]/n, -q[2]/n, q[3]/n)


def q_rotate(q, p):
    return q_mul(q_mul(q, (*p, 0.0)), q_inv(q))[:3]


def q_axis_angle(axis, angle):
    """angle is in radians."""
    n = v_length(axis)
    if n < EPS:
        raise ValueError("旋转轴不能为零")
    s = math.sin(angle/2)/n
    return (*v_mul(axis, s), math.cos(angle/2))


def q_angle(a, b=(0, 0, 0, 1)):
    """Shortest angle between rotations, in radians (q and -q equivalent)."""
    a, b = q_normalize(a), q_normalize(b)
    return 2*math.acos(min(1.0, abs(sum(x*y for x, y in zip(a, b)))))


def q_slerp(a, b, t):
    a, b = q_normalize(a), q_normalize(b)
    d = sum(x*y for x, y in zip(a, b))
    if d < 0:
        b, d = tuple(-x for x in b), -d
    d = min(1.0, d)
    if d > .9995:
        return q_normalize(tuple(x+(y-x)*t for x, y in zip(a, b)))
    theta = math.acos(d)
    s = math.sin(theta)
    return tuple((math.sin((1-t)*theta)*x+math.sin(t*theta)*y)/s
                 for x, y in zip(a, b))


def q_yaw(q):
    x, y, z, w = q_normalize(q)
    return q_axis_angle((0, 0, 1), math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))


def polyline_parameters(points):
    """Reference WORLD arc coordinates, anchored at the first/last listed joint.

    Zero edges (<= 1e-7 scene units) are rejected rather than silently merging
    joint identities. A parent outside this point list never contributes length.
    """
    points = [_vector(point, 3, "链参考位置") for point in points]
    if len(points) < 2:
        raise ValueError("语义重采样两侧都至少需要两个不同位置的节点")
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        length = v_length(v_sub(b, a))
        if length <= 1e-7:
            raise ValueError("语义重采样不能包含零长边或重合的相邻节点（长度须大于 1e-7 场景单位）")
        cumulative.append(cumulative[-1]+length)
    total = cumulative[-1]
    if not math.isfinite(total):
        raise ValueError("语义链弧长不是有限值")
    return tuple(distance/total for distance in cumulative[:-1])+(1.0,), total


def q_curve_sample(parameters, rotations, t):
    """Piecewise shortest-path slerp on strictly increasing arc coordinates.

    The endpoints return their exact stored rotations, with no extrapolation.
    Parameter validation belongs to the caller (polyline_parameters).
    """
    if t <= parameters[0]:
        return rotations[0]
    if t >= parameters[-1]:
        return rotations[-1]
    index = bisect_right(parameters, t)-1
    weight = (t-parameters[index])/(parameters[index+1]-parameters[index])
    return q_slerp(rotations[index], rotations[index+1], weight)


def _vector(value, length, name):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{name}必须包含 {length} 个数字")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError(f"{name}必须使用有限数字")
    return tuple(float(x) for x in value)


@dataclass(frozen=True)
class Transform:
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0, 1.0)
    scale: tuple = (1.0, 1.0, 1.0)

    def __post_init__(self):
        object.__setattr__(self, "position", _vector(self.position, 3, "位置"))
        object.__setattr__(self, "rotation", q_normalize(_vector(self.rotation, 4, "旋转")))
        object.__setattr__(self, "scale", _vector(self.scale, 3, "缩放"))


def compose(parent, local):
    p = tuple(x*y for x, y in zip(local.position, parent.scale))
    return Transform(v_add(parent.position, q_rotate(parent.rotation, p)),
                     q_mul(parent.rotation, local.rotation),
                     tuple(x*y for x, y in zip(parent.scale, local.scale)))


def relative(parent, world):
    if min(abs(x) for x in parent.scale) < EPS:
        raise ValueError("父节点缩放为零，无法转换局部姿态")
    p = q_rotate(q_inv(parent.rotation), v_sub(world.position, parent.position))
    return Transform(tuple(x/y for x, y in zip(p, parent.scale)),
                     q_mul(q_inv(parent.rotation), world.rotation),
                     tuple(x/y for x, y in zip(world.scale, parent.scale)))
