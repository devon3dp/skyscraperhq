# Tower SMB Share — Mount Recipes

Server: HQ box, `smbd` running.
Reachable subnets (UFW 445 allow):
- `192.168.0.0/24` — wired LAN (ThinkPad)
- `172.20.10.0/28` — iPhone tether (Acer, HQ when tethered)
- `10.198.101.0/24` — Galaxy WiFi hotspot (phones, laptops)

Server IPs (pick the one that matches your subnet):
- `192.168.0.20` — from ThinkPad-LAN
- `172.20.10.2` — from iPhone tether
- `10.198.101.207` — from Galaxy hotspot

Shares:
| Name | Path | Notes |
|---|---|---|
| tower | /vaults/nvme0/qsb_tower_v1 | Code, registries, floors (vault excluded) |
| ai | /vaults/ai | Backup snapshots + downloads |
| kingston | /vaults/kingston | Kernel iterations, brains/ |
| ssk | /media/ross/SSK Cloud | 1.9T external — shared meeting room + backups |
| root_ro | / | Full PC read-only (vault excluded) |

Auth: `ross` + password saved to `data/registries/samba/tower_share_credentials.json` (chmod 600).

---

## Linux (ThinkPad, other HQ nodes)

One-off:
```bash
sudo mkdir -p /mnt/tower_ssk
sudo mount -t cifs "//192.168.0.20/ssk" /mnt/tower_ssk \
  -o username=ross,password='<PW>',uid=$(id -u),gid=$(id -g),iocharset=utf8,vers=3.0
```

Persistent (`/etc/fstab`):
```
//192.168.0.20/ssk  /mnt/tower_ssk  cifs  credentials=/etc/samba/tower_creds,uid=1000,gid=1000,iocharset=utf8,vers=3.0,_netdev  0  0
```

Where `/etc/samba/tower_creds` (chmod 600) contains:
```
username=ross
password=<PW>
```

Prereq: `sudo apt install cifs-utils`.

## Windows (Acer)

File Explorer → address bar:
```
\\172.20.10.2\ssk
```
(or `\\192.168.0.20\ssk` if on LAN)

When it prompts, use `ross` / `<PW>`. Tick "Remember credentials".

Persistent map to drive letter (PowerShell):
```powershell
$creds = New-Object System.Management.Automation.PSCredential("ross", (ConvertTo-SecureString "<PW>" -AsPlainText -Force))
New-PSDrive -Name "S" -PSProvider FileSystem -Root "\\172.20.10.2\ssk" -Credential $creds -Persist
```

## Android (Galaxy phones)

Solid Explorer (recommended) or CX File Explorer:
1. Menu → Add cloud → SMB / Windows share
2. Server: `10.198.101.207` (or `192.168.0.20` if on LAN)
3. Share: `ssk`
4. Username: `ross`  Password: `<PW>`
5. SMB version: SMBv3 (SMBv2 fallback OK)

## Quick sanity check

```bash
# From any node with smbclient installed
smbclient -L 192.168.0.20 -U "ross%<PW>"
smbclient //192.168.0.20/ssk -U "ross%<PW>" -c 'ls'
```

## Notes

- All shares require auth. No guest / anonymous.
- SMB traffic is on port 445 only; NetBIOS 137/138 blocked.
- Vault under `floors/floor_28_security_department/vault/` is excluded from every share by `veto files` / `path` restrictions in `smb.conf` — verify with `smbclient` before treating this as guaranteed.
- Real-money gates stay OFF everywhere. This share moves files only.
