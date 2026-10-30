"""Native Max painter session with one undo transaction per stroke."""
import math,time,json
from pathlib import Path
from . import max_host as H,weight_edit
rt=H.rt
_active=None

class Brush:
    def __init__(self,p):
        self.p=dict(p);self.scene=str(rt.LXRigSceneToken);self.obj=H.mesh(p);self.skin=H.skin(self.obj,p)
        self.data=H.skin_data(self.obj,self.skin);self.rows=self.data['weights'];self.locked=H.profile(self.obj,self.skin).get('locked',[])
        self.bones=list(map(str,p.get('bones',[])));self.mode=p.get('mode','add');self.radius=float(p.get('radius',5));self.strength=float(p.get('strength',.2));self.value=float(p.get('value',.5))
        if self.radius<=0 or not 0<self.strength<=1:raise ValueError('笔刷半径和强度无效')
        if self.mode!='smooth' and (not self.bones or set(self.bones)&set(self.locked)):raise ValueError('请选择未锁定的影响骨骼')
        if not set(self.bones)<={b['id'] for b in self.data['bones']}:raise ValueError('影响骨骼已经变化')
        self.positions=[H.vec(rt.Point3(*v)*self.obj.objectTransform) for v in self.data['positions']]
        self.graph=H.W.adjacency(len(self.rows),self.data['faces']);self.grid={}
        for i,pos in enumerate(self.positions):self.grid.setdefault(self.cell(pos),[]).append(i)
        self.allowed=set(H.selected_vertices(self.skin,p,len(self.rows))) if p.get('selectedOnly') else set(range(len(self.rows)))
        self.allowed-=set(int(i)-1 for i in json.loads(str(rt.getUserProp(self.obj,'LXHiddenVertices') or '[]')))
        self.before=None;self.changed=set();self.last=None;self.last_time=0;self.holding=False
        H.backup(self.data,'进入笔刷前')
    def cell(self,pos):return tuple(math.floor(v/self.radius) for v in pos)
    def valid(self):
        if self.scene!=str(rt.LXRigSceneToken) or not rt.isValidNode(self.obj):raise ValueError('场景已改变，笔刷已停止')
        if self.skin not in list(self.obj.modifiers):raise ValueError('Skin 已移除，笔刷已停止')
    def begin(self):
        self.valid()
        if self.holding:self.cancel()
        if rt.theHold.Holding():raise ValueError('另一个撤销事务正在运行')
        self.rows=H.read_rows(self.skin);self.before=[dict(r) for r in self.rows];self.changed=set();self.last=None
        from . import history
        history.prepare(self.skin,self.before)
        self.undo_context=H.pymxs.undo(True,'LX 权重笔刷');self.undo_context.__enter__();self.holding=True
    def dab(self,pos,radius=None,pressure=1,mode=None):
        self.valid()
        if not self.holding:self.begin()
        mode=mode or self.mode;radius=max(.0001,float(radius or self.radius));now=time.monotonic()
        if self.last is not None and H.W.finite(sum((x-y)**2 for x,y in zip(pos,self.last)))<(radius*.07)**2 and now-self.last_time<.04:return
        self.last=list(pos);self.last_time=now
        cells=self.cell(pos);extent=math.ceil(radius/self.radius);hits=[]
        for x in range(cells[0]-extent,cells[0]+extent+1):
            for y in range(cells[1]-extent,cells[1]+extent+1):
                for z in range(cells[2]-extent,cells[2]+extent+1):
                    for i in self.grid.get((x,y,z),[]):
                        if i not in self.allowed:continue
                        d=math.sqrt(sum((a-b)**2 for a,b in zip(pos,self.positions[i])))
                        if d<radius:hits.append((i,self.strength*max(0,min(1,pressure))*(1-(d/radius)**2)**2))
        if not hits:return
        before=[dict(r) for r in self.rows] if mode=='smooth' else self.rows
        for i,alpha in hits:
            if mode=='smooth':
                neighbors=self.graph[i]
                if not neighbors:continue
                average={}
                for j in neighbors:
                    for k,v in before[j].items():average[k]=average.get(k,0)+v/len(neighbors)
                row={k:before[i].get(k,0)*(1-alpha)+average.get(k,0)*alpha for k in set(before[i])|set(average)}
                for k in self.locked:row[k]=before[i].get(k,0)
                row=H.W.normalize(row,self.locked)
            else:
                current=sum(self.rows[i].get(k,0) for k in self.bones)
                value=current+(self.value-current)*alpha if mode=='set' else alpha
                row=weight_edit.edit_many(self.rows[i],self.bones,value,'set' if mode=='set' else mode,self.locked,[b['id'] for b in self.data['bones']])
            self.rows[i]=row;keys=sorted(row,key=int)
            rt.skinOps.ReplaceVertexWeights(self.skin,i+1,H.arr([int(k) for k in keys]),H.arr([row[k] for k in keys]));self.changed.add(i)
        rt.skinOps.Invalidate(self.skin,1);rt.redrawViews()
    def end(self):
        if not self.holding:return
        try:
            self.valid();H.write_rows(self.skin,self.rows,self.changed,record_history=False)
            from . import history
            history.commit(self.skin,self.rows)
            self.undo_context.__exit__(None,None,None);self.undo_context=None;self.holding=False
        except Exception:self.cancel();raise
    def cancel(self):
        if not self.holding:return
        if self.holding:
            error=RuntimeError('取消笔划');self.undo_context.__exit__(RuntimeError,error,None);self.undo_context=None;self.holding=False
        if self.before is not None:
            self.rows=self.before
            if self.scene==str(rt.LXRigSceneToken):
                with H.pymxs.undo(False):H.write_rows(self.skin,self.rows,record_history=False)

