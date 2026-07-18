#!/usr/bin/env bash
# QSB Pi Receptionist flasher — SAFETY LOCKED
# Flashes Raspberry Pi OS Lite 64-bit to a USB SSD for hostname qsb-reception.
#
# Usage:
#   ./qsb_pi_flash.sh                              # LIST mode — read-only, no writes
#   TARGET=sdX ./qsb_pi_flash.sh                   # VALIDATE target only (still no write)
#   TARGET=sdX CONFIRM=FLASH-QSB ./qsb_pi_flash.sh # actually flash (double-locked)
#
# Safety: refuses any device that is NVMe, hosts a protected mount, is not USB
# transport, or has a partition mounted under / or /vaults. The tower vault
# (nvme1n1 -> /vaults/nvme0) can never be selected.
set -euo pipefail

PROTECT_MOUNTS=("/" "/boot" "/boot/efi" "/vaults/nvme0" "/vaults/ai" "/vaults/kingston")
HOSTNAME_PI="qsb-reception"
PI_USER="qsbpi"
IMG_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
WORK="/vaults/ai/cache/tmp/qsb_pi_build"

red(){ printf '\033[31m%s\033[0m\n' "$*"; }
grn(){ printf '\033[32m%s\033[0m\n' "$*"; }
ylw(){ printf '\033[33m%s\033[0m\n' "$*"; }

# --- compute the set of protected base disks ---
declare -A PROTECTED
for m in "${PROTECT_MOUNTS[@]}"; do
  src=$(findmnt -no SOURCE --target "$m" 2>/dev/null || true)
  [ -z "$src" ] && continue
  base=$(lsblk -no PKNAME "$src" 2>/dev/null | head -1)
  [ -z "$base" ] && base=$(basename "$src" | sed -E 's/p?[0-9]+$//')
  [ -n "$base" ] && PROTECTED["$base"]=1
done
# every nvme disk is protected regardless
while read -r d tran; do
  [ "$tran" = "nvme" ] && PROTECTED["$d"]=1
done < <(lsblk -dn -o NAME,TRAN 2>/dev/null)

is_protected(){ [ -n "${PROTECTED[$1]:-}" ]; }
is_usb(){ [ "$(lsblk -dn -o TRAN /dev/$1 2>/dev/null)" = "usb" ]; }
has_protected_mount(){
  # true if any partition of $1 is mounted under / or /vaults
  local mnts; mnts=$(lsblk -no MOUNTPOINT "/dev/$1" 2>/dev/null | grep -vE '^$' || true)
  while read -r mp; do
    [ -z "$mp" ] && continue
    case "$mp" in /|/boot*|/vaults/*) return 0;; esac
  done <<< "$mnts"
  return 1
}

list_disks(){
  echo "=== BLOCK DEVICES (read-only) ==="
  lsblk -dn -o NAME,SIZE,TRAN,MODEL,SERIAL 2>/dev/null | while read -r name size tran model serial; do
    tag=""
    if is_protected "$name"; then tag=$(red "🔒 PROTECTED")
    elif [ "$tran" = "usb" ]; then tag=$(grn "✅ USB CANDIDATE")
    else tag=$(ylw "— (not usb, skipped)")
    fi
    printf '  /dev/%-8s %-8s %-5s %-22s %-18s %s\n' "$name" "$size" "$tran" "$model" "$serial" "$tag"
  done
  echo ""
  echo "Protected base disks: ${!PROTECTED[*]}"
}

validate_target(){
  local t="$1"
  [ -b "/dev/$t" ] || { red "ABORT: /dev/$t is not a block device"; exit 2; }
  if is_protected "$t"; then red "ABORT: /dev/$t is PROTECTED (nvme/vault/root). Refusing."; exit 3; fi
  if ! is_usb "$t"; then red "ABORT: /dev/$t is not USB transport. Refusing."; exit 4; fi
  if has_protected_mount "$t"; then red "ABORT: /dev/$t has a partition mounted under / or /vaults. Refusing."; exit 5; fi
  local sz; sz=$(lsblk -dn -o SIZE /dev/$t)
  grn "VALIDATED: /dev/$t is USB, not protected, no vault mounts. Size=$sz"
}

TARGET="${TARGET:-}"
CONFIRM="${CONFIRM:-}"

if [ -z "$TARGET" ]; then
  list_disks
  echo ""
  ylw "LIST MODE ONLY — nothing written. To validate a target:"
  echo "  TARGET=sdX $0"
  exit 0
fi

echo "=== VALIDATE TARGET /dev/$TARGET ==="
validate_target "$TARGET"

if [ "$CONFIRM" != "FLASH-QSB" ]; then
  echo ""
  ylw "VALIDATION ONLY — no write performed."
  ylw "To flash Raspberry Pi OS Lite 64-bit to /dev/$TARGET, re-run with:"
  echo "  TARGET=$TARGET CONFIRM=FLASH-QSB $0"
  exit 0
fi

# ---- FLASH PATH (double-locked, only reached with CONFIRM=FLASH-QSB) ----
red "!!! FLASHING /dev/$TARGET — all data on it will be destroyed !!!"
validate_target "$TARGET"   # re-check right before write
mkdir -p "$WORK"
IMG_XZ="$WORK/raspios_lite_arm64.img.xz"
IMG="$WORK/raspios_lite_arm64.img"
if [ ! -f "$IMG" ]; then
  echo "[dl] fetching official RPi OS Lite 64-bit ..."
  curl -fL --retry 3 -o "$IMG_XZ" "$IMG_URL"
  echo "[dl] decompressing ..."
  xz -dk -T0 "$IMG_XZ"
  mv "${IMG_XZ%.xz}" "$IMG" 2>/dev/null || true
  [ -f "$IMG" ] || IMG="${IMG_XZ%.xz}"
fi
echo "[flash] caching sudo credentials (non-interactive)"
echo "${SUDO_PASSWORD:-}" | sudo -S -v 2>/dev/null || { red "sudo auth failed"; exit 6; }
echo "[flash] dd -> /dev/$TARGET"
sudo dd if="$IMG" of="/dev/$TARGET" bs=8M conv=fsync status=progress
sync
echo "[boot] mounting boot partition to enable SSH + hostname + user ..."
sudo partprobe "/dev/$TARGET" || true
BOOTP="/dev/${TARGET}1"
MNT="$WORK/bootmnt"; mkdir -p "$MNT"
sudo mount "$BOOTP" "$MNT"
sudo touch "$MNT/ssh"
# userconf: user + password hash (hash provided at flash time via PI_PW_HASH env)
if [ -n "${PI_PW_HASH:-}" ]; then
  echo "${PI_USER}:${PI_PW_HASH}" | sudo tee "$MNT/userconf.txt" >/dev/null
fi
echo "$HOSTNAME_PI" | sudo tee "$MNT/qsb_hostname_marker" >/dev/null
sudo umount "$MNT"
grn "[done] flashed + SSH enabled. Set hostname/user on first boot. Insert into Pi and power on."
