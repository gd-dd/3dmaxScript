/*
================================================================================
   PMX 导入插件 for 3ds Max
   支持 PMX 2.0 / 2.1 模型导入，包括网格、骨骼蒙皮、材质贴图、顶点变形
================================================================================
*/

-------------------------------------------------------------------------------
--  DotNet 编码器（UTF-8 / UTF-16LE 字符串解码用）
-------------------------------------------------------------------------------
global PMX_UTF8    = (dotNetClass "System.Text.Encoding").UTF8
global PMX_Unicode = (dotNetClass "System.Text.Encoding").Unicode

-------------------------------------------------------------------------------
--  工具函数
-------------------------------------------------------------------------------
fn pmxReadULong f = (
    local v = readLong f
    if v == undefined or v < 0 do throw "PMX 数据截断或计数无效"
    v
)

fn pmxReadIndex f size = (
    case size of (
        1: readByte f #signed
        2: (readShort f #signed)
        4: (readLong f #signed)
        default: 0
    )
)

fn pmxReadText f encoding = (
    local len = pmxReadULong f
    if len > 16777216 do throw "PMX 文本长度超过安全上限"
    if len == 0 then return ""
    local ba = dotNetObject "System.Byte[]" len
    local byteType = dotNetClass "System.Byte"
    for i = 0 to len-1 do
        ba.SetValue (dotNet.ValueToDotNetObject (readByte f #unsigned) byteType) i
    if encoding == 0 then PMX_Unicode.GetString ba else PMX_UTF8.GetString ba
)

fn pmxReadVertexIndex f size =
(
    case size of
    (
        1: (readByte f #unsigned)
        2: (readShort f #unsigned)
        4: (readLong f #unsigned)
        default: (throw "Invalid PMX vertex index size")
    )
)
fn pmxReadVec2 f = [readFloat f, readFloat f, 0]
fn pmxReadVec3 f = [readFloat f, readFloat f, readFloat f]
fn pmxReadVec4 f = [readFloat f, readFloat f, readFloat f, readFloat f]

-------------------------------------------------------------------------------
--  文件选择 & 路径工具
-------------------------------------------------------------------------------
fn pmxPickFile = (
    getOpenFileName caption:"选择 PMX 模型文件" \
        types:"PMX Model (*.pmx)|*.pmx|All Files (*.*)|*.*|"
)

fn pmxResolveTex baseDir texPath = (
    if texPath == "" or texPath == undefined then return undefined
    local r = texPath
    if (substring texPath 1 1) == "*" do r = baseDir + (substring texPath 2 -1)
    r = substituteString r "/" "\\"
    if doesFileExist r then r else undefined
)

-------------------------------------------------------------------------------
--  PMX 数据结构体
-------------------------------------------------------------------------------
struct PMXVertex (
    pos, normal, uv,
    weightType,      -- 0=BDEF1, 1=BDEF2, 2=BDEF4, 3=SDEF
    boneIndices = #(), boneWeights = #(),
    sdefC, sdefR0, sdefR1,
    edgeScale = 1.0
)
struct PMXMaterial (
    name, nameEng,
    diffuse, specular, specPower, ambient,
    drawFlags, edgeColor, edgeSize,
    texIdx, toonIdx, sphereIdx, sphereMode,
    toonShared, comment, faceVertCount
)
struct PMXBone (
    name, nameEng, pos,
    parentIdx, deformLayer,
    flags, tailType,
    tailPos, tailBoneIdx, tailWeight,
    inheritIdx, inheritWeight,
    fixedAxis, localAxisX, localAxisZ,
    extParentKey,
    ikTarget, ikIteration, ikLimit,
    ikLinks = #()
)
struct PMXMorph (
    name, nameEng, panel, morphType,
    offsets = #()
)

-------------------------------------------------------------------------------
--  PMX 主数据 & 解析器
-------------------------------------------------------------------------------
struct PMXData (
    version, encoding, additionalUV,
    idxV, idxT, idxM, idxB, idxMrph, idxR,
    modelName, modelNameEng, comment, commentEng,
    vertices=#(), faces=#(), textures=#(), materials=#(),
    bones=#(), morphs=#(), dispFrames=#(), rigidBodies=#(), joints=#(),

    fn parse path = (
        local f = fopen path "rb"
        if f == undefined then (messageBox "无法打开文件" title:"PMX导入"; return false)
        try (
        local sig = ""
        for i = 1 to 4 do sig += bit.intAsChar (readByte f)
        if sig != "PMX " then (fclose f; messageBox "不是有效的PMX文件" title:"PMX导入"; return false)
        version = readFloat f
        if version < 2.0 or version > 2.2 then (
            fclose f
            messageBox ("不支持的PMX版本: "+version as string) title:"PMX导入"
            return false
        )
        -- 全局标记
        local fc = readByte f
        if fc != 8 do throw "PMX 全局头长度无效"
        for i = 1 to fc do (
            case i of (
                1: encoding     = readByte f
                2: additionalUV = readByte f
                3: idxV = readByte f
                4: idxT = readByte f
                5: idxM = readByte f
                6: idxB = readByte f
                7: idxMrph = readByte f
                8: idxR = readByte f
                default: readByte f
            )
        )
        -- 模型信息
        modelName    = pmxReadText f encoding
        modelNameEng = pmxReadText f encoding
        comment      = pmxReadText f encoding
        commentEng   = pmxReadText f encoding
        ---------------------------------------------------------------
        --  顶点
        ---------------------------------------------------------------
        local vCnt = pmxReadULong f
        for vi = 1 to vCnt do (
            local v = PMXVertex()
            v.pos    = pmxReadVec3 f
            v.normal = pmxReadVec3 f
            v.uv     = pmxReadVec2 f
            -- 追加UVレイヤーをスキップ (additionalUV 個の vec4)
            for auv = 1 to additionalUV do (readFloat f; readFloat f; readFloat f; readFloat f)
            v.weightType = readByte f
            case v.weightType of (
                0: ( v.boneIndices=#(pmxReadIndex f idxB); v.boneWeights=#(1.0) )
                1: (
                    v.boneIndices=#(pmxReadIndex f idxB, pmxReadIndex f idxB)
                    local w=readFloat f; v.boneWeights=#(w,1.0-w)
                )
                2: (
                    v.boneIndices=#(pmxReadIndex f idxB,pmxReadIndex f idxB,pmxReadIndex f idxB,pmxReadIndex f idxB)
                    v.boneWeights=#(readFloat f,readFloat f,readFloat f,readFloat f)
                )
                3: (
                    v.boneIndices=#(pmxReadIndex f idxB, pmxReadIndex f idxB)
                    local w=readFloat f; v.boneWeights=#(w,1.0-w)
                    v.sdefC=pmxReadVec3 f; v.sdefR0=pmxReadVec3 f; v.sdefR1=pmxReadVec3 f
                )
            )
            v.edgeScale = readFloat f
            append vertices v
        )
        ---------------------------------------------------------------
        --  面索引
        ---------------------------------------------------------------
        local fiCnt = pmxReadULong f
        for i = 1 to fiCnt do append faces (pmxReadVertexIndex f idxV)
        ---------------------------------------------------------------
        --  纹理
        ---------------------------------------------------------------
        local tCnt = pmxReadULong f
        for i = 1 to tCnt do append textures (pmxReadText f encoding)
        ---------------------------------------------------------------
        --  材质
        ---------------------------------------------------------------
        local mCnt = pmxReadULong f
        for i = 1 to mCnt do (
            local m = PMXMaterial()
            m.name=pmxReadText f encoding; m.nameEng=pmxReadText f encoding
            m.diffuse=pmxReadVec4 f; m.specular=pmxReadVec3 f; m.specPower=readFloat f
            m.ambient=pmxReadVec3 f; m.drawFlags=readByte f
            m.edgeColor=pmxReadVec4 f; m.edgeSize=readFloat f
            m.texIdx=pmxReadIndex f idxT
            m.sphereIdx=pmxReadIndex f idxT; m.sphereMode=readByte f
            m.toonShared=readByte f
            m.toonIdx=if m.toonShared == 1 then readByte f #unsigned else pmxReadIndex f idxT
            m.comment=pmxReadText f encoding
            m.faceVertCount=pmxReadULong f
            append materials m
        )
        ---------------------------------------------------------------
        --  骨骼
        ---------------------------------------------------------------
        local bCnt = pmxReadULong f
        for i = 1 to bCnt do (
            local b = PMXBone()
            b.name=pmxReadText f encoding; b.nameEng=pmxReadText f encoding
            b.pos=pmxReadVec3 f; b.parentIdx=pmxReadIndex f idxB
            b.deformLayer=pmxReadULong f; b.flags=readShort f #unsigned
            if bit.and b.flags 0x0001 != 0 then (
                b.tailType=1; b.tailBoneIdx=pmxReadIndex f idxB
            ) else (b.tailType=0; b.tailPos=pmxReadVec3 f; b.tailBoneIdx = -1)
            if bit.and b.flags 0x0300 != 0 then (b.inheritIdx=pmxReadIndex f idxB; b.inheritWeight=readFloat f)
            if bit.and b.flags 0x0400 != 0 then b.fixedAxis=pmxReadVec3 f
            if bit.and b.flags 0x0800 != 0 then (b.localAxisX=pmxReadVec3 f; b.localAxisZ=pmxReadVec3 f)
            if bit.and b.flags 0x2000 != 0 then b.extParentKey=pmxReadULong f
            if bit.and b.flags 0x0020 != 0 then (
                b.ikTarget=pmxReadIndex f idxB; b.ikIteration=pmxReadULong f
                b.ikLimit=readFloat f
                local ikCnt=pmxReadULong f
                for k=1 to ikCnt do (
                    local lbi=pmxReadIndex f idxB; local hl=readByte f
                    local lmn=[0,0,0]; local lmx=[0,0,0]
                    if hl==1 then (lmn=pmxReadVec3 f; lmx=pmxReadVec3 f)
                    append b.ikLinks #(lbi,lmn,lmx)
                )
            )
            append bones b
        )
        ---------------------------------------------------------------
        --  变形
        ---------------------------------------------------------------
        local mrCnt = pmxReadULong f
        for i = 1 to mrCnt do (
            local mr = PMXMorph()
            mr.name=pmxReadText f encoding; mr.nameEng=pmxReadText f encoding
            mr.panel=readByte f; mr.morphType=readByte f
            local ofsCnt=pmxReadULong f
            for j=1 to ofsCnt do (
                case mr.morphType of (
                    0: (pmxReadIndex f idxMrph; readFloat f)
                    1: (local vi=pmxReadVertexIndex f idxV; local po=pmxReadVec3 f; append mr.offsets #(vi,po))
                    2: (pmxReadIndex f idxB; pmxReadVec3 f; pmxReadVec4 f)
                    3: (pmxReadVertexIndex f idxV; pmxReadVec4 f)
                    4: (pmxReadVertexIndex f idxV; pmxReadVec4 f)
                    5: (pmxReadVertexIndex f idxV; pmxReadVec4 f)
                    6: (pmxReadVertexIndex f idxV; pmxReadVec4 f)
                    7: (pmxReadVertexIndex f idxV; pmxReadVec4 f)
                    8: (pmxReadIndex f idxM; readByte f; for k=1 to 28 do readFloat f)
                    9: (pmxReadIndex f idxMrph; readFloat f)
                    10: (pmxReadIndex f idxR; readByte f; pmxReadVec3 f; pmxReadVec3 f)
                    default: (throw "不支持的 PMX 变形类型")
                )
            )
            append morphs mr
        )
        ---------------------------------------------------------------
        --  显示枠
        ---------------------------------------------------------------
        local dfCnt = pmxReadULong f
        for i=1 to dfCnt do (
            pmxReadText f encoding; pmxReadText f encoding; readByte f
            local entries=pmxReadULong f
            for j=1 to entries do (
                local dt=readByte f
                if dt==0 then append dispFrames #("bone",pmxReadIndex f idxB)
                else append dispFrames #("morph",pmxReadIndex f idxMrph)
            )
        )
        ---------------------------------------------------------------
        --  刚体（跳过）
        ---------------------------------------------------------------
        local rbCnt = pmxReadULong f
        for i=1 to rbCnt do (
            pmxReadText f encoding  -- name
            pmxReadText f encoding  -- nameEng
            pmxReadIndex f idxB     -- boneIndex
            readByte f; readShort f #unsigned; readByte f
            pmxReadVec3 f; pmxReadVec3 f; pmxReadVec3 f
            readFloat f; readFloat f; readFloat f; readFloat f; readFloat f
            readByte f
        )
        ---------------------------------------------------------------
        --  关节（跳过）
        ---------------------------------------------------------------
        local jCnt = pmxReadULong f
        for i=1 to jCnt do (
            pmxReadText f encoding; pmxReadText f encoding
            readByte f
            pmxReadIndex f idxR; pmxReadIndex f idxR
            pmxReadVec3 f; pmxReadVec3 f
            pmxReadVec3 f; pmxReadVec3 f
            pmxReadVec3 f; pmxReadVec3 f
            pmxReadVec3 f; pmxReadVec3 f
        )
        fclose f
        format "PMX解析: 顶点% 三角面% 材质% 骨骼%\n" vertices.count (faces.count/3) materials.count bones.count
        true
        ) catch (local reason=getCurrentException(); try(fclose f)catch(); throw())
    )  -- end fn parse
)  -- end struct PMXData

-------------------------------------------------------------------------------
--  场景构建
-------------------------------------------------------------------------------
fn pmxBuildBoneHierarchy pmxData = (
    local boneCount = pmxData.bones.count
    local allBones = #()
    -- 正确初始化数组：append undefined 填充
    for i = 1 to boneCount do append allBones undefined
    local rootNodes = #()

    for i = 1 to boneCount do (
        if allBones[i] == undefined then (
            -- 迭代栈：从当前骨骼向上追溯，建立父骨骼链
            local stack = #(i)
            local cur = i
            local b = pmxData.bones[cur]
            while b.parentIdx >= 0 and b.parentIdx < boneCount and (b.parentIdx + 1) != cur \
                and allBones[b.parentIdx + 1] == undefined do (
                if findItem stack (b.parentIdx+1) > 0 do throw "PMX 骨骼父子关系循环"
                cur = b.parentIdx + 1
                append stack cur
                b = pmxData.bones[cur]
            )
            -- 栈顶是已存在的骨骼或根骨骼，逐层弹出创建
            local parentForNext = undefined
            if b.parentIdx >= 0 and b.parentIdx < boneCount and (b.parentIdx + 1) != cur then
                parentForNext = allBones[b.parentIdx + 1]

            while stack.count > 0 do (
                cur = stack[stack.count]
                stack.count = stack.count - 1
                b = pmxData.bones[cur]

                local bn = BoneSys.createBone b.pos (b.pos+[5,0,0]) [0,0,1]
                bn.name = b.name
                bn.width = 0.5; bn.height = 0.5; bn.taper = 90

                local tail = b.pos + [0,0,5]
                if b.tailType == 0 then tail = b.pos+b.tailPos
                else if b.tailType == 1 and b.tailBoneIdx >= 0 and b.tailBoneIdx < boneCount then
                    tail = pmxData.bones[b.tailBoneIdx + 1].pos

                local dir = tail - b.pos
                bn.length = if (length dir) > 0.001 then (length dir) else 5.0
                if (length dir) > 0.001 then (
                    local xA = normalize dir
                    local up = [0,0,1]
                    if abs(dot xA up) > 0.999 then up = [0,1,0]
                    local yA = normalize (cross up xA)
                    local zA = normalize (cross xA yA)
                    bn.transform = matrix3 xA yA zA b.pos
                ) else bn.pos = b.pos

                if parentForNext != undefined then bn.parent = parentForNext
                allBones[cur] = bn
                parentForNext = bn
            )
            append rootNodes allBones[i]
        )
    )
    #(allBones, rootNodes)
)

fn pmxBuildScene pmxData baseDir = (
    ---------------------------------------------------------------
    --  材质
    ---------------------------------------------------------------
    local maxMats = #()
    for m in pmxData.materials do (
        local mat = standardMaterial()
        mat.name=m.name
        mat.diffuse=color (m.diffuse.x*255) (m.diffuse.y*255) (m.diffuse.z*255)
        mat.opacity=m.diffuse.w*100
        mat.specular=color (m.specular.x*255) (m.specular.y*255) (m.specular.z*255)
        mat.glossiness=amin 100 (m.specPower*100.0/256.0)
        mat.ambient=color (m.ambient.x*255) (m.ambient.y*255) (m.ambient.z*255)
        if bit.and m.drawFlags 0x01 != 0 then mat.twoSided=true
        if m.texIdx>=0 and m.texIdx<pmxData.textures.count then (
            local tp=pmxResolveTex baseDir pmxData.textures[m.texIdx+1]
            if tp!=undefined then (
                local bmp=bitmaptexture(); bmp.filename=tp
                mat.diffuseMap=bmp; mat.diffuseMapEnable=true
            )
        )
        append maxMats mat
    )
    ---------------------------------------------------------------
    --  骨骼
    ---------------------------------------------------------------
    local boneResult = pmxBuildBoneHierarchy pmxData
    local allBones=boneResult[1]
    ---------------------------------------------------------------
    --  网格
    ---------------------------------------------------------------
    local vCnt=pmxData.vertices.count
    local triCnt=pmxData.faces.count/3
    local verts=for v in pmxData.vertices collect v.pos
    local tris=for f=1 to triCnt collect [pmxData.faces[f*3-2]+1,pmxData.faces[f*3]+1,pmxData.faces[f*3-1]+1]
    local msh=mesh name:pmxData.modelName vertices:verts faces:tris
    msh.numTVerts=vCnt; buildTVFaces msh false
    for v=1 to vCnt do setTVert msh v pmxData.vertices[v].uv
    for f=1 to triCnt do setTVFace msh f tris[f]
    update msh
    ---------------------------------------------------------------
    --  材质 ID
    ---------------------------------------------------------------
    if maxMats.count>0 then (
        msh.material=multiMaterial numsubs:maxMats.count
        for i=1 to maxMats.count do msh.material[i]=maxMats[i]
        local fi=1
        for m=1 to pmxData.materials.count do (
            local mtc=pmxData.materials[m].faceVertCount/3
            for f=1 to mtc do (
                if fi<=msh.numfaces then (setFaceMatID msh fi m; fi+=1)
            )
        )
        for f=fi to msh.numfaces do setFaceMatID msh f maxMats.count
    )
    ---------------------------------------------------------------
    --  蒙皮
    ---------------------------------------------------------------
    if allBones.count>0 then (
        local hasW=false
        for v in pmxData.vertices do if v.boneIndices.count>0 then (hasW=true; exit)
        if hasW then (
            local sm=skin(); addModifier msh sm
            local bMap=#(); bMap.count=pmxData.bones.count
            for i=1 to pmxData.bones.count do (
                if allBones[i]!=undefined then (
                    skinOps.addBone sm allBones[i] 1
                    bMap[i]=skinOps.getNumberBones sm
                )
            )
            select msh; max modify mode; modPanel.setCurrentObject sm
            for v=1 to vCnt do (
                local vd=pmxData.vertices[v]; local ids=#(); local weights=#()
                for j=1 to vd.boneIndices.count do (
                    local idx=vd.boneIndices[j]+1
                    if idx>=1 and idx<=bMap.count and bMap[idx]!=undefined and vd.boneWeights[j]>0 do (
                        append ids bMap[idx]; append weights vd.boneWeights[j]
                    )
                )
                if ids.count>0 do skinOps.ReplaceVertexWeights sm v ids weights
            )
            skinOps.Invalidate sm 1
        )
    )
    ---------------------------------------------------------------
    --  变形
    ---------------------------------------------------------------
    local hasMrph=false
    for mr in pmxData.morphs do if mr.morphType==1 and mr.offsets.count>0 then (hasMrph=true; exit)
    if hasMrph then (
        local mm=morpher(); addModifier msh mm before:msh.modifiers.count
        local ch=1
        for mi=1 to pmxData.morphs.count do (
            local mr=pmxData.morphs[mi]
            if mr.morphType==1 and mr.offsets.count>0 and ch<=100 then (
                local tm=copy msh; tm.name=mr.name; hide tm
                for ofs in mr.offsets do (
                    local vi=ofs[1]+1
                    if vi<=tm.numverts then setVert tm vi (tm.verts[vi].pos+ofs[2])
                )
                update tm
                WM3_MC_BuildFromNode mm ch tm
                WM3_MC_SetName mm ch mr.name
                ch+=1
            )
        )
    )
    select msh; redrawViews()
    msh
)

-------------------------------------------------------------------------------
--  主导入函数
-------------------------------------------------------------------------------
fn importPMXFile filePath showUI:false = (
    if not doesFileExist filePath then (
        messageBox ("文件不存在:\n"+filePath) title:"PMX导入"; return undefined
    )
    local pd=PMXData()
    if not pd.parse filePath then return undefined
    if mod pd.faces.count 3 != 0 do throw "PMX 面索引数量无效"
    for vi in pd.faces do if vi<0 or vi>=pd.vertices.count do throw "PMX 顶点索引越界"
    local baseDir=getFilenamePath filePath
    local result=undefined
    local previousNodes=objects as array
    try (
        with redraw off, undo "PMX导入" on (result=pmxBuildScene pd baseDir)
    ) catch (
        local reason=getCurrentException()
        local partial=for n in objects where findItem previousNodes n == 0 collect n
        with undo off (delete partial)
        throw()
    )
    if result!=undefined and showUI then (
        local msg="导入完成!\n\n"
        msg+="模型: "+pd.modelName+"\n"
        msg+="顶点: "+(pd.vertices.count as string)+"\n"
        msg+="三角面: "+((pd.faces.count/3) as string)+"\n"
        msg+="材质: "+(pd.materials.count as string)+"\n"
        msg+="骨骼: "+(pd.bones.count as string)+"\n"
        msg+="变形: "+(pd.morphs.count as string)
        messageBox msg title:"PMX导入-完成"
    )
    format "PMX导入完成: %\n" pd.modelName
    result
)

-------------------------------------------------------------------------------
--  UI Rollout
-------------------------------------------------------------------------------
global LXLegacyRoot = getFilenamePath (getSourceFileName())
fileIn (LXLegacyRoot + "ui\\legacy_theme.ms") quiet:true
try(destroyDialog PMXImportRollout)catch()

rollout PMXImportRollout "PMX 导入" width:420
(
    dotNetControl lxHeader "System.Windows.Forms.Panel" width:392 height:84 align:#center

    dotNetControl lxSection1 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"01  PMX 文件"
        editText edtPath "" width:300 height:22 readonly:true
        dotNetControl btnBrowse "System.Windows.Forms.Button" width:376 height:30 align:#center
    dotNetControl lxSection2 "System.Windows.Forms.Label" width:392 height:28 align:#center Text:"02  模型信息"
        dotNetControl lblInfo "System.Windows.Forms.Label" width:376 height:22 align:#center Text:"尚未选择文件" TextAlign:((dotNetClass "System.Drawing.ContentAlignment").MiddleLeft)
    dotNetControl btnImport "System.Windows.Forms.Button" width:376 height:42 align:#center enabled:false

    local selectedFilePath=""


    on PMXImportRollout open do (
        LXLegacySection lxSection1
        LXLegacySection lxSection2
        LXLegacyText lblInfo
        LXLegacySecondary btnBrowse "选择 PMX 文件..."

        LXLegacyHeader lxHeader "PMX 模型导入" "选择文件，检查信息，再导入当前场景" (LXLegacyRoot + ".lxtool\\icon.png")
        LXLegacyPrimary btnImport "导入到当前场景"

    )
    on btnBrowse Click args do (
        local fname=pmxPickFile()
        if fname!=undefined then (
            selectedFilePath=fname; edtPath.text=fname; btnImport.enabled=true
            local f=fopen fname "rb"
            if f!=undefined then (
                local sig=""
                for i=1 to 4 do sig+=bit.intAsChar(readByte f)
                if sig=="PMX " then (
                    local ver=readFloat f; fclose f
                    lblInfo.text="版本: "+(ver as string)+" | "+filenameFromPath fname
                ) else (fclose f; lblInfo.text="无效的PMX文件"; btnImport.enabled=false)
            )
        )
    )
    on btnImport Click args do (
        if selectedFilePath=="" then (messageBox "请先选择PMX文件" title:"PMX导入"; return false)
        btnBrowse.enabled=false; btnImport.enabled=false
        local st=timestamp()
        local result=undefined
        try (result=importPMXFile selectedFilePath showUI:true) catch (
            lblInfo.text="导入失败，可重新选择文件"
            messageBox (getCurrentException() as string) title:"PMX 导入失败"
        )
        local el=(timestamp()-st)/1000.0
        if result!=undefined then (
            edtPath.text=""; selectedFilePath=""; btnImport.enabled=false
            lblInfo.text="导入完成! (用时 "+(el as string)+" 秒)"
        )
        btnBrowse.enabled=true; btnImport.enabled=(selectedFilePath!="")
    )
    on PMXImportRollout close do LXLegacyDisposeHeader lxHeader

)

createDialog PMXImportRollout width:420 bgcolor:(color 39 44 37) fgcolor:(color 229 235 222) style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)
format "PMX导入插件已加载。\n"
-- 纳西妲世界第一可爱
