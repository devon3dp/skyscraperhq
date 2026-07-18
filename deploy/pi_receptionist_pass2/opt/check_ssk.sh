#!/bin/bash
# QSB Receptionist — SSK 2TB storage check + safe mount. NEVER formats.
# Mounts an existing filesystem read-write under /srv/qsb_reception_vault.
set -u
MNT=/srv/qsb_reception_vault
echo "=== QSB SSK check $(date -Is) ==="
echo "--- block devices ---"
lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN,TYPE,FSTYPE,LABEL,MOUNTPOINTS 2>/dev/null

# Identify SSK by model/size/label — do NOT touch the boot disk.
BOOTDEV=$(findmnt -n -o SOURCE / 2>/dev/null | sed -E 's/p?[0-9]+$//')
CAND=""
while read -r name size model; do
  dev="/dev/$name"
  [ "$dev" = "$BOOTDEV" ] && continue
  if echo "$model" | grep -qiE 'ssk|ssm|nas'; then CAND="$dev"; fi
done < <(lsblk -dn -o NAME,SIZE,MODEL 2>/dev/null)

if [ -z "$CAND" ]; then
  echo "SSK not identified by model. Not mounting. (Never guesses a disk.)"
  exit 0
fi
echo "SSK candidate: $CAND"

PART=$(lsblk -ln -o NAME,FSTYPE "$CAND" 2>/dev/null | awk '$2!=""{print "/dev/"$1; exit}')
if [ -z "$PART" ]; then
  echo "REFUSING to format. No existing filesystem found on $CAND — leaving untouched."
  exit 0
fi
echo "SSK filesystem partition: $PART"
mkdir -p "$MNT"
if mountpoint -q "$MNT"; then
  echo "Already mounted at $MNT"
else
  if sudo mount "$PART" "$MNT" 2>/dev/null; then
    echo "Mounted $PART at $MNT (read-write, no format)."
  else
    echo "Mount failed (fs may need check). NOT formatting."
  fi
fi
echo "NOTE: SSK is never used as boot disk and is never formatted by this script."
