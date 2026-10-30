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
    dotNetControl lxHeader "System.Windows.Forms.Panel" width:392 height:84 align:#center

    dotNetControl lxSection1 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"01  公式设置"
        edittext edtFormula "" width:376 text:"v"
        dotNetControl lblVar "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"变量" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
        dotNetControl lblV "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  v = 当前帧值    t = 帧号    n = 物体名后缀数字" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblOp "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"运算符" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
        dotNetControl lblOp2 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  + - * /    ^幂    mod a b 取余" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblFunc0 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"函数 · 角度制" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
        dotNetControl lblFunc1 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  sin(x) cos(x) tan(x)  asin(x) acos(x) atan(x)" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblFunc2 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  sqrt abs pow log exp ceil floor round pi e" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblSep "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"常用示例" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleCenter)
        dotNetControl lblEx1 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  v * (1 + sin(t * 5))          振幅波动" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblEx2 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  v + n * 10                     按物体编号偏移" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
        dotNetControl lblEx3 "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"  mod (v + t * 3) 360            0~360 循环" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)

    dotNetControl btnApply "System.Windows.Forms.Button" width:376 height:42 align:#center


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

    fn convertDegToRad str = (
        local result = ""; local i = 1
        local d2r = "0.0174532925199433"; local r2d = "57.2957795130823"
        local fwd = #("sin","cos","tan"); local inv = #("asin","acos","atan")
        while i <= str.count do (
            local matched = false
            for func in fwd while not matched do (
                local tag = func + "("
                if i+tag.count-1<=str.count and subString str i tag.count == tag then (
                    if i==1 or not (isWordChar str[i-1]) then (
                        local depth=1; local j=i+tag.count
                        while j<=str.count and depth>0 do (
                            if str[j]=="(" then depth+=1 else if str[j]==")" then depth-=1
                            if depth>0 then j+=1
                        )
                        if j<=str.count then (
                            local inner = subString str (i+tag.count) (j-i-tag.count)
                            result += func + "((" + inner + ")*" + d2r + ")"
                            i=j+1; matched=true
                        )
                    )
                )
            )
            for func in inv while not matched do (
                local tag = func + "("
                if i+tag.count-1<=str.count and subString str i tag.count == tag then (
                    if i==1 or not (isWordChar str[i-1]) then (
                        local depth=1; local j=i+tag.count
                        while j<=str.count and depth>0 do (
                            if str[j]=="(" then depth+=1 else if str[j]==")" then depth-=1
                            if depth>0 then j+=1
                        )
                        if j<=str.count then (
                            local inner = subString str (i+tag.count) (j-i-tag.count)
                            result += "(" + func + "(" + inner + ")*" + r2d + ")"
                            i=j+1; matched=true
                        )
                    )
                )
            )
            if not matched then (result += str[i]; i+=1)
        )
        result
    )

    ------------------------------------------------------------------------
    --  事件
    ------------------------------------------------------------------------
    on CustomFormulaRollout open do
    (
        LXLegacySection lxSection1
        LXLegacyText lblVar
        LXLegacyText lblV
        LXLegacyText lblOp
        LXLegacyText lblOp2
        LXLegacyText lblFunc0
        LXLegacyText lblFunc1
        LXLegacyText lblFunc2
        LXLegacyText lblSep
        LXLegacyText lblEx1
        LXLegacyText lblEx2
        LXLegacyText lblEx3

        LXLegacyHeader lxHeader "公式关键帧" "用公式批量调整选中的动画关键帧" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnApply "应用到选中关键帧"

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

        with redraw off
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

createDialog CustomFormulaRollout width:420 bgcolor:(color 39 44 37) fgcolor:(color 229 235 222) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

format "自定义公式计算关键帧 已加载（角度制）。\n"

-- 纳西妲世界第一可爱
