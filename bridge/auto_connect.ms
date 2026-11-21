-- Shared startup and idle attachment for the two LX Max packages.
global LXMaxAutoConnectRoot
global LXMaxAutoConnectTimer
global LXMaxAutoConnectApplied
global LXMaxAutoConnectRetry
global LXMaxBridgeSource
global LXMaxBridgeUserRoot
global LXMaxBridgeRequestedUserRoot
global LXMaxBridgeBusy
global LXMaxBridgeSession
global LXMaxAnimationBootstrapSource
global LXMaxAnimationBootstrapDigest
global LXMaxAnimationCanReload

fn LXMaxAutoConnectSignature path =
(
    local io = dotNetClass "System.IO.File"
    local stream = io.OpenRead path
    local sha = (dotNetClass "System.Security.Cryptography.SHA256").Create()
    local value = undefined
    try (value = (dotNetClass "System.BitConverter").ToString (sha.ComputeHash stream))
    catch (stream.Close(); sha.Dispose(); throw())
    stream.Close()
    sha.Dispose()
    substituteString (toLower value) "-" ""
)

fn LXMaxAutoConnectTick =
(
    if theHold.Holding() or LXMaxBridgeBusy == true do return false
    local io = dotNetClass "System.IO.File"
    local paths = dotNetClass "System.IO.Path"
    local year = (((maxVersion())[1] / 1000) as integer) + 1998
    if year < 2023 or year > 2027 do return false
    local hostNames = #("max-tools", "max-animation")
    local entries = #("bridge\\LXMaxBridge.ms", "max\\bootstrap.ms")
    local config = paths.Combine LXMaxAutoConnectRoot "auto-connect"
    for index = 1 to (if year >= 2024 then 2 else 1) do
    (
        local descriptor = paths.Combine config (hostNames[index] + ".txt")
        if io.Exists descriptor do
        (
            local signature = undefined
            try
            (
                local lines = io.ReadAllLines descriptor
                if lines.count != 3 do throw "Invalid LX Max registration"
                signature = lines[1] + "|" + lines[2] + "|" + lines[3]
                if LXMaxAutoConnectApplied[index] != signature and (timeStamp()) >= LXMaxAutoConnectRetry[index] do
                (
                    local root = (dotNetClass "System.Text.Encoding").UTF8.GetString ((dotNetClass "System.Convert").FromBase64String lines[1])
                    if not (paths.IsPathRooted root) or (paths.GetPathRoot root).count < 3 do throw "Invalid LX tool path"
                    if not (io.Exists (paths.Combine root ".lxtool\\manifest.json")) do throw "Missing LX tool manifest"
                    local entry = paths.Combine root entries[index]
                    if index == 1 then
                    (
                        if LXMaxAutoConnectSignature entry != lines[2] do throw "LX Max Tools bridge checksum mismatch"
                        if LXMaxBridgeSource == undefined or toLower LXMaxBridgeSource != toLower entry or LXMaxBridgeUserRoot != LXMaxAutoConnectRoot do
                        (
                            if LXMaxBridgeSession != undefined and ((getFiles (LXMaxBridgeSession + "\\*.request")).count != 0) do return false
                            LXMaxBridgeRequestedUserRoot = LXMaxAutoConnectRoot
                            fileIn entry quiet:true
                        )
                        LXMaxAutoConnectApplied[index] = signature
                    )
                    else
                    (
                        if LXMaxAnimationCanReload == undefined or LXMaxAnimationCanReload == true do
                        (
                            if LXMaxAutoConnectSignature entry != lines[2] do throw "LX Animation startup checksum mismatch"
                            if LXMaxAutoConnectSignature (paths.Combine root "max\\bridge.py") != lines[3] do throw "LX Animation bridge checksum mismatch"
                            if LXMaxAnimationBootstrapSource == undefined or toLower LXMaxAnimationBootstrapSource != toLower entry or LXMaxAnimationBootstrapDigest != lines[3] do fileIn entry quiet:true
                            LXMaxAutoConnectApplied[index] = signature
                        )
                    )
                )
            )
            catch
            (
                LXMaxAutoConnectRetry[index] = (timeStamp()) + 30000
                format "LX Max auto-connect (%): %\n" hostNames[index] (getCurrentException())
            )
        )
    )
    true
)

if LXMaxAutoConnectTimer == undefined do
(
    LXMaxAutoConnectApplied = #(undefined, undefined)
    LXMaxAutoConnectRetry = #(-1,-1)
    LXMaxAutoConnectTimer = dotNetObject "System.Windows.Forms.Timer"
    LXMaxAutoConnectTimer.Interval = 1500
    dotNet.addEventHandler LXMaxAutoConnectTimer "Tick" LXMaxAutoConnectTick
    LXMaxAutoConnectTimer.Start()
)
