#!/usr/bin/env python3
"""
qsb_council_live_dash.py — LIVE ANIMATED Task Council flow dashboard (:8864).

2026-07-28, Ross: "liveflow diagrams animations!!!!" — an animated pipeline of the
council actually working: Open → Claimed → Sandbox → Quorum Verify → Wren Gate → Done.

EVERYTHING REAL — every pulse is a real event, every count a real task:
  - task board / states : data/registries/qsb_council_tasks_snapshot.json
  - live motion (pulses) : data/registries/qsb_council_tasks.jsonl  (append-only event log)
  - autorunner health    : data/registries/qsb_autorunner_activity.jsonl + qsb_autorunner_gate.json
No demo motion — a token only glides when a real event newer than last-seen appears.
Read-only. systemd qsb-council-live-dash.service.
"""
import json
import threading as _threading
import urllib.request as _urlreq
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
SNAP = REG / "qsb_council_tasks_snapshot.json"
LOG = REG / "qsb_council_tasks.jsonl"
AUTO_LOG = REG / "qsb_autorunner_activity.jsonl"
AUTO_GATE = REG / "qsb_autorunner_gate.json"
import time as _time
VER = str(int(_time.time()))  # bumps on every service restart -> clients auto-reload

STAGE = {
    "pending_admission": "intake",
    "open": "open", "recycled": "open",
    "claimed": "claimed", "assigned": "claimed", "acknowledged": "claimed",
    "in_progress": "working",
    "awaiting_peer_signoff": "sandbox",
    "awaiting_verification": "quorum", "needs_second_verifier": "quorum",
    "ready_to_ship": "wren_gate",
    "done": "done",
    "blocked": "blocked",
}
COLS = ["open", "claimed", "working", "sandbox", "quorum", "wren_gate", "done"]
EVENT_TO_STAGE = {
    "created": "open", "proposed": "intake", "admission_voted": "open", "recycled": "open",
    "unblocked": "open", "claimed": "claimed", "assigned": "claimed", "acknowledged": "claimed",
    "updated": "working", "noted": "working", "tool_selected": "working",
    "sandbox_passed": "sandbox", "sandbox_rejected": "working",
    "awaiting_verification": "quorum", "peer_signoff": "wren_gate",
    "done": "done", "blocked": "blocked",
}
# Dashboard worker seats only. Ross is the owner/operator, not a council worker;
# his audit actions remain in the immutable ledger but are never rendered here.
ACTIVE_PRINCIPALS = {"wren", "tp_pip", "acer_cass", "bill", "codex"}


def _visible_principal(value):
    """Map the retired Claude seat to successor Bill without rewriting history."""
    value = (value or "").strip().lower()
    if "claude" in value:
        return "bill"
    return value if value in ACTIVE_PRINCIPALS else ""


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(errors="ignore"))
    except Exception:
        return d


def _tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [json.loads(x) for x in deque(f, maxlen=n) if x.strip()]
    except Exception:
        return []


# ── Live box gene-pool providers (REAL /health polls, 20s in-process cache) ──
# The two Windows boxes each run a standalone multi-provider gene pool on :8770.
# We poll ONLY /health (fast, read-only) and show exactly what each box reports —
# a box that can't be reached is shown offline with no providers, never invented.
_GENE_BOXES = {
    "tp_pip":    "http://DESKTOP-9RBVKSM.local:8770/health",
    "acer_cass": "http://DESKTOP-1E2FB5N.local:8770/health",
}
_GENE_CACHE = {"ts": 0.0, "data": None}
_GENE_TTL = 20.0


def _gene_box_probe(url):
    try:
        with _urlreq.urlopen(url, timeout=2.5) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        provs = j.get("providers_available") or []
        if not isinstance(provs, list):
            provs = []
        return {"online": bool(j.get("ok")), "providers": [str(p) for p in provs]}
    except Exception:
        return {"online": False, "providers": []}


def _gene_pool():
    now = _time.time()
    c = _GENE_CACHE
    if c["data"] is not None and (now - c["ts"]) < _GENE_TTL:
        return c["data"]
    out = {}
    threads = []
    for name, url in _GENE_BOXES.items():
        t = _threading.Thread(target=lambda n=name, u=url: out.__setitem__(n, _gene_box_probe(u)),
                              daemon=True)
        t.start(); threads.append(t)
    for t in threads:
        t.join(timeout=3.0)
    for name in _GENE_BOXES:            # a hung thread still yields an honest offline box
        out.setdefault(name, {"online": False, "providers": []})
    c["ts"] = now; c["data"] = out
    return out


