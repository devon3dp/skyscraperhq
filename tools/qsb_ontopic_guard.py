#!/usr/bin/env python3
"""qsb_ontopic_guard.py — On-Topic Guard + Reputation-Aware Re-Router.

2026-07-30, Ross-authorized capability build.

REAL GAP (grounded, cited):
  data/registries/qsb_worker_reputation.json (the tower's own reward loop) proves
  some cockpit minds answer OFF-DOMAIN a lot:
      acer_cass  on_topic=0.97   rep=0.92
      tp_pip     on_topic=0.96   rep=0.83
      bill       on_topic=0.58   rep=0.47
      hermes     on_topic=0.06   rep=0.33
  Yet nothing GATES on this at answer time. When a low-on-topic CEO/cockpit
  answers a task, the off-domain text still lands in room.jsonl / the KB.
  Separately, tools/qsb_task_council_gene_pool_dispatcher.py picks who answers
  with a STATIC choose_ceo(task_type) map that still names retired "Claude HQ"
  and ignores the live reputation data entirely.

WHAT THIS TOOL DOES (two real, deterministic functions — no model call):

  1) GUARD(prompt, answer, source):
     - infers the intended topic of the *prompt* via the KB's own deterministic
       router qsb_knowledge._topic_of (reused, not reinvented),
     - infers the topic of the produced *answer* the same way,
     - flags OFF-TOPIC when answer.topic != prompt.topic (and prompt.topic is a
       real domain, i.e. not "general"),
     - ALSO flags LOW-TRUST when the source's live on_topic_rate (from the real
       reputation registry) is below a floor, even if this one answer matched.

  2) BEST_SOURCE_FOR(prompt):
     - replaces the stale static choose_ceo map with a LIVE pick: among sources
       that actually produce deliverables (excludes observers), choose the one
       with the highest (on_topic_rate, then reputation). This is "route to the
       best brain per task-type using the reputation data".

  3) ROUTE(prompt, answer, source):
     - runs GUARD; if it fails, returns a re-route decision to BEST_SOURCE_FOR,
       and writes an audit row to
       data/registries/qsb_ontopic_guard_audit.jsonl
       {ts, prompt_topic, source, answer_topic, verdict, reason, reroute_to}.

HONESTY (R01):
  - Topic inference is the tower's OWN deterministic keyword router. No opinion
    invented, no external model, no network.
  - Reputation numbers are read live from qsb_worker_reputation.compute() which
    is derived line-for-line from real council + KB registry rows.
  - If reputation can't be computed, the guard degrades to topic-only checks and
    says so in the reason — it never fabricates a score.

BOUNDARIES (this tool only READS these; it owns ONLY this file + its audit log):
  - qsb_knowledge.py (topic router), qsb_worker_reputation.py (scores).
  - It NEVER edits the map, Wren/Bill minds, SAFETY_DENY paths, gates, or any
    active agent's files. It flips no gates. It is advisory: it emits a verdict
    + a suggested re-route; the caller decides.

Usage:
  # one-shot guard on a prompt/answer pair from a given source
  python3 tools/qsb_ontopic_guard.py --prompt "..." --answer "..." --source hermes

  # ask who the best brain is for a task
  python3 tools/qsb_ontopic_guard.py --best-for "summarise today's trading pnl"

  # replay the last N real room rows through the guard (proof on real data)
  python3 tools/qsb_ontopic_guard.py --replay-room 20

  # self-proof (deterministic, uses live reputation): exits 0 on pass
  python3 tools/qsb_ontopic_guard.py --prove
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
TOOLS = ROOT / "tools"
AUDIT = REG / "qsb_ontopic_guard_audit.jsonl"

sys.path.insert(0, str(TOOLS))
import qsb_knowledge as KB  # deterministic topic router (reused, no new heuristics)

# reputation is optional at import time so the guard never hard-fails
try:
    import qsb_worker_reputation as REP
    _REP_OK = True
except Exception:  # pragma: no cover - degrade gracefully
    REP = None
    _REP_OK = False

# Sources that FLAG others' work rather than produce deliverables — never a
# re-route target. Mirrors the reputation module's own observer exclusion.
_OBSERVERS = {"codex", "council_watcher", "sandbox_gate", "tc_sandbox", "wren",
              "claude-verifier", "evolution_heartbeat"}

# a source whose live on-topic rate is below this is "low-trust" for on-topic work
_LOW_TRUST_ONTOPIC = 0.50


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def topic_of(text: str) -> str:
    """The tower's OWN deterministic topic router."""
    return KB._topic_of(text or "")


