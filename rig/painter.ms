global LXPaintPoint=[0,0,0], LXPaintRadius=1.0, LXPaintPressure=1.0, LXPaintHit=false, LXPaintShift=false, LXPaintCtrl=false
fn LXPaintBegin = (python.Execute "from rig.brush import event; event('begin')")
fn LXPaintDab =
(
    LXPaintHit=thePainterInterface.getIsHit 0
    if LXPaintHit do
    (
        local lp=[0,0,0],ln=[0,0,1],wn=[0,0,1],strength=1.0,alt=false
        thePainterInterface.getHitPointData &lp &ln &LXPaintPoint &wn &LXPaintRadius &strength 0
        thePainterInterface.getHitPressureData &LXPaintShift &LXPaintCtrl &alt &LXPaintPressure 0
        python.Execute "from rig.brush import event; event('dab')"
    )
)
fn LXPaintEnd = (python.Execute "from rig.brush import event; event('end')")
fn LXPaintCancel = (python.Execute "from rig.brush import event; event('cancel')")
fn LXPaintStop = (python.Execute "from rig.brush import event; event('stop')")
thePainterInterface.ScriptFunctions LXPaintBegin LXPaintDab LXPaintEnd LXPaintCancel LXPaintStop
