$ErrorActionPreference = 'Stop'
Remove-NetFirewallRule -Name 'OrbitDisplay-Private-TCP-48620' -ErrorAction SilentlyContinue
Write-Output 'Orbit Display firewall rule removed.'
