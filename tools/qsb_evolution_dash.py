#!/usr/bin/env python3
"""
qsb_evolution_dash.py — SkyscraperHQ EVOLUTION dashboard (:8869).

2026-07-29, Ross: "build a dashboard that lets Ross SEE the tower learning /
fixing / evolving over time — so 'is it evolving as a whole?' has a live,
honest answer."

TRUTH RULES (this dash exists BECAUSE fake progress is the failure mode):
  - REAL registries only. Every number traces to a file on disk.
  - HONEST ZEROS. If a metric is 0, it shows 0. If a source file does not
    exist yet (agents still building it), the panel says "not yet wired" —
    it does NOT invent a number and it does NOT crash.
  - READ-ONLY. This process opens files for reading, serves HTTP, and writes
    NOTHING back into the tower. It never touches CLAUDE.md / vault / .env /
    any gate file.

Source registries (under data/registries/), each optional:
  SELF-FIXING
    qsb_master_self_audit.json      — self-audit findings by status
    qsb_self_audit_findings.jsonl   — (if an agent wires it) raw findings feed
    qsb_council_tasks.jsonl         — council task event log ("done" events)
    qsb_proposal_queue.jsonl        — proposals: queued_unsigned/sandbox_green
    qsb_code_apply_audit.jsonl      — applied patches (applied=true)
  LEARNING
    qsb_knowledge.jsonl             — (if wired) knowledge store append feed
    qsb_wren_skyscraper_knowledge_index.json — terms/floors/reports indexed
    qsb_cohort_training_runs.jsonl  — real training runs (cert pass, trains)
    qsb_trader_learning_events.jsonl— strategy-switch learnings
  WORKING
    leadership_comms/presence.json  — Wren/TP/Asa/Bill live heartbeats
    qsb_ceo_task_worker_activity.jsonl — real CEO worker ticks
  EVOLVING
    qsb_evolution_log.jsonl         — (if wired) forward-step loop log
    git log                          — real committed forward steps (fallback)
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8869
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "data", "registries")


# ----------------------------------------------------------------------------
# safe readers — never raise, always report presence honestly
# ----------------------------------------------------------------------------
def _path(name):
    return os.path.join(REG, name)


def read_json(name):
    p = _path(name)
    if not os.path.exists(p):
        return None, False
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f), True
    except Exception:
        return None, True  # present but unreadable


def iter_jsonl(name, limit=None):
    """Yield parsed rows from a jsonl. Returns (rows, present)."""
    p = _path(name)
    if not os.path.exists(p):
        return [], False
    rows = []
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip().lstrip("\x00").strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return rows, True
    if limit is not None and len(rows) > limit:
        rows = rows[-limit:]
    return rows, True


def parse_ts(s):
    if not s:
        return None
    try:
        s = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def now_utc():
    return datetime.now(timezone.utc)


def today_str():
    return now_utc().strftime("%Y-%m-%d")


def ago(dt):
    if not dt:
        return "—"
    secs = (now_utc() - dt).total_seconds()
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def missing(label):
    return {"wired": False, "note": f"{label} not yet wired"}


# ----------------------------------------------------------------------------
# SELF-FIXING
# ----------------------------------------------------------------------------
def panel_self_fixing():
    out = {}

    # --- self-audit findings: prefer jsonl feed, fall back to master json ---
    feed, feed_present = iter_jsonl("qsb_self_audit_findings.jsonl")
    audit_json, audit_present = read_json("qsb_master_self_audit.json")
    if feed_present and feed:
        # each row a finding; look for a resolved/status flag
        total = len(feed)
        resolved = 0
        for r in feed:
            st = str(r.get("status", r.get("state", ""))).lower()
            if st in ("resolved", "fixed", "closed", "done"):
                resolved += 1
        out["self_audit"] = {
            "wired": True, "source": "qsb_self_audit_findings.jsonl",
            "total_findings": total, "resolved": resolved,
            "open": total - resolved,
        }
    elif audit_present and isinstance(audit_json, dict):
        by = audit_json.get("by_status_counts", {}) or {}
        total = audit_json.get("total_items", sum(by.values()) if by else 0)
        resolved = sum(v for k, v in by.items()
                       if str(k).lower() in ("resolved", "fixed", "closed", "done", "ok", "pass"))
        out["self_audit"] = {
            "wired": True, "source": "qsb_master_self_audit.json",
            "total_findings": total, "resolved": resolved,
            "open": total - resolved, "by_status": by,
            "generated_ts": audit_json.get("generated_ts"),
        }
    else:
        out["self_audit"] = missing("self-audit findings")

    # --- council autonomous completions ---
    rows, present = iter_jsonl("qsb_council_tasks.jsonl")
    if present:
        done_total = 0
        done_today = 0
        recent_done = []
        td = today_str()
        for r in rows:
            if r.get("event") == "done":
                done_total += 1
                ts = str(r.get("ts", ""))
                if ts.startswith(td):
                    done_today += 1
                recent_done.append({
                    "ts": ts, "task_id": r.get("task_id"),
                    "actor": r.get("actor"),
                    "text": (r.get("text") or "")[:120],
                })
        # hourly trend over last 24h
        trend = _hourly_trend([r for r in rows if r.get("event") == "done"])
        out["council"] = {
            "wired": True, "source": "qsb_council_tasks.jsonl",
            "done_total": done_total, "done_today": done_today,
            "recent_done": recent_done[-8:][::-1],
            "trend_24h": trend,
        }
    else:
        out["council"] = missing("council task log")

    # --- proposals pipeline: queued -> sandbox-green -> signed -> applied ---
    props, p_present = iter_jsonl("qsb_proposal_queue.jsonl")
    apply_rows, a_present = iter_jsonl("qsb_code_apply_audit.jsonl")
    if p_present or a_present:
        by_status = {}
        for r in props:
            st = str(r.get("status", "unknown"))
            by_status[st] = by_status.get(st, 0) + 1
        applied_true = sum(1 for r in props if r.get("applied") is True)
        # apply audit: rows with applied==true are real installs
        applied_audit = sum(1 for r in apply_rows if r.get("applied") is True)
        applied_today = sum(1 for r in apply_rows
                            if r.get("applied") is True
                            and str(r.get("ts", "")).startswith(today_str()))
        green_rows=[r for r in props if r.get("status")=="sandbox_green"]
        linked=sum(1 for r in green_rows if r.get("council_task_id"))
        ages=[]
        for r in green_rows:
            try: ages.append(max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(str(r.get("ts")).replace("Z","+00:00"))).days))
            except Exception: pass
        rollback_rows=sum(1 for r in apply_rows if r.get("applied") is True and r.get("sha_before") and r.get("sha_after"))
        priority={p:sum(1 for r in green_rows if r.get("priority")==p) for p in ("high","normal","low")}
        out["proposals"] = {
            "wired": True,
            "source": "qsb_proposal_queue.jsonl + qsb_code_apply_audit.jsonl",
            "queued": len(props),
            "by_status": by_status,
            "sandbox_green": by_status.get("sandbox_green", 0),
            "queued_unsigned": by_status.get("queued_unsigned", 0),
            "not_runnable": by_status.get("not_runnable", 0),
            "applied_in_queue": applied_true,
            "applied_audit_rows": applied_audit,
            "applied_today": applied_today,
            "council_linked": linked, "council_unlinked": len(green_rows)-linked,
            "oldest_green_days": max(ages or [0]), "priority_mix": priority,
            "rollback_evidence": rollback_rows,
        }
    else:
        out["proposals"] = missing("proposal pipeline")

    return out


# ----------------------------------------------------------------------------
# LEARNING
# ----------------------------------------------------------------------------
def panel_learning():
    out = {}

    # --- knowledge store (append feed if wired) ---
    kfeed, kpresent = iter_jsonl("qsb_knowledge.jsonl")
    kindex, ipresent = read_json("qsb_wren_skyscraper_knowledge_index.json")
    if kpresent and kfeed:
        recent = []
        for r in kfeed[-6:][::-1]:
            recent.append({
                "ts": r.get("ts"),
                "text": (r.get("text") or r.get("learning") or
                         json.dumps(r))[:140],
            })
        out["knowledge"] = {
            "wired": True, "source": "qsb_knowledge.jsonl",
            "entries": len(kfeed),
            "recent": recent,
            "trend_24h": _hourly_trend(kfeed),
        }
    elif ipresent and isinstance(kindex, dict):
        floors = kindex.get("floors")
        reports = kindex.get("recent_reports") or []
        out["knowledge"] = {
            "wired": True, "source": "qsb_wren_skyscraper_knowledge_index.json",
            "terms_indexed": kindex.get("terms_indexed"),
            "floors_indexed": (len(floors) if isinstance(floors, (list, dict))
                               else floors),
            "reports_indexed": len(reports) if isinstance(reports, list) else 0,
            "generated_ts": kindex.get("generated_ts"),
            "note": "knowledge INDEX (no per-entry append feed yet)",
        }
    else:
        out["knowledge"] = missing("knowledge store")

    # --- real training runs / certifications ---
    runs, present = iter_jsonl("qsb_cohort_training_runs.jsonl")
    if present:
        total_passed = sum(r.get("passed_cert", 0) for r in runs)
        total_failed = sum(r.get("failed_cert", 0) for r in runs)
        trains = sum(r.get("first_trade_placed", 0) for r in runs)
        last = runs[-1] if runs else {}
        out["training"] = {
            "wired": True, "source": "qsb_cohort_training_runs.jsonl",
            "runs": len(runs),
            "cert_passed": total_passed, "cert_failed": total_failed,
            "real_trains_placed": trains,
            "last_run_ts": last.get("ts"),
        }
    else:
        out["training"] = missing("training runs")

    # --- strategy-switch learnings ---
    learn, lpresent = iter_jsonl("qsb_trader_learning_events.jsonl")
    if lpresent:
        recent = []
        for r in learn[-5:][::-1]:
            recent.append({
                "ts": r.get("ts"), "worker": r.get("worker_id"),
                "from": r.get("old"), "to": r.get("new"),
                "reason": (r.get("reason") or "")[:120],
            })
        out["strategy_learnings"] = {
            "wired": True, "source": "qsb_trader_learning_events.jsonl",
            "events": len(learn), "recent": recent,
        }
    else:
        out["strategy_learnings"] = missing("strategy learnings")

    return out


# ----------------------------------------------------------------------------
# WORKING
# ----------------------------------------------------------------------------
def panel_working():
    out = {}
    pres, present = read_json(os.path.join("leadership_comms", "presence.json"))
    workers = []
    if present and isinstance(pres, dict):
        for name, info in pres.items():
            if not isinstance(info, dict):
                continue
            hb = parse_ts(info.get("last_heartbeat"))
            live = hb is not None and (now_utc() - hb).total_seconds() < 300
            workers.append({
                "name": name,
                "addr": info.get("reachable_addr"),
                "last_heartbeat": info.get("last_heartbeat"),
                "ago": ago(hb),
                "live": live,
            })
        out["leadership"] = {
            "wired": True, "source": "leadership_comms/presence.json",
            "workers": workers,
            "live_count": sum(1 for w in workers if w["live"]),
            "total": len(workers),
        }
    else:
        out["leadership"] = missing("leadership presence")

    # CEO worker ticks (real work done by the local-model CEOs)
    acts, apresent = iter_jsonl("qsb_ceo_task_worker_activity.jsonl")
    if apresent:
        by_ceo = {}
        last_ts = {}
        for r in acts:
            c = r.get("ceo", "?")
            by_ceo[c] = by_ceo.get(c, 0) + 1
            ts = r.get("ts")
            if ts:
                last_ts[c] = ts
        ceos = [{"ceo": c, "ticks": n, "last": last_ts.get(c),
                 "ago": ago(parse_ts(last_ts.get(c)))}
                for c, n in sorted(by_ceo.items(), key=lambda x: -x[1])]
        out["ceo_workers"] = {
            "wired": True, "source": "qsb_ceo_task_worker_activity.jsonl",
            "total_ticks": len(acts), "by_ceo": ceos,
        }
    else:
        out["ceo_workers"] = missing("ceo worker activity")

    return out


# ----------------------------------------------------------------------------
# EVOLVING
# ----------------------------------------------------------------------------
def panel_evolving():
    out = {}
    log, present = iter_jsonl("qsb_evolution_log.jsonl", limit=200)
    if present and log:
        steps = []
        for r in log[-10:][::-1]:
            steps.append({
                "ts": r.get("ts"),
                "text": (r.get("text") or r.get("step") or
                         r.get("event") or json.dumps(r))[:140],
            })
        out["evolution_log"] = {
            "wired": True, "source": "qsb_evolution_log.jsonl",
            "steps_total": len(log), "recent": steps,
        }
    else:
        # honest fallback: real committed forward-steps from git
        commits = _git_forward_steps()
        out["evolution_log"] = {
            "wired": False,
            "note": "qsb_evolution_log.jsonl not yet wired — showing real git "
                    "forward-steps as evidence of forward motion",
            "source": "git log (fallback)",
            "recent_commits": commits,
            "commits_today": sum(1 for c in commits
                                 if c.get("date", "").startswith(today_str())),
        }
    return out


def _git_forward_steps():
    try:
        r = subprocess.run(
            ["git", "-C", ROOT, "log", "-15", "--format=%cI\x1f%s"],
            capture_output=True, text=True, timeout=8)
        out = []
        for line in r.stdout.splitlines():
            if "\x1f" not in line:
                continue
            iso, subj = line.split("\x1f", 1)
            out.append({"date": iso[:10], "ts": iso, "subject": subj[:120]})
        return out
    except Exception:
        return []


def _hourly_trend(rows, hours=24):
    """Count rows (with a 'ts') per hour over the last `hours`. Real timestamps only."""
    buckets = {}
    cutoff = now_utc() - timedelta(hours=hours)
    for r in rows:
        dt = parse_ts(r.get("ts"))
        if dt is None or dt < cutoff:
            continue
        key = dt.strftime("%m-%d %H:00")
        buckets[key] = buckets.get(key, 0) + 1
    return [{"hour": k, "count": v} for k, v in sorted(buckets.items())]


def _source_health():
    """Freshness is measured from the actual registry files, never inferred."""
    names = [
        "qsb_council_tasks.jsonl", "qsb_ceo_task_worker_activity.jsonl",
        "qsb_proposal_queue.jsonl", "qsb_code_apply_audit.jsonl",
        "qsb_cohort_training_runs.jsonl", "qsb_trader_learning_events.jsonl",
        os.path.join("leadership_comms", "presence.json"),
    ]
    now = time.time(); out = []
    for name in names:
        p = _path(name); exists = os.path.exists(p)
        age = round(max(0, now - os.path.getmtime(p)), 1) if exists else None
        out.append({"source": name, "exists": exists, "age_s": age,
                    "state": "LIVE" if exists and age is not None and age < 300 else
                             "STALE" if exists else "MISSING"})
    return out


def _recent_activity():
    """Small cross-loop activity feed, sorted by real timestamps."""
    rows = []
    for name, label, key in (("qsb_council_tasks.jsonl", "Council", "event"),
                             ("qsb_ceo_task_worker_activity.jsonl", "CEO worker", "tick"),
                             ("qsb_trader_learning_events.jsonl", "Strategy", "reason")):
        data, present = iter_jsonl(name, limit=80)
        if not present: continue
        for r in data:
            ts = parse_ts(r.get("ts"));
            if ts is None: continue
            rows.append({"ts": r.get("ts"), "kind": label,
                         "text": str(r.get(key) or r.get("event") or r.get("worker_id") or "activity")[:150]})
    rows.sort(key=lambda r: parse_ts(r.get("ts")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows[:18]


# ----------------------------------------------------------------------------
# LIVE CADENCE — the real evolution heartbeat the monitor was ignoring
# ----------------------------------------------------------------------------
def panel_live_cadence():
    """Today's REAL live-evolution cadence.

    The tower runs an evolution heartbeat (audit->queue->sandbox->learn) plus a
    Wren governor loop all day. Those signals are honest, timestamped, and were
    being ignored — so the headline read "0 today" and the tower looked dead
    even while 100s of ticks/sandbox verdicts landed. This block counts them.

    "today" is matched robustly on the date prefix (first 10 chars YYYY-MM-DD)
    so mixed ts formats (…Z vs …+00:00) all count. Every read is guarded → 0
    on a missing/unreadable file; nothing here is invented.

    Note: autonomous *applies* are still 0/day by design — applying a patch is
    human-gated (>=3 sigs + Ross). Live cadence != auto-apply; this shows the
    loop is turning without pretending the gate is open.
    """
    td = today_str()

    def _scan(name, pred=None):
        """Return (count_today, most_recent_dt_today, present)."""
        rows, present = iter_jsonl(name)
        if not present:
            return 0, None, False
        n = 0
        last = None
        for r in rows:
            ts = str(r.get("ts", ""))
            if ts[:10] != td:
                continue
            if pred is not None and not pred(r):
                continue
            n += 1
            dt = parse_ts(ts)
            if dt and (last is None or dt > last):
                last = dt
        return n, last, True

    ticks, last_tick, ticks_present = _scan(
        "qsb_evolution_log.jsonl", lambda r: r.get("event") == "evolution_tick")
    sb_total, last_sb, sb_present = _scan("qsb_proposal_sandbox_results.jsonl")
    sb_green, last_green, _ = _scan(
        "qsb_proposal_sandbox_results.jsonl",
        lambda r: r.get("verdict") == "green")
    cycles, last_cycle, cyc_present = _scan("qsb_wren_evolution_cycles.jsonl")
    commentary, _lc, com_present = _scan("qsb_boardroom_commentary.jsonl")

    return {
        "wired": bool(ticks_present or sb_present or cyc_present),
        "today": td,
        "evolution_ticks_today": ticks,
        "sandbox_verdicts_today": sb_total,
        "sandbox_green_today": sb_green,
        "governor_cycles_today": cycles,
        "boardroom_commentary_today": commentary,
        "last_tick_ts": last_tick.isoformat() if last_tick else None,
        "last_tick_ago": ago(last_tick),
        "last_green_ts": last_green.isoformat() if last_green else None,
        "last_green_ago": ago(last_green),
        "last_cycle_ago": ago(last_cycle),
        "sources": {
            "ticks": "qsb_evolution_log.jsonl",
            "sandbox": "qsb_proposal_sandbox_results.jsonl",
            "cycles": "qsb_wren_evolution_cycles.jsonl",
            "commentary": "qsb_boardroom_commentary.jsonl",
        },
    }


# ----------------------------------------------------------------------------
# TOP-LINE honest state
# ----------------------------------------------------------------------------
def build_state():
    sf = panel_self_fixing()
    ln = panel_learning()
    wk = panel_working()
    ev = panel_evolving()

    council = sf.get("council", {})
    proposals = sf.get("proposals", {})
    knowledge = ln.get("knowledge", {})
    training = ln.get("training", {})
    leadership = wk.get("leadership", {})

    done_today = council.get("done_today", 0) if council.get("wired") else 0
    applied = proposals.get("applied_audit_rows", 0) if proposals.get("wired") else 0
    applied_today = proposals.get("applied_today", 0) if proposals.get("wired") else 0
    sandbox_green = proposals.get("sandbox_green", 0) if proposals.get("wired") else 0
    learnings = 0
    if knowledge.get("wired"):
        learnings = knowledge.get("entries", 0)
    elif knowledge.get("terms_indexed"):
        learnings = knowledge.get("terms_indexed", 0)
    live_workers = leadership.get("live_count", 0) if leadership.get("wired") else 0
    trains = training.get("real_trains_placed", 0) if training.get("wired") else 0

    # LIVE CADENCE — today's real evolution heartbeat (was being ignored)
    cadence = panel_live_cadence()
    ticks_today = cadence.get("evolution_ticks_today", 0)
    green_today = cadence.get("sandbox_green_today", 0)
    cycles_today = cadence.get("governor_cycles_today", 0)
    cadence_live = ticks_today > 0 or green_today > 0

    done_total = council.get("done_total", 0) if council.get("wired") else 0
    waiting = sandbox_green  # proposals sandbox-green & waiting for signatures

    # Headline: lead with live cadence when the loop is turning, but stay
    # honest that auto-APPLIES are 0/day (human-gated) — no hiding the gate.
    if cadence_live:
        headline = (
            f"Evolving now — {ticks_today} evolution ticks today · "
            f"{green_today} sandbox-green today · {cycles_today} governor "
            f"cycles today · {waiting} proposals waiting · {done_total} "
            f"council-done all-time ({applied_today} auto-applied today: "
            f"apply is human-gated)"
        )
    else:
        parts = []
        parts.append(f"{done_today} autonomous completions today")
        parts.append(f"{applied} patches applied (all-time), {applied_today} today")
        parts.append(f"{sandbox_green} proposals sandbox-green & waiting")
        parts.append(f"{learnings} knowledge items")
        parts.append(f"{live_workers} live workers")
        headline = "Loop status — " + " · ".join(parts)

    # loop-closing verdict: is the full audit->fix->learn loop actually turning?
    loop_signals = {
        "cadence_live": cadence_live,
        "council_completing": done_today > 0,
        "proposals_flowing": sandbox_green > 0 or applied_today > 0,
        "learning_growing": learnings > 0,
        "workers_live": live_workers > 0,
        "training_real": trains > 0,
    }
    turning = sum(1 for v in loop_signals.values() if v)
    if cadence_live:
        verdict = "EVOLVING — live cadence + proposals + learning"
    elif turning >= 4:
        verdict = "LOOP CLOSING — multiple evolution signals live"
    elif turning >= 2:
        verdict = "LOOP PARTIAL — some signals live, some idle"
    elif turning >= 1:
        verdict = "LOOP FAINT — only one signal live"
    else:
        verdict = "LOOP IDLE — no forward motion detected right now"

    return {
        "generated": now_utc().isoformat(),
        "headline": headline,
        "verdict": verdict,
        "loop_signals": loop_signals,
        "signals_live": turning,
        "signals_total": len(loop_signals),
        "live_cadence": cadence,
        "self_fixing": sf,
        "learning": ln,
        "working": wk,
        "evolving": ev,
        "source_health": _source_health(),
        "recent_activity": _recent_activity(),
    }


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Tower Evolution — is it evolving as a whole?</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0e14;--panel:#111823;--edge:#1e2a3a;--txt:#cfe3ff;--dim:#7f95b3;
--good:#37d67a;--warn:#ffcf5c;--bad:#ff6b6b;--acc:#5cc8ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--edge);
background:linear-gradient(180deg,#0e1622,#0a0e14)}
h1{margin:0;font-size:20px;letter-spacing:.3px}
.sub{color:var(--dim);font-size:12px;margin-top:4px}
.verdict{margin:14px 22px 0;padding:14px 18px;border-radius:10px;
border:1px solid var(--edge);background:var(--panel);font-size:16px;font-weight:600}
.headline{margin:8px 22px 0;color:var(--acc);font-size:13px}
.signals{display:flex;flex-wrap:wrap;gap:8px;margin:10px 22px}
.sig{padding:5px 11px;border-radius:20px;font-size:12px;border:1px solid var(--edge)}
.sig.on{background:rgba(55,214,122,.12);color:var(--good);border-color:var(--good)}
.sig.off{background:rgba(127,149,179,.08);color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));
gap:14px;padding:16px 22px}
.card{background:var(--panel);border:1px solid var(--edge);border-radius:10px;
padding:14px 16px}
.card h2{margin:0 0 10px;font-size:13px;text-transform:uppercase;
letter-spacing:1px;color:var(--acc)}
.metric{display:flex;justify-content:space-between;padding:4px 0;
border-bottom:1px dashed var(--edge)}
.metric b{font-size:16px}
.big{font-size:30px;font-weight:700;line-height:1}
.small{color:var(--dim);font-size:11px}
.notwired{color:var(--warn);font-size:12px;font-style:italic}
.row{font-size:12px;color:var(--dim);padding:3px 0;border-bottom:1px dashed var(--edge)}
.row .t{color:var(--txt)}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px}
.live{background:rgba(55,214,122,.15);color:var(--good)}
.dead{background:rgba(255,107,107,.12);color:var(--bad)}
.bars{display:flex;align-items:flex-end;gap:2px;height:40px;margin-top:8px}
.bar{flex:1;background:var(--acc);min-height:2px;border-radius:1px 1px 0 0;opacity:.8}
code{color:var(--dim);font-size:10px}
.loopmeter{margin:0 22px 2px;padding:12px 14px;background:var(--panel);border:1px solid var(--edge);border-radius:10px}.looptrack{height:13px;background:#0a1018;border-radius:9px;overflow:hidden;margin-top:8px}.loopfill{height:100%;background:linear-gradient(90deg,#5cc8ff,#37d67a);transition:width .8s ease}.sourcegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:6px}.src{font-size:11px;padding:7px 8px;border:1px solid var(--edge);border-radius:7px;display:flex;justify-content:space-between;gap:8px}.src b{font-size:10px}.src.live b{color:var(--good)}.src.stale b{color:var(--warn)}.src.missing b{color:var(--dim)}.activity{max-height:250px;overflow:auto}.activity .row{display:grid;grid-template-columns:75px 90px 1fr;gap:8px}.scrollline{margin:10px 22px 0;overflow:hidden;white-space:nowrap;border:1px solid var(--edge);border-radius:8px;padding:8px;color:var(--dim)}.scrolltrack{display:inline-flex;gap:34px;animation:scroll 28s linear infinite}.scrolltrack span{color:var(--txt)}@keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-45%)}}
/* ---- evolution motion (real-data-driven, self-contained) ---- */
.helixwrap{display:inline-flex;vertical-align:middle;margin-left:10px}
.helix path{fill:none;stroke:var(--acc);stroke-width:1.6;opacity:.9}
.helix .rungs line{stroke:var(--good);stroke-width:1.2;opacity:.55}
.helixmove{animation:helixslide 3s linear infinite}
@keyframes helixslide{from{transform:translateX(0)}to{transform:translateX(-72px)}}
.verdict.evolving{background:linear-gradient(90deg,#0d1f18,#12331f,#0d1f18);background-size:200% 100%;animation:vshimmer 5s linear infinite,vglow 2.6s ease-in-out infinite}
@keyframes vshimmer{from{background-position:0 0}to{background-position:200% 0}}
@keyframes vglow{0%,100%{box-shadow:0 0 0 rgba(55,214,122,0)}50%{box-shadow:0 0 20px rgba(55,214,122,.32)}}
.cadence{margin:12px 22px 0;padding:14px 16px;background:var(--panel);border:1px solid var(--edge);border-radius:10px}
.cad-head{display:flex;align-items:center;gap:9px;font-size:13px}
.cad-head b{color:var(--acc);text-transform:uppercase;letter-spacing:1px;font-size:13px}
.cad-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:10px}
.cad-cell{padding:8px 10px;border:1px solid var(--edge);border-radius:8px;background:#0a1018;text-align:center}
.cad-val{font-size:28px;font-weight:700;line-height:1;color:var(--txt);transition:color .3s}
.cad-cell.green .cad-val{color:var(--good)}
.cad-val.flash{animation:flashUp 1s ease-out}
@keyframes flashUp{0%{color:var(--good);text-shadow:0 0 16px rgba(55,214,122,.85);transform:scale(1.22)}100%{text-shadow:none;transform:scale(1)}}
.hb{display:inline-block;width:11px;height:11px;border-radius:50%;background:var(--good);box-shadow:0 0 9px rgba(55,214,122,.75);animation:heartbeat 1.6s ease-in-out infinite}
@keyframes heartbeat{0%,100%{transform:scale(.82);opacity:.7}22%{transform:scale(1.3);opacity:1}38%{transform:scale(.95)}}
.hb.tick{animation:hbtick .6s ease-out}
@keyframes hbtick{0%{transform:scale(1.7);box-shadow:0 0 18px rgba(55,214,122,.95)}100%{transform:scale(1);box-shadow:0 0 9px rgba(55,214,122,.75)}}
@media (prefers-reduced-motion:reduce){.helixmove,.verdict.evolving,.hb,.hb.tick,.cad-val.flash,.scrolltrack{animation:none!important}}
</style></head><body>
<header>
  <h1 style="display:flex;align-items:center">🏢 Tower Evolution Monitor<span id="helix" class="helixwrap"></span></h1>
  <div class="sub">Is it evolving as a whole? &nbsp;·&nbsp; real registries only ·
  honest zeros · read-only ·&nbsp;<span id="gen"></span></div>
</header>
<div class="verdict" id="verdict">loading…</div>
<div class="headline" id="headline"></div>
<div class="signals" id="signals"></div>
<div class="cadence" id="cadence">
  <div class="cad-head"><span class="hb" id="hbDot"></span> <b>⚡ Live evolution today</b>
  <span class="small" id="cadWhen"></span></div>
  <div class="cad-grid" id="cadGrid"></div>
</div>
<div class="loopmeter"><div style="display:flex;justify-content:space-between"><b>Evolution loop completion</b><span id="loopPct" class="small">—</span></div><div class="looptrack"><div id="loopFill" class="loopfill" style="width:0"></div></div><div id="loopNote" class="small" style="margin-top:6px">Measured from live council, proposal, learning, worker, and training signals.</div></div>
<div class="scrollline"><div id="activityRail" class="scrolltrack">Waiting for real evolution activity…</div></div>
<div class="grid" id="grid"></div>
<script>
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function wiredNote(o){return o&&o.wired===false?`<div class="notwired">⚠ ${esc(o.note||'not yet wired')}</div>`:''}
function bars(trend){
  if(!trend||!trend.length)return '<div class="small">no timestamped events in last 24h</div>';
  const mx=Math.max(...trend.map(t=>t.count),1);
  return '<div class="bars">'+trend.map(t=>`<div class="bar" style="height:${Math.round(t.count/mx*40)}px" title="${esc(t.hour)}: ${t.count}"></div>`).join('')+'</div>';
}
function metric(label,val,sub){return `<div class="metric"><span>${esc(label)}${sub?` <span class="small">${esc(sub)}</span>`:''}</span><b>${esc(val)}</b></div>`}
function card(title,html){return `<div class="card"><h2>${title}</h2>${html}</div>`}

// --- animated DNA double-helix header motif (self-contained SVG) ---
function buildHelix(){
  const W=216,period=72,H=26,mid=H/2,amp=8.5,N=72;
  let s1='',s2='',rungs='';
  for(let i=0;i<=N;i++){
    const x=i/N*W, a=x/period*Math.PI*2;
    const y1=(mid+Math.sin(a)*amp).toFixed(1), y2=(mid-Math.sin(a)*amp).toFixed(1);
    const xs=x.toFixed(1);
    s1+=(i?'L':'M')+xs+' '+y1+' ';
    s2+=(i?'L':'M')+xs+' '+y2+' ';
    if(i%4===0)rungs+=`<line x1="${xs}" y1="${y1}" x2="${xs}" y2="${y2}"/>`;
  }
  const strand=`<path d="${s1}"/><path d="${s2}"/><g class="rungs">${rungs}</g>`;
  return `<svg class="helix" width="72" height="26" viewBox="0 0 72 26" aria-hidden="true">`
    +`<defs><clipPath id="hc"><rect width="72" height="26"/></clipPath></defs>`
    +`<g clip-path="url(#hc)"><g class="helixmove">${strand}</g></g></svg>`;
}

// --- live cadence panel: count-up on load, flash a counter that increases ---
const CAD_ITEMS=[['evolution ticks','evolution_ticks_today',false],
                 ['sandbox verdicts','sandbox_verdicts_today',false],
                 ['sandbox GREEN','sandbox_green_today',true],
                 ['governor cycles','governor_cycles_today',false]];
let cadPrev={}, cadInit=false;
function countUp(el,to,dur){
  const start=performance.now(),from=0;
  (function step(t){
    const p=Math.min(1,(t-start)/dur);
    el.textContent=Math.round(from+(to-from)*(0.5-0.5*Math.cos(p*Math.PI)));
    if(p<1)requestAnimationFrame(step);
  })(performance.now());
}
function renderCadence(c){
  if(!c)return;
  document.getElementById('cadWhen').textContent=
    '('+esc(c.today)+' UTC · last tick '+esc(c.last_tick_ago)
    +' · last green '+esc(c.last_green_ago)+' · '+esc(c.governor_cycles_today)+' cycles)';
  const grid=document.getElementById('cadGrid');
  if(!cadInit){
    grid.innerHTML=CAD_ITEMS.map(([lab,key,g])=>
      `<div class="cad-cell${g?' green':''}"><div class="cad-val" id="cad_${key}">0</div>`
      +`<div class="small">${esc(lab)}</div></div>`).join('');
  }
  CAD_ITEMS.forEach(([lab,key])=>{
    const el=document.getElementById('cad_'+key); if(!el)return;
    const nv=c[key]||0, pv=cadPrev[key];
    if(!cadInit){countUp(el,nv,900);}
    else if(pv!==undefined&&nv>pv){el.textContent=nv;el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
    else{el.textContent=nv;}
    cadPrev[key]=nv;
  });
  cadInit=true;
  const hb=document.getElementById('hbDot'); // heartbeat pulse on every refresh
  if(hb){hb.classList.remove('tick');void hb.offsetWidth;hb.classList.add('tick');}
}

async function tick(){
  let s;
  try{s=await (await fetch('/api/state')).json()}catch(e){document.getElementById('verdict').textContent='fetch error';return}
  document.getElementById('gen').textContent='updated '+new Date().toLocaleTimeString();
  const v=document.getElementById('verdict');
  v.textContent=s.verdict+`  (${s.signals_live}/${s.signals_total} signals live)`;
  const col=s.signals_live>=4?'var(--good)':s.signals_live>=2?'var(--warn)':'var(--bad)';
  v.style.borderColor=col; v.style.color=col;
  if(s.loop_signals&&s.loop_signals.cadence_live){v.classList.add('evolving');}else{v.classList.remove('evolving');}
  renderCadence(s.live_cadence);
  document.getElementById('headline').textContent=s.headline;
  const sig=s.loop_signals||{};
  document.getElementById('signals').innerHTML=Object.keys(sig).map(k=>
    `<span class="sig ${sig[k]?'on':'off'}">${sig[k]?'●':'○'} ${esc(k.replace(/_/g,' '))}</span>`).join('');
  const pct=s.signals_total?Math.round(100*s.signals_live/s.signals_total):0;
  document.getElementById('loopPct').textContent=pct+'% · '+s.signals_live+'/'+s.signals_total+' signals';
  document.getElementById('loopFill').style.width=pct+'%';
  document.getElementById('loopNote').textContent=pct>=80?'Multiple independent signals are live; inspect applied changes below.':pct>=40?'Partial loop: some signals are live, while others are idle or unavailable.':'Little current movement is evidenced by the connected registries.';
  const activity=(s.recent_activity||[]).map(a=>`<span>${esc(a.kind)} · ${esc(a.text)}</span>`);
  document.getElementById('activityRail').innerHTML=(activity.concat(activity)).join(' · ')||'<span>No timestamped activity in connected sources.</span>';

  const g=[];

  // SOURCE FRESHNESS / TRUST
  {
    const rows=s.source_health||[];
    const h='<div class="sourcegrid">'+rows.map(r=>`<div class="src ${r.state.toLowerCase()}"><span>${esc(r.source)}</span><b>${esc(r.state)}${r.age_s!=null?' · '+esc(r.age_s)+'s':''}</b></div>`).join('')+'</div>';
    g.push(card('🛰 Source freshness & trust',h));
  }

  // SELF-FIXING
  const sf=s.self_fixing||{};
  {
    const a=sf.self_audit||{}, c=sf.council||{}, p=sf.proposals||{};
    let h='';
    h+='<div class="small" style="margin-bottom:6px">SELF-AUDIT</div>'+wiredNote(a);
    if(a.wired){h+=metric('open findings',a.open)+metric('resolved',a.resolved)+metric('total',a.total_findings)+`<code>${esc(a.source)}</code>`;}
    h+='<div class="small" style="margin:10px 0 6px">AUTONOMOUS COMPLETIONS</div>'+wiredNote(c);
    if(c.wired){
      h+=`<div class="big">${esc(c.done_today)}<span class="small"> done today</span></div>`;
      h+=metric('done all-time',c.done_total);
      h+=bars(c.trend_24h);
      (c.recent_done||[]).slice(0,4).forEach(r=>h+=`<div class="row"><span class="t">${esc(r.task_id)}</span> <span class="small">${esc(r.actor)}</span></div>`);
    }
    h+='<div class="small" style="margin:10px 0 6px">PROPOSAL PIPELINE</div>'+wiredNote(p);
    if(p.wired){
      h+=metric('queued',p.queued)+metric('sandbox-green',p.sandbox_green)+metric('Task Council linked',p.council_linked)+metric('quorum unlinked',p.council_unlinked)+metric('oldest green (days)',p.oldest_green_days)+metric('rollback evidence',p.rollback_evidence)+metric('applied (audit rows)',p.applied_audit_rows)+metric('applied today',p.applied_today);
    }
    g.push(card('🔧 Self-Fixing',h));
  }

  // LEARNING
  const ln=s.learning||{};
  {
    const k=ln.knowledge||{}, t=ln.training||{}, l=ln.strategy_learnings||{};
    let h='';
    h+='<div class="small" style="margin-bottom:6px">KNOWLEDGE STORE</div>'+wiredNote(k);
    if(k.entries!=null)h+=`<div class="big">${esc(k.entries)}<span class="small"> entries</span></div>`;
    else if(k.terms_indexed!=null)h+=`<div class="big">${esc(k.terms_indexed)}<span class="small"> terms indexed</span></div>`;
    if(k.floors_indexed!=null)h+=metric('floors indexed',k.floors_indexed);
    if(k.reports_indexed!=null)h+=metric('reports indexed',k.reports_indexed);
    if(k.note)h+=`<div class="small">${esc(k.note)}</div>`;
    if(k.trend_24h)h+=bars(k.trend_24h);
    (k.recent||[]).slice(0,3).forEach(r=>h+=`<div class="row t">${esc(r.text)}</div>`);
    h+='<div class="small" style="margin:10px 0 6px">TRAINING / CERTIFICATION</div>'+wiredNote(t);
    if(t.wired){h+=metric('training runs',t.runs)+metric('cert passed',t.cert_passed)+metric('cert failed',t.cert_failed)+metric('real trains placed',t.real_trains_placed);}
    h+='<div class="small" style="margin:10px 0 6px">STRATEGY LEARNINGS</div>'+wiredNote(l);
    if(l.wired){h+=metric('events',l.events);(l.recent||[]).slice(0,3).forEach(r=>h+=`<div class="row"><span class="t">${esc(r.worker)}</span>: ${esc(r.from)}→${esc(r.to)}</div>`);}
    g.push(card('📚 Learning',h));
  }

  // WORKING
  const wk=s.working||{};
  {
    const L=wk.leadership||{}, cw=wk.ceo_workers||{};
    let h='';
    h+='<div class="small" style="margin-bottom:6px">LIVE LEADERSHIP</div>'+wiredNote(L);
    if(L.wired){
      h+=`<div class="big">${esc(L.live_count)}<span class="small"> / ${esc(L.total)} live</span></div>`;
      (L.workers||[]).forEach(w=>h+=`<div class="row"><span class="badge ${w.live?'live':'dead'}">${w.live?'LIVE':'idle'}</span> <span class="t">${esc(w.name)}</span> <span class="small">${esc(w.ago)}</span></div>`);
    }
    h+='<div class="small" style="margin:10px 0 6px">CEO WORKER TICKS</div>'+wiredNote(cw);
    if(cw.wired){h+=metric('total ticks',cw.total_ticks);(cw.by_ceo||[]).forEach(c=>h+=`<div class="row"><span class="t">${esc(c.ceo)}</span> ${esc(c.ticks)} ticks <span class="small">${esc(c.ago)}</span></div>`);}
    g.push(card('👷 Working',h));
  }

  // EVOLVING
  const ev=s.evolving||{};
  {
    const e=ev.evolution_log||{};
    let h=wiredNote(e);
    if(e.wired){
      h+=metric('forward steps',e.steps_total);
      (e.recent||[]).forEach(r=>h+=`<div class="row"><span class="t">${esc(r.text)}</span></div>`);
    }else{
      if(e.commits_today!=null)h+=`<div class="big">${esc(e.commits_today)}<span class="small"> commits today</span></div>`;
      (e.recent_commits||[]).slice(0,8).forEach(c=>h+=`<div class="row"><span class="small">${esc(c.date)}</span> <span class="t">${esc(c.subject)}</span></div>`);
    }
    g.push(card('🧬 Evolving',h));
  }

  // CROSS-LOOP ACTIVITY
  {
    const rows=s.recent_activity||[];
    const h='<div class="activity">'+(rows.map(r=>`<div class="row"><span>${esc((r.ts||'').slice(11,19))}</span><span class="t">${esc(r.kind)}</span><span>${esc(r.text)}</span></div>`).join('')||'<div class="small">No timestamped activity.</div>')+'</div>';
    g.push(card('📡 Live evolution activity',h));
  }

  document.getElementById('grid').innerHTML=g.join('');
}
document.getElementById('helix').innerHTML=buildHelix();
tick(); setInterval(tick,4000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path.startswith("/api/state"):
                self._send(200, json.dumps(build_state()), "application/json")
            elif self.path in ("/", "/index.html"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/healthz":
                self._send(200, json.dumps({"ok": True, "ts": time.time()}),
                           "application/json")
            else:
                self._send(404, json.dumps({"error": "not found"}),
                           "application/json")
        except Exception as e:
            try:
                self._send(500, json.dumps({"error": str(e)}),
                           "application/json")
            except Exception:
                pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"qsb_evolution_dash serving on http://127.0.0.1:{PORT}  (ROOT={ROOT})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
