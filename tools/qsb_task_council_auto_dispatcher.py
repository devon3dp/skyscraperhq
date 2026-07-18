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


# QSB_ROUTE_LOOP_GUARD_V1
ROUTED_LEDGER = REG / "qsb_task_council_auto_dispatcher_routed_ids.json"
PAUSE_FILE = RUNTIME / "AUTONOMY_PAUSED_DASHBOARD_SERVICE_REPAIR"

def _load_routed_ids():
    try:
        if ROUTED_LEDGER.exists():
            data = json.loads(ROUTED_LEDGER.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return set(str(x) for x in data)
    except Exception:
        pass
    return set()

def _mark_routed_id(tid):
    try:
        ids = _load_routed_ids()
        ids.add(str(tid))
        ROUTED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ROUTED_LEDGER.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
    except Exception:
        pass


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

    if tid in _load_routed_ids():
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
    if state in {"done", "complete", "completed", "closed", "blocked", "routed_for_work", "routed", "assigned"}:
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

def update_task(tid, result_text, state="routed_for_work"):
    # Ross/ChatGPT 2026-07-09 Priority 1/A: FREEZE shallow auto-completion.
    # The dispatcher is INTAKE ONLY — it may set routing/status but must NEVER complete a task.
    # /tasks/done and /tasks/complete are REMOVED from the fallback chain so a failed
    # status update can never silently complete work. Completion requires a verifier gate.
    ALLOWED = {"routed_for_work", "routed", "claimed", "in_progress", "needs_implementation", "needs_verification", "assigned"}
    if state not in ALLOWED:
        state = "needs_verification"  # never 'done'/'complete' from the dispatcher
    payloads = [
        ("/tasks/update", {"id": tid, "status": state, "state": state, "result": result_text, "note": result_text, "updated_by": "task_council_auto_dispatcher"}),
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
        f"Task Council Auto Dispatcher ROUTED task for work.\n"
        f"Task ID: {tid}\n"
        f"CEO: {ceo}\n"
        f"Task type: {task_type}\n"
        f"Provider: {provider}\n"
        f"Brain Router reply: {reply}\n"
        "Truth gate: this is NOT marked complete until a worker implements it and a verifier confirms it.\n"
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
    _mark_routed_id(tid)
    log_event("dispatch_routed_for_work", **out)
    return out

def cycle_once():
    if PAUSE_FILE.exists():
        state = {"ts": now(), "ok": True, "paused": True, "reason": str(PAUSE_FILE), "processed": [], "errors": []}
        write_json(STATE_JSON, state)
        log_event("cycle_paused", reason=str(PAUSE_FILE))
        return state
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
