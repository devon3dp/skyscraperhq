# Acer Node Bootstrap

Drop this folder onto the Acer laptop. Ships two files:

- `qsb_node_listener_acer.py` — the HTTP listener (Python 3.11+).
- `setup_acer.ps1` — Windows installer: firewall + autostart + first-run.

## One-shot install (from ADMIN PowerShell on Acer)

```powershell
cd <path>\acer_bootstrap
Set-ExecutionPolicy -Scope Process Bypass
.\setup_acer.ps1
```

That will:
1. Verify Python is installed.
2. Open inbound TCP 9100 in Windows Firewall.
3. Write `qsb_acer_identity.json` (node_id=acer, peers=HQ+ThinkPad).
4. Register `QSB-Node-Acer` scheduled task (autostart at logon, auto-restart).
5. Start the listener in the foreground.

## Verify from HQ

```bash
# HQ side, once Acer is reachable
curl -sS http://<acer-ip>:9100/                # {"ok":true,"node":"acer",...}
curl -sS http://<acer-ip>:9100/status          # host + platform + pid
curl -sS -X POST http://<acer-ip>:9100/msg \
     -H 'Content-Type: application/json' \
     -d '{"from":"hq","to":"acer","kind":"hello","body":"welcome to the tower"}'
```

## Config

To rename or repoint peers later, edit `qsb_acer_identity.json`:

```json
{
  "node_id": "acer",
  "node_name": "Acer-Node",
  "peers": [
    {"id": "hq", "url": "http://172.20.10.2:9100"},
    {"id": "thinkpad", "url": "http://192.168.0.10:9100"}
  ]
}
```

Restart the scheduled task after editing:

```powershell
Stop-ScheduledTask -TaskName "QSB-Node-Acer"
Start-ScheduledTask -TaskName "QSB-Node-Acer"
```

## Uninstall

```powershell
Unregister-ScheduledTask -TaskName "QSB-Node-Acer" -Confirm:$false
Remove-NetFirewallRule -DisplayName "QSB Node Listener 9100"
```

Real-money gates stay OFF everywhere. This is a fleet-comms node only.
