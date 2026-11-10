"""World-space child Bone endpoints; direction and length are independent."""
import math


def point(value):
    result=tuple(float(v) for v in value)
    if len(result)!=3 or not all(math.isfinite(v) for v in result):
        raise ValueError('坐标必须是三个有限数值 X, Y, Z')
    return result


def segment(start,direction_point,length):
    start=point(start);target=point(direction_point);length=float(length)
    if not math.isfinite(length) or length<.001:
        raise ValueError('骨骼长度必须是大于等于 0.001 的有限数值')
    delta=tuple(b-a for a,b in zip(start,target));distance=math.hypot(*delta)
    if not math.isfinite(distance):raise ValueError('坐标跨度超出可计算范围')
    if distance<1e-9:
        raise ValueError('起点与方向点不能重合，请重新取方向点')
    return start,point(a+d/distance*length for a,d in zip(start,delta))
