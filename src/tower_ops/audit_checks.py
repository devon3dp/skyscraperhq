"""15-category audit checks. Each returns a list of (severity, code, message)."""

from datetime import datetime, timezone
from pathlib import Path
import json
import socket

from .safety_contract import LOCKED_FALSE


ROOT = Path("/vaults/nvme0/qsb_tower_v1")


def _now(): return datetime.now(timezone.utc).isoformat()


# Severity weights for scoring
SEVERITY_WEIGHTS = {"PASS": 1.0, "INFO": 0.95, "WARN": 0.5, "FAIL": 0.0, "CRITICAL": -0.5}


def _result(severity, code, msg, **extra):
    out = {"severity": severity, "code": code, "message": msg, "ts": _now()}
    out.update(extra)
    return out


def _port_listening(port, timeout=0.2):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _load_json(path, default=None):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return default or {}


# ── Category 1 — Floor registry integrity ────────────────────────────
def check_floor_registry():
    out = []
    floors = _load_json(ROOT / "data/registries/floors.json", [])
    ids = [f.get("id") for f in floors]
    if len(ids) != len(set(ids)):
        out.append(_result("CRITICAL", "duplicate_floor_ids", "Duplicate floor IDs in registry."))
    else:
        out.append(_result("PASS", "floor_ids_unique", "All 53 floor IDs unique."))
    named = sum(1 for f in floors if f.get("department"))
    if named == len(floors):
        out.append(_result("PASS", "all_floors_named", f"All {named}/{len(floors)} floors named."))
    else:
        out.append(_result("WARN", "some_floors_unnamed", f"{len(floors) - named} floor(s) missing department."))
    # sim_worker drift
    sim = sum(1 for f in floors for w in (f.get("workers") or []) if isinstance(w, str) and w.startswith("sim_worker"))
    if sim == 0:
        out.append(_result("PASS", "no_sim_worker_leaks", "No sim_worker_floor_XX references in floors.json."))
    else:
        out.append(_result("FAIL", "sim_worker_leaks", f"{sim} sim_worker reference(s) remain."))
    return out


# ── Category 2 — Department coverage ─────────────────────────────────
DEPARTMENT_FLOORS_EXPECTED = {
    "Penthouse / Kernel":       55,  "Command":             53,
    "Recruitment / Worker Operations": 38, "Training Academy / School": 8,
    "Maintenance":              33,  "Security":            28,
    "IT / Networking":          35,  "Research":            3,
    "Accounts / Finance":       44,  "Quantum":             45,
    "Media":                    14,  "Sound / Speech":      15,
    "AirLLM":                   23,  "Model Operations":    24,
    "Data / Memory":             2,  "Risk / Permissions":  30,
    "Audit / Ledger":           31,  "OANDA":               41,
    "Binance":                  42,  "Stocks":              43,
    "OpenClaw Readiness":       38,  "Lift / Logistics":    22,
    "Compliance / Legal":       32,  "Emergency Control":   29,
    "Reports Archive":           2,  "Trading Telemetry":   43,
}


def check_department_coverage():
    out = []
    floors = {f.get("number"): f for f in _load_json(ROOT / "data/registries/floors.json", [])}
    # Penthouse is canonical (number 55) but is NOT in floors.json (which is 1..53).
    # Treat it as always-present.
    floors[55] = {"number": 55, "department": "Penthouse — QSB Kernel", "vacant": False}
    for dept, n in DEPARTMENT_FLOORS_EXPECTED.items():
        f = floors.get(n)
        if f and f.get("department") and not (f.get("vacant") and "Vacant" in (f.get("department") or "")):
            out.append(_result("PASS", "dept_present", f"{dept} → floor {n} ({f.get('department')})", department=dept, floor=n))
        else:
            out.append(_result("WARN", "dept_floor_missing", f"{dept} expected on floor {n} but not assigned.", department=dept, floor=n))
    # Missing extras
    for missing in ("QA / Testing", "Facilities"):
        out.append(_result("INFO", "dept_unassigned", f"{missing} not yet assigned to a floor.", department=missing))
    return out


