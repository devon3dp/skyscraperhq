#!/bin/bash
# QSB Raspberry Pi Receptionist — Rebuild Pass 2 flasher + injector.
# NO-KEYBOARD build: RPi OS Desktop 64-bit + custom.toml (user/wifi/ssh/hostname)
# + autologin + kiosk + on-screen keyboard + rotation scripts.
#
# SAFETY: writes ONLY to the confirmed 59.5G USB target. Aborts otherwise.
# Wi-Fi creds are read LIVE from NetworkManager at runtime — never stored in repo.
set -euo pipefail

DEV="${DEV:-/dev/sda}"
STAGE="$(cd "$(dirname "$0")" && pwd)"
SP="$(cat /tmp/qsb_pi_scratch_path 2>/dev/null || echo /tmp)"
IMG_XZ="$SP/raspios-desktop-arm64.img.xz"
HOSTNAME_PI="qsb-reception"
PI_USER="ross"
PI_PASS="ross"          # temporary — Ross must change after first login
WIFI_COUNTRY="GB"

log(){ echo "[build] $*"; }
abort(){ echo "[build][ABORT] $*" >&2; exit 1; }

# ---------- 1. SAFETY: verify target is the 59.5G USB card ----------
[ -b "$DEV" ] || abort "$DEV is not a block device"
TRAN=$(lsblk -dn -o TRAN "$DEV" | tr -d ' ')
SIZE=$(blockdev --getsize64 "$DEV")
MODEL=$(lsblk -dn -o MODEL "$DEV" | sed 's/ *$//')
MIN=$((55*1024*1024*1024)); MAX=$((66*1024*1024*1024))
log "target $DEV  model='$MODEL'  tran=$TRAN  size=$SIZE bytes"
[ "$TRAN" = "usb" ] || abort "$DEV is not USB (tran=$TRAN) — refusing"
[ "$SIZE" -ge "$MIN" ] && [ "$SIZE" -le "$MAX" ] || abort "$DEV size $SIZE out of 55-66G window — refusing"
# Never write a disk that carries / or /vaults
for mp in $(lsblk -ln -o MOUNTPOINT "$DEV" 2>/dev/null); do
  case "$mp" in /|/vaults*|/boot|/boot/efi) abort "$DEV has system mount $mp — refusing";; esac
done
log "SAFETY OK — $DEV is the 59.5G USB Pi card."

if [ "${SKIP_FLASH:-0}" = 1 ]; then
  log "SKIP_FLASH=1 — image already written, doing injection only."
else
# ---------- 2. verify image ----------
[ -f "$IMG_XZ" ] || abort "image not found: $IMG_XZ"
log "verifying image integrity (xz -t)..."
xz -t "$IMG_XZ" || abort "image failed integrity check"

# ---------- 3. unmount any sda partitions ----------
for p in "${DEV}"?*; do
  [ -b "$p" ] || continue
  mp=$(lsblk -no MOUNTPOINT "$p" 2>/dev/null | head -1)
  [ -n "$mp" ] && { log "unmounting $p ($mp)"; umount "$p" || udisksctl unmount -b "$p" 2>/dev/null || true; }
done

# ---------- 4. write image ----------
log "WRITING image to $DEV (this erases the card)..."
xz -dc "$IMG_XZ" | dd of="$DEV" bs=4M conv=fsync status=progress
sync
partprobe "$DEV" 2>/dev/null || true
sleep 3
# resolve partition names (sda1/sda2 or sda p1)
BOOTP="${DEV}1"; ROOTP="${DEV}2"
[ -b "$BOOTP" ] || BOOTP="${DEV}p1"
[ -b "$ROOTP" ] || ROOTP="${DEV}p2"
[ -b "$BOOTP" ] && [ -b "$ROOTP" ] || { partprobe "$DEV"; sleep 3; }
log "boot=$BOOTP root=$ROOTP"
fi  # end SKIP_FLASH guard

# In SKIP_FLASH mode, resolve partitions here.
BOOTP="${BOOTP:-${DEV}1}"; ROOTP="${ROOTP:-${DEV}2}"
[ -b "$BOOTP" ] || BOOTP="${DEV}p1"
[ -b "$ROOTP" ] || ROOTP="${DEV}p2"

# ---------- 5. mount ----------
B=$(mktemp -d); R=$(mktemp -d)
mount "$BOOTP" "$B"
mount "$ROOTP" "$R"
log "mounted boot->$B root->$R"

# ---------- 6. custom.toml (headless first-boot: user/wifi/ssh/hostname/locale) ----------
# Wi-Fi creds: prefer values passed in via env (extracted as the user BEFORE
# sudo, because the NM secret agent is user-session bound). Fallback to nmcli.
WSSID="${WIFI_SSID:-}"
WPSK="${WIFI_PSK:-}"
if [ -z "$WSSID" ]; then
  WCON=$(nmcli -t -f NAME,TYPE con show --active 2>/dev/null | awk -F: '$2~/wireless/{print $1; exit}')
  WSSID=$(nmcli -t -f 802-11-wireless.ssid con show "$WCON" 2>/dev/null | cut -d: -f2-)
  WPSK=$(nmcli -s -g 802-11-wireless-security.psk con show "$WCON" 2>/dev/null)
