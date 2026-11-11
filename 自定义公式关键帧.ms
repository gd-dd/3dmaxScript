/*
================================================================================
   自定义公式计算关键帧 for 3ds Max
   对曲线编辑器中选中的关键帧应用公式
   变量：v=当前关键帧值, t=关键帧时间(帧号), n=物体名称后缀数字
   三角函数使用角度制 (sin(90)=1)
================================================================================
*/
global LXLegacyRoot = getFilenamePath (getSourceFileName())
fileIn (LXLegacyRoot + "ui\\legacy_theme.ms") quiet:true
try(destroyDialog CustomFormulaRollout)catch()

rollout CustomFormulaRollout "自定义公式计算关键帧" width:420
(
    dotNetControl lxHeader "System.Windows.Forms.Panel" pos:[14,12] width:392 height:64

    dotNetControl lxSection1 "System.Windows.Forms.Label" Text:"01  公式设置" pos:[14,88] width:392 height:26
        edittext edtFormula "" text:"v" pos:[22,124] width:376 height:24
        dotNetControl lblV "System.Windows.Forms.Label" Text:"先在曲线编辑器选关键帧。v = 当前值，t = 帧号；\nn = 物体名称末尾数字，三角函数使用角度。" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,156] width:376 height:40
        dotNetControl lblOp2 "System.Windows.Forms.Label" Text:"运算：+ - * /    ^幂    mod a b 取余" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,286] width:376 height:22
        dotNetControl lblFunc1 "System.Windows.Forms.Label" Text:"  sin(x) cos(x) tan(x)  asin(x) acos(x) atan(x)" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,308] width:376 height:22
        dotNetControl lblFunc2 "System.Windows.Forms.Label" Text:"  sqrt abs pow log exp ceil floor round pi e" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,330] width:376 height:22
        dotNetControl lblEx1 "System.Windows.Forms.Label" Text:"示例：v * (1 + sin(t * 5))    振幅波动" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,356] width:376 height:22
        dotNetControl lblEx2 "System.Windows.Forms.Label" Text:"  v + n * 10                     按物体编号偏移" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,378] width:376 height:22
        dotNetControl lblEx3 "System.Windows.Forms.Label" Text:"  mod (v + t * 3) 360            0~360 循环" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft) pos:[22,400] width:376 height:22

    dotNetControl btnApply "System.Windows.Forms.Button" pos:[22,204] width:376 height:38


    dotNetControl btnHelp "System.Windows.Forms.Button" pos:[22,250] width:376 height:26
    local helpExpanded = false
    fn showReference expanded =
    (
        helpExpanded = expanded
        for item in #(lblOp2,lblFunc1,lblFunc2,lblEx1,lblEx2,lblEx3) do item.visible = expanded
        btnHelp.Text = if expanded then "收起公式参考" else "公式参考与示例 ▾"
        setDialogSize CustomFormulaRollout [420, (if expanded then 434 else 290)]
    )
    on btnHelp Click args do showReference (not helpExpanded)

    ------------------------------------------------------------------------
    --  辅助函数
    ------------------------------------------------------------------------
    fn isWordChar ch = (
        local code = bit.charAsInt ch
        (code>=65 and code<=90) or (code>=97 and code<=122) or (code>=48 and code<=57) or code==95
    )

    fn replaceVariable str varName valStr = (
        local result = ""
        for i = 1 to str.count do (
            local ch = str[i]
            if ch == varName then (
                local leftOK  = (i==1 or not (isWordChar str[i-1]))
                local rightOK = (i>=str.count or not (isWordChar str[i+1]))
                if leftOK and rightOK then result += "(" + valStr + ")" else result += ch
            ) else result += ch
        )
        result
    )

    fn extractSuffixNum nodeName = (
        local digitsStr = ""
        for i = nodeName.count to 1 by -1 while (
            local code = bit.charAsInt nodeName[i]; code>=48 and code<=57
        ) do digitsStr = nodeName[i] + digitsStr
        if digitsStr.count>0 then digitsStr as integer else 0
    )

    -- MAXScript trigonometric functions already use degrees.
    fn convertDegToRad str = str

    ------------------------------------------------------------------------
    --  事件
    ------------------------------------------------------------------------
    on CustomFormulaRollout open do
    (
        LXLegacySection lxSection1
        LXLegacyText lblV
        LXLegacyText lblOp2
        LXLegacyText lblFunc1
        LXLegacyText lblFunc2
        LXLegacyText lblEx1
        LXLegacyText lblEx2
        LXLegacyText lblEx3

        LXLegacyHeader lxHeader "公式关键帧" "用公式批量调整选中的动画关键帧" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnApply "应用到选中关键帧"
        LXLegacySecondary btnHelp "公式参考与示例 ▾"
        showReference false

    )

    on btnApply Click args do
    (
        local formula = edtFormula.text
        if formula == "" do
        (messageBox "请输入公式！" title:"自定义公式"; return false)

        local tv = trackviews.current
        if tv == undefined do
        (messageBox "请先打开曲线编辑器！" title:"自定义公式"; return false)

        local selTrackNum = tv.numSelTracks()
        if selTrackNum == 0 do
        (messageBox "请在曲线编辑器中选中轨道或关键帧！" title:"自定义公式"; return false)

        local rad2deg = 57.2957795130823
        local deg2rad = 0.0174532925199433
        local changeCount = 0; local errorCount = 0
        local curTime = sliderTime

        with redraw off, undo "公式关键帧" on
        (
            for tIdx = 1 to selTrackNum do
            (
                local ctrl = tv.getSelected tIdx
                if ctrl == undefined do continue

                -- 检测是否为旋转轨道
                local isRot = false
                try (
                    local cName = (ctrl.name) as string
                    if matchPattern cName pattern:"*Rotation*" or matchPattern cName pattern:"*旋转*" then
                        isRot = true
                ) catch()

                local ownerNode = undefined
                local depNodes = refs.dependentNodes ctrl
                if depNodes.count > 0 do ownerNode = depNodes[1]

                local suffixNum = 0
                if ownerNode != undefined do
                    suffixNum = extractSuffixNum ownerNode.name

                local keyList = undefined
                try (keyList = ctrl.keys) catch()
                if keyList == undefined or keyList.count == 0 do continue

                for kIdx = 1 to keyList.count do
                (
                    if isKeySelected ctrl kIdx do
                    (
                        local keyItem = keyList[kIdx]
                        local v = keyItem.value
                        local t = keyItem.time.frame as float

                        -- 旋转轨道：弧度→角度，让公式中 v 以「度」呈现
                        if isRot then v = v * rad2deg

                        local expr = replaceVariable formula "v" (v as string)
                        expr = replaceVariable expr "t" (t as string)
                        expr = replaceVariable expr "n" (suffixNum as string)
                        expr = convertDegToRad expr

                        local result = undefined
                        try (result = execute expr) catch (errorCount += 1)

                        -- 旋转轨道：角度→弧度，写回 Max 内部弧度值
                        if result != undefined and isRot then
                            result = result * deg2rad

                        if result != undefined then
                        (
                            keyItem.value = result
                            changeCount += 1
                        )
                    )
                )
            )
        )

        sliderTime = curTime; redrawViews()

        local msg = "完成！修改了 " + changeCount as string + " 个关键帧"
        if errorCount > 0 then msg += "\n" + errorCount as string + " 个出错"
        messageBox msg title:"自定义公式"
    )
    on CustomFormulaRollout close do LXLegacyDisposeHeader lxHeader

)

createDialog CustomFormulaRollout width:420 height:290 bgcolor:(color 248 250 245) fgcolor:(color 48 61 42) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "自定义公式计算关键帧 已加载（角度制）。\n"

-- 纳西妲世界第一可爱
