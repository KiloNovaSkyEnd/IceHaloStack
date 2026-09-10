param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64"
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PIP_PROGRESS_BAR = "off"
$repo = $PSScriptRoot
Push-Location $repo
try {
$buildPython = Join-Path $env:LOCALAPPDATA "IceHaloStackBuild095\venv\Scripts\python.exe"
$runtimePython = Join-Path $env:LOCALAPPDATA "IceHaloStackRuntime0946\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        throw "IceHaloStack private Python runtime was not found."
    }
    $buildRoot = Split-Path (Split-Path $buildPython)
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    & $runtimePython -m venv (Split-Path $buildPython)
}

& $buildPython -m pip install --disable-pip-version-check -r (Join-Path $repo "requirements_runtime.txt") -r (Join-Path $repo "requirements_gpu_cuda11.txt") -r (Join-Path $repo "requirements_build.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed: $LASTEXITCODE" }
& $buildPython -m PyInstaller --noconfirm --clean (Join-Path $repo "IceHaloStackEngine.spec")
if ($LASTEXITCODE -ne 0) { throw "IPC engine build failed: $LASTEXITCODE" }
& $buildPython -m PyInstaller --noconfirm --clean (Join-Path $repo "IceHaloStack.spec")
if ($LASTEXITCODE -ne 0) { throw "Classic workspace build failed: $LASTEXITCODE" }

$publish = Join-Path $repo "artifacts\winui-publish"
$package = Join-Path $repo "dist\IceHaloStack.WinUI_v0.9.6.8a"
if (Test-Path -LiteralPath $publish) { Remove-Item -LiteralPath $publish -Recurse -Force }
if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Recurse -Force }
dotnet publish (Join-Path $repo "winui\IceHaloStack.WinUI\IceHaloStack.WinUI.csproj") -c $Configuration -r $Runtime -p:Platform=x64 --self-contained true -o $publish
if ($LASTEXITCODE -ne 0) { throw "WinUI publish failed: $LASTEXITCODE" }
New-Item -ItemType Directory -Force -Path $package | Out-Null
Copy-Item -Path (Join-Path $publish "*") -Destination $package -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo "dist\IceHaloStackEngine") -Destination (Join-Path $package "Engine") -Recurse
Copy-Item -LiteralPath (Join-Path $repo "dist\IceHaloStack") -Destination (Join-Path $package "Classic") -Recurse

$archive = Join-Path $repo "dist\IceHaloStack.WinUI_v0.9.6.8a_win-x64.zip"
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -LiteralPath $package -DestinationPath $archive -CompressionLevel Optimal
Write-Host "WinUI release package: $archive"
}
finally {
    Pop-Location
}
