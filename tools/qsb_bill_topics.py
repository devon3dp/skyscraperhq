#!/usr/bin/env python3
"""
qsb_bill_topics.py — LIVE, CHANGING topic generator for Bill's concierge + coordinator.

THE PROBLEM (Ross 2026-07-30): "Bill's not working very well ... he only gets the
same questions ... make it real-time, real-live." Bill looped because every driver
fed him a FIXED prompt:
  * qsb_live_workers.py had a hard-coded 6-item WORK list.
  * qsb_bill_concierge_feed.py always asked for the same "morning-style briefing".
  * qsb_bill_wren_coordinator.py always asked Wren the same "top priority" question.
Same question in -> same answer out. Not real, just canned.

THE FIX (this module): a single source of VARIED, REAL, DELTA-AWARE topics driven
from LIVE tower state. Every call:
  1. Reads current REAL tower state (health, board, PnL, pot, self-audit, gene pool,
     recent provider/agent activity, a real floor).
  2. Computes DELTAS vs the last time this ran (persisted cursor) — "since last check,
     3 tasks completed, board +37, CHF unjammed, F43 now busy".
  3. ROTATES through real topic *angles* (health / trading / tasks / a specific floor /
     workers / a real recent event / a delta) so consecutive prompts differ.
  4. Emits a topic dict the three drivers turn into DIFFERENT prompts each cycle.

HONESTY (R01): every field comes from a real registry read. On a read failure the
angle is skipped, never faked. This module NEVER speaks as Bill or Wren — it only
decides WHAT they are asked, from real state.

The cursor persists at data/runtime/qsb_bill_topic_cursor.json so deltas are real
across process restarts and the rotation index doesn't reset every tick.
"""
from __future__ import annotations
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
RUNTIME = ROOT / "data" / "runtime"
sys.path.insert(0, str(ROOT / "tools"))

CURSOR = RUNTIME / "qsb_bill_topic_cursor.json"

HEALTH_SNAP = REG / "qsb_tower_health_snapshot.json"
ACTIVITY = REG / "qsb_tower_activity_tail.jsonl"
COUNCIL = REG / "qsb_council_tasks.jsonl"
FLOORS = REG / "floors.json"
OANDA_SUM = REG / "qsb_oanda_history_summary.json"
SESSION_PNL = REG / "qsb_session_pnl_stop.json"
POT = REG / "qsb_portfolio_pot.json"
SELF_AUDIT = REG / "qsb_self_audit_findings.jsonl"
GENE = REG / "gene_pool_router_state.json"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── cursor (delta memory) ─────────────────────────────────────────────────────

def load_cursor() -> dict:
    try:
        return json.loads(CURSOR.read_text())
    except Exception:
        return {}


def save_cursor(c: dict) -> None:
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        tmp = CURSOR.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, indent=2))
        tmp.replace(CURSOR)
    except Exception:
        pass


# ── real state reads (each isolated; failure => field absent, never faked) ────

def _read_json(p: Path):
    return json.loads(p.read_text())


def _health() -> dict:
    # prefer the live module (freshest); fall back to the on-disk snapshot.
    try:
        import qsb_tower_health as H
        return H.snapshot()
    except Exception:
        try:
            return _read_json(HEALTH_SNAP)
        except Exception:
            return {}


def _recent_activity(n: int = 40) -> list[dict]:
    out = []
    try:
        lines = ACTIVITY.read_text(errors="replace").splitlines()
    except Exception:
        return out
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _tail_council(n: int = 60) -> list[dict]:
    out = []
    try:
        lines = COUNCIL.read_text(errors="replace").splitlines()
    except Exception:
        return out
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _pick_live_floor(activity: list[dict], cursor: dict) -> dict | None:
    """Pick a REAL floor that is actually being mentioned in live activity, rotating
    so we don't keep naming the same one. Returns {number, name, dept, why}."""
    try:
        floors = _read_json(FLOORS)
    except Exception:
        return None
    by_num = {}
    for fl in (floors if isinstance(floors, list) else []):
        by_num[str(fl.get("number"))] = fl
    # count Fnn mentions in recent activity (real signal of which floor is busy)
    import re
    counts: dict[str, int] = {}
    for a in activity:
        blob = json.dumps(a)
        for m in re.findall(r"\bF(\d{1,3})\b", blob):
            counts[m] = counts.get(m, 0) + 1
    if not counts:
        return None
    # rotate: skip the floor we surfaced last time if there is another candidate
    ranked = [n for n, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if n in by_num]
    if not ranked:
        return None
    last = str(cursor.get("last_floor", ""))
    pick = ranked[0]
    if pick == last and len(ranked) > 1:
        pick = ranked[1]
    fl = by_num.get(pick, {})
    return {
        "number": pick,
        "name": fl.get("floor_name") or fl.get("department") or f"Floor {pick}",
        "dept": fl.get("department", ""),
        "status": fl.get("status", ""),
        "mentions": counts.get(pick, 0),
    }


