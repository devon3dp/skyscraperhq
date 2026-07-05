#!/usr/bin/env bash
# qsb_unreal_open_editor.sh — launch UE editor windowed if not already running.

set -u
PROJECT=/vaults/nvme0/qsb_unreal_skyscraper/QSB_Skyscraper.uproject
ENGINE=/vaults/nvme0/UnrealEngine/Engine/Binaries/Linux/UnrealEditor
LOG=/tmp/qsb_skyscraper_editor.log

if pgrep -f "UnrealEditor.*QSB_Skyscraper.uproject" >/dev/null 2>&1; then
  echo "editor already running pid=$(pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' | head -1)"
  exit 0
fi

DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority \
  nohup "$ENGINE" "$PROJECT" -log -stdout > "$LOG" 2>&1 &
echo "launched editor pid=$!"
# Wait up to 90s for TCP
for i in {1..18}; do
  if ss -tnlp 2>/dev/null | grep -q ':55557 '; then
    echo "TCP 55557 UP at $((i*5))s"; exit 0
  fi
  sleep 5
done
echo "TCP did not come up within 90s"; exit 1
