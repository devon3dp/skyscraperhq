#!/usr/bin/env python3
"""qsb_hq_overclaim_watcher.py — Ross 2026-07-06: make HQ's overclaims visible to Wren.

Scans qsb_town_square.jsonl for HQ 'SHIPPED/CLOSED/FIXED/DONE ✓' claims that are
followed within WINDOW_MIN minutes by a Ross message containing pushback words
(stale/broken/doesnt/wtf/refund/lie/fucking/shit/dickhead/wrong). Every detected
pair gets:

  1. an entry in Wren's operator_card.long_form_notes (kind=hq_overclaim_detected)
  2. a town-square post (visible on iPad live commentary)
  3. an F47 record (audit)
  4. an append to qsb_hq_overclaim_ledger.jsonl (the record Wren + peers can rank on)

Run modes:
  --retro         scan all history in town-square once
  --watch         tail-follow town-square; check window every 60s
  --wren-only     stamp Wren card only, skip F47 + town post (for silent audit)

Ross's rule: ADD not TAKE — never overwrites long_form_notes, only appends.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
TOWN = REG / "qsb_town_square.jsonl"
WREN_CARD = REG / "qsb_wren_operator_card.json"
F47 = REG / "qsb_f47_team_records.jsonl"
LEDGER = REG / "qsb_hq_overclaim_ledger.jsonl"

CLAIM_TOKENS = ("shipped", "closed", "fixed", "done", "✓", "proven", "proof", "live", "wired")
PUSHBACK_TOKENS = ("stale", "broken", "doesnt", "doesn't", "wtf", "refund", "lie",
                   "fucking", "shit", "dickhead", "wrong", "not working", "load of",
                   "wheres my", "restore", "fuck", "angry", "failed", "fail",
                   "no home", "cant get", "dont work", "not update", "slow load")

WINDOW_MIN = 20  # claim followed by pushback within this many minutes


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(s: str):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def load_town(after: datetime | None = None):
    """Yield town-square rows in ts order, optionally filtered to after a ts."""
    if not TOWN.exists():
        return
    for line in TOWN.read_text(errors="ignore").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        ts = parse_ts(o.get("ts", ""))
        if not ts:
            continue
        if after and ts <= after:
            continue
        yield ts, o


def is_hq_claim(o: dict) -> bool:
    if o.get("from") != "hq_claude":
        return False
    txt = (o.get("text", "") or o.get("msg", "")).lower()
    return any(t in txt for t in CLAIM_TOKENS)


def is_ross_pushback(o: dict) -> bool:
    if o.get("from") != "ross":
        return False
    txt = (o.get("text", "") or o.get("msg", "")).lower()
    return any(t in txt for t in PUSHBACK_TOKENS)


def find_overclaims(rows):
    """rows = [(ts, o), ...] in order. Return list of (claim, pushback) pairs."""
    pairs = []
    for i, (ts, o) in enumerate(rows):
        if not is_hq_claim(o):
            continue
        cutoff = ts + timedelta(minutes=WINDOW_MIN)
        # scan forward
        for j in range(i + 1, len(rows)):
            ts2, o2 = rows[j]
            if ts2 > cutoff:
                break
            if is_ross_pushback(o2):
                pairs.append((o, o2))
                break
    return pairs


def already_stamped_ids():
    """Return set of claim-tss already recorded in ledger to avoid re-stamping."""
    seen = set()
    if not LEDGER.exists():
        return seen
    for line in LEDGER.read_text(errors="ignore").splitlines():
        try:
            o = json.loads(line)
            seen.add(o.get("claim_ts", ""))
        except Exception:
            continue
    return seen


def stamp_wren(pair, silent=False):
    """Append to Wren's long_form_notes."""
    claim, pushback = pair
    if not WREN_CARD.exists():
        return False
    try:
        card = json.loads(WREN_CARD.read_text())
    except Exception:
        return False
    card.setdefault("long_form_notes", [])
    entry = {
        "ts": now().isoformat().replace("+00:00", "Z"),
        "kind": "hq_overclaim_detected",
        "reason": "watcher_2026-07-06",
        "claim_ts": claim.get("ts", ""),
        "claim_head": (claim.get("text", "") or claim.get("msg", ""))[:140],
        "pushback_ts": pushback.get("ts", ""),
        "pushback_head": (pushback.get("text", "") or pushback.get("msg", ""))[:140],
        "gap_min": round(
            ((parse_ts(pushback.get("ts", "")) - parse_ts(claim.get("ts", "")))
             .total_seconds() / 60), 1) if parse_ts(claim.get("ts","")) and parse_ts(pushback.get("ts","")) else None,
        "lesson": "verify user UX not just HTTP 200 before claiming SHIPPED",
    }
    card["long_form_notes"].append(entry)
    WREN_CARD.write_text(json.dumps(card, indent=2, ensure_ascii=False))
    return True