def _recent_event_line(activity: list[dict], council: list[dict]) -> str | None:
    """One REAL, human-readable recent event to anchor a prompt (rotates naturally
    because the tail moves). Prefers a council state-change, else a provider/session."""
    for r in reversed(council):
        ev = r.get("event")
        if ev in ("peer_signoff", "recycled", "completed", "done", "verified"):
            tid = r.get("task_id", "?")
            actor = r.get("actor", "?")
            verdict = r.get("verdict") or ev
            return f"task {tid}: {actor} {verdict} ({(r.get('text') or '')[:60]})"
    for r in reversed(activity):
        k = r.get("event_kind")
        if k in ("provider_call", "wren_local_agent_session", "provider_agent_session", "capability_prototype"):
            return f"{k}: {(r.get('summary') or '')[:80]}"
    return None


def gather() -> dict:
    """One real snapshot of the changing tower, flattened for topic use."""
    h = _health()
    svc = h.get("services", {}) or {}
    tc = h.get("task_council", {}) or {}
    g: dict = {"ts": utc()}
    g["services_up"] = svc.get("up")
    g["services_total"] = svc.get("total")
    g["services_down"] = svc.get("down", [])
    g["bus"] = bool(h.get("event_bus_bound"))
    g["traders_alive"] = h.get("traders_alive")
    g["traders_trading"] = h.get("traders_attempting_orders_recently")
    g["disk_pct"] = h.get("root_disk_pct")
    g["load_1m"] = h.get("load_1m")
    g["tasks_open"] = tc.get("open")
    g["tasks_in_progress"] = tc.get("in_progress")
    g["tasks_blocked"] = tc.get("blocked")
    g["tasks_done"] = tc.get("done")
    try:
        sp = _read_json(SESSION_PNL)
        g["session_pnl"] = sp.get("realized_pnl")
        g["pnl_cap"] = sp.get("daily_cap")
        g["pnl_tripped"] = sp.get("tripped")
    except Exception:
        pass
    try:
        g["oanda_grand_gbp"] = _read_json(OANDA_SUM).get("grand_pl_gbp")
    except Exception:
        pass
    try:
        pot = _read_json(POT)
        g["pot_committed"] = round(pot.get("committed_gbp", 0), 2)
        g["pot_cap"] = pot.get("cap_gbp")
        g["pot_open"] = len(pot.get("open_positions", {}))
    except Exception:
        pass
    try:
        latest: dict = {}
        for line in SELF_AUDIT.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            latest[d.get("key")] = d
        reds = [d.get("title", "?") for d in latest.values()
                if d.get("status") == "open" and d.get("severity") == "red"]
        ambers = [d.get("title", "?") for d in latest.values()
                  if d.get("status") == "open" and d.get("severity") == "amber"]
        g["audit_red"] = reds
        g["audit_amber_count"] = len(ambers)
    except Exception:
        pass
    try:
        m = _read_json(GENE).get("metrics", {})
        g["gene_events"] = m.get("events")
        g["gene_uptime_h"] = int((m.get("uptime_s") or 0) / 3600)
    except Exception:
        pass
    return g


# ── delta computation ─────────────────────────────────────────────────────────

def compute_deltas(cur: dict, prev: dict) -> list[str]:
    """Human-readable REAL deltas since last cycle. Empty if nothing moved."""
    d = []
    def _num(x):
        return x if isinstance(x, (int, float)) else None
    # task board movement
    for label, key in (("done", "tasks_done"), ("open", "tasks_open"),
                        ("blocked", "tasks_blocked"), ("in-progress", "tasks_in_progress")):
        a, b = _num(cur.get(key)), _num(prev.get(key))
        if a is not None and b is not None and a != b:
            d.append(f"{label} {a - b:+d} (now {a})")
    # services
    cd, pd = set(cur.get("services_down") or []), set(prev.get("services_down") or [])
    if cd - pd:
        d.append("service(s) went DOWN: " + ", ".join(sorted(cd - pd)))
    if pd - cd:
        d.append("service(s) RECOVERED: " + ", ".join(sorted(pd - cd)))
    # PnL
    a, b = cur.get("session_pnl"), prev.get("session_pnl")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) >= 0.01:
        d.append(f"session PnL {a - b:+.2f} (now GBP {a:+.2f})")
    a, b = cur.get("oanda_grand_gbp"), prev.get("oanda_grand_gbp")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) >= 0.5:
        d.append(f"OANDA grand PnL {a - b:+.2f} (now GBP {a:.2f})")
    # pot / positions
    a, b = _num(cur.get("pot_open")), _num(prev.get("pot_open"))
    if a is not None and b is not None and a != b:
        d.append(f"open positions {a - b:+d} (now {a})")
    # audit
    cr, pr = set(cur.get("audit_red") or []), set(prev.get("audit_red") or [])
    if cr - pr:
        d.append("NEW audit RED: " + "; ".join(sorted(cr - pr))[:80])
    if pr - cr:
        d.append("audit RED cleared: " + "; ".join(sorted(pr - cr))[:80])
    # traders
    a, b = _num(cur.get("traders_alive")), _num(prev.get("traders_alive"))
    if a is not None and b is not None and a != b:
        d.append(f"traders alive {a - b:+d} (now {a})")
    return d


