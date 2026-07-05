"""Compensation — Pay workers in QBC for advisory milestones.

SOLE minting API. The Bank's mint() is internal-only; everyone else calls
compensation_engine.pay_*().

Pay rules (defaults — operator may adjust):
  · per-$1 practice PnL  →  +1 QBC, capped at 200 QBC per worker per
                            settlement round (avoid one whale draining mint)
  · classroom test pass  →  +50 QBC
  · friend pairing 30+ days  →  +25 QBC (one-time anniversary, per pair)
  · mentor a child to certified  →  +200 QBC to the parent
  · child dowry on grant execute  →  +100 QBC to the newborn child

Idempotency:
  Each pay reason carries a stable reason_key. We refuse to mint the
  same reason_key twice. State for reason_keys is persisted; rehydrates
  with the bank.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Any
import time

from . import write_registry, append_log, now, load, COG_REG
from .bank import bank
from .worker_pnl import worker_pnl
from .worker_certification import worker_certification
from .family_tree import family_tree


PAY_RATES = {
    "per_usd_pnl_qbc":            1.0,
    "max_qbc_per_pnl_settlement": 200.0,
    "classroom_pass_qbc":         50.0,
    "friend_anniversary_qbc":     25.0,
    "friend_anniversary_after_days": 30,
    "mentor_child_certified_qbc": 200.0,
    "child_dowry_qbc":            100.0,
}


@dataclass
class PaymentRecord:
    reason_key: str
    worker_id: str
    qbc_amount: float
    kind: str
    paid_ts: float
    note: str = ""


class CompensationEngine:
    def __init__(self):
        self._paid_reasons: Set[str] = set()
        self._records: List[PaymentRecord] = []

    # ── unit pay APIs ─────────────────────────────────────────────
    def pay_pnl_share(self, worker_id: str, pnl_usd: float,
                       settlement_round_key: str = "") -> Optional[PaymentRecord]:
        if pnl_usd <= 0: return None
        reason = f"pnl|{worker_id}|{settlement_round_key or 'auto'}"
        if reason in self._paid_reasons:
            return None
        amount = min(pnl_usd * PAY_RATES["per_usd_pnl_qbc"],
                      PAY_RATES["max_qbc_per_pnl_settlement"])
        return self._pay(reason, worker_id, amount, "mint_pnl_share",
                          note=f"PnL share for ${pnl_usd:.2f} practice profit")

    def pay_classroom_pass(self, worker_id: str, instrument: str) -> Optional[PaymentRecord]:
        reason = f"classroom|{worker_id}|{instrument}"
        if reason in self._paid_reasons:
            return None
        return self._pay(reason, worker_id,
                          PAY_RATES["classroom_pass_qbc"],
                          "mint_classroom_pass",
                          note=f"Passed classroom for {instrument}")

    def pay_friend_anniversary(self, a: str, b: str,
                                 days_since_pairing: int) -> List[PaymentRecord]:
        if days_since_pairing < PAY_RATES["friend_anniversary_after_days"]:
            return []
        # Pay BOTH friends
        out: List[PaymentRecord] = []
        for who in (a, b):
            reason = f"friend|{a}|{b}|{days_since_pairing // 30}|{who}"
            if reason in self._paid_reasons:
                continue
            rec = self._pay(reason, who,
                             PAY_RATES["friend_anniversary_qbc"],
                             "mint_friend_anniversary",
                             note=f"Friend pairing with {b if who==a else a} "
                                   f"at {days_since_pairing}d")
            if rec: out.append(rec)
        return out

    def pay_mentor_child_certified(self, parent_id: str,
                                     child_id: str,
                                     instrument: str) -> Optional[PaymentRecord]:
        reason = f"mentor|{parent_id}|{child_id}|{instrument}"
        if reason in self._paid_reasons:
            return None
        return self._pay(reason, parent_id,
                          PAY_RATES["mentor_child_certified_qbc"],
                          "mint_mentorship_certified",
                          note=f"Mentored {child_id} to certified on {instrument}")

    def pay_child_dowry(self, child_id: str, grant_id: str) -> Optional[PaymentRecord]:
        reason = f"dowry|{child_id}|{grant_id}"
        if reason in self._paid_reasons:
            return None
        return self._pay(reason, child_id,
                          PAY_RATES["child_dowry_qbc"],
                          "mint_grant_bonus",
                          note=f"Newborn dowry on grant {grant_id}")

    # ── batch settlement ─────────────────────────────────────────
    def settle_round(self) -> Dict[str, Any]:
        """Sweep all known sources, idempotent. Pays only NEW reasons."""
        # 1. PnL share — pay every worker by their CURRENT realized_pnl
        pnl = worker_pnl(); pnl.refresh()
        snap = pnl.snapshot()
        pnl_paid: List[str] = []
        # Daily settlement key to keep PnL share idempotent within a day
        day_key = time.strftime("%Y-%m-%d", time.gmtime())
        for row in snap.get("rows_sample") or []:
            wid = row.get("worker_id")
            if wid in (None, "unassigned"): continue
            r = self.pay_pnl_share(
                wid, float(row.get("realized_pnl") or 0),
                settlement_round_key=day_key,
            )
            if r: pnl_paid.append(wid)

        # 2. Classroom passes — read cert ledger; if certified and we
        #    haven't paid this (worker, instrument) before, pay it.
        cert = worker_certification()
        snap_c = cert.snapshot()
        class_paid: List[str] = []
        for e in snap_c.get("entries_sample") or []:
            if e.get("status") == "certified":
                wid = e.get("worker_id"); inst = e.get("instrument")
                if wid and inst:
                    r = self.pay_classroom_pass(wid, inst)
                    if r: class_paid.append(f"{wid}/{inst}")

        # 3. Friend anniversaries
        ft = family_tree()
        ft_snap = ft.snapshot()
        anniv_paid: List[str] = []
        for e in ft_snap.get("friends_sample") or []:
            days = max(0, int((time.time() - float(e.get("granted_ts") or 0))
                                / 86400))
            recs = self.pay_friend_anniversary(e["a"], e["b"], days)
            for r in recs: anniv_paid.append(r.worker_id)

        # 4. Child dowries — for every child edge we haven't dowered yet
        dowry_paid: List[str] = []
        for e in ft_snap.get("children_sample") or []:
            cid = e.get("child_id"); gid = e.get("grant_id")
            if cid and gid:
                r = self.pay_child_dowry(cid, gid)
                if r: dowry_paid.append(cid)

        append_log("compensation.jsonl", {
            "event": "settle_round",
            "pnl_paid": len(pnl_paid),
            "classroom_paid": len(class_paid),
            "friend_anniversary_paid": len(anniv_paid),
            "child_dowry_paid": len(dowry_paid),
        })
        return {
            "pnl_paid": pnl_paid,
            "classroom_paid": class_paid,
            "friend_anniversary_paid": anniv_paid,
            "child_dowry_paid": dowry_paid,
        }

    # ── internal ──────────────────────────────────────────────────
    def _pay(self, reason_key: str, worker_id: str, qbc_amount: float,
              kind: str, note: str = "") -> Optional[PaymentRecord]:
        t = bank().mint(worker_id, qbc_amount, kind, note=note,
                         metadata={"reason_key": reason_key})
        if t is None:
            return None
        self._paid_reasons.add(reason_key)
        rec = PaymentRecord(reason_key=reason_key, worker_id=worker_id,
                             qbc_amount=qbc_amount, kind=kind,
                             paid_ts=time.time(), note=note)
        self._records.append(rec)
        return rec

    # ── snapshot ──────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        by_kind: Dict[str, float] = {}
        for r in self._records:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + r.qbc_amount
        return {
            "ok": True,
            "kind": "cognitive_compensation_state",
            "generated_ts": now(),
            "policy": ("Sole minting API. Idempotent per reason_key. "
                        "Audit trail in bank_transactions.jsonl."),
            "pay_rates": dict(PAY_RATES),
            "paid_reason_count": len(self._paid_reasons),
            "total_paid_by_kind": {k: round(v, 2) for k, v in by_kind.items()},
            "recent_payments": [asdict(r) for r in self._records[-30:]],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_compensation_state.json", snap)
        return snap

    def load_from_snapshot(self) -> int:
        d = load(COG_REG / "cognitive_compensation_state.json")
        if not isinstance(d, dict):
            return 0
        for r in d.get("recent_payments") or []:
            rk = r.get("reason_key")
            if rk:
                self._paid_reasons.add(rk)
        return len(self._paid_reasons)


_COMP: Optional[CompensationEngine] = None


def compensation_engine() -> CompensationEngine:
    global _COMP
    if _COMP is None:
        _COMP = CompensationEngine()
    return _COMP