def _signals() -> dict:
    """Per-source live signals from the real reputation loop, or {} if unavailable."""
    if not _REP_OK:
        return {}
    try:
        ranked = REP.compute()["ranked"]
    except Exception:
        return {}
    out = {}
    for r in ranked:
        s = r.get("signals", {})
        out[r["source"]] = {
            "reputation": r.get("reputation", 0.5),
            "on_topic_rate": s.get("on_topic_rate", 0.0),
            "outcome_rate": s.get("outcome_rate", 0.5),
        }
    return out


def best_source_for(prompt: str, exclude: set | None = None) -> dict:
    """LIVE replacement for the static choose_ceo map: pick the deliverable
    source with the highest (on_topic_rate, reputation). Topic-neutral today
    because the reputation registry carries a single on_topic_rate per source;
    kept per-prompt so a future per-topic reputation slice drops straight in."""
    exclude = (exclude or set()) | _OBSERVERS
    sig = _signals()
    cands = [(src, v) for src, v in sig.items() if src not in exclude]
    if not cands:
        return {"source": None, "reason": "no reputation data / no eligible sources",
                "prompt_topic": topic_of(prompt)}
    cands.sort(key=lambda kv: (kv[1]["on_topic_rate"], kv[1]["reputation"]), reverse=True)
    best_src, best = cands[0]
    return {
        "source": best_src,
        "on_topic_rate": round(best["on_topic_rate"], 4),
        "reputation": round(best["reputation"], 4),
        "prompt_topic": topic_of(prompt),
        "reason": "highest live on_topic_rate then reputation among deliverable sources",
    }


def guard(prompt: str, answer: str, source: str) -> dict:
    """Deterministic on-topic verdict for one (prompt, answer, source)."""
    p_topic = topic_of(prompt)
    a_topic = topic_of(answer)
    sig = _signals()
    src_ontopic = sig.get(source, {}).get("on_topic_rate")

    reasons = []
    verdict = "pass"

    # 1) topic mismatch — only meaningful when the prompt has a real domain
    topic_mismatch = (p_topic != "general" and a_topic != p_topic)
    if topic_mismatch:
        verdict = "off_topic"
        reasons.append(f"answer topic '{a_topic}' != prompt topic '{p_topic}'")

    # 2) low-trust source on on-topic work (uses live reputation)
    low_trust = (src_ontopic is not None and src_ontopic < _LOW_TRUST_ONTOPIC)
    if low_trust:
        if verdict == "pass":
            verdict = "low_trust"
        reasons.append(
            f"source '{source}' live on_topic_rate={src_ontopic:.2f} < {_LOW_TRUST_ONTOPIC}")

    if verdict == "pass" and src_ontopic is None:
        reasons.append(f"no reputation data for source '{source}' (topic-only check)")

    return {
        "verdict": verdict,
        "prompt_topic": p_topic,
        "answer_topic": a_topic,
        "source": source,
        "source_on_topic_rate": (round(src_ontopic, 4) if src_ontopic is not None else None),
        "reasons": reasons,
        "reputation_available": _REP_OK,
    }


def route(prompt: str, answer: str, source: str, write_audit: bool = True) -> dict:
    """Guard + suggested re-route. Advisory only — flips no gate, moves no work."""
    g = guard(prompt, answer, source)
    decision = {**g, "reroute_to": None, "ts": utc()}
    if g["verdict"] != "pass":
        best = best_source_for(prompt, exclude={source})
        decision["reroute_to"] = best.get("source")
        decision["reroute_reason"] = best.get("reason")
        decision["reroute_on_topic_rate"] = best.get("on_topic_rate")
    if write_audit:
        try:
            with open(AUDIT, "a") as fh:
                fh.write(json.dumps({
                    "ts": decision["ts"],
                    "prompt_topic": decision["prompt_topic"],
                    "source": source,
                    "answer_topic": decision["answer_topic"],
                    "verdict": decision["verdict"],
                    "reason": "; ".join(decision["reasons"]),
                    "reroute_to": decision["reroute_to"],
                }) + "\n")
        except Exception as e:  # never break the caller on audit failure
            decision["audit_error"] = str(e)[:120]
    return decision


