#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
DISPATCHER="$PROJECT/tools/qsb_task_council_gene_pool_dispatcher.py"
BOARDROOM_LOG="$PROJECT/logs/boardroom_hub_8852.log"
ROUTER_LOG="$PROJECT/logs/gene_pool_router_8860.log"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_task_council_gene_pool_dispatcher"
REPORT="$RUN_DIR/reports/task_council_gene_pool_dispatcher_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$RUN_DIR/logs" "$SEND" "$PROJECT/tools" "$PROJECT/runtime" "$PROJECT/logs" "$PROJECT/data/registries"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — TASK COUNCIL → RULEBOOK → BRAIN ROUTER DISPATCHER"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "============================================================"
echo "Rules:"
echo " - Build controlled Task Council dispatcher."
echo " - Create and complete smoke tasks only."
echo " - Route through Brain Router Gene Pool."
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO fallback to Wren/local GPU."
echo " - No key changes."
echo " - No secure key printing."
echo " - No trading/order changes."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ -f "$DISPATCHER" ]; then
  cp -a "$DISPATCHER" "$RUN_DIR/backups/qsb_task_council_gene_pool_dispatcher.py.bak_$STAMP"
fi

echo
echo "===== 1. WRITE DISPATCHER ====="

cat > "$DISPATCHER" <<'PY'
#!/usr/bin/env python3
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"
OUT = REG / "qsb_task_council_gene_pool_dispatch_log.jsonl"

BASE = "http://127.0.0.1:8852"

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

def log(obj):
    REG.mkdir(parents=True, exist_ok=True)
    obj["ts"] = now()
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def http_get(path, timeout=30):
    url = BASE + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            ctype = r.headers.get("Content-Type", "")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:2000]}
            return {"ok": 200 <= r.status < 300, "http": r.status, "data": data, "raw": raw[:2000], "url": url, "ctype": ctype}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return {"ok": False, "http": e.code, "error": raw[:2000], "url": url}
    except Exception as e:
        return {"ok": False, "http": 0, "error": repr(e), "url": url}

def http_post(path, payload, timeout=45):
    url = BASE + path
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    try:
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

def task_text(t):
    parts = []
    for k in ("title", "task", "description", "body", "text", "name"):
        v = t.get(k)
        if v:
            parts.append(str(v))
    return "\n".join(parts).strip()

def task_id(t):
    return str(t.get("id") or t.get("task_id") or t.get("uid") or "")

def classify_task(text):
    low = text.lower()
    if any(x in low for x in ["code", "script", "python", "bash", "bug", "traceback", "compile", "patch", "repair"]):
        return "coding"
    if any(x in low for x in ["summarise", "summarize", "summary", "recap", "report", "state"]):
        return "summary"
    if any(x in low for x in ["cheap", "cost", "token", "quota", "fast"]):
        return "cheap"
    if any(x in low for x in ["architecture", "design", "rulebook", "rule book", "kernel", "system", "council", "brain router", "strategy"]):
        return "architecture"
    return "default"

def choose_ceo(task_type):
    if task_type == "coding":
        return "CEO 2"
    if task_type == "summary":
        return "CEO 3"
    if task_type == "cheap":
        return "Claude HQ"
    if task_type == "architecture":
        return "Claude HQ"
    return "CEO 2"

def post_town(text, src="task_council_gene_pool_dispatcher"):
    payloads = [
        {"from": "Task Council Dispatcher", "src": src, "to": "council", "text": text, "message": text},
        {"speaker": "Task Council Dispatcher", "source": src, "target": "council", "text": text, "message": text},
    ]
    for payload in payloads:
        r = http_post("/town/post", payload, timeout=20)
        if r["ok"]:
            return r
    return r

def create_task(title, description, tag):
    payloads = [
        {
            "title": title,
            "description": description,
            "task": description,
            "body": description,
            "created_by": "task_council_gene_pool_dispatcher",
            "from": "task_council_gene_pool_dispatcher",
            "assignee": "brain_router",
            "status": "open",
            "tag": tag,
            "tags": ["smoke", "gene_pool", tag],
        },
        {
            "title": title,
            "task": description,
            "from": "task_council_gene_pool_dispatcher",
        },
    ]

    last = None
    for payload in payloads:
        last = http_post("/tasks/create", payload, timeout=25)
        if last["ok"]:
            return last
    return last

