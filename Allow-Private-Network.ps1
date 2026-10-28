# Run explicitly as Administrator only when using Wi-Fi / USB tethering.
# Only this executable, TCP 48620, private profiles and local subnet are allowed.
$ErrorActionPreference = 'Stop'
$program = Join-Path $PSScriptRoot 'OrbitDisplay.exe'
if (!(Test-Path -LiteralPath $program)) { throw 'Place this script beside OrbitDisplay.exe' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator, then run this script.' }
$ruleName = 'OrbitDisplay-Private-TCP-48620'
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $ruleName -Enabled True -Profile Private -Direction Inbound -Action Allow -Protocol TCP -LocalPort 48620 -RemoteAddress LocalSubnet -Program $program
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Orbit Display (private local network)' -Direction Inbound -Action Allow -Profile Private -Protocol TCP -LocalPort 48620 -RemoteAddress LocalSubnet -Program $program | Out-Null
}
Write-Output 'Orbit Display can receive connections from the local subnet on private networks.'
