global LXPlacementStart, LXPlacementEnd
tool LXHumanoidPlacement numPoints:2
(
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
            gw.setTransform (matrix3 1)
            gw.setColor #line (color 134 184 61)
            gw.polyline #(LXPlacementStart,worldPoint) false
            gw.enlargeUpdateRect #whole
            gw.updateScreen()
        )
    )
)
