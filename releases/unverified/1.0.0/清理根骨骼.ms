/*
================================================================================
  根骨骼约束烘焙工具 for 3ds Max
  将 Bip001 位移逐帧烘焙到已有虚拟体，勾选 = 传递该轴
================================================================================
*/
try(destroyDialog RootBoneBakeRollout)catch()

rollout RootBoneBakeRollout "根骨骼约束烘焙" width:360 height:600
(
    group "源 - 根骨骼"
    (
        pickbutton btnPickBone "选择 Bip001" width:320 height:28 autoDisplay:true
        label lblBoneInfo "执行时自动查找 Bip001" align:#center
    )
    group "目标 - 虚拟体"
    (
        pickbutton btnPickDummy "选择虚拟体" width:320 height:28 autoDisplay:true
        label lblDummyInfo "也可先选中虚拟体再打开工具" align:#center
    )
    group "对齐 —— 勾选 = 将该轴位移传给虚拟体"
    (
        checkbox chkAxisX "X 轴" checked:false
        checkbox chkAxisY "Y 轴" checked:true
        checkbox chkAxisZ "Z 轴" checked:false
    )
    group "帧范围"
    (
        spinner spnStart "起始帧:" range:[-9999,99999,0] type:#integer width:120
        spinner spnEnd   "结束帧:" range:[-9999,99999,100] type:#integer width:120
        button btnGetRange "获取场景时间范围" width:140 height:22
    )
    button btnExecute "执行烘焙" width:320 height:40

    local boneNode  = undefined
    local dummyNode = undefined

    dotNetControl nahidaImg "System.Windows.Forms.PictureBox" pos:[80,380] width:200 height:200

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
        if selection.count == 1 do
        (
            dummyNode = selection[1]
            lblDummyInfo.text = "虚拟体: " + dummyNode.name
        )
        local imgPath = (getFilenamePath (getSourceFileName())) + "Nahida.jpg"
        if nahidaImg != undefined and doesFileExist imgPath do
        (
            nahidaImg.image = (dotNetClass "System.Drawing.Image").FromFile imgPath
            nahidaImg.SizeMode = nahidaImg.SizeMode.Zoom
        )
    )
    on btnGetRange pressed do
    (
        spnStart.value = animationRange.start.frame as integer
        spnEnd.value   = animationRange.end.frame as integer
    )

    on btnExecute pressed do
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


)

createDialog RootBoneBakeRollout

format "根骨骼约束烘焙工具已加载。\n"

-- 纳西妲世界第一可爱
