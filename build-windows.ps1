param([string]$Python = 'python', [string]$OutputDirectory = "$PSScriptRoot\dist")
$ErrorActionPreference = 'Stop'
$pythonExe = (Get-Command $Python -ErrorAction Stop).Source
$previousSearchPath = $env:Path
# Dependency scanners otherwise pick up unrelated DLLs (for example Poppler's
# versioned ICU instead of the Windows ICU API used by Qt). Build with a clean PATH.
$env:Path = (Split-Path -Parent $pythonExe) + ';' + "$env:SystemRoot\System32;$env:SystemRoot"
Push-Location $PSScriptRoot
try {
    & $pythonExe -m PyInstaller --noconfirm --clean --windowed --onedir --name OrbitDisplay --icon "$PSScriptRoot/assets/orbit.ico" --add-data "$PSScriptRoot/assets;assets" --distpath $OutputDirectory --workpath "$PSScriptRoot\build\pyinstaller" --specpath "$PSScriptRoot\build" --collect-all av --collect-submodules dxcam --collect-submodules winrt --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtWebEngineCore --exclude-module cv2 desktop\app.py
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
    # Some managed Python distributions ship an extra SSL trust-policy data file.
    # Preserve it in the frozen runtime; stock CPython does not have this file.
    $sslPolicyFile = & $pythonExe -c "import ssl; from pathlib import Path; p=Path(ssl.__file__).with_name('codex-rejected-cas.pem'); print(str(p) if p.is_file() else '')"
    if ($sslPolicyFile) { Copy-Item -LiteralPath $sslPolicyFile -Destination (Join-Path $OutputDirectory 'OrbitDisplay\_internal\codex-rejected-cas.pem') }
} finally { Pop-Location; $env:Path = $previousSearchPath }


