#!/usr/bin/env bash
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="/home/ross/Desktop/qsb_phase2_find_remaining_breaks_$STAMP.txt"

exec > >(tee "$REPORT") 2>&1

sec(){ echo; echo "============================================================"; echo "$*"; echo "============================================================"; }

sec "QSB PHASE 2 — FIND REMAINING BREAKS ONLY"
echo "Generated: $(date -Is)"
echo "Root: $ROOT"
echo "Report: $REPORT"
echo
echo "READ ONLY:"
echo " - no patching"
echo " - no dashboard replacement"
echo " - no live trading"
echo " - no kill-switch"
echo " - no emergency buttons"

cd "$ROOT" || exit 1

sec "1. CONFIRM ORIGINAL HQ / WREN / BOARDROOM / 8765"

for url in \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8851/" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8765/" \
  "http://127.0.0.1:8765/api/unified" \
  "http://127.0.0.1:9100/" \
  "http://127.0.0.1:11434/api/tags" \
  "http://192.168.1.41:9000/" \
  "http://192.168.1.91:9110/"
do
  echo "--- $url"
  curl -sS --max-time 8 -o /tmp/qsb_phase2_body \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" 2>&1 || true
  head -c 180 /tmp/qsb_phase2_body 2>/dev/null | tr '\n' ' '
  echo
done

sec "2. CURRENT PROCESSES / PORTS"

ps aux | grep -Ei "qsb_|boardroom|wren|claude|dashboard|dash|annex|oracle|trader|8850|8851|8852|8765|9110|9000|9201|9202|19200" | grep -v grep || true

echo
ss -ltnp | grep -E ':(8850|8851|8852|8765|9100|9110|9000|8795|8796|9200|9201|9202|19200|8846|8848|8849)\b' || true

sec "3. BOARDROOM RESOURCE STATE"

PY_PID="$(ps -eo pid=,ppid=,pcpu=,pmem=,rss=,vsz=,etime=,nlwp=,args= \
  | awk '/python3/ && /tools\/qsb_boardroom_hub.py/ && /--port 8852/ && !/awk/ {print $1; exit}')"

echo "Boardroom Python PID: $PY_PID"

if [ -n "$PY_PID" ]; then
  echo
  ps -p "$PY_PID" -o pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd

  echo
  echo "--- open fd count"
  ls "/proc/$PY_PID/fd" 2>/dev/null | wc -l

  echo
  echo "--- top open targets"
  for fd in /proc/$PY_PID/fd/*; do
    readlink "$fd" 2>/dev/null || true
  done | sort | uniq -c | sort -nr | head -100

  echo
  echo "--- thread CPU"
  ps -L -p "$PY_PID" -o pid,tid,pcpu,pmem,etime,comm | sort -k3 -nr | head -40

  echo
  echo "--- sockets for boardroom"
  ss -tanp 2>/dev/null | grep "pid=$PY_PID" | head -160 || true
fi

sec "4. LINK HEALTH / DIAGNOSTICS / SLOW ROUTES"

for url in \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/diagnostics" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/trading/data" \
  "http://127.0.0.1:8852/trader_scoreboard" \
  "http://127.0.0.1:8852/brain" \
  "http://127.0.0.1:8852/brain/usage" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/proxy/wren" \
  "http://127.0.0.1:8852/proxy/tp" \
  "http://127.0.0.1:8852/proxy/acer"
do
  echo "--- $url"
  curl -sS --max-time 12 -o /tmp/qsb_phase2_route \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" 2>&1 || true
  head -c 260 /tmp/qsb_phase2_route 2>/dev/null | tr '\n' ' '
  echo
done

sec "5. FIND ORIGINAL ANNEX / ORACLE / TRADER FILES"

echo "--- filenames"
find "$ROOT" \
  -path '*/.git' -prune -o \
  -path '*/.venv' -prune -o \
  -path '*/venv' -prune -o \
  -type f \( \
    -iname '*annex*' -o \
    -iname '*oracle*' -o \
    -iname '*trader*' -o \
    -iname '*scoreboard*' -o \
    -iname '*ticker*' -o \
    -iname '*9201*' -o \
    -iname '*9202*' -o \
    -iname '*19200*' -o \
    -iname '*8846*' -o \
    -iname '*8848*' -o \
    -iname '*8849*' \
  \) -print | sort | head -400

echo
echo "--- grep ports/routes"
grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
  -E "9201|9202|19200|8846|8848|8849|proxy/oracle|proxy/studio|proxy/lumen|proxy/traders_live|annexes/leaderboard|trader_ticker|trading/data|trader_scoreboard|oracle annex|HQ annex|Wren annex" \
  tools src data scripts floors departments 2>/dev/null | head -500

