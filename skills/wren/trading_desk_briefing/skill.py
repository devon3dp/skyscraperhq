"""trading_desk_briefing — reconciled accounts / trading-desk briefing for Wren.

Read-only. Always surfaces the execution flags (advisory_only / no real money)
so Wren states the truth about what is and isn't live.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SUMMARY = ROOT / "data/registries/qsb_accounts_summary_latest.json"


def run():
    if not SUMMARY.exists():
        return {"ok": False, "error": "accounts_summary_latest not found"}
    try:
        d = json.loads(SUMMARY.read_text())
    except Exception as e:
        return {"ok": False, "error": f"bad summary json: {e}"}
    rt = d.get("reconciled_totals", {})
    comp = rt.get("realized_pnl_components_gbp", {})
    return {
        "ok": True,
        "generated_ts": d.get("generated_ts"),
        "advisory_only": d.get("advisory_only"),
        "execution_allowed": d.get("execution_allowed"),
        "real_money": d.get("real_money"),
        "realized_pnl_gbp_all_venues": rt.get("realized_pnl_gbp_all_venues"),
        "pnl_by_venue_gbp": {
            "F41_oanda": comp.get("F41_oanda_lifetime_gbp"),
            "F42_binance": comp.get("F42_binance_gbp"),
            "F43_alpaca": comp.get("F43_alpaca_gbp"),
        },
        "oanda_practice_nav_gbp": rt.get("oanda_practice_nav_gbp"),
        "oanda_practice_balance_gbp": rt.get("oanda_practice_balance_gbp"),
        "oanda_unrealized_gbp": rt.get("oanda_unrealized_gbp"),
        "belief_fleet_committed_gbp": rt.get("belief_fleet_committed_gbp"),
        "belief_fleet_open_exposure_gbp": rt.get("belief_fleet_open_exposure_gbp"),
        "provider_spend_usd_today": rt.get("provider_spend_usd_today"),
        "data_gaps": d.get("data_gaps"),
        "note": "advisory only — no real-money execution; OANDA practice + testnet/paper only",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
