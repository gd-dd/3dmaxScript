global LXWeightViewData = #(), LXWeightViewDraw
if LXWeightViewDraw != undefined do unregisterRedrawViewsCallback LXWeightViewDraw
fn LXWeightViewDraw =
(
    local limits = gw.getRndLimits()
    gw.setTransform (matrix3 1)
    gw.setRndLimits #(#colorVerts, #illum, #zBuffer)
    for model in LXWeightViewData do
    (
        for face in model[2] do
            gw.triangle #(model[1][face[1]],model[1][face[2]],model[1][face[3]]) #(model[3][face[1]],model[3][face[2]],model[3][face[3]])
    )
    gw.setRndLimits limits
    gw.enlargeUpdateRect #whole
)
registerRedrawViewsCallback LXWeightViewDraw
