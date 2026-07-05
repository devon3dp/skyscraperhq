#!/usr/bin/env bash
# Launches UE windowed if not running. Honors -ExecutePythonScript=<path> via $PYSCRIPT.
set -u
PROJECT=/vaults/nvme0/qsb_unreal_skyscraper/QSB_Skyscraper.uproject
ENGINE=/vaults/nvme0/UnrealEngine/Engine/Binaries/Linux/UnrealEditor
LOG=/tmp/qsb_skyscraper_editor.log
PYSCRIPT="${PYSCRIPT:-}"

if pgrep -f "UnrealEditor.*QSB_Skyscraper.uproject" >/dev/null 2>&1; then
  echo "editor already running pid=$(pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' | head -1)"
  exit 0
fi

ARGS=("$PROJECT" "-log" "-stdout")
[[ -n "$PYSCRIPT" ]] && ARGS+=("-ExecutePythonScript=$PYSCRIPT")

DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority \
  nohup "$ENGINE" "${ARGS[@]}" > "$LOG" 2>&1 &
echo "launched editor pid=$!"
for i in {1..18}; do
  if ss -tnlp 2>/dev/null | grep -q ':55557 '; then
    echo "TCP 55557 UP at $((i*5))s"; exit 0
  fi
  sleep 5
done
echo "TCP did not come up within 90s"; exit 1
