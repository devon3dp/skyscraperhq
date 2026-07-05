#!/usr/bin/env python3
"""qsb_codebase_audit_run.py — one tick of the F47 codebase audit crew.

Ross 2026-06-13: "yes ... wire auto sig etc" — the engine that produces work.

Each tick picks ONE track (round-robin via state file) and scans the codebase
through that lens. Writes 1-3 proposals to qsb_code_proposals.jsonl.

Tracks (v1):
  graphics_new_photos   — re-scan ~/Pictures/Screenshots for unseen images
  name_map_extension    — qsb_floor_name_map.json only has 0-55, propose 56-165
  route_health          — server.py declares routes; check for orphaned wiring
  shop_catalog_gaps     — find storefronts with missing prices/descriptions
  dead_imports          — find python files importing missing names

Bounded: at most 3 proposals per tick. Always stamps a F47 record.
"""
from __future__ import annotations
import json, sys, os, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"
STATE = ROOT / "data/registries/qsb_audit_crew_state.json"

TRACKS = [
    "graphics_new_photos",
    "name_map_extension",
    "route_health",
    "shop_catalog_gaps",
    "dead_imports",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"track_cursor": 0, "ticks": 0, "proposals_total": 0}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2))


def write_proposal(p: dict) -> str:
    PROPOSALS.parent.mkdir(parents=True, exist_ok=True)
    p.setdefault("id", f"audit-{utcnow()}-{p.get('track','x')}-{os.getpid()}")
    p.setdefault("ts", utcnow())
    p.setdefault("approved_by_ross", None)
    p.setdefault("applied", False)
    p.setdefault("sigs", [])
    with PROPOSALS.open("a") as f:
        f.write(json.dumps(p) + "\n")
    return p["id"]


# ── track scanners ────────────────────────────────────────────────────

def track_graphics_new_photos() -> list[dict]:
    """If new screenshots arrived, queue a graphics_research run."""
    state_path = ROOT / "data/registries/qsb_graphics_research_state.json"
    photos = Path("/home/ross/Pictures/Screenshots")
    if not photos.exists():
        return []
    on_disk = len(list(photos.glob("Screenshot from *.png")))
    seen = 0
    if state_path.exists():
        try:
            seen = len(json.loads(state_path.read_text()).get("analyzed_hashes", []))
        except Exception:
            pass
    delta = on_disk - seen
    if delta <= 0:
        return []
    return [{
        "from": "f47.architect.audit_crew",
        "track": "graphics_new_photos",
        "kind": "trigger_graphics_run",
        "reason": f"{delta} new screenshots in folder, not yet analyzed",
        "target_files": ["data/registries/qsb_graphics_research_state.json"],
        "concrete_change": {
            "action": "invoke tools/qsb_graphics_research_crew.py next tick",
        },
    }]


def track_name_map_extension() -> list[dict]:
    """qsb_floor_name_map.json holds floors 0-55 only; tower has 165 floors.
    Propose extending it from the unified state."""
    nm_path = ROOT / "data/registries/qsb_floor_name_map.json"
    try:
        nm = json.loads(nm_path.read_text())
        m = nm.get("name_map", {})
        max_in_map = max((int(k) for k in m if k.isdigit()), default=0)
    except Exception:
        return []
    if max_in_map >= 165:
        return []
    # Read unified for 56-165 names
    try:
        unified_path = ROOT / "data/registries/qsb_floor_interior_master_registry.json"
        unified = json.loads(unified_path.read_text())
    except Exception:
        return []
    floors = unified.get("floors", []) if isinstance(unified, dict) else unified
    missing = {}
    for f in floors:
        if not isinstance(f, dict):
            continue
        # floor_id is "F01", "F100" etc — parse the integer
        fid = f.get("floor_id") or ""
        try:
            n = int(fid[1:]) if fid.startswith("F") else int(
                f.get("number") or f.get("floor") or 0)
        except Exception:
            continue
        if not isinstance(n, int) or n <= max_in_map or n > 165:
            continue
        name = f.get("floor_name") or f.get("canonical_name") or f.get("department")
        if name:
            missing[str(n)] = name
    if not missing:
        return []
    return [{
        "from": "f47.architect.audit_crew",
        "track": "name_map_extension",
        "kind": "registry_extension_proposal",
        "reason": (f"qsb_floor_name_map.json covers floors 0-{max_in_map} "
                    f"but tower has 165 floors. Cockpit + Godot read this map "
                    f"for floor labels; floors beyond {max_in_map} fall back to "
                    f"generic. Proposing to extend with {len(missing)} entries "
                    f"from the unified registry."),
        "target_files": ["data/registries/qsb_floor_name_map.json"],
        "concrete_change": {
            "operation": "merge_dict",
            "into": "name_map",
            "values": missing,
        },
    }]


