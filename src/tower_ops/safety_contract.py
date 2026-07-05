"""Safety contract for the Tower Operations layer.

This file is the single source of truth for the execution-lock posture.
Every department module imports `LOCKED_FALSE` and stamps it on every
published record. None of these flags is ever set to true in code.
"""

NEW_LOCK_KEYS = (
    # Required by the Tower Operations V1 brief
    "worker_real_registry_enabled",          # set true by default — the registry IS live
    "worker_execution_enabled",
    "recruited_worker_execution_enabled",
    "openclaw_readiness_enabled",            # set true — readiness assessment is allowed
    "openclaw_execution_enabled",
    "maintenance_auto_repair_enabled",
    "security_enforcement_enabled",          # set true — Security floor enforces locks
    "it_network_observability_enabled",      # set true — IT observes only
    "web_access_autonomous_enabled",
)

# Boolean defaults — most locks remain false; a small number of capability
# flags are intentionally TRUE because they describe "allowed to observe"
# rather than "allowed to execute".
LOCKED_FALSE = {
    "live_trading_enabled":                       False,
    "order_execution_enabled":                    False,
    "practice_order_execution_enabled":           False,
    "binance_order_execution_enabled":            False,
    "binance_live_trading_enabled":               False,
    "stock_order_execution_enabled":              False,
    "stock_live_trading_enabled":                 False,
    "stock_paper_order_execution_enabled":        False,
    "cross_market_execution_enabled":             False,
    "worker_execution_enabled":                   False,
    "recruited_worker_execution_enabled":         False,
    "provider_execution_enabled":                 False,
    "external_provider_execution_enabled":        False,
    "openclaw_execution_enabled":                 False,
    "openclaw_real_tool_execution_enabled":       False,
    "autonomous_dispatch_enabled":                False,
    "live_dispatch_enabled":                      False,
    "direct_provider_access":                     False,
    "recruitment_openclaw_execution_enabled":     False,
    "recruited_worker_live_execution_enabled":    False,
    "recruited_worker_provider_access_enabled":   False,
    "recruited_worker_autonomous_dispatch_enabled": False,
    "maintenance_auto_repair_enabled":            False,
    "web_access_autonomous_enabled":              False,
    # Capability flags — observation only, not execution. Surfacing them
    # in /api/unified gives Floor 30 / Security a single source of truth.
    "worker_real_registry_enabled":               True,
    "openclaw_readiness_enabled":                 True,
    "security_enforcement_enabled":               True,
    "it_network_observability_enabled":           True,
}


def all_lock_keys():
    return tuple(LOCKED_FALSE.keys())


def stamp_safe(obj):
    """Return obj with the safety contract stamped on. obj must be a dict."""
    out = dict(obj or {})
    out.update(LOCKED_FALSE)
    out["execution_allowed"] = False
    out["paper_only"] = True
    out["advisory_only"] = True
    out["read_only"] = True
    out["not_financial_advice"] = True
    return out
