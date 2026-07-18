#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
SERVICE="$PROJECT/tools/qsb_task_council_auto_dispatcher.py"
RUNNER="$PROJECT/run_task_council_auto_dispatcher.sh"
LOG="$PROJECT/logs/task_council_auto_dispatcher.log"
PIDFILE="$PROJECT/runtime/task_council_auto_dispatcher.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_fix_auto_dispatcher_truth_gate"
REPORT="$RUN_DIR/reports/fix_auto_dispatcher_truth_gate_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/runtime" "$PROJECT/logs" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "FIX AUTO DISPATCHER TRUTH GATE"
echo "Generated: $(date -Is)"
echo "============================================================"
echo "Purpose:"
echo " - Stop premature 'done' marking."
echo " - Reopen tasks that were routed but not truly implemented."
echo " - Restart dispatcher in safe route-only mode."
echo "============================================================"

cd "$PROJECT" || exit 1

echo
echo "===== 1. STOP CURRENT AUTO DISPATCHER ====="
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ]; then
    kill "$OLD" 2>/dev/null || true
    echo "[OK] killed pid $OLD if running"
  fi
fi
pkill -f "qsb_task_council_auto_dispatcher.py" 2>/dev/null || true
sleep 2

echo
echo "===== 2. BACKUP SERVICE ====="
cp -a "$SERVICE" "$RUN_DIR/backups/qsb_task_council_auto_dispatcher.py.before_truth_gate_$STAMP"
echo "[OK] backup written"

echo
echo "===== 3. REOPEN PREMATURELY COMPLETED TASKS ====="
python3 - <<'PY'
import json, urllib.request, urllib.error

BASE="http://127.0.0.1:8852"
tasks = {
    "t_c0743b3659": "Routed by auto dispatcher, but not actually implemented or verified. Reopened for real implementation: live dashboard/Acer visibility still needs work.",
    "t_e85ca2174c": "Routed by auto dispatcher, but not actually implemented or verified. Reopened for real implementation: Wren learning/evolution dashboard metrics still need work.",
}

def post(path, payload):
    data=json.dumps(payload).encode()
    req=urllib.request.Request(BASE+path, data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(path, payload.get("id"), "http", r.status, r.read().decode("utf-8","replace")[:500])
    except urllib.error.HTTPError as e:
        print(path, payload.get("id"), "HTTP_ERROR", e.code, e.read().decode("utf-8","replace")[:500])
    except Exception as e:
        print(path, payload.get("id"), "ERROR", repr(e))

for tid, note in tasks.items():
    post("/tasks/update", {
        "id": tid,
        "status": "open",
        "state": "open",
        "note": note,
        "result": note,
        "updated_by": "truth_gate_fix"
    })
    post("/town/post", {
        "from": "Truth Gate",
        "to": "council",
        "text": f"⚠️ Task {tid} was routed but not truly completed. It has been reopened for real implementation and verification.",
        "message": f"Task {tid} reopened: routed is not the same as complete."
    })
PY

echo
echo "===== 4. PATCH AUTO DISPATCHER TO ROUTE-ONLY TRUTH MODE ====="
python3 - <<'PY'
from pathlib import Path
import re

p=Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_task_council_auto_dispatcher.py")
s=p.read_text(errors="ignore")

# Replace the dangerous update-to-done block in dispatch_one.
old='''    result = (
        f"Task Council Auto Dispatcher completed task.\\n"
        f"Task ID: {tid}\\n"
        f"CEO: {ceo}\\n"
        f"Task type: {task_type}\\n"
        f"Provider: {provider}\\n"
        f"Reply: {reply}\\n"
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
'''

new='''    result = (
        f"Task Council Auto Dispatcher ROUTED task for work.\\n"
        f"Task ID: {tid}\\n"
        f"CEO: {ceo}\\n"
        f"Task type: {task_type}\\n"
        f"Provider: {provider}\\n"
        f"Brain Router reply: {reply}\\n"
        "Truth gate: this is NOT marked complete until a worker implements it and a verifier confirms it.\\n"
        "Doctrine: Wren protected; CEOs used API Gene Pool only; no key changes; no trading."
    )

    update = update_task(tid, result, state="routed_for_work")
    town = post_town(f"📨 Auto Dispatcher routed Task {tid} → {ceo} → {provider}. Type={task_type}. Status=routed_for_work, not complete yet.")

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
        "truth_gate": "routed_not_complete",
        "result": result,
    }
    log_event("dispatch_routed_for_work", **out)
    return out
'''

if old not in s:
    print("[WARN] exact done block not found; applying fallback replacements")
    s=s.replace('f"Task Council Auto Dispatcher completed task.\\\\n"', 'f"Task Council Auto Dispatcher ROUTED task for work.\\\\n"')
    s=s.replace('update = update_task(tid, result, state="done")', 'update = update_task(tid, result, state="routed_for_work")')
    s=s.replace('log_event("dispatch_complete", **out)', 'log_event("dispatch_routed_for_work", **out)')
else:
    s=s.replace(old,new)
    print("[OK] replaced completion block with route-only truth gate")

# Prevent reprocessing already routed tasks.
old_state='''    if state in {"done", "complete", "completed", "closed", "blocked"}:
        return False
'''
new_state='''    if state in {"done", "complete", "completed", "closed", "blocked", "routed_for_work", "routed", "assigned"}:
        return False
'''
s=s.replace(old_state,new_state)

p.write_text(s,encoding="utf-8")
PY

echo
echo "===== 5. COMPILE ====="
python3 -m py_compile "$SERVICE" && echo "[OK] service compiles" || exit 2

echo
echo "===== 6. START SAFER AUTO DISPATCHER ====="
TASK_COUNCIL_INTERVAL=60 TASK_COUNCIL_MAX_PER_CYCLE=1 TASK_COUNCIL_DRY_RUN=0 "$RUNNER"

sleep 8

echo
echo "===== 7. STATUS ====="
PID="$(cat "$PIDFILE" 2>/dev/null || true)"
echo "PID: $PID"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "[OK] running"
  grep -i "Max open files" "/proc/$PID/limits" 2>/dev/null || true
  echo -n "Open FD count: "
  ls "/proc/$PID/fd" 2>/dev/null | wc -l || true
else
  echo "[FAIL] not running"
fi

echo
echo "===== 8. LOG TAIL ====="
tail -n 80 "$LOG" || true

echo
echo "===== 9. STATE ====="
STATE="$PROJECT/data/registries/qsb_task_council_auto_dispatcher_state.json"
if [ -f "$STATE" ]; then
  python3 -m json.tool "$STATE" | head -n 200
fi

echo
echo "===== 10. HEALTH CHECKS ====="
for url in \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/task_rules" \
  "http://127.0.0.1:8852/town_square_feed" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live"
do
  echo "--- $url"
  curl -sS --max-time 30 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
done

echo
echo "============================================================"
echo "DONE — TRUTH GATE PATCHED"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
[ -f "$STATE" ] && cp -a "$STATE" "$SEND/auto_dispatcher_state.json"
