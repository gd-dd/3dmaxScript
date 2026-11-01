global LXPlacementStart, LXPlacementEnd, LXPlacementPlan, LXPlacementHeight = 0
global LXPlacementDraw
if LXPlacementDraw != undefined do unregisterRedrawViewsCallback LXPlacementDraw
fn LXPlacementDraw =
(
    if LXPlacementStart != undefined and LXPlacementHeight > 0 and LXPlacementPlan != undefined do
    (
        gw.setTransform (matrix3 1)
        gw.setColor #line (color 134 184 61)
        for segment in LXPlacementPlan do
        (
            local a=LXPlacementStart + segment[1]*LXPlacementHeight
            local b=LXPlacementStart + segment[2]*LXPlacementHeight
            gw.polyline #(a,b) false
            if segment.count > 2 do
            (
                local x=normalize (b-a)
                local up=if abs x.z < 0.95 then [0,0,1] else [0,1,0]
                local y=normalize (cross up x)
                local z=normalize (cross x y)
                y *= segment[3].y*LXPlacementHeight*0.5
                z *= segment[3].x*LXPlacementHeight*0.5
                local offsets=#(-y-z,y-z,y+z,-y+z)
                local corners=for v in offsets collect (a+v)
                gw.polyline corners true
                for i=1 to 4 do gw.polyline #(corners[i],if segment[3].z > 0 then b+offsets[i] else b) false
                if segment[3].z > 0 do gw.polyline (for v in offsets collect (b+v)) true
            )
        )
        gw.text (LXPlacementStart + [0,0,LXPlacementHeight]) ("Height: " + formattedPrint (LXPlacementHeight as float) format:".2f") color:(color 134 184 61)
        gw.enlargeUpdateRect #whole
    )
)
tool LXHumanoidPlacement numPoints:2
(
    on start do (LXPlacementHeight=0; registerRedrawViewsCallback LXPlacementDraw)
    on stop do (LXPlacementHeight=0; unregisterRedrawViewsCallback LXPlacementDraw; redrawViews())
    on mouseAbort click do (#stop)
    on mousePoint click do
    (
        if click == 1 then LXPlacementStart = worldPoint
        else
        (
            LXPlacementEnd = worldPoint
            python.Execute "from rig.workflow_host import complete_drag; complete_drag()"
            #stop
        )
    )
    on mouseMove click do
    (
        if click == 2 do
        (
            LXPlacementHeight = distance LXPlacementStart worldPoint
            redrawViews()
        )
    )
)