sec "6. FIND TP-PIP ORIGINAL WIRING"

grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
  -E "tp_pip|TP-Pip|192\.168\.1\.91|192\.168\.1\.74|192\.168\.1\.41|9110|heartbeat\.json|proof\.json|proxy/tp" \
  tools src data scripts floors departments 2>/dev/null | head -500

sec "7. EXACT BOARDROOM ROUTE AREAS"

echo "--- proxy map"
grep -nE "proxy/hq|proxy/wren|proxy/tp|proxy/acer|proxy/oracle|proxy/studio|proxy/lumen|proxy/traders_live|_proxy_map" tools/qsb_boardroom_hub.py | head -120

echo
echo "--- trading/data area"
grep -nE "if self.path == \"/trading/data\"|trading/data|trader_scoreboard|oanda_practice|binance_testnet|alpaca_paper" tools/qsb_boardroom_hub.py | head -160

echo
echo "--- brain route area"
grep -nE "if self.path == \"/brain\"|/brain/usage|brain/route|BRAIN|Brain" tools/qsb_boardroom_hub.py | head -160

echo
echo "--- team live data area"
nl -ba tools/qsb_boardroom_hub.py | sed -n '8238,8310p'

echo
echo "--- link health/diagnostics area"
nl -ba tools/qsb_boardroom_hub.py | sed -n '8550,8650p'

sec "8. IPAD LINK MAP FULL"

HTML="/tmp/qsb_phase2_ipad.html"
LINKS="/tmp/qsb_phase2_links.txt"

curl -sS --max-time 8 "http://127.0.0.1:8852/ipad" -o "$HTML" || true

python3 - "$HTML" "$LINKS" <<'PY'
import re, sys
html_path, links_path = sys.argv[1], sys.argv[2]
html = open(html_path, encoding="utf-8", errors="ignore").read()
links = []
for pat in [
    r"""href=['"]([^'"]+)['"]""",
    r"""src=['"]([^'"]+)['"]""",
    r"""fetch\(['"]([^'"]+)['"]""",
    r"""window\.open\(['"]([^'"]+)['"]""",
]:
    links += re.findall(pat, html)

clean = []
for x in links:
    if not x or x.startswith("#") or x.startswith("javascript:") or x.startswith("mailto:"):
        continue
    if x not in clean:
        clean.append(x)

open(links_path, "w").write("\n".join(clean) + "\n")
print("count:", len(clean))
for x in clean:
    print(x)
PY

sec "9. TEST EACH IPAD LINK"

while IFS= read -r link; do
  [ -z "$link" ] && continue

  case "$link" in
    http://*|https://*) url="$link" ;;
    /*) url="http://127.0.0.1:8852$link" ;;
    *) continue ;;
  esac

  case "$url" in
    https://fonts.googleapis.com/*|https://x.com/*|https://skyscraperhq.com/*|https://trade.oanda.com/*|https://app.alpaca.markets/*)
      echo "[SKIP external] $url"
      continue
      ;;
  esac

  line="$(curl -L -sS --max-time 6 -o /tmp/qsb_phase2_linkbody -w "http=%{http_code} total=%{time_total}s size=%{size_download}" "$url" 2>&1)"
  code="$(echo "$line" | sed -n 's/.*http=\([0-9][0-9][0-9]\).*/\1/p' | tail -1)"
  [ -z "$code" ] && code="000"

  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "301" ] || [ "$code" = "302" ]; then
    echo "[OK]   $url -> $line"
  else
    echo "[DEAD] $url -> $line"
  fi
done < "$LINKS"

sec "10. RECENT LOG ERRORS"

echo "--- boardroom log errors"
grep -iE "traceback|error|exception|too many open files|empty reply|broken pipe|connection refused|no route|trading/data|brain|annex|proxy" logs/boardroom_hub_8852.log 2>/dev/null | tail -200 || true

echo
echo "--- dashboard 8765 errors"
grep -iE "traceback|error|exception|keyerror|workers|api/unified" logs/dashboard_8765.log 2>/dev/null | tail -160 || true

echo
echo "--- hq original errors"
grep -iE "traceback|error|exception|brain|town/post|route" logs/hq_claude_original_8850.log 2>/dev/null | tail -160 || true

echo
echo "--- wren errors"
grep -iE "traceback|error|exception|route|ollama|brain" logs/*wren* 2>/dev/null | tail -160 || true

sec "DONE"
echo "Report:"
echo "$REPORT"
