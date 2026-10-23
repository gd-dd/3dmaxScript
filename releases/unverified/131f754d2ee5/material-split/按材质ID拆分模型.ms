/*
================================================================================
   按材质ID拆分模型 for 3ds Max
   将选中模型的三角面按材质ID分离为独立元素，元素名使用对应材质名称
================================================================================
*/
try(destroyDialog MatIDSplitRollout)catch()

rollout MatIDSplitRollout "按材质ID拆分模型" width:360 height:480
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
        checkbox chkDeleteSrc "拆分后删除原对象" checked:false
        checkbox chkCopyMat   "新元素保留材质"   checked:true
    )
    button btnExecute "执行拆分" width:320 height:40

    ----------------------------------------------------------------------------
    --  变量
    ----------------------------------------------------------------------------
    local srcNode = undefined

    ----------------------------------------------------------------------------
    --  Nahida
    ----------------------------------------------------------------------------
    dotNetControl nahidaImg "System.Windows.Forms.PictureBox" pos:[80,260] width:200 height:200

    ----------------------------------------------------------------------------
    --  事件
    ----------------------------------------------------------------------------
    on btnPickSrc picked obj do
    (
        if superClassOf obj != GeometryClass then
        (
            messageBox "请选择几何体对象！" title:"错误"
            return false
        )
        srcNode = obj
        lblSrcInfo.text = "已选择: " + obj.name
    )

    on MatIDSplitRollout open do
    (
        if selection.count == 1 and superClassOf selection[1] == GeometryClass do
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

    on btnExecute pressed do
    (
        if srcNode == undefined do
        (
            messageBox "请先选择对象！" title:"错误"
            return false
        )
        if not (isKindOf srcNode Editable_Mesh or isKindOf srcNode Editable_Poly) do
        (
            messageBox "对象必须是可编辑网格或可编辑多边形！\n请先转换为可编辑网格/多边形。" title:"错误"
            return false
        )

        with redraw off, undo "按材质ID拆分" on
        (
            local isPoly = isKindOf srcNode Editable_Poly
            if isPoly do convertToMesh srcNode
            local msh = srcNode

            -- 收集材质ID→名称映射
            local matToName = #()
            local matObj = msh.material
            if matObj != undefined then
            (
                if classOf matObj == MultiMaterial then
                (
                    for mid = 1 to matObj.numsubs do
                    (
                        local subName = ""
                        if matObj[mid] != undefined do subName = matObj[mid].name
                        if subName == "" do subName = "材质ID_" + mid as string
                        append matToName subName
                    )
                )
                else
                (
                    local subName = matObj.name
                    if subName == "" do subName = "默认材质"
                    append matToName subName
                )
            )

            -- 按材质ID分组面
            local faceGroups = #()
            for f = 1 to msh.numfaces do
            (
                local mid = getFaceMatID msh f
                if mid < 1 do mid = 1
                while faceGroups.count < mid do append faceGroups #()
                append faceGroups[mid] f
            )

            local validIDs = #()
            for mid = 1 to faceGroups.count do
                if faceGroups[mid] != undefined and faceGroups[mid].count > 0 do
                    append validIDs mid

            if validIDs.count <= 1 then
            (
                if isPoly do convertToPoly msh
                messageBox "该对象只有一种材质ID，无需拆分。" title:"提示"
                return false
            )

            local parentNode = msh.parent

            -- 为每个材质ID克隆一份，删除非匹配面
            local newNodes = #()
            for mid in validIDs do
            (
                local newObj = copy msh
                if isPoly do convertToMesh newObj

                -- 收集要删除的面（不属于当前材质ID的）
                local toDel = #()
                for f = 1 to newObj.numfaces do
                    if getFaceMatID newObj f != mid do append toDel f

                if toDel.count > 0 then
                    meshop.deleteFaces newObj toDel delIsoVerts:true

                -- 命名
                local newName = "未知材质"
                if mid <= matToName.count then
                    newName = matToName[mid]
                else
                    newName = "材质ID_" + mid as string
                newObj.name = uniqueName newName

                if parentNode != undefined do newObj.parent = parentNode

                -- 赋予材质
                if chkCopyMat.checked and matObj != undefined then
                (
                    if classOf matObj == MultiMaterial \
                        and mid <= matObj.numsubs then
                        newObj.material = copy matObj[mid]
                    else
                        newObj.material = copy matObj
                )

                append newNodes newObj
            )

            -- 处理原对象
            if chkDeleteSrc.checked then
                delete msh
            else if isPoly do
                convertToPoly msh

            -- 选中新元素
            if newNodes.count > 0 do
            (
                select newNodes[1]
                for i = 2 to newNodes.count do selectMore newNodes[i]
            )
        )

        redrawViews()

        local msg = "拆分完成！\n\n"
        msg += "源对象: " + (if chkDeleteSrc.checked then "已删除" else "已保留") + "\n"
        msg += "生成元素: " + validIDs.count as string + " 个"
        messageBox msg title:"按材质ID拆分 - 完成"
    )
)

createDialog MatIDSplitRollout

format "按材质ID拆分模型工具已加载。\n"

-- 纳西妲世界第一可爱