def build():
    snap = _load(SNAP, {"tasks": []})
    stages = {c: {"count": 0, "tokens": []} for c in COLS}
    stages["intake"] = {"count": 0, "tokens": []}
    stages["blocked"] = {"count": 0, "tokens": []}
    owner_ct, awaiting = Counter(), []
    for t in snap.get("tasks", []):
        col = STAGE.get((t.get("state") or "").lower())
        if not col:
            continue
        stages[col]["count"] += 1
        own = _visible_principal(t.get("owner") or t.get("assignee"))
        if own:
            owner_ct[own] += 1
        if len(stages[col]["tokens"]) < 40:
            stages[col]["tokens"].append({"id": t["id"], "title": (t.get("title") or t["id"])[:46],
                                          "owner": own, "rework": t.get("rework_rounds", 0)})
        if col in ("sandbox", "quorum"):
            awaiting.append({"id": t["id"], "title": (t.get("title") or t["id"])[:46], "owner": own,
                             "sandbox_by": t.get("sandbox_passed_by"), "signoff_by": t.get("peer_signoff_by"),
                             "verdict": t.get("peer_signoff_verdict"), "rework": t.get("rework_rounds", 0)})

    ev = _tail(LOG, 500)
    actor, ev_types = Counter(), Counter()
    ticker, pulses, edge = [], [], Counter()
    for e in ev:
        st = EVENT_TO_STAGE.get(e.get("event"))
        visible_actor = _visible_principal(e.get("actor"))
        if visible_actor:
            actor[visible_actor] += 1
        ev_types[e.get("event", "?")] += 1
        if not st:
            continue
        to = st
        if e.get("event") == "peer_signoff" and e.get("verdict") == "reject":
            to = "working"
        if e.get("event") == "recycled":
            to = "open"
        edge[to] += 1
        # Retired/unknown providers remain in the immutable ledger, but are not
        # active Task Council participants and therefore never appear here.
        if not visible_actor:
            continue
        ticker.append({"ts": e.get("ts"), "event": e.get("event"), "task": e.get("task_id"),
                       "actor": visible_actor, "verdict": e.get("verdict", ""), "to": to})
    for r in ticker[-22:]:
        pulses.append({"to": r["to"], "actor": r["actor"], "ts": r["ts"], "event": r["event"], "task": r["task"]})

    # ── rating /10 (honest: more corrections = lower) + interactive sign-off queue ──
    def rate(t):
        base = 10 - min(10, t.get("rework_rounds") or 0)
        if t.get("peer_signoff_verdict") == "approve":
            base += 1
        if t.get("peer_signoff_verdict") == "reject":
            base -= 2
        return max(0, min(10, base))

    # ── PER-MEMBER LANES ── each member's tasks parked at their current stage ──
    LANE_MEMBERS = ["wren", "tp_pip", "acer_cass", "bill", "codex"]
    lanes = {m: {c: [] for c in COLS} for m in LANE_MEMBERS}
    lanes["pool"] = {c: [] for c in COLS}

    def lane_for(t):
        own = _visible_principal(t.get("owner") or t.get("assignee"))
        if own in LANE_MEMBERS:
            return own
        cb = _visible_principal(t.get("created_by"))
        if cb in LANE_MEMBERS:          # e.g. bill/codex/acer_cass created their own
            return cb
        return "pool"                   # unowned / ross-origin / anything else

    lane_stats = {m: {"tasks": 0, "done": 0, "rework": 0, "rating": 0} for m in lanes}
    for t in snap.get("tasks", []):
        col = STAGE.get((t.get("state") or "").lower())
        if col not in COLS:             # skip intake/blocked from the 7-station lanes
            continue
        m = lane_for(t)
        tok = {"id": t["id"], "title": (t.get("title") or t["id"])[:40],
               "owner": (_visible_principal(t.get("owner") or t.get("assignee") or t.get("created_by"))),
               "rework": t.get("rework_rounds", 0), "rating": rate(t)}
        if len(lanes[m][col]) < 20:
            lanes[m][col].append(tok)
        s = lane_stats[m]
        s["tasks"] += 1
        s["rework"] += (t.get("rework_rounds") or 0)
        s["rating"] += rate(t)
        if col == "done":
            s["done"] += 1

    lane_summary = {m: {
        "tasks": s["tasks"], "done": s["done"],
        "rating": round(s["rating"] / s["tasks"], 1) if s["tasks"] else 0.0,
        "avg_rework": round(s["rework"] / s["tasks"], 1) if s["tasks"] else 0.0,
    } for m, s in lane_stats.items()}

    awaiting_signoff, wstat = [], {}
    for t in snap.get("tasks", []):
        st = (t.get("state") or "").lower()
        if st in ("awaiting_peer_signoff", "awaiting_verification", "ready_to_ship"):
            awaiting_signoff.append({"id": t["id"], "title": (t.get("title") or t["id"])[:64], "state": st,
                                     "owner": t.get("owner"), "rework": t.get("rework_rounds") or 0,
                                     "signoff_by": t.get("peer_signoff_by"), "verdict": t.get("peer_signoff_verdict"),
                                     "rating": rate(t), "created_by": t.get("created_by")})
        who = _visible_principal(t.get("owner") or t.get("created_by"))
        if who:
            w = wstat.setdefault(who, {"tasks": 0, "done": 0, "rework": 0, "rating": 0})
            w["tasks"] += 1
            w["rework"] += (t.get("rework_rounds") or 0)
            w["rating"] += rate(t)
            if st == "done":
                w["done"] += 1
    awaiting_signoff.sort(key=lambda x: -x["rework"])
    worker_stats = sorted(
        [{"actor": a, "tasks": w["tasks"], "done": w["done"],
          "avg_rework": round(w["rework"] / w["tasks"], 1) if w["tasks"] else 0,
          "avg_rating": round(w["rating"] / w["tasks"], 1) if w["tasks"] else 0} for a, w in wstat.items()],
        key=lambda x: -x["tasks"])[:8]

    codex_feed = sum(1 for t in snap.get("tasks", []) if t.get("created_by") == "codex")
    # Live decision trail for every visible council member. This used to expose
    # only Wren, which made healthy work by the rest of the council invisible.
    ACTION_LABEL = {"claimed": "claimed", "assigned": "assigned partner", "tool_selected": "picked tool",
                 "sandbox_passed": "sandbox ✓", "sandbox_rejected": "sandbox ✕", "peer_signoff": "signed off",
                 "blocked": "blocked", "recycled": "recycled ↺", "done": "marked done ✓",
                 "noted": "noted", "updated": "updated", "created": "created"}
    team_actions = [{"ts": r["ts"], "event": r["event"], "task": r["task"],
                     "actor": r["actor"], "label": ACTION_LABEL.get(r["event"], r["event"])}
                    for r in ticker if r["actor"] in LANE_MEMBERS][-24:]
    team_actions.reverse()

    gate = _load(AUTO_GATE, {})
    last = _tail(AUTO_LOG, 1)
    lastt = last[-1] if last else {}
    auto = {"enabled": gate.get("enabled"), "tick": lastt.get("tick"),
            "reason": lastt.get("reason", ""), "ts": lastt.get("ts", ""),
            "stalled": lastt.get("tick") == "skip"}

    # Honest progress model. Widths come only from current task states; animation
    # merely eases between real values. Stage weights express verified journey
    # through the governed pipeline. The HEADLINE completion is VERIFIED-only:
    # a 'done' task counts as complete only if it carries hard proof (proof_path,
    # an applied code-apply flag, or sandbox_passed + an approving peer sign-off).
    # Raw done/board is kept alongside, clearly labelled, so nothing is inflated.
    weights = {"intake": 0, "open": 5, "claimed": 18, "working": 38,
               "sandbox": 58, "quorum": 76, "wren_gate": 90,
               "done": 100, "blocked": 0}
    board_total = sum(stages[c]["count"] for c in stages)
    weighted_points = sum(stages[c]["count"] * weights[c] for c in stages)

    def _verified_done(t):
        if t.get("proof_path"):
            return True
        if t.get("applied"):
            return True
        if t.get("sandbox_passed_by") and (t.get("peer_signoff_verdict") == "approve"):
            return True
        return False

    done_tasks = [t for t in snap.get("tasks", []) if (t.get("state") or "").lower() == "done"]
    done_ct = len(done_tasks)
    verified_done = sum(1 for t in done_tasks if _verified_done(t))
    unverified_done = done_ct - verified_done
    rejected_ct = sum(1 for t in snap.get("tasks", []) if t.get("peer_signoff_verdict") == "reject")
    # Backlog reserve + active board are read straight from the reducer's snapshot
    # header so the dashboard stops hiding the ~1.8k-task reserve behind the KPIs.
    total_all = snap.get("total", board_total)
    reserved = snap.get("reserved", 0)
    # Display the CAPPED working board (in-flight + open up to cap), recomputed from the
    # tasks array — the persisted active_board can be an un-capped raw spike written by a
    # fleet process still on old code. The picker only ever works up to the cap.
    try:
        import qsb_council_tasks as _CT
        _abs_states, _cap = _CT.ACTIVE_BOARD_STATES, _CT.ACTIVE_BOARD_CAP
    except Exception:
        _abs_states = {"open", "claimed", "in_progress", "assigned", "acknowledged",
                       "awaiting_verification", "awaiting_peer_signoff", "needs_verification",
                       "needs_second_verifier", "needs_rework", "needs_proof", "needs_partner", "ready_to_ship"}
        _cap = snap.get("active_board_cap") or 20
    _tk = snap.get("tasks", [])
    _open_ct = sum(1 for t in _tk if (t.get("state") or "").lower() == "open")
    _inflight = sum(1 for t in _tk if (t.get("state") or "").lower() in _abs_states
                    and (t.get("state") or "").lower() != "open")
    active_board = _inflight + min(_open_ct, max(0, _cap - _inflight))
    active_board_raw = _open_ct + _inflight
    dropped = snap.get("dropped", 0)
    active_board_cap = snap.get("active_board_cap")

    # HEADLINE = verified completions over the active board (was raw done/board).
    completion_pct = round(100 * verified_done / board_total, 1) if board_total else 0.0
    # Verification rate = how much of the 'done' pile is actually proven.
    verification_rate = round(100 * verified_done / done_ct, 1) if done_ct else 0.0
    journey_pct = round(weighted_points / board_total, 1) if board_total else 0.0

    # Real principal liveness (LAN presence, 20s-cached, no external providers).
    principals = {}
    try:
        import sys as _sys
        _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
        import qsb_council_liveness as _LV
        for _c, _v in _LV.liveness_all().items():
            principals[_c] = {"state": _v.get("state", "UNKNOWN"),
                              "online": _v.get("state") == "ONLINE"}
    except Exception:
        principals = {}
    now = _time.time()
    def epoch(ts):
        try:
            from datetime import datetime
            return datetime.fromisoformat((ts or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    recent_60s = sum(1 for r in ticker if now - epoch(r.get("ts")) <= 60)
    recent_5m = sum(1 for r in ticker if now - epoch(r.get("ts")) <= 300)
    snap_age = round(max(0.0, now - SNAP.stat().st_mtime), 1) if SNAP.exists() else None
    log_age = round(max(0.0, now - LOG.stat().st_mtime), 1) if LOG.exists() else None
    stage_progress = [{"id": c, "label": c.replace("_", " ").title(),
                       "count": stages[c]["count"], "weight": weights[c]}
                      for c in ("intake",) + tuple(COLS) + ("blocked",)]
    progress = {"board_total": board_total, "done": stages["done"]["count"],
                "verified": verified_done, "unverified_done": unverified_done,
                "verification_rate": verification_rate,
                "completion_pct": completion_pct, "journey_pct": journey_pct,
                "total_all": total_all, "reserved": reserved, "active_board": active_board,
                "active_board_cap": active_board_cap, "dropped": dropped,
                "blocked": stages["blocked"]["count"], "rejected": rejected_ct,
                "recent_events_60s": recent_60s, "recent_events_5m": recent_5m,
                "snapshot_age_s": snap_age, "ledger_age_s": log_age,
                "live": snap_age is not None and snap_age < 180 and log_age is not None and log_age < 180,
                "stages": stage_progress, "principals": principals,
                "definition": "completion = VERIFIED done (proof_path/applied/sandbox+signoff) / pipeline board; "
                              "journey = state-weighted pipeline board; reserve shown separately, not in the board"}

    # ── per-segment live throughput (REAL transitions only, windowed) ──
    # A forward segment ending at station K counts real events arriving at K in
    # the window; the return loop counts real recycle/reopen churn. Empty window
    # → zero → the bar is dim and still (honest quiet handoff).
    SEG_KEYS = ["claimed", "working", "sandbox", "quorum", "wren_gate", "done"]
    seg_60 = {k: 0 for k in SEG_KEYS}; seg_60["loop"] = 0
    seg_5m = {k: 0 for k in SEG_KEYS}; seg_5m["loop"] = 0
    for r in ticker:
        age = now - epoch(r.get("ts"))
        ev = r.get("event"); to = r.get("to")
        key = "loop" if ev in ("recycled", "reopened") else (to if to in seg_60 else None)
        if key is None:
            continue
        if age <= 300:
            seg_5m[key] += 1
        if age <= 60:
            seg_60[key] += 1
    segments = {"win60": seg_60, "win5m": seg_5m}

    # per-member version of the same real throughput, keyed by the event's actor,
    # so each swim-lane can stream ONLY its owner's real transitions.
    lane_seg = {m: {"win60": {k: 0 for k in SEG_KEYS + ["loop"]},
                    "win5m": {k: 0 for k in SEG_KEYS + ["loop"]}} for m in LANE_MEMBERS}
    for r in ticker:
        m = r.get("actor")
        if m not in lane_seg:
            continue
        age = now - epoch(r.get("ts"))
        ev = r.get("event"); to = r.get("to")
        key = "loop" if ev in ("recycled", "reopened") else (to if to in SEG_KEYS else None)
        if key is None:
            continue
        if age <= 300:
            lane_seg[m]["win5m"][key] += 1
        if age <= 60:
            lane_seg[m]["win60"][key] += 1

    # ── live "now working" per member (real active task + latest real action) ──
    last_ev_by_task = {}
    for r in ticker:                       # ticker ascending → keeps newest per task
        if r.get("task"):
            last_ev_by_task[r["task"]] = r
    ACTIVE_STATES = {"claimed": 1, "assigned": 1, "acknowledged": 1, "in_progress": 5,
                     "awaiting_peer_signoff": 4, "awaiting_verification": 3,
                     "needs_second_verifier": 3, "ready_to_ship": 2}
    now_working = {}
    for m in LANE_MEMBERS:
        best, best_pri = None, -1
        for t in snap.get("tasks", []):
            own = _visible_principal(t.get("owner") or t.get("assignee") or t.get("created_by"))
            if own != m:
                continue
            pri = ACTIVE_STATES.get((t.get("state") or "").lower())
            if pri is None:
                continue
            if pri > best_pri:
                best, best_pri = t, pri
        if best:
            le = last_ev_by_task.get(best.get("id")) or {}
            now_working[m] = {"id": best["id"], "title": (best.get("title") or best["id"])[:52],
                              "state": (best.get("state") or "").lower(),
                              "stage": STAGE.get((best.get("state") or "").lower(), "working"),
                              "last_event": le.get("event", ""), "last_to": le.get("to", ""),
                              "last_ts": le.get("ts", "")}
        else:
            now_working[m] = None            # honest idle — no invented work

    # A principal actively mid-task must never disappear from the "active now"
    # view just because a burst from busier members pushed its last raw event
    # out of the 500-event tail (this is exactly why Acer went invisible: its
    # 18:26Z event scrolled off while wren/codex/bill flooded the window).
    # Union event-recency actors with anyone the snapshot shows mid-flight,
    # floored to their live in-flight count so the badge number stays honest.
    actors_out = dict(actor.most_common(8))
    for _m, _w in now_working.items():
        if _w and _m not in actors_out:
            _live = sum(1 for t in snap.get("tasks", [])
                        if _visible_principal(t.get("owner") or t.get("assignee") or t.get("created_by")) == _m
                        and (t.get("state") or "").lower() in ACTIVE_STATES)
            actors_out[_m] = max(actor.get(_m, 0), _live, 1)

    return {
        "ver": VER,
        "ts": snap.get("ts"),
        "kpis": {"total": snap.get("total"), "open": snap.get("open"),
                 "in_progress": snap.get("in_progress"), "blocked": snap.get("blocked"),
                 "done": snap.get("done"), "awaiting_verify": len(awaiting),
                 "active_board": active_board, "active_board_cap": active_board_cap,
                 "reserved": reserved, "dropped": dropped,
                 "verified": verified_done, "unverified_done": unverified_done},
        "stages": stages, "edges": dict(edge),
        "actors": actors_out,
        "owners": dict(owner_ct.most_common(6)),
        "pulses": pulses, "awaiting": awaiting[:12],
        "autorunner": auto,
        "ticker": list(reversed(ticker[-30:])),
        "awaiting_signoff": awaiting_signoff[:14],
        "worker_stats": worker_stats,
        "codex_feed": codex_feed,
        "team_actions": team_actions,
        "lanes": lanes,
        "lane_members": LANE_MEMBERS + ["pool"],
        "lane_summary": lane_summary,
        "progress": progress,
        "segments": segments,
        "lane_segments": lane_seg,
        "now_working": now_working,
        "gene_pool": _gene_pool(),
    }


def act(payload):
    """Ross's OWNER gate — accept/reject a task escalated to him. Recorded as
    ross_knechtel (his own authority), never a faked peer quorum. Append-only."""
    tid = payload.get("task_id")
    action = payload.get("action")
    note = (payload.get("note") or "")[:300]
    if not tid or action not in ("accept", "reject"):
        return {"ok": False, "error": "bad request"}
    snap = _load(SNAP, {"tasks": []})
    t = next((x for x in snap.get("tasks", []) if x.get("id") == tid), None)
    if not t:
        return {"ok": False, "error": "task not found"}
    if (t.get("state") or "").lower() not in ("awaiting_peer_signoff", "awaiting_verification", "ready_to_ship"):
        return {"ok": False, "error": "task is not awaiting sign-off"}
    import sys
    sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
    try:
        import qsb_council_tasks as C
        if action == "accept":
            C.note(tid, "ross_knechtel", "ACCEPTED by Ross via dash" + (": " + note if note else ""))
            C.update(tid, "ross_knechtel", state="done")
        else:
            C.note(tid, "ross_knechtel", "REJECTED by Ross via dash" + (": " + note if note else ""))
            C.update(tid, "ross_knechtel", state="blocked")
        return {"ok": True, "action": action, "task": tid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Task Council · Live Flow · :8864</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--wren:#22d3ee;--tp:#a855f7;--asa:#34d399;--bill:#f5b301;--codex:#ff8f3f;--bad:#ff6b6b;--ok:#39d98a;--warn:#f5c451}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1340px;margin:0 auto;padding:16px}
h1{margin:0;font-size:20px}h1 .n{color:var(--wren)}
.sub{color:var(--dim);margin:2px 0 10px;font-style:italic}
.kpis{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:7px 13px}
.kpi .v{font-size:19px;font-weight:700}.kpi .l{color:var(--dim);font-size:10px;text-transform:uppercase}
.auto{padding:8px 13px;border-radius:9px;margin-bottom:10px;font-size:12px;border:1px solid var(--line)}
.auto.ok{background:rgba(57,217,138,.10);border-color:var(--ok)}
.auto.stall{background:rgba(255,107,107,.12);border-color:var(--bad)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
.card h2{margin:0 0 8px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim)}
#flow{width:100%;height:400px}
#lanes{width:100%}
.beam{fill:none;stroke:var(--line);stroke-width:2;stroke-dasharray:6 10;animation:march var(--spd,4s) linear infinite;opacity:.4}
@keyframes march{to{stroke-dashoffset:-160}}
.bay{fill:#0d1420;stroke:var(--line);stroke-width:1.5}
.baylabel{fill:var(--dim);font-size:10px;text-transform:uppercase}
.baycount{fill:var(--txt);font-size:22px;font-weight:700}
.wgate{fill:#0d1420;stroke:var(--wren);stroke-width:2}
.wgate.act{animation:wpulse 1.1s ease-out}
@keyframes wpulse{0%{stroke-width:2}45%{stroke-width:6;filter:drop-shadow(0 0 16px var(--wren))}100%{stroke-width:2}}
.pulse{filter:drop-shadow(0 0 6px currentColor)}
.lanedot.act{animation:blink .9s ease-out}
@keyframes blink{0%{r:5}50%{r:11;opacity:1}100%{r:5;opacity:.5}}
.cols2{display:grid;grid-template-columns:1fr 340px;gap:12px}@media(max-width:900px){.cols2{grid-template-columns:1fr}}
.tickrow{border-bottom:1px solid var(--line);padding:3px 4px;font-size:11px;display:flex;gap:7px}
.tickrow.new{animation:flashin 1.5s ease-out}
@keyframes flashin{from{background:rgba(34,211,238,.20)}to{background:transparent}}
.av{border-bottom:1px solid var(--line);padding:5px 0;font-size:11px}
.mono{font-family:ui-monospace,monospace}.pill{color:var(--dim);font-size:11px}.dim{color:var(--dim)}
.badge{font-size:9px;padding:1px 6px;border-radius:999px;border:1px solid var(--line)}
.livehead{display:flex;align-items:center;gap:9px;margin:7px 0 11px}.live-dot{width:9px;height:9px;border-radius:50%;background:var(--bad);box-shadow:0 0 10px var(--bad)}
.live-dot.on{background:var(--ok);box-shadow:0 0 12px var(--ok);animation:livebeat 1.4s ease-in-out infinite}@keyframes livebeat{50%{transform:scale(1.45);opacity:.55}}
.progress-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:14px}@media(max-width:900px){.progress-grid{grid-template-columns:1fr}}
.hero-progress{height:24px;background:#090d14;border:1px solid var(--line);border-radius:999px;overflow:hidden;position:relative}
.hero-fill,.stage-fill,.rating-fill{height:100%;width:0;transition:width 1.35s cubic-bezier(.2,.8,.2,1);position:relative;overflow:hidden}
.hero-fill{background:linear-gradient(90deg,#5aa9ff,#8a5cf6,#39d98a)}
.hero-fill.live::after,.stage-fill.live::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 20%,rgba(255,255,255,.28) 45%,transparent 70%);transform:translateX(-120%);animation:sweep 2.2s linear infinite}@keyframes sweep{to{transform:translateX(120%)}}
.progress-labels{display:flex;justify-content:space-between;margin:5px 2px 0;font-size:11px;color:var(--dim)}
.stage-row{display:grid;grid-template-columns:90px 1fr 42px;gap:8px;align-items:center;margin:5px 0;font-size:11px}.stage-track{height:8px;background:#090d14;border-radius:999px;overflow:hidden}.stage-fill{background:linear-gradient(90deg,#5aa9ff,#8a5cf6)}
.rail{overflow:hidden;border:1px solid var(--line);border-radius:9px;background:#090d14;margin-bottom:12px;white-space:nowrap}.rail-track{display:inline-flex;min-width:max-content;animation:railscroll var(--rail-speed,45s) linear infinite}.rail:hover .rail-track{animation-play-state:paused}@keyframes railscroll{to{transform:translateX(-50%)}}
.rail-item{display:inline-flex;gap:7px;align-items:center;padding:8px 18px;border-right:1px solid var(--line);font:11px ui-monospace,monospace}.rail-empty{padding:8px 14px;color:var(--dim)}
.source-note{font-size:10px;color:var(--dim);margin-top:8px}.progress-number{font-size:26px;font-weight:800;color:var(--ok)}
</style></head><body><div class=wrap>
<h1>Task Council <span class=n>· Live Flow · :8864</span></h1>
<div class=sub>Every pulse is a real event from qsb_council_tasks.jsonl. No demo motion.</div>
<div class=livehead><span class=live-dot id=liveDot></span><b id=liveState>CONNECTING</b><span class=dim id=freshness>waiting for source freshness…</span></div>
<div class=kpis>
  <div class=kpi><div class=v id=kTotal>—</div><div class=l>tasks total</div></div>
  <div class=kpi><div class=v id=kActive>—</div><div class=l id=kActiveL>active board</div></div>
  <div class=kpi><div class=v id=kReserve style="color:var(--warn)">—</div><div class=l>reserve backlog</div></div>
  <div class=kpi><div class=v id=kOpen>—</div><div class=l>open</div></div>
  <div class=kpi><div class=v id=kVerify>—</div><div class=l>awaiting verify</div></div>
  <div class=kpi><div class=v id=kBlocked style="color:var(--bad)">—</div><div class=l>blocked</div></div>
  <div class=kpi><div class=v id=kDropped>—</div><div class=l>dropped</div></div>
  <div class=kpi><div class=v id=kDone>—</div><div class=l>done (claimed)</div></div>
  <div class=kpi><div class=v id=kVerified style="color:var(--ok)">—</div><div class=l>verified complete</div></div>
</div>
<div class=kpis id=principalRow></div>
<div class=auto id=auto>—</div>
<div class=card><h2>Real board progress — completion and governed journey</h2><div class=progress-grid>
  <div><div style="display:flex;align-items:end;justify-content:space-between"><div><span class=progress-number id=completionNum>—</span><span class=dim> verified complete</span></div><span class=dim id=movement>—</span></div><div class=hero-progress><div class=hero-fill id=completionBar></div></div><div class=progress-labels><span id=doneLabel>— verified / — done</span><span id=boardLabel>— active board · — reserve</span></div><div style="margin-top:12px"><b id=journeyNum>—</b> <span class=dim>state-weighted journey progress</span><div class=hero-progress style="height:12px;margin-top:4px"><div class=hero-fill id=journeyBar></div></div></div></div>
  <div id=stageBars></div>
</div><div class=source-note id=progressDefinition>Source: current snapshot + append-only council ledger.</div></div>
<div class=rail aria-label="Live scrolling council events"><div class=rail-track id=liveRail><span class=rail-empty>Waiting for real council events…</span></div></div>
<div class=card><h2>Live pipeline — Open → Claimed → Sandbox → Quorum → Wren Gate → Done</h2><svg id=flow></svg></div>
<div class=card><h2>⚡ Now working — each member's live active task (real snapshot, not counts)</h2><div id=nowWorking></div></div>
<div class=card id=genePoolCard><h2>🧬 Gene Pool — box providers (live)</h2><div id=genePool></div><div class=source-note>Source: live /health poll of each box gene pool on :8770 (20s cached). Providers self-heal — a box shown DOWN is genuinely unreachable.</div></div>
<div class=card><h2>🛤️ Per-member swim-lanes — where each member's work is parked</h2><svg id=lanes></svg></div>
<div class=card><h2>✅ Awaiting YOUR sign-off — tick to keep the council moving</h2><div id=signoff></div></div>
<div class=card><h2>Worker ratings /10 — real, from corrections &amp; rework</h2><div id=wstats></div></div>
<div class=card><h2>🟣 What the Council is doing — Wren, Bill, Codex, TP-Pip &amp; Acer-Cass live</h2><div id=teamActions></div></div>
<div class=cols2>
  <div class=card><h2>Live event ticker (real council actions)</h2><div id=ticker></div></div>
  <div>
    <div class=card><h2>Awaiting verification (Wren + quorum)</h2><div id=await></div></div>
    <div class=card><h2>Who's active now</h2><div id=actors></div></div>
  </div>
</div>
</div><script>
const NS="http://www.w3.org/2000/svg";
const COLS=["open","claimed","working","sandbox","quorum","wren_gate","done"];
const LABEL={open:"Open",claimed:"Claimed",working:"Working",sandbox:"Sandbox",quorum:"Quorum Verify",wren_gate:"Wren Gate",done:"Done"};
// ── ONE identity palette across the whole dashboard: a cyan train = Wren everywhere ──
const ACTORC={wren:"#22d3ee",tp_pip:"#a855f7",acer_cass:"#34d399",bill:"#f5b301",codex:"#ff8f3f",sandbox_gate:"#ff6b6b",pool:"#7d8da6"};
const LANE_LABEL={wren:"Wren",tp_pip:"TP-Pip",acer_cass:"Asa / Acer",bill:"Bill",codex:"Codex",pool:"Pool"};
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
function esc(s){return (''+(s==null?'':s)).replace(/</g,'&lt;')}
function agestr(ts){if(!ts)return '';const t=Date.parse((''+ts).replace(' ','T'));if(isNaN(t))return '';const s=Math.max(0,Math.round((Date.now()-t)/1000));return s<60?s+'s ago':s<3600?Math.round(s/60)+'m ago':Math.round(s/3600)+'h ago';}
const svg=document.getElementById("flow");let bayX={},seen=new Set(),first=true;
// ── persistent layer split ── static track/stations are rebuilt every 2s tick,
// but MOVING carriages live in their own group so a redraw never wipes a train
// mid-journey. This is what makes the motion smooth across refreshes.
let staticG=null,trainG=null,loopPathEl=null,trainSeq=0;
function layers(){
  if(!staticG||staticG.ownerSVGElement!==svg){
    svg.innerHTML="";
    staticG=el("g",{}); trainG=el("g",{class:"trains"});
    svg.appendChild(staticG); svg.appendChild(trainG);
  }
  return staticG;
}
function carriage(x,y,col,title){
  const g=el("g",{});
  g.appendChild(el("rect",{x:x-17,y:y,width:34,height:11,rx:3,fill:col,opacity:.92}));
  g.appendChild(el("rect",{x:x-13,y:y+2,width:8,height:4,rx:1,fill:"#0b0f17",opacity:.45}));
  g.appendChild(el("circle",{cx:x-9,cy:y+13,r:2,fill:"#1a2740"}));
  g.appendChild(el("circle",{cx:x+9,cy:y+13,r:2,fill:"#1a2740"}));
  if(title){const t=el("title");t.textContent=title;g.appendChild(t);}
  return g;
}
// ── a premium moving train: glow aura + engine + carriage + wheels + event glyph.
//    ret=true → rework/recycle return trip, tinted red + dashed so it reads apart.
function makeTrain(col,glyph,label,ret){
  const g=el("g",{class:"pulse"});g.style.color=col;
  g.appendChild(el("rect",{x:-20,y:-7,width:28,height:15,rx:5,fill:col,opacity:.16}));                 // soft glow aura
  g.appendChild(el("rect",{x:-18,y:-5,width:24,height:11,rx:3,fill:col,opacity:.96,
                           stroke:ret?"#ff6b6b":"none","stroke-width":ret?1.4:0,"stroke-dasharray":ret?"3 2":"0"}));
  g.appendChild(el("rect",{x:6,y:-6,width:13,height:13,rx:3,fill:col}));                                // engine
  g.appendChild(el("rect",{x:-14,y:-3,width:6,height:4,rx:1,fill:"#0b0f17",opacity:.5}));               // window
  g.appendChild(el("circle",{cx:-12,cy:8,r:2,fill:"#0b0f17"}));
  g.appendChild(el("circle",{cx:0,cy:8,r:2,fill:"#0b0f17"}));
  g.appendChild(el("circle",{cx:13,cy:8,r:2,fill:"#0b0f17"}));
  if(glyph){const t=el("text",{x:12.5,y:1.5,"text-anchor":"middle","font-size":8.5,fill:"#0b0f17","font-weight":700});t.textContent=glyph;g.appendChild(t);}
  if(label){const tt=el("title");tt.textContent=label;g.appendChild(tt);}
  return g;
}
// comet trail: a fading dot dropped at the train's current position each frame.
function spawnTrail(x,y,col,ret,layer){
  layer=layer||trainG;if(!layer)return;
  const c=el("circle",{cx:x,cy:y,r:2.6,fill:ret?"#ff6b6b":col,opacity:.45});
  layer.insertBefore(c,layer.firstChild);                                                              // paint behind trains
  c.animate([{opacity:.45},{opacity:0}],{duration:430,easing:"ease-out"}).onfinish=()=>c.remove();
}
// Underground-style station pulse when a train arrives.
function stationRipple(x,y,col,layer){
  layer=layer||trainG;if(!layer)return;
  const r=el("circle",{cx:x,cy:y,r:6,fill:"none",stroke:col,"stroke-width":2.5,opacity:.85});
  layer.appendChild(r);
  r.animate([{opacity:.85,strokeWidth:2.6},{opacity:0,strokeWidth:.4}],{duration:680,easing:"ease-out"});
  r.animate([{r:6},{r:22}],{duration:680,easing:"ease-out"}).onfinish=()=>r.remove();
}
// unified rAF train ride. getPos(u)->{x,y} for eased u in [0,1]; onArrive fires once.
// layer/tag/scale let the SAME engine drive both the main pipeline and each swim-lane.
function rideTrain(getPos,dur,col,glyph,label,ret,onArrive,layer,tag,scale){
  layer=layer||trainG;if(!layer)return;scale=scale||1;
  const g=makeTrain(col,glyph,label,ret);if(tag)g.dataset.m=tag;layer.appendChild(g);
  const t0=performance.now();let lastTrail=0;
  function frame(now){
    let u=(now-t0)/dur;if(u>1)u=1;
    const e=u<0.5?2*u*u:1-Math.pow(-2*u+2,2)/2;                                                        // easeInOut — accel off, ease in
    const p=getPos(e);g.setAttribute("transform",`translate(${p.x},${p.y}) scale(${scale})`);
    if(now-lastTrail>32){spawnTrail(p.x,p.y,col,ret,layer);lastTrail=now;}
    if(u>=1){if(onArrive)onArrive();g.animate([{opacity:1},{opacity:0}],{duration:300,easing:"ease-in"}).onfinish=()=>g.remove();return;}
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
// ── live per-segment throughput bar drawn ON the track between two stations.
//    Fill intensity = real 5m transition count; conveyor shimmer speed = real 60s
//    rate. Zero flow → dim bar, NO shimmer (a stalled handoff visibly sits still).
//    col tints the flow to the member's identity colour on swim-lanes.
function segBar(S,xa,xb,y,c60,c5m,loop,col){
  const w=xb-xa;if(w<10)return;col=col||"#5aa9ff";
  S.appendChild(el("rect",{x:xa,y:y-2.5,width:w,height:5,rx:2.5,fill:loop?"#4a3524":"#1a2434",opacity:.9}));
  S.appendChild(el("rect",{x:xa,y:y-2.5,width:w,height:5,rx:2.5,fill:loop?"#ff9d5c":col,opacity:Math.min(.72,.10+c5m*.09)}));
  if(c5m>0){const t=el("text",{x:(xa+xb)/2,y:y-6,"text-anchor":"middle",fill:loop?"#ff9d5c":col,"font-size":8.5,"font-weight":700});t.textContent=c5m;S.appendChild(t);}
  if(c60>0){                                                    // conveyor highlight — only when a REAL flow exists
    const from=loop?(xb-16):xa,to=loop?xa:(xb-16);
    const hl=el("rect",{x:from,y:y-2.5,width:16,height:5,rx:2.5,fill:loop?"#ffd7a0":"#eaf4ff",opacity:0});
    S.appendChild(hl);
    const dur=Math.max(650,Math.min(2600,2600/(1+c60)));         // busier segment = faster stream
    hl.animate([{transform:"translateX(0px)",opacity:0},{transform:`translateX(${(to-from)*.2}px)`,opacity:.8},
                {transform:`translateX(${(to-from)*.8}px)`,opacity:.8},{transform:`translateX(${to-from}px)`,opacity:0}],
               {duration:dur,iterations:Infinity,easing:"linear"});
  }
}
function draw(d){
  const S=layers();S.innerHTML="";
  const W=svg.clientWidth||1200,H=400;svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  const pad=66,tY=142,rg=8;
  const gap=(W-2*pad)/(COLS.length-1);
  COLS.forEach((c,i)=>bayX[c]=pad+i*gap);
  const x0=pad-30,x1=W-pad+30;
  // sleepers + two rails = the train track
  for(let x=x0;x<=x1;x+=15)S.appendChild(el("line",{x1:x,y1:tY-rg,x2:x,y2:tY+rg,stroke:"#2a3a52","stroke-width":3}));
  [tY-rg,tY+rg].forEach(ry=>S.appendChild(el("line",{x1:x0,y1:ry,x2:x1,y2:ry,stroke:"#5a7aa0","stroke-width":2.5})));
  // return loop — the track curves back = full circle (recycle/rework trains ride this)
  loopPathEl=el("path",{class:"beam",id:"returnLoop",fill:"none",stroke:"#5a7aa0","stroke-width":2.5,d:`M ${x1} ${tY} C ${W-14} ${tY}, ${W-14} ${tY+158}, ${W/2} ${tY+158} C ${14} ${tY+158}, ${14} ${tY}, ${x0} ${tY}`});
  S.appendChild(loopPathEl);
  {const rl=el("text",{x:W/2,y:tY+174,"text-anchor":"middle",fill:"#7d8da6","font-size":11});rl.textContent="↺ recycle / rework — the track loops full circle";S.appendChild(rl);}
  // Codex feeder engine onto the track at Open
  {const cx=bayX.open;
   const fb=el("path",{d:`M ${cx} 42 L ${cx} ${tY-rg-2}`,class:"beam"});fb.style.stroke="#ff9d5c";S.appendChild(fb);
   S.appendChild(el("circle",{cx:cx,cy:30,r:13,fill:"#0d1420",stroke:"#ff9d5c","stroke-width":2}));
   const ct=el("text",{x:cx,y:33,"text-anchor":"middle",fill:"#ff9d5c","font-size":8,"font-weight":700});ct.textContent="CODEX";S.appendChild(ct);
   const cl=el("text",{x:cx,y:12,"text-anchor":"middle",fill:"#7d8da6","font-size":9});cl.textContent=(d.codex_feed||0)+" in";S.appendChild(cl);}
  // ── live per-segment throughput bars (real transitions in the window) ──
  const seg=d.segments||{win60:{},win5m:{}};
  for(let i=1;i<COLS.length;i++){
    segBar(S,bayX[COLS[i-1]]+9,bayX[COLS[i]]-9,tY,(seg.win60||{})[COLS[i]]||0,(seg.win5m||{})[COLS[i]]||0,false);
  }
  // return-loop throughput = churn, tinted amber, flows right→left along the curve
  {const lc60=(seg.win60||{}).loop||0,lc5m=(seg.win5m||{}).loop||0;
   if(lc5m>0){
     const lp=el("path",{fill:"none",stroke:"#ff9d5c","stroke-width":3,opacity:Math.min(.8,.25+lc5m*.12),
       "stroke-dasharray":"10 12","stroke-linecap":"round",d:loopPathEl.getAttribute("d")});
     S.appendChild(lp);
     if(lc60>0){const dur=Math.max(700,Math.min(2600,2600/(1+lc60)));
       lp.animate([{strokeDashoffset:0},{strokeDashoffset:44}],{duration:dur,iterations:Infinity,easing:"linear"});}
     const lt=el("text",{x:W/2,y:tY+150,"text-anchor":"middle",fill:"#ff9d5c","font-size":9,"font-weight":700});lt.textContent="↺ "+lc5m+" rework/5m";S.appendChild(lt);
   }}
  // stations + carriages (tasks) parked on the track
  COLS.forEach(c=>{
    const x=bayX[c],SG=d.stages[c]||{count:0,tokens:[]};
    S.appendChild(el("circle",{cx:x,cy:tY,r:6,fill:"#0d1420",stroke:"#5aa9ff","stroke-width":2}));
    const lb=el("text",{x:x,y:tY-24,"text-anchor":"middle",class:"baylabel"});lb.textContent=LABEL[c];S.appendChild(lb);
    const cn=el("text",{x:x,y:tY-38,"text-anchor":"middle",fill:"#dce6f5","font-size":17,"font-weight":700});cn.textContent=SG.count;S.appendChild(cn);
    (SG.tokens||[]).slice(0,6).forEach((t,i)=>S.appendChild(carriage(x,tY+20+i*14,ACTORC[t.owner]||"#5aa9ff",t.id+" · "+t.title+(t.rework?` (rework ${t.rework})`:""))));
    if(SG.count>6){const m=el("text",{x:x,y:tY+20+6*14+7,"text-anchor":"middle",fill:"#7d8da6","font-size":9});m.textContent="+"+(SG.count-6)+" more";S.appendChild(m);}
  });
  // Wren gate arch straddling the track
  {const wx=bayX.wren_gate;
   S.appendChild(el("path",{class:"wgate",id:"wgate",fill:"none",stroke:"#22d3ee","stroke-width":3,d:`M ${wx-17} ${tY-4} L ${wx-17} ${tY-20} Q ${wx} ${tY-34}, ${wx+17} ${tY-20} L ${wx+17} ${tY-4}`}));
   const wt=el("text",{x:wx,y:tY-42,"text-anchor":"middle",fill:"#22d3ee","font-size":9,"font-weight":700});wt.textContent="WREN GATE";S.appendChild(wt);}
  pulse(d);
}
// EVENT → source stage index (COLS order). Destination stage comes from the
// backend (p.to). Every carriage is driven by a REAL ledger event; nothing spawns
// on a quiet feed. On first load we only SEED history (no motion) so the track is
// still until a genuinely new transition appears.
const EV_SRC={created:-1,proposed:-1,admission_voted:0,unblocked:0,claimed:0,assigned:0,acknowledged:0,
  updated:1,noted:1,tool_selected:1,sandbox_passed:2,sandbox_rejected:3,awaiting_verification:3,
  peer_signoff:4,done:5,recycled:6,reopened:6};
const GLYPH={created:"+",admission_voted:"+",unblocked:"+",claimed:"»",assigned:"»",acknowledged:"»",
  updated:"·",noted:"·",tool_selected:"⚙",sandbox_passed:"✓",sandbox_rejected:"✕",
  awaiting_verification:"?",peer_signoff:"✔",done:"★",recycled:"↺",reopened:"↺",blocked:"✕"};
function pulse(d){
  const tY=142,CAP=20;
  (d.pulses||[]).forEach(p=>{
    const key=p.ts+"|"+p.task+"|"+p.event;if(seen.has(key))return;seen.add(key);
    if(first)return;                                                   // seed history silently — only NEW events ride
    const toX=bayX[p.to];if(toX==null)return;
    const active=[...trainG.children].filter(n=>n.tagName==='g').length;
    if(active>=CAP)return;                                             // cap concurrent trains (cull excess)
    const col=ACTORC[p.actor]||"#5aa9ff",glyph=GLYPH[p.event]||"";
    const toIdx=COLS.indexOf(p.to);
    const srcIdx=(p.event in EV_SRC)?EV_SRC[p.event]:Math.max(0,toIdx-1);
    const label=(p.actor||'')+' · '+(p.event||'')+' · '+(p.task||'');
    const ret=(p.event==='recycled'||p.event==='reopened'||(toIdx>=0&&srcIdx-toIdx>=3));
    trainSeq++;const yb=tY-6+((trainSeq%3)-1)*8;                       // stagger so concurrent trains don't blob
    if(ret&&loopPathEl){
      const L=loopPathEl.getTotalLength();
      rideTrain(u=>loopPathEl.getPointAtLength(L*u),2600,col,glyph,label,true,()=>stationRipple(bayX.open,tY,"#ff6b6b"));
    }else{
      const fromX=srcIdx<0?(bayX.open-46):(bayX[COLS[srcIdx]]||toX-90);
      const dur=Math.min(1700,Math.max(680,Math.abs(toX-fromX)*3.2));
      rideTrain(u=>({x:fromX+(toX-fromX)*u,y:yb}),dur,col,glyph,label,false,()=>{
        stationRipple(toX,tY,col);
        if(p.actor==="wren"||p.to==="wren_gate"){const gt=document.getElementById("wgate");if(gt){gt.classList.remove("act");void gt.offsetWidth;gt.classList.add("act");}}
      });
    }
  });
  if(seen.size>3000)seen=new Set([...seen].slice(-1500));
}
// ── per-member swim-lanes (ADDITIVE — own SVG, own persistent train layer) ──
const laneSvg=document.getElementById("lanes");let laneBayX={},laneCY={},laneStaticG=null,laneTrainG=null;
function lrc(r){return r>=8?'#34d399':r>=5?'#f5b301':'#ff6b6b';}
// static lanes rebuilt each tick; lane carriages persist in their own group so a
// redraw never wipes a lane train mid-journey (mirrors the main pipeline split).
function laneLayers(){
  if(!laneStaticG||laneStaticG.ownerSVGElement!==laneSvg){
    laneSvg.innerHTML="";
    laneStaticG=el("g",{}); laneTrainG=el("g",{});
    laneSvg.appendChild(laneStaticG); laneSvg.appendChild(laneTrainG);
  }
  return laneStaticG;
}
function drawLanes(d){
  const LS=laneLayers();LS.innerHTML="";
  const members=d.lane_members||["wren","tp_pip","acer_cass","bill","codex","pool"];
  const W=laneSvg.clientWidth||1200,LGUT=150,pad=40,rg=7,laneH=92,topPad=20;
  const H=topPad+members.length*laneH+16;
  laneSvg.setAttribute("viewBox",`0 0 ${W} ${H}`);laneSvg.setAttribute("height",H);
  const gap=(W-LGUT-2*pad)/(COLS.length-1);
  COLS.forEach((c,i)=>laneBayX[c]=LGUT+pad+i*gap);
  const x0=laneBayX[COLS[0]]-24,x1=laneBayX[COLS[COLS.length-1]]+24;
  laneCY={};
  // shared station headers (one row at the top)
  COLS.forEach(c=>{const hx=laneBayX[c];const lb=el("text",{x:hx,y:topPad-4,"text-anchor":"middle",class:"baylabel"});lb.textContent=LABEL[c];LS.appendChild(lb);});
  members.forEach((m,k)=>{
    const cY=topPad+k*laneH+26,col=ACTORC[m]||"#7d8da6";
    if(m!=="pool")laneCY[m]=cY;                                       // pool has no actor stream
    const S=(d.lanes&&d.lanes[m])||{},sum=(d.lane_summary&&d.lane_summary[m])||{tasks:0,done:0,rating:0,avg_rework:0};
    const lseg=(d.lane_segments&&d.lane_segments[m])||{win60:{},win5m:{}};
    if(k>0)LS.appendChild(el("line",{x1:8,y1:cY-laneH/2+4,x2:W-8,y2:cY-laneH/2+4,stroke:"#1a2740","stroke-width":1}));
    // sleepers + two rails = this member's track (rails tinted to member identity)
    for(let x=x0;x<=x1;x+=15)LS.appendChild(el("line",{x1:x,y1:cY-rg,x2:x,y2:cY+rg,stroke:"#2a3a52","stroke-width":2}));
    [cY-rg,cY+rg].forEach(ry=>LS.appendChild(el("line",{x1:x0,y1:ry,x2:x1,y2:ry,stroke:col,"stroke-width":2,opacity:.55})));
    // live per-segment throughput bars — this member's real transitions only
    if(m!=="pool")for(let i=1;i<COLS.length;i++){
      segBar(LS,laneBayX[COLS[i-1]]+7,laneBayX[COLS[i]]-7,cY,(lseg.win60||{})[COLS[i]]||0,(lseg.win5m||{})[COLS[i]]||0,false,col);
    }
    // left gutter: member label + count + rating chip (right-aligned stat)
    const nm=el("text",{x:12,y:cY-2,fill:col,"font-size":14,"font-weight":700});nm.textContent=LANE_LABEL[m]||m;LS.appendChild(nm);
    const ct=el("text",{x:12,y:cY+14,fill:"#7d8da6","font-size":10});ct.textContent=`${sum.tasks} tasks · ${sum.done} done`;LS.appendChild(ct);
    const rt=el("text",{x:LGUT-14,y:cY-2,"text-anchor":"end",fill:lrc(sum.rating),"font-size":12,"font-weight":700});rt.textContent=`${sum.rating}/10`;LS.appendChild(rt);
    const rw=el("text",{x:LGUT-14,y:cY+14,"text-anchor":"end",fill:col,opacity:.75,"font-size":9});rw.textContent=`rework ${sum.avg_rework}`;LS.appendChild(rw);
    // stations + this member's carriages parked at each stage
    COLS.forEach(c=>{
      const x=laneBayX[c],toks=(S[c]||[]);
      LS.appendChild(el("circle",{cx:x,cy:cY,r:4,fill:"#0d1420",stroke:col,"stroke-width":1.5,opacity:.7}));
      if(toks.length){const cn=el("text",{x:x,y:cY-11,"text-anchor":"middle",fill:"#dce6f5","font-size":11,"font-weight":700});cn.textContent=toks.length;LS.appendChild(cn);}
      toks.slice(0,3).forEach((t,i)=>LS.appendChild(carriage(x,cY+14+i*13,ACTORC[t.owner]||col,t.id+" · "+t.title+(t.rework?` (rework ${t.rework})`:"")+` · ${t.rating}/10`)));
      if(toks.length>3){const mo=el("text",{x:x,y:cY+14+3*13+7,"text-anchor":"middle",fill:"#7d8da6","font-size":8});mo.textContent="+"+(toks.length-3);LS.appendChild(mo);}
    });
    // Wren gate arch on Wren's lane only (she is the gate) — cyan identity
    if(m==="wren"){const wx=laneBayX.wren_gate;LS.appendChild(el("path",{fill:"none",stroke:col,"stroke-width":2.5,d:`M ${wx-15} ${cY-3} L ${wx-15} ${cY-16} Q ${wx} ${cY-27}, ${wx+15} ${cY-16} L ${wx+15} ${cY-3}`}));}
  });
  lanePulse(d);
}
// Live lane carriages: the SAME real pulse feed, filtered by actor → each event
// rides ONLY its owner's lane. Quiet lane = still track; no fabricated motion.
function lanePulse(d){
  const CAP=5;
  (d.pulses||[]).forEach(p=>{
    const m=p.actor;if(!(m in laneCY))return;
    const key="L|"+p.ts+"|"+p.task+"|"+p.event;if(seen.has(key))return;seen.add(key);
    if(first)return;                                                  // seed history silently
    const toX=laneBayX[p.to];if(toX==null)return;
    const cY=laneCY[m],col=ACTORC[m]||"#7d8da6";
    const active=[...laneTrainG.children].filter(n=>n.tagName==='g'&&n.dataset.m===m).length;
    if(active>=CAP)return;                                            // per-lane cap
    const toIdx=COLS.indexOf(p.to);
    const srcIdx=(p.event in EV_SRC)?EV_SRC[p.event]:Math.max(0,toIdx-1);
    const fromX=srcIdx<0?(laneBayX.open-28):(laneBayX[COLS[srcIdx]]||toX-50);
    const ret=(p.event==='recycled'||p.event==='reopened'||(toIdx>=0&&srcIdx-toIdx>=3));
    const dur=Math.min(1500,Math.max(560,Math.abs(toX-fromX)*3));
    rideTrain(u=>({x:fromX+(toX-fromX)*u,y:cY}),dur,col,GLYPH[p.event]||"",
              m+' · '+(p.event||'')+' · '+(p.task||''),ret,
              ()=>stationRipple(toX,cY,col,laneTrainG),laneTrainG,m,0.7);
  });
}
async function tick(){
  let d;try{d=await(await fetch("/api/data")).json()}catch(e){return}
  if(window.__ver&&window.__ver!==d.ver){location.reload();return}window.__ver=d.ver;
  const k=d.kpis;kTotal.textContent=k.total;kOpen.textContent=k.open;kVerify.textContent=k.awaiting_verify;kBlocked.textContent=k.blocked;kDone.textContent=k.done;
  kActive.textContent=(k.active_board==null?'—':k.active_board);kActiveL.textContent='active board'+(k.active_board_cap?(' (cap '+k.active_board_cap+')'):'');
  kReserve.textContent=(k.reserved==null?'—':k.reserved);kDropped.textContent=(k.dropped==null?'—':k.dropped);kVerified.textContent=(k.verified==null?'—':k.verified);
  const p=d.progress||{},isLive=!!p.live,hasMotion=(p.recent_events_5m||0)>0;
  const prow=document.getElementById('principalRow');const pr=p.principals||{};const pk=Object.keys(pr);
  prow.innerHTML=pk.length?pk.map(n=>{const on=pr[n].online;const st=esc(pr[n].state||'?');return `<div class=kpi style="border-color:${on?'var(--ok)':'var(--bad)'}"><div class=v style="font-size:12px;color:${on?'var(--ok)':'var(--bad)'}">${on?'● ONLINE':'○ '+st}</div><div class=l>${esc(LANE_LABEL[n]||n)}</div></div>`}).join(''):'';
  liveDot.className='live-dot'+(isLive?' on':'');liveState.textContent=isLive?'LIVE SOURCES':'SOURCE STALE';liveState.style.color=isLive?'var(--ok)':'var(--bad)';
  freshness.textContent=`snapshot ${p.snapshot_age_s==null?'missing':p.snapshot_age_s+'s'} · ledger ${p.ledger_age_s==null?'missing':p.ledger_age_s+'s'} old · refresh 2s`;
  completionNum.textContent=(p.completion_pct==null?'—':p.completion_pct+'%');completionBar.style.width=(p.completion_pct||0)+'%';completionBar.className='hero-fill'+(hasMotion?' live':'');
  journeyNum.textContent=(p.journey_pct==null?'—':p.journey_pct+'%');journeyBar.style.width=(p.journey_pct||0)+'%';journeyBar.className='hero-fill'+(hasMotion?' live':'');
  doneLabel.textContent=`${p.verified||0} verified / ${p.done||0} done (${p.verification_rate==null?'—':p.verification_rate+'%'} proven)`;boardLabel.textContent=`${p.board_total||0} on pipeline · ${p.reserved||0} reserve`;movement.textContent=`${p.recent_events_60s||0} events/min · ${p.recent_events_5m||0} in 5 min`;
  progressDefinition.textContent='Source: qsb_council_tasks_snapshot.json + append-only qsb_council_tasks.jsonl · '+(p.definition||'');
  stageBars.innerHTML=(p.stages||[]).map(s=>{const pct=p.board_total?Math.round(100*s.count/p.board_total):0;return `<div class=stage-row><span>${esc(s.label)}</span><div class=stage-track><div class="stage-fill${hasMotion?' live':''}" style="width:${pct}%"></div></div><b style="text-align:right">${s.count}</b></div>`}).join('');
  const realRail=(d.ticker||[]).slice(0,18).map(r=>{const col=ACTORC[r.actor]||'#7d8da6';return `<span class=rail-item><span class=dim>${esc((r.ts||'').slice(11,19))}</span><b style="color:${col}">${esc(r.actor)}</b><span>${esc(r.event)}</span><span class=dim>${esc(r.task||'')} → ${esc(r.to||'')}</span></span>`}).join('');
  liveRail.innerHTML=realRail?(realRail+realRail):'<span class=rail-empty>No real events in the current ledger window.</span>';
  liveRail.style.animationPlayState=realRail?'running':'paused';
  const a=d.autorunner,ae=document.getElementById("auto");
  ae.className="auto "+(a.stalled?"stall":"ok");
  ae.innerHTML=a.stalled?`⚠ <b>AUTONOMOUS VERIFY STALLED</b> — last tick <b>${esc(a.tick)}</b>: ${esc(a.reason)} <span class=pill>${esc((a.ts||'').slice(11,19))}</span> · gate enabled=${a.enabled}`
    :`✓ autorunner ${esc(a.tick||'')} · gate enabled=${a.enabled} <span class=pill>${esc((a.ts||'').slice(11,19))}</span>`;
  draw(d);
  drawLanes(d);
  const nw=d.now_working||{};
  document.getElementById("nowWorking").innerHTML=(d.lane_members||[]).filter(m=>m!=='pool').map(m=>{
    const col=ACTORC[m]||'#7d8da6',lbl=esc(LANE_LABEL[m]||m),w=nw[m];
    if(!w)return `<div style="display:grid;grid-template-columns:120px 1fr;gap:10px;padding:5px 4px;border-bottom:1px solid var(--line);font-size:12px;align-items:center"><span style="color:${col};font-weight:700">${lbl}</span><span class=dim>idle — no active task</span></div>`;
    const st=esc(w.stage||w.state||''),age=agestr(w.last_ts);
    const last=w.last_event?`<span style="color:${col}">${esc(w.last_event)}</span>${w.last_to?(' → '+esc(w.last_to)):''}${age?(' <span class=dim>'+age+'</span>'):''}`:'<span class=dim>—</span>';
    return `<div style="display:grid;grid-template-columns:120px 84px 1fr 210px;gap:10px;padding:5px 4px;border-bottom:1px solid var(--line);font-size:12px;align-items:center"><span style="color:${col};font-weight:700">${lbl}</span><span class=badge style="color:${col};border-color:${col}">${st}</span><span><b class=mono>${esc(w.id)}</b> ${esc(w.title)}</span><span class=dim>${last}</span></div>`;
  }).join('');
  // ── 🧬 Gene Pool — live box providers (defensive: no data → honest fallback) ──
  const gpEl=document.getElementById("genePool");
  if(gpEl){
    const GP_COL={tp_pip:'var(--tp)',acer_cass:'var(--asa)'};
    const gp=d.gene_pool||{};const gpKeys=Object.keys(gp);
    gpEl.innerHTML=gpKeys.length?gpKeys.map(kk=>{
      const box=gp[kk]||{},on=!!box.online,col=GP_COL[kk]||'#7d8da6',lbl=esc(LANE_LABEL[kk]||kk);
      const provs=Array.isArray(box.providers)?box.providers:[];
      const pill=on?`<span class=badge style="color:var(--ok);border-color:var(--ok)">● ONLINE</span>`
                   :`<span class=badge style="color:var(--bad);border-color:var(--bad)">○ DOWN</span>`;
      const chips=on?(provs.length?provs.map(pv=>`<span class=badge style="color:${col};border-color:${col};margin:2px;display:inline-block">${esc(pv)}</span>`).join(''):'<span class=pill>no providers reported</span>'):'';
      return `<div style="padding:6px 2px;border-bottom:1px solid var(--line)"><div style="display:flex;align-items:center;gap:9px;margin-bottom:5px"><b style="color:${col}">${lbl}</b>${pill}<span class=dim>${on?(provs.length+' live provider'+(provs.length===1?'':'s')):'unreachable :8770'}</span></div><div>${chips}</div></div>`;
    }).join(''):'<span class=pill>gene-pool boxes not reporting</span>';
  }
  document.getElementById("ticker").innerHTML=(d.ticker||[]).map((r,i)=>{
    const col=ACTORC[r.actor]||"#7d8da6";
    const vd=r.verdict?` <b style="color:${r.verdict==='approve'?'#39d98a':'#ff6b6b'}">${esc(r.verdict)}</b>`:"";
    return `<div class="tickrow${(!first&&i===0)?' new':''}"><span class=dim>${esc((r.ts||'').slice(11,19))}</span><span style="color:${col};font-weight:700">${esc(r.actor)}</span><span>${esc(r.event)}${vd}</span><span class=dim>${esc(r.task||'')} → ${esc(r.to)}</span></div>`;
  }).join("");
  document.getElementById("await").innerHTML=(d.awaiting||[]).map(t=>`<div class=av><b class=mono>${esc(t.id)}</b> ${esc(t.title)}<br><span class=pill>owner ${esc(t.owner||'—')} · sandbox ${esc(t.sandbox_by||'—')} · signoff ${esc(t.signoff_by||'—')} ${t.verdict?('· '+esc(t.verdict)):''}${t.rework?(' · rework '+t.rework):''}</span></div>`).join('')||'<span class=pill>none awaiting</span>';
  document.getElementById("actors").innerHTML=Object.entries(d.actors||{}).map(([a,n])=>`<span class=badge style="color:${ACTORC[a]||'#7d8da6'};border-color:${ACTORC[a]||'#233146'};margin:2px;display:inline-block">${esc(a)} ${n}</span>`).join('');
  const rc=r=>r>=8?'var(--ok)':r>=5?'var(--warn)':'var(--bad)';
  document.getElementById("signoff").innerHTML=(d.awaiting_signoff||[]).map(t=>`<div style="border:1px solid var(--line);border-radius:8px;padding:8px;margin-bottom:6px;font-size:12px"><b class=mono>${esc(t.id)}</b> ${esc(t.title)}<br><span class=pill>${esc(t.state)} · owner ${esc(t.owner||t.created_by||'—')} · rework ${t.rework} · rating <b style="color:${rc(t.rating)}">${t.rating}/10</b></span><div style="margin-top:5px"><button onclick="act('${esc(t.id)}','accept')" style="background:var(--ok);color:#04120d;border:0;border-radius:6px;padding:5px 12px;font-weight:700;cursor:pointer">✓ Accept</button> <button onclick="act('${esc(t.id)}','reject')" style="background:transparent;border:1px solid var(--bad);color:var(--bad);border-radius:6px;padding:5px 12px;cursor:pointer">✕ Reject</button></div></div>`).join('')||'<span class=pill>nothing awaiting your sign-off</span>';
  document.getElementById("wstats").innerHTML=(d.worker_stats||[]).map(w=>`<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px"><span style="color:${ACTORC[w.actor]||'#7d8da6'};font-weight:700;width:96px">${esc(w.actor)}</span><div style="flex:1;height:8px;background:#0d1420;border-radius:6px;overflow:hidden"><div class="rating-fill${hasMotion?' live':''}" style="width:${w.avg_rating*10}%;background:${rc(w.avg_rating)}"></div></div><span class=pill>${w.avg_rating}/10 · ${w.tasks} tasks · ${w.done} done · avg rework ${w.avg_rework}</span></div>`).join('')||'<span class=pill>—</span>';
  document.getElementById("teamActions").innerHTML=(d.team_actions||[]).map(a=>`<div style="padding:3px 4px;border-bottom:1px solid var(--line);font-size:11px;display:grid;grid-template-columns:64px 92px 130px 1fr;gap:8px"><span class=dim>${esc((a.ts||'').slice(11,19))}</span><span style="color:${ACTORC[a.actor]||'#7d8da6'};font-weight:700">${esc(LANE_LABEL[a.actor]||a.actor)}</span><span>${esc(a.label)}</span><span class=dim>${esc(a.task||'')}</span></div>`).join('')||'<span class=pill>no recent council actions in the live ledger window</span>';
  first=false;
}
async function act(id,action){
  const note=action==='reject'?(prompt('Reject '+id+' — reason (optional):')||''):'';
  if(action==='reject'&&note===null)return;
  const r=await(await fetch('/api/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:id,action,note})})).json();
  if(r.ok){tick()}else{alert('failed: '+(r.error||'?'))}
}
tick();setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data") or self.path.startswith("/api/council"):
            # Presentation-only succession rule: Bill replaced Claude. Preserve
            # immutable source records, but expose no retired Claude identity or
            # stale wording through the live dashboard API.
            rendered = json.dumps(build())
            rendered = rendered.replace("CLAUDE", "BILL").replace("Claude", "Bill").replace("claude", "bill")
            b = rendered.encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if self.path.startswith("/api/act"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            b = json.dumps(act(payload)).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8864)
    a = ap.parse_args()
    print(f"council live flow dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
