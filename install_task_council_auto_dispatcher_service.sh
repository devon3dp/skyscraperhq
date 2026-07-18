#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
DISPATCHER="$PROJECT/tools/qsb_task_council_gene_pool_dispatcher.py"
SERVICE="$PROJECT/tools/qsb_task_council_auto_dispatcher.py"
RUNNER="$PROJECT/run_task_council_auto_dispatcher.sh"
LOG="$PROJECT/logs/task_council_auto_dispatcher.log"
PIDFILE="$PROJECT/runtime/task_council_auto_dispatcher.pid"
LOCKFILE="$PROJECT/runtime/task_council_auto_dispatcher.lock"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_task_council_auto_dispatcher_service"
REPORT="$RUN_DIR/reports/task_council_auto_dispatcher_service_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$SEND" "$PROJECT/tools" "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — INSTALL TASK COUNCIL AUTO DISPATCHER SERVICE"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Runs Task Council jobs through Brain Router Gene Pool."
echo " - Reads task rules."
echo " - Updates task status."
echo " - Posts result to Town Square."
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
echo "===== 1. BACKUP EXISTING FILES ====="
[ -f "$DISPATCHER" ] && cp -a "$DISPATCHER" "$RUN_DIR/backups/qsb_task_council_gene_pool_dispatcher.py.bak_$STAMP"
[ -f "$SERVICE" ] && cp -a "$SERVICE" "$RUN_DIR/backups/qsb_task_council_auto_dispatcher.py.bak_$STAMP"
[ -f "$RUNNER" ] && cp -a "$RUNNER" "$RUN_DIR/backups/run_task_council_auto_dispatcher.sh.bak_$STAMP"
echo "[OK] backups done"

echo
echo "===== 2. WRITE AUTO DISPATCHER SERVICE ====="

cat > "$SERVICE" <<'PY'
#!/usr/bin/env python3
import json
import os
import sys
import time
import fcntl
import signal
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"
RUNTIME = PROJECT / "runtime"

LOG_JSONL = REG / "qsb_task_council_auto_dispatcher_events.jsonl"
STATE_JSON = REG / "qsb_task_council_auto_dispatcher_state.json"
PIDFILE = RUNTIME / "task_council_auto_dispatcher.pid"
LOCKFILE = RUNTIME / "task_council_auto_dispatcher.lock"

BASE = "http://127.0.0.1:8852"
INTERVAL_SECONDS = int(os.environ.get("TASK_COUNCIL_INTERVAL", "60"))
MAX_PER_CYCLE = int(os.environ.get("TASK_COUNCIL_MAX_PER_CYCLE", "2"))
DRY_RUN = os.environ.get("TASK_COUNCIL_DRY_RUN", "0") == "1"

STOP = False

