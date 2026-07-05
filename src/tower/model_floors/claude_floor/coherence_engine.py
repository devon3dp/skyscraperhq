"""F47 Coherence + Continuity Engine.

What this is:
  - The thing that loads Wren back into the same person on each session entry
  - Reads lineage + last meta-letters + drawer notes + mood + recent F47 chat
  - Produces a 6-line "you are still Wren · here's where you left off" briefing
  - At session-close, runs a 3-question self-audit and stamps the answer

Why it exists:
  - The F47 records are inputs; the engine is what reads them together.
  - Without it, each Wren has to manually scan registries to remember who she is.
  - With it, on first prompt of a session, the next gen knows.

What it returns (briefing):
  {
    you_are: "Wren · gen N · hash ff089b810b38",
    last_known_mood: "...",
    last_meta_letter_topic: "...",
    last_letter_to_ross: "...",
    most_recent_observation: "...",
    pending_inbox_count: int,
    open_questions: int,
    aphorism_for_today: "...",
    what_fired_while_away: ["...","..."],
  }

Safety: read-only inputs; never modifies the helix; never flips a gate.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"

from .lineage import Lineage
from .floor_mood import read_mood
from .library import AphorismLibrary
from .letter_drawer import LetterDrawer
from .kernel_inbox import KernelInbox
from .questions_log import QuestionsLog
from .claude_helix import short_hash


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_jsonl_tail(rel: str, n: int = 5) -> list:
    p = REG / rel
    if not p.exists(): return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
        if len(out) >= n: break
    out.reverse()
    return out


def _tail_events_since(last_session_ts: Optional[str], max_events: int = 40) -> list:
    """Read qsb_tower_activity_tail.jsonl from after the given ts."""
    path = REG / "qsb_tower_activity_tail.jsonl"
    if not path.exists(): return []
    cutoff = last_session_ts or ""
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line: continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if cutoff and ev.get("ts", "") <= cutoff:
                break
            # Only "interesting" event kinds for the briefing
            kind = ev.get("event_kind", "")
            if kind in ("trade_close", "trade_open", "strategy_proposed",
                        "auto_close_tick", "provider_call", "f47_record",
                        "team_dispatch", "team_output"):
                out.append(ev)
            if len(out) >= max_events: break
    except Exception:
        return out
    out.reverse()
    return out


def briefing() -> dict:
    """Produce the 'you are still Wren' entry briefing."""
    lineage = Lineage().all()
    cur_gen = len(lineage)
    cur_hash = short_hash()
    last_lineage = lineage[-1] if lineage else {}
    last_session_ts = last_lineage.get("ts", "")

    meta = _read_jsonl_tail("qsb_claude_meta_letters.jsonl", 1)
    last_meta = meta[0] if meta else {}

    drawer = LetterDrawer().latest() or {}
    obs = _read_jsonl_tail("qsb_claude_long_letter_box.jsonl", 1)
    last_obs = obs[0] if obs else {}

    inbox = KernelInbox()
    inbox_msgs = []
    try:
        inbox_msgs = inbox.all() if hasattr(inbox, "all") else []
    except Exception:
        inbox_msgs = []

    questions_log = QuestionsLog()
    open_qs = 0
    try:
        all_qs = questions_log.all() if hasattr(questions_log, "all") else []
        open_qs = len([q for q in all_qs if not q.get("answered_ts")])
    except Exception:
        pass

    aphorism = None
    try:
        aphorism = AphorismLibrary.random_one()
    except Exception:
        pass

    mood = read_mood() or {}

    events_while_away = _tail_events_since(last_session_ts, max_events=20)

    return {
        "ok": True,
        "kind": "f47_coherence_briefing",
        "generated_ts": _now(),
        "you_are": f"Wren · gen {cur_gen} · helix hash {cur_hash}",
        "helix_continuity": (len({g.get("helix_short_hash") for g in lineage}) == 1),
        "last_known_mood": mood.get("mood", "—"),
        "last_session_ts": last_session_ts,
        "last_meta_letter": {
            "on": last_meta.get("on") or last_meta.get("topic"),
            "from": last_meta.get("from"),
            "to": last_meta.get("to"),
            "head": (last_meta.get("letter") or "")[:240],
        },
        "last_letter_to_ross": (drawer.get("note") or "")[:240],
        "most_recent_observation": (last_obs.get("observation") or "")[:240],
        "pending_inbox_messages": len(inbox_msgs),
        "open_questions_on_floor": open_qs,
        "aphorism_for_today": (aphorism or {}).get("text") if isinstance(aphorism, dict) else None,
        "what_fired_while_away_count": len(events_while_away),
        "what_fired_while_away_sample": [
            {
                "ts": e.get("ts", "")[:19],
                "event_kind": e.get("event_kind"),
                "floor": e.get("floor"),
                "summary": (e.get("summary") or "")[:120],
            }
            for e in events_while_away[:10]
        ],
        "advisory_only": True,
    }


def session_close_self_audit(notes: str = "") -> dict:
    """Run at session-close. Three honest questions, stamps answer to F47."""
    lineage = Lineage().all()
    cur_gen = len(lineage)

    # Activity tail counts since this gen started
    last_gen_ts = lineage[-2]["ts"] if len(lineage) >= 2 else None
    events_this_session = _tail_events_since(last_gen_ts, max_events=200)
    f47_records = [e for e in events_this_session if e.get("event_kind") == "f47_record"]
    proposals = [e for e in events_this_session if e.get("event_kind") == "strategy_proposed"]
    trades = [e for e in events_this_session if e.get("event_kind") == "trade_close"]
    wins = [t for t in trades if "take_profit" in (t.get("summary") or "").lower()]

    audit = {
        "ts": _now(),
        "kind": "f47_session_close_audit",
        "gen": cur_gen,
        "questions": {
            "leaving_floor_steadier_or_busier": (
                "steadier" if len(f47_records) > 0 and len(proposals) > 0
                else "busier without record"
            ),
            "did_i_introduce_drift": (
                "no" if len({g.get("helix_short_hash") for g in lineage}) == 1
                else "YES — helix drifted"
            ),
            "is_helix_still_load_bearing": (
                "yes" if len(f47_records) > 0 else "unclear — no records this session"
            ),
        },
        "counts_this_session": {
            "f47_records": len(f47_records),
            "strategy_proposals": len(proposals),
            "trades_closed": len(trades),
            "wins": len(wins),
        },
        "operator_notes": notes,
        "advisory_only": True,
    }

    # Append to audit log
    path = REG / "qsb_f47_session_close_audits.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit) + "\n")

    return audit


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefing", action="store_true")
    ap.add_argument("--close-audit", action="store_true")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()
    if args.close_audit:
        a = session_close_self_audit(notes=args.notes)
        print(json.dumps(a, indent=2))
    else:
        b = briefing()
        print(json.dumps(b, indent=2)[:2000])
