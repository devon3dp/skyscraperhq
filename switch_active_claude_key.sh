#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_switch_claude_key"
REPORT="$RUN_DIR/reports/switch_claude_key_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/scripts" "$RUN_DIR/backups" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ SWITCH ACTIVE CLAUDE KEY"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Run folder: $RUN_DIR"
echo "============================================================"
echo
echo "Safety:"
echo " - full keys will NOT be printed"
echo " - existing active env files will be backed up"
echo " - live trading/execution is NOT touched"
echo " - only Claude/HQ/Boardroom key environment is changed"
echo

cd "$PROJECT" || exit 1

python3 - "$RUN_DIR" <<'PY'
import re, hashlib, shutil, os, sys
from pathlib import Path

run_dir = Path(sys.argv[1])

KEY_RE = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{20,})")

candidate_files = [
    Path("/home/ross/.skyscraper_secrets/anthropic_api.env"),
    Path("/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.anthropic"),
    Path("/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.anthropic.bak_20260706T1200Z_key_swap"),
    Path("/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.anthropic.bak_20260707T150241Z_ross_new_key_paste"),
    Path("/vaults/nvme0/qsb_tower_v1/vaults/keys/anthropic_api.env"),
]

def mask(k):
    return k[:14] + "..." + k[-8:]

def fp(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]

keys = []
seen = set()

for p in candidate_files:
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for k in KEY_RE.findall(txt):
        if k in seen:
            continue
        seen.add(k)
        keys.append({
            "key": k,
            "masked": mask(k),
            "fingerprint": fp(k),
            "source": str(p)
        })

print("===== CANDIDATE CLAUDE KEYS FOUND =====")
if not keys:
    print("NO CLAUDE KEYS FOUND. STOP.")
    raise SystemExit(2)

for i, item in enumerate(keys, 1):
    active_hint = ""
    if item["source"] == "/home/ross/.skyscraper_secrets/anthropic_api.env":
        active_hint = "  <-- currently active source before switch"
    print(f"[{i}] masked={item['masked']} fingerprint={item['fingerprint']}")
    print(f"    source={item['source']}{active_hint}")

print()
print("Recommended from your last report:")
print(" - current running/team-member key: fingerprint b9426ec469b14e8e")
print(" - main SkyscraperHQ vault key:     fingerprint a156f6c5a5535d2f")
print()

choice = input("Type the number to activate, or paste fingerprint to activate: ").strip()

selected = None
if choice.isdigit():
    idx = int(choice)
    if 1 <= idx <= len(keys):
        selected = keys[idx-1]
else:
    for item in keys:
        if item["fingerprint"] == choice:
            selected = item
            break

if not selected:
    print("INVALID SELECTION. STOP.")
    raise SystemExit(3)

key = selected["key"]
masked = selected["masked"]
fingerprint = selected["fingerprint"]

print()
print("===== SELECTED KEY =====")
print(f"masked={masked}")
print(f"fingerprint={fingerprint}")
print(f"source={selected['source']}")

backup_dir = run_dir / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)

targets = [
    Path("/home/ross/.skyscraper_secrets/anthropic_api.env"),
    Path("/vaults/nvme0/qsb_tower_v1/vaults/keys/anthropic_api.env"),
]

for t in targets:
    t.parent.mkdir(parents=True, exist_ok=True)
    if t.exists():
        backup = backup_dir / (t.name + ".bak")
        shutil.copy2(t, backup)
        print(f"backup: {t} -> {backup}")

# Write active env files.
targets[0].write_text(
    '# SkyscraperHQ active Claude / Anthropic API key\n'
    f'# selected_fingerprint={fingerprint}\n'
    f'# selected_source={selected["source"]}\n'
    'export ANTHROPIC_API_KEY="' + key + '"\n'
    'export QSB_ANTHROPIC_API_KEY="' + key + '"\n',
    encoding="utf-8"
)

targets[1].write_text(
    '# SkyscraperHQ vault Claude / Anthropic API key\n'
    f'# selected_fingerprint={fingerprint}\n'
    f'# selected_source={selected["source"]}\n'
    'export ANTHROPIC_API_KEY="' + key + '"\n'
    'export QSB_ANTHROPIC_API_KEY="' + key + '"\n',
    encoding="utf-8"
)