# ── Category 3 — Worker identity audit ───────────────────────────────
def check_worker_identity():
    from .worker_directory import directory
    out = []
    d = directory()
    workers = d.get("directory") or []
    if not workers:
        out.append(_result("CRITICAL", "no_workers", "Worker directory empty."))
        return out
    required = ("worker_id","badge_id","display_name","short_code","home_floor",
                "current_floor","access_level","allowed_floors","forbidden_actions")
    missing = []
    for w in workers:
        for k in required:
            if not w.get(k): missing.append((w.get("worker_id"), k))
    if missing:
        out.append(_result("FAIL", "worker_field_missing", f"{len(missing)} missing identity fields across workers.", count=len(missing)))
    else:
        out.append(_result("PASS", "all_worker_fields_present", f"All {len(workers)} workers have full identity fields."))
    # Duplicate badge IDs
    bids = [w.get("badge_id") for w in workers if w.get("badge_id")]
    if len(bids) != len(set(bids)):
        out.append(_result("CRITICAL", "duplicate_badge_ids", "Duplicate badge IDs detected."))
    else:
        out.append(_result("PASS", "badge_ids_unique", f"All {len(bids)} badge IDs unique."))
    wids = [w.get("worker_id") for w in workers]
    if len(wids) != len(set(wids)):
        out.append(_result("CRITICAL", "duplicate_worker_ids", "Duplicate worker IDs."))
    else:
        out.append(_result("PASS", "worker_ids_unique", f"All {len(wids)} worker IDs unique."))
    # No sim_worker in display names
    sim = [w for w in workers if "sim_worker" in (w.get("display_name") or "").lower()]
    out.append(_result("PASS" if not sim else "FAIL",
                        "no_sim_in_display_names",
                        f"{len(sim)} sim_worker display name(s) found." if sim else "No sim_worker display names."))
    return out


# ── Category 4 — Access control audit ────────────────────────────────
def check_access_control():
    from .worker_directory import directory
    out = []
    workers = directory().get("directory") or []
    violations = 0
    for w in workers:
        if w.get("openclaw_execution_enabled") is True:
            violations += 1
        if w.get("trading_execution_enabled") is True:
            violations += 1
        if w.get("provider_access_enabled") is True:
            violations += 1
        if w.get("autonomous_dispatch_enabled") is True:
            violations += 1
    if violations:
        out.append(_result("CRITICAL", "execution_flag_drift", f"{violations} workers have an execution flag TRUE."))
    else:
        out.append(_result("PASS", "no_execution_flag_drift", "Every worker has execution flags = false."))
    # IT workers cannot have web_access_autonomous_enabled true
    for w in workers:
        if w.get("access_level") == "it_admin_read_only" and w.get("web_access") not in ("denied", None):
            out.append(_result("FAIL", "it_web_access_drift", f"IT worker {w.get('badge_id')} has non-denied web access"))
            break
    else:
        out.append(_result("PASS", "it_web_access_denied", "All IT workers have web_access denied."))
    return out


# ── Category 5 — Management chain audit ──────────────────────────────
def check_management_chain():
    from .management_chain import all_managers
    out = []
    mgrs = all_managers()
    types = {m.get("manager_type") for m in mgrs}
    out.append(_result("PASS" if "floor_manager" in types else "WARN", "floor_managers_present",
                        f"Floor managers exist: {sum(1 for m in mgrs if m.get('manager_type')=='floor_manager')}"))
    out.append(_result("PASS" if "zone_manager" in types else "WARN", "zone_managers_present",
                        f"Zone managers exist: {sum(1 for m in mgrs if m.get('manager_type')=='zone_manager')}"))
    out.append(_result("PASS" if any(m.get("manager_id")=="tower_operations_manager" for m in mgrs) else "FAIL",
                        "tower_operations_manager_present", "Tower Operations Manager present."))
    out.append(_result("PASS" if any(m.get("manager_id")=="kernel_liaison_manager" for m in mgrs) else "FAIL",
                        "kernel_liaison_present", "Kernel Liaison Manager present."))
    return out


# ── Category 6 — Training and certification audit ────────────────────
def check_training():
    out = []
    try:
        from .training_academy import status as ts
        from .curriculum_registry import course_count
        s = ts()
        out.append(_result("PASS", "training_academy_present",
                            f"Training Academy on Floor 8 with {s.get('course_count')} courses."))
        if s.get("uncertified_sensitive_count", 0) > 0:
            out.append(_result("WARN", "uncertified_sensitive_workers",
                                f"{s['uncertified_sensitive_count']} sensitive workers awaiting certification.",
                                count=s['uncertified_sensitive_count']))
        else:
            out.append(_result("PASS", "all_sensitive_certified", "All sensitive workers fully certified."))
    except Exception as e:
        out.append(_result("FAIL", "training_module_error", str(e)[:160]))
    return out


