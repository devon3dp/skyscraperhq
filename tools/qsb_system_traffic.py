#!/usr/bin/env python3
"""
qsb_system_traffic.py — REAL traffic emitter for the tower systems that were
SILENT on the Underground map (:8875).

Ross ("all working with all the trains ... moving information where it needs to
go"): every LIVE tower system must show its genuine traffic as trains, so no
active system is dark. The map (tools/qsb_tower_transit_map.py) already reads
several logs DIRECTLY (gene-pool router calls, council tasks, leadership
room/acks/dm, OANDA fills, portfolio pot, belief ticks, wren-chat). A sibling
(tools/qsb_lift_traffic.py) owns the inter-zone LIFT movements (worker needs
deliveries, chain reports, leadership comms along real lift shafts). This tool
covers the REMAINING live systems that produced NO visible train:

  A. Boardroom commentary   data/registries/qsb_boardroom_commentary.jsonl
       a real board post / watcher alert -> the Boardroom hub.
       from = resolved poster (wren/asa/bill/tp/hermes) else task_council
              (watcher/SLA/CEO-cap events come from the council machinery);
              a `who=<x>` state_change row -> that actor.
       to   = boardroom.                                       cat = comms
  B. Boardroom hub activity  data/registries/qsb_boardroom_hub_activity.jsonl
       a real compose/broadcast -> the Boardroom hub (or the named recipient
       when it resolves, e.g. wren->hermes).                   cat = comms
  C. Gene-pool router live events  data/registries/gene_pool_router_live_events.jsonl
       a real router/scanner event (auto_scan, admit, route, probe) touching the
       Gene Pool secure store. from = named provider when placeable, else the
       Gene Pool itself reporting; to = gene_pool.             cat = route
  D. Provider ADVISORY consult calls  data/registries/qsb_tower_activity_tail.jsonl
       event_kind == "provider_call" — the $1/day advisory second-opinion path
       (tools/qsb_consult_external.py), DISTINCT from qsb_brain_router_calls.jsonl
       (which the map already draws). Each real call is a round trip:
       gene_pool -> provider (request) and provider -> gene_pool (reply).  cat = provider
  E. F47 team records  data/registries/qsb_f47_team_records.jsonl
       a real F47 stamp (audit/ledger/activation tick/oanda pull) -> the Task
       Council ledger. from = resolved operator (wren/asa/bill/tp) else
       task_council's own machinery reporting to itself is skipped; unresolved
       operators (claude / engine names) route from wren (the governor who owns
       the F47 ledger) -> task_council.                        cat = council

HONESTY (R01): a train is emitted ONLY for a REAL event that carries a real,
parseable timestamp and a real source row. Every emitted row carries real=true,
its own `source` path, and a label quoting the real event. Endpoints must both
resolve to a real map station (hub node-id or placeable floor number) or the row
is skipped, never faked. Events older than --window seconds (default 900 = the
map's AGE_MAX) are skipped (they would never animate anyway). Nothing invented.

NON-DUPLICATION: this tool deliberately does NOT touch the sources already drawn
by the map's direct readers, nor the needs/chain/comms LIFT movements owned by
qsb_lift_traffic.py. It ONLY covers boardroom / gene / provider-consult / F47.

TOPOLOGY ONLY: reads real registries, APPENDS rows to the shared feed. Executes
nothing, dispatches nothing, flips no gate, places no order.

OUTPUT (append-only, shared with siblings):
  data/registries/qsb_map_traffic_feed.jsonl
  {"ts","from":<node/floor>,"to":<node/floor>,"cat","label","real":true,"source"}

RATE LIMIT / BOUND: at most --max rows per run (default 60). Own cursor at
data/registries/qsb_system_traffic_cursor.json (sha1 sigs) prevents re-emitting
the same event twice. Idempotent across runs.

USAGE:
  python3 tools/qsb_system_traffic.py            # emit new system traffic
  python3 tools/qsb_system_traffic.py --dry-run  # show what WOULD emit, write nothing
  python3 tools/qsb_system_traffic.py --max 40 --window 900
"""
from __future__ import annotations
import argparse, json, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"

FEED = REG / "qsb_map_traffic_feed.jsonl"            # SHARED, append-only
CURSOR = REG / "qsb_system_traffic_cursor.json"      # OURS only

BOARDROOM_COMMENTARY = REG / "qsb_boardroom_commentary.jsonl"
BOARDROOM_HUB        = REG / "qsb_boardroom_hub_activity.jsonl"
GENE_LIVE            = REG / "gene_pool_router_live_events.jsonl"
ACTIVITY_TAIL        = REG / "qsb_tower_activity_tail.jsonl"
F47_RECORDS          = REG / "qsb_f47_team_records.jsonl"