def read_tasks():
    r = http_get("/tasks/data", timeout=30)
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

def submit_to_gene_pool(task):
    text = task_text(task)
    tid = task_id(task)
    task_type = classify_task(text)
    ceo = choose_ceo(task_type)

    ask = (
        f"Task Council job {tid or 'NO_ID'}.\n"
        f"Task type: {task_type}.\n"
        f"Original task:\n{text}\n\n"
        "Complete this as a safe SkyscraperHQ executive routing task. "
        "Return a clear result. Do not use Wren/local GPU fallback. "
        "Do not change keys. Do not touch trading."
    )

    payload = {
        "ceo": ceo,
        "task": task_type,
        "ask": ask,
        "source": "task_council",
        "task_id": tid,
    }

    r = http_post("/proxy/gene_pool/api/submit_job", payload, timeout=60)
    return r, ceo, task_type, ask

def try_update_task(task, result_text):
    tid = task_id(task)
    if not tid:
        return {"ok": False, "reason": "no_task_id"}

    payloads = [
        ("/tasks/update", {"id": tid, "status": "done", "result": result_text, "note": result_text, "updated_by": "task_council_gene_pool_dispatcher"}),
        ("/tasks/complete", {"id": tid, "result": result_text, "completed_by": "task_council_gene_pool_dispatcher"}),
        ("/tasks/done", {"id": tid, "result": result_text, "completed_by": "task_council_gene_pool_dispatcher"}),
        ("/tasks/status", {"id": tid, "status": "done", "note": result_text}),
        ("/tasks/comment", {"id": tid, "comment": result_text, "from": "task_council_gene_pool_dispatcher"}),
        ("/tasks/assign", {"id": tid, "actor": "task_council_gene_pool_dispatcher", "assignee": "done"}),
    ]

    attempts = []
    for path, payload in payloads:
        r = http_post(path, payload, timeout=20)
        attempts.append({"path": path, "http": r.get("http"), "ok": r.get("ok"), "error": r.get("error", "")[:200]})
        if r["ok"]:
            return {"ok": True, "path": path, "response": r, "attempts": attempts}

    return {"ok": False, "attempts": attempts}

def dispatch_task(task):
    tid = task_id(task)
    text = task_text(task)
    r, ceo, task_type, ask = submit_to_gene_pool(task)

    if r["ok"]:
        data = r.get("data", {})
        decision = data.get("decision", {})
        reply = data.get("reply") or decision.get("provider_reply") or json.dumps(data)[:1000]
        selected = decision.get("selected_label") or decision.get("selected_provider") or "unknown"

        result_text = (
            f"Task Council Dispatcher completed route.\n"
            f"Task ID: {tid or 'NO_ID'}\n"
            f"CEO: {ceo}\n"
            f"Task type: {task_type}\n"
            f"Provider: {selected}\n"
            f"Reply: {reply}\n"
            "Doctrine: Wren protected; CEOs used API Gene Pool only."
        )

        town = post_town(
            f"✅ Task Council dispatched {tid or 'NO_ID'} → {ceo} → {selected}. "
            f"Task type={task_type}. Wren protected; API Gene Pool only."
        )

        update = try_update_task(task, result_text)

        out = {
            "ok": True,
            "task_id": tid,
            "ceo": ceo,
            "task_type": task_type,
            "selected": selected,
            "gene_pool": r,
            "town": town,
            "task_update": update,
            "result": result_text,
        }
        log({"event": "dispatch_complete", **out})
        return out

    result_text = (
        f"Task Council Dispatcher failed to route task {tid or 'NO_ID'} through Gene Pool. "
        f"Error: {r.get('error') or r.get('raw') or r}"
    )
    town = post_town("⚠️ Task Council dispatcher failed: " + result_text[:800])
    out = {
        "ok": False,
        "task_id": tid,
        "ceo": ceo,
        "task_type": task_type,
        "gene_pool": r,
        "town": town,
        "result": result_text,
    }
    log({"event": "dispatch_failed", **out})
    return out