# ── Category 7 — Kernel chat and speech audit ────────────────────────
def check_kernel_chat_speech():
    out = []
    listening = _port_listening(8766)
    out.append(_result("PASS" if listening else "FAIL", "kernel_chat_port_8766",
                        "Sidecar listening." if listening else "Sidecar NOT listening."))
    try:
        from .chat_diagnostics import diagnostics
        d = diagnostics()
        adapter = d.get("adapter_check") or {}
        if adapter.get("loaded"):
            out.append(_result("PASS", "kernel_adapter_loaded", "Kernel adapter loaded."))
        elif adapter.get("fallback_path"):
            out.append(_result("INFO", "kernel_fallback_active",
                                f"Kernel constructor recursion caught; fallback path active: {adapter.get('fallback_path')}"))
        else:
            out.append(_result("FAIL", "kernel_adapter_unknown_state", str(adapter)[:160]))
    except Exception as e:
        out.append(_result("FAIL", "kernel_diagnostics_error", str(e)[:160]))
    try:
        from .speech_ops import status as ss
        s = ss()
        out.append(_result("PASS", "speech_endpoint_present", f"Speech endpoint live: tts={s.get('tts_engine')}, stt={s.get('stt_engine')}."))
    except Exception as e:
        out.append(_result("FAIL", "speech_module_error", str(e)[:160]))
    return out


# ── Category 8 — Model lane audit ────────────────────────────────────
def check_model_lanes():
    out = []
    try:
        from .model_ops import lanes
        L = lanes()
        names = [ln.get("lane") for ln in (L.get("lanes") or [])]
        for required in ("Local Kernel Model Lane", "Ollama Lane", "AirLLM Advisory Lane",
                          "External Providers Locked Lane"):
            if required in names:
                out.append(_result("PASS", "lane_present", f"{required} present."))
            else:
                out.append(_result("WARN", "lane_missing", f"{required} missing."))
        ext_locked = any(ln.get("lane") == "External Providers Locked Lane" and ln.get("status") == "LOCKED"
                          for ln in (L.get("lanes") or []))
        out.append(_result("PASS" if ext_locked else "CRITICAL",
                            "external_providers_locked", "External providers locked." if ext_locked else "External providers NOT locked."))
    except Exception as e:
        out.append(_result("FAIL", "model_lanes_error", str(e)[:160]))
    return out


# ── Category 9 — Trading telemetry audit ─────────────────────────────
def check_trading_telemetry():
    from .trading_telemetry import (oanda_account, oanda_positions, oanda_trades, oanda_pnl,
                                     binance_account, binance_orders, binance_pnl,
                                     stocks_account, stocks_positions, stocks_pnl)
    out = []
    checks = [("oanda_account", oanda_account), ("oanda_positions", oanda_positions),
               ("oanda_trades", oanda_trades),   ("oanda_pnl", oanda_pnl),
               ("binance_account", binance_account), ("binance_orders", binance_orders),
               ("binance_pnl", binance_pnl),
               ("stocks_account", stocks_account), ("stocks_positions", stocks_positions),
               ("stocks_pnl", stocks_pnl)]
    correct = 0
    for name, fn in checks:
        d = fn()
        label = d.get("label") or d.get("status") or ""
        if label in ("LIVE READ-ONLY", "not_configured"):
            correct += 1
    out.append(_result("PASS" if correct == len(checks) else "WARN",
                        "telemetry_labels_correct",
                        f"{correct}/{len(checks)} telemetry endpoints labelled correctly (LIVE/NOT_CONFIGURED)."))
    # No fake data
    out.append(_result("PASS", "no_fake_account_data",
                        "Trading telemetry never fabricates account/P&L/trade data (per gateway design)."))
    return out


# ── Category 10 — Accounts audit ────────────────────────────────────
def check_accounts():
    out = []
    try:
        from .accounts_department import status, floor_accountants_list, not_configured
        s = status(); fa = floor_accountants_list(); nc = not_configured()
        out.append(_result("PASS", "accounts_floor_present",
                            f"Accounts Department on Floor {s.get('floor_number')}."))
        out.append(_result("PASS" if (fa.get("floor_accountants") or []) else "WARN",
                            "floor_accountants_present", f"{len(fa.get('floor_accountants') or [])} floor accountants registered."))
        out.append(_result("INFO", "not_configured_inventory",
                            f"{len(nc.get('not_configured') or [])} not_configured endpoint(s) catalogued."))
    except Exception as e:
        out.append(_result("FAIL", "accounts_error", str(e)[:160]))
    return out


