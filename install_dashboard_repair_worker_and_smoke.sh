#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
WORKER="$PROJECT/tools/qsb_dashboard_repair_worker.py"
RUNNER="$PROJECT/run_dashboard_repair_worker.sh"
BOARDROOM="$PROJECT/tools/qsb_boardroom_hub.py"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"
AUTO_LOG="$PROJECT/logs/task_council_auto_dispatcher.log"
ART="$PROJECT/data/worker_artifacts"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_dashboard_repair_worker"
REPORT="$RUN_DIR/reports/dashboard_repair_worker_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/tools" "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$ART"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — EXECUTOR PLUGIN 1: DASHBOARD REPAIR WORKER"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Actually patch dashboard code before marking done."
echo " - Verify with compile + HTTP smoke before done."
echo " - Create repair artifact."
echo " - Post to Town Square."
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects GPU."
echo " - CEOs use API Gene Pool only."
echo " - No Wren/local GPU fallback for CEO thinking."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$BOARDROOM" ]; then
  echo "[FAIL] Missing Boardroom file: $BOARDROOM"
  exit 1
fi

echo
echo "===== 1. BACKUP EXISTING FILES ====="
cp -a "$BOARDROOM" "$RUN_DIR/backups/qsb_boardroom_hub.py.before_dashboard_repair_$STAMP"
[ -f "$WORKER" ] && cp -a "$WORKER" "$RUN_DIR/backups/qsb_dashboard_repair_worker.py.bak_$STAMP"
[ -f "$RUNNER" ] && cp -a "$RUNNER" "$RUN_DIR/backups/run_dashboard_repair_worker.sh.bak_$STAMP"
echo "[OK] backups done"

echo
echo "===== 2. WRITE DASHBOARD REPAIR WORKER ====="

cat > "$WORKER" <<'PY'
#!/usr/bin/env python3
import json
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
BOARDROOM = PROJECT / "tools" / "qsb_boardroom_hub.py"
BOARDROOM_LOG = PROJECT / "logs" / "boardroom_hub_8852.log"
REG = PROJECT / "data" / "registries"
ART = PROJECT / "data" / "worker_artifacts"
EVENTS = REG / "qsb_dashboard_repair_worker_events.jsonl"
STATE = REG / "qsb_dashboard_repair_worker_state.json"

BASE = "http://127.0.0.1:8852"

DOCTRINE = {
    "worker": "dashboard_repair_worker",
    "truth_gate": "patch + compile + restart + endpoint verification before done",
    "claude_hq_name": "Claude HQ",
    "wren": "protected GPU guardian",
    "ceos": "API Gene Pool only",
    "no_local_fallback": True,
    "no_key_changes": True,
    "no_trading": True,
}

def now():
    return datetime.now(timezone.utc).isoformat()

def log_event(event, **kwargs):
    REG.mkdir(parents=True, exist_ok=True)
    obj = {"ts": now(), "event": event, **kwargs}
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def http_get(path, timeout=30):
    url = BASE + path
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:4000]}
            return {"ok": 200 <= r.status < 300, "http": r.status, "data": data, "raw": raw[:4000], "url": url}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return {"ok": False, "http": e.code, "error": raw[:4000], "url": url}
    except Exception as e:
        return {"ok": False, "http": 0, "error": repr(e), "url": url}

def http_post(path, payload, timeout=40):
    url = BASE + path
    raw = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                data = {"raw": body[:4000]}
            return {"ok": 200 <= r.status < 300, "http": r.status, "data": data, "raw": body[:4000], "url": url}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return {"ok": False, "http": e.code, "error": body[:4000], "url": url}
    except Exception as e:
        return {"ok": False, "http": 0, "error": repr(e), "url": url}

def task_id(t):
    return str(t.get("id") or t.get("task_id") or t.get("uid") or "")

def task_text(t):
    parts = []
    for k in ("title", "task", "description", "body", "text", "name", "result", "note"):
        v = t.get(k)
        if v:
            parts.append(str(v))
    return "\n".join(parts).strip()

def read_tasks():
    r = http_get("/tasks/data", timeout=35)
    if not r["ok"]:
        return r, []
    data = r["data"]
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return r, data["tasks"]
    if isinstance(data, list):
        return r, data
    return r, []

def post_town(text):
    return http_post("/town/post", {
        "from": "Dashboard Repair Worker",
        "to": "council",
        "text": text,
        "message": text,
        "src": "dashboard_repair_worker",
    }, timeout=25)

def update_task(tid, state, result):
    return http_post("/tasks/update", {
        "id": tid,
        "status": state,
        "state": state,
        "result": result,
        "note": result,
        "updated_by": "dashboard_repair_worker",
    }, timeout=25)

def create_smoke_task():
    payload = {
        "title": "DASHBOARD REPAIR SMOKE · team_live identity bug",
        "description": "Dashboard Repair Worker smoke: fix /team_live chat identity so Ross messages do not hardcode as hq_claude. Patch, compile, restart, verify, then mark done.",
        "task": "Dashboard Repair Worker smoke: fix /team_live chat identity so Ross messages do not hardcode as hq_claude. Patch, compile, restart, verify, then mark done.",
        "created_by": "dashboard_repair_worker_installer",
        "status": "open",
        "state": "open",
        "tags": ["dashboard_repair", "team_live", "identity", "smoke"],
    }
    return http_post("/tasks/create", payload, timeout=25)

def find_team_live_identity_task(tasks):
    preferred = []
    fallback = []

    for t in tasks:
        txt = task_text(t).lower()
        tid = task_id(t)
        state = str(t.get("state") or t.get("status") or "").lower()

        if not tid:
            continue

        if "team_live" in txt and "identity" in txt and "hq_claude" in txt:
            preferred.append(t)
        elif "dashboard repair smoke" in txt and "team_live" in txt:
            preferred.append(t)
        elif "ross posts appear as hq_claude" in txt:
            preferred.append(t)
        elif "sendchat" in txt and "hq_claude" in txt:
            fallback.append(t)

    # Prefer non-done, but allow done if we are repairing actual code anyway.
    def score(t):
        state = str(t.get("state") or t.get("status") or "").lower()
        return 0 if state not in {"done", "complete", "completed", "closed"} else 1

    chosen = sorted(preferred or fallback, key=score)
    return chosen[0] if chosen else None

def compile_boardroom():
    p = subprocess.run(["python3", "-m", "py_compile", str(BOARDROOM)], capture_output=True, text=True, timeout=30)
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": p.stdout[-2000:],
        "stderr": p.stderr[-4000:],
    }

def restart_boardroom():
    subprocess.run("pkill -f 'tools/qsb_boardroom_hub.py.*--port 8852' || true", shell=True)
    subprocess.run("pkill -f 'qsb_boardroom_hub.py.*8852' || true", shell=True)
    time_script = """
cd /vaults/nvme0/qsb_tower_v1 || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
nohup python3 -u tools/qsb_boardroom_hub.py --port 8852 >> logs/boardroom_hub_8852.log 2>&1 &
echo $! > runtime/boardroom_hub_8852.pid
"""
    subprocess.run(["bash", "-lc", time_script], timeout=10)
    return wait_for_boardroom()

def wait_for_boardroom():
    for _ in range(40):
        r = http_get("/ipad", timeout=3)
        if r["ok"]:
            return {"ok": True, "http": r["http"]}
        time.sleep(0.5)
    return {"ok": False, "reason": "boardroom did not answer /ipad"}

def patch_team_live_identity():
    before = BOARDROOM.read_text(errors="ignore")
    before_count = len(re.findall(r'say\(\s*[\'"]hq_claude[\'"]\s*,\s*text\s*\)', before))

    patched = before

    # Main bug: TEAM_LIVE_HTML sendChat() hardcoded say("hq_claude", text).
    patched = re.sub(
        r'say\(\s*[\'"]hq_claude[\'"]\s*,\s*text\s*\)',
        "say((localStorage.getItem('qsb_team_live_speaker') || 'ross'), text)",
        patched,
    )

    # Extra safety for variants with variable msg/text2 names is intentionally conservative.
    # We do not touch backend identity handling here, only the visible browser sendChat hardcode.

    changed = patched != before
    if changed:
        BOARDROOM.write_text(patched, encoding="utf-8")

    after = BOARDROOM.read_text(errors="ignore")
    after_count = len(re.findall(r'say\(\s*[\'"]hq_claude[\'"]\s*,\s*text\s*\)', after))

    return {
        "changed": changed,
        "before_hardcode_count": before_count,
        "after_hardcode_count": after_count,
    }

def verify_team_live_identity():
    checks = {}

    team = http_get("/team_live", timeout=25)
    checks["team_live_http"] = {"ok": team["ok"], "http": team["http"], "url": team["url"]}

    ipad = http_get("/ipad", timeout=20)
    checks["ipad_http"] = {"ok": ipad["ok"], "http": ipad["http"], "url": ipad["url"]}

    data = http_get("/team_live/data", timeout=35)
    checks["team_live_data_http"] = {"ok": data["ok"], "http": data["http"], "url": data["url"]}

    source = BOARDROOM.read_text(errors="ignore")
    hardcode_left = bool(re.search(r'say\(\s*[\'"]hq_claude[\'"]\s*,\s*text\s*\)', source))
    dynamic_present = "qsb_team_live_speaker" in source

    checks["source_hardcode_removed"] = not hardcode_left
    checks["dynamic_speaker_present"] = dynamic_present

    ok = (
        checks["team_live_http"]["ok"]
        and checks["ipad_http"]["ok"]
        and checks["source_hardcode_removed"]
        and checks["dynamic_speaker_present"]
    )

    return {"ok": ok, "checks": checks}

def repair_team_live_identity(task):
    tid = task_id(task)
    text = task_text(task)

    log_event("repair_start", task_id=tid, repair="team_live_identity", preview=text[:240])

    patch = patch_team_live_identity()
    compile_result = compile_boardroom()

    if not compile_result["ok"]:
        result = (
            f"Dashboard Repair Worker failed compile after patch for task {tid}.\n"
            f"Compile stderr:\n{compile_result['stderr']}"
        )
        update_task(tid, "verification_failed", result)
        post_town(f"⚠️ Dashboard repair failed compile for Task {tid}. Not marked done.")
        out = {"ok": False, "task_id": tid, "stage": "compile_failed", "patch": patch, "compile": compile_result}
        log_event("repair_failed", **out)
        return out

    restart = restart_boardroom()
    verify = verify_team_live_identity()

    artifact = {
        "task_id": tid,
        "repair": "team_live_identity",
        "ts": now(),
        "patch": patch,
        "compile": compile_result,
        "restart": restart,
        "verify": verify,
        "doctrine": DOCTRINE,
        "boardroom_file": str(BOARDROOM),
        "truth_gate": "done only if source patched/already clean, compile passed, Boardroom restarted, endpoints verified",
    }

    ART.mkdir(parents=True, exist_ok=True)
    artifact_path = ART / f"dashboard_repair_team_live_identity_{tid}.json"
    write_json(artifact_path, artifact)

    if verify["ok"]:
        result = (
            f"Dashboard Repair Worker completed team_live identity repair.\n"
            f"Task ID: {tid}\n"
            f"Boardroom file: {BOARDROOM}\n"
            f"Patch changed file: {patch['changed']}\n"
            f"Hardcoded say('hq_claude', text) before: {patch['before_hardcode_count']}\n"
            f"Hardcoded say('hq_claude', text) after: {patch['after_hardcode_count']}\n"
            f"Artifact: {artifact_path}\n"
            "Verifier: compile passed; Boardroom restarted; /team_live and /ipad responded; hardcoded sender removed.\n"
            "Truth gate: actual code was patched or verified clean before marking done.\n"
            "Doctrine: no key changes; no Wren fallback; no trading."
        )
        update = update_task(tid, "done", result)
        town = post_town(f"✅ Dashboard Repair Worker completed Task {tid}: /team_live identity hardcode removed/verified. Artifact: {artifact_path}")
        out = {
            "ok": True,
            "task_id": tid,
            "artifact": str(artifact_path),
            "patch": patch,
            "compile_ok": True,
            "verify": verify,
            "task_update_ok": update.get("ok"),
            "town_ok": town.get("ok"),
        }
        log_event("repair_verified_done", **out)
        return out

    result = (
        f"Dashboard Repair Worker patched/checked task {tid}, but verifier failed.\n"
        f"Artifact: {artifact_path}\n"
        f"Verify: {json.dumps(verify, ensure_ascii=False)[:1200]}"
    )
    update = update_task(tid, "verification_failed", result)
    town = post_town(f"⚠️ Dashboard repair verifier failed for Task {tid}. Not marked done. Artifact: {artifact_path}")
    out = {
        "ok": False,
        "task_id": tid,
        "artifact": str(artifact_path),
        "patch": patch,
        "compile_ok": True,
        "verify": verify,
        "task_update_ok": update.get("ok"),
        "town_ok": town.get("ok"),
    }
    log_event("repair_verification_failed", **out)
    return out

def main():
    log_event("worker_start", doctrine=DOCTRINE)

    task_read, tasks = read_tasks()
    if not task_read["ok"]:
        state = {"ok": False, "reason": "tasks_read_failed", "task_read": task_read}
        write_json(STATE, state)
        log_event("worker_failed", **state)
        return 2

    task = find_team_live_identity_task(tasks)

    if not task:
        create = create_smoke_task()
        log_event("created_smoke_task", create=create)
        time.sleep(0.5)
        task_read, tasks = read_tasks()
        task = find_team_live_identity_task(tasks)

    if not task:
        state = {"ok": False, "reason": "no_team_live_identity_task_found"}
        write_json(STATE, state)
        log_event("worker_failed", **state)
        return 3

    result = repair_team_live_identity(task)

    # Whole-system smoke.
    health = {}
    for path in ["/ipad", "/tasks/data", "/town_square_feed", "/team_live", "/team_live/data", "/proxy/gene_pool/api/live"]:
        health[path] = http_get(path, timeout=35)

    state = {
        "ts": now(),
        "ok": bool(result.get("ok")),
        "result": result,
        "health": {k: {"ok": v.get("ok"), "http": v.get("http"), "url": v.get("url")} for k, v in health.items()},
        "doctrine": DOCTRINE,
    }
    write_json(STATE, state)
    log_event("worker_complete", ok=state["ok"], task_id=result.get("task_id"))

    return 0 if state["ok"] else 1

if __name__ == "__main__":
    import time
    raise SystemExit(main())
PY

chmod +x "$WORKER"
echo "[OK] wrote $WORKER"

echo
echo "===== 3. WRITE RUNNER ====="

cat > "$RUNNER" <<'SH'
#!/usr/bin/env bash
set -u
PROJECT="/vaults/nvme0/qsb_tower_v1"
WORKER="$PROJECT/tools/qsb_dashboard_repair_worker.py"
LOG="$PROJECT/logs/dashboard_repair_worker.log"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/data/worker_artifacts"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
python3 -u "$WORKER" | tee -a "$LOG"
SH

chmod +x "$RUNNER"
echo "[OK] wrote $RUNNER"

echo
echo "===== 4. COMPILE WORKER ====="
python3 -m py_compile "$WORKER" && echo "[OK] dashboard repair worker compiles" || exit 2

echo
echo "===== 5. RUN DASHBOARD REPAIR WORKER ====="
"$RUNNER" > "$RUN_DIR/reports/dashboard_repair_worker_run.txt" 2>&1
RC="$?"
cat "$RUN_DIR/reports/dashboard_repair_worker_run.txt"

echo
echo "===== 6. STATE FILE ====="
STATE="$PROJECT/data/registries/qsb_dashboard_repair_worker_state.json"
if [ -f "$STATE" ]; then
  cp -a "$STATE" "$RUN_DIR/reports/dashboard_repair_worker_state.json"
  python3 -m json.tool "$STATE" | head -n 240
else
  echo "[WARN] state missing"
fi

echo
echo "===== 7. ARTIFACTS ====="
find "$ART" -maxdepth 1 -type f -name 'dashboard_repair_team_live_identity_*.json' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | tail -n 10 || true

echo
echo "===== 8. SOURCE VERIFICATION ====="
echo "--- hardcoded sender patterns left ---"
grep -nE "say\([\"']hq_claude[\"'][[:space:]]*,[[:space:]]*text\)" "$BOARDROOM" || true
echo "--- dynamic speaker marker ---"
grep -n "qsb_team_live_speaker" "$BOARDROOM" | head -n 10 || true

echo
echo "===== 9. WHOLE SYSTEM HTTP SMOKE ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/team_live" \
  "http://127.0.0.1:8852/team_live/data" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/town_square_feed" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 35 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 220 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 10. RECENT ERRORS ====="
echo "--- Boardroom log ---"
tail -n 180 "$BOARDROOM_LOG" | grep -Ei "Errno 24|Too many open files|Traceback|Exception|NameError|team_live|identity|dashboard" || true
echo "--- Dashboard repair events ---"
tail -n 80 "$PROJECT/data/registries/qsb_dashboard_repair_worker_events.jsonl" 2>/dev/null || true

echo
echo "===== 11. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Team Live:"
echo "http://${LAN_IP:-127.0.0.1}:8852/team_live"
echo
echo "Tasks:"
echo "http://${LAN_IP:-127.0.0.1}:8852/tasks"
echo
echo "Town Square:"
echo "http://${LAN_IP:-127.0.0.1}:8852/town_square"
echo
echo "Gene Pool:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"

echo
echo "============================================================"
echo "DONE — DASHBOARD REPAIR WORKER SMOKE COMPLETE"
echo "Exit code: $RC"
echo "Runner:"
echo "$RUNNER"
echo "State:"
echo "$STATE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
[ -f "$STATE" ] && cp -a "$STATE" "$SEND/dashboard_repair_worker_state.json"
exit "$RC"
