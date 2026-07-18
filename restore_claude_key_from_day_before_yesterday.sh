#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_restore_claude_key_day_before_yesterday"
REPORT="$RUN_DIR/reports/restore_claude_key_day_before_yesterday_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/scripts" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ RESTORE CLAUDE KEY FROM DAY BEFORE YESTERDAY"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Run folder: $RUN_DIR"
echo "============================================================"
echo
echo "Safety:"
echo " - no full keys printed"
echo " - auto-selects dated backup from day before yesterday"
echo " - backs up active env files first"
echo " - restarts only HQ-Claude 8850 and Boardroom 8852"
echo " - live trading/execution untouched"
echo

cd "$PROJECT" || exit 1

TARGET_DATE="${TARGET_DATE:-$(date -d '2 days ago' +%Y%m%d)}"
echo "TARGET_DATE=$TARGET_DATE"
echo

python3 - "$RUN_DIR" "$TARGET_DATE" <<'PY'
import os, re, sys, hashlib, shutil, time
from pathlib import Path

run_dir = Path(sys.argv[1])
target_date = sys.argv[2]
project = Path("/vaults/nvme0/qsb_tower_v1")

KEY_RE = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{20,})")

def mask(k):
    return k[:14] + "..." + k[-8:]

def fp(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]

search_roots = [
    Path("/home/ross/.skyscraper_secrets"),
    project / "floors/floor_28_security_department/vault",
    project / "vaults/keys",
]

records = []
seen_file_key = set()

for root in search_roots:
    if not root.exists():
        continue
    for p in sorted(root.glob("*")):
        if not p.is_file():
            continue
        name = p.name.lower()
        if not any(x in name for x in ["anthropic", "claude", "env", "key", "bak"]):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        keys = KEY_RE.findall(txt)
        if not keys:
            continue
        for k in keys:
            key = (str(p), k)
            if key in seen_file_key:
                continue
            seen_file_key.add(key)
            try:
                mtime_date = time.strftime("%Y%m%d", time.localtime(p.stat().st_mtime))
            except Exception:
                mtime_date = ""
            records.append({
                "path": p,
                "key": k,
                "masked": mask(k),
                "fingerprint": fp(k),
                "mtime_date": mtime_date,
                "path_text": str(p),
            })

print("===== ALL CLAUDE KEY RECORDS FOUND =====")
for i, r in enumerate(records, 1):
    date_hit = "YES" if target_date in r["path_text"] or target_date == r["mtime_date"] else "NO"
    print(f"[{i}] masked={r['masked']} fingerprint={r['fingerprint']} date_match={date_hit}")
    print(f"    source={r['path']}")
    print(f"    mtime_date={r['mtime_date']}")

matches = [r for r in records if target_date in r["path_text"]]

if not matches:
    matches = [r for r in records if r["mtime_date"] == target_date]

# Prefer backup files dated that day.
matches.sort(key=lambda r: (
    0 if ".bak_" in r["path_text"] else 1,
    0 if "key_swap" in r["path_text"] else 1,
    len(r["path_text"])
))

print()
print("===== AUTO-SELECTION =====")
if not matches:
    print(f"[STOP] No Claude key found for target date {target_date}.")
    raise SystemExit(2)

selected = matches[0]
print(f"selected_masked={selected['masked']}")
print(f"selected_fingerprint={selected['fingerprint']}")
print(f"selected_source={selected['path']}")

key = selected["key"]
selected_fp = selected["fingerprint"]

backup_dir = run_dir / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)

targets = [
    Path("/home/ross/.skyscraper_secrets/anthropic_api.env"),
    Path("/vaults/nvme0/qsb_tower_v1/vaults/keys/anthropic_api.env"),
    Path("/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.anthropic"),
]

print()
print("===== BACKUP ACTIVE ENV FILES =====")
for t in targets:
    t.parent.mkdir(parents=True, exist_ok=True)
    if t.exists():
        b = backup_dir / (t.name + ".bak_before_restore")
        shutil.copy2(t, b)
        print(f"backup={t} -> {b}")
    else:
        print(f"missing_before_restore={t}")

print()
print("===== WRITE RESTORED ACTIVE ENV FILES =====")

home_env = targets[0]
home_env.write_text(
    "# SkyscraperHQ active Claude / Anthropic API key\n"
    f"# restored_from={selected['path']}\n"
    f"# restored_fingerprint={selected_fp}\n"
    f"# restored_at={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
    f'export ANTHROPIC_API_KEY="{key}"\n'
    f'export QSB_ANTHROPIC_API_KEY="{key}"\n',
    encoding="utf-8"
)
os.chmod(home_env, 0o600)
print(f"wrote={home_env}")

