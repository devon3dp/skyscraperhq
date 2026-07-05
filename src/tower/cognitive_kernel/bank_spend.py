"""BankSpend — Operator-approved QBC spending.

Workers can spend QBC on:
  · classroom unlock (e.g., advanced instrument curriculum)   — 100 QBC
  · advanced instrument unlock                                 — 250 QBC
  · cosmetic title                                              —  50 QBC
  · child dowry top-up (transfer to a child the worker mentors) — variable

All burns + transfers go through bank.burn() / bank.transfer() so the
audit log captures every QBC move.

Spending requires operator approval per request — the Kernel files a
pending spend; the operator approves via qsb_spend.py CLI.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time
import uuid

from . import write_registry, append_log, now, load, COG_REG
from .bank import bank


SPEND_KINDS = {
    "burn_classroom_unlock":     100.0,
    "burn_instrument_unlock":    250.0,
    "burn_cosmetic_title":        50.0,
    # transfer_dowry_to_child is variable; operator types amount
}


@dataclass
class SpendRequest:
    spend_id: str
    kind: str
    worker_id: str          # the worker spending (from_worker)
    qbc_amount: float
    target_worker_id: Optional[str] = None     # for transfers
    note: str = ""
    status: str = "open"        # open | approved | executed | declined
    proposed_ts: float = 0.0
    operator_decision_at: Optional[float] = None


class BankSpend:

    def __init__(self):
        self._requests: Dict[str, SpendRequest] = {}

    def request(self, kind: str, worker_id: str,
                  qbc_amount: Optional[float] = None,
                  target_worker_id: Optional[str] = None,
                  note: str = "") -> Optional[SpendRequest]:
        # Validate kind
        if kind.startswith("burn_"):
            default_amount = SPEND_KINDS.get(kind)
            if default_amount is None:
                return None
            amount = qbc_amount if qbc_amount is not None else default_amount
            if target_worker_id is not None:
                return None  # burns don't target
        elif kind == "transfer_dowry_to_child":
            if not target_worker_id or qbc_amount is None or qbc_amount <= 0:
                return None
            amount = qbc_amount
        elif kind == "transfer_friend_gift":
            if not target_worker_id or qbc_amount is None or qbc_amount <= 0:
                return None
            amount = qbc_amount
        else:
            return None
        # Validate balance
        if bank().balance(worker_id) < amount:
            append_log("bank_spend.jsonl", {
                "event": "request_refused_insufficient",
                "worker": worker_id, "kind": kind,
                "amount": amount,
                "balance": bank().balance(worker_id),
            })
            return None
        spend_id = f"spend_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        s = SpendRequest(
            spend_id=spend_id, kind=kind,
            worker_id=worker_id, qbc_amount=amount,
            target_worker_id=target_worker_id, note=note,
            proposed_ts=time.time(),
        )
        self._requests[spend_id] = s
        append_log("bank_spend.jsonl", {
            "event": "request",
            "spend_id": spend_id, "kind": kind,
            "worker": worker_id, "amount": amount,
        })
        return s

    def approve(self, spend_id: str, note: str = "") -> bool:
        s = self._requests.get(spend_id)
        if not s or s.status != "open":
            return False
        s.status = "approved"
        s.operator_decision_at = time.time()
        if note: s.note += f" | approve: {note}"
        append_log("bank_spend.jsonl",
                   {"event": "approved", "spend_id": spend_id})
        return True

    def decline(self, spend_id: str, note: str = "") -> bool:
        s = self._requests.get(spend_id)
        if not s or s.status not in ("open", "approved"):
            return False
        s.status = "declined"
        s.operator_decision_at = time.time()
        if note: s.note += f" | decline: {note}"
        append_log("bank_spend.jsonl",
                   {"event": "declined", "spend_id": spend_id})
        return True

    def execute(self, spend_id: str) -> bool:
        s = self._requests.get(spend_id)
        if not s or s.status != "approved":
            return False
        if s.kind.startswith("burn_"):
            t = bank().burn(s.worker_id, s.qbc_amount, s.kind,
                              note=f"spend {spend_id}: {s.note}")
        else:
            t = bank().transfer(s.worker_id, s.target_worker_id,
                                  s.qbc_amount, s.kind,
                                  note=f"spend {spend_id}: {s.note}")
        if t is None:
            return False
        s.status = "executed"
        append_log("bank_spend.jsonl",
                   {"event": "executed", "spend_id": spend_id,
                    "txn_id": t.txn_id})
        return True

    def all_requests(self) -> List[SpendRequest]:
        return list(self._requests.values())

    def open_requests(self) -> List[SpendRequest]:
        return [s for s in self._requests.values() if s.status == "open"]

    def get(self, spend_id: str) -> Optional[SpendRequest]:
        return self._requests.get(spend_id)

    def snapshot(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for s in self._requests.values():
            by_status[s.status] = by_status.get(s.status, 0) + 1
        return {
            "ok": True,
            "kind": "cognitive_bank_spend_state",
            "generated_ts": now(),
            "policy": ("Operator-approved spending. Burns + transfers go "
                        "through Bank with full audit log."),
            "spend_kinds": SPEND_KINDS,
            "request_count": len(self._requests),
            "by_status": by_status,
            "requests": [asdict(s) for s in self._requests.values()],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_bank_spend_state.json", snap)
        return snap

    def load_from_snapshot(self) -> int:
        d = load(COG_REG / "cognitive_bank_spend_state.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("requests") or []:
            sid = r.get("spend_id")
            if sid and sid not in self._requests:
                self._requests[sid] = SpendRequest(
                    spend_id=sid, kind=r.get("kind", ""),
                    worker_id=r.get("worker_id", ""),
                    qbc_amount=float(r.get("qbc_amount") or 0),
                    target_worker_id=r.get("target_worker_id"),
                    note=r.get("note", ""),
                    status=r.get("status", "open"),
                    proposed_ts=float(r.get("proposed_ts") or 0),
                    operator_decision_at=(float(r["operator_decision_at"])
                                            if r.get("operator_decision_at") else None),
                )
                count += 1
        return count


_BS: Optional[BankSpend] = None


def bank_spend() -> BankSpend:
    global _BS
    if _BS is None:
        _BS = BankSpend()
    return _BS
