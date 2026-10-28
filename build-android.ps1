param(
    [Parameter(Mandatory=$true)][string]$ToolchainRoot,
    [string]$OutputFile = "$PSScriptRoot\dist\Orbit-Display-Android.apk",
    [string]$Keystore
)
$ErrorActionPreference = 'Stop'
$toolchain = (Resolve-Path -LiteralPath $ToolchainRoot).Path
$jdk = Get-ChildItem -LiteralPath (Join-Path $toolchain 'jdk') -Directory | Select-Object -First 1
$buildTools = Get-ChildItem -LiteralPath (Join-Path $toolchain 'build-tools') -Directory | Select-Object -First 1
$platform = Get-ChildItem -LiteralPath (Join-Path $toolchain 'platform') -Directory | Select-Object -First 1
if (!$jdk -or !$buildTools -or !$platform) { throw 'JDK 17, Android platform 35 and build-tools 35 are required. See BUILD.md.' }
$env:JAVA_HOME = $jdk.FullName
$env:Path = (Join-Path $jdk.FullName 'bin') + ';' + $env:Path
$build = Join-Path $PSScriptRoot 'build\android'
$android = Join-Path $PSScriptRoot 'android'
New-Item -ItemType Directory -Force "$build\classes","$build\dex",(Split-Path -Parent $OutputFile) | Out-Null
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Build tool failed with exit code $LASTEXITCODE" } }
& "$($buildTools.FullName)\aapt2.exe" compile --dir "$android\res" -o "$build\resources.zip"
Check-Exit
& "$($buildTools.FullName)\aapt2.exe" link -o "$build\unsigned.apk" -I "$($platform.FullName)\android.jar" --manifest "$android\AndroidManifest.xml" "$build\resources.zip"
Check-Exit
$sources = @(Get-ChildItem -LiteralPath "$android\src" -Recurse -Filter '*.java' | ForEach-Object { $_.FullName })
& "$($jdk.FullName)\bin\javac.exe" -encoding UTF-8 --release 8 -classpath "$($platform.FullName)\android.jar" -d "$build\classes" @sources
Check-Exit
& "$($jdk.FullName)\bin\jar.exe" cf "$build\classes.jar" -C "$build\classes" .
Check-Exit
& "$($buildTools.FullName)\d8.bat" --lib "$($platform.FullName)\android.jar" --min-api 26 --output "$build\dex" "$build\classes.jar"
Check-Exit
& "$($jdk.FullName)\bin\jar.exe" uf "$build\unsigned.apk" -C "$build\dex" classes.dex
Check-Exit
& "$($buildTools.FullName)\zipalign.exe" -f -p 4 "$build\unsigned.apk" "$build\aligned.apk"
Check-Exit
if (!$Keystore) { $Keystore = Join-Path $toolchain 'orbit-development.jks' }
if (!(Test-Path -LiteralPath $Keystore)) {
    & "$($jdk.FullName)\bin\keytool.exe" -genkeypair -keystore $Keystore -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Orbit Display Development'
    Check-Exit
}
& "$($buildTools.FullName)\apksigner.bat" sign --ks $Keystore --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out $OutputFile "$build\aligned.apk"
Check-Exit
& "$($buildTools.FullName)\apksigner.bat" verify --verbose --print-certs $OutputFile
Check-Exit
& "$($buildTools.FullName)\aapt2.exe" dump badging $OutputFile
Check-Exit
Get-FileHash -LiteralPath $OutputFile -Algorithm SHA256
