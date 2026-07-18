#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
BOARDROOM="$PROJECT/tools/qsb_boardroom_hub.py"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"
ROUTER_LOG="$PROJECT/logs/gene_pool_router_8860.log"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_fix_boardroom_wren_file_leak"
REPORT="$RUN_DIR/reports/fix_boardroom_wren_file_leak_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIX BOARDROOM / WREN FILE-HANDLE LEAK + SMOKE TEST"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Fix Boardroom Wren registry reads."
echo " - Keep Gene Pool wiring."
echo " - Keep Claude HQ name."
echo " - Keep Wren protected."
echo " - CEOs use API Gene Pool only."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading changes."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$BOARDROOM" ]; then
  echo "[FAIL] Missing Boardroom file: $BOARDROOM"
  exit 1
fi

echo
echo "===== 1. BACKUP BOARDROOM ====="
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.before_wren_file_leak_fix_$STAMP"
echo "[OK] backup written"

echo
echo "===== 2. PATCH SAFE CACHED TAIL READER ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
s = p.read_text(errors="ignore")

# Remove misplaced future import if present.
s = s.replace("from __future__ import annotations\n", "")
s = s.replace("from __future__ import annotations\r\n", "")

# Ensure imports.
for imp in ["import time", "from collections import deque"]:
    if imp not in s:
        s = imp + "\n" + s

helper = r'''
# SKYSCRAPERHQ_SAFE_TAIL_CACHE_V1
_SAFE_TAIL_CACHE = {}

def _safe_tail_lines(path_obj, n=8, ttl=1.5, max_bytes=262144):
    """
    Cached tail reader for hot JSONL/registry files.
    Prevents Boardroom request handlers repeatedly opening Wren registry files.
    Always closes file handles immediately.
    """
    import time
    from pathlib import Path

    try:
        path = str(path_obj)
        n = int(n or 8)
        now_ts = time.time()
        cached = _SAFE_TAIL_CACHE.get((path, n))
        if cached and now_ts - cached.get("ts", 0) < ttl:
            return list(cached.get("lines", []))

        pp = Path(path)
        if not pp.exists() or not pp.is_file():
            lines = []
        else:
            size = pp.stat().st_size
            with pp.open("rb") as f:
                if size > max_bytes:
                    f.seek(max(0, size - max_bytes))
                raw = f.read()
            text = raw.decode("utf-8", "ignore")
            lines = text.splitlines()[-n:]

        _SAFE_TAIL_CACHE[(path, n)] = {"ts": now_ts, "lines": lines}
        return lines
    except OSError as e:
        # Especially Errno 24: do not crash the Boardroom request.
        return [f"[safe_tail_error] {type(e).__name__}: {e}"]
    except Exception as e:
        return [f"[safe_tail_error] {type(e).__name__}: {e}"]

'''

if "def _safe_tail_lines(" not in s:
    # Insert after import block.
    lines = s.splitlines(True)
    insert_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_idx = i + 1
        elif stripped == "" or stripped.startswith("#"):
            continue
        else:
            break
    s = "".join(lines[:insert_idx]) + helper + "".join(lines[insert_idx:])
    print("[OK] inserted _safe_tail_lines helper")
else:
    print("[OK] _safe_tail_lines already exists")

# Replace known hot patterns.
patterns = [
    (r'for l in cyc\.read_text\(errors="ignore"\)\.splitlines\(\)\[-8:\]:',
     'for l in _safe_tail_lines(cyc, 8):'),
    (r'for l in bc\.read_text\(errors="ignore"\)\.splitlines\(\)\[-4:\]:',
     'for l in _safe_tail_lines(bc, 4):'),
    (r'for l in ([A-Za-z_][A-Za-z0-9_]*)\.read_text\(errors="ignore"\)\.splitlines\(\)\[-8:\]:',
     r'for l in _safe_tail_lines(\1, 8):'),
    (r'for l in ([A-Za-z_][A-Za-z0-9_]*)\.read_text\(errors="ignore"\)\.splitlines\(\)\[-4:\]:',
     r'for l in _safe_tail_lines(\1, 4):'),
]

changed = 0
for pat, repl in patterns:
    s2, n = re.subn(pat, repl, s)
    if n:
        changed += n
        s = s2

print(f"[OK] replaced hot read_text tail loops: {changed}")

p.write_text(s, encoding="utf-8")
PY

echo
echo "===== 3. VERIFY PATCH LOCATIONS ====="
grep -n "_safe_tail_lines\|qsb_wren_evolution_cycles\|qsb_wren_bug_catches" "$BOARDROOM" | head -n 40 || true

echo
echo "===== 4. COMPILE BOARDROOM ====="
python3 -m py_compile "$BOARDROOM" && echo "[OK] Boardroom compiles" || exit 2

echo
echo "===== 5. STOP DUPLICATE BOARDROOM PROCESSES ====="
echo "--- before ---"
pgrep -af "qsb_boardroom_hub.py|:8852" || true

pkill -f "tools/qsb_boardroom_hub.py.*--port 8852" 2>/dev/null || true
pkill -f "qsb_boardroom_hub.py.*8852" 2>/dev/null || true
sleep 3