# ── the rotating topic angles ─────────────────────────────────────────────────

ANGLES = ("delta", "health", "trading", "tasks", "floor", "workers", "event", "audit")


def _angle_text(angle: str, g: dict, deltas: list[str], floor: dict | None,
                event_line: str | None) -> tuple[str, str] | None:
    """Return (short_label, fact_context) for the given angle, or None if that angle
    has no real data this cycle (so the caller can rotate to the next one)."""
    if angle == "delta":
        if not deltas:
            return None
        return ("what changed since last check", "Changes since the last check: " + "; ".join(deltas[:4]))
    if angle == "health":
        if g.get("services_up") is None:
            return None
        return ("tower health right now",
                f"{g.get('services_up')}/{g.get('services_total')} services up"
                + (f" (DOWN: {', '.join(g.get('services_down'))})" if g.get("services_down") else "")
                + f", bus {'LIVE' if g.get('bus') else 'DOWN'}, disk {g.get('disk_pct')}, load {g.get('load_1m')}.")
    if angle == "trading":
        if g.get("session_pnl") is None and g.get("oanda_grand_gbp") is None:
            return None
        parts = []
        if g.get("session_pnl") is not None:
            parts.append(f"today's PnL GBP {g.get('session_pnl'):+.2f} (cap {g.get('pnl_cap')}, tripped={g.get('pnl_tripped')})")
        if g.get("oanda_grand_gbp") is not None:
            parts.append(f"OANDA grand PnL GBP {g.get('oanda_grand_gbp')}")
        if g.get("pot_committed") is not None:
            parts.append(f"capital GBP {g.get('pot_committed')}/{g.get('pot_cap')} across {g.get('pot_open')} positions")
        if g.get("traders_trading") is not None:
            placing = "some placing orders recently" if g.get("traders_trading") else "none placed orders in the last few minutes"
            parts.append(f"{g.get('traders_alive')} traders alive, {placing}")
        return ("the trading floors tonight", "; ".join(parts) + ".")
    if angle == "tasks":
        if g.get("tasks_open") is None:
            return None
        return ("the task board",
                f"board: {g.get('tasks_open')} open, {g.get('tasks_in_progress')} in progress, "
                f"{g.get('tasks_blocked')} blocked, {g.get('tasks_done')} done.")
    if angle == "floor":
        if not floor:
            return None
        return (f"Floor {floor['number']} ({floor['name']})",
                f"Floor {floor['number']} — {floor['dept']} — is active in the live feed "
                f"({floor['mentions']} recent mentions), status {floor['status']}.")
    if angle == "workers":
        if g.get("traders_alive") is None:
            return None
        placing = "some placing orders recently" if g.get("traders_trading") else "quiet on new orders"
        return ("the worker fleet",
                f"{g.get('traders_alive')} traders alive ({placing}); "
                f"gene pool {g.get('gene_events')} events over {g.get('gene_uptime_h')}h.")
    if angle == "event":
        if not event_line:
            return None
        return ("a real thing that just happened", "Most recent tower event: " + event_line)
    if angle == "audit":
        if g.get("audit_red") is None:
            return None
        if g.get("audit_red"):
            return ("a self-audit RED item", "Self-audit RED open: " + "; ".join(g["audit_red"][:2]))
        return ("the self-audit picture",
                f"self-audit: 0 red, {g.get('audit_amber_count')} amber open.")
    return None


