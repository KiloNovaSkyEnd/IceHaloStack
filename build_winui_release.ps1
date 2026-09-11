param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [int]$MaximumUnpackedMiB = 750,
    [switch]$SkipEngineBuild
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PIP_PROGRESS_BAR = "off"
$repo = $PSScriptRoot
$ReleaseVersion = "v0.9.6.8c"
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

if (-not $SkipEngineBuild) {
    & $buildPython -m pip install --disable-pip-version-check -r (Join-Path $repo "requirements_runtime.txt") -r (Join-Path $repo "requirements_gpu_cuda11.txt") -r (Join-Path $repo "requirements_build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed: $LASTEXITCODE" }
    & $buildPython -m PyInstaller --noconfirm --clean (Join-Path $repo "IceHaloStackEngine.spec")
    if ($LASTEXITCODE -ne 0) { throw "IPC engine build failed: $LASTEXITCODE" }
} elseif (-not (Test-Path -LiteralPath (Join-Path $repo "dist\IceHaloStackEngine\IceHaloStackEngine.exe"))) {
    throw "SkipEngineBuild requires an existing frozen engine output."
}
$publish = Join-Path $repo "artifacts\winui-publish"
$package = Join-Path $repo "dist\IceHaloStack.WinUI_$ReleaseVersion"
if (Test-Path -LiteralPath $publish) { Remove-Item -LiteralPath $publish -Recurse -Force }
if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Recurse -Force }
dotnet publish (Join-Path $repo "winui\IceHaloStack.WinUI\IceHaloStack.WinUI.csproj") -c $Configuration -r $Runtime -p:Platform=x64 --self-contained true -o $publish
if ($LASTEXITCODE -ne 0) { throw "WinUI publish failed: $LASTEXITCODE" }
New-Item -ItemType Directory -Force -Path $package | Out-Null
Copy-Item -Path (Join-Path $publish "*") -Destination $package -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo "dist\IceHaloStackEngine") -Destination (Join-Path $package "Engine") -Recurse

# The Windows 11 package is WinUI-only. Bundling the independent Classic build
# duplicated Python, NumPy, OpenCV, FFmpeg and CUDA and was the cause of the
# previous ~1.3 GiB directory. Windows 7 will receive its own package later.
$forbidden = @("Classic", "venv", "site-packages", "pip-cache", "build")
foreach ($name in $forbidden) {
    if (Test-Path -LiteralPath (Join-Path $package $name)) {
        throw "Forbidden duplicate runtime directory in WinUI package: $name"
    }
}
$packageFiles = Get-ChildItem -LiteralPath $package -Recurse -File
$packageBytes = ($packageFiles | Measure-Object -Property Length -Sum).Sum
$packageMiB = [math]::Round($packageBytes / 1MB, 1)
if ($packageMiB -gt $MaximumUnpackedMiB) {
    throw "WinUI package is $packageMiB MiB, above the $MaximumUnpackedMiB MiB budget."
}
$largestFiles = $packageFiles | Sort-Object Length -Descending | Select-Object -First 20
$sizeReport = Join-Path $package "package-size-report.txt"
@(
    "IceHaloStack WinUI package size report",
    "Version: $ReleaseVersion",
    "Files: $($packageFiles.Count)",
    "Unpacked MiB: $packageMiB",
    "Budget MiB: $MaximumUnpackedMiB",
    "",
    "Largest files:",
    ($largestFiles | ForEach-Object { "{0,8:N1} MiB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($package.Length + 1) })
) | Set-Content -LiteralPath $sizeReport -Encoding UTF8

$archive = Join-Path $repo "dist\IceHaloStack.WinUI_${ReleaseVersion}_win-x64.zip"
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -LiteralPath $package -DestinationPath $archive -CompressionLevel Optimal
Write-Host "WinUI release package: $archive"
Write-Host "Unpacked package size: $packageMiB MiB (budget: $MaximumUnpackedMiB MiB)"
}
finally {
    Pop-Location
}
