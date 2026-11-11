/*
================================================================================
  根骨骼约束烘焙工具 for 3ds Max
  将 Bip001 位移逐帧烘焙到已有虚拟体，勾选 = 传递该轴
================================================================================
*/
global LXLegacyRoot = getFilenamePath (getSourceFileName())
fileIn (LXLegacyRoot + "ui\\legacy_theme.ms") quiet:true
try(destroyDialog RootBoneBakeRollout)catch()

rollout RootBoneBakeRollout "根骨骼约束烘焙" width:420
(
    dotNetControl lxHeader "System.Windows.Forms.Panel" pos:[14,8] width:392 height:64

    dotNetControl lxSection1 "System.Windows.Forms.Label" Text:"01  源 - 根骨骼" pos:[14,78] width:392 height:24
        pickbutton btnPickBone "选择 Bip001" autoDisplay:true pos:[22,106] width:376 height:26
        dotNetControl lblBoneInfo "System.Windows.Forms.Label" Text:"执行时自动查找 Bip001" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter) pos:[22,136] width:376 height:30
    dotNetControl lxSection2 "System.Windows.Forms.Label" Text:"02  目标 - 虚拟体" pos:[14,170] width:392 height:24
        pickbutton btnPickDummy "选择虚拟体" autoDisplay:true pos:[22,198] width:376 height:26
        dotNetControl lblDummyInfo "System.Windows.Forms.Label" Text:"也可先选中虚拟体再打开工具" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter) pos:[22,228] width:376 height:30
    dotNetControl lxSection3 "System.Windows.Forms.Label" Text:"03  传递位移轴（勾选的轴传给虚拟体）" pos:[14,262] width:392 height:24
        dotNetControl chkAxisX "System.Windows.Forms.CheckBox" Text:"X 轴" Checked:false pos:[22,290] width:120 height:24
        dotNetControl chkAxisY "System.Windows.Forms.CheckBox" Text:"Y 轴" Checked:true pos:[150,290] width:120 height:24
        dotNetControl chkAxisZ "System.Windows.Forms.CheckBox" Text:"Z 轴" Checked:false pos:[278,290] width:120 height:24
    dotNetControl lxSection4 "System.Windows.Forms.Label" Text:"04  帧范围" pos:[14,318] width:392 height:24
        dotNetControl spnStartLabel "System.Windows.Forms.Label" Text:"开始" pos:[22,350] width:36 height:20
        spinner spnStart "" range:[-9999,99999,0] type:#integer pos:[62,348] width:120 height:20
        dotNetControl spnEndLabel "System.Windows.Forms.Label" Text:"结束" pos:[220,350] width:36 height:20
        spinner spnEnd   "" range:[-9999,99999,100] type:#integer pos:[260,348] width:138 height:20
        dotNetControl btnGetRange "System.Windows.Forms.Button" pos:[22,382] width:160 height:30
    dotNetControl btnExecute "System.Windows.Forms.Button" pos:[198,380] width:200 height:36

    local boneNode  = undefined
    local dummyNode = undefined


    on btnPickBone picked obj do
    (
        boneNode = obj
        lblBoneInfo.text = "根骨骼: " + obj.name
    )
    on btnPickDummy picked obj do
    (
        dummyNode = obj
        lblDummyInfo.text = "虚拟体: " + obj.name
    )
    on RootBoneBakeRollout open do
    (
        LXLegacyText spnStartLabel
        LXLegacyText spnEndLabel
        LXLegacySection lxSection1
        LXLegacySection lxSection2
        LXLegacySection lxSection3
        LXLegacySection lxSection4
        LXLegacyText lblBoneInfo
        LXLegacyText lblDummyInfo
        LXLegacyText chkAxisX
        LXLegacyText chkAxisY
        LXLegacyText chkAxisZ
        LXLegacySecondary btnGetRange "获取场景时间范围"

        LXLegacyHeader lxHeader "根骨骼约束烘焙" "把根骨骼运动传递给目标虚拟体" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnExecute "烘焙根骨骼运动"

        if selection.count == 1 do
        (
            dummyNode = selection[1]
            lblDummyInfo.text = "虚拟体: " + dummyNode.name
        )
    )
    on btnGetRange Click args do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
    )

    on btnExecute Click args do
    (
        if boneNode == undefined do
        (
            boneNode = getNodeByName "Bip001"
            if boneNode != undefined do lblBoneInfo.text = "根骨骼: Bip001（自动）"
        )
        if boneNode == undefined do
        (
            messageBox "未找到根骨骼！请选择 Bip001。" title:"错误"
            return false
        )
        if dummyNode == undefined and selection.count == 1 do
        (
            dummyNode = selection[1]
            lblDummyInfo.text = "虚拟体: " + dummyNode.name
        )
        if dummyNode == undefined do
        (
            messageBox "未选择虚拟体！请先选中虚拟物体。" title:"错误"
            return false
        )

        local startF = spnStart.value
        local endF   = spnEnd.value
        if startF > endF do
        (
            messageBox "起始帧不能大于结束帧！" title:"错误"
            return false
        )
        if not chkAxisX.checked and not chkAxisY.checked and not chkAxisZ.checked do
        (
            messageBox "至少需要勾选一个轴！" title:"错误"
            return false
        )


        local curTime = sliderTime

        with redraw off, undo "根骨骼烘焙" on
        (
            with animate on
            (
                for t = startF to endF do
                (
                    sliderTime = t
                    local bp = biped.getTransform boneNode #pos
                    local dp = dummyNode.position
                    if chkAxisX.checked do dp.x = bp.x
                    if chkAxisY.checked do dp.y = bp.y
                    if chkAxisZ.checked do dp.z = bp.z
                    dummyNode.position = dp
                )
            )
        )

        sliderTime = curTime
        redrawViews()
        select dummyNode

        local ax = ""
        if chkAxisX.checked do ax += "X "
        if chkAxisY.checked do ax += "Y "
        if chkAxisZ.checked do ax += "Z "

        local msg = "烘焙完成！\n\n"
        msg += "源: " + boneNode.name + "\n"
        msg += "目标: " + dummyNode.name + "\n"
        msg += "传递轴: " + ax + "\n"
        msg += "帧范围: " + startF as string + " ~ " + endF as string
        msg += "  共 " + (endF - startF + 1) as string + " 帧"
        messageBox msg title:"根骨骼烘焙 - 完成"
    )


    on RootBoneBakeRollout close do LXLegacyDisposeHeader lxHeader

)

createDialog RootBoneBakeRollout width:420 height:430 bgcolor:(color 248 250 245) fgcolor:(color 48 61 42) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "根骨骼约束烘焙工具已加载。\n"

-- 纳西妲世界第一可爱
