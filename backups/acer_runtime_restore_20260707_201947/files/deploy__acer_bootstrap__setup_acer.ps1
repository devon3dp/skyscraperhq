# setup_acer.ps1 - Acer node bootstrap
# Run in an ADMIN PowerShell in the folder that holds this script:
#   Set-ExecutionPolicy -Scope Process Bypass; .\setup_acer.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "[acer] verifying Python..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[acer] python not found. Install Python 3.11+ from python.org and re-run." -ForegroundColor Red
    exit 1
}
& python --version

Write-Host "[acer] opening Windows Firewall inbound TCP 9100..."
try {
    New-NetFirewallRule -DisplayName "QSB Node Listener 9100" -Direction Inbound -Protocol TCP -LocalPort 9100 -Action Allow -Profile Any -ErrorAction Stop | Out-Null
    Write-Host "[acer] firewall rule added."
} catch {
    Write-Host "[acer] firewall rule may already exist ($_)."
}

Write-Host "[acer] writing identity file..."
$identity = @{
    node_id = "acer"
    node_name = "Acer-Node"
    hostname = $env:COMPUTERNAME
    added_ts = (Get-Date).ToString("o")
    peers = @(
        @{ id = "hq"; url = "http://172.20.10.2:9100" },
        @{ id = "thinkpad"; url = "http://192.168.0.10:9100" }
    )
}
$identity | ConvertTo-Json -Depth 5 | Set-Content -Path "$here\qsb_acer_identity.json" -Encoding UTF8
Write-Host "[acer] identity -> $here\qsb_acer_identity.json"

Write-Host "[acer] registering scheduled task (autostart at logon)..."
$exe = (Get-Command python).Source
$args = "`"$here\qsb_node_listener_acer.py`" --host 0.0.0.0 --port 9100"
$action = New-ScheduledTaskAction -Execute $exe -Argument $args -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
try {
    Register-ScheduledTask -TaskName "QSB-Node-Acer" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "[acer] scheduled task 'QSB-Node-Acer' registered."
} catch {
    Write-Host "[acer] scheduled task registration failed: $_" -ForegroundColor Yellow
}

Write-Host "[acer] starting node listener now (foreground; Ctrl-C to stop)..."
& python "$here\qsb_node_listener_acer.py" --host 0.0.0.0 --port 9100