def next_topic() -> dict:
    """THE entry point. Returns a rotating, real, delta-aware topic dict:
        {ts, angle, label, fact_context, deltas[], floor, headline}
    Advances the persisted rotation cursor and records this cycle's state so the NEXT
    call can compute real deltas. Skips angles with no real data this cycle so Bill is
    never asked about something empty."""
    cursor = load_cursor()
    prev = cursor.get("last_state") or {}
    g = gather()
    activity = _recent_activity()
    council = _tail_council()
    deltas = compute_deltas(g, prev)
    floor = _pick_live_floor(activity, cursor)
    event_line = _recent_event_line(activity, council)

    start = int(cursor.get("angle_idx", 0))
    chosen = None
    for step in range(len(ANGLES)):
        angle = ANGLES[(start + step) % len(ANGLES)]
        got = _angle_text(angle, g, deltas, floor, event_line)
        if got:
            chosen = (angle, got[0], got[1])
            next_idx = (start + step + 1) % len(ANGLES)
            break
    if not chosen:
        # extreme fallback — health line always has *something* real if reachable
        chosen = ("tasks", "the task board",
                  f"board: {g.get('tasks_open')} open, {g.get('tasks_done')} done.")
        next_idx = (start + 1) % len(ANGLES)

    angle, label, fact = chosen
    cursor["angle_idx"] = next_idx
    cursor["last_state"] = g
    if floor:
        cursor["last_floor"] = floor["number"]
    cursor["last_topic_ts"] = g["ts"]
    save_cursor(cursor)

    return {
        "ts": g["ts"],
        "angle": angle,
        "label": label,
        "fact_context": fact,
        "deltas": deltas,
        "floor": floor,
        "event": event_line,
        "headline": f"{label}: {fact}",
    }


# ── prompt builders the three drivers use (so wording differs per driver) ─────

def worker_prompt() -> tuple[str, dict]:
    """SHORT prompt for Bill's live-worker cycle (single Mac qwen — keep it tight).
    Returns (prompt, topic)."""
    t = next_topic()
    ctx = t["fact_context"]
    return (f"CONCIERGE CHECK — {t['label']}. Real state: {ctx} "
            f"In ONE sentence, tell Ross the ONE thing here that matters most right now.",
            t)


def concierge_ask(facts_text: str) -> tuple[str, dict]:
    """The 'ask' for qsb_bill_concierge_feed's briefing. Rotates the angle so the
    briefing is about a DIFFERENT real thing each time, not the same 'morning briefing'.
    facts_text is the full fact bundle the feed already gathered; we focus Bill on the
    rotating angle within it. Returns (ask, topic)."""
    t = next_topic()
    focus = t["label"]
    delta_note = (" Note what changed since your last update: " + "; ".join(t["deltas"][:3])) if t["deltas"] else ""
    return (f"give Ross a SHORT, FRESH concierge note focused on {focus}. "
            f"Lead with that, then one line of wider context.{delta_note} "
            f"Do NOT open with 'Good morning' every time — vary your opener; be specific and new.",
            t)


def coordinator_prompt() -> tuple[str, dict]:
    """The question the coordinator asks WREN to brief Bill on. Rotates the focus so
    Wren isn't answering the identical 'top priority' question each tick. Returns
    (wren_instruction, topic)."""
    t = next_topic()
    focus = t["label"]
    delta_note = (" Changes since last brief: " + "; ".join(t["deltas"][:3]) + "." ) if t["deltas"] else ""
    return (f"Brief Bill (Ross's concierge) specifically about {focus}, grounded in live telemetry. "
            f"Real context you can confirm: {t['fact_context']}{delta_note} "
            f"In 2-3 sentences say what it means and what you are doing about it — be concrete, "
            f"cite real numbers, and make this DIFFERENT from your last brief.",
            t)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Bill live-topic generator (varied, real, delta-aware).")
    ap.add_argument("--topic", action="store_true", help="print the next rotating topic (advances cursor)")
    ap.add_argument("--worker", action="store_true", help="print the worker-cycle prompt")
    ap.add_argument("--concierge", action="store_true", help="print the concierge ask")
    ap.add_argument("--coordinator", action="store_true", help="print the coordinator (Wren) prompt")
    ap.add_argument("--demo", type=int, metavar="N", help="print N consecutive topics to prove variation")
    ap.add_argument("--facts", action="store_true", help="print the raw gathered state")
    a = ap.parse_args()
    if a.facts:
        print(json.dumps(gather(), indent=2, default=str))
    elif a.demo:
        for i in range(a.demo):
            t = next_topic()
            print(f"[{i+1}] angle={t['angle']:10s} | {t['headline'][:150]}")
    elif a.worker:
        p, t = worker_prompt(); print(f"# angle={t['angle']}\n{p}")
    elif a.concierge:
        p, t = concierge_ask(""); print(f"# angle={t['angle']}\n{p}")
    elif a.coordinator:
        p, t = coordinator_prompt(); print(f"# angle={t['angle']}\n{p}")
    else:
        print(json.dumps(next_topic(), indent=2, default=str))
