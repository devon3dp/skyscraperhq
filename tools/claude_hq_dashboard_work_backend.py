#!/usr/bin/env python3
"""claude_hq_dashboard_work_backend.py — CLI-side pickup of dashboard work queue.

Ross 2026-07-10: the public dashboard must NOT run arbitrary shell. Dashboard
chat only WRITES an approved work request to
data/registries/claude_hq_dashboard_work_queue.jsonl. THIS script is run by the
Claude HQ CLI (a human/agent at the terminal) to see pending work, ensure a
Task Council task exists, and mark an item processed ONLY after its report
exists. It never self-closes and never executes work on its own — it surfaces
work for the CLI operator to do.

USAGE
    python3 tools/claude_hq_dashboard_work_backend.py list         # show pending
    python3 tools/claude_hq_dashboard_work_backend.py show <rid>    # one item
    python3 tools/claude_hq_dashboard_work_backend.py mark <rid>    # mark processed
                                                                    # (requires report exists)
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
QUEUE = REG / "claude_hq_dashboard_work_queue.jsonl"
PROCESSED_LOG = REG / "claude_hq_dashboard_work_processed.jsonl"
sys.path.insert(0, str(ROOT / "tools"))

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _load():
    items = []
    if QUEUE.exists():
        for ln in QUEUE.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try: items.append(json.loads(ln))
            except Exception: pass
    return items

def _processed_ids():
    done = set()
    if PROCESSED_LOG.exists():
        for ln in PROCESSED_LOG.read_text().splitlines():
            try: done.add(json.loads(ln).get("request_id"))
            except Exception: pass
    return done

def pending():
    done = _processed_ids()
    return [i for i in _load() if i.get("request_id") not in done]

def cmd_list():
    p = pending()
    print(f"=== {len(p)} pending dashboard work item(s) for Claude HQ CLI ===")
    for i in p:
        print(f"  {i['request_id']}  [{i.get('classification')}]  {i.get('task_title','')[:60]}")
        print(f"      task_id={i.get('task_id')}  report={i.get('report_path')}")
        print(f"      state={i.get('state')}  root={i.get('approved_root')}")
    if not p:
        print("  (none)")

def cmd_show(rid):
    for i in _load():
        if i.get("request_id") == rid:
            print(json.dumps(i, indent=2)); return
    print(f"no such request_id: {rid}")

def cmd_mark(rid):
    item = next((i for i in _load() if i.get("request_id") == rid), None)
    if not item:
        print(f"no such request_id: {rid}"); return
    rp = item.get("report_path")
    # SAFETY: only mark processed once the report actually exists (no fake complete)
    if not rp or not Path(rp).exists():
        print(f"REFUSED: report does not exist yet ({rp}). Do the work + write the "
              f"report first. No self-close, no fake complete.")
        return
    # ensure a Task Council task exists / note it (never mark done here)
    tid = item.get("task_id")
    try:
        import qsb_council_tasks as qct
        if tid:
            qct.note(tid, "hq_claude",
                     f"dashboard work {rid} processed by CLI backend; report at {rp}. "
                     "Left OPEN for Ross/verifier (backend does not close).")
    except Exception as e:
        print(f"(council note skipped: {e})")
    with open(PROCESSED_LOG, "a") as f:
        f.write(json.dumps({"request_id": rid, "task_id": tid, "report_path": rp,
                            "processed_at": utc(), "by": "hq_claude_cli",
                            "note": "report verified present; task left OPEN"}) + "\n")
    print(f"marked {rid} processed (report verified). Task {tid} left OPEN for review.")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "list": cmd_list()
    elif a[0] == "show" and len(a) > 1: cmd_show(a[1])
    elif a[0] == "mark" and len(a) > 1: cmd_mark(a[1])
    else: print(__doc__)
