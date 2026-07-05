"""TradingAuthority — Authorization checks for worker trade proposals.

Used by the Reasoning layer AND by any orchestration code that wants to
test whether a worker may place a practice order.

Decision = ALLOW iff:
  · worker is certified for the instrument (worker_certification)
  · status != suspended
  · last_recert within window
  · NOT currently on a fresh-loss streak >= 3 (cool-down nudge; not
    an outright block but flagged)

Every check produces a structured audit row.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import time

from . import write_registry, append_log, now
from .worker_certification import worker_certification


@dataclass
class AuthorityCheck:
    worker_id: str
    instrument: str
    decision: str          # ALLOW | BLOCK | WARN_BUT_ALLOW
    reason: str
    checked_ts: float


def check_authority(worker_id: str, instrument: str) -> AuthorityCheck:
    wc = worker_certification()
    e = wc.get_or_create(worker_id, instrument)
    ts = time.time()
    if e.status == "suspended":
        ac = AuthorityCheck(worker_id, instrument, "BLOCK",
                             "worker is suspended; must recertify", ts)
    elif e.status != "certified":
        ac = AuthorityCheck(worker_id, instrument, "BLOCK",
                             f"worker not certified (status={e.status})", ts)
    elif e.last_recert_ts is None or (ts - e.last_recert_ts) > 365 * 86400:
        ac = AuthorityCheck(worker_id, instrument, "BLOCK",
                             "certification expired; recert required", ts)
    elif e.consecutive_losses >= 3:
        ac = AuthorityCheck(worker_id, instrument, "WARN_BUT_ALLOW",
                             f"warn: {e.consecutive_losses} consecutive losses; "
                             "consider cool-down", ts)
    else:
        ac = AuthorityCheck(worker_id, instrument, "ALLOW",
                             "certified, active, no recent loss streak", ts)
    append_log("trading_authority.jsonl", {
        "event": "check",
        "worker_id": worker_id, "instrument": instrument,
        "decision": ac.decision, "reason": ac.reason,
    })
    return ac


def gate_snapshot() -> Dict[str, Any]:
    wc = worker_certification()
    return {
        "ok": True,
        "kind": "cognitive_trading_authority_gate",
        "generated_ts": now(),
        "policy": ("Reasoning rule: trade proposal blocked unless ALLOW. "
                    "WARN_BUT_ALLOW is permitted but logged loudly."),
        "certified_workers_count": len(wc.certified_workers()),
        "suspended_workers_count": len(wc.suspended_workers()),
        "studying_workers_count": len(wc.studying_workers()),
    }


def persist_gate() -> None:
    write_registry("cognitive_trading_authority_gate.json", gate_snapshot())


# ── Reasoning-layer integration ──────────────────────────────────────

def install_authority_rule() -> None:
    """Adds a rule to the Reasoning layer that surfaces blocked trades.

    The Reasoning rule itself is observation-level: it inspects the
    working memory blackboard for any 'pending_trade_proposal' slot and
    derives a 'trade_blocked' belief if the corresponding worker is not
    authorized.
    """
    from .reasoning import reasoning, Rule
    from .working_memory import WorkingMemory

    def _pending_trade_exists(bb: WorkingMemory) -> bool:
        slot = bb.read("pending_trade_proposal")
        return slot is not None and isinstance(slot.value, dict)

    def _evaluate_pending(bb: WorkingMemory) -> dict:
        slot = bb.read("pending_trade_proposal")
        v = slot.value
        wid = str(v.get("worker_id") or "?")
        inst = str(v.get("instrument") or "?")
        ac = check_authority(wid, inst)
        return {
            "key": "trade_authority_decision",
            "statement": (f"Trade proposal for worker {wid} on {inst}: "
                          f"{ac.decision} — {ac.reason}"),
            "confidence": 0.95,
            "tags": ["trading_authority", ac.decision.lower()],
        }

    reasoning().add_rule(Rule(
        name="trading_authority_gate",
        predicate=_pending_trade_exists,
        conclude=_evaluate_pending,
        rationale=("Block trade proposal unless worker certified, active, "
                    "and not in a fresh loss streak."),
    ))
