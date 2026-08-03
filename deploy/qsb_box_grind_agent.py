#!/usr/bin/env python3
"""qsb_box_grind_agent.py — OFFLINE-FIRST grind + sync agent (runs ON a worker box).

Deployed to the Acer / ThinkPad worker boxes (Windows, python 3.11). It is the
box-side half of the offline-first work-bundle system. Its contract:

  * grind  — read the local bundle file, process EVERY unit against the LOCAL
             Ollama at 127.0.0.1:11434, append each result to the local results
             queue. Requires ZERO connection to SkyscraperHQ. Idempotent: a unit
             already in the local results queue is skipped, so a crash/resume
             never double-grinds.

  * status — print how many bundle units are done / pending in the local queue.

The grind loop NEVER touches HQ. HQ delivers the bundle (scp) and later collects
the results queue (scp) — but that transport is OUT of band. If HQ is offline the
box keeps grinding whatever bundle it already has on local disk.

Local layout on the box (self-contained, survives reboot):
  %USERPROFILE%\\.qsb\\bundle.json          <- the bundle HQ delivered
  %USERPROFILE%\\.qsb\\results.jsonl        <- append-only local results queue
  %USERPROFILE%\\.qsb\\results_bundle.json  <- rolled-up results file for upload

Usage on the box:
  python qsb_box_grind_agent.py grind
  python qsb_box_grind_agent.py rollup     # build results_bundle.json for upload
  python qsb_box_grind_agent.py status
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, socket, sys, time, urllib.request

HOME = os.path.expanduser("~")
QSB = os.path.join(HOME, ".qsb")
BUNDLE = os.path.join(QSB, "bundle.json")
RESULTS_Q = os.path.join(QSB, "results.jsonl")
RESULTS_BUNDLE = os.path.join(QSB, "results_bundle.json")
WORK_STATE = os.path.join(QSB, "work_state.json")
OLLAMA = "http://127.0.0.1:11434/api/generate"
STAGES = ("TASK RECEIVED", "RESEARCH", "PLAN", "LOCAL WORK", "FILE OR ARTIFACT", "TEST", "RESULT", "VERIFICATION", "COMPLETE")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def box_name() -> str:
    h = socket.gethostname().lower()
    if "9rbvksm" in h or "thinkpad" in h or "lenovo" in h:
        return "thinkpad"
    if "1e2fb5n" in h or "acer" in h or "aspire" in h:
        return "acer"
    return h


def principal_identity() -> str:
    return "tp_pip" if box_name() == "thinkpad" else "acer_cass" if box_name() == "acer" else "UNKNOWN"


def degraded_message() -> str:
    label = "PIP" if principal_identity() == "tp_pip" else "ASA" if principal_identity() == "acer_cass" else "LOCAL PRINCIPAL"
    return f"{label} LOCAL PRIMARY UNAVAILABLE\nREMOTE PRIMARY FORBIDDEN\n{label} DEGRADED"


def _write_state(**changes):
    """Atomically publish factual work state from this physical agent."""
    os.makedirs(QSB, exist_ok=True)
    state = {"schema": "qsb_local_principal_work/v1", "principal_identity": principal_identity(),
             "physical_hostname": socket.gethostname(), "local_model": None, "current_task": None,
             "task_id": None, "work_status": "IDLE", "start_time": None, "current_stage": "IDLE",
             "stage_sequence": list(STAGES), "file_being_inspected": None, "file_being_modified": None,
             "tool_being_used": None, "current_blocker": None, "latest_output": None,
             "test_status": "NOT RUN", "evidence": None, "completion_status": "IDLE",
             "active": False, "updated_at": now(), "reasoning_route": "127.0.0.1:11434",
             "remote_primary_allowed": False}
    try:
        with open(WORK_STATE, "r", encoding="utf-8") as f:
            old = json.load(f)
        if isinstance(old, dict): state.update(old)
    except Exception:
        pass
    state.update(changes); state["updated_at"] = now()
    tmp = WORK_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, WORK_STATE)
    return state


def _done_unit_ids() -> set:
    done = set()
    if os.path.exists(RESULTS_Q):
        with open(RESULTS_Q, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["unit_id"])
                except Exception:
                    pass
    return done


def _ollama(prompt: str, model: str, max_tokens: int):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d.get("response", ""), int((time.time() - t0) * 1000)


def grind():
    if not os.path.exists(BUNDLE):
        print(json.dumps({"error": "no bundle on box", "path": BUNDLE})); return 1
    with open(BUNDLE, "r", encoding="utf-8") as f: bundle = json.load(f)
    model = bundle.get("model_hint", "llama3.2")
    done = _done_unit_ids(); box = box_name(); ground = skipped = failed = 0
    os.makedirs(QSB, exist_ok=True)
    for u in bundle.get("units", []):
        uid = u["unit_id"]
        if uid in done:
            skipped += 1; continue
        common = {"local_model": model, "current_task": str(u.get("prompt") or "")[:500],
                  "task_id": uid, "work_status": "WORKING", "start_time": now(), "active": True,
                  "file_being_inspected": BUNDLE, "file_being_modified": RESULTS_Q,
                  "tool_being_used": "local Ollama http://127.0.0.1:11434",
                  "current_blocker": None, "completion_status": "IN PROGRESS"}
        for stage, message in (("TASK RECEIVED", "Local task accepted"),
                               ("RESEARCH", "Inspecting the local bundle unit"),
                               ("PLAN", "Preparing a local-only inference request"),
                               ("LOCAL WORK", "Reasoning with this laptop local model")):
            _write_state(current_stage=stage, latest_output=message, **common)
        try:
            out, dur = _ollama(u["prompt"], model, u.get("max_tokens", 400))
            row = {"unit_id": uid, "source_id": u.get("source_id"), "bundle_id": bundle.get("bundle_id"),
                   "status": "done" if out.strip() else "error", "model": model, "provider": "local_ollama",
                   "output": out, "duration_ms": dur, "grind_ts": now(), "offline_at_grind": True, "box": box}
            if out.strip(): ground += 1
            else: failed += 1
        except Exception as e:
            blocker = str(e)[:500]
            row = {"unit_id": uid, "source_id": u.get("source_id"), "bundle_id": bundle.get("bundle_id"),
                   "status": "error", "error": blocker[:200], "model": model, "provider": "local_ollama",
                   "grind_ts": now(), "offline_at_grind": True, "box": box}
            failed += 1
            common["current_blocker"] = blocker
            blocked = dict(common); blocked.update({"current_stage": "LOCAL WORK",
                "latest_output": degraded_message(),
                "test_status": "FAIL", "completion_status": "BLOCKED", "active": False})
            _write_state(**blocked)
        _write_state(current_stage="FILE OR ARTIFACT", latest_output="Writing the local result artifact", **common)
        encoded = json.dumps(row, sort_keys=True)
        with open(RESULTS_Q, "a", encoding="utf-8") as f:
            f.write(encoded + "\n"); f.flush(); os.fsync(f.fileno())
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        evidence = {"artifact": RESULTS_Q, "result_row_sha256": digest, "provider": row.get("provider"),
                    "box": row.get("box"), "finished_at": row.get("grind_ts")}
        _write_state(current_stage="TEST", test_status="PASS" if row["status"] == "done" else "FAIL", latest_output="Verified local result row was written", **common)
        _write_state(current_stage="RESULT", latest_output=str(row.get("output") or row.get("error") or "")[:1000], **common)
        _write_state(current_stage="VERIFICATION", evidence=evidence, latest_output="Recorded local artifact SHA-256", **common)
        final_output = (str(row.get("output") or "")[:1000] if row["status"] == "done" else degraded_message())
        final = dict(common); final.update({"current_stage": "COMPLETE", "work_status": "COMPLETE" if row["status"] == "done" else "BLOCKED", "active": False,
            "completion_status": "COMPLETE" if row["status"] == "done" else "FAILED",
            "test_status": "PASS" if row["status"] == "done" else "FAIL", "evidence": evidence,
            "latest_output": final_output})
        _write_state(**final)
        print(f"[grind] {uid} {row['status']} ({row.get('duration_ms', '-')}ms)")
    print(json.dumps({"box": box, "ground": ground, "skipped": skipped, "failed": failed, "queue": RESULTS_Q}))
    return 0


def rollup():
    """Roll the append-only queue into a single upload-ready results bundle."""
    results = []
    if os.path.exists(RESULTS_Q):
        with open(RESULTS_Q, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except Exception:
                        pass
    bundle_id = results[0]["bundle_id"] if results else None
    out = {
        "schema": "qsb_work_results/v1", "bundle_id": bundle_id,
        "box": box_name(), "captured_ts": now(), "results": results,
    }
    json.dump(out, open(RESULTS_BUNDLE, "w", encoding="utf-8"), indent=2)
    print(json.dumps({"results_bundle": RESULTS_BUNDLE, "results": len(results),
                      "bundle_id": bundle_id}))
    return 0


def status():
    total = 0
    if os.path.exists(BUNDLE):
        total = len(json.load(open(BUNDLE, "r", encoding="utf-8")).get("units", []))
    done = len(_done_unit_ids())
    print(json.dumps({"box": box_name(), "bundle_units": total, "done": done,
                      "pending": max(0, total - done)}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["grind", "rollup", "status"])
    args = ap.parse_args()
    sys.exit({"grind": grind, "rollup": rollup, "status": status}[args.cmd]())


if __name__ == "__main__":
    main()
