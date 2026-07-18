#!/usr/bin/env bash
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
HUB="$ROOT/tools/qsb_boardroom_hub.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
BK="$HUB.bak_team_live_fast_$STAMP"
LOG="$ROOT/logs/boardroom_hub_8852.log"

echo "============================================================"
echo "PATCH TEAM LIVE FAST ROUTE"
echo "Time: $STAMP"
echo "Hub:  $HUB"
echo "Backup: $BK"
echo "============================================================"

cd "$ROOT"

if [ ! -f "$HUB" ]; then
  echo "[FAIL] Hub file not found: $HUB"
  exit 1
fi

cp -a "$HUB" "$BK"
echo "[OK] Backup made"

python3 - <<'PY'
from pathlib import Path
import re, sys

p = Path("tools/qsb_boardroom_hub.py")
txt = p.read_text(encoding="utf-8", errors="ignore")

pattern = re.compile(
    r'(?ms)^(\s*)if self\.path == "/team_live/data":\n.*?^\1if self\.path\.startswith\("/team_live/say"\):'
)

m = pattern.search(txt)
if not m:
    print("[FAIL] Could not find /team_live/data block ending before /team_live/say")
    sys.exit(1)

indent = m.group(1)

replacement = r'''__IND__if self.path == "/team_live/data":
__IND__    # Ross 2026-07-08: FAST iPad Team Live route.
__IND__    # This endpoint must never block the iPad cockpit while dead/offline peers time out.
__IND__    import json as _json
__IND__    import socket as _socket
__IND__    from collections import deque as _deque
__IND__
__IND__    def _alive(_host, _port, _timeout=0.25):
__IND__        try:
__IND__            with _socket.create_connection((_host, int(_port)), timeout=_timeout):
__IND__                return True
__IND__        except Exception:
__IND__            return False
__IND__
__IND__    out = {
__IND__        "ts": utc_iso(),
__IND__        "fast_route": True,
__IND__        "quorum": None,
__IND__        "town_square": [],
__IND__        "cards": {},
__IND__        "connections": {},
__IND__        "note": "Fast route: local status only; dead peers are marked offline, not allowed to block iPad."
__IND__    }
__IND__
__IND__    _peers = {
__IND__        "hq_claude": ("127.0.0.1", 8852),
__IND__        "tp_pip": ("192.168.1.91", 9110),
__IND__        "acer_cass": ("192.168.1.41", 9000),
__IND__        "wren": ("127.0.0.1", 8851),
__IND__    }
__IND__
__IND__    _ceos = []
__IND__    for _ceo, (_host, _port) in _peers.items():
__IND__        _on = _alive(_host, _port)
__IND__        out["connections"][_ceo] = {
__IND__            "endpoint": f"{_host}:{_port}",
__IND__            "status": "online" if _on else "offline",
__IND__            "fast_probe": True
__IND__        }
__IND__        _ceos.append({
__IND__            "ceo": _ceo,
__IND__            "online": bool(_on),
__IND__            "available": bool(_on),
__IND__            "latency_s": 0,
__IND__            "mind": "?",
__IND__            "reply": "",
__IND__            "error": "" if _on else "offline_or_unreachable_fast_probe"
__IND__        })
__IND__
__IND__    _online_count = sum(1 for _c in _ceos if _c["online"])
__IND__    out["quorum"] = {
__IND__        "ts": utc_iso(),
__IND__        "checked_by": "team_live_fast_route",
__IND__        "ceos": _ceos,
__IND__        "online_count": f"{_online_count}/{len(_ceos)}",
__IND__        "quorum_met": _online_count >= 2
__IND__    }
__IND__
__IND__    # Tail town square safely and quickly.
__IND__    try:
__IND__        _p = REG / "qsb_town_square.jsonl"
__IND__        if _p.exists():
__IND__            with _p.open("r", encoding="utf-8", errors="ignore") as _f:
__IND__                _lines = list(_deque(_f, maxlen=60))
__IND__            _rows = []
__IND__            for _l in _lines:
__IND__                _l = _l.strip()
__IND__                if not _l:
__IND__                    continue
__IND__                try:
__IND__                    _rows.append(_json.loads(_l))
__IND__                except Exception:
__IND__                    pass
__IND__            out["town_square"] = _rows
__IND__    except Exception as _e:
__IND__        out["town_square_err"] = str(_e)[:200]
__IND__
__IND__    # Read local operator cards only; never call remote peers here.
__IND__    _card_paths = {
__IND__        "hq_claude": REG / "qsb_hq_claude_operator_card.json",
__IND__        "tp_pip": REG / "qsb_tp_pip_operator_card.json",
__IND__        "acer_cass": REG / "qsb_acer_cass_operator_card.json",
__IND__        "wren": REG / "qsb_wren_operator_card.json",
__IND__    }
__IND__    for _ceo, _path in _card_paths.items():
__IND__        try:
__IND__            if _path.exists():
__IND__                _card = _json.loads(_path.read_text(encoding="utf-8", errors="ignore"))
__IND__                _notes = _card.get("long_form_notes", [])[-3:]
__IND__                out["cards"][_ceo] = [
__IND__                    {
__IND__                        "ts": _n.get("ts", ""),
__IND__                        "head": _n.get("head") or _n.get("text") or _n.get("note") or str(_n)[:180]
__IND__                    }
__IND__                    for _n in _notes
__IND__                ]
__IND__            else:
__IND__                out["cards"][_ceo] = []
__IND__        except Exception as _e:
__IND__            out["cards"][_ceo] = [{"ts": utc_iso(), "head": "card read error: " + str(_e)[:120]}]
__IND__
__IND__    self._send_json(200, out)
__IND__    return
__IND__
__IND__if self.path.startswith("/team_live/say"):'''.replace("__IND__", indent)

new = txt[:m.start()] + replacement + txt[m.end():]
p.write_text(new, encoding="utf-8")
print("[OK] Patched /team_live/data fast route")
PY

echo "[CHECK] Python compile"
python3 -m py_compile "$HUB"
echo "[OK] Python syntax good"

echo "[RESTART] Boardroom hub 8852"
mkdir -p "$ROOT/logs"

if command -v tmux >/dev/null 2>&1; then
  tmux kill-session -t br 2>/dev/null || true
  sleep 1
  tmux new-session -d -s br "cd '$ROOT' && exec python3 tools/qsb_boardroom_hub.py --port 8852 >> '$LOG' 2>&1"
else
  pkill -f "tools/qsb_boardroom_hub.py --port 8852" 2>/dev/null || true
  sleep 1
  nohup python3 tools/qsb_boardroom_hub.py --port 8852 >> "$LOG" 2>&1 &
fi

sleep 3

echo
echo "============================================================"
echo "POST-PATCH PROCESS"
echo "============================================================"
ps -eo pid,ppid,pcpu,pmem,rss,vsz,etime,nlwp,cmd \
  | grep 'tools/qsb_boardroom_hub.py --port 8852' \
  | grep -v grep || true

echo
echo "============================================================"
echo "POST-PATCH ENDPOINT TIMINGS"
echo "============================================================"

for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/link_health" \
  "http://127.0.0.1:8852/diagnostics"
do
  echo "--- $url"
  curl -sS --max-time 10 -o /tmp/qsb_patch_body.txt \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" \
    "$url" || true
  head -c 260 /tmp/qsb_patch_body.txt 2>/dev/null | tr '\n' ' '
  echo
done

echo
echo "============================================================"
echo "DONE"
echo "Backup:"
echo "$BK"
echo "Log:"
echo "$LOG"
echo "============================================================"
