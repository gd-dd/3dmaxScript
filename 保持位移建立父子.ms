/*
================================================================================
  保持相对位移建立父子关系
  选择子物体和父物体，在位移不变的情况下建立父子关系，逐帧打关键帧
================================================================================
*/
global LXLegacyRoot = getFilenamePath (getSourceFileName())
fileIn (LXLegacyRoot + "ui\\legacy_theme.ms") quiet:true
try(destroyDialog ReparentBakeRollout)catch()

rollout ReparentBakeRollout "保持位移建立父子" width:420
(
    dotNetControl lxHeader "System.Windows.Forms.Panel" width:392 height:84 align:#center

    dotNetControl lxSection1 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"01  子物体"
        pickbutton btnPickChild "选择子物体" width:376 height:28 autoDisplay:true
        dotNetControl lblChildInfo "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"未选择" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
    dotNetControl lxSection2 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"02  父物体"
        pickbutton btnPickParent "选择父物体" width:376 height:28 autoDisplay:true
        dotNetControl lblParentInfo "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"未选择" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
    dotNetControl lxSection3 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"03  帧范围"
        spinner spnStart "起始帧:" range:[-9999,99999,0] type:#integer width:120
        spinner spnEnd   "结束帧:" range:[-9999,99999,100] type:#integer width:120
        dotNetControl btnGetRange "System.Windows.Forms.Button" width:376 height:30 align:#center
    dotNetControl btnExecute "System.Windows.Forms.Button" width:376 height:42 align:#center

    local childNode  = undefined
    local parentNode = undefined


    on btnPickChild picked obj do
    (
        childNode = obj
        lblChildInfo.text = "子物体: " + obj.name
    )
    on btnPickParent picked obj do
    (
        parentNode = obj
        lblParentInfo.text = "父物体: " + obj.name
    )
    on ReparentBakeRollout open do
    (
        LXLegacySection lxSection1
        LXLegacySection lxSection2
        LXLegacySection lxSection3
        LXLegacyText lblChildInfo
        LXLegacyText lblParentInfo
        LXLegacySecondary btnGetRange "获取场景时间范围"

        LXLegacyHeader lxHeader "保持位移建立父子" "建立新层级，逐帧保留世界变换" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnExecute "建立父子并烘焙"

        if selection.count >= 2 do
        (
            childNode = selection[1]
            parentNode = selection[2]
            lblChildInfo.text = "子物体: " + childNode.name
            lblParentInfo.text = "父物体: " + parentNode.name
        )
    )
    on btnGetRange Click args do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
    )

    on btnExecute Click args do
    (
        if childNode == undefined do
        (
            messageBox "请选择子物体！" title:"错误"
            return false
        )
        if parentNode == undefined do
        (
            messageBox "请选择父物体！" title:"错误"
            return false
        )
        if childNode == parentNode do
        (
            messageBox "子物体和父物体不能是同一个！" title:"错误"
            return false
        )

        local startF = spnStart.value
        local endF   = spnEnd.value
        if startF > endF do
        (
            messageBox "起始帧不能大于结束帧！" title:"错误"
            return false
        )

        local curTime = sliderTime

        -- 阶段1：记录子物体每帧的世界变换
        local worldTM = #()
        for t = startF to endF do
        (
            sliderTime = t
            append worldTM childNode.transform
        )

        -- 阶段2：建立父子关系
        childNode.parent = parentNode

        -- 阶段3：逐帧用世界变换写回，并打关键帧
        with redraw off, undo "保持位移建立父子" on
        (
            with animate on
            (
                for i = 1 to worldTM.count do
                (
                    sliderTime = startF + i - 1
                    childNode.transform = worldTM[i]
                )
            )
        )

        sliderTime = curTime
        redrawViews()
        select childNode

        local msg = "完成！\n\n"
        msg += "子: " + childNode.name + "\n"
        msg += "父: " + parentNode.name + "\n"
        msg += "帧: " + startF as string + " ~ " + endF as string
        msg += "  共 " + (endF - startF + 1) as string + " 帧"
        messageBox msg title:"保持位移建立父子 - 完成"
    )


    on ReparentBakeRollout close do LXLegacyDisposeHeader lxHeader

)

createDialog ReparentBakeRollout width:420 bgcolor:(color 39 44 37) fgcolor:(color 229 235 222) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "保持位移建立父子关系工具已加载。\n"

-- 纳西妲世界第一可爱
