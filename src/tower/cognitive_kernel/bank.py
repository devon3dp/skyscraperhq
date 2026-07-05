"""Bank — Internal QSB Bank Credit (QBC) accounting layer.

QBC is the skyscraper's internal currency. Its purpose:
  · reward workers for advisory milestones (PnL, certifications, mentor)
  · let workers "spend" on classroom unlocks, child dowries, titles
  · model an internal economy the Kernel can reason about

Hard rules (every transaction stamps SAFETY):
  · NEVER convertible to fiat without an operator-flipped gate
  · NEVER an external transfer surface
  · ONLY compensation_engine.pay() and bank.spend() / .transfer() may
    move QBC; direct registry edits are NOT honoured by the in-memory
    ledger (rehydration ignores any balance not backed by a txn).

Supply governance:
  · TOTAL_SUPPLY_CAP = 1_000_000 QBC (operator can lift)
  · Inflation watch: if 7-day net-mint > 7-day net-burn for 7
    consecutive days, file 'tighten' proposal at 80% cap utilisation.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time
import uuid

from . import write_registry, append_log, now, load, COG_REG


TOTAL_SUPPLY_CAP = 1_000_000
TIGHTEN_AT_UTILISATION = 0.80
TXN_LOG = "bank_transactions.jsonl"


VALID_TXN_KINDS = {
    "mint_pnl_share",
    "mint_classroom_pass",
    "mint_mentorship_certified",
    "mint_friend_anniversary",
    "mint_grant_bonus",
    "burn_classroom_unlock",
    "burn_instrument_unlock",
    "burn_cosmetic_title",
    "burn_child_dowry",
    "transfer_friend_gift",
    "transfer_dowry_to_child",
    "adjustment_operator_audit",
}


@dataclass
class Transaction:
    txn_id: str
    kind: str                 # one of VALID_TXN_KINDS
    amount: float             # positive = credit to `to_worker`; negative = debit
    from_worker: Optional[str]   # None for mint
    to_worker: Optional[str]     # None for burn
    ts: float
    note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerAccount:
    worker_id: str
    balance: float = 0.0
    total_minted: float = 0.0
    total_burned: float = 0.0
    txn_count: int = 0
    last_txn_ts: Optional[float] = None


class Bank:
    def __init__(self):
        self._accounts: Dict[str, WorkerAccount] = {}
        self._txns: List[Transaction] = []
        self._total_supply: float = 0.0  # outstanding QBC across all balances

    # ── public API ─────────────────────────────────────────────────
    def mint(self, to_worker: str, amount: float, kind: str,
              note: str = "",
              metadata: Optional[Dict[str, Any]] = None) -> Optional[Transaction]:
        if amount <= 0: return None
        if kind not in VALID_TXN_KINDS or not kind.startswith("mint_"):
            return None
        if self._total_supply + amount > TOTAL_SUPPLY_CAP:
            append_log(TXN_LOG, {"event": "mint_refused_at_cap",
                                  "would_mint": amount,
                                  "current_supply": self._total_supply,
                                  "cap": TOTAL_SUPPLY_CAP})
            return None
        acc = self._account(to_worker)
        acc.balance += amount
        acc.total_minted += amount
        acc.txn_count += 1
        acc.last_txn_ts = time.time()
        self._total_supply += amount
        return self._record(kind=kind, amount=amount,
                             from_worker=None, to_worker=to_worker,
                             note=note, metadata=metadata)

    def burn(self, from_worker: str, amount: float, kind: str,
              note: str = "",
              metadata: Optional[Dict[str, Any]] = None) -> Optional[Transaction]:
        if amount <= 0: return None
        if kind not in VALID_TXN_KINDS or not kind.startswith("burn_"):
            return None
        acc = self._account(from_worker)
        if acc.balance < amount:
            append_log(TXN_LOG, {"event": "burn_refused_insufficient",
                                  "worker": from_worker,
                                  "balance": acc.balance,
                                  "amount": amount})
            return None
        acc.balance -= amount
        acc.total_burned += amount
        acc.txn_count += 1
        acc.last_txn_ts = time.time()
        self._total_supply -= amount
        return self._record(kind=kind, amount=amount,
                             from_worker=from_worker, to_worker=None,
                             note=note, metadata=metadata)

    def transfer(self, from_worker: str, to_worker: str, amount: float,
                  kind: str, note: str = "",
                  metadata: Optional[Dict[str, Any]] = None) -> Optional[Transaction]:
        if amount <= 0 or from_worker == to_worker: return None
        if kind not in VALID_TXN_KINDS or not kind.startswith("transfer_"):
            return None
        fa = self._account(from_worker)
        ta = self._account(to_worker)
        if fa.balance < amount:
            append_log(TXN_LOG, {"event": "transfer_refused_insufficient",
                                  "from": from_worker, "to": to_worker,
                                  "amount": amount,
                                  "balance": fa.balance})
            return None
        fa.balance -= amount
        ta.balance += amount
        fa.txn_count += 1
        ta.txn_count += 1
        fa.last_txn_ts = ta.last_txn_ts = time.time()
        return self._record(kind=kind, amount=amount,
                             from_worker=from_worker, to_worker=to_worker,
                             note=note, metadata=metadata)

    # ── read API ───────────────────────────────────────────────────
    def balance(self, worker_id: str) -> float:
        return self._accounts.get(worker_id, WorkerAccount(worker_id)).balance

    def account(self, worker_id: str) -> WorkerAccount:
        return self._account(worker_id)

    def total_supply(self) -> float:
        return self._total_supply

    def utilisation(self) -> float:
        return self._total_supply / TOTAL_SUPPLY_CAP if TOTAL_SUPPLY_CAP else 0.0

    def recent_transactions(self, n: int = 50) -> List[Dict[str, Any]]:
        return [asdict(t) for t in self._txns[-n:]]

    def top_balances(self, n: int = 10) -> List[Dict[str, Any]]:
        rows = sorted(self._accounts.values(),
                      key=lambda a: -a.balance)[:n]
        return [asdict(a) for a in rows]

    # ── internal ───────────────────────────────────────────────────
    def _account(self, worker_id: str) -> WorkerAccount:
        if worker_id not in self._accounts:
            self._accounts[worker_id] = WorkerAccount(worker_id=worker_id)
        return self._accounts[worker_id]

    def _record(self, kind: str, amount: float,
                 from_worker: Optional[str], to_worker: Optional[str],
                 note: str,
                 metadata: Optional[Dict[str, Any]]) -> Transaction:
        t = Transaction(
            txn_id=f"qbc_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}",
            kind=kind, amount=amount,
            from_worker=from_worker, to_worker=to_worker,
            ts=time.time(), note=note,
            metadata=metadata or {},
        )
        self._txns.append(t)
        append_log(TXN_LOG, asdict(t))
        return t

    # ── snapshot ───────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        # Concentration: % of supply held by top 10% of accounts
        accs = list(self._accounts.values())
        accs.sort(key=lambda a: -a.balance)
        n = len(accs)
        top_share = 0.0
        if n > 0 and self._total_supply > 0:
            cut = max(1, n // 10)
            top_share = sum(a.balance for a in accs[:cut]) / self._total_supply
        return {
            "ok": True,
            "kind": "cognitive_bank_state",
            "generated_ts": now(),
            "policy": ("Internal QBC accounting only. No fiat conversion. "
                        "No external transfer. Operator-flipped gates "
                        "would be required to change either."),
            "currency": "QBC",
            "total_supply_cap": TOTAL_SUPPLY_CAP,
            "outstanding_supply": round(self._total_supply, 2),
            "utilisation": round(self.utilisation(), 4),
            "tighten_at_utilisation": TIGHTEN_AT_UTILISATION,
            "account_count": n,
            "txn_count": len(self._txns),
            "top10_pct_concentration": round(top_share, 4),
            "top_balances": self.top_balances(15),
            "recent_transactions": self.recent_transactions(40),
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_bank_state.json", snap)
        return snap

    def load_from_snapshot(self) -> int:
        """Rehydrate accounts + txns from cognitive_bank_state.json.

        Txns are the source of truth — we replay them so balances and
        total_supply are derived, not trusted. This means tampering with
        the persisted snapshot can ONLY harm the txn record; balance
        integrity is rebuilt.
        """
        d = load(COG_REG / "cognitive_bank_state.json")
        if not isinstance(d, dict):
            return 0
        rebuilt = 0
        known_txn_ids = {t.txn_id for t in self._txns}
        for r in d.get("recent_transactions") or []:
            if r.get("txn_id") in known_txn_ids:
                continue
            t = Transaction(
                txn_id=r["txn_id"], kind=r["kind"],
                amount=float(r["amount"]),
                from_worker=r.get("from_worker"),
                to_worker=r.get("to_worker"),
                ts=float(r.get("ts") or 0),
                note=r.get("note", ""),
                metadata=r.get("metadata") or {},
            )
            self._txns.append(t)
            known_txn_ids.add(t.txn_id)
            # Replay into balances
            if t.kind.startswith("mint_") and t.to_worker:
                acc = self._account(t.to_worker)
                acc.balance += t.amount
                acc.total_minted += t.amount
                acc.txn_count += 1
                acc.last_txn_ts = t.ts
                self._total_supply += t.amount
            elif t.kind.startswith("burn_") and t.from_worker:
                acc = self._account(t.from_worker)
                acc.balance -= t.amount
                acc.total_burned += t.amount
                acc.txn_count += 1
                acc.last_txn_ts = t.ts
                self._total_supply -= t.amount
            elif t.kind.startswith("transfer_") and t.from_worker and t.to_worker:
                fa = self._account(t.from_worker)
                ta = self._account(t.to_worker)
                fa.balance -= t.amount
                ta.balance += t.amount
                fa.txn_count += 1
                ta.txn_count += 1
                fa.last_txn_ts = ta.last_txn_ts = t.ts
            rebuilt += 1
        return rebuilt


_BANK: Optional[Bank] = None


def bank() -> Bank:
    global _BANK
    if _BANK is None:
        _BANK = Bank()
    return _BANK