fi
[ -n "$WSSID" ] || WSSID="Ross’s iPhone"
log "wifi ssid='$WSSID' (psk ${WPSK:+present}${WPSK:-MISSING})"
PWHASH=$(openssl passwd -6 "$PI_PASS")

cat > "$B/custom.toml" <<TOML
# QSB Receptionist Pass 2 — headless first-boot config (no keyboard needed).
config_version = 1

[system]
hostname = "$HOSTNAME_PI"

[user]
name = "$PI_USER"
password = "$PWHASH"
password_encrypted = true

[ssh]
enabled = true
password_authentication = true

[wlan]
ssid = "$WSSID"
password = "$WPSK"
password_encrypted = false
hidden = false
country = "$WIFI_COUNTRY"

[locale]
keymap = "gb"
timezone = "Europe/London"
TOML
log "wrote $B/custom.toml"

# ---------- 6b. rotation options in config.txt (commented; safe default off) ----------
CFG="$B/config.txt"; [ -f "$CFG" ] || CFG="$B/firmware/config.txt"
cat >> "$CFG" <<'CFGADD'

# QSB touchscreen rotation options (Receptionist Pass 2)
# If the screen is upside down, uncomment ONE of these and reboot,
# or run /opt/skyscraper_receptionist/rotate_screen_180.sh after boot.
# display_rotate=2
# video=DSI-1:800x480@60,rotate=180
CFGADD
log "appended rotation options to $(basename "$CFG")"

# ---------- 7. inject into rootfs ----------
# 7a. receptionist files
install -d -m0755 "$R/opt/skyscraper_receptionist"
cp -a "$STAGE/opt/." "$R/opt/skyscraper_receptionist/"
chmod +x "$R/opt/skyscraper_receptionist/"*.sh
log "installed /opt/skyscraper_receptionist"

# 7b. XDG autostart (kiosk + open-keyboard) — reliable on labwc/wayfire
install -d -m0755 "$R/etc/xdg/autostart"
cp "$STAGE/autostart/qsb-reception-kiosk.desktop" "$R/etc/xdg/autostart/"
cp "$STAGE/autostart/qsb-open-keyboard.desktop"  "$R/etc/xdg/autostart/"
# Desktop shortcut copy for the user (visible "Open Keyboard" button)
install -d -m0755 "$R/etc/skel/Desktop"
cp "$STAGE/autostart/qsb-open-keyboard.desktop" "$R/etc/skel/Desktop/Open Keyboard.desktop" || true
log "installed XDG autostart + desktop Open Keyboard shortcut"

# 7c. disable the first-run wizard (piwiz) so no blue setup dialog
for wiz in "$R/etc/xdg/autostart/piwiz.desktop"; do
  [ -f "$wiz" ] && mv "$wiz" "$wiz.qsb_disabled" && log "disabled $(basename "$wiz")"
done

# 7d. lightdm desktop autologin
if [ -d "$R/etc/lightdm" ]; then
  install -d "$R/etc/lightdm/lightdm.conf.d"
  cat > "$R/etc/lightdm/lightdm.conf.d/90-qsb-autologin.conf" <<LD
[Seat:*]
autologin-user=$PI_USER
autologin-user-timeout=0
LD
  log "lightdm autologin -> $PI_USER"
fi

# 7e. console autologin (belt-and-braces)
install -d "$R/etc/systemd/system/getty@tty1.service.d"
cat > "$R/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<GA
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $PI_USER --noclear %I \$TERM
GA
log "console autologin -> $PI_USER"

# 7f. hostname / hosts (belt; custom.toml also sets it)
echo "$HOSTNAME_PI" > "$R/etc/hostname"
if [ -f "$R/etc/hosts" ] && ! grep -q "$HOSTNAME_PI" "$R/etc/hosts"; then
  printf '127.0.1.1\t%s\n' "$HOSTNAME_PI" >> "$R/etc/hosts"
fi

# 7g. first-boot package top-up service (OSK/chromium if missing), enabled
cp "$STAGE/systemd/qsb-reception-firstboot-pkgs.service" "$R/etc/systemd/system/"
ln -sf ../qsb-reception-firstboot-pkgs.service \
  "$R/etc/systemd/system/multi-user.target.wants/qsb-reception-firstboot-pkgs.service"
log "enabled qsb-reception-firstboot-pkgs.service"

# 7h. kiosk USER service available (NOT enabled — autostart is primary)
install -d "$R/etc/systemd/user"
cp "$STAGE/systemd/qsb-reception-kiosk.service" "$R/etc/systemd/user/"
log "installed qsb-reception-kiosk.service (user, available; autostart is primary)"

# ---------- 8. finish ----------
sync
umount "$B"; umount "$R"
rmdir "$B" "$R" 2>/dev/null || true
sync
log "DONE. Card is ready. Safe to remove $DEV."
echo "OK_BUILD_COMPLETE"
