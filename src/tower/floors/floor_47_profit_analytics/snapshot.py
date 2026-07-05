"""ProfitAnalytics — Floor 47.

Reads all revenue surfaces in the tower and emits one profit_snapshot.
NEVER writes anywhere except the cognitive registries namespace, NEVER
calls any external API.

Sources (all read-only):
  · qsb_floor41_oanda_pnl.json                  (realized + unrealized FX)
  · qsb_floor41_oanda_trade_ledger.jsonl        (per-trade detail)
  · qsb_floor42_binance_state.json              (testnet preview)
  · qsb_floor43_stocks_state.json               (paper preview)
  · qsb_floor46_commerce_pricing.json           (projected commerce revenue)
  · qsb_worker_scene_state.json                 (workforce throughput)

Emits:
  · cognitive_profit_snapshot.json
  · advisory action proposals via action_proposer
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

from tower.cognitive_kernel import (
    ROOT, REG, COG_REG, SAFETY, write_registry, append_log, now, load,
)
from tower.cognitive_kernel.action_proposal import action_proposer


class ProfitAnalytics:

    # ── source readers ─────────────────────────────────────────────
    def _read_oanda(self) -> Dict[str, Any]:
        pnl = load(REG / "qsb_floor41_oanda_pnl.json")
        ledger = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"
        n_ledger = 0
        last_ts = None
        win = loss = 0
        if ledger.exists():
            try:
                with ledger.open("r", encoding="utf-8") as f:
                    for line in f:
                        n_ledger += 1
                        try:
                            r = json.loads(line)
                            last_ts = r.get("ts", last_ts)
                            pnl_v = r.get("realized_pnl") or r.get("pnl")
                            if isinstance(pnl_v, (int, float)):
                                if pnl_v > 0: win += 1
                                elif pnl_v < 0: loss += 1
                        except Exception:
                            continue
            except Exception:
                pass
        wr = (win / (win + loss)) if (win + loss) else None
        return {
            "floor": "floor_41_oanda_practice",
            "mode": "PRACTICE_ONLY",
            "realized_pnl": (pnl or {}).get("realized_pnl"),
            "unrealized_pnl": (pnl or {}).get("unrealized_pnl"),
            "open_trade_count": (pnl or {}).get("open_trade_count"),
            "closed_trade_count": (pnl or {}).get("closed_trade_count"),
            "ledger_lines": n_ledger,
            "win_count": win,
            "loss_count": loss,
            "approx_win_rate": round(wr, 3) if wr is not None else None,
            "last_trade_ts": last_ts,
        }

    def _read_binance_testnet(self) -> Dict[str, Any]:
        d = load(REG / "qsb_floor42_binance_state.json") or {}
        return {
            "floor": "floor_42_binance_testnet",
            "mode": "TESTNET_PREVIEW_ONLY",
            "state_present": bool(d),
            "balance_preview": d.get("balance_preview") if isinstance(d, dict) else None,
        }

    def _read_stocks_paper(self) -> Dict[str, Any]:
        d = load(REG / "qsb_floor43_stocks_state.json") or {}
        return {
            "floor": "floor_43_stocks_paper",
            "mode": "PAPER_PREVIEW_ONLY",
            "state_present": bool(d),
            "paper_balance": d.get("paper_balance") if isinstance(d, dict) else None,
        }

    def _read_commerce(self) -> Dict[str, Any]:
        d = load(REG / "qsb_floor46_commerce_pricing.json") or {}
        return {
            "floor": "floor_46_commerce",
            "mode": "PREVIEW_ONLY",
            "projected_monthly_revenue": d.get("projected_monthly_revenue"),
            "projected_monthly_profit":  d.get("projected_monthly_profit"),
            "product_count":             d.get("product_count"),
        }

    def _read_workforce(self) -> Dict[str, Any]:
        ws = load(REG / "qsb_worker_scene_state.json") or {}
        floors = ws.get("floors") or ws.get("floor_summary") or {}
        total = active = idle = 0
        if isinstance(floors, dict):
            for f in floors.values():
                if not isinstance(f, dict): continue
                total += int(f.get("worker_count", f.get("workers", 0) or 0))
                active += int(f.get("active_count", f.get("active", 0) or 0))
                idle += int(f.get("idle_count", 0) or 0)
        elif isinstance(floors, list):
            for f in floors:
                if not isinstance(f, dict): continue
                total += int(f.get("worker_count", f.get("workers", 0) or 0))
                active += int(f.get("active_count", f.get("active", 0) or 0))
                idle += int(f.get("idle_count", 0) or 0)
        return {
            "total_workers": total,
            "active_workers": active,
            "idle_workers": idle if idle else max(0, total - active),
            "active_ratio": round(active / total, 3) if total else None,
        }

    # ── snapshot ───────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        oanda = self._read_oanda()
        binance = self._read_binance_testnet()
        stocks = self._read_stocks_paper()
        commerce = self._read_commerce()
        workforce = self._read_workforce()

        # Aggregate projected monthly revenue. Only commerce contributes a
        # number we can trust as a "projection" today. Trading floors are
        # practice/testnet, so they get realized PnL fields surfaced
        # separately rather than added to a topline projection.
        proj_rev = float(commerce.get("projected_monthly_revenue") or 0)
        proj_profit = float(commerce.get("projected_monthly_profit") or 0)
        realized_oanda = float(oanda.get("realized_pnl") or 0)

        # Risk/health flags
        warnings: List[str] = []
        if oanda["realized_pnl"] in (None, 0, 0.0):
            warnings.append("oanda_floor41_pnl_zero_or_missing")
        if not commerce.get("projected_monthly_revenue"):
            warnings.append("commerce_floor46_no_projection")
        if (workforce.get("active_ratio") or 0) < 0.5 and workforce["total_workers"]:
            warnings.append("workforce_under_50_percent_active")
        if not binance["state_present"]:
            warnings.append("binance_testnet_state_missing")
        if not stocks["state_present"]:
            warnings.append("stocks_paper_state_missing")

        return {
            "ok": True,
            "kind": "cognitive_profit_snapshot",
            "generated_ts": now(),
            "policy": ("Read-only cross-floor profit summary. Advisory. "
                        "Kernel does not enable any execution path."),
            "safety_envelope": dict(SAFETY),
            "topline": {
                "projected_monthly_revenue_commerce": round(proj_rev, 2),
                "projected_monthly_profit_commerce":  round(proj_profit, 2),
                "realized_pnl_oanda_practice": realized_oanda,
                "warnings": warnings,
            },
            "by_floor": {
                "floor_41_oanda_practice": oanda,
                "floor_42_binance_testnet": binance,
                "floor_43_stocks_paper": stocks,
                "floor_46_commerce_preview": commerce,
            },
            "workforce": workforce,
            "advisory_actions": self._advisory_actions(
                proj_rev, proj_profit, realized_oanda, workforce, warnings,
            ),
        }

    def _advisory_actions(self, proj_rev: float, proj_profit: float,
                          realized_oanda: float,
                          workforce: Dict[str, Any],
                          warnings: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if "commerce_floor46_no_projection" in warnings:
            out.append({
                "id": "advise_commerce_seed",
                "title": "Seed commerce catalog so projections can be computed",
                "action": "operator+claude: edit src/tower/floors/floor_46_commerce/catalog.py SANDBOX_PRODUCTS",
                "expected_value": "unblocks profit_snapshot.commerce projection",
            })
        if "oanda_floor41_pnl_zero_or_missing" in warnings:
            out.append({
                "id": "advise_oanda_strategy_eval",
                "title": "Run strategy evaluation on Floor 41 (practice only)",
                "action": "operator+claude: schedule strategy-eval worker; report win-rate + drawdown",
                "expected_value": "either lift practice PnL or learn the current strategy is unsuitable",
            })
        if proj_profit < 100 and proj_rev > 0:
            out.append({
                "id": "advise_pricing_review",
                "title": "Pricing review — projected profit < $100/mo across the whole commerce floor",
                "action": "operator: run pricing_advisor().propose_repricing()",
                "expected_value": "either lift price on under-market SKUs or trim the catalog",
            })
        if (workforce.get("active_ratio") or 0) < 0.5 and workforce["total_workers"]:
            out.append({
                "id": "advise_worker_reassignment",
                "title": "Workforce under 50% active — reassign idle workers",
                "action": "operator: review worker_reassignment proposals; approve highest-priority moves",
                "expected_value": "lift active_ratio above 0.7",
            })
        return out

    # ── persist + propose ─────────────────────────────────────────
    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_profit_snapshot.json", snap)
        append_log("profit_analytics.jsonl", {
            "event": "snapshot",
            "topline": snap["topline"],
            "warning_count": len(snap["topline"]["warnings"]),
        })
        return snap

    def file_proposals(self) -> List[str]:
        ap = action_proposer()
        snap = self.snapshot()
        filed: List[str] = []
        for a in snap["advisory_actions"]:
            p = ap.propose(
                title=a["title"],
                rationale=(f"Profit snapshot advisory_actions[{a['id']}]. "
                            f"Expected value: {a['expected_value']}."),
                proposed_action=a["action"],
                requires_approval_from="operator",
                confidence=0.6,
                tags=["floor47", "profit_analytics", a["id"]],
            )
            filed.append(p.id)
        return filed


_PA: Optional[ProfitAnalytics] = None


def profit_analytics() -> ProfitAnalytics:
    global _PA
    if _PA is None:
        _PA = ProfitAnalytics()
    return _PA
