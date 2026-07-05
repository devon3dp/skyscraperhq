"""FreeImagePromotion — Operator-approved draft → Floor 46 catalog.

Reads cognitive_free_image_catalog.json (drafts). The operator approves
specific drafts via tools/qsb_image.py. Approved drafts get promoted
into qsb_floor46_commerce_catalog.json with status='draft_from_free_image'.

The PUBLISH gate (live_listings_publishing_enabled) stays locked. This
module only moves a draft from "advisory synthesised" to "operator-
approved-ready-for-future-publish".

State machine per draft:
  proposed (in free_image_catalog snapshot)
    → approved_for_catalog (operator says yes; stamped in approvals)
      → promoted (added to Floor 46 catalog as draft)
        → published   ← requires SEPARATE Claude phase that flips
                        live_listings_publishing_enabled=True
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json
import time

from . import REG, COG_REG, write_registry, append_log, now, load


APPROVALS_REGISTRY = "cognitive_free_image_approvals.json"
FLOOR46_CATALOG = "qsb_floor46_commerce_catalog.json"


@dataclass
class Approval:
    draft_id: str
    sku: str
    source_name: str
    approved_ts: float
    approved_by: str        # 'operator' | 'operator+claude'
    promoted: bool = False
    promoted_ts: Optional[float] = None
    note: str = ""


class FreeImagePromotion:

    def __init__(self):
        self._approvals: Dict[str, Approval] = {}

    def load_approvals(self) -> int:
        d = load(COG_REG / APPROVALS_REGISTRY)
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("approvals") or []:
            did = r.get("draft_id")
            if did and did not in self._approvals:
                self._approvals[did] = Approval(
                    draft_id=did, sku=r.get("sku", ""),
                    source_name=r.get("source_name", ""),
                    approved_ts=float(r.get("approved_ts") or 0),
                    approved_by=r.get("approved_by", "operator"),
                    promoted=bool(r.get("promoted")),
                    promoted_ts=(float(r["promoted_ts"])
                                  if r.get("promoted_ts") else None),
                    note=r.get("note", ""),
                )
                count += 1
        return count

    def approve(self, draft_id: str, approved_by: str = "operator",
                  note: str = "") -> Optional[Approval]:
        # Look up draft in free_image_catalog
        cat = load(COG_REG / "cognitive_free_image_catalog.json")
        if not isinstance(cat, dict):
            return None
        draft = next((d for d in cat.get("draft_sample") or []
                       if d.get("draft_id") == draft_id), None)
        if not draft:
            append_log("free_image_promotion.jsonl", {
                "event": "approve_unknown_draft",
                "draft_id": draft_id,
            })
            return None
        if draft_id in self._approvals:
            return self._approvals[draft_id]
        a = Approval(
            draft_id=draft_id, sku=draft.get("sku", ""),
            source_name=draft.get("source_name", ""),
            approved_ts=time.time(),
            approved_by=approved_by, note=note,
        )
        self._approvals[draft_id] = a
        append_log("free_image_promotion.jsonl", {
            "event": "approved",
            "draft_id": draft_id, "approved_by": approved_by,
        })
        return a

    def promote_approved(self) -> List[str]:
        """For every approved-but-not-promoted draft, add it to the
        Floor 46 catalog. Returns SKUs promoted this round."""
        cat = load(COG_REG / "cognitive_free_image_catalog.json")
        if not isinstance(cat, dict):
            return []
        # Resolve drafts by draft_id
        by_did = {d.get("draft_id"): d for d in
                  (cat.get("draft_sample") or [])
                  if d.get("draft_id")}
        # Read floor 46 catalog (in MAIN REG namespace)
        f46_path = REG / FLOOR46_CATALOG
        if not f46_path.exists():
            return []
        try:
            f46 = json.loads(f46_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        products = f46.get("products") or []
        existing_skus = {p.get("sku") for p in products}
        promoted_now: List[str] = []
        for a in self._approvals.values():
            if a.promoted:
                continue
            draft = by_did.get(a.draft_id)
            if not draft:
                continue
            if draft.get("sku") in existing_skus:
                a.promoted = True
                a.promoted_ts = time.time()
                continue
            # Add as a draft product
            products.append({
                "sku": draft.get("sku"),
                "title": draft.get("title"),
                "category": draft.get("category"),
                "cost_to_produce": draft.get("base_cost"),
                "suggested_price": draft.get("suggested_price"),
                "avg_market_price": draft.get("suggested_price"),  # no anchor yet
                "estimated_demand_monthly": draft.get("notional_demand_monthly"),
                "tags": ["free_image_derivative",
                          draft.get("source_name", "").lower(),
                          draft.get("category", "")],
                "status": "draft_from_free_image",
                "notes": (f"Promoted from free-image draft "
                           f"{a.draft_id}. Source: {draft.get('source_name')}. "
                           f"License: {draft.get('source_license')}. "
                           f"NOT PUBLISHED — needs separate gate flip."),
            })
            existing_skus.add(draft.get("sku"))
            a.promoted = True
            a.promoted_ts = time.time()
            promoted_now.append(draft.get("sku"))
            append_log("free_image_promotion.jsonl", {
                "event": "promoted",
                "draft_id": a.draft_id, "sku": draft.get("sku"),
            })
        if promoted_now:
            f46["products"] = products
            f46["product_count"] = len(products)
            f46["last_promotion_ts"] = now()
            f46_path.write_text(json.dumps(f46, indent=2), encoding="utf-8")
        return promoted_now

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "kind": "cognitive_free_image_approvals",
            "generated_ts": now(),
            "policy": ("Operator-approved free-image drafts only. No "
                        "publishing without the live_listings_publishing "
                        "gate flip — a separate phase."),
            "approval_count": len(self._approvals),
            "promoted_count": sum(1 for a in self._approvals.values()
                                    if a.promoted),
            "approvals": [asdict(a) for a in self._approvals.values()],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry(APPROVALS_REGISTRY, snap)
        return snap


_FIP: Optional[FreeImagePromotion] = None


def free_image_promotion() -> FreeImagePromotion:
    global _FIP
    if _FIP is None:
        _FIP = FreeImagePromotion()
    return _FIP
