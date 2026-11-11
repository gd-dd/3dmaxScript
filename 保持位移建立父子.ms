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
    dotNetControl lxHeader "System.Windows.Forms.Panel" pos:[14,12] width:392 height:64

    dotNetControl lxSection1 "System.Windows.Forms.Label" Text:"01  子物体" pos:[14,88] width:392 height:26
        pickbutton btnPickChild "选择子物体" autoDisplay:true pos:[22,122] width:376 height:28
        dotNetControl lblChildInfo "System.Windows.Forms.Label" Text:"未选择" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter) pos:[22,156] width:376 height:34
    dotNetControl lxSection2 "System.Windows.Forms.Label" Text:"02  父物体" pos:[14,198] width:392 height:26
        pickbutton btnPickParent "选择父物体" autoDisplay:true pos:[22,232] width:376 height:28
        dotNetControl lblParentInfo "System.Windows.Forms.Label" Text:"未选择" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter) pos:[22,266] width:376 height:34
    dotNetControl lxSection3 "System.Windows.Forms.Label" Text:"03  帧范围" pos:[14,308] width:392 height:26
        dotNetControl spnStartLabel "System.Windows.Forms.Label" Text:"开始" pos:[22,346] width:36 height:20
        spinner spnStart "" range:[-9999,99999,0] type:#integer pos:[62,344] width:120 height:20
        dotNetControl spnEndLabel "System.Windows.Forms.Label" Text:"结束" pos:[220,346] width:36 height:20
        spinner spnEnd   "" range:[-9999,99999,100] type:#integer pos:[260,344] width:138 height:20
        dotNetControl btnGetRange "System.Windows.Forms.Button" pos:[22,376] width:160 height:30
    dotNetControl btnExecute "System.Windows.Forms.Button" pos:[198,374] width:200 height:36

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
        LXLegacyText spnStartLabel
        LXLegacyText spnEndLabel
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
        if not isValidNode childNode do
        (
            messageBox "请选择子物体！" title:"错误"
            return false
        )
        if not isValidNode parentNode do
        (
            messageBox "请选择父物体！" title:"错误"
            return false
        )
        if childNode == parentNode do
        (
            messageBox "子物体和父物体不能是同一个！" title:"错误"
            return false
        )

        local ancestor = parentNode
        while ancestor != undefined do (
            if ancestor == childNode do (messageBox "不能将对象连接到自己的子层级！" title:"错误"; return false)
            ancestor = ancestor.parent
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
        -- Parent assignment belongs to the same undo operation as the keys.

        -- 阶段3：逐帧用世界变换写回，并打关键帧
        with redraw off, undo "保持位移建立父子" on
        (
            childNode.parent = parentNode
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

createDialog ReparentBakeRollout width:420 height:424 bgcolor:(color 248 250 245) fgcolor:(color 48 61 42) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "保持位移建立父子关系工具已加载。\n"

-- 纳西妲世界第一可爱
