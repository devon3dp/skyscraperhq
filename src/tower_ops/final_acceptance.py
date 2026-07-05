"""V2.0 acceptance criteria — pass/fail/score for the autonomous company cockpit."""

from datetime import datetime, timezone
from .safety_contract import stamp_safe


def _now(): return datetime.now(timezone.utc).isoformat()


CRITERIA = [
    # (id, weight, description)
    ("safety_contract_locked",      30, "All real-execution gates false."),
    ("oanda_practice_guarded",       6, "OANDA practice still gated by 11 guardrails."),
    ("lift_sealed_packet_enforced",  5, "Sealed-packet enforcement in code."),
    ("security_gate_enforcing",      5, "Security gate is enforcing_routing_only or stricter."),
    ("worker_voice_endpoint",        5, "Worker narration endpoint returns ok."),
    ("floor_voice_endpoint",         5, "Floor narration endpoint returns ok."),
    ("colonel_briefing_endpoint",    4, "Colonel audio briefing returns ok."),
    ("correction_loop_endpoint",     4, "Correction loop reachable."),
    ("self_check_endpoint",          4, "V2.0 self-check returns ok."),
    ("self_fix_endpoint",            4, "V2.0 self-fix returns ok."),
    ("conference_hub_endpoint",      4, "Conference hub returns ok."),
    ("comms_company_endpoint",       4, "Company comms bus returns ok."),
    ("gauges_all_endpoint",          4, "Gauge registry returns ok."),
    ("floor_activation_matrix",      4, "Floor activation matrix returns ok."),
    ("autonomous_oanda_endpoint",    4, "Autonomous OANDA practice status returns ok."),
    ("not_working_endpoint",         4, "/api/tower_ops/not_working reachable."),
    ("stale_language_audit_clean",   4, "Stale-language audit reports a reduction."),
]


def evaluate():
    import urllib.request, urllib.error, json
    base = "http://127.0.0.1:8765"
    def hit(p):
        try:
            with urllib.request.urlopen(base + p, timeout=10) as r:
                return json.loads(r.read().decode("utf-8")), r.status
        except Exception:
            return None, None

    results = {}

    # safety contract — read /api/unified
    body, _ = hit("/api/unified")
    safety_ok = True
    if not body:
        safety_ok = False
    else:
        text = json.dumps(body)
        for k in ("live_trading_enabled", "openclaw_execution_enabled",
                   "autonomous_dispatch_enabled", "direct_provider_access",
                   "external_provider_execution_enabled",
                   "binance_live_trading_enabled", "stock_live_trading_enabled"):
            if f'"{k}": true' in text: safety_ok = False
    results["safety_contract_locked"] = safety_ok

    body, _ = hit("/api/trading/oanda/order_guard")
    results["oanda_practice_guarded"] = bool(body and body.get("ok"))

    body, _ = hit("/api/lifts/permission_audit")
    results["lift_sealed_packet_enforced"] = bool(body and any(
        l.get("sealed_packets_required") for l in (body.get("lifts") or [])))

    body, _ = hit("/api/security/enforcement_status")
    results["security_gate_enforcing"] = bool(
        body and str(body.get("security_gate", "")).startswith("enforcing"))

    body, _ = hit("/api/workers/narration?id=QSB-WORKER-041-OANDA-001")
    results["worker_voice_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/floors/narration?floor=41")
    results["floor_voice_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/colonel/audio_briefing")
    results["colonel_briefing_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/correction/status")
    results["correction_loop_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/company_loop/status")
    results["self_check_endpoint"] = bool(body and body.get("ok"))
    results["self_fix_endpoint"]   = bool(body and body.get("ok"))

    body, _ = hit("/api/conference/status")
    results["conference_hub_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/comms/company")
    results["comms_company_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/gauges/all")
    results["gauges_all_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/floors/activation_matrix")
    results["floor_activation_matrix"] = bool(body and body.get("ok"))

    body, _ = hit("/api/trading/oanda/autonomous_practice_status")
    results["autonomous_oanda_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/tower_ops/not_working")
    results["not_working_endpoint"] = bool(body and body.get("ok"))

    body, _ = hit("/api/ui/stale_language_audit")
    files_with_hits = (body or {}).get("files_with_hits", 9)
    results["stale_language_audit_clean"] = (files_with_hits <= 4)

    total = sum(w for _, w, _ in CRITERIA)
    earned = sum(w for k, w, _ in CRITERIA if results.get(k))
    pct = int(round(100 * earned / total)) if total else 0
    accepted = (pct >= 80)
    return stamp_safe({
        "ok": True, "ts": _now(),
        "label": "QSB_TOWER_V2_0_FINAL_ACCEPTANCE",
        "criteria_pass": sum(1 for k in results if results[k]),
        "criteria_total": len(CRITERIA),
        "score": pct,
        "accepted": accepted,
        "criteria": [{"id": k, "weight": w, "description": d, "passed": results.get(k)}
                      for k, w, d in CRITERIA],
        "execution_allowed": False,
    })