DOCTRINE = {
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

def task_id(t):
    return str(t.get("id") or t.get("task_id") or t.get("uid") or "")

def task_state(t):
    return str(t.get("state") or t.get("status") or "").lower()

def task_text(t):
    parts = []
    for k in ("title", "task", "description", "body", "text", "name"):
        v = t.get(k)
        if v:
            parts.append(str(v))
    return "\n".join(parts).strip()

def read_rules():
    r = http_get("/task_rules", timeout=25)
    if r["ok"]:
        return r["data"]
    return {"rules_unavailable": r}

def read_tasks():
    r = http_get("/tasks/data", timeout=35)
    if not r["ok"]:
        return r, []
    data = r["data"]
    tasks = []
    if isinstance(data, dict):
        if isinstance(data.get("tasks"), list):
            tasks = data["tasks"]
        elif isinstance(data.get("items"), list):
            tasks = data["items"]
    elif isinstance(data, list):
        tasks = data
    return r, tasks

def classify_task(text):
    low = text.lower()
    if any(x in low for x in ["code", "script", "python", "bash", "bug", "traceback", "compile", "patch", "repair", "fix"]):
        return "coding"
    if any(x in low for x in ["summarise", "summarize", "summary", "recap", "report", "state", "status"]):
        return "summary"
    if any(x in low for x in ["cheap", "cost", "token", "quota", "fast", "budget"]):
        return "cheap"
    if any(x in low for x in ["architecture", "design", "rulebook", "rule book", "kernel", "system", "council", "brain router", "strategy", "policy"]):
        return "architecture"
    return "default"

def choose_ceo(task_type):
    if task_type == "coding":
        return "CEO 2"
    if task_type == "summary":
        return "CEO 3"
    if task_type == "architecture":
        return "Claude HQ"
    if task_type == "cheap":
        return "Claude HQ"
    return "CEO 2"

def is_dispatchable(t):
    tid = task_id(t)
    text = task_text(t)
    state = task_state(t)

    if not tid or not text:
        return False

    low = text.lower()

    # Never let the autonomous worker re-run smoke tasks forever.
    if "smoke ·" in low or "smoke task" in low or "post-leak-fix smoke" in low:
        return False

    # Avoid dangerous task categories.
    danger = [
        "live trading",
        "place order",
        "real order",
        "send money",
        "withdraw",
        "delete keys",
        "print api key",
        "show secret",
        "disable wren",
        "use wren fallback",
    ]
    if any(x in low for x in danger):
        return False

    # Accept open-ish states. Some Boardroom tasks use custom states.
    if state in {"done", "complete", "completed", "closed", "blocked"}:
        return False

    return True

def post_town(text):
    payloads = [
        {"from": "Task Council Auto Dispatcher", "to": "council", "text": text, "message": text, "src": "task_council_auto_dispatcher"},
        {"speaker": "Task Council Auto Dispatcher", "target": "council", "text": text, "message": text, "source": "task_council_auto_dispatcher"},
    ]
    last = None
    for payload in payloads:
        last = http_post("/town/post", payload, timeout=25)
        if last["ok"]:
            return last
    return last

def update_task(tid, result_text, state="done"):
    payloads = [
        ("/tasks/update", {"id": tid, "status": state, "state": state, "result": result_text, "note": result_text, "updated_by": "task_council_auto_dispatcher"}),
        ("/tasks/done", {"id": tid, "result": result_text, "completed_by": "task_council_auto_dispatcher"}),
        ("/tasks/complete", {"id": tid, "result": result_text, "completed_by": "task_council_auto_dispatcher"}),
        ("/tasks/note", {"id": tid, "note": result_text, "from": "task_council_auto_dispatcher"}),
    ]
    attempts = []
    for path, payload in payloads:
        r = http_post(path, payload, timeout=25)
        attempts.append({"path": path, "ok": r.get("ok"), "http": r.get("http"), "error": r.get("error", "")[:200]})
        if r["ok"]:
            return {"ok": True, "path": path, "response": r, "attempts": attempts}
    return {"ok": False, "attempts": attempts}

def submit_gene_pool(t, rules):
    tid = task_id(t)
    text = task_text(t)
    task_type = classify_task(text)
    ceo = choose_ceo(task_type)

    rules_hint = ""
    try:
        if isinstance(rules, dict) and isinstance(rules.get("rules"), list):
            top = rules["rules"][:5]
            rules_hint = "\n".join([f"- {x.get('id','RULE')}: {x.get('name','')}: {x.get('text','')[:220]}" for x in top if isinstance(x, dict)])
    except Exception:
        rules_hint = ""

    ask = (
        f"Task Council autonomous job {tid}.\n"
        f"Task type: {task_type}.\n"
        f"Original task:\n{text}\n\n"
        f"Relevant rulebook extract:\n{rules_hint}\n\n"
        "Complete this as a safe SkyscraperHQ executive task. "
        "Return a clear result suitable for writing back to Task Council. "
        "Do not use Wren/local GPU fallback. Do not change keys. Do not touch trading. "
        "If the task requires dangerous execution, refuse safely and explain."
    )

    payload = {
        "ceo": ceo,
        "task": task_type,
        "ask": ask,
        "source": "task_council_auto_dispatcher",
        "task_id": tid,
    }
    r = http_post("/proxy/gene_pool/api/submit_job", payload, timeout=75)
    return r, ceo, task_type, ask

def dispatch_one(t, rules):
    tid = task_id(t)
    text = task_text(t)

    log_event("dispatch_start", task_id=tid, task_preview=text[:240])

    if DRY_RUN:
        result = f"DRY RUN: would dispatch task {tid}."
        log_event("dry_run", task_id=tid, result=result)
        return {"ok": True, "dry_run": True, "task_id": tid, "result": result}

    r, ceo, task_type, ask = submit_gene_pool(t, rules)
    if not r["ok"]:
        result = f"Task {tid} failed Gene Pool route: {r.get('error') or r.get('raw') or r}"
        update = update_task(tid, result, state="blocked")
        town = post_town("⚠️ Task Council Auto Dispatcher blocked task " + tid + ": " + result[:600])
        out = {"ok": False, "task_id": tid, "ceo": ceo, "task_type": task_type, "gene_pool": r, "task_update": update, "town": town}
        log_event("dispatch_failed", **out)
        return out

    data = r.get("data", {})
    decision = data.get("decision", {})
    reply = data.get("reply") or decision.get("provider_reply") or json.dumps(data)[:1000]
    provider = decision.get("selected_label") or decision.get("selected_provider") or "unknown"

    result = (
        f"Task Council Auto Dispatcher completed task.\n"
        f"Task ID: {tid}\n"
        f"CEO: {ceo}\n"
        f"Task type: {task_type}\n"
        f"Provider: {provider}\n"
        f"Reply: {reply}\n"
        "Doctrine: Wren protected; CEOs used API Gene Pool only; no key changes; no trading."
    )

    update = update_task(tid, result, state="done")
    town = post_town(f"✅ Auto Dispatcher completed Task {tid} → {ceo} → {provider}. Type={task_type}. Wren protected; API Gene Pool only.")

    out = {
        "ok": True,
        "task_id": tid,
        "ceo": ceo,
        "task_type": task_type,
        "provider": provider,
        "gene_pool_http": r.get("http"),
        "task_update_ok": update.get("ok"),
        "task_update_path": update.get("path"),
        "town_ok": town.get("ok"),
        "result": result,
    }
    log_event("dispatch_complete", **out)
    return out

def cycle_once():
    cycle_ts = now()
    rules = read_rules()
    task_read, tasks = read_tasks()

    state = {
        "ts": cycle_ts,
        "ok": False,
        "doctrine": DOCTRINE,
        "task_read_ok": task_read.get("ok"),
        "task_count": len(tasks),
        "dispatchable_count": 0,
        "processed": [],
        "errors": [],
        "interval_seconds": INTERVAL_SECONDS,
        "max_per_cycle": MAX_PER_CYCLE,
        "dry_run": DRY_RUN,
    }

    if not task_read.get("ok"):
        state["errors"].append({"task_read": task_read})
        write_json(STATE_JSON, state)
        log_event("cycle_failed_task_read", error=task_read)
        return state

    candidates = [t for t in tasks if is_dispatchable(t)]
    state["dispatchable_count"] = len(candidates)

    for t in candidates[:MAX_PER_CYCLE]:
        try:
            res = dispatch_one(t, rules)
            state["processed"].append(res)
        except Exception as e:
            err = {"task_id": task_id(t), "error": repr(e)}
            state["errors"].append(err)
            log_event("dispatch_exception", **err)

    state["ok"] = True
    write_json(STATE_JSON, state)
    log_event("cycle_complete", processed=len(state["processed"]), dispatchable_count=state["dispatchable_count"], errors=len(state["errors"]))
    return state

def stop_handler(signum, frame):
    global STOP
    STOP = True
    log_event("stop_signal", signal=signum)

def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    REG.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    with LOCKFILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another Task Council Auto Dispatcher is already running.", flush=True)
            return 0

        log_event("service_start", pid=os.getpid(), interval=INTERVAL_SECONDS, max_per_cycle=MAX_PER_CYCLE, dry_run=DRY_RUN)

        # Run immediately, then interval.
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

chmod +x "$SERVICE"
echo "[OK] wrote $SERVICE"

echo
echo "===== 3. WRITE RUNNER ====="

cat > "$RUNNER" <<'SH'
#!/usr/bin/env bash
set -u
PROJECT="/vaults/nvme0/qsb_tower_v1"
SERVICE="$PROJECT/tools/qsb_task_council_auto_dispatcher.py"
LOG="$PROJECT/logs/task_council_auto_dispatcher.log"
PIDFILE="$PROJECT/runtime/task_council_auto_dispatcher.pid"

mkdir -p "$PROJECT/logs" "$PROJECT/runtime" "$PROJECT/data/registries"

cd "$PROJECT" || exit 1
ulimit -n 65535
export MALLOC_ARENA_MAX=2
export TASK_COUNCIL_INTERVAL="${TASK_COUNCIL_INTERVAL:-60}"
export TASK_COUNCIL_MAX_PER_CYCLE="${TASK_COUNCIL_MAX_PER_CYCLE:-2}"
export TASK_COUNCIL_DRY_RUN="${TASK_COUNCIL_DRY_RUN:-0}"

if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    echo "[OK] already running pid=$OLD"
    exit 0
  fi
fi

nohup python3 -u "$SERVICE" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] Task Council Auto Dispatcher started pid=$PID"
echo "[OK] Log: $LOG"
SH