# --------------------------------------------------------------------------- #
# Proof harness — deterministic, runs against LIVE reputation data.
# --------------------------------------------------------------------------- #
def prove() -> dict:
    """Self-proof on real data. Returns a report; exits 0 on pass via _main."""
    checks = []

    # (a) An off-domain answer to a trading prompt is caught.
    r1 = route("summarise today's trading pnl and open positions",
               "The council rulebook governs sandbox sign-off across floors.",
               source="hermes", write_audit=False)
    checks.append(("off_topic_caught",
                   r1["verdict"] == "off_topic" and r1["reroute_to"] is not None,
                   r1))

    # (b) A low-trust source is flagged even when the single answer is on-topic.
    #     hermes live on_topic_rate ~0.06 -> low_trust.
    r2 = route("what is the trading strategy for the traders",
               "The trading strategy uses paper positions with risk caps.",
               source="hermes", write_audit=False)
    checks.append(("low_trust_flagged",
                   r2["verdict"] in ("low_trust", "off_topic"),
                   r2))

    # (c) A high-trust on-topic source PASSES.
    r3 = route("what is the trading strategy for the traders",
               "The trading strategy uses paper positions with risk caps.",
               source="acer_cass", write_audit=False)
    checks.append(("high_trust_pass", r3["verdict"] == "pass", r3))

    # (d) best_source_for returns the live top brain (acer_cass by on_topic).
    b = best_source_for("summarise the tower reliability status")
    checks.append(("best_source_is_live_top",
                   b["source"] == "acer_cass" and b["source"] not in _OBSERVERS,
                   b))

    # (e) re-route target is never an observer.
    checks.append(("reroute_not_observer",
                   (r1["reroute_to"] not in _OBSERVERS),
                   {"reroute_to": r1["reroute_to"]}))

    passed = all(ok for _, ok, _ in checks)
    return {
        "ok": passed,
        "reputation_available": _REP_OK,
        "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks],
    }


def replay_room(n: int) -> dict:
    """Replay the last N real room rows through the guard. Each room row is a
    CEO/cockpit utterance; we treat the SLA/status prompt as the intended topic
    ('tower' / status) and check whether the utterance stays on-domain. Real
    data, no fabrication."""
    room = REG / "leadership_comms" / "room.jsonl"
    rows = []
    if room.exists():
        with open(room) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    rows = rows[-n:]
    # The room's standing prompt is an operational status/briefing ask -> topic 'tower'.
    standing_prompt = "give a status briefing on the tower services traders disk and council"
    out = []
    for r in rows:
        src = r.get("from", "?")
        body = r.get("body", "")
        g = guard(standing_prompt, body, src)
        out.append({"from": src, "answer_topic": g["answer_topic"],
                    "verdict": g["verdict"], "body": body[:70]})
    return {"standing_prompt_topic": topic_of(standing_prompt),
            "n": len(out), "rows": out}


_WATCH_CURSOR = REG / "qsb_ontopic_guard_cursor.json"


def watch_once() -> dict:
    """Process only NEW room rows since the last run (byte-offset cursor) and
    audit any off-topic/low-trust ones. Idempotent; safe to run on a timer.
    Read-only against room.jsonl; owns only its cursor + audit log."""
    room = REG / "leadership_comms" / "room.jsonl"
    if not room.exists():
        return {"ok": True, "new": 0, "flagged": 0, "note": "no room.jsonl"}
    off = 0
    if _WATCH_CURSOR.exists():
        try:
            off = int(json.loads(_WATCH_CURSOR.read_text()).get("offset", 0))
        except Exception:
            off = 0
    size = room.stat().st_size
    if off > size:  # file rotated/truncated -> restart
        off = 0
    standing_prompt = "give a status briefing on the tower services traders disk and council"
    new = flagged = 0
    with open(room) as fh:
        fh.seek(off)
        for line in fh:
            line = line.strip()
            if not line:
                continue
            new += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            src = r.get("from", "?")
            body = r.get("body", "")
            d = route(standing_prompt, body, src, write_audit=True)
            if d["verdict"] != "pass":
                flagged += 1
    _WATCH_CURSOR.write_text(json.dumps({"offset": size, "ts": utc()}))
    return {"ok": True, "new": new, "flagged": flagged, "cursor": size}


def _main(argv) -> int:
    ap = argparse.ArgumentParser(description="On-Topic Guard + Reputation Re-Router")
    ap.add_argument("--prompt")
    ap.add_argument("--answer")
    ap.add_argument("--source", default="unknown")
    ap.add_argument("--best-for", metavar="PROMPT")
    ap.add_argument("--replay-room", type=int, metavar="N")
    ap.add_argument("--watch", action="store_true",
                    help="process new room rows since last cursor (timer mode)")
    ap.add_argument("--prove", action="store_true")
    ap.add_argument("--no-audit", action="store_true")
    a = ap.parse_args(argv)

    if a.watch:
        print(json.dumps(watch_once(), indent=2))
        return 0

    if a.prove:
        rep = prove()
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    if a.best_for:
        print(json.dumps(best_source_for(a.best_for), indent=2))
        return 0

    if a.replay_room is not None:
        print(json.dumps(replay_room(a.replay_room), indent=2))
        return 0

    if a.prompt and a.answer:
        print(json.dumps(route(a.prompt, a.answer, a.source,
                               write_audit=not a.no_audit), indent=2))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