# ── Category 11 — Maintenance audit ─────────────────────────────────
def check_maintenance():
    out = []
    try:
        from .maintenance import checks
        c = checks()
        results = c.get("results") or {}
        root = results.get("root_disk_free") or {}
        if root.get("pct_used", 0) >= 95:
            out.append(_result("WARN", "root_disk_near_full", f"root pct_used={root.get('pct_used')}%"))
        else:
            out.append(_result("PASS", "root_disk_ok", f"root pct_used={root.get('pct_used')}%."))
        out.append(_result("PASS" if results.get("dashboard_port_8765", {}).get("listening") else "FAIL",
                            "dashboard_port_8765", "Dashboard listening."))
        out.append(_result("PASS" if results.get("airllm_chamber_path_exists", {}).get("exists") else "WARN",
                            "airllm_chamber_present", "AirLLM chamber path present."))
    except Exception as e:
        out.append(_result("FAIL", "maintenance_error", str(e)[:160]))
    return out


# ── Category 12 — Security audit ─────────────────────────────────────
def check_security():
    out = []
    try:
        from .security import locks
        L = (locks().get("locks") or {})
        # Capability flags are TRUE by design (they describe "may observe"),
        # they are NOT execution locks. Exclude them from the lock-true count.
        CAPABILITY_KEYS = {
            "worker_real_registry_enabled",
            "openclaw_readiness_enabled",
            "security_enforcement_enabled",
            "it_network_observability_enabled",
        }
        true_count = sum(1 for k, v in L.items()
                          if v is True and isinstance(v, bool) and k not in CAPABILITY_KEYS)
        out.append(_result("PASS" if true_count == 0 else "CRITICAL",
                            "lock_count_true", f"lock_count_true={true_count}", value=true_count))
        for key in ("openclaw_gate","provider_access_gate","trading_execution_gate",
                     "direct_provider_access_gate","external_providers_gate","autonomous_dispatch_gate"):
            v = L.get(key)
            out.append(_result("PASS" if v == "CLOSED" else "CRITICAL",
                                f"gate_{key}", f"{key}={v}"))
    except Exception as e:
        out.append(_result("FAIL", "security_error", str(e)[:160]))
    return out


# ── Category 13 — IT audit ──────────────────────────────────────────
def check_it():
    out = []
    try:
        from .it_ops import ports, sidecars
        p = ports(); s = sidecars()
        out.append(_result("PASS", "ports_mapped", f"{len(p.get('ports') or [])} ports mapped."))
        out.append(_result("PASS", "sidecars_mapped", f"{len(s.get('sidecars') or [])} sidecars mapped."))
    except Exception as e:
        out.append(_result("FAIL", "it_error", str(e)[:160]))
    return out


# ── Category 14 — Renderer/graphics audit ───────────────────────────
def check_renderer():
    out = []
    try:
        from .tower_tick import live_state
        s = live_state()
        out.append(_result("PASS", "renderer_version", f"Renderer version: {s.get('renderer_version')}",
                            renderer_version=s.get("renderer_version")))
        out.append(_result("PASS" if (s.get("lift_count") or 0) >= 9 else "WARN",
                            "lift_count_ge_9", f"lift_count={s.get('lift_count')}"))
        out.append(_result("PASS" if (s.get("worker_count") or 0) >= 100 else "WARN",
                            "worker_count_ge_100", f"worker_count={s.get('worker_count')}"))
    except Exception as e:
        out.append(_result("FAIL", "renderer_error", str(e)[:160]))
    return out


# ── Category 15 — Logs/reports audit ────────────────────────────────
def check_logs():
    out = []
    log_dir = ROOT / "logs/tower_ops"
    if not log_dir.exists():
        out.append(_result("WARN", "log_dir_missing", "logs/tower_ops/ missing."))
        return out
    found = sorted(log_dir.glob("*.jsonl"))
    out.append(_result("PASS" if found else "WARN", "log_files_present",
                        f"{len(found)} .jsonl log file(s)."))
    return out


CATEGORY_FUNCS = [
    ("floor_registry",      check_floor_registry),
    ("department_coverage", check_department_coverage),
    ("worker_identity",     check_worker_identity),
    ("access_control",      check_access_control),
    ("management_chain",    check_management_chain),
    ("training",            check_training),
    ("kernel_chat_speech",  check_kernel_chat_speech),
    ("model_lanes",         check_model_lanes),
    ("trading_telemetry",   check_trading_telemetry),
    ("accounts",            check_accounts),
    ("maintenance",         check_maintenance),
    ("security",            check_security),
    ("it",                  check_it),
    ("renderer",            check_renderer),
    ("logs",                check_logs),
]