echo "--- after stop ---"
pgrep -af "qsb_boardroom_hub.py|:8852" || true

echo
echo "===== 6. START BOARDROOM WITH HIGH FILE LIMIT ====="
(
  cd "$PROJECT" || exit 1
  ulimit -n 65535
  export MALLOC_ARENA_MAX=2
  exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> "$BOARDROOM_LOG" 2>&1
) &
BPID="$!"
echo "$BPID" > "$PROJECT/runtime/boardroom_hub_8852.pid"
echo "[OK] Boardroom pid=$BPID"

echo
echo "===== 7. WAIT FOR BOARDROOM ====="
OK=NO
for i in $(seq 1 30); do
  if curl -sS --max-time 2 "http://127.0.0.1:8852/ipad" >/tmp/boardroom_ipad.html 2>/dev/null; then
    OK=YES
    break
  fi
  sleep 1
done

if [ "$OK" != YES ]; then
  echo "[FAIL] Boardroom did not come online"
  tail -n 200 "$BOARDROOM_LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] Boardroom online"

echo
echo "===== 8. CHECK LIVE FILE LIMIT ====="
PID="$(cat "$PROJECT/runtime/boardroom_hub_8852.pid" 2>/dev/null || true)"
if [ -n "$PID" ] && [ -r "/proc/$PID/limits" ]; then
  grep -i "Max open files" "/proc/$PID/limits" || true
fi

echo
echo "===== 9. SMOKE TEST HOT ROUTES REPEATEDLY ====="
URLS=(
  "http://127.0.0.1:8852/ipad"
  "http://127.0.0.1:8852/team_live/data"
  "http://127.0.0.1:8852/link_health"
  "http://127.0.0.1:8852/town_square_feed"
  "http://127.0.0.1:8852/tasks/data"
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
)

for round in 1 2 3; do
  echo "--- round $round ---"
  for url in "${URLS[@]}"; do
    printf "%s -> " "$url"
    curl -sS --max-time 25 -o "$RUN_DIR/logs/route_${round}.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  done
done

echo
echo "===== 10. CEO SUBMIT CHECK THROUGH BOARDROOM PROXY ====="
python3 - <<'PY'
import json, urllib.request, urllib.error

jobs = [
    ("Claude HQ", "architecture", "Post-leak-fix smoke: Claude HQ architecture job through Boardroom proxy."),
    ("CEO 2", "coding", "Post-leak-fix smoke: CEO 2 coding job through Boardroom proxy."),
    ("CEO 3", "summary", "Post-leak-fix smoke: CEO 3 summary job through Boardroom proxy."),
]

for ceo, task, ask in jobs:
    payload = {"ceo": ceo, "task": task, "ask": ask}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8852/proxy/gene_pool/api/submit_job",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("---", ceo, task)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            print("http", r.status)
            print(r.read().decode("utf-8", "replace")[:1000])
    except Exception as e:
        print("ERROR", repr(e))
PY

echo
echo "===== 11. FINAL GENE POOL LIVE CHECK ====="
sleep 6
curl -sS --max-time 25 "http://127.0.0.1:8852/proxy/gene_pool/api/live" > "$RUN_DIR/reports/final_gene_pool_live.json"

python3 - <<PYSHOW
import json
d=json.load(open("$RUN_DIR/reports/final_gene_pool_live.json"))
m=d.get("metrics",{})
print("ok:", d.get("ok"))
print("stored_key_count:", m.get("stored_key_count"))
print("active_provider_count:", m.get("active_provider_count"))
print("route_count:", m.get("autonomy",{}).get("route_count"))
print("events:", len(d.get("logs",[])))
print("latest_decision:", d.get("latest_decision"))
print("")
for name,panel in (d.get("ceo_panels") or {}).items():
    print(name, "| task=", panel.get("task"), "| provider=", panel.get("provider_label"), "| ask=", (panel.get("ask") or "")[:90])
PYSHOW

echo
echo "===== 12. ERROR SCAN AFTER PATCH ====="
echo "--- Boardroom recent Errno 24 / traceback check ---"
tail -n 260 "$BOARDROOM_LOG" | grep -Ei "Errno 24|Too many open files|Traceback|Exception|NameError|BrokenPipe" || true

echo
echo "--- current fd count ---"
if [ -n "$PID" ] && [ -d "/proc/$PID/fd" ]; then
  echo "Boardroom PID: $PID"
  echo -n "Open FD count: "
  ls "/proc/$PID/fd" 2>/dev/null | wc -l || true
fi

echo
echo "===== 13. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Gene Pool through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"
echo
echo "Town Square:"
echo "http://${LAN_IP:-127.0.0.1}:8852/town_square"
echo
echo "Task Council:"
echo "http://${LAN_IP:-127.0.0.1}:8852/tasks"

echo
echo "============================================================"
echo "DONE — BOARDROOM/WREN FILE LEAK PATCH + SMOKE COMPLETE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/final_gene_pool_live.json" "$SEND/final_gene_pool_live.json"
