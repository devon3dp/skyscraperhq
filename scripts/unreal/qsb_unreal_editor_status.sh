#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
PID=$(pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' | head -1)
TCP=$(ss -tnlp 2>/dev/null | grep -c ':55557 ')
if [[ -n "$PID" ]]; then
  ETIME=$(ps -o etime= -p "$PID" 2>/dev/null | tr -d ' ')
  echo "editor RUNNING pid=$PID etime=$ETIME tcp_55557=$TCP"
else
  echo "editor DOWN tcp_55557=$TCP"
fi
