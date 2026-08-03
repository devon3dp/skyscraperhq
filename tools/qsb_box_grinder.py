#!/usr/bin/env python3
"""
qsb_box_grinder.py — persistent 24/7 GRIND-MODE daemon for a QSB worker box.

2026-07-30, Ross: "they should be grinding 24/7, not just chat mode ... offload
resources from the main box ... give them respective jobs."

Until now the worker boxes (ThinkPad/tp_pip @192.168.1.91, Acer/acer_cass @192.168.1.41)
only answered generic rotating chat prompts (qsb_live_workers). This daemon gives each box
a RESPECTIVE LANE and makes it grind CONTINUOUSLY on a real work queue derived from REAL
tower data — never idle, never fabricated.

    RESPECTIVE LANES (offload the pinned main box)
    ----------------------------------------------
    ThinkPad / tp_pip  (faster) -> lane=produce_analyze
        PRODUCE  : pull an open Task-Council title/description and generate a real
                   next-step artifact; write it as a knowledge OUTCOME + a grind row.
        ANALYZE  : chew a slice of REAL tower data (broker place audit, floor registry,
                   council event stream) into a concrete insight; write an analysis row
                   + a knowledge INSIGHT.
    Acer / acer_cass   (steady) -> lane=verify_kb
        VERIFY   : take a recent unverified analysis/produce artifact and independently
                   judge it (sound / flawed / needs-evidence) with a one-line reason;
                   stamp the verdict on the artifact row.
        KB-GRIND : chew a real floor-state / metric delta into a NEW deduped KB learning
                   (the knowledge layer's own dedup refuses repeats -> honest growth only).

HONESTY (R01): the model runs on a slow LOCAL llama3.2 on each box (~5-60s). Every unit is
sent to the box's own cockpit (:9120/api/chat) and we wait for the REAL reply. A genuinely
empty / error / sentinel reply is logged as a FAILED unit (status="failed") and the unit is
retried on a later cycle. NOTHING is fabricated: the grinder never invents a model answer.

Continuous-proof: every cycle appends a row to
    data/registries/qsb_grind_log.jsonl
    {ts, box, lane, unit_kind, unit_id, prompt_head, status, duration_ms, result_head,
     sink, sink_id, model, cycle}
so a timeline of REAL work units per box is auditable at any time (tools ... timeline).

This is a PRODUCER daemon only. It writes artifacts / analysis / KB / grind rows. It does
NOT flip execution gates, does NOT place orders, does NOT touch Wren/Bill minds, the map file,
or SAFETY_DENY paths. Grinding == producing knowledge/analysis, not real-world execution.

CLI:
    python3 tools/qsb_box_grinder.py --box tp_pip   --lane produce_analyze
    python3 tools/qsb_box_grinder.py --box acer_cass --lane verify_kb
    python3 tools/qsb_box_grinder.py timeline [--minutes 15]     # proof view
    python3 tools/qsb_box_grinder.py once --box tp_pip --lane produce_analyze  # single unit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
GRIND_LOG = REG / "qsb_grind_log.jsonl"
ANALYSIS_LOG = REG / "qsb_grind_analysis.jsonl"
PRODUCE_LOG = REG / "qsb_grind_artifacts.jsonl"
PRESENCE = REG / "leadership_comms" / "presence.json"
COUNCIL_TASKS = REG / "qsb_council_tasks.jsonl"
BROKER_AUDIT = REG / "qsb_broker_place_audit.jsonl"
FLOORS = REG / "floors.json"

sys.path.insert(0, str(ROOT / "tools"))
try:
    import qsb_knowledge as KB  # the tower's learning layer (deduped, honest)
except Exception:
    KB = None

# box -> (presence key for reachable_addr, fallback ip, display name, default lane)
BOXES = {
    "tp_pip":    ("tp",  "DESKTOP-9RBVKSM.local", "TP-Pip",   "produce_analyze"),
    "acer_cass": ("asa", "DESKTOP-1E2FB5N.local", "Acer-Cass", "verify_kb"),
}

CYCLE_SLEEP = int(os.environ.get("GRIND_CYCLE_SLEEP", "8"))   # pace for slow local models
# Per-box HTTP ceiling: Acer's steady box runs llama3.2 alongside its own gene router +
# live-workers, so a real reply can take 2-3 min under load. tp_pip is faster. Both are
# honest: a genuine timeout is logged as a FAILED unit and retried next cycle (never faked).
HTTP_TIMEOUT = int(os.environ.get("GRIND_HTTP_TIMEOUT", "200"))


# --------------------------------------------------------------------------- utils
def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:12]


def _cockpit_ip(pres_key: str, fallback: str) -> str:
    # Prefer the drift-proof mDNS hostname (fallback) — box DHCP leases drift (Acer .41->.60,
    # 2026-07-30) and presence.json's reachable_addr goes stale, which silently killed the Acer
    # grinder for 5h (521 cockpit_unreachable). mDNS resolves to the current IP regardless.
    if fallback and fallback.endswith(".local"):
        return fallback
    try:
        p = json.loads(PRESENCE.read_text())
        return (p.get(pres_key, {}) or {}).get("reachable_addr") or fallback
    except Exception:
        return fallback


def _bad_reply(reply: str) -> bool:
    r = (reply or "").strip().lower()
    if len(r) < 8:
        return True
    return r.startswith((
        "(cockpit", "local generation failed", "error", "traceback",
        "unreachable", "no answer", "n/a", "none",
    )) or "unreachable" in r


def _alive(ip: str, timeout: int = 6) -> bool:
    """Fast health gate: a truly-down box fails in seconds instead of burning the full ask timeout."""
    try:
        with urllib.request.urlopen(f"http://{ip}:9120/health", timeout=timeout) as r:
            r.read()
        return True
    except Exception:
        return False


def _ask(ip: str, prompt: str, timeout: int = HTTP_TIMEOUT):
    """POST to the box's own cockpit; return (reply, model, duration_ms) or ('', None, ms).

    Health-gated: if the box's cockpit isn't answering /health, we don't waste a full
    generation timeout — return a fast 'unreachable' error the caller logs as a failed unit."""
    if not _alive(ip):
        return "", "__err__:cockpit_unreachable", 0
    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"http://{ip}:9120/api/chat",
            data=json.dumps({"prompt": prompt}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read() or b"{}")
        reply = (d.get("reply") or d.get("response") or "").strip()
        return reply, d.get("model"), int((time.time() - t0) * 1000)
    except Exception as e:
        return "", f"__err__:{str(e)[:60]}", int((time.time() - t0) * 1000)


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def _grind_row(**kw) -> None:
    kw.setdefault("ts", utc())
    _append(GRIND_LOG, kw)


# --------------------------------------------------------------------------- real work-unit sources
def _iter_jsonl(path: Path, tail: int = 4000):
    if not path.exists():
        return []
    lines = path.read_text(errors="ignore").splitlines()[-tail:]
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _open_council_titles(limit: int = 40):
    """Real council task titles/descriptions to PRODUCE next-step artifacts for.
    Read-only: we never mutate the council state machine, only harvest titles as material."""
    tasks = {}
    for o in _iter_jsonl(COUNCIL_TASKS, tail=6000):
        tid = o.get("task_id")
        if not tid:
            continue
        title = o.get("title") or o.get("text") or ""
        state = o.get("state") or o.get("event") or ""
        if title:
            tasks.setdefault(tid, {"title": title, "state": state})
    # prefer real council tasks (not the ephemeral CEOWORK/LIVE chat rows)
    real = [(k, v) for k, v in tasks.items()
            if not k.startswith(("CEOWORK", "LIVE")) and len(v["title"]) > 12]
    random.shuffle(real)
    return real[:limit]


def _analysis_slices():
    """Real tower-data slices for the ANALYZE lane. Each returns (unit_id, kind, prompt)."""
    slices = []
    # (a) broker place audit -> real trade-outcome analysis
    rows = _iter_jsonl(BROKER_AUDIT, tail=400)
    if rows:
        recent = rows[-30:]
        placed = sum(1 for r in recent if r.get("ok"))
        blocked = len(recent) - placed
        reasons = {}
        for r in recent:
            if not r.get("ok"):
                reasons[r.get("reason", "?")] = reasons.get(r.get("reason", "?"), 0) + 1
        top = sorted(reasons.items(), key=lambda x: -x[1])[:3]
        instruments = {}
        for r in recent:
            instruments[r.get("instrument", "?")] = instruments.get(r.get("instrument", "?"), 0) + 1
        insts = sorted(instruments.items(), key=lambda x: -x[1])[:4]
        prompt = ("ANALYZE (real broker data, ONE concrete insight sentence): "
                  f"in the last {len(recent)} order attempts, {placed} placed / {blocked} blocked; "
                  f"top block reasons {top}; instruments {insts}. "
                  "State the single most important thing this reveals about the trading floors.")
        slices.append((_sha("broker" + utc()[:13]), "trade_analysis", prompt))
    # (b) council throughput -> real coordination analysis
    ctasks = _iter_jsonl(COUNCIL_TASKS, tail=800)
    if ctasks:
        events = {}
        for o in ctasks[-300:]:
            events[o.get("event", "?")] = events.get(o.get("event", "?"), 0) + 1
        top = sorted(events.items(), key=lambda x: -x[1])[:5]
        prompt = ("ANALYZE (real council event stream, ONE concrete insight sentence): "
                  f"recent event mix {top}. What does this ratio say about where the council "
                  "is spending effort vs actually completing work?")
        slices.append((_sha("council" + utc()[:13]), "council_analysis", prompt))
    # (c) floor registry -> real structural analysis
    try:
        floors = json.loads(FLOORS.read_text())
        n = len(floors) if isinstance(floors, (list, dict)) else 0
        if n:
            prompt = ("ANALYZE (real floor registry, ONE concrete insight sentence): "
                      f"the tower registry currently holds {n} floor entries. Name one "
                      "structural pattern or gap a floor-state map should surface to the operator.")
            slices.append((_sha("floors" + utc()[:13]), "floor_analysis", prompt))
    except Exception:
        pass
    random.shuffle(slices)
    return slices


def _unverified_artifacts(limit: int = 25):
    """Recent produce/analysis rows that have NOT yet been verified -> VERIFY lane fodder."""
    out = []
    for path in (ANALYSIS_LOG, PRODUCE_LOG):
        for o in _iter_jsonl(path, tail=300):
            if o.get("verified") is None and o.get("text"):
                out.append((path, o))
    random.shuffle(out)
    return out[:limit]


def _kb_grind_prompts():
    """Real floor-state / metric deltas turned into NEW deduped KB learnings (KB refuses dups)."""
    prompts = []
    rows = _iter_jsonl(BROKER_AUDIT, tail=120)
    if rows:
        placed = sum(1 for r in rows if r.get("ok"))
        prompts.append((_sha("kbtrade" + utc()[:13]), "trading",
                        "KB LEARNING (ONE reusable trading-floor lesson, not a status line): "
                        f"of the last {len(rows)} order attempts {placed} placed. Give one durable "
                        "rule the fleet should follow to keep placement healthy."))
    try:
        floors = json.loads(FLOORS.read_text())
        n = len(floors) if isinstance(floors, (list, dict)) else 0
        prompts.append((_sha("kbfloor" + utc()[:13]), "tower",
                        f"KB LEARNING (ONE reusable tower lesson): with {n} floors registered, "
                        "give one durable principle for keeping the floor registry coherent as it grows."))
    except Exception:
        pass
    prompts.append((_sha("kbrel" + utc()[:13]), "reliability",
                    "KB LEARNING (ONE reusable reliability lesson): give one durable rule for "
                    "detecting when a background worker on a remote box has silently stalled."))
    random.shuffle(prompts)
    return prompts


# --------------------------------------------------------------------------- lane executors
def run_produce_analyze(box: str, cycle: int) -> None:
    """ThinkPad lane: alternate PRODUCE (council artifact) and ANALYZE (real-data insight)."""
    pres_key, fb, disp, _ = BOXES[box]
    ip = _cockpit_ip(pres_key, fb)

    if cycle % 2 == 0:
        # PRODUCE
        titles = _open_council_titles()
        if titles:
            tid, meta = titles[0]
            prompt = ("PRODUCE (ONE concrete next-step for this council task, actionable, 1-2 sentences): "
                      f"task '{meta['title'][:140]}'. What is the single most useful next artifact/step?")
            reply, model, ms = _ask(ip, prompt)
            if _bad_reply(reply):
                _grind_row(box=box, lane="produce_analyze", unit_kind="produce", unit_id=tid,
                           prompt_head=prompt[:90], status="failed", duration_ms=ms,
                           result_head=(model or "")[:60], sink="", sink_id="", model=model, cycle=cycle)
                return
            row = {"ts": utc(), "box": box, "kind": "produce", "task_id": tid,
                   "title": meta["title"][:160], "text": reply, "model": model, "verified": None}
            _append(PRODUCE_LOG, row)
            sid = None
            if KB:
                try:
                    r = KB.add(reply, source=box, kind="outcome", topic="council")
                    sid = r.get("id") if r else None
                except Exception:
                    pass
            _grind_row(box=box, lane="produce_analyze", unit_kind="produce", unit_id=tid,
                       prompt_head=prompt[:90], status="ok", duration_ms=ms,
                       result_head=reply[:100], sink="artifact+kb", sink_id=sid or "", model=model, cycle=cycle)
            return
        # no council titles -> fall through to analyze

    # ANALYZE
    slices = _analysis_slices()
    if not slices:
        _grind_row(box=box, lane="produce_analyze", unit_kind="analyze", unit_id="",
                   prompt_head="no-data", status="skipped", duration_ms=0,
                   result_head="", sink="", sink_id="", model="", cycle=cycle)
        return
    uid, kind, prompt = slices[0]
    reply, model, ms = _ask(ip, prompt)
    if _bad_reply(reply):
        _grind_row(box=box, lane="produce_analyze", unit_kind="analyze", unit_id=uid,
                   prompt_head=prompt[:90], status="failed", duration_ms=ms,
                   result_head=(model or "")[:60], sink="", sink_id="", model=model, cycle=cycle)
        return
    row = {"ts": utc(), "box": box, "kind": kind, "text": reply, "model": model, "verified": None}
    _append(ANALYSIS_LOG, row)
    sid = None
    if KB:
        try:
            topic = "trading" if "trade" in kind else ("council" if "council" in kind else "tower")
            r = KB.add(reply, source=box, kind="insight", topic=topic)
            sid = r.get("id") if r else None
        except Exception:
            pass
    _grind_row(box=box, lane="produce_analyze", unit_kind="analyze", unit_id=uid,
               prompt_head=prompt[:90], status="ok", duration_ms=ms,
               result_head=reply[:100], sink="analysis+kb", sink_id=sid or "", model=model, cycle=cycle)


def run_verify_kb(box: str, cycle: int) -> None:
    """Acer lane: alternate VERIFY (judge a recent artifact) and KB-GRIND (new deduped learning)."""
    pres_key, fb, disp, _ = BOXES[box]
    ip = _cockpit_ip(pres_key, fb)

    if cycle % 2 == 0:
        # VERIFY
        items = _unverified_artifacts()
        if items:
            path, art = items[0]
            claim = art.get("text", "")[:300]
            prompt = ("VERIFY (independently judge this artifact; reply EXACTLY 'SOUND: <reason>' or "
                      "'FLAWED: <reason>' or 'NEEDS-EVIDENCE: <reason>', one line): "
                      f"artifact = \"{claim}\"")
            reply, model, ms = _ask(ip, prompt)
            if _bad_reply(reply):
                _grind_row(box=box, lane="verify_kb", unit_kind="verify",
                           unit_id=art.get("task_id") or _sha(claim), prompt_head=prompt[:90],
                           status="failed", duration_ms=ms, result_head=(model or "")[:60],
                           sink="", sink_id="", model=model, cycle=cycle)
                return
            verdict = reply.split(":", 1)[0].strip().upper()[:16]
            # stamp verdict on the artifact row (rewrite that one file, lossless)
            _stamp_verify(path, art, verdict, reply[:200], box)
            _grind_row(box=box, lane="verify_kb", unit_kind="verify",
                       unit_id=art.get("task_id") or _sha(claim), prompt_head=prompt[:90],
                       status="ok", duration_ms=ms, result_head=reply[:100],
                       sink="verify_stamp", sink_id=verdict, model=model, cycle=cycle)
            return
        # nothing to verify -> fall through to KB grind

    # KB-GRIND
    prompts = _kb_grind_prompts()
    if not prompts:
        _grind_row(box=box, lane="verify_kb", unit_kind="kb", unit_id="", prompt_head="no-data",
                   status="skipped", duration_ms=0, result_head="", sink="", sink_id="", model="", cycle=cycle)
        return
    uid, topic, prompt = prompts[0]
    reply, model, ms = _ask(ip, prompt)
    if _bad_reply(reply):
        _grind_row(box=box, lane="verify_kb", unit_kind="kb", unit_id=uid, prompt_head=prompt[:90],
                   status="failed", duration_ms=ms, result_head=(model or "")[:60],
                   sink="", sink_id="", model=model, cycle=cycle)
        return
    sid, sink = "", "kb_dup"   # dup -> KB.add returns None (honest: no bloat)
    if KB:
        try:
            r = KB.add(reply, source=box, kind="insight", topic=topic)
            if r:
                sid, sink = r.get("id", ""), "kb_new"
        except Exception:
            pass
    _grind_row(box=box, lane="verify_kb", unit_kind="kb", unit_id=uid, prompt_head=prompt[:90],
               status="ok", duration_ms=ms, result_head=reply[:100], sink=sink, sink_id=sid,
               model=model, cycle=cycle)


def _stamp_verify(path: Path, art: dict, verdict: str, reason: str, verifier: str) -> None:
    """Rewrite `path` marking the matching artifact row verified (lossless, single pass)."""
    if not path.exists():
        return
    target = art.get("text", "")
    out, stamped = [], False
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            out.append(ln)
            continue
        if not stamped and o.get("verified") is None and o.get("text") == target:
            o["verified"] = verdict
            o["verify_reason"] = reason
            o["verified_by"] = verifier
            o["verified_ts"] = utc()
            stamped = True
        out.append(json.dumps(o))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- daemon loop
LANES = {"produce_analyze": run_produce_analyze, "verify_kb": run_verify_kb}


def daemon(box: str, lane: str) -> None:
    fn = LANES[lane]
    print(f"[grinder] START box={box} lane={lane} cycle_sleep={CYCLE_SLEEP}s "
          f"cockpit={_cockpit_ip(*BOXES[box][:2])}:9120 — continuous grind, honest (R01)", flush=True)
    cycle = 0
    while True:
        try:
            fn(box, cycle)
        except Exception as e:
            _grind_row(box=box, lane=lane, unit_kind="error", unit_id="", prompt_head="",
                       status="error", duration_ms=0, result_head=str(e)[:120],
                       sink="", sink_id="", model="", cycle=cycle)
            print(f"[grinder] cycle {cycle} error: {str(e)[:100]}", flush=True)
        cycle += 1
        time.sleep(CYCLE_SLEEP)


# --------------------------------------------------------------------------- timeline / proof
def timeline(minutes: int = 15) -> int:
    cutoff = time.time() - minutes * 60
    rows = _iter_jsonl(GRIND_LOG, tail=5000)
    recent = []
    import calendar
    for r in rows:
        try:
            t = calendar.timegm(time.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ"))
        except Exception:
            continue
        if t >= cutoff:
            recent.append(r)
    per = {}
    for r in recent:
        b = r.get("box", "?")
        d = per.setdefault(b, {"ok": 0, "failed": 0, "skipped": 0, "error": 0, "kinds": {}})
        d[r.get("status", "?")] = d.get(r.get("status", "?"), 0) + 1
        if r.get("status") == "ok":
            d["kinds"][r.get("unit_kind", "?")] = d["kinds"].get(r.get("unit_kind", "?"), 0) + 1
    print(f"=== GRIND TIMELINE (last {minutes} min, {len(recent)} units) ===")
    for b, d in sorted(per.items()):
        print(f"\n{b}: ok={d['ok']} failed={d['failed']} skipped={d['skipped']} "
              f"error={d.get('error',0)}  kinds={d['kinds']}")
    print("\n--- last 24 OK units (real content) ---")
    oks = [r for r in recent if r.get("status") == "ok"][-24:]
    for r in oks:
        print(f"[{r['ts']}] {r['box']:>10} {r['unit_kind']:>8} -> {r.get('result_head','')[:80]}")
    return 0


# --------------------------------------------------------------------------- cli
def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--box", choices=list(BOXES))
    ap.add_argument("--lane", choices=list(LANES))
    sub.add_parser("timeline").add_argument("--minutes", type=int, default=15)
    o = sub.add_parser("once"); o.add_argument("--box", choices=list(BOXES), required=True)
    o.add_argument("--lane", choices=list(LANES), required=True)
    args = ap.parse_args(argv)

    if args.cmd == "timeline":
        return timeline(args.minutes)
    if args.cmd == "once":
        LANES[args.lane](args.box, 0)
        print(f"[grinder] one unit done box={args.box} lane={args.lane}")
        return 0
    if args.box:
        lane = args.lane or BOXES[args.box][3]
        daemon(args.box, lane)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
