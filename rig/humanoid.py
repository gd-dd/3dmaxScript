"""Parametric humanoid plan: plain data, no Max dependency. Z up, front -Y."""
import math

def plan(options):
    height=float(options.get('height',170));origin=options.get('origin',[0,0,0]);prefix=str(options.get('prefix','LX')).strip().rstrip('_')
    if not math.isfinite(height) or height<=0:raise ValueError('人体高度必须大于零')
    def count(key,default,low=1,high=12):
        n=int(options.get(key,default))
        if not low<=n<=high:raise ValueError(key+' 数量超出范围')
        return n
    specs=[]
    def world(v):return [origin[i]+v[i]*height for i in range(3)]
    def bone(role,a,b,parent=None,chain=None):
        specs.append(dict(role=role,name=(prefix+'_' if prefix else '')+role,start=world(a),end=world(b),parent=parent,chain=chain));return role
    def chain(role,a,b,n,parent,group=None):
        for i in range(n):
            p=[a[j]+(b[j]-a[j])*i/n for j in range(3)];q=[a[j]+(b[j]-a[j])*(i+1)/n for j in range(3)]
            parent=bone(role+'_%02d'%(i+1),p,q,parent,group)
        return parent
    # Proportions sampled from a standard Max Biped facing -Y, grounded at Z=0.
    # Keep ordinary Bone nodes: no Biped controllers, IK, or fixed lengths.
    hip=bone('Pelvis',[0,0,.535],[0,0,.59])
    chest=chain('Spine',[0,0,.59],[0,0,.841],count('spine',3),hip)
    neck=chain('Neck',[0,0,.841],[0,0,.877],count('neck',1),chest)
    bone('Head',[0,0,.877],[0,0,1],neck)
    for side,sign in [('L',1),('R',-1)]:
        clav=bone(side+'_Clavicle',[sign*.017,0,.841],[sign*.0783,0,.8285],'Neck_01')
        upper=chain(side+'_UpperArm',[sign*.0783,0,.8285],[sign*.0927,.0144,.6854],count('upperArm',1),clav,side+'_Arm')
        lower=chain(side+'_Forearm',[sign*.0927,.0144,.6854],[sign*.1068,0,.5422],count('forearm',1),upper,side+'_Arm')
        hand=bone(side+'_Hand',[sign*.1068,0,.5422],[sign*.112,0,.484],lower)
        for digit in range(count('fingers',5,0,5)):
            # Thumb sits in front of the palm; remaining fingers fan across it.
            y=-.034 if digit==0 else (digit-3)*.012
            a=[sign*(.11 if digit==0 else .112),y,.504 if digit==0 else .484]
            z=.459 if digit==0 else .484-(.062 if digit==2 else .053 if digit in (1,3) else .044)
            b=[sign*.113,y,z]
            tip=chain(side+'_Finger%d'%digit,a,b,count('fingerLinks',3),hand)
            bone(side+'_Finger%d_End'%digit,b,[b[0],b[1],b[2]-.005],tip)
        thigh=chain(side+'_Thigh',[sign*.0482,0,.535],[sign*.0482,-.0241,.2952],count('thigh',1),hip,side+'_Leg')
        calf=chain(side+'_Calf',[sign*.0482,-.0241,.2952],[sign*.0482,0,.0554],count('calf',1),thigh,side+'_Leg')
        foot=bone(side+'_Foot',[sign*.0482,0,.0554],[sign*.0482,-.0713,.008],calf)
        for digit in range(count('toes',1,0,5)):
            x=sign*.0482+(digit-(count('toes',1,0,5)-1)/2)*.009
            tip=chain(side+'_Toe%d'%digit,[x,-.0713,.008],[x,-.09,.008],count('toeLinks',2),foot)
            bone(side+'_Toe%d_End'%digit,[x,-.09,.008],[x,-.095,.008],tip)
    return specs


def dimensions(role,height):
    """Readable body volumes, including the separate shoulder/clavicle pair."""
    sizes={'Pelvis':(.10,.06),'Spine':(.08,.055),'Neck':(.025,.025),'Head':(.075,.07),
           'Clavicle':(.027,.025),'UpperArm':(.033,.033),'Forearm':(.027,.027),
           'Hand':(.045,.022),'Thigh':(.045,.045),'Calf':(.035,.035),'Foot':(.04,.025)}
    part=role.split('_')[1] if role.startswith(('L_','R_')) else role.split('_')[0]
    w,h=sizes.get(part,(.007,.007))
    return w*height,h*height
