/*
================================================================================
   自定义公式计算关键帧 for 3ds Max
   对曲线编辑器中选中的关键帧应用公式
   变量：v=当前关键帧值, t=关键帧时间(帧号), n=物体名称后缀数字
   三角函数使用角度制 (sin(90)=1)
================================================================================
*/
try(destroyDialog CustomFormulaRollout)catch()

rollout CustomFormulaRollout "自定义公式计算关键帧" width:400 height:560
(
    group "公式设置"
    (
        edittext edtFormula "" width:360 text:"v"
        label lblVar "━━━━ 变量 ━━━━" align:#center
        label lblV "  v = 当前帧值    t = 帧号    n = 物体名后缀数字" align:#left
        label lblOp "━━━━ 运算符 ━━━━" align:#center
        label lblOp2 "  + - * /    ^幂    mod a b 取余" align:#left
        label lblFunc0 "━━━━ 函数（角度制）━━━━" align:#center
        label lblFunc1 "  sin(x) cos(x) tan(x)  asin(x) acos(x) atan(x)" align:#left
        label lblFunc2 "  sqrt abs pow log exp ceil floor round pi e" align:#left
        label lblSep "━━━━ 示例 ━━━━" align:#center
        label lblEx1 "  v * (1 + sin(t * 5))          振幅波动" align:#left
        label lblEx2 "  v + n * 10                     按物体编号偏移" align:#left
        label lblEx3 "  mod (v + t * 3) 360            0~360 循环" align:#left
    )

    button btnApply "应用公式到选中关键帧" width:360 height:44

    dotNetControl nahidaImg "System.Windows.Forms.PictureBox" pos:[100,320] width:200 height:200

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
        local imgPath = (getFilenamePath (getSourceFileName())) + "Nahida.jpg"
        if nahidaImg != undefined and doesFileExist imgPath do
        (
            nahidaImg.image = (dotNetClass "System.Drawing.Image").FromFile imgPath
            nahidaImg.SizeMode = nahidaImg.SizeMode.Zoom
        )
    )

    on btnApply pressed do
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
)

createDialog CustomFormulaRollout

format "自定义公式计算关键帧 已加载（角度制）。\n"

-- 纳西妲世界第一可爱