vault_env = targets[1]
vault_env.write_text(
    "# SkyscraperHQ vault Claude / Anthropic API key\n"
    f"# restored_from={selected['path']}\n"
    f"# restored_fingerprint={selected_fp}\n"
    f'export ANTHROPIC_API_KEY="{key}"\n'
    f'export QSB_ANTHROPIC_API_KEY="{key}"\n',
    encoding="utf-8"
)
os.chmod(vault_env, 0o600)
print(f"wrote={vault_env}")

floor_env = targets[2]
floor_env.write_text(
    "# Anthropic Claude API — SkyscraperHQ restored active key\n"
    f"# restored_from={selected['path']}\n"
    f"# restored_fingerprint={selected_fp}\n"
    f'export ANTHROPIC_API_KEY="{key}"\n'
    f'export QSB_ANTHROPIC_API_KEY="{key}"\n'
    f'QSB_ANTHROPIC_API_KEY={key}\n'
    "QSB_ANTHROPIC_ENDPOINT=https://api.anthropic.com/v1/messages\n"
    "QSB_ANTHROPIC_DEFAULT_MODEL=claude-haiku-4-5-20251001\n"
    "QSB_ANTHROPIC_PREMIUM_MODEL=claude-opus-4-7\n",
    encoding="utf-8"
)
os.chmod(floor_env, 0o600)
print(f"wrote={floor_env}")

(run_dir / "selected_public.txt").write_text(
    f"selected_masked={selected['masked']}\n"
    f"selected_fingerprint={selected_fp}\n"
    f"selected_source={selected['path']}\n",
    encoding="utf-8"
)

print()
print("RESTORE_SELECTION_OK")
PY

STATUS="$?"
if [ "$STATUS" != "0" ]; then
  echo "[STOP] restore selection failed with status $STATUS"
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit "$STATUS"
fi

echo
echo "===== SELECTED PUBLIC FINGERPRINT ====="
cat "$RUN_DIR/selected_public.txt"

echo
echo "===== RESTART ONLY HQ-CLAUDE AND BOARDROOM ====="
tmux kill-session -t hqdash 2>/dev/null || true
tmux kill-session -t br 2>/dev/null || true
sleep 2

echo "--- starting HQ-Claude 8850"
tmux new-session -d -s hqdash "cd '$PROJECT' && set -a && . /home/ross/.skyscraper_secrets/anthropic_api.env && set +a && exec python3 -u tools/qsb_hq_claude_dash.py --host 0.0.0.0 --port 8850 >> logs/hq_claude_original_8850.log 2>&1"

sleep 3

echo "--- starting Boardroom 8852"
tmux new-session -d -s br "cd '$PROJECT' && ulimit -n 65535 && export MALLOC_ARENA_MAX=2 && set -a && . /home/ross/.skyscraper_secrets/anthropic_api.env && set +a && exec python3 -u tools/qsb_boardroom_hub.py --port 8852 >> logs/boardroom_hub_8852.log 2>&1"

sleep 7

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
  tmp="$(mktemp /tmp/skyscraperhq_restore_XXXXXX)"
  curl -sS --max-time 10 -o "$tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 400 "$tmp" | tr '\n' ' '
  echo
  rm -f "$tmp"
done

echo
echo "===== PROVE LOADED CLAUDE TOKEN FINGERPRINT ====="
python3 - "$RUN_DIR/selected_public.txt" <<'PY'
import re, sys, hashlib, subprocess
from pathlib import Path

pub = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
expected = ""
for line in pub.splitlines():
    if line.startswith("selected_fingerprint="):
        expected = line.split("=",1)[1].strip()

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

ok = True
for pid in sorted(set(pids)):
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\x00", b"\n").decode("utf-8","ignore")
    except Exception as e:
        print(f"pid={pid} env_read_error={e}")
        ok = False
        continue
    keys = sorted(set(KEY_RE.findall(raw)))
    if not keys:
        print(f"pid={pid} NO sk-ant key visible")
        ok = False
        continue
    for k in keys:
        got = fp(k)
        verdict = "MATCH" if got == expected else "WRONG"
        print(f"pid={pid} masked={mask(k)} fingerprint={got} expected={expected} verdict={verdict}")
        if got != expected:
            ok = False

print()
print("FINAL_TOKEN_LOAD_VERDICT=" + ("OK" if ok else "CHECK_FAILED"))
PY

echo
echo "============================================================"
echo "DONE"
echo "Report:"
echo "$REPORT"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
