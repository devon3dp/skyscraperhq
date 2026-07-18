# QSB Worker Network Snapshot — MASTER PHASE 2 (read-only; run on TP-Pip / Acer-Cass)
# Displays identity + network + listening QSB ports. Changes NOTHING.
# Does NOT print Wi-Fi passwords, API keys, or environment values.
# Usage (PowerShell on the worker box):  powershell -ExecutionPolicy Bypass -File qsb_worker_netsnapshot.ps1

Write-Host "=== IDENTITY ==="
hostname
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,Name

Write-Host "`n=== ADAPTERS (Up) ==="
Get-NetAdapter | Where-Object Status -eq "Up" |
  Format-Table Name,InterfaceDescription,Status,MacAddress,LinkSpeed -AutoSize

Write-Host "`n=== IPV4 CONFIG ==="
Get-NetIPConfiguration |
  Format-List InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer

Write-Host "`n=== INTERFACE METRICS (lower = preferred) ==="
Get-NetIPInterface -AddressFamily IPv4 |
  Sort-Object InterfaceMetric |
  Format-Table InterfaceAlias,ConnectionState,InterfaceMetric,Dhcp -AutoSize

Write-Host "`n=== WI-FI (SSID only; NO password) ==="
netsh wlan show interfaces | Select-String -Pattern "Name","SSID","State","Signal","Radio type" |
  Where-Object { $_ -notmatch "Password|Key" }

Write-Host "`n=== LISTENING QSB PORTS ==="
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 8871,8872,9110,9111,9000,8852,8857 } |
  Format-Table LocalAddress,LocalPort,OwningProcess -AutoSize

Write-Host "`n=== PROCESSES OWNING THOSE PORTS ==="
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 8871,8872,9110,9111,9000 } |
  ForEach-Object {
    Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue |
      Select-Object Id,ProcessName,Path
  } | Sort-Object Id -Unique

Write-Host "`n=== TOP ROUTES ==="
Get-NetRoute -AddressFamily IPv4 | Sort-Object RouteMetric | Select-Object -First 20 |
  Format-Table DestinationPrefix,NextHop,RouteMetric,InterfaceAlias -AutoSize

Write-Host "`n=== BOARDROOM REACHABILITY (replace HQ IP if it moved) ==="
foreach ($hq in @('192.168.1.92','192.168.1.72','192.168.1.84')) {
  $r = Test-NetConnection $hq -Port 8852 -WarningAction SilentlyContinue
  Write-Host ("HQ {0}:8852 -> TcpTestSucceeded={1}" -f $hq, $r.TcpTestSucceeded)
}
Write-Host "`n(Read-only snapshot complete. Nothing was changed.)"
