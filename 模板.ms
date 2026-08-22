/*
================================================================================
  插件名称 for 3ds Max
  功能描述
================================================================================
*/
try(destroyDialog MyToolRollout)catch()

rollout MyToolRollout "插件名称" width:360 height:500
(
    ----------------------------------------------------------------------------
    --  UI
    ----------------------------------------------------------------------------
    group "源对象"
    (
        pickbutton btnPickSrc "选择对象" width:320 height:28 autoDisplay:true
        label lblSrcInfo "未选择" align:#center
    )
    group "选项"
    (
        checkbox chkOption "选项开关" checked:true
    )
    group "帧范围"
    (
        spinner spnStart "起始帧:" range:[-9999,99999,0] type:#integer width:120
        spinner spnEnd   "结束帧:" range:[-9999,99999,100] type:#integer width:120
        button btnGetRange "获取场景时间范围" width:140 height:22
    )
    button btnExecute "执行" width:320 height:40

    ----------------------------------------------------------------------------
    --  变量
    ----------------------------------------------------------------------------
    local srcNode = undefined

    ----------------------------------------------------------------------------
    --  Nahida
    ----------------------------------------------------------------------------
    dotNetControl nahidaImg "System.Windows.Forms.PictureBox" pos:[80,280] width:200 height:200

    ----------------------------------------------------------------------------
    --  事件
    ----------------------------------------------------------------------------
    on btnPickSrc picked obj do
    (
        srcNode = obj
        lblSrcInfo.text = "已选择: " + obj.name
    )

    on MyToolRollout open do
    (
        if selection.count == 1 do
        (
            srcNode = selection[1]
            lblSrcInfo.text = "已选择: " + srcNode.name
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
        ------------------------------------------------------------------------
        --  验证
        ------------------------------------------------------------------------
        if srcNode == undefined do
        (
            messageBox "请选择对象！" title:"错误"
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

        ------------------------------------------------------------------------
        --  核心逻辑
        ------------------------------------------------------------------------
        with redraw off, undo "插件名称" on
        (
            with animate on
            (
                for t = startF to endF do
                (
                    sliderTime = t
                    -- 在此编写逐帧处理逻辑
                    -- srcNode.position / srcNode.rotation / ...
                )
            )
        )

        ------------------------------------------------------------------------
        --  收尾
        ------------------------------------------------------------------------
        sliderTime = curTime
        redrawViews()
        select srcNode

        local msg = "完成！\n\n"
        msg += "对象: " + srcNode.name + "\n"
        msg += "帧范围: " + startF as string + " ~ " + endF as string
        msg += "  共 " + (endF - startF + 1) as string + " 帧"
        messageBox msg title:"插件名称 - 完成"
    )
)

createDialog MyToolRollout

format "插件名称已加载。\n"

-- 纳西妲世界第一可爱