# Hub node-ids the map knows (STATIONS keys) + comms aliases the map resolves.
HUB_IDS = {
    "wren", "codex", "bill", "tp_pip", "acer_cass", "task_council", "boardroom",
    "town_square", "council15", "gene_pool", "oracle", "f10_traders", "f41_oanda",
    "f42_binance", "f43_stocks", "f44_pnl", "hermes", "kimi", "openai", "deepseek",
    "cohere", "gemini", "groq", "grok", "nvidia_nim", "openrouter", "sambanova",
}
# comms-name -> hub id (mirrors the map's ALIAS; local copy, map file untouched)
ALIAS = {"asa": "acer_cass", "tp": "tp_pip", "pip": "tp_pip", "tp_pip": "tp_pip",
         "acer_cass": "acer_cass", "wren": "wren", "bill": "bill"}


def _node(name):
    """Resolve a log actor name to a hub node-id the map can place, else None.
    Provider/hub names pass straight through; comms aliases map; everything the
    map cannot place (system/council/ross/all/claude/probe/engine names) -> None
    so the caller can pick a truthful fallback hub instead of faking a station."""
    if not name:
        return None
    s = str(name).strip().lower()
    s = ALIAS.get(s, s)
    return s if s in HUB_IDS else None


def _parse_ts(ts):
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _iter_jsonl(path, tail):
    if not path.exists():
        return
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception:
        return
    for ln in lines[-tail:]:
        ln = ln.strip().lstrip("\x00").strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if isinstance(r, dict):
            yield r


def load_cursor():
    if CURSOR.exists():
        try:
            d = json.loads(CURSOR.read_text())
            if isinstance(d, dict) and isinstance(d.get("emitted_sigs"), list):
                return d
        except Exception:
            pass
    return {"emitted_sigs": [], "last_run": None, "total_emitted": 0}


def save_cursor(cur):
    # keep the sig ring bounded so the cursor file can't grow unbounded
    cur["emitted_sigs"] = cur["emitted_sigs"][-20000:]
    cur["last_run"] = datetime.now(timezone.utc).isoformat()
    tmp = CURSOR.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cur))
    tmp.replace(CURSOR)


