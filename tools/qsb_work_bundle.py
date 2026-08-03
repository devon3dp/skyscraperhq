#!/usr/bin/env python3
"""qsb_work_bundle.py — OFFLINE-FIRST work-bundle builder + result applier (tower side).

Ross 2026-07-30: "if the Skyscraper goes offline, they should have a work bundle
they can still work... when it comes back online they upload their work...
everything choreographed."

This tool lives on SkyscraperHQ. It has TWO jobs:

  build  — assemble a self-contained JSON bundle of REAL pending work
           (drawn from the council task snapshot). Each unit carries the FULL
           prompt + any data it needs, so a worker box can grind it with ZERO
           HQ round-trips mid-grind. Emits to data/registries/work_bundles/.

  apply  — ingest a RESULTS file uploaded by a box after it reconnects.
           Idempotent (unit_id de-dup via an applied-cursor), writes each
           learning/artifact into the tower KB + stamps a council note.

The box-side counterpart is tools/qsb_box_grind_agent.py — it pulls a bundle,
grinds every unit against its LOCAL Ollama (127.0.0.1:11434), and writes a
local results queue that ONLY needs HQ when it uploads. Blocking the box's HQ
path (SSH/LAN) does NOT stop the grind — that is the whole point.

Bundle schema (v1):
  {
    "bundle_id": "wb_<hex>",
    "schema": "qsb_work_bundle/v1",
    "built_ts": "..Z",
    "built_by": "claude",
    "target_box": "thinkpad|acer|any",
    "model_hint": "llama3.2",
    "units": [
      {
        "unit_id": "u_<hex>",           # stable, de-dup key
        "source": "council_task",
        "source_id": "t_....",           # provenance
        "kind": "kb_gen|analysis|research",
        "title": "...",
        "prompt": "<full self-contained prompt>",
        "context": {...},                # any data the unit needs, inline
        "max_tokens": 512
      }, ...
    ]
  }

Results schema (v1) — written by the box, applied here:
  {
    "bundle_id": "wb_...",
    "schema": "qsb_work_results/v1",
    "box": "thinkpad|acer",
    "graptured_ts": "..Z",
    "results": [
      {
        "unit_id": "u_...",
        "source_id": "t_...",
        "status": "done|error",
        "model": "llama3.2",
        "provider": "local_ollama",
        "output": "<real model text>",
        "duration_ms": 1234,
        "grind_ts": "..Z",             # when the box actually ground it (offline)
        "offline_at_grind": true
      }, ...
    ]
  }
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, sys, uuid
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
BUNDLE_DIR = REG / "work_bundles"
KB_DIR = REG / "work_bundle_kb"
APPLIED_CURSOR = REG / "qsb_work_bundle_applied.json"
SNAPSHOT = REG / "qsb_council_tasks_snapshot.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hex(n=8):
    return uuid.uuid4().hex[:n]


def _unit_id(source_id: str, kind: str) -> str:
    # stable per (task, kind) so re-building the same pending work yields the
    # same unit_id -> apply stays idempotent across bundles.
    h = hashlib.sha1(f"{source_id}|{kind}".encode()).hexdigest()[:12]
    return f"u_{h}"


def _pending_tasks(limit: int = 0):
    """Return pending council tasks. limit=0 means no cap (caller filters)."""
    if not SNAPSHOT.exists():
        return []
    d = json.loads(SNAPSHOT.read_text())
    if isinstance(d, dict):
        d = d.get("tasks", d.get("items", list(d.values())))
    out = []
    for t in d:
        if not isinstance(t, dict):
            continue
        if t.get("state") not in ("open", "blocked"):
            continue
        title = (t.get("title") or "").strip()
        desc = (t.get("description") or "").strip()
        if not title:
            continue
        out.append({"id": t.get("id") or t.get("task_id"), "title": title, "desc": desc,
                    "state": t.get("state")})
        if limit and len(out) >= limit:
            break
    return out


def _box_of(unit_id: str) -> str:
    """Deterministically assign a unit to one worker box so the two boxes get
    DISJOINT work (grinding the same task on both would collide on unit_id and
    the second box's real learning would be discarded as a dup). Uses the stable
    unit_id hash so the same task always routes to the same box."""
    return "thinkpad" if int(unit_id[2:4], 16) % 2 == 0 else "acer"


def _unit_from_task(t: dict) -> dict:
    # Each pending council task becomes a self-contained KB-gen unit. The prompt
    # embeds the task so the box never has to call back to HQ to understand it.
    prompt = (
        "You are a QSB Tower worker grinding OFFLINE with your local model. "
        "Produce a concise, actionable analysis of the following tower work item. "
        "Give: (1) a one-line restatement, (2) the concrete first implementation step, "
        "(3) one risk to watch. Keep it under 120 words.\n\n"
        f"WORK ITEM: {t['title']}\n"
        f"DETAIL: {t['desc'] or '(no extra detail supplied)'}\n"
    )
    return {
        "unit_id": _unit_id(t["id"], "kb_gen"),
        "source": "council_task",
        "source_id": t["id"],
        "kind": "kb_gen",
        "title": t["title"][:140],
        "prompt": prompt,
        "context": {"task_state": t["state"]},
        "max_tokens": 400,
    }


def build(target_box: str, size: int, model_hint: str) -> dict:
    # Pull ALL pending work, drop anything already applied (so the builder
    # advances through the backlog instead of re-shipping the same top-N
    # forever), then keep only the units routed to this box (disjoint split).
    applied = set(_load_cursor().get("applied_unit_ids", []))
    tasks = _pending_tasks(0)
    units = []
    for t in tasks:
        if not t.get("id"):
            continue
        u = _unit_from_task(t)
        if u["unit_id"] in applied:
            continue
        if target_box in ("thinkpad", "acer") and _box_of(u["unit_id"]) != target_box:
            continue
        units.append(u)
        if len(units) >= size:
            break
    bundle = {
        "bundle_id": f"wb_{_hex(10)}",
        "schema": "qsb_work_bundle/v1",
        "built_ts": now(),
        "built_by": "claude",
        "target_box": target_box,
        "model_hint": model_hint,
        "units": units,
    }
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    path = BUNDLE_DIR / f"{bundle['bundle_id']}.json"
    path.write_text(json.dumps(bundle, indent=2))
    return {"bundle_id": bundle["bundle_id"], "units": len(units), "path": str(path),
            "target_box": target_box}


def _load_cursor() -> dict:
    if APPLIED_CURSOR.exists():
        return json.loads(APPLIED_CURSOR.read_text())
    return {"applied_unit_ids": []}


def _save_cursor(c: dict):
    APPLIED_CURSOR.write_text(json.dumps(c, indent=2))


def apply(results_path: str) -> dict:
    res = json.loads(Path(results_path).read_text())
    if res.get("schema") != "qsb_work_results/v1":
        return {"error": f"bad schema {res.get('schema')}"}
    cursor = _load_cursor()
    already = set(cursor.get("applied_unit_ids", []))
    KB_DIR.mkdir(parents=True, exist_ok=True)
    applied, skipped_dup, errors = [], [], []
    box = res.get("box", "?")
    for r in res.get("results", []):
        uid = r.get("unit_id")
        if not uid:
            continue
        if uid in already:
            skipped_dup.append(uid)
            continue
        if r.get("status") != "done":
            errors.append(uid)
            already.add(uid)  # don't re-apply a permanent error either
            continue
        # land the learning as a KB artifact
        kb = {
            "ts": now(), "unit_id": uid, "source_id": r.get("source_id"),
            "box": box, "model": r.get("model"), "provider": r.get("provider"),
            "grind_ts": r.get("grind_ts"), "offline_at_grind": r.get("offline_at_grind"),
            "bundle_id": res.get("bundle_id"), "output": r.get("output", ""),
        }
        (KB_DIR / f"{uid}.json").write_text(json.dumps(kb, indent=2))
        with open(KB_DIR / "kb_index.jsonl", "a") as f:
            f.write(json.dumps({"ts": kb["ts"], "unit_id": uid, "source_id": kb["source_id"],
                                "box": box, "chars": len(kb["output"])}) + "\n")
        applied.append(uid)
        already.add(uid)
        # council note against the source task (provenance back to the board)
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import qsb_council_tasks as ct
            ct.note(r.get("source_id"), box,
                    f"offline-bundle result applied ({len(r.get('output',''))} chars, "
                    f"model {r.get('model')}, unit {uid})")
        except Exception as e:
            pass
    cursor["applied_unit_ids"] = sorted(already)
    _save_cursor(cursor)
    return {"bundle_id": res.get("bundle_id"), "box": box,
            "applied": applied, "skipped_dup": skipped_dup, "errors": errors,
            "applied_n": len(applied), "dup_n": len(skipped_dup), "err_n": len(errors)}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--box", default="any")
    b.add_argument("--size", type=int, default=5)
    b.add_argument("--model", default="llama3.2")
    a = sub.add_parser("apply")
    a.add_argument("--results", required=True)
    args = ap.parse_args()
    if args.cmd == "build":
        print(json.dumps(build(args.box, args.size, args.model), indent=2))
    elif args.cmd == "apply":
        print(json.dumps(apply(args.results), indent=2))


if __name__ == "__main__":
    main()
