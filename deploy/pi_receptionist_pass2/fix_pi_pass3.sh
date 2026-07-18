#!/bin/bash
# QSB Pi Receptionist — Pass 3 CORRECT no-keyboard fix (re-inject, no re-flash).
# Root cause of Pass 1/2: this stock RPi OS image honors userconf.txt (via
# userconfig.service), NOT custom.toml. With no valid userconf.txt a Desktop
# image drops into the INTERACTIVE user-setup dialog. Fix = valid userconf.txt
# + NetworkManager Wi-Fi + ssh file, keeping the desktop autologin/kiosk bits.
set -euo pipefail
STAGE="$(cd "$(dirname "$0")" && pwd)"
BOOT="${BOOT:-/media/ross/bootfs}"
ROOT="${ROOT:-/media/ross/rootfs}"
PI_USER="ross"; PI_PASS="ross"; HOSTPI="qsb-reception"; WCOUNTRY="GB"
log(){ echo "[pass3] $*"; }
abort(){ echo "[pass3][ABORT] $*" >&2; exit 1; }

# ---- safety: mounts must be on /dev/sda ----
for M in "$BOOT" "$ROOT"; do
  src=$(findmnt -n -o SOURCE --target "$M" 2>/dev/null || true)
  case "$src" in /dev/sda*) ;; *) abort "$M is on '$src', not /dev/sda — refusing";; esac
done
log "boot=$BOOT root=$ROOT (both on /dev/sda — OK)"

# ---- 1. valid userconf.txt (THE fix) ----
HASH=$(openssl passwd -6 "$PI_PASS")
printf '%s:%s\n' "$PI_USER" "$HASH" > "$BOOT/userconf.txt"
log "wrote valid $BOOT/userconf.txt ($PI_USER : \$6\$ sha512)"
# remove the ignored custom.toml + any stale failed_userconf
rm -f "$BOOT/custom.toml" "$BOOT/failed_userconf.txt" "$BOOT/failed_userconf" 2>/dev/null || true
log "removed custom.toml + stale failed_userconf*"

# ---- 2. enable ssh (image honors empty 'ssh' file in boot) ----
touch "$BOOT/ssh"
log "enabled ssh (touch $BOOT/ssh)"

# ---- 3. Wi-Fi via NetworkManager preconfigured connection ----
WSSID="${WIFI_SSID:-Ross’s iPhone}"; WPSK="${WIFI_PSK:-}"
NMD="$ROOT/etc/NetworkManager/system-connections"
install -d -m0755 "$NMD"
cat > "$NMD/preconfigured.nmconnection" <<NM
[connection]
id=preconfigured
uuid=$(cat /proc/sys/kernel/random/uuid)
type=wifi
autoconnect=true
interface-name=wlan0

[wifi]
mode=infrastructure
ssid=$WSSID

[wifi-security]
key-mgmt=wpa-psk
psk=$WPSK

[ipv4]
method=auto

[ipv6]
method=auto
NM
chmod 600 "$NMD/preconfigured.nmconnection"
chown 0:0 "$NMD/preconfigured.nmconnection" 2>/dev/null || true
log "wrote NetworkManager preconfigured.nmconnection (ssid='$WSSID' psk ${WPSK:+set})"
# set wifi regulatory country (needed for RF to enable)
echo "$WCOUNTRY" > "$BOOT/wpa_country.txt" 2>/dev/null || true

# ---- 4. re-apply desktop/kiosk injections (idempotent) ----
# piwiz off
[ -f "$ROOT/etc/xdg/autostart/piwiz.desktop" ] && mv "$ROOT/etc/xdg/autostart/piwiz.desktop" "$ROOT/etc/xdg/autostart/piwiz.desktop.qsb_disabled" && log "piwiz disabled"
# receptionist files
install -d -m0755 "$ROOT/opt/skyscraper_receptionist"
cp -a "$STAGE/opt/." "$ROOT/opt/skyscraper_receptionist/"
chmod +x "$ROOT/opt/skyscraper_receptionist/"*.sh
# autostart
install -d -m0755 "$ROOT/etc/xdg/autostart"
cp "$STAGE/autostart/qsb-reception-kiosk.desktop" "$ROOT/etc/xdg/autostart/"
cp "$STAGE/autostart/qsb-open-keyboard.desktop"  "$ROOT/etc/xdg/autostart/"
install -d -m0755 "$ROOT/etc/skel/Desktop"
cp "$STAGE/autostart/qsb-open-keyboard.desktop" "$ROOT/etc/skel/Desktop/Open Keyboard.desktop" || true
# lightdm desktop autologin
if [ -d "$ROOT/etc/lightdm" ]; then
  install -d "$ROOT/etc/lightdm/lightdm.conf.d"
  printf '[Seat:*]\nautologin-user=%s\nautologin-user-timeout=0\n' "$PI_USER" > "$ROOT/etc/lightdm/lightdm.conf.d/90-qsb-autologin.conf"
fi
# console autologin
install -d "$ROOT/etc/systemd/system/getty@tty1.service.d"
printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin %s --noclear %%I $TERM\n' "$PI_USER" > "$ROOT/etc/systemd/system/getty@tty1.service.d/autologin.conf"
# hostname/hosts
echo "$HOSTPI" > "$ROOT/etc/hostname"
grep -q "$HOSTPI" "$ROOT/etc/hosts" 2>/dev/null || printf '127.0.1.1\t%s\n' "$HOSTPI" >> "$ROOT/etc/hosts"
# firstboot pkg top-up service (safety net) + kiosk user service
cp "$STAGE/systemd/qsb-reception-firstboot-pkgs.service" "$ROOT/etc/systemd/system/"
install -d "$ROOT/etc/systemd/system/multi-user.target.wants"
ln -sf ../qsb-reception-firstboot-pkgs.service "$ROOT/etc/systemd/system/multi-user.target.wants/qsb-reception-firstboot-pkgs.service"
install -d "$ROOT/etc/systemd/user"
cp "$STAGE/systemd/qsb-reception-kiosk.service" "$ROOT/etc/systemd/user/"
log "re-applied desktop autologin + kiosk autostart + /opt + hostname + services"

sync
log "DONE — Pass 3 fix applied. userconf.txt is the real fix; no dialog expected."
echo "OK_PASS3_COMPLETE"