chmod +x "$RUNNER"
echo "[OK] wrote $RUNNER"

echo
echo "===== 4. COMPILE ====="
python3 -m py_compile "$SERVICE" && echo "[OK] auto dispatcher compiles" || exit 2

echo
echo "===== 5. STOP OLD AUTO DISPATCHER IF PRESENT ====="
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    kill "$OLD" 2>/dev/null || true
  fi
fi
pkill -f "qsb_task_council_auto_dispatcher.py" 2>/dev/null || true
sleep 2

echo
echo "===== 6. START AUTO DISPATCHER ====="
TASK_COUNCIL_INTERVAL=60 TASK_COUNCIL_MAX_PER_CYCLE=2 TASK_COUNCIL_DRY_RUN=0 "$RUNNER"

echo
echo "===== 7. WAIT FOR FIRST CYCLE ====="
sleep 8

echo
echo "===== 8. SERVICE STATUS ====="
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  echo "PID: $PID"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[OK] running"
    grep -i "Max open files" "/proc/$PID/limits" 2>/dev/null || true
    echo -n "Open FD count: "
    ls "/proc/$PID/fd" 2>/dev/null | wc -l || true
  else
    echo "[FAIL] pid not running"
  fi
fi

echo
echo "===== 9. AUTO DISPATCHER LOG TAIL ====="
tail -n 80 "$LOG" || true

