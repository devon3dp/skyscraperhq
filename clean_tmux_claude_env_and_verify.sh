#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_clean_tmux_claude_env"
REPORT="$RUN_DIR/reports/clean_tmux_claude_env_report.txt"

mkdir -p "$RUN_DIR/reports" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ CLEAN TMUX CLAUDE ENV + VERIFY"
echo "Generated: $(date -Is)"
echo "Run folder: $RUN_DIR"
echo "============================================================"
echo
echo "Purpose:"
echo " - keep restored Claude key active"
echo " - update tmux global environment"
echo " - verify HQ-Claude and Boardroom are using the restored key"
echo " - do not print full keys"
echo

cd "$PROJECT" || exit 1

set -a
. /home/ross/.skyscraper_secrets/anthropic_api.env
set +a

tmux set-environment -g ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY" 2>/dev/null || true
tmux set-environment -g QSB_ANTHROPIC_API_KEY "$QSB_ANTHROPIC_API_KEY" 2>/dev/null || true

echo "tmux global environment updated from:"
echo "/home/ross/.skyscraper_secrets/anthropic_api.env"

echo
echo "===== EXPECTED ACTIVE KEY ====="
python3 - <<'PY'
import os, re, hashlib
from pathlib import Path

txt = Path("/home/ross/.skyscraper_secrets/anthropic_api.env").read_text(errors="ignore")
m = re.search(r"(sk-ant-[A-Za-z0-9_\-]{20,})", txt)
if not m:
    print("NO KEY FOUND IN ACTIVE ENV FILE")
    raise SystemExit(1)

k = m.group(1)
print("masked=" + k[:14] + "..." + k[-8:])
print("fingerprint=" + hashlib.sha256(k.encode()).hexdigest()[:16])
PY

echo
echo "===== VERIFY LIVE PYTHON SERVICES ONLY ====="
python3 - <<'PY'
import re, hashlib, subprocess
from pathlib import Path

KEY_RE = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{20,})")

active_txt = Path("/home/ross/.skyscraper_secrets/anthropic_api.env").read_text(errors="ignore")
expected_key = KEY_RE.search(active_txt).group(1)
expected_fp = hashlib.sha256(expected_key.encode()).hexdigest()[:16]

def mask(k):
    return k[:14] + "..." + k[-8:]

def fp(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]

ps = subprocess.run(["ps","-eo","pid,comm,args"], capture_output=True, text=True).stdout

pids = []
for line in ps.splitlines():
    if "tools/qsb_hq_claude_dash.py" in line or "tools/qsb_boardroom_hub.py" in line:
        print(line)
        parts = line.split(None, 2)
        if parts and parts[0].isdigit():
            pids.append(parts[0])

ok = True
for pid in sorted(set(pids)):
    raw = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\x00", b"\n").decode("utf-8","ignore")
    keys = sorted(set(KEY_RE.findall(raw)))
    if not keys:
        print(f"pid={pid} NO_CLAUDE_KEY_VISIBLE")
        ok = False
        continue
    for k in keys:
        got = fp(k)
        verdict = "MATCH" if got == expected_fp else "WRONG"
        print(f"pid={pid} masked={mask(k)} fingerprint={got} expected={expected_fp} verdict={verdict}")
        if got != expected_fp:
            ok = False

print()
print("LIVE_CLAUDE_TOKEN_VERDICT=" + ("OK" if ok else "CHECK_FAILED"))
PY

echo
echo "===== ROUTE CHECK ====="
for url in \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/hq/stats" \
  "http://127.0.0.1:8852/brain/usage"
do
  echo "--- $url"
  tmp="$(mktemp /tmp/skyscraperhq_clean_env_XXXXXX)"
  curl -sS --max-time 10 -o "$tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 300 "$tmp" | tr '\n' ' '
  echo
  rm -f "$tmp"
done

echo
echo "============================================================"
echo "DONE"
echo "Report:"
echo "$REPORT"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
