import math

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def length(a): return math.sqrt(sum(x*x for x in a))
def unit(a):
    n=length(a)
    return mul(a,1/n) if n>1e-10 else (1,0,0)

class Solver:
    """Fixed-length sequential pendulums; all positions in scene units."""
    def __init__(self, points, gravity=980.0, inertia=0.95, mass=1.0, influence=1.0, damping=3.0):
        self.p=list(points); self.v=[(0,0,0)]*len(points)
        self.lengths=[length(sub(b,a)) for a,b in zip(points,points[1:])]
        if not self.lengths or min(self.lengths)<1e-5: raise ValueError('骨段长度必须大于零')
        if mass<=0 or not 0<=inertia<=1: raise ValueError('质量必须为正，惯性必须在零到一之间')
        self.g=gravity; self.inertia=inertia; self.mass=mass; self.influence=influence; self.damping=damping
    def step(self, root, dt):
        old=list(self.p); shift=sub(root,old[0]); self.p[0]=root
        mean=sum(self.lengths)/len(self.lengths)
        for i,L in enumerate(self.lengths,1):
            response=(L/mean)**self.influence
            drag=math.exp(-self.damping*dt/(self.mass*response))
            velocity=add(mul(self.v[i],drag),(0,0,-self.g*dt))
            candidate=add(add(old[i],mul(shift,1-self.inertia)),mul(velocity,dt))
            self.p[i]=add(self.p[i-1],mul(unit(sub(candidate,self.p[i-1])),L))
            self.v[i]=mul(sub(self.p[i],add(old[i],mul(shift,1-self.inertia))),1/dt)
        return list(self.p)