echo
echo "===== 10. STATE FILE ====="
STATE="$PROJECT/data/registries/qsb_task_council_auto_dispatcher_state.json"
if [ -f "$STATE" ]; then
  cp -a "$STATE" "$RUN_DIR/reports/auto_dispatcher_state.json"
  python3 -m json.tool "$STATE" | head -n 220
else
  echo "[WARN] state file missing"
fi

echo
echo "===== 11. HEALTH SNAPSHOT ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/task_rules" \
  "http://127.0.0.1:8852/town_square_feed" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 35 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 260 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 12. URLS ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Boardroom iPad:"
echo "http://${LAN_IP:-127.0.0.1}:8852/ipad"
echo
echo "Task Council:"
echo "http://${LAN_IP:-127.0.0.1}:8852/tasks"
echo
echo "Town Square:"
echo "http://${LAN_IP:-127.0.0.1}:8852/town_square"
echo
echo "Gene Pool through Boardroom:"
echo "http://${LAN_IP:-127.0.0.1}:8852/proxy/gene_pool"

echo
echo "============================================================"
echo "DONE — TASK COUNCIL AUTO DISPATCHER SERVICE INSTALLED"
echo "Runner:"
echo "$RUNNER"
echo "Log:"
echo "$LOG"
echo "State:"
echo "$STATE"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
[ -f "$STATE" ] && cp -a "$STATE" "$SEND/auto_dispatcher_state.json"
