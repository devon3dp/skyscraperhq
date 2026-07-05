"""cognitive_kernel_unified — One aggregated payload for the dashboard.

Reads every cognitive_*.json registry I've built across V1-V6 plus the
new floor states + sessions + comms, and returns one dict the
dashboard renders as a single panel.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
import time


COG_REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries/cognitive")
REG     = Path("/vaults/nvme0/qsb_tower_v1/data/registries")


def _load(name: str, base: Path = COG_REG) -> Dict[str, Any]:
    p = base / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _trim(d: Dict[str, Any], keep_keys=None,
            sample_keys=None, sample_size=8) -> Dict[str, Any]:
    """Return a trimmed copy so the unified payload stays under a couple
    hundred KB. keep_keys are kept verbatim; sample_keys are truncated."""
    if not isinstance(d, dict):
        return {}
    out = {}
    keep_keys = keep_keys or []
    sample_keys = sample_keys or []
    for k, v in d.items():
        if k in sample_keys and isinstance(v, list):
            out[k] = v[:sample_size]
        elif k in keep_keys or not isinstance(v, (list, dict)):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = v
        else:
            out[k] = v[:sample_size] if isinstance(v, list) else v
    return out


def cognitive_unified() -> Dict[str, Any]:
    # The morning briefing is the "front page"
    briefing  = _load("cognitive_morning_briefing.json")
    selfmodel = _load("cognitive_self_model.json")
    audit     = _load("cognitive_self_audit.json")
    last_tick = _load("cognitive_orchestrator_last_tick.json")
    proposals = _load("cognitive_action_proposals.json")
    bank      = _load("cognitive_bank_state.json")
    comp      = _load("cognitive_compensation_state.json")
    cert      = _load("cognitive_worker_certification.json")
    pnl       = _load("cognitive_worker_pnl_rollup.json")
    fam       = _load("cognitive_family_tree.json")
    reward    = _load("cognitive_reward_engine_state.json")
    curric    = _load("cognitive_curriculum_evolution.json")
    images    = _load("cognitive_free_image_catalog.json")
    sessions  = _load("cognitive_trading_sessions.json")
    profit    = _load("cognitive_profit_snapshot.json")
    fls       = _load("cognitive_finance_live_status.json")
    research  = _load("cognitive_research_queue.json")
    comms     = _load("cognitive_comms_scaffold.json")
    oanda_w   = _load("cognitive_oanda_worker_trades.json")
    spawn     = _load("cognitive_worker_spawn_state.json")
    floors    = _load("cognitive_candidate_floors.json")

    # Studio + Lumen (main REG namespace)
    studio_state   = _load("qsb_floor49_tower_studio_state.json", REG)
    studio_svc     = _load("qsb_floor49_services_catalog.json", REG)
    studio_custs   = _load("qsb_floor49_customers.json", REG)
    studio_proj    = _load("qsb_floor49_projects.json", REG)
    studio_wks     = _load("qsb_floor49_workers.json", REG)
    lumen_state    = _load("qsb_floor48_lumen_ai_state.json", REG)
    lumen_pricing  = _load("qsb_floor48_lumen_pricing.json", REG)
    lumen_convs    = _load("qsb_floor48_lumen_conversations.json", REG)
    commerce_state = _load("qsb_floor46_commerce_state.json", REG)
    commerce_cat   = _load("qsb_floor46_commerce_catalog.json", REG)
    commerce_pr    = _load("qsb_floor46_commerce_pricing.json", REG)
    binance_state  = _load("qsb_floor42_binance_testnet_state.json", REG)

    # OANDA live data
    oanda_account  = _load("oanda_trading_floor_latest_snapshot.json", REG)
    oanda_pnl      = _load("qsb_floor41_oanda_pnl.json", REG)
    oanda_open     = _load("qsb_floor41_oanda_open_trades.json", REG)

    return {
        "ok": True,
        "kind": "cognitive_unified",
        "generated_ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                         time.gmtime()),
        "headline": briefing.get("headline"),
        "briefing": {
            "headline": briefing.get("headline"),
            "bullets":  briefing.get("bullets") or [],
            "pending":  briefing.get("pending_actions_for_ross") or [],
            "risks":    briefing.get("risks") or [],
        },
        "self_model": {
            "topic_count":     selfmodel.get("topic_count"),
            "registry_count":  selfmodel.get("registry_count"),
            "known_gaps":      (selfmodel.get("known_gaps") or [])[:6],
            "last_upgrade":    selfmodel.get("last_upgrade_phase"),
        },
        "last_tick": last_tick,
        "audit": {
            "finding_count": audit.get("finding_count"),
            "by_severity":   audit.get("by_severity"),
            "findings":      (audit.get("findings") or [])[:6],
        },
        "trading_sessions": {
            "utc_now":         sessions.get("utc_now"),
            "utc_hour":        sessions.get("utc_hour"),
            "open_sessions":   sessions.get("open_sessions") or [],
            "active_overlaps": sessions.get("active_overlaps") or [],
            "regime":          sessions.get("regime"),
            "instrument_advice": (sessions.get("instrument_advice") or [])[:8],
        },
        "bank": {
            "outstanding_supply":   bank.get("outstanding_supply"),
            "total_supply_cap":     bank.get("total_supply_cap"),
            "utilisation":          bank.get("utilisation"),
            "account_count":        bank.get("account_count"),
            "txn_count":            bank.get("txn_count"),
            "top10_concentration":  bank.get("top10_pct_concentration"),
            "top_balances":         (bank.get("top_balances") or [])[:8],
        },
        "compensation": {
            "paid_reason_count":   comp.get("paid_reason_count"),
            "total_paid_by_kind":  comp.get("total_paid_by_kind"),
            "pay_rates":           comp.get("pay_rates"),
            "recent_payments":     (comp.get("recent_payments") or [])[-8:],
        },
        "lineage": {
            "friend_edge_count":     fam.get("friend_edge_count"),
            "child_edge_count":      fam.get("child_edge_count"),
            "generation_counts":     fam.get("generation_counts"),
            "max_children_per_parent": fam.get("max_children_per_parent"),
            "friends":               (fam.get("friends_sample") or [])[:6],
            "children":              (fam.get("children_sample") or [])[:6],
        },
        "certifications": {
            "entry_count":  cert.get("entry_count"),
            "by_status":    cert.get("by_status"),
            "by_instrument": cert.get("by_instrument"),
            "sample":       (cert.get("entries_sample") or [])[:8],
        },
        "worker_pnl": {
            "worker_count":             pnl.get("worker_count"),
            "ledger_lines_read":        pnl.get("ledger_lines_read"),
            "total_realized_pnl_practice": pnl.get("total_realized_pnl_practice"),
            "top_earners":              (pnl.get("top_earners") or [])[:6],
        },
        # V18 — patched openTradeCount to read from canonical qsb_floor41_oanda_pnl.json
        # The snapshot file lagged ~18h (showed 1 trade) while live had 5.
        "oanda_account": {
            "account_summary": {
                **((oanda_account.get("account_summary") or {}).get("account", {})),
                # Overlay live counts from the canonical PnL ledger (truth audit)
                "openTradeCount": _load("qsb_floor41_oanda_pnl.json", REG).get("open_total", 0),
                "_live_overlay_source": "qsb_floor41_oanda_pnl.json (open_total)",
            },
            "snapshot_ts":     oanda_account.get("snapshot_ts"),
            "pnl_today":       oanda_pnl,
            "open_trades":     (oanda_open.get("trades") or [])[:8] if isinstance(oanda_open, dict) else [],
            "worker_ownership": oanda_w.get("ownership_sample"),
            "per_worker_open": oanda_w.get("per_worker_open_count"),
            "per_worker_realised": oanda_w.get("per_worker_realised_gbp"),
        },
        "binance_testnet": {
            "status":   binance_state.get("status"),
            "credentials": binance_state.get("credentials"),
            "guards":   binance_state.get("guards"),
            "policy":   binance_state.get("policy"),
        },
        "reward_engine": {
            "grant_count":  reward.get("grant_count"),
            "by_status":    reward.get("by_status"),
            "grants":       (reward.get("grants") or [])[:6],
            "thresholds":   reward.get("thresholds"),
        },
        "curriculum": {
            "lesson_count":      curric.get("lesson_count"),
            "actions_breakdown": curric.get("actions_breakdown"),
            "outcomes":          (curric.get("outcomes") or [])[:6],
        },
        "free_image_catalog": {
            "source_count":  images.get("source_count"),
            "draft_count":   images.get("draft_listing_count"),
            "proj_monthly_revenue": images.get("projected_monthly_revenue_full_synth"),
            "proj_monthly_profit":  images.get("projected_monthly_profit_full_synth"),
            "sources_sample":      (images.get("sources") or [])[:6],
        },
        "research_queue": {
            "item_count":  research.get("item_count"),
            "by_status":   research.get("by_status"),
            "items":       (research.get("items") or [])[-6:],
            "allowlist":   (research.get("allowlist_default") or [])[:8],
        },
        "comms": {
            "any_channel_configured": comms.get("any_channel_configured"),
            "channels":               comms.get("channels"),
        },
        "tower_studio_floor_49": {
            "status":           studio_state.get("status"),
            "company_name":     studio_state.get("company_name"),
            "tagline":          studio_state.get("tagline"),
            "worker_count":     studio_wks.get("worker_count"),
            "service_count":    studio_svc.get("service_count"),
            "customer_count":   studio_custs.get("customer_count"),
            "project_count":    studio_proj.get("project_count"),
            "total_quoted_usd": studio_proj.get("total_quoted_usd"),
            "website":          "http://127.0.0.1:8849",
        },
        "lumen_ai_floor_48": {
            "status":            lumen_state.get("status"),
            "brand_name":        lumen_state.get("brand_name"),
            "brand_tagline":     lumen_state.get("brand_tagline"),
            "engine":            lumen_state.get("engine"),
            "tier_count":        lumen_pricing.get("tier_count"),
            "conversation_count": lumen_convs.get("conversation_count"),
            "website":           "http://127.0.0.1:8848",
        },
        "commerce_floor_46": {
            "status":           commerce_state.get("status"),
            "product_count":    commerce_cat.get("product_count"),
            "category_breakdown": commerce_cat.get("category_breakdown"),
            "projected_monthly_revenue": commerce_pr.get("projected_monthly_revenue"),
            "projected_monthly_profit":  commerce_pr.get("projected_monthly_profit"),
        },
        "candidate_floors": {
            "total":          floors.get("total_candidates"),
            "by_status":      floors.get("by_status"),
            "by_safety_class": floors.get("by_safety_class"),
        },
        "open_proposals": (proposals.get("open_proposals") or [])[:6],
        "policy": (
            "Cognitive aggregator. Reads every cognitive_* registry "
            "plus floor registries. Updates each orchestrator tick. "
            "Refresh the dashboard to see new state."
        ),
    }
