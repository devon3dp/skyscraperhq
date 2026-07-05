#!/usr/bin/env python3
"""qsb_floor_rooms_generate.py — STAGE C of the per-floor walkable interiors
workstream. For floors without rooms/, call qwen2.5:7b once per floor with
the floor_card (archetype + tour_blurb + team_roster) and ask the local model
to propose 3-7 unique rooms each with layout/render/interactive blocks.

Agreed in qsb_claude_wren_bridge.jsonl turns 32-33 (2026-06-20):
  Q3 — per-floor qwen call for the 166 floors. Slower than a lookup table
       but produces unique fit-outs per Ross's "every floor is unique" rule.

Run:
  # Dry run — print decisions, don't write anything
  python3 tools/qsb_floor_rooms_generate.py --floors 41,44,57,80,165 --dry-run

  # Apply to a subset
  python3 tools/qsb_floor_rooms_generate.py --floors 41,44,57,80,165

  # Apply to ALL floors lacking a rooms/ dir (slow — ~14 min for 166 floors)
  python3 tools/qsb_floor_rooms_generate.py --all-missing
"""
from __future__ import annotations
import argparse, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS = ROOT / "floors"
LOG = ROOT / "data/registries/qsb_floor_rooms_generation.jsonl"

SCHEMA_REMINDER = """Each room is one JSON object:
{
  "room_id": "snake_case",
  "name": "Human Title",
  "category": "operations|workshop|audit|security|admin|reception|library|seating|kitchen|display|lab|trading|window",
  "purpose": "this room is for ... (one sentence)",
  "concierge_blurb": "What a visitor sees when they enter. One sentence.",
  "current_state": "already_exists",
  "visitor_open": true,
  "evidence_paths": [],
  "live_signals": {},
  "layout": {
    "zone": "back_center|back_left|back_right|back_wall|center|front_center|front_left|front_right|left_wall|right_wall",
    "offset_x": -8.0 to 8.0 (relative to 18x18 floor center; -X is left),
    "offset_z": -8.0 to 8.0 (relative to floor center; -Z is back),
    "footprint_m": [width, depth],
    "height_m": 0.4 to 2.5
  },
  "render": {
    "primary_prop": "desk|dais|wall_panel|plinth|bench|chamber|archive_shelf|chair_set|display|reception|seating|kitchen_line|trading_desk|server_rack|library_shelf|garden_bed|altar",
    "palette": "embassy_brass_wren_green",
    "label_text": "SHORT IN-WORLD LABEL (max 20 chars)",
    "glow": true|false
  },
  "interactive": {
    "type": "live_data|toggle|tail|count|none",
    "source_path": "data/registries/<file>.jsonl|.json|null",
    "display": "scrolling_list|big_number|status_dot|none",
    "refresh_seconds": 30 to 600
  }
}"""


def _ollama(prompt: str, system: str, model="qwen2.5:7b-instruct",
            timeout=180) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "system": system,
                       "stream": False,
                       "options": {"temperature": 0.6, "num_predict": 1800}}
                      ).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"]


def _extract_json_array(text: str):
    """Pull the first top-level JSON array out of the model's reply,
    forgiving extra prose either side."""
    m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if not m:
        return None, "no_array_found"
    raw = m.group(0)
    # Try strict parse first
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        # Fix trailing commas
        cleaned = re.sub(r",(\s*[\]\}])", r"\1", raw)
        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError as e2:
            return None, f"json_decode_fail: {e2}"


def _floor_paths():
    out = []
    for d in sorted(FLOORS.iterdir()):
        m = re.match(r"floor_(\d+)_(.+)", d.name)
        if not m:
            continue
        n = int(m.group(1))
        out.append((n, d))
    return out


def _floor_card(d: Path):
    fc = d / "floor_card.json"
    if not fc.exists():
        return None
    try:
        return json.loads(fc.read_text())
    except Exception:
        return None


def _has_rooms(d: Path):
    rdir = d / "rooms"
    return rdir.exists() and any(rdir.glob("*.json"))


