"""Pricing advisor for Floor 46.

Looks at the sandbox catalog and proposes — never enacts — pricing
moves. Files advisory action proposals through the cognitive kernel's
action_proposer.

Metrics produced per product:
  · margin_percent
  · vs_market_percent  (suggested vs. anchor)
  · projected_monthly_revenue
  · projected_monthly_profit
  · advisory_action  ('raise' / 'lower' / 'hold')
  · advisory_reason  (one-line)

A floor-level summary emits:
  · total projected revenue / profit
  · best three SKUs by projected profit
  · worst three SKUs by margin
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from tower.cognitive_kernel import REG, now
from tower.cognitive_kernel.action_proposal import action_proposer
from .catalog import SANDBOX_PRODUCTS, SandboxProduct
import json as _json


MARGIN_TARGET_PERCENT = 55.0
UNDERPRICED_VS_MARKET_PERCENT = -8.0       # we're > 8% below market
OVERPRICED_VS_MARKET_PERCENT = 10.0         # we're > 10% above market


@dataclass
class PricingRecommendation:
    sku: str
    current_price: float
    advisory_action: str          # 'raise' | 'lower' | 'hold'
    advisory_reason: str
    projected_monthly_revenue: float
    projected_monthly_profit: float
    margin_percent: float
    vs_market_percent: float


class PricingAdvisor:
    def evaluate(self, product: SandboxProduct) -> PricingRecommendation:
        m = product.margin_percent()
        vm = product.vs_market()
        rev = product.suggested_price * product.estimated_demand_monthly
        profit = (product.suggested_price - product.cost_to_produce) \
                 * product.estimated_demand_monthly

        action = "hold"
        reason = "within target band"
        if vm < UNDERPRICED_VS_MARKET_PERCENT and m >= MARGIN_TARGET_PERCENT - 5:
            action = "raise"
            reason = (f"under market by {abs(vm):.1f}% with healthy "
                      f"margin {m:.1f}%; lift price toward anchor")
        elif vm > OVERPRICED_VS_MARKET_PERCENT and product.estimated_demand_monthly < 25:
            action = "lower"
            reason = (f"over market by {vm:.1f}% with thin demand; "
                      f"trim toward anchor")
        elif m < 30.0:
            action = "raise"
            reason = (f"margin {m:.1f}% below 30%; either raise price or "
                      f"reduce cost-to-produce")

        return PricingRecommendation(
            sku=product.sku,
            current_price=product.suggested_price,
            advisory_action=action,
            advisory_reason=reason,
            projected_monthly_revenue=round(rev, 2),
            projected_monthly_profit=round(profit, 2),
            margin_percent=m,
            vs_market_percent=vm,
        )

    def evaluate_all(self) -> List[PricingRecommendation]:
        return [self.evaluate(p) for p in SANDBOX_PRODUCTS]

    def summarize(self) -> Dict[str, Any]:
        recs = self.evaluate_all()
        total_rev = sum(r.projected_monthly_revenue for r in recs)
        total_profit = sum(r.projected_monthly_profit for r in recs)
        best_profit = sorted(recs, key=lambda r: -r.projected_monthly_profit)[:3]
        worst_margin = sorted(recs, key=lambda r: r.margin_percent)[:3]
        return {
            "ok": True,
            "kind": "qsb_floor46_commerce_pricing",
            "generated_ts": now(),
            "policy": ("Advisory only. PricingAdvisor never edits product prices; "
                        "it proposes changes for operator approval."),
            "product_count": len(recs),
            "projected_monthly_revenue": round(total_rev, 2),
            "projected_monthly_profit":  round(total_profit, 2),
            "best_by_projected_profit": [r.__dict__ for r in best_profit],
            "worst_by_margin":          [r.__dict__ for r in worst_margin],
            "recommendations": [r.__dict__ for r in recs],
        }

    def propose_repricing(self) -> List[str]:
        """File one consolidated proposal per non-hold action group."""
        recs = self.evaluate_all()
        ap = action_proposer()
        filed: List[str] = []
        raises = [r for r in recs if r.advisory_action == "raise"]
        lowers = [r for r in recs if r.advisory_action == "lower"]
        if raises:
            p = ap.propose(
                title=f"Raise price on {len(raises)} SKU(s) (Floor 46 commerce)",
                rationale=("Pricing advisor flags these as under-market with "
                            "healthy margins, or below the 30% margin floor. "
                            "Per-SKU reasons in cognitive_action_proposals.json."),
                proposed_action=("operator: review each SKU's "
                                  "advisory_reason in "
                                  "qsb_floor46_commerce_pricing.json; update "
                                  "suggested_price in catalog.py; re-run "
                                  "advisor."),
                requires_approval_from="operator",
                confidence=0.65,
                tags=["floor46", "commerce", "pricing", "raise"],
            )
            filed.append(p.id)
        if lowers:
            p = ap.propose(
                title=f"Lower price on {len(lowers)} SKU(s) (Floor 46 commerce)",
                rationale=("Pricing advisor flags these as over-market with thin "
                            "demand; risk of sitting unsold once listed."),
                proposed_action=("operator: review each SKU's advisory_reason; "
                                  "trim suggested_price; re-run advisor."),
                requires_approval_from="operator",
                confidence=0.6,
                tags=["floor46", "commerce", "pricing", "lower"],
            )
            filed.append(p.id)
        return filed

    def persist(self) -> Dict[str, Any]:
        summary = self.summarize()
        p = REG / "qsb_floor46_commerce_pricing.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_json.dumps(summary, indent=2), encoding="utf-8")
        return summary


_ADVISOR: Optional[PricingAdvisor] = None


def pricing_advisor() -> PricingAdvisor:
    global _ADVISOR
    if _ADVISOR is None:
        _ADVISOR = PricingAdvisor()
    return _ADVISOR