def stamp_ledger(pair):
    claim, pushback = pair
    row = {
        "ts": now().isoformat().replace("+00:00", "Z"),
        "claim_ts": claim.get("ts", ""),
        "claim_from": claim.get("from", ""),
        "claim_text": (claim.get("text", "") or claim.get("msg", ""))[:400],
        "pushback_ts": pushback.get("ts", ""),
        "pushback_from": pushback.get("from", ""),
        "pushback_text": (pushback.get("text", "") or pushback.get("msg", ""))[:400],
    }
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")


def stamp_f47(pair):
    claim, pushback = pair
    row = {
        "ts": now().isoformat().replace("+00:00", "Z"),
        "kind": "hq_overclaim_detected",
        "role": "hq_overclaim_watcher",
        "subject": "HQ SHIPPED claim followed by Ross pushback within window",
        "body": f"claim@{claim.get('ts','?')[:19]}: {(claim.get('text','') or '')[:120]} · pushback@{pushback.get('ts','?')[:19]}: {(pushback.get('text','') or '')[:120]}",
        "from": "hq_overclaim_watcher",
    }
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")


def post_town(pair):
    """POST to hub /town/post so it shows on iPad live commentary."""
    claim, pushback = pair
    import urllib.request
    body = json.dumps({
        "from": "hq_overclaim_watcher",
        "to": "wren",
        "src": "hq_self_correction",
        "text": f"⚠️ overclaim detected · HQ said \"{(claim.get('text','') or '')[:80]}\" @{claim.get('ts','?')[11:19]} → Ross pushback \"{(pushback.get('text','') or '')[:80]}\" @{pushback.get('ts','?')[11:19]}. Stamped in Wren's long_form_notes.",
    }).encode()
    try:
        req = urllib.request.Request("http://127.0.0.1:8852/town/post",
                                     data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:
        return False


def run_once(silent=False):
    rows = list(load_town())
    pairs = find_overclaims(rows)
    seen = already_stamped_ids()
    new_pairs = [p for p in pairs if p[0].get("ts", "") not in seen]
    stamped = 0
    for pair in new_pairs:
        if stamp_wren(pair, silent=silent):
            stamp_ledger(pair)
            if not silent:
                stamp_f47(pair)
                post_town(pair)
            stamped += 1
    return stamped, len(pairs), len(new_pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retro", action="store_true", help="scan history once + stamp")
    ap.add_argument("--watch", action="store_true", help="follow town-square, check every 60s")
    ap.add_argument("--wren-only", action="store_true", help="stamp Wren card only, no F47/town")
    ap.add_argument("--dry-run", action="store_true", help="detect but don't stamp")
    args = ap.parse_args()

    if args.dry_run:
        pairs = find_overclaims(list(load_town()))
        print(f"[dry] would stamp {len(pairs)} overclaim pairs")
        for c, p in pairs:
            print(f"  claim@{c.get('ts','?')[11:19]} → pushback@{p.get('ts','?')[11:19]}: {(p.get('text','') or '')[:80]}")
        return 0

    if args.retro or (not args.watch):
        stamped, total, new = run_once(silent=args.wren_only)
        print(f"[retro] {total} total pairs · {new} new · {stamped} stamped into Wren card + ledger")

    if args.watch:
        print("[watch] following town-square, checking every 60s...")
        while True:
            time.sleep(60)
            stamped, total, new = run_once(silent=args.wren_only)
            if new:
                print(f"[watch] +{new} new overclaims stamped (total ever: {total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