def track_route_health() -> list[dict]:
    """Find routes declared in server.py that point at endpoint paths but have
    no handler. Conservative: report findings, don't propose patches yet."""
    server = ROOT / "src/dashboard/server.py"
    if not server.exists():
        return []
    try:
        text = server.read_text()
    except Exception:
        return []
    # cheap heuristic: lines like `if path == "/api/foo"` should have a
    # send_json or send_html within ~40 lines below them. Skip for now —
    # this track will produce a real proposal once the scanner is mature.
    # v1: only flag if there are TODO/XXX/FIXME markers
    flags = []
    for i, ln in enumerate(text.splitlines()):
        if any(tag in ln for tag in ("TODO", "XXX", "FIXME")):
            flags.append({"line": i+1, "text": ln.strip()[:120]})
    if not flags:
        return []
    return [{
        "from": "f47.builder.audit_crew",
        "track": "route_health",
        "kind": "todo_audit_report",
        "reason": (f"server.py has {len(flags)} TODO/XXX/FIXME markers — "
                    f"flagged for review, not auto-patched"),
        "target_files": ["src/dashboard/server.py"],
        "concrete_change": {
            "action": "review_only",
            "todo_lines": flags[:10],
        },
    }]


def track_shop_catalog_gaps() -> list[dict]:
    """Find shop catalog JSONs with SKUs missing price or description."""
    reg = ROOT / "data/registries"
    catalogs = list(reg.glob("qsb_floor*catalog*.json"))
    gaps = []
    for cp in catalogs[:25]:
        try:
            c = json.loads(cp.read_text())
        except Exception:
            continue
        items = (c.get("items") if isinstance(c, dict) else None) or \
                (c.get("skus") if isinstance(c, dict) else None) or \
                (c.get("products") if isinstance(c, dict) else None) or []
        miss_price = 0
        miss_desc = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            if not it.get("price") and not it.get("price_gbp") and not it.get("price_usd"):
                miss_price += 1
            if not it.get("description") and not it.get("desc") and not it.get("blurb"):
                miss_desc += 1
        if miss_price + miss_desc > 0:
            gaps.append({"catalog": cp.name, "items": len(items),
                          "missing_price": miss_price, "missing_description": miss_desc})
    if not gaps:
        return []
    return [{
        "from": "f47.fitter.audit_crew",
        "track": "shop_catalog_gaps",
        "kind": "catalog_quality_report",
        "reason": (f"{len(gaps)} shop catalogs have items missing price or "
                    f"description — flagged for content team"),
        "target_files": [],
        "concrete_change": {
            "action": "review_and_research",
            "catalog_gaps": gaps[:10],
        },
    }]


def track_dead_imports() -> list[dict]:
    """Python files importing names that don't exist as modules / files."""
    # v1: scan tools/*.py for `from tower.X import Y` where X doesn't exist.
    tools_dir = ROOT / "tools"
    findings = []
    for py in list(tools_dir.glob("*.py"))[:40]:
        try:
            src = py.read_text()
        except Exception:
            continue
        for ln in src.splitlines():
            ln_s = ln.strip()
            if ln_s.startswith("from tower.") and " import " in ln_s:
                mod = ln_s.split("from tower.")[1].split(" import ")[0].strip()
                # check src/tower/<mod>.py or src/tower/<mod>/__init__.py
                mod_path = ROOT / "src/tower" / mod.replace(".", "/")
                if not mod_path.with_suffix(".py").exists() and \
                   not (mod_path / "__init__.py").exists():
                    findings.append({"file": py.name, "import": ln_s[:120]})
                    if len(findings) >= 6:
                        break
        if len(findings) >= 6:
            break
    if not findings:
        return []
    return [{
        "from": "f47.builder.audit_crew",
        "track": "dead_imports",
        "kind": "broken_import_report",
        "reason": (f"{len(findings)} python files import tower.X modules that "
                    f"don't exist at src/tower/<X>"),
        "target_files": [],
        "concrete_change": {
            "action": "investigate",
            "findings": findings,
        },
    }]


SCANNERS = {
    "graphics_new_photos": track_graphics_new_photos,
    "name_map_extension":  track_name_map_extension,
    "route_health":        track_route_health,
    "shop_catalog_gaps":   track_shop_catalog_gaps,
    "dead_imports":        track_dead_imports,
}


def main():
    state = load_state()
    cursor = state.get("track_cursor", 0) % len(TRACKS)
    track = TRACKS[cursor]
    state["track_cursor"] = (cursor + 1) % len(TRACKS)
    state["ticks"] = state.get("ticks", 0) + 1

    scanner = SCANNERS[track]
    try:
        proposals = scanner()
    except Exception as exc:
        proposals = []
        err = str(exc)[:200]
    else:
        err = None

    written = []
    for p in proposals[:3]:
        pid = write_proposal(p)
        written.append(pid)

    state["proposals_total"] = state.get("proposals_total", 0) + len(written)
    save_state(state)

    rec = {
        "ts": utcnow(),
        "kind": "audit_crew_tick",
        "floor": "F47",
        "operator": "background",
        "executed_by": f"f47.audit_crew.{track}",
        "track": track,
        "proposals_written": len(written),
        "proposal_ids": written,
        "ticks_total": state["ticks"],
        "proposals_total": state["proposals_total"],
        "error": err,
    }
    with F47_REC.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