def _sig(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _clip(s, n=118):
    s = str(s).replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# --------------------------------------------------------------------- builders
def collect(window):
    """Return a list of candidate moves: (sig, {row}). Only REAL, in-window,
    two-endpoint-resolved events. `window` seconds bounds recency (== map AGE_MAX)."""
    now = datetime.now(timezone.utc).timestamp()
    moves = []

    def fresh(ts):
        te = _parse_ts(ts)
        return te is not None and (now - te) <= window and (now - te) >= -60, te

    # A. Boardroom commentary -> boardroom hub
    for r in _iter_jsonl(BOARDROOM_COMMENTARY, 400):
        ts = r.get("ts")
        ok, _ = fresh(ts)
        if not ok:
            continue
        poster = r.get("from") or r.get("who")
        frm = _node(poster) or "task_council"   # watcher/system/council events ride the council machinery
        if frm == "boardroom":
            continue
        text = r.get("text") or r.get("summary") or "board post"
        src_tag = r.get("src") or r.get("kind") or "board"
        lab = "board: " + _clip(text, 90)
        sig = _sig("bc", frm, ts, text[:60], src_tag)
        moves.append((sig, {"ts": ts, "from": frm, "to": "boardroom", "cat": "comms",
                            "label": _clip(lab), "real": True,
                            "source": "data/registries/qsb_boardroom_commentary.jsonl"}))

    # B. Boardroom hub activity -> boardroom hub (or named recipient when placeable)
    for r in _iter_jsonl(BOARDROOM_HUB, 400):
        ts = r.get("ts")
        ok, _ = fresh(ts)
        if not ok:
            continue
        frm = _node(r.get("from"))
        if not frm:
            continue                             # need a real placeable poster
        to = _node(r.get("to")) or "boardroom"
        if to == frm:
            to = "boardroom"
        if to == frm:
            continue
        text = r.get("text") or (r.get("kind") or "compose")
        lab = "hub: " + _clip(text, 90)
        sig = _sig("bh", frm, to, ts, str(text)[:60])
        moves.append((sig, {"ts": ts, "from": frm, "to": to, "cat": "comms",
                            "label": _clip(lab), "real": True,
                            "source": "data/registries/qsb_boardroom_hub_activity.jsonl"}))

    # C. Gene-pool router live events -> gene_pool secure store
    for r in _iter_jsonl(GENE_LIVE, 300):
        ts = r.get("ts")
        ok, _ = fresh(ts)
        if not ok:
            continue
        prov = _node(r.get("provider"))
        ev = r.get("event") or "event"
        detail = r.get("detail") or r.get("status") or ""
        if prov and prov != "gene_pool":
            frm, to = prov, "gene_pool"
        else:
            # a router/scanner event with no single placeable provider: it lands
            # ON the gene pool from the router's own machinery. Route it in from
            # the boardroom hub (the tower's activity bus) so it still draws.
            frm, to = "boardroom", "gene_pool"
        lab = "gene: " + _clip(ev + (" · " + str(detail) if detail else ""), 90)
        sig = _sig("gp", frm, to, ts, ev, str(detail)[:50])
        moves.append((sig, {"ts": ts, "from": frm, "to": to, "cat": "route",
                            "label": _clip(lab), "real": True,
                            "source": "data/registries/gene_pool_router_live_events.jsonl"}))

    # D. Provider ADVISORY consult calls -> gene_pool <-> provider (round trip)
    for r in _iter_jsonl(ACTIVITY_TAIL, 1500):
        if r.get("event_kind") != "provider_call":
            continue
        pay = r.get("payload") or {}
        ts = r.get("ts") or pay.get("ts")
        ok, _ = fresh(ts)
        if not ok:
            continue
        prov = _node(pay.get("provider") or r.get("provider"))
        if not prov:
            continue
        model = pay.get("model") or ""
        cost = pay.get("cost_usd")
        reason = pay.get("reason") or "advisory consult"
        ctxt = (f" ${round(cost,4)}" if isinstance(cost, (int, float)) else "")
        base = _clip((model or prov) + " · " + str(reason), 80)
        # request leg
        sig_q = _sig("pcq", prov, ts, model, reason)
        moves.append((sig_q, {"ts": ts, "from": "gene_pool", "to": prov, "cat": "provider",
                              "label": _clip("consult → " + base + ctxt), "real": True,
                              "source": "data/registries/qsb_tower_activity_tail.jsonl :: provider_call"}))
        # reply leg (the call returned a completion -> a real answer came back)
        if pay.get("completion_tokens") or pay.get("cost_usd") is not None:
            sig_a = _sig("pca", prov, ts, model, reason)
            moves.append((sig_a, {"ts": ts, "from": prov, "to": "gene_pool", "cat": "provider",
                                  "label": _clip(prov + " → Gene Pool (reply) · " + base), "real": True,
                                  "source": "data/registries/qsb_tower_activity_tail.jsonl :: provider_call"}))

    # E. F47 team records -> Task Council ledger
    for r in _iter_jsonl(F47_RECORDS, 300):
        ts = r.get("ts")
        ok, _ = fresh(ts)
        if not ok:
            continue
        op = r.get("operator") or r.get("actor")
        frm = _node(op) or "wren"                # unresolved operators (claude/engine) ride Wren, the F47-ledger governor
        if frm == "task_council":
            continue
        kind = r.get("kind") or "record"
        summary = r.get("summary") or kind
        lab = "F47: " + _clip(summary, 90)
        sig = _sig("f47", frm, ts, kind, str(summary)[:60])
        moves.append((sig, {"ts": ts, "from": frm, "to": "task_council", "cat": "council",
                            "label": _clip(lab), "real": True,
                            "source": "data/registries/qsb_f47_team_records.jsonl"}))

    return moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60, help="max rows to emit this run")
    ap.add_argument("--window", type=int, default=900,
                    help="only emit events fresher than this many seconds (map AGE_MAX)")
    ap.add_argument("--dry-run", action="store_true", help="show what would emit, write nothing")
    args = ap.parse_args()

    cur = load_cursor()
    seen = set(cur["emitted_sigs"])

    moves = collect(args.window)
    # freshest-first so when --max bites we keep the most recent real events
    moves.sort(key=lambda sr: _parse_ts(sr[1].get("ts")) or 0, reverse=True)

    emitted, rows, new_sigs = 0, [], []
    per_cat = {}
    for sig, row in moves:
        if sig in seen:
            continue
        if emitted >= args.max:
            break
        rows.append(row)
        new_sigs.append(sig)
        seen.add(sig)
        emitted += 1
        per_cat[row["cat"]] = per_cat.get(row["cat"], 0) + 1

    if args.dry_run:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        print(f"# DRY-RUN would emit {emitted} rows  cats={per_cat}", file=sys.stderr)
        return

    if rows:
        with FEED.open("a") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        cur["emitted_sigs"].extend(new_sigs)
        cur["total_emitted"] = cur.get("total_emitted", 0) + emitted
        save_cursor(cur)
    else:
        # still stamp the run so last_run reflects reality
        save_cursor(cur)

    print(json.dumps({"emitted": emitted, "cats": per_cat,
                      "candidates": len(moves), "feed": str(FEED)}))


if __name__ == "__main__":
    main()