def message(text):
    from .workflow_host import notify
    notify(text)
def event(name):
    # MAXScript Painter callbacks must unwind before creating Python undo contexts.
    from PySide6.QtCore import QTimer
    identity=_active
    sample=None
    if name=='dab':sample=(bool(rt.LXPaintHit),H.vec(rt.LXPaintPoint),float(rt.LXPaintRadius),float(rt.LXPaintPressure),bool(rt.LXPaintShift),bool(rt.LXPaintCtrl))
    QTimer.singleShot(0,lambda:process_event(name,sample) if _active is identity else None)

def process_event(name,sample=None):
    global _active
    brush=_active
    if brush is None:return
    try:
        if name=='begin':brush.begin()
        elif name=='dab':
            if not sample or not sample[0]:return
            hit,position,radius,pressure,shift,ctrl=sample
            mode='smooth' if shift else 'subtract' if ctrl else brush.mode
            brush.dab(position,radius,pressure,mode)
        elif name=='end':brush.end();message('笔划已应用，可 Ctrl+Z 撤销；Shift 平滑，Ctrl 减值。')
        elif name=='cancel':brush.cancel()
        elif name=='stop':brush.cancel();_active=None
    except Exception as e:
        brush.cancel();message('笔刷停止：'+str(e));stop()

def stop():
    global _active
    brush=_active;_active=None
    if brush is not None:
        brush.cancel()
        if rt.thePainterInterface.inPaintMode():rt.thePainterInterface.endPaintSession()

@H.command('brush.start')
def start(p):
    global _active
    stop();brush=Brush(p)
    if rt.thePainterInterface.inPaintMode():raise ValueError('请先退出其他绘制工具')
    rt.fileIn(str(Path(__file__).parent/'painter.ms'))
    brush.skin.shadeweights=True;brush.skin.filter_vertices=True;rt.subObjectLevel=1
    if brush.bones:rt.skinOps.SelectBone(brush.skin,int(brush.bones[0]))
    painter=rt.thePainterInterface;painter.initializeNodes(0,H.arr([brush.obj]));painter.maxSize=brush.radius*2;painter.minSize=brush.radius*2
    painter.maxStr=1;painter.minStr=1;painter.updateOnMouseUp=False;painter.pointGatherEnable=False;painter.mirrorEnable=False
    _active=brush;painter.startPaintSession()
    return {'message':'笔刷已开启：Shift 平滑 / Ctrl 减值 / 右键退出；一次笔划对应一次撤销。'}
@H.command('brush.stop')
def stop_command(p):stop();return {'message':'笔刷已退出'}
