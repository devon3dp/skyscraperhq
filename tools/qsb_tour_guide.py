#!/usr/bin/env python3
"""qsb_tour_guide.py — Skyscraper Tour Guide service.

Ross 2026-06-13: "Like film companies have tour guides that take people around
the set, I want to offer tours of the skyscraper so people get to observe what's
happening. They can't change anything, but they can get to go in rooms and have
a look if they've got an access code that lets them on the tour."

The tour is READ-ONLY by design — visitors see floors, see workers, hear
narration, but cannot click anything that triggers an action. This aligns with
the helix strand "builds rooms with no execution console": the tour floor IS
a viewing gallery, not a control surface.

Mechanism:
  · Tour codes are minted by Ross (or a Tour Guide worker on his behalf)
    via mint_code(). Each code carries an issued_ts, expires_ts, max_floors,
    and an audit row in qsb_tour_codes.jsonl.
  · Tour Guide workers are a new role on F47 (added to the roster by the
    audit-crew makeover team). Each tour assigns one Guide who narrates.
  · Visitors send GET /api/tour/{code}/floor/{N} → returns a sanitized view
    of floor N (name, rooms, workers anonymized, narration line). No POSTs
    accepted in the tour namespace.

Audit:
  · Every code mint, redemption, floor view, and code expiry stamps a F47
    record with kind="tour_*". So Wren sees who's touring what, when.
"""
from __future__ import annotations
import json, sys, hashlib, secrets, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CODES = ROOT / "data/registries/qsb_tour_codes.jsonl"
VIEWS = ROOT / "data/registries/qsb_tour_views.jsonl"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"

