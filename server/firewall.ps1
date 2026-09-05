# Interview Cracker — allow the voice server (port 8765) through Windows Defender Firewall.
# Run ONCE as Administrator:  powershell -ExecutionPolicy Bypass -File .\firewall.ps1
# The hotspot adapter is usually classed "Public", so both profiles are included (BLUEPRINT §8.4).
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "venv python not found at $py — run 'uv sync' first" }
$name = 'InterviewCracker voice server (8765)'
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Program $py -Profile Private,Public | Out-Null
Write-Host "OK: inbound TCP 8765 allowed for $py (Private+Public)."
# Optional hardening for the demo laptop (uncomment to apply):
# reg add HKLM\SYSTEM\CurrentControlSet\Services\icssvc\Settings /v PeerlessTimeoutEnabled /t REG_DWORD /d 0 /f   # hotspot never auto-sleeps
# powercfg /change standby-timeout-ac 0                                                                            # no sleep on AC
