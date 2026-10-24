-- LX Max Tools: per-process bridge. Only known plugin IDs are accepted.
global LXMaxBridgeTimer
global LXMaxBridgeRoot
global LXMaxBridgeSession
global LXMaxBridgeBusy = false
global LXMaxBridgeSource
try (if LXMaxBridgeTimer != undefined do LXMaxBridgeTimer.Stop()) catch()
LXMaxBridgeSource = getSourceFileName()
LXMaxBridgeRoot = (dotNetClass "System.IO.Path").GetFullPath ((getFilenamePath LXMaxBridgeSource) + "..")
(
    local proc = (dotNetClass "System.Diagnostics.Process").GetCurrentProcess()
    local started = proc.StartTime
    local utc = started.ToUniversalTime()
    local ticks = utc.Ticks
    local birth = (dotNetClass "System.Convert").ToString ticks
    local userRoot = (dotNetClass "System.Environment").GetEnvironmentVariable "LOCALAPPDATA"
    LXMaxBridgeSession = userRoot + "\\LXMaxTools\\sessions\\" + (proc.Id as string) + "-" + birth
)
(dotNetClass "System.IO.Directory").CreateDirectory LXMaxBridgeSession

fn LXMaxBridgeEncode s = ((dotNetClass "System.Convert").ToBase64String ((dotNetClass "System.Text.Encoding").UTF8.GetBytes s))
fn LXMaxBridgeWrite path value =
(
    local io = dotNetClass "System.IO.File"
    local token = (dotNetClass "System.Guid").NewGuid()
    local tmp = path + "." + token.ToString() + ".tmp"
    io.WriteAllText tmp value (dotNetObject "System.Text.UTF8Encoding" false)
    if io.Exists path then
    (
        io.Replace tmp path (tmp + ".bak")
        io.Delete (tmp + ".bak")
    )
    else io.Move tmp path
)
fn LXMaxBridgeHeartbeat =
(
    local scene = maxFilePath + maxFileName
    if scene == "" do scene = "Untitled"
    LXMaxBridgeWrite (LXMaxBridgeSession + "\\info") ("1\n" + (LXMaxBridgeEncode LXMaxBridgeRoot) + "\n" + (LXMaxBridgeEncode scene))
)
fn LXMaxBridgeRun id =
(
    local script = case id of
    (
        "animation-bake": "动画烘焙工具.ms"
        "keyframe-formula": "自定义公式关键帧.ms"
        "material-split": "按材质ID拆分模型.ms"
        "parent-keep-world": "保持位移建立父子.ms"
        "pmx-import": "PMX导入.ms"
        "root-cleanup": "清理根骨骼.ms"
        default: undefined
    )
    if script == undefined then throw "Unknown plugin ID"
    fileIn (LXMaxBridgeRoot + "\\" + script) quiet:true
)
fn LXMaxBridgeTick =
(
    if LXMaxBridgeBusy do return undefined
    LXMaxBridgeBusy = true
    try
    (
        LXMaxBridgeHeartbeat()
        local requests = getFiles (LXMaxBridgeSession + "\\*.request")
        sort requests
        for request in requests do
        (
            local io = dotNetClass "System.IO.File"
            local working = request + ".working"
            if io.Exists request do
            (
                try
                (
                    io.Move request working
                    local lines = io.ReadAllLines working
                    local response = "OK"
                    try
                    (
                        if lines.count != 2 do throw "Invalid request"
                        local expires = (dotNetClass "System.Int64").Parse lines[2]
                        if (dotNetClass "System.DateTime").UtcNow.Ticks > expires do throw "Request expired"
                        LXMaxBridgeRun lines[1]
                    )
                    catch (response = "ERROR\n" + (LXMaxBridgeEncode (getCurrentException() as string)))
                    LXMaxBridgeWrite (request + ".result") response
                    io.Delete working
                ) catch (format "LX Max bridge request failed: %\n" (getCurrentException()))
            )
        )
    ) catch
    (
        local errorText = getCurrentException() as string
        format "LX Max bridge: %\n" errorText
        try ((dotNetClass "System.IO.File").WriteAllText (LXMaxBridgeSession + "\\last-error.txt") errorText) catch()
    )
    LXMaxBridgeBusy = false
)
LXMaxBridgeHeartbeat()
LXMaxBridgeTimer = dotNetObject "System.Windows.Forms.Timer"
LXMaxBridgeTimer.Interval = 500
dotNet.addEventHandler LXMaxBridgeTimer "Tick" LXMaxBridgeTick
LXMaxBridgeTimer.Start()
format "LX Max Tools connected: %\n" LXMaxBridgeSession
