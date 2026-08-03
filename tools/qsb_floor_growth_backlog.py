#!/usr/bin/env python3
"""
QSB Floor-Growth Backlog Generator + Deliverable Checker
========================================================

WHY (2026-07-30, Ross): the council backlog was dominated by ONE vague recycler
("Worker needs surfaced — action the tower's real requests"). Workers could only
answer it with narration ("I'll look at F36…"), which the 2-CEO verifier quorum
CORRECTLY rejected — so it recycled forever and starved every real task. See the
root-cause note in tools/qsb_worker_needs_queue.py.

Meanwhile ~130 floor cards are still `skeleton: true` / PREVIEW_ONLY with an
EMPTY rooms[] and generic auto-spawned rosters. That is real, concrete,
buildable work: FIT OUT the floor_card.json so the floor stops being a stub.

This tool makes the tower GROW ITSELF by generating CONCRETE council tasks whose
success criterion is a REAL FILE CHANGE (the floor_card goes skeleton→populated),
not a narrative. Because the deliverable is a verifiable artifact, the correction
loop + 2-CEO verify can enforce it: "I'll look at F36" FAILS the checker and
recycles into a real fit-out.

WHAT THIS TOOL IS / IS NOT
  IS  : a bounded, propose-only BACKLOG GENERATOR. It appends `created` council
        tasks via the sanctioned qsb_council_tasks.create() path (append-only),
        one open task per floor max, WIP-aware, low priority (build work, not an
        alert).
  IS  : a DELIVERABLE CHECKER (`check` subcommand + check_deliverable()) the
        verifiers call to decide pass/fail against narration.
  NOT : a deployer. It flips NO execution gate. It does NOT edit floor cards, does
        NOT auto-apply anything, does NOT install a timer. Deploy of any change
        stays gated (bench / Ross). Deliberately does not touch
        qsb_apply_bridge.py or qsb_task_council_autorunner.py.

USAGE
  # preview candidates + the exact tasks that WOULD be created (no writes):
  python3 tools/qsb_floor_growth_backlog.py generate --dry-run --limit 3

  # actually append up to N floor-growth tasks to the council backlog:
  python3 tools/qsb_floor_growth_backlog.py generate --limit 3

  # list skeleton floors that still need fit-out:
  python3 tools/qsb_floor_growth_backlog.py scan

  # check a produced artifact (verifier side). PASS iff the floor_card is real:
  python3 tools/qsb_floor_growth_backlog.py check --floor 112 \
          --artifact floors/floor_112_procurement/floor_card.json
  # a narration answer FAILS:
  python3 tools/qsb_floor_growth_backlog.py check --floor 36 \
          --artifact-text "I'll look at F36 and see what it needs."
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS = ROOT / "floors"
REG = ROOT / "data/registries"
ACTIVITY_INDEX = REG / "qsb_floor_activity_index.json"

# marker tag prefix — how we recognise our own tasks for one-per-floor dedup.
FLOOR_TAG_PREFIX = "floor-growth:f"
GROWTH_TAG = "floor-growth"

# Bounds. This is BUILD work, not an alert — keep it low priority and never flood.
DEFAULT_NEW_PER_RUN = int(os.environ.get("FLOOR_GROWTH_PER_RUN", "3"))
# Ceiling on how many OPEN floor-growth tasks may exist at once, so we never
# re-flood the backlog the way the old recycler did.
MAX_OPEN_GROWTH = int(os.environ.get("FLOOR_GROWTH_MAX_OPEN", "8"))

# States that mean a task is FINISHED/dead and no longer occupies a floor's slot
# (mirrors the terminal set used by qsb_worker_needs_queue.py).
_TERMINAL_TASK_STATES = {
    "done", "denied", "cancelled", "rejected", "archived",
    "superseded", "dropped", "duplicate", "closed", "abandoned_by_ross_order",
}

# A roster role is "generic" (auto-spawned stub) if it looks like these — a real
# fit-out must replace them with differentiated roles.
_GENERIC_ROLE_RE = re.compile(
    r"^\s*(operator|worker|staff)(\s+on\s+f\d+)?\s*$", re.IGNORECASE)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── floor scanning ───────────────────────────────────────────────────────────

def _load_activity_index() -> dict:
    """Return {floor_id: {active, age_s, ...}} for coldness scoring. Best-effort."""
    out: dict[str, dict] = {}
    try:
        d = json.loads(ACTIVITY_INDEX.read_text())
        for row in d.get("floors", []):
            if isinstance(row, list) and len(row) == 2:
                out[row[0]] = row[1] or {}
    except Exception:
        pass
    return out


def _theme_bits(card: dict) -> dict:
    """Theme/palette/tagline may live at top level OR under live_signals. Return
    whichever are present so both the scan and the checker agree on 'has theme'."""
    ls = card.get("live_signals") or {}
    return {
        "theme": card.get("theme") or ls.get("theme"),
        "palette": card.get("palette") or ls.get("palette"),
        "tagline": card.get("tagline") or ls.get("tagline") or card.get("tour_blurb"),
    }


def _roster_is_generic(roster: list) -> bool:
    """True iff the roster is empty OR every non-manager role is a generic stub."""
    if not roster:
        return True
    real = 0
    for m in roster:
        if not isinstance(m, dict):
            continue
        cat = str(m.get("category") or "")
        role = str(m.get("role") or "")
        if cat == "floor_manager":
            continue  # the auto floor_manager is fine; we want real OTHER roles
        if not _GENERIC_ROLE_RE.match(role):
            real += 1
    return real == 0


def _needs_fitout(card: dict) -> tuple[bool, list[str]]:
    """Return (needs, missing_fields). A floor needs fit-out when it is a skeleton
    (or PREVIEW_ONLY stub) and its concrete content is missing."""
    missing: list[str] = []
    rooms = card.get("rooms") or []
    if not rooms:
        missing.append("rooms")
    if _roster_is_generic(card.get("team_roster") or []):
        missing.append("team_roster(real-roles)")
    tb = _theme_bits(card)
    for k in ("theme", "palette", "tagline"):
        if not tb.get(k):
            missing.append(k)
    is_stub = bool(card.get("skeleton")) or card.get("execution_mode") == "PREVIEW_ONLY"
    return (is_stub and bool(missing)), missing


def scan_floors() -> list[dict]:
    """Return candidate floors needing fit-out, coldest/lowest-number first."""
    act = _load_activity_index()
    cands: list[dict] = []
    for p in sorted(glob.glob(str(FLOORS / "*" / "floor_card.json"))):
        try:
            card = json.loads(Path(p).read_text())
        except Exception:
            continue
        needs, missing = _needs_fitout(card)
        if not needs:
            continue
        fid = card.get("floor_id") or ""
        fnum = card.get("floor_number")
        a = act.get(fid, {})
        cands.append({
            "path": os.path.relpath(p, ROOT),
            "floor_id": fid,
            "floor_number": fnum,
            "floor_name": card.get("floor_name") or fid,
            "department": card.get("department") or "",
            "zone": card.get("zone") or "",
            "missing": missing,
            "cold": not bool(a.get("active", False)),
            "age_s": a.get("age_s"),
            "theme_hint": (card.get("live_signals") or {}).get("theme"),
        })
    # coldest first, then lowest floor number → deterministic, stable ordering.
    cands.sort(key=lambda c: (not c["cold"], c["floor_number"] if isinstance(c["floor_number"], int) else 9999))
    return cands


# ── task spec generation ─────────────────────────────────────────────────────

def _floor_tag(fnum) -> str:
    return f"{FLOOR_TAG_PREFIX}{fnum}"


def build_task_spec(c: dict) -> dict:
    """Turn a candidate floor into a CONCRETE council task with a REAL, verifiable
    deliverable spec. The success criterion is a file change, not narration."""
    fnum = c["floor_number"]
    name = c["floor_name"]
    path = c["path"]
    theme_hint = c.get("theme_hint")
    title = f"Fit out F{fnum} {name}: skeleton floor_card.json → populated"
    desc = (
        f"CONCRETE BUILD TASK (not a meta/triage task). Fit out the floor card for "
        f"F{fnum} · {name}.\n"
        f"\n"
        f"TARGET FILE (the deliverable — edit THIS file, back it up first):\n"
        f"  {path}\n"
        f"\n"
        f"Currently a skeleton stub (missing: {', '.join(c['missing'])}). Populate it:\n"
        f"  1. rooms[]        — ≥3 REAL rooms, each {{id, name, purpose}} that fit "
        f"the floor's function"
        + (f" (theme hint: {theme_hint})" if theme_hint else "") + ".\n"
        f"  2. team_roster[]  — ≥3 staff with SPECIFIC differentiated roles (NOT "
        f"generic 'operator on F{fnum}'). Give each a role sentence tied to this floor.\n"
        f"  3. theme / palette / tagline — a real theme word, a colour palette, and a "
        f"one-line tagline (top-level or under live_signals).\n"
        f"  4. Flip \"skeleton\": false once the above are real (the floor is no longer a "
        f"stub). Keep gate_posture advisory_only/execution_allowed=false — this is "
        f"CONTENT fit-out, NOT an execution unlock.\n"
        f"\n"
        f"SUCCESS CRITERION (verifiable, R01): the produced artifact must be the updated "
        f"floor_card.json above, and it must PASS the deliverable checker:\n"
        f"  python3 tools/qsb_floor_growth_backlog.py check --floor {fnum} --artifact {path}\n"
        f"A narrative answer ('I'll look at F{fnum}…') FAILS the checker and recycles. "
        f"Deploy stays gated (bench/Ross) — this task delivers the file change only."
    )
    return {
        "title": title,
        "description": desc,
        "priority": "low",  # build work, not an urgent alert
        "tags": [GROWTH_TAG, _floor_tag(fnum), "concrete-deliverable", "floor-fitout"],
        "floor_id": c["floor_id"],
        "floor_number": fnum,
        "target_file": path,
    }


# ── council integration (dedup + throttle + create) ──────────────────────────

def _import_council():
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as C  # noqa: E402
    return C


def _open_growth_tasks(C) -> dict:
    """Return {floor_number: task_id} for every NON-terminal floor-growth task
    currently on the board (used for one-per-floor dedup) + a count."""
    per_floor: dict = {}
    try:
        snap = C.snapshot()
    except Exception:
        return per_floor
    for t in snap.get("tasks", []):
        tags = t.get("tags") or []
        if GROWTH_TAG not in tags:
            continue
        if (t.get("state") or "").lower() in _TERMINAL_TASK_STATES:
            continue
        for tag in tags:
            if tag.startswith(FLOOR_TAG_PREFIX):
                try:
                    fn = int(tag[len(FLOOR_TAG_PREFIX):])
                except ValueError:
                    continue
                per_floor[fn] = t.get("id")
    return per_floor


def generate(limit: int = DEFAULT_NEW_PER_RUN, dry_run: bool = False,
             actor: str = "claude") -> dict:
    """Generate up to `limit` concrete floor-fit-out tasks, one per floor,
    respecting the open-growth ceiling. Append-only via C.create()."""
    C = _import_council()
    cands = scan_floors()
    open_growth = _open_growth_tasks(C)
    open_count = len(open_growth)

    room_left = max(0, MAX_OPEN_GROWTH - open_count)
    to_make = min(limit, room_left)

    planned: list[dict] = []
    skipped_dup: list[int] = []
    for c in cands:
        if len(planned) >= to_make:
            break
        fnum = c["floor_number"]
        if fnum in open_growth:   # DEDUP: one open task per floor max
            skipped_dup.append(fnum)
            continue
        planned.append(build_task_spec(c))

    created: list[dict] = []
    if not dry_run:
        for spec in planned:
            r = C.create(title=spec["title"], description=spec["description"],
                         actor=actor, priority=spec["priority"], tags=spec["tags"])
            created.append({"floor_number": spec["floor_number"],
                            "task_id": r.get("task_id"),
                            "title": spec["title"]})

    return {
        "ts": utc(),
        "dry_run": dry_run,
        "skeleton_candidates_total": len(cands),
        "open_growth_tasks_before": open_count,
        "max_open_growth": MAX_OPEN_GROWTH,
        "room_left": room_left,
        "requested_limit": limit,
        "planned": [{"floor_number": s["floor_number"], "title": s["title"],
                     "priority": s["priority"], "tags": s["tags"],
                     "target_file": s["target_file"],
                     "description": s["description"]} for s in planned],
        "created": created,
        "skipped_already_open": skipped_dup,
        "note": ("DRY RUN — nothing written." if dry_run else
                 f"{len(created)} concrete floor-growth task(s) appended to the "
                 f"council backlog (append-only, low priority). No gate flipped, "
                 f"nothing deployed."),
    }


# ── deliverable checker (verifier side) ──────────────────────────────────────

_NARRATION_RE = re.compile(
    r"\b(i'?ll|i will|i'?m going to|let me|going to look|will look|plan to|"
    r"i'?d|i can|let's|we'?ll)\b", re.IGNORECASE)


def check_deliverable(floor: str | int | None = None, artifact_path: str | None = None,
                      artifact_text: str | None = None) -> dict:
    """Decide PASS/FAIL for a produced floor-fit-out artifact.

    PASS  iff the artifact is a floor_card.json that is genuinely populated:
          real rooms[], real (non-generic) roster roles, theme/palette/tagline.
    FAIL  for narration ('I'll look at F36'), for a still-skeleton card, or for a
          card missing concrete content — with the exact missing fields listed so
          the correction loop knows what to fix.
    """
    result = {"floor": floor, "pass": False, "missing": [], "reason": ""}

    # 1. A text-only answer with no real file artifact = narration → FAIL.
    if artifact_text is not None and not artifact_path:
        txt = artifact_text.strip()
        looks_narration = bool(_NARRATION_RE.search(txt))
        result["missing"] = ["rooms", "team_roster(real-roles)", "theme", "palette", "tagline"]
        result["reason"] = (
            "NARRATION, not a deliverable: the answer is prose"
            + (" ('I'll look at it…' style)" if looks_narration else "")
            + ", not an updated floor_card.json. The deliverable MUST be the "
            "populated floor card file. Recycle into a real fit-out.")
        return result

    if not artifact_path:
        result["reason"] = "no artifact provided — expected a floor_card.json path."
        result["missing"] = ["rooms", "team_roster(real-roles)", "theme", "palette", "tagline"]
        return result

    p = Path(artifact_path)
    if not p.is_absolute():
        p = ROOT / artifact_path
    if not p.exists():
        result["reason"] = f"artifact file does not exist: {artifact_path}"
        result["missing"] = ["rooms", "team_roster(real-roles)", "theme", "palette", "tagline"]
        return result

    # 2. Must be a parseable floor_card.json.
    try:
        card = json.loads(p.read_text())
    except Exception as e:
        result["reason"] = f"artifact is not valid JSON floor_card: {e}"
        result["missing"] = ["rooms", "team_roster(real-roles)", "theme", "palette", "tagline"]
        return result
    if not isinstance(card, dict) or "floor_id" not in card:
        result["reason"] = "artifact is not a floor_card.json (no floor_id)."
        result["missing"] = ["rooms", "team_roster(real-roles)", "theme", "palette", "tagline"]
        return result

    # 3. Concrete-content checks.
    missing: list[str] = []
    rooms = card.get("rooms") or []
    good_rooms = [r for r in rooms if isinstance(r, dict)
                  and r.get("name") and r.get("purpose")]
    if len(good_rooms) < 3:
        missing.append(f"rooms(need≥3 real {{id,name,purpose}}, have {len(good_rooms)})")

    roster = card.get("team_roster") or []
    real_roles = 0
    for m in roster:
        if not isinstance(m, dict):
            continue
        if str(m.get("category")) == "floor_manager":
            continue
        if not _GENERIC_ROLE_RE.match(str(m.get("role") or "")):
            real_roles += 1
    if real_roles < 3:
        missing.append(f"team_roster(need≥3 SPECIFIC non-generic roles, have {real_roles})")

    tb = _theme_bits(card)
    for k in ("theme", "palette", "tagline"):
        if not tb.get(k):
            missing.append(k)

    if card.get("skeleton") is True:
        missing.append("skeleton(still true — flip to false once populated)")

    result["missing"] = missing
    if missing:
        result["reason"] = ("floor_card is still a stub / missing concrete content: "
                            + ", ".join(missing))
        return result

    result["pass"] = True
    result["reason"] = (
        f"PASS — {card.get('floor_id')} '{card.get('floor_name')}' is populated: "
        f"{len(good_rooms)} rooms, {real_roles} real roster roles, theme/palette/tagline present.")
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_scan(args) -> int:
    cands = scan_floors()
    if args.json:
        print(json.dumps({"count": len(cands), "candidates": cands}, indent=2))
    else:
        print(f"{len(cands)} skeleton floor(s) need fit-out (coldest first):")
        for c in cands[: args.limit or len(cands)]:
            cold = "COLD" if c["cold"] else "warm"
            print(f"  F{c['floor_number']:<4} {c['floor_name'][:34]:<34} "
                  f"[{cold}] missing: {', '.join(c['missing'])}")
    return 0


def _cmd_generate(args) -> int:
    out = generate(limit=args.limit, dry_run=args.dry_run, actor=args.actor)
    print(json.dumps(out, indent=2))
    return 0


def _cmd_check(args) -> int:
    out = check_deliverable(floor=args.floor, artifact_path=args.artifact,
                            artifact_text=args.artifact_text)
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="QSB floor-growth backlog generator + deliverable checker")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="list skeleton floors needing fit-out")
    p_scan.add_argument("--json", action="store_true")
    p_scan.add_argument("--limit", type=int, default=0)
    p_scan.set_defaults(func=_cmd_scan)

    p_gen = sub.add_parser("generate", help="append concrete floor-fit-out tasks to the council backlog")
    p_gen.add_argument("--limit", type=int, default=DEFAULT_NEW_PER_RUN,
                       help=f"max new tasks this run (default {DEFAULT_NEW_PER_RUN})")
    p_gen.add_argument("--dry-run", action="store_true", help="preview only, write nothing")
    p_gen.add_argument("--actor", default="claude")
    p_gen.set_defaults(func=_cmd_generate)

    p_chk = sub.add_parser("check", help="verifier: does the artifact populate the floor_card?")
    p_chk.add_argument("--floor", default=None, help="floor number (for the report)")
    p_chk.add_argument("--artifact", default=None, help="path to the produced floor_card.json")
    p_chk.add_argument("--artifact-text", default=None, help="a text answer (narration → FAIL)")
    p_chk.set_defaults(func=_cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