# Write selected key to a private handoff file for shell; chmod 600.
handoff = run_dir / "selected_claude_key.env"
handoff.write_text(
    f'ANTHROPIC_API_KEY="{key}"\n'
    f'QSB_ANTHROPIC_API_KEY="{key}"\n'
    f'SELECTED_MASKED="{masked}"\n'
    f'SELECTED_FINGERPRINT="{fingerprint}"\n',
    encoding="utf-8"
)
os.chmod(handoff, 0o600)

print()
print("WROTE ACTIVE FILES:")
for t in targets:
    print(" -", t)
print()
print("handoff=", handoff)
PY

STATUS="$?"
if [ "$STATUS" != "0" ]; then
  echo "[STOP] Python selection failed with status $STATUS"
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit "$STATUS"
fi

HANDOFF="$RUN_DIR/selected_claude_key.env"
if [ ! -f "$HANDOFF" ]; then
  echo "[FAIL] Missing handoff file: $HANDOFF"
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 4
fi

set -a
. "$HANDOFF"
set +a

echo
echo "===== APPLY KEY TO CURRENT TMUX SERVER ENV ====="
tmux set-environment -g ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY" 2>/dev/null || true
tmux set-environment -g QSB_ANTHROPIC_API_KEY "$QSB_ANTHROPIC_API_KEY" 2>/dev/null || true
echo "selected_masked=$SELECTED_MASKED"
echo "selected_fingerprint=$SELECTED_FINGERPRINT"

echo
echo "===== RESTART ONLY HQ-CLAUDE AND BOARDROOM ====="
tmux kill-session -t hqdash 2>/dev/null || true
tmux kill-session -t br 2>/dev/null || true
sleep 2

echo
echo "--- start HQ-Claude 8850"
tmux new-session -d -s hqdash "cd '$PROJECT' && set -a && . /home/ross/.skyscraper_secrets/anthropic_api.env && set +a && exec python3 -u tools/qsb_hq_claude_dash.py --host 0.0.0.0 --port 8850 >> logs/hq_claude_original_8850.log 2>&1"

sleep 3

echo
echo "--- start Boardroom 8852"
tmux new-session -d -s br "cd '$PROJECT' && ulimit -n 65535 && export MALLOC_ARENA_MAX=2 && set -a && . /home/ross/.skyscraper_secrets/anthropic_api.env && set +a && exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> logs/boardroom_hub_8852.log 2>&1"

sleep 6

echo
echo "===== PORT CHECK ====="
ss -ltnp | grep -E ':(8850|8852)\b' || true

echo
echo "===== ROUTE CHECK ====="
for url in \
  "http://127.0.0.1:8850/" \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/proxy/hq" \
  "http://127.0.0.1:8852/hq/stats" \
  "http://127.0.0.1:8852/brain/usage"
do
  echo "--- $url"
  curl -sS --max-time 10 -o /tmp/skyscraperhq_switch_check.out \
    -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 500 /tmp/skyscraperhq_switch_check.out 2>/dev/null | tr '\n' ' '
  echo
done

echo
echo "===== PROVE RUNNING PROCESS TOKEN FINGERPRINT ====="
python3 - <<'PY'
import re, hashlib
from pathlib import Path
import subprocess

KEY_RE = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{20,})")

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

for pid in pids:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\x00", b"\n").decode("utf-8","ignore")
    except Exception as e:
        print(f"pid={pid} env_read_error={e}")
        continue
    keys = KEY_RE.findall(raw)
    if not keys:
        print(f"pid={pid} NO sk-ant key visible")
        continue
    for k in sorted(set(keys)):
        print(f"pid={pid} masked={mask(k)} fingerprint={fp(k)}")
PY

echo
echo "============================================================"
echo "DONE"
echo "Active Claude key should now be:"
echo "masked=$SELECTED_MASKED"
echo "fingerprint=$SELECTED_FINGERPRINT"
echo
echo "Report:"
echo "$REPORT"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
