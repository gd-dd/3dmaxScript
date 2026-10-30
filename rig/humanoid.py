"""Parametric humanoid plan: plain data, no Max dependency. Z up, front -Y."""
import math

def plan(options):
    height=float(options.get('height',170));origin=options.get('origin',[0,0,0]);prefix=str(options.get('prefix','LX'))
    if not math.isfinite(height) or height<=0:raise ValueError('人体高度必须大于零')
    def count(key,default,low=1,high=12):
        n=int(options.get(key,default))
        if not low<=n<=high:raise ValueError(key+' 数量超出范围')
        return n
    specs=[]
    def world(v):return [origin[i]+v[i]*height for i in range(3)]
    def bone(role,a,b,parent=None,chain=None):
        specs.append(dict(role=role,name=prefix+'_'+role,start=world(a),end=world(b),parent=parent,chain=chain));return role
    def chain(role,a,b,n,parent,group=None):
        for i in range(n):
            p=[a[j]+(b[j]-a[j])*i/n for j in range(3)];q=[a[j]+(b[j]-a[j])*(i+1)/n for j in range(3)]
            parent=bone(role+'_%02d'%(i+1),p,q,parent,group)
        return parent
    hip=bone('Pelvis',[0,0,.51],[0,0,.56])
    chest=chain('Spine',[0,0,.56],[0,0,.8],count('spine',3),hip)
    neck=chain('Neck',[0,0,.8],[0,0,.89],count('neck',1),chest)
    bone('Head',[0,0,.89],[0,0,1],neck)
    for side,sign in [('L',1),('R',-1)]:
        clav=bone(side+'_Clavicle',[0,0,.79],[sign*.12,0,.79],chest)
        upper=chain(side+'_UpperArm',[sign*.12,0,.79],[sign*.3,-.025,.77],count('upperArm',1),clav,side+'_Arm')
        lower=chain(side+'_Forearm',[sign*.3,-.025,.77],[sign*.46,0,.75],count('forearm',1),upper,side+'_Arm')
        hand=bone(side+'_Hand',[sign*.46,0,.75],[sign*.51,0,.75],lower)
        for digit in range(count('fingers',5,0,5)):
            y=(digit-2)*.018
            tip=chain(side+'_Finger%d'%digit,[sign*.51,y,.75],[sign*(.57-abs(digit-2)*.012),y,.75],count('fingerLinks',3),hand)
            bone(side+'_Finger%d_End'%digit,[sign*(.57-abs(digit-2)*.012),y,.75],[sign*(.575-abs(digit-2)*.012),y,.75],tip)
        thigh=chain(side+'_Thigh',[sign*.075,0,.51],[sign*.075,-.025,.285],count('thigh',1),hip,side+'_Leg')
        calf=chain(side+'_Calf',[sign*.075,-.025,.285],[sign*.075,0,.06],count('calf',1),thigh,side+'_Leg')
        foot=bone(side+'_Foot',[sign*.075,0,.06],[sign*.075,-.09,.025],calf)
        for digit in range(count('toes',1,0,5)):
            x=sign*.075+(digit-(count('toes',1,0,5)-1)/2)*.012
            tip=chain(side+'_Toe%d'%digit,[x,-.09,.025],[x,-.145,.025],count('toeLinks',2),foot)
            bone(side+'_Toe%d_End'%digit,[x,-.145,.025],[x,-.15,.025],tip)
    return specs
