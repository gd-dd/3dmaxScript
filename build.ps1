$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (!(Test-Path -LiteralPath $compilerPath)) { throw '.NET Framework 4.x C# compiler is required.' }
New-Item -ItemType Directory -Force -Path (Join-Path $toolRoot 'bin') | Out-Null
& $compilerPath /nologo /target:winexe /platform:x64 /optimize+ /r:System.Web.Extensions.dll "/win32icon:$toolRoot\src\controller.ico" "/out:$toolRoot\bin\LXMaxSession.exe" "$toolRoot\src\SessionProvider.cs"
if ($LASTEXITCODE -ne 0) { throw 'Controller build failed.' }
$manifestPath = Join-Path $toolRoot '.lxtool\manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
foreach ($property in $manifest.files.PSObject.Properties) {
    $property.Value = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $toolRoot $property.Name)).Hash.ToLowerInvariant()
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 20), $utf8)
Write-Host 'Built bin/LXMaxSession.exe and refreshed manifest hashes. Do not rebuild a published version.'