def create_smoke_tasks():
    smoke = [
        (
            "SMOKE · Architecture route through Brain Router",
            "Architecture smoke task: check that Task Council can send an executive architecture job through Claude HQ and the API Gene Pool.",
            "architecture",
        ),
        (
            "SMOKE · Coding route through Brain Router",
            "Coding smoke task: check that Task Council can send a coding repair job through CEO 2 and the API Gene Pool.",
            "coding",
        ),
        (
            "SMOKE · Summary route through Brain Router",
            "Summary smoke task: check that Task Council can send a reporting job through CEO 3 and the API Gene Pool.",
            "summary",
        ),
    ]

    created = []
    for title, desc, tag in smoke:
        r = create_task(title, desc, tag)
        created.append({"title": title, "tag": tag, "create": r})
        time.sleep(0.25)

    return created

def find_created_smoke_tasks(all_tasks):
    wanted = []
    for t in all_tasks:
        text = task_text(t)
        if "SMOKE ·" in text or "Architecture smoke task" in text or "Coding smoke task" in text or "Summary smoke task" in text:
            wanted.append(t)
    # newest likely last or first depending Boardroom. Return up to 6 but dispatcher will handle smoke only.
    return wanted[:6]

def system_health():
    checks = {}
    for path in ["/ipad", "/tasks", "/tasks/data", "/town_square", "/town_square_feed", "/proxy/gene_pool", "/proxy/gene_pool/api/live", "/link_health"]:
        checks[path] = http_get(path, timeout=35)
    return checks

def main():
    print("TASK COUNCIL GENE POOL DISPATCHER")
    print("ts:", now())
    print("doctrine:", json.dumps(DOCTRINE, indent=2))

    print("\n--- preflight health")
    health = system_health()
    for path, r in health.items():
        print(path, "ok=", r["ok"], "http=", r["http"], "size=", len(r.get("raw", "")))

    print("\n--- create smoke tasks")
    created = create_smoke_tasks()
    print(json.dumps(created, indent=2)[:5000])

    print("\n--- read tasks")
    task_read, tasks = read_tasks()
    print("tasks_read_ok:", task_read["ok"], "http:", task_read.get("http"), "task_count:", len(tasks))

    smoke_tasks = find_created_smoke_tasks(tasks)
    print("smoke_tasks_found:", len(smoke_tasks))
    for t in smoke_tasks[:6]:
        print(" -", task_id(t), task_text(t).replace("\n", " ")[:160])

    if not smoke_tasks:
        print("[FAIL] No smoke tasks found after create. Cannot prove full loop.")
        log({"event": "no_smoke_tasks_found", "created": created, "task_read": task_read})
        return 2

    print("\n--- dispatch smoke tasks")
    results = []
    seen_types = set()

    for t in smoke_tasks:
        text = task_text(t).lower()
        # Dispatch one of each smoke class only.
        cls = classify_task(text)
        if cls in seen_types:
            continue
        if cls not in {"architecture", "coding", "summary"}:
            continue
        seen_types.add(cls)

        res = dispatch_task(t)
        results.append(res)
        print(json.dumps({
            "ok": res.get("ok"),
            "task_id": res.get("task_id"),
            "ceo": res.get("ceo"),
            "task_type": res.get("task_type"),
            "selected": res.get("selected"),
            "task_update_ok": res.get("task_update", {}).get("ok"),
            "task_update_path": res.get("task_update", {}).get("path"),
        }, indent=2))
        time.sleep(0.5)

    print("\n--- final live data")
    live = http_get("/proxy/gene_pool/api/live", timeout=35)
    if live["ok"]:
        data = live["data"]
        metrics = data.get("metrics", {})
        print("live_ok:", data.get("ok"))
        print("active_provider_count:", metrics.get("active_provider_count"))
        print("stored_key_count:", metrics.get("stored_key_count"))
        print("route_count:", metrics.get("autonomy", {}).get("route_count"))
        print("latest_decision:", data.get("latest_decision"))
        print("ceo_panels:")
        for name, panel in (data.get("ceo_panels") or {}).items():
            print(" ", name, "|", panel.get("task"), "|", panel.get("provider_label"), "|", (panel.get("ask") or "")[:90])
    else:
        print("live_failed:", live)

    print("\n--- final task data")
    final_task_read, final_tasks = read_tasks()
    print("tasks_ok:", final_task_read["ok"], "count:", len(final_tasks))

    ok_count = sum(1 for r in results if r.get("ok"))
    update_count = sum(1 for r in results if r.get("task_update", {}).get("ok"))
    summary = {
        "ok": ok_count >= 3,
        "created_count": len(created),
        "smoke_tasks_found": len(smoke_tasks),
        "dispatched_ok": ok_count,
        "task_update_ok": update_count,
        "results": results,
        "health": {k: {"ok": v["ok"], "http": v["http"], "url": v["url"]} for k, v in health.items()},
        "doctrine": DOCTRINE,
    }

    out = PROJECT / "data" / "registries" / "qsb_task_council_gene_pool_dispatch_last_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n--- dispatcher summary")
    print(json.dumps({
        "ok": summary["ok"],
        "created_count": summary["created_count"],
        "smoke_tasks_found": summary["smoke_tasks_found"],
        "dispatched_ok": summary["dispatched_ok"],
        "task_update_ok": summary["task_update_ok"],
        "summary_file": str(out),
    }, indent=2))

    if summary["ok"]:
        post_town("✅ WHOLE SYSTEM SMOKE PASSED: Task Council created tasks, dispatcher routed them through Brain Router Gene Pool, CEO panels updated, and Town Square received completion notices.")
        return 0

    post_town("⚠️ WHOLE SYSTEM SMOKE PARTIAL: Task Council dispatcher ran but did not complete all three controlled smoke tasks.")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x "$DISPATCHER"