def _log_row(row: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _floor_dims(template: str, department: str, name: str):
    """Mirror cockpit3d's _officeDims sizing so generator + renderer agree."""
    txt = f"{template} {department} {name}".lower()
    import re
    if re.search(r"tradingfloor|restaurant|district|grandlibrary|libraryfloor|shopping|mall|botanical|cinema|observatory|museum|brewery|distillery|hall", txt):
        return (60, 60, 5)
    if re.search(r"council|opspit|classroom|vaultchamber|studio|chapel|kitchen|workshop|gym|wellness|labfloor|laboratory|accounts|bank|exchange|operations|command", txt):
        return (40, 40, 4)
    return (35, 35, 4)


def generate_for_floor(n: int, fdir: Path, fcard: dict, dry_run: bool,
                       master_entry: dict | None = None):
    name = fcard.get("floor_name") or fcard.get("name") or fdir.name
    archetype = fcard.get("archetype", "operations")
    department = (master_entry or {}).get("department", "")
    template = (master_entry or {}).get("template", "")
    blurb = (fcard.get("tour_blurb") or "")[:600]
    roster = fcard.get("team_roster", [])
    roster_lines = "; ".join(
        f"{r.get('role','?')} ({r.get('category','?')})" for r in roster[:4]
    )
    W, D, _H = _floor_dims(template, department, name)
    # Useful offset range so qwen places props inside the walls.
    halfW = W / 2 - 2.0
    halfD = D / 2 - 2.0
    prompt = (
        f"Floor {n} — {name}.\n"
        f"Department: {department or '(unspecified)'}.\n"
        f"Template/archetype: {template or archetype}.\n"
        f"Floor dimensions: {W}m × {D}m × skyscraper-scale.\n"
        f"Allowed offset_x range: -{halfW:.1f} to +{halfW:.1f} (in meters from center).\n"
        f"Allowed offset_z range: -{halfD:.1f} to +{halfD:.1f} (in meters from center).\n"
        f"Tour blurb: {blurb}\n"
        f"Team roster excerpt: {roster_lines or 'none'}\n\n"
        f"This floor IS THE {department or archetype} DEPARTMENT. Design 4 to 7"
        f" UNIQUE rooms that physically express THIS department's work. Do NOT"
        f" produce a generic office — props must visibly say what this"
        f" department does (trading desks for a trading floor; book stacks +"
        f" reading chairs for a library; pots + dining tables for a restaurant;"
        f" vault doors + ledgers for accounts; sermon altar for a chapel; etc.).\n\n"
        f"Spread the rooms across the {W}m × {D}m floor so a visitor walking"
        f" from the front entry sees a clear journey, not a cluster.\n\n"
        f"Respond with a JSON array, NO PROSE BEFORE OR AFTER. Each"
        f" object must match this exact schema:\n{SCHEMA_REMINDER}"
    )
    system = (
        "You are a 3D room layout designer for the QSB Tower's per-floor"
        " walkable interiors. You answer with valid JSON only, no markdown"
        " fences. Every floor is unique — pick props that match THIS"
        " floor's archetype + tour blurb."
    )
    t0 = time.time()
    try:
        reply = _ollama(prompt, system)
    except Exception as e:
        return {"floor": n, "ok": False, "reason": f"ollama_call_fail: {e}",
                "wall_s": time.time() - t0}
    arr, err = _extract_json_array(reply)
    if err:
        return {"floor": n, "ok": False, "reason": err,
                "raw_preview": reply[:300], "wall_s": time.time() - t0}
    # Write each room. Set floor field even if model forgot.
    written = []
    if not dry_run:
        rdir = fdir / "rooms"
        rdir.mkdir(parents=True, exist_ok=True)
    for room in arr:
        rid = room.get("room_id") or "unnamed"
        rid = re.sub(r"[^a-z0-9_]+", "_", str(rid).lower()).strip("_") or "unnamed"
        room["room_id"] = rid
        room.setdefault("floor", f"floor_{n}")
        if not dry_run:
            (fdir / "rooms" / f"{rid}.json").write_text(
                json.dumps(room, indent=2) + "\n")
        written.append(rid)
    return {"floor": n, "ok": True, "rooms": written,
            "wall_s": round(time.time() - t0, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floors", help="comma-separated floor numbers e.g. 41,44,57")
    ap.add_argument("--all-missing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="regenerate even when rooms/ already populated")
    args = ap.parse_args()

    all_floors = _floor_paths()

    # Pre-load floor master registry once for department/template hints.
    master_index = {}
    try:
        mreg = json.loads(
            (ROOT / "data/registries/qsb_floor_master_registry.json").read_text())
        for fe in mreg.get("floors", []):
            fid = fe.get("floor_id", "")
            if fid.startswith("F") and fid[1:].isdigit():
                master_index[int(fid[1:])] = fe
    except Exception:
        pass

    if args.floors:
        target_nums = set(int(x) for x in args.floors.split(","))
        targets = [(n, d) for (n, d) in all_floors if n in target_nums]
    elif args.all_missing:
        targets = [(n, d) for (n, d) in all_floors if not _has_rooms(d)]
    else:
        ap.error("must pass --floors N,M,... or --all-missing")

    results = []
    for n, d in targets:
        fcard = _floor_card(d)
        if fcard is None:
            results.append({"floor": n, "ok": False, "reason": "no_floor_card"})
            continue
        if _has_rooms(d) and not args.dry_run and not args.force:
            results.append({"floor": n, "ok": False, "reason": "rooms_already_exist"})
            continue
        print(f"[F{n:03d}] generating ...", flush=True)
        r = generate_for_floor(n, d, fcard, args.dry_run,
                               master_index.get(n))
        print(f"[F{n:03d}] {r.get('ok')} {r.get('reason') or r.get('rooms')}",
              flush=True)
        _log_row({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  **r})
        results.append(r)
    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"\nSummary: {ok} ok, {fail} fail, {len(results)} total")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
