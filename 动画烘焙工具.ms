/*
================================================================================
   动画烘焙工具 for 3ds Max
   将选中对象的动画通道逐帧烘焙为关键帧，支持自动对齐场景时间范围
================================================================================
*/
global LXLegacyRoot = getFilenamePath (getSourceFileName())
fileIn (LXLegacyRoot + "ui\\legacy_theme.ms") quiet:true
try(destroyDialog AnimBakeRollout)catch()

rollout AnimBakeRollout "动画烘焙工具" width:420
(
    dotNetControl lxHeader "System.Windows.Forms.Panel" width:392 height:84 align:#center

    ----------------------------------------------------------------------------
    --  UI
    ----------------------------------------------------------------------------
    dotNetControl lxSection1 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"01  目标对象"
        dotNetControl btnGetObjs "System.Windows.Forms.Button" width:376 height:30 align:#center
        dotNetControl lblObjInfo "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"未获取对象" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
    dotNetControl lxSection2 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"02  烘焙通道"
        dotNetControl chkPos "System.Windows.Forms.CheckBox" width:376 height:24 align:#center Text:"位移 (Position)" Checked:true
        dotNetControl chkRot "System.Windows.Forms.CheckBox" width:376 height:24 align:#center Text:"旋转 (Rotation)" Checked:true
        dotNetControl chkScale "System.Windows.Forms.CheckBox" width:376 height:24 align:#center Text:"缩放 (Scale)" Checked:true
    dotNetControl lxSection3 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"03  帧范围"
        spinner spnStart "起始帧:" range:[-9999,99999,0] type:#integer width:120
        spinner spnEnd   "结束帧:" range:[-9999,99999,100] type:#integer width:120
        spinner spnStep  "采样间隔:" range:[1,100,1] type:#integer width:120
        dotNetControl btnGetRange "System.Windows.Forms.Button" width:376 height:30 align:#center
    dotNetControl btnExecute "System.Windows.Forms.Button" width:376 height:42 align:#center

    local bakeObjs = #()


    ----------------------------------------------------------------------------
    --  事件
    ----------------------------------------------------------------------------
    on AnimBakeRollout open do
    (
        LXLegacySection lxSection1
        LXLegacySection lxSection2
        LXLegacySection lxSection3
        LXLegacyText lblObjInfo
        LXLegacyText chkPos
        LXLegacyText chkRot
        LXLegacyText chkScale
        LXLegacySecondary btnGetObjs "从场景选择中获取对象"
        LXLegacySecondary btnGetRange "获取场景时间范围"

        LXLegacyHeader lxHeader "动画烘焙" "选择对象，设置通道与采样范围" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnExecute "执行烘焙"

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
    )

    on btnGetObjs Click args do
    (
        bakeObjs = selection as array
        if bakeObjs.count == 0 then
        (messageBox "请先在场景中选择对象！" title:"动画烘焙"; return false)
        if bakeObjs.count == 1 then
            lblObjInfo.text = "已获取: " + bakeObjs[1].name
        else
            lblObjInfo.text = "已获取 " + bakeObjs.count as string + " 个对象"
    )

    on btnGetRange Click args do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
    )

    on btnExecute Click args do
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
    on AnimBakeRollout close do LXLegacyDisposeHeader lxHeader

)

createDialog AnimBakeRollout width:420 bgcolor:(color 39 44 37) fgcolor:(color 229 235 222) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "动画烘焙工具已加载。\n"

-- 纳西妲世界第一可爱