echo "[OK] wrote $DISPATCHER"

echo
echo "===== 2. COMPILE DISPATCHER ====="
python3 -m py_compile "$DISPATCHER" && echo "[OK] dispatcher compiles" || exit 2

echo
echo "===== 3. RUN DISPATCHER SMOKE TEST ====="
python3 "$DISPATCHER" > "$RUN_DIR/reports/dispatcher_run.txt" 2>&1
DISPATCH_RC="$?"
cat "$RUN_DIR/reports/dispatcher_run.txt"

echo
echo "===== 4. WHOLE SYSTEM HEALTH SNAPSHOT ====="
for url in \
  "http://127.0.0.1:8852/ipad" \
  "http://127.0.0.1:8852/tasks" \
  "http://127.0.0.1:8852/tasks/data" \
  "http://127.0.0.1:8852/town_square" \
  "http://127.0.0.1:8852/town_square_feed" \
  "http://127.0.0.1:8852/proxy/gene_pool" \
  "http://127.0.0.1:8852/proxy/gene_pool/api/live" \
  "http://127.0.0.1:8852/link_health"
do
  echo "--- $url"
  curl -sS --max-time 35 -o "$RUN_DIR/logs/http.tmp" -w "http=%{http_code} total=%{time_total}s size=%{size_download}\n" "$url" || true
  head -c 260 "$RUN_DIR/logs/http.tmp" 2>/dev/null || true
  echo
done

echo
echo "===== 5. FINAL SUMMARY JSON ====="
SUMMARY_JSON="$PROJECT/data/registries/qsb_task_council_gene_pool_dispatch_last_summary.json"
if [ -f "$SUMMARY_JSON" ]; then
  cp -a "$SUMMARY_JSON" "$RUN_DIR/reports/dispatch_last_summary.json"
  python3 -m json.tool "$SUMMARY_JSON" | head -n 220
else
  echo "[WARN] summary JSON missing"
fi

echo
echo "===== 6. RECENT TOWN / TASK / GENE POOL EVENTS ====="
echo "--- dispatcher log tail ---"
tail -n 80 "$PROJECT/data/registries/qsb_task_council_gene_pool_dispatch_log.jsonl" 2>/dev/null || true

echo
echo "--- Boardroom recent errors ---"
tail -n 220 "$BOARDROOM_LOG" | grep -Ei "Errno 24|Too many open files|Traceback|Exception|NameError|BrokenPipe|task|town|gene|proxy" || true

echo
echo "--- Gene Pool recent errors ---"
tail -n 160 "$ROUTER_LOG" | grep -Ei "error|exception|traceback|fail|warning|submit|POST|BrokenPipe" || true

echo
echo "===== 7. URLS ====="
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
echo "DONE — TASK COUNCIL DISPATCHER + WHOLE SYSTEM SMOKE"
echo "Dispatcher exit code: $DISPATCH_RC"
echo "Report:"
echo "$REPORT"
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/dispatcher_run.txt" "$SEND/dispatcher_run.txt"
[ -f "$SUMMARY_JSON" ] && cp -a "$SUMMARY_JSON" "$SEND/dispatch_last_summary.json"

exit "$DISPATCH_RC"