# Floors the tour CAN show. Excludes: vault, kernel internals, F47 itself
# (private to Wren), real-money trading details (F44 ledger sums only).
PUBLIC_TOUR_FLOORS = list(range(1, 56)) + list(range(56, 166))
PRIVATE_NOT_TOURABLE = {
    28,   # Security / vault
    47,   # Wren's embassy — private
    153,  # Penthouse (kernel reserve)
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utcnow_dt() -> datetime:
    return datetime.now(timezone.utc)


def append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def mint_code(issued_to: str = "", hours_valid: int = 24,
              max_floors: int = 20) -> dict:
    code = secrets.token_urlsafe(8)
    rec = {
        "ts": utcnow(),
        "kind": "tour_code_minted",
        "code": code,
        "issued_to": issued_to,
        "issued_by": "Ross",
        "issued_ts": utcnow(),
        "expires_ts": (utcnow_dt() + timedelta(hours=hours_valid)).isoformat()
                      .replace("+00:00", "Z"),
        "max_floors_per_visit": max_floors,
        "revoked": False,
        "redemptions": 0,
    }
    append_jsonl(CODES, rec)
    append_jsonl(F47_REC, {
        "ts": utcnow(), "kind": "tour_code_minted", "floor": "F47",
        "operator": "Ross", "executed_by": "Wren",
        "code_prefix": code[:4] + "…", "issued_to": issued_to,
        "hours_valid": hours_valid,
    })
    return rec


def lookup_code(code: str) -> dict | None:
    """Return the latest state of a code (folding in revocations + redemption count)."""
    rows = [r for r in read_jsonl(CODES) if r.get("code") == code]
    if not rows:
        return None
    base = rows[0]
    redemptions = sum(1 for r in rows if r.get("kind") == "tour_code_redemption")
    revoked = any(r.get("kind") == "tour_code_revoked" for r in rows)
    base = dict(base)
    base["redemptions"] = redemptions
    base["revoked"] = revoked
    return base


def is_code_valid(code: str) -> tuple[bool, str]:
    rec = lookup_code(code)
    if not rec:
        return False, "code not recognized"
    if rec.get("revoked"):
        return False, "code revoked"
    expires = rec.get("expires_ts")
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if utcnow_dt() > exp:
                return False, "code expired"
        except Exception:
            pass
    return True, "ok"


def revoke_code(code: str, reason: str = "") -> dict:
    rec = {"ts": utcnow(), "kind": "tour_code_revoked",
            "code": code, "reason": reason}
    append_jsonl(CODES, rec)
    append_jsonl(F47_REC, {
        "ts": utcnow(), "kind": "tour_code_revoked", "floor": "F47",
        "operator": "Ross", "executed_by": "Wren",
        "code_prefix": code[:4] + "…", "reason": reason,
    })
    return rec


def sanitize_floor_view(floor_num: int) -> dict:
    """Read-only public-safe view of a floor. No actions, no sensitive data."""
    if floor_num in PRIVATE_NOT_TOURABLE:
        return {"ok": False,
                "error": f"F{floor_num} is private — not on the tour route"}
    if floor_num not in PUBLIC_TOUR_FLOORS:
        return {"ok": False, "error": f"F{floor_num} does not exist"}
    try:
        unified = json.loads(
            (ROOT / "data/registries/qsb_floor_interior_master_registry.json")
            .read_text())
        floors = unified.get("floors", [])
        target = next((f for f in floors
                        if f.get("floor_id") == f"F{floor_num:02d}"), None)
        if not target:
            return {"ok": False, "error": f"F{floor_num} not in registry"}
    except Exception as exc:
        return {"ok": False, "error": f"registry read failed: {str(exc)[:80]}"}

    workers_anon = []
    for i, w in enumerate(target.get("workers", [])[:20]):
        workers_anon.append({
            "label": f"Worker {chr(ord('A') + i % 26)}{i // 26 if i >= 26 else ''}",
            "role": w.get("role", "tower worker"),
            "doing": "(currently on shift)",
        })

    return {
        "ok": True,
        "floor": floor_num,
        "floor_name": target.get("floor_name"),
        "department": target.get("department"),
        "rooms_open_to_tour": [r for r in target.get("rooms", [])
                                if r.lower() not in ("vault", "private")],
        "workers": workers_anon,
        "narration": narration_for(floor_num, target),
        "interactive": False,
        "tour_advisory": "You can look but not touch — this is a read-only tour.",
    }


def narration_for(floor_num: int, target: dict) -> str:
    name = target.get("floor_name", f"Floor {floor_num}")
    dept = target.get("department", "tower operations")
    workers_n = target.get("worker_count", 0)
    return (f"Welcome to {name}. This is where {dept} happens in the tower. "
            f"Today there are around {workers_n} workers on this floor. "
            f"Please take a look around — you cannot change anything from the "
            f"tour, but you can observe what's happening.")


def visit(code: str, floor_num: int) -> dict:
    ok, why = is_code_valid(code)
    if not ok:
        return {"ok": False, "error": why}
    view = sanitize_floor_view(floor_num)
    rec = {"ts": utcnow(), "kind": "tour_code_redemption",
            "code": code, "floor": floor_num,
            "view_ok": view.get("ok")}
    append_jsonl(CODES, rec)
    append_jsonl(VIEWS, {"ts": utcnow(), "code_prefix": code[:4] + "…",
                          "floor": floor_num})
    append_jsonl(F47_REC, {
        "ts": utcnow(), "kind": "tour_floor_visited", "floor": "F47",
        "operator": "Visitor", "executed_by": "tour_guide",
        "code_prefix": code[:4] + "…", "visited_floor": floor_num,
    })
    return view


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_m = sub.add_parser("mint")
    p_m.add_argument("--to", default="anonymous")
    p_m.add_argument("--hours", type=int, default=24)
    p_v = sub.add_parser("visit")
    p_v.add_argument("--code", required=True)
    p_v.add_argument("--floor", type=int, required=True)
    p_r = sub.add_parser("revoke")
    p_r.add_argument("--code", required=True)
    p_r.add_argument("--reason", default="manual revoke")
    sub.add_parser("list")

    args = ap.parse_args()
    if args.cmd == "mint":
        print(json.dumps(mint_code(args.to, args.hours), indent=2))
    elif args.cmd == "visit":
        print(json.dumps(visit(args.code, args.floor), indent=2))
    elif args.cmd == "revoke":
        print(json.dumps(revoke_code(args.code, args.reason), indent=2))
    elif args.cmd == "list":
        codes = {r["code"]: r for r in read_jsonl(CODES)
                  if r.get("kind") == "tour_code_minted"}
        print(json.dumps({"codes_minted": len(codes),
                           "codes": list(codes.values())[-10:]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
