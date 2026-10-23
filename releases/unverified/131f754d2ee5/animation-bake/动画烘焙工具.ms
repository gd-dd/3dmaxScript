/*
================================================================================
   动画烘焙工具 for 3ds Max
   将选中对象的动画通道逐帧烘焙为关键帧，支持自动对齐场景时间范围
================================================================================
*/
try(destroyDialog AnimBakeRollout)catch()

rollout AnimBakeRollout "动画烘焙工具" width:360 height:560
(
    ----------------------------------------------------------------------------
    --  UI
    ----------------------------------------------------------------------------
    group "目标对象"
    (
        button btnGetObjs "从场景选择中获取对象" width:320 height:28
        label lblObjInfo "未获取对象" align:#center
    )
    group "烘焙通道"
    (
        checkbox chkPos "位移 (Position)" checked:true
        checkbox chkRot "旋转 (Rotation)" checked:true
        checkbox chkScale "缩放 (Scale)" checked:true
    )
    group "帧范围"
    (
        spinner spnStart "起始帧:" range:[-9999,99999,0] type:#integer width:120
        spinner spnEnd   "结束帧:" range:[-9999,99999,100] type:#integer width:120
        spinner spnStep  "采样间隔:" range:[1,100,1] type:#integer width:120
        button btnGetRange "获取场景时间范围" width:150 height:22
    )
    button btnExecute "执行烘焙" width:320 height:44

    local bakeObjs = #()

    dotNetControl nahidaImg "System.Windows.Forms.PictureBox" pos:[80,330] width:200 height:200

    ----------------------------------------------------------------------------
    --  事件
    ----------------------------------------------------------------------------
    on AnimBakeRollout open do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
        if selection.count > 0 do
        (
            bakeObjs = selection as array
            if bakeObjs.count == 1 then
                lblObjInfo.text = "已获取: " + bakeObjs[1].name
            else if bakeObjs.count > 1 then
                lblObjInfo.text = "已获取 " + bakeObjs.count as string + " 个对象"
        )
        local imgPath = (getFilenamePath (getSourceFileName())) + "Nahida.jpg"
        if nahidaImg != undefined and doesFileExist imgPath do
        (
            nahidaImg.image = (dotNetClass "System.Drawing.Image").FromFile imgPath
            nahidaImg.SizeMode = nahidaImg.SizeMode.Zoom
        )
    )

    on btnGetObjs pressed do
    (
        bakeObjs = selection as array
        if bakeObjs.count == 0 then
        (messageBox "请先在场景中选择对象！" title:"动画烘焙"; return false)
        if bakeObjs.count == 1 then
            lblObjInfo.text = "已获取: " + bakeObjs[1].name
        else
            lblObjInfo.text = "已获取 " + bakeObjs.count as string + " 个对象"
    )

    on btnGetRange pressed do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
    )

    on btnExecute pressed do
    (
        if bakeObjs.count == 0 do
        (
            messageBox "请先获取目标对象！" title:"动画烘焙"
            return false
        )
        if not chkPos.checked and not chkRot.checked and not chkScale.checked do
        (
            messageBox "请至少选择一个烘焙通道！" title:"动画烘焙"
            return false
        )
        local startF = spnStart.value
        local endF   = spnEnd.value
        local stepF  = spnStep.value
        if startF > endF do
        (
            messageBox "起始帧不能大于结束帧！" title:"动画烘焙"
            return false
        )

        local curTime = sliderTime

        with redraw off, undo "动画烘焙" on
        (
            for obj in bakeObjs do
            (
                -- 阶段1：逐帧采样记录
                local posSamples = #()
                local rotSamples = #()
                local sclSamples = #()
                for t = startF to endF by stepF do
                (
                    sliderTime = t
                    append posSamples obj.position
                    append rotSamples obj.rotation
                    append sclSamples obj.scale
                )
                -- 阶段2：写回 + 打关键帧
                with animate on
                (
                    local idx = 1
                    for t = startF to endF by stepF do
                    (
                        sliderTime = t
                        if chkPos.checked   then obj.position = posSamples[idx]
                        if chkRot.checked   then obj.rotation = rotSamples[idx]
                        if chkScale.checked then obj.scale   = sclSamples[idx]
                        idx += 1
                    )
                )
            )
        )

        sliderTime = curTime
        redrawViews()

        local frameCount = ((endF - startF) / stepF + 1) as integer
        local msg = "烘焙完成！\n\n"
        msg += "对象: " + bakeObjs.count as string + " 个\n"
        local chs = ""
        if chkPos.checked   then chs += "位移 "
        if chkRot.checked   then chs += "旋转 "
        if chkScale.checked then chs += "缩放 "
        msg += "通道: " + chs + "\n"
        msg += "帧范围: " + startF as string + " ~ " + endF as string
        msg += " (间隔 " + stepF as string + ")"
        msg += "\n共 " + frameCount as string + " 帧"
        messageBox msg title:"动画烘焙 - 完成"
    )
)

createDialog AnimBakeRollout

format "动画烘焙工具已加载。\n"

-- 纳西妲世界第一可爱