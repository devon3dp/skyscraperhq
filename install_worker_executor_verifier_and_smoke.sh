#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
WORKER="$PROJECT/tools/qsb_worker_executor_verifier.py"
RUNNER="$PROJECT/run_worker_executor_verifier.sh"
LOG="$PROJECT/logs/worker_executor_verifier.log"
PIDFILE="$PROJECT/runtime/worker_executor_verifier.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_worker_executor_verifier"
REPORT="$RUN_DIR/reports/worker_executor_verifier_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/tools" "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/data/worker_artifacts"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — WORKER EXECUTOR + VERIFIER"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Executor may only complete tasks it actually implements."
echo " - Verifier must smoke-test before done."
echo " - Unknown/unsafe tasks are marked needs_implementation, not done."
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects GPU."
echo " - CEOs use API Gene Pool only."
echo " - No Wren/local GPU fallback for CEO thinking."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. BACKUP EXISTING WORKER ====="
[ -f "$WORKER" ] && cp -a "$WORKER" "$RUN_DIR/backups/qsb_worker_executor_verifier.py.bak_$STAMP"
[ -f "$RUNNER" ] && cp -a "$RUNNER" "$RUN_DIR/backups/run_worker_executor_verifier.sh.bak_$STAMP"
echo "[OK] backups done"

echo
echo "===== 2. WRITE WORKER EXECUTOR + VERIFIER ====="

cat > "$WORKER" <<'PY'
#!/usr/bin/env python3
import json
import os
import time
import fcntl
import signal
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"
ART = PROJECT / "data" / "worker_artifacts"
RUNTIME = PROJECT / "runtime"

LOG_JSONL = REG / "qsb_worker_executor_verifier_events.jsonl"
STATE_JSON = REG / "qsb_worker_executor_verifier_state.json"
PIDFILE = RUNTIME / "worker_executor_verifier.pid"
LOCKFILE = RUNTIME / "worker_executor_verifier.lock"

BASE = "http://127.0.0.1:8852"
INTERVAL_SECONDS = int(os.environ.get("WORKER_EXECUTOR_INTERVAL", "60"))
MAX_PER_CYCLE = int(os.environ.get("WORKER_EXECUTOR_MAX_PER_CYCLE", "1"))
DRY_RUN = os.environ.get("WORKER_EXECUTOR_DRY_RUN", "0") == "1"

STOP = False

DOCTRINE = {
    "worker_truth_gate": "implementation plus verification required before done",
    "claude_hq_name": "Claude HQ",
    "wren": "protected GPU guardian",
    "ceos": "API Gene Pool only",
    "no_local_fallback": True,
    "no_key_changes": True,
    "no_trading": True,
}

def now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def log_event(event, **kwargs):
    REG.mkdir(parents=True, exist_ok=True)
    obj = {"ts": now(), "event": event, **kwargs}
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)

def http_get(path, timeout=35):
    url = BASE + path
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:2000]}
            return {"ok": 200 <= r.status < 300, "http": r.status, "data": data, "raw": raw[:2000], "url": url}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return {"ok": False, "http": e.code, "error": raw[:2000], "url": url}
    except Exception as e:
        return {"ok": False, "http": 0, "error": repr(e), "url": url}

def http_post(path, payload, timeout=60):
    url = BASE + path
    raw = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                data = {"raw": body[:2000]}
            return {"ok": 200 <= r.status < 300, "http": r.status, "data": data, "raw": body[:2000], "url": url}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return {"ok": False, "http": e.code, "error": body[:2000], "url": url}
    except Exception as e:
        return {"ok": False, "http": 0, "error": repr(e), "url": url}

def post_town(text):
    payload = {
        "from": "Worker Executor + Verifier",
        "to": "council",
        "text": text,
        "message": text,
        "src": "worker_executor_verifier",
    }
    return http_post("/town/post", payload, timeout=25)

def update_task(tid, state, result):
    payload = {
        "id": tid,
        "status": state,
        "state": state,
        "result": result,
        "note": result,
        "updated_by": "worker_executor_verifier",
    }
    return http_post("/tasks/update", payload, timeout=25)

def task_id(t):
    return str(t.get("id") or t.get("task_id") or t.get("uid") or "")

def task_state(t):
    return str(t.get("state") or t.get("status") or "").lower()

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

def is_safe_worker_task(t):
    tid = task_id(t)
    text = task_text(t)
    low = text.lower()
    state = task_state(t)

    if not tid or not text:
        return False

    if state in {"done", "complete", "completed", "closed", "blocked", "verified_done"}:
        return False

    dangerous = [
        "live trading",
        "place order",
        "real order",
        "withdraw",
        "delete keys",
        "print api key",
        "show secret",
        "disable wren",
        "use wren fallback",
        "rm -rf",
        "format disk",
        "send money",
    ]
    if any(x in low for x in dangerous):
        return False

    # This worker only auto-implements controlled proof/artifact tasks for now.
    # Real code/dashboard tasks are routed to needs_implementation unless later given a safe executor plugin.
    if "worker executor smoke proof" in low:
        return True

    return False

def is_routed_but_not_executable(t):
    state = task_state(t)
    if state not in {"routed_for_work", "open", "awaiting", "in_progress"}:
        return False
    return not is_safe_worker_task(t)

def create_proof_artifact(t):
    tid = task_id(t)
    ART.mkdir(parents=True, exist_ok=True)

    proof = {
        "task_id": tid,
        "implemented_by": "worker_executor",
        "verified_by": "worker_verifier",
        "ts": now(),
        "doctrine": DOCTRINE,
        "proof": "This controlled smoke task was actually implemented by writing this artifact, then verified by checking it exists and contains the correct task_id.",
    }

    path = ART / f"worker_executor_verified_{tid}.json"
    write_json(path, proof)
    return path

def verify_proof_artifact(path, tid):
    if not path.exists():
        return {"ok": False, "reason": "artifact missing", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "reason": repr(e), "path": str(path)}
    if data.get("task_id") != tid:
        return {"ok": False, "reason": "task_id mismatch", "path": str(path)}
    return {"ok": True, "path": str(path), "artifact": data}

def execute_and_verify(t):
    tid = task_id(t)
    text = task_text(t)
    log_event("execute_start", task_id=tid, preview=text[:240])

    if DRY_RUN:
        return {"ok": True, "task_id": tid, "dry_run": True}

    path = create_proof_artifact(t)
    verification = verify_proof_artifact(path, tid)

    if verification["ok"]:
        result = (
            f"Worker Executor + Verifier completed controlled task.\n"
            f"Task ID: {tid}\n"
            f"Artifact: {path}\n"
            f"Verifier: passed\n"
            "Truth gate: actual artifact was created and verified before marking done.\n"
            "Doctrine: no key changes; no Wren fallback; no trading."
        )
        update = update_task(tid, "done", result)
        town = post_town(f"✅ Worker Executor + Verifier completed and verified Task {tid}. Artifact: {path}")
        out = {
            "ok": True,
            "task_id": tid,
            "artifact": str(path),
            "verification": verification,
            "task_update_ok": update.get("ok"),
            "town_ok": town.get("ok"),
            "result": result,
        }
        log_event("execute_verified_done", **out)
        return out

    result = (
        f"Worker Executor attempted task {tid}, but verifier failed.\n"
        f"Verification: {verification}"
    )
    update = update_task(tid, "verification_failed", result)
    town = post_town(f"⚠️ Worker verifier failed Task {tid}. Not marked done.")
    out = {
        "ok": False,
        "task_id": tid,
        "verification": verification,
        "task_update_ok": update.get("ok"),
        "town_ok": town.get("ok"),
        "result": result,
    }
    log_event("execute_verification_failed", **out)
    return out

def mark_needs_implementation(t):
    tid = task_id(t)
    text = task_text(t)

    result = (
        f"Worker Executor inspected task {tid}.\n"
        "Status: needs_implementation.\n"
        "Reason: this worker can only mark done after a real implementation and verifier smoke test. "
        "This task requires a specific executor plugin or direct implementation script.\n"
        f"Task preview: {text[:800]}"
    )

    update = update_task(tid, "needs_implementation", result)
    town = post_town(f"🧱 Task {tid} needs a real implementation worker/plugin before it can be marked done.")
    out = {
        "ok": True,
        "task_id": tid,
        "state": "needs_implementation",
        "task_update_ok": update.get("ok"),
        "town_ok": town.get("ok"),
    }
    log_event("needs_implementation", **out)
    return out

def cycle_once():
    task_read, tasks = read_tasks()
    state = {
        "ts": now(),
        "ok": False,
        "task_read_ok": task_read.get("ok"),
        "task_count": len(tasks),
        "executed": [],
        "needs_implementation": [],
        "errors": [],
        "dry_run": DRY_RUN,
        "interval_seconds": INTERVAL_SECONDS,
        "max_per_cycle": MAX_PER_CYCLE,
        "doctrine": DOCTRINE,
    }

    if not task_read.get("ok"):
        state["errors"].append(task_read)
        write_json(STATE_JSON, state)
        log_event("cycle_failed_task_read", error=task_read)
        return state

    safe = [t for t in tasks if is_safe_worker_task(t)]
    routed = [t for t in tasks if is_routed_but_not_executable(t)]

    for t in safe[:MAX_PER_CYCLE]:
        try:
            state["executed"].append(execute_and_verify(t))
        except Exception as e:
            err = {"task_id": task_id(t), "error": repr(e)}
            state["errors"].append(err)
            log_event("execute_exception", **err)

    # Mark only one non-executable routed task per cycle, so we do not spam the board.
    if not state["executed"] and routed:
        try:
            state["needs_implementation"].append(mark_needs_implementation(routed[0]))
        except Exception as e:
            err = {"task_id": task_id(routed[0]), "error": repr(e)}
            state["errors"].append(err)
            log_event("needs_implementation_exception", **err)

    state["ok"] = True
    write_json(STATE_JSON, state)
    log_event("cycle_complete", executed=len(state["executed"]), needs_implementation=len(state["needs_implementation"]), errors=len(state["errors"]))
    return state

def stop_handler(signum, frame):
    global STOP
    STOP = True
    log_event("stop_signal", signal=signum)

def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    REG.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    with LOCKFILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another Worker Executor + Verifier is already running.", flush=True)
            return 0

        log_event("service_start", pid=os.getpid(), interval=INTERVAL_SECONDS, max_per_cycle=MAX_PER_CYCLE, dry_run=DRY_RUN)

        while not STOP:
            cycle_once()
            for _ in range(INTERVAL_SECONDS):
                if STOP:
                    break
                time.sleep(1)

        log_event("service_stop", pid=os.getpid())
        return 0

if __name__ == "__main__":
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
WORKER="$PROJECT/tools/qsb_worker_executor_verifier.py"
LOG="$PROJECT/logs/worker_executor_verifier.log"
PIDFILE="$PROJECT/runtime/worker_executor_verifier.pid"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries" "$PROJECT/data/worker_artifacts"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
export WORKER_EXECUTOR_INTERVAL="${WORKER_EXECUTOR_INTERVAL:-60}"
export WORKER_EXECUTOR_MAX_PER_CYCLE="${WORKER_EXECUTOR_MAX_PER_CYCLE:-1}"
export WORKER_EXECUTOR_DRY_RUN="${WORKER_EXECUTOR_DRY_RUN:-0}"

if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "[OK] already running pid=$OLD"
    exit 0
  fi
fi

nohup python3 -u "$WORKER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] Worker Executor + Verifier started pid=$PID"
echo "[OK] Log: $LOG"
SH

chmod +x "$RUNNER"
echo "[OK] wrote $RUNNER"

echo
echo "===== 4. COMPILE WORKER ====="
python3 -m py_compile "$WORKER" && echo "[OK] worker compiles" || exit 2

echo
echo "===== 5. CREATE CONTROLLED WORKER SMOKE TASK ====="
python3 - <<'PY'
import json, urllib.request

payload = {
    "title": "WORKER EXECUTOR SMOKE PROOF",
    "description": "Worker Executor Smoke Proof: create a verified proof artifact, verify it exists, then and only then mark this task done.",
    "task": "Worker Executor Smoke Proof: create a verified proof artifact, verify it exists, then and only then mark this task done.",
    "created_by": "worker_executor_verifier_installer",
    "status": "open",
    "state": "open",
    "tags": ["worker_executor", "verifier", "smoke"],
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8852/tasks/create", data=data, headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=25) as r:
    print("http", r.status)
    print(r.read().decode("utf-8", "replace"))
PY

echo
echo "===== 6. STOP OLD WORKER IF PRESENT ====="
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    kill "$OLD" 2>/dev/null || true
  fi
fi
pkill -f "qsb_worker_executor_verifier.py" 2>/dev/null || true
sleep 2

echo
echo "===== 7. START WORKER ====="
WORKER_EXECUTOR_INTERVAL=60 WORKER_EXECUTOR_MAX_PER_CYCLE=1 WORKER_EXECUTOR_DRY_RUN=0 "$RUNNER"

echo
echo "===== 8. WAIT FOR FIRST CYCLE ====="
sleep 10

echo
echo "===== 9. WORKER STATUS ====="
PID="$(cat "$PIDFILE" 2>/dev/null || true)"
echo "PID: $PID"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "[OK] running"
  grep -i "Max open files" "/proc/$PID/limits" 2>/dev/null || true
  echo -n "Open FD count: "
  ls "/proc/$PID/fd" 2>/dev/null | wc -l || true
else
  echo "[FAIL] worker not running"
fi

echo
echo "===== 10. WORKER LOG TAIL ====="
tail -n 100 "$LOG" || true

echo
echo "===== 11. WORKER STATE ====="
STATE="$PROJECT/data/registries/qsb_worker_executor_verifier_state.json"
if [ -f "$STATE" ]; then
  cp -a "$STATE" "$RUN_DIR/reports/worker_executor_verifier_state.json"
  python3 -m json.tool "$STATE" | head -n 220
else
  echo "[WARN] state missing"
fi

echo
echo "===== 12. ARTIFACTS ====="
find "$PROJECT/data/worker_artifacts" -maxdepth 1 -type f -name 'worker_executor_verified_*.json' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | tail -n 10 || true

echo
echo "===== 13. HEALTH SNAPSHOT ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/town_square_feed" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 35 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
done

echo
echo "===== 14. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
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
echo "DONE — WORKER EXECUTOR + VERIFIER INSTALLED"
echo "Runner:"
echo "$RUNNER"
echo "Log:"
echo "$LOG"
echo "State:"
echo "$STATE"
echo "Artifacts:"
echo "$PROJECT/data/worker_artifacts"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
[ -f "$STATE" ] && cp -a "$STATE" "$SEND/worker_executor_verifier_state.json"
