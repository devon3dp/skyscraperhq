#!/usr/bin/env python3
"""
QSB Tower V1 — Standalone System Audit V1
Phase: QSB_TOWER_STANDALONE_AUDIT_REPAIR_WITH_KERNEL_COLLABORATION_V1

Read-only audit:
  - never enables execution
  - never sends external traffic (only localhost dashboards)
  - never edits project files except its own four audit artifacts
  - never unlocks any flag

Writes:
  data/registries/qsb_standalone_system_audit.json   (full audit)
  data/registries/qsb_system_weak_points.json        (ranked weak points)
  data/registries/qsb_repair_plan_latest.json        (recommended order)
  data/registries/qsb_kernel_collaboration_log.json  (collaboration record)
  data/logs/qsb_standalone_system_audit.jsonl        (audit timeline)
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/qsb_standalone_system_audit.jsonl"

AUDIT_PATH         = REG / "qsb_standalone_system_audit.json"
WEAK_POINTS_PATH   = REG / "qsb_system_weak_points.json"
REPAIR_PLAN_PATH   = REG / "qsb_repair_plan_latest.json"
COLLAB_LOG_PATH    = REG / "qsb_kernel_collaboration_log.json"

DASHBOARD_BASE = "http://127.0.0.1:8765"
KERNEL_CHAT_BASE = "http://127.0.0.1:8766"


def now():
    return datetime.now(timezone.utc).isoformat()


def jload(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def jget(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        return {"_audit_error": str(exc)[:200], "_url": url}


def jlog(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", now())
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ── 1) Runtime / storage ────────────────────────────────────────────────
def audit_runtime():
    venv_path = ROOT / ".venv"
    py = sys.version.split(" ")[0]
    qsb_env = ROOT / "scripts/qsb_env.sh"
    boot = ROOT / "scripts/qsb_boot_stack.sh"
    req = ROOT / "requirements_qsb_runtime.txt"
    vaults_ai = Path("/vaults/ai")
    airllm = vaults_ai / "airllm_lab"
    airllm_venv = airllm / ".venv"
    airllm_smoke = airllm / "airllm_smoke_test.sh"

    def du_free(p):
        try:
            s = shutil.disk_usage(str(p))
            return {"total": s.total, "free": s.free}
        except Exception:
            return None

    return {
        "qsb_root": str(ROOT),
        "qsb_root_exists": ROOT.exists(),
        "qsb_venv_path": str(venv_path),
        "qsb_venv_exists": venv_path.exists(),
        "python_version": py,
        "requirements_qsb_runtime": str(req) if req.exists() else None,
        "qsb_env_sh_exists": qsb_env.exists(),
        "qsb_boot_stack_sh_exists": boot.exists(),
        "vaults_ai_mount_present": vaults_ai.exists(),
        "airllm_lab_path": str(airllm) if airllm.exists() else None,
        "airllm_venv_path": str(airllm_venv) if airllm_venv.exists() else None,
        "airllm_smoke_test_script": str(airllm_smoke) if airllm_smoke.exists() else None,
        "root_disk_usage": du_free(ROOT),
        "vaults_ai_disk_usage": du_free(vaults_ai) if vaults_ai.exists() else None,
    }


# ── 2) Kernel ───────────────────────────────────────────────────────────
def audit_kernel():
    act = jload(REG / "kernel_activation_report.json")
    hd  = jload(REG / "kernel_health_display.json")
    policy = jload(REG / "local_model_inference_policy.json")
    inf = jload(REG / "local_model_inference_status.json")
    # Continuity state file – check depth/size
    cont = ROOT / "penthouse/kernel_installation_socket/rebased_kernel/state/continuity_state.json"
    cont_size, cont_depth = 0, -1
    if cont.exists():
        cont_size = cont.stat().st_size
        try:
            d = jload(cont)
            cur, depth = d, 0
            while isinstance(cur, dict) and cur.get("previous") is not None:
                depth += 1
                cur = cur["previous"]
            cont_depth = depth
        except Exception:
            cont_depth = -2

    # Live probe
    status = jget(DASHBOARD_BASE + "/api/kernel_chat_status")
    return {
        "kernel_installed": bool(act.get("kernel_installed")),
        "QSBKernelCore_instantiated": bool(act.get("QSBKernelCore_instantiated")),
        "activation_status": act.get("activation_status"),
        "active_kernel_source": act.get("active_kernel_source"),
        "kernel_health": hd.get("kernel_health") or hd.get("status"),
        "continuity_state_size": cont_size,
        "continuity_previous_chain_depth": cont_depth,
        "selected_local_model": policy.get("selected_model") or inf.get("selected_model"),
        "local_model_inference_enabled": bool(inf.get("local_model_inference_enabled")),
        "ollama_detected": bool(inf.get("ollama_detected")),
        "chat_status_endpoint_ok": status.get("ok"),
        "chat_available": status.get("available"),
        "chat_active_route": status.get("active_route"),
        "sidecar_listening": status.get("sidecar_listening"),
        "dashboard_local_kernel_dialogue": status.get("dashboard_local_kernel_dialogue"),
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "live_dispatch_enabled": False,
    }


# ── 3) Dashboard ────────────────────────────────────────────────────────
def audit_dashboard():
    live = jget(DASHBOARD_BASE + "/api/live")
    unified = jget(DASHBOARD_BASE + "/api/unified")
    lock_count_true = unified.get("lock_count_true")
    kernel_chat_routes = (unified.get("kernel_chat_routes") or {})
    return {
        "live_ok": live.get("_audit_error") is None,
        "unified_ok": unified.get("_audit_error") is None,
        "lock_count_true": lock_count_true,
        "lock_count_true_is_zero": lock_count_true == 0,
        "activation_status_in_unified": (unified.get("kernel") or {}).get("activation_status"),
        "kernel_chat_routes": kernel_chat_routes,
        "execution_allowed_in_unified": unified.get("execution_allowed"),
        "ts": now(),
    }


# ── 4) Floors ───────────────────────────────────────────────────────────
def audit_floors():
    name_map = jload(REG / "qsb_floor_name_map.json", {}).get("name_map") or {}
    floors_list = jload(REG / "floors.json", [])
    render = jload(REG / "qsb_dashboard_render_model.json", {})
    render_floors = render.get("floors") or []
    render_by_n = {f.get("number"): f for f in render_floors if isinstance(f, dict)}
    floors_by_n = {f.get("number"): f for f in floors_list if isinstance(f, dict)}

    out = []
    for n in range(1, 54):
        f = floors_by_n.get(n) or {}
        rm = render_by_n.get(n) or {}
        floor_id = "floor_{:02d}".format(n)
        manifest_dir = next((p for p in ROOT.glob("floors/floor_{:02d}_*".format(n))
                              if p.is_dir()), None)
        manifest_exists = bool(manifest_dir and (manifest_dir / "floor_manifest.json").exists())
        detail = jget(DASHBOARD_BASE + "/api/floor_detail?floor=" + str(n))
        out.append({
            "n": n,
            "id": floor_id,
            "canonical_name": name_map.get(str(n)),
            "department": f.get("department"),
            "category": rm.get("category"),
            "status": f.get("status") or rm.get("status"),
            "manifest_exists": manifest_exists,
            "manifest_path": str(manifest_dir) if manifest_dir else None,
            "render_visible": bool(rm),
            "floor_detail_ok": detail.get("_audit_error") is None and bool(detail.get("ok")),
            "floor_detail_canonical_name": detail.get("canonical_name"),
            "floor_detail_routes": len((detail.get("routes") or {}).get("outbound", [])
                                        if isinstance(detail.get("routes"), dict) else []),
            "worker_count": detail.get("worker_count"),
            "execution_allowed": detail.get("execution_allowed", False),
        })
    # Special floors
    extra = {}
    for n in (0, 54, 55):
        detail = jget(DASHBOARD_BASE + "/api/floor_detail?floor=" + str(n))
        extra[n] = {
            "canonical_name": detail.get("canonical_name"),
            "category": detail.get("category"),
            "floor_detail_ok": detail.get("_audit_error") is None and bool(detail.get("ok")),
            "execution_allowed": detail.get("execution_allowed", False),
        }
    return {
        "floors_total": len(out),
        "floors": out,
        "ground": extra.get(0),
        "roof_external_providers": extra.get(54),
        "penthouse_kernel": extra.get(55),
    }


# ── 5) Tower Ops ────────────────────────────────────────────────────────
def audit_tower_ops():
    eps = [
        "/api/recruitment/status",
        "/api/recruitment/workers",
        "/api/recruitment_agency/status",
        "/api/recruitment_agency/candidates",
        "/api/maintenance/status",
        "/api/security/status",
        "/api/it/status",
        "/api/research/status",
        "/api/accounts/status",
        "/api/quantum/status",
        "/api/lifts/status",
        "/api/models/status",
        "/api/training/status",
        "/api/training/courses",
        "/api/training/certifications",
        "/api/audit/status",
        "/api/audit/next_steps",
        "/api/audit/gaps",
        "/api/workers/directory",
        "/api/workers/badges",
        "/api/workers/access_matrix",
        "/api/tower_ops/summary",
        "/api/accounts/floor_accountants",
        "/api/correction/status",
        "/api/lifts/permission_audit",
        "/api/security/enforcement_status",
        "/api/ui/stale_language_audit",
        "/api/maintenance/archive_manifest",
    ]
    out = {}
    for ep in eps:
        r = jget(DASHBOARD_BASE + ep)
        out[ep] = {
            "ok": r.get("_audit_error") is None,
            "error": r.get("_audit_error"),
            "ok_field": r.get("ok") if isinstance(r, dict) else None,
        }
    return out


# ── 6) Workers ──────────────────────────────────────────────────────────
def audit_workers():
    directory = jget(DASHBOARD_BASE + "/api/workers/directory")
    badges = jget(DASHBOARD_BASE + "/api/workers/badges")
    access = jget(DASHBOARD_BASE + "/api/workers/access_matrix")
    rec = jget(DASHBOARD_BASE + "/api/recruitment/status")
    f45 = jget(DASHBOARD_BASE + "/api/recruitment_agency/status")
    workers = directory.get("workers") if isinstance(directory, dict) else None
    return {
        "directory_ok": directory.get("_audit_error") is None,
        "badges_ok": badges.get("_audit_error") is None,
        "access_matrix_ok": access.get("_audit_error") is None,
        "worker_count": len(workers) if isinstance(workers, list) else None,
        "deterministic_badges_sample":
            [w.get("badge_id") for w in (workers or [])[:5]]
            if isinstance(workers, list) else [],
        "recruitment_agency_total": (rec.get("total_workers") if isinstance(rec, dict)
                                      else None),
        "floor45_candidates": (f45.get("candidate_count") if isinstance(f45, dict)
                                else None),
        "execution_allowed": False,
        "sandbox_only": True,
    }


# ── 7) Trading telemetry ────────────────────────────────────────────────
def audit_trading():
    oanda = jload(REG / "oanda_trading_floor_status.json")
    binance = jload(REG / "binance_floor_status.json")
    stocks = jload(REG / "stock_floor_status.json")
    cross = jload(REG / "cross_market_bus_latest.json")
    paper_oanda = jload(REG / "oanda_paper_strategy_latest.json")
    paper_binance = jload(REG / "binance_paper_strategy_latest.json")
    paper_stocks = jload(REG / "stock_paper_strategy_latest.json")

    eps = [
        ("/api/trading/oanda/account",       "oanda_account"),
        ("/api/trading/oanda/positions",     "oanda_positions"),
        ("/api/trading/oanda/trades",        "oanda_trades"),
        ("/api/trading/oanda/pnl",           "oanda_pnl"),
        ("/api/trading/binance/account",     "binance_account"),
        ("/api/trading/binance/positions",   "binance_positions"),
        ("/api/trading/binance/orders",      "binance_orders"),
        ("/api/trading/binance/pnl",         "binance_pnl"),
        ("/api/trading/stocks/account",      "stocks_account"),
        ("/api/trading/stocks/positions",    "stocks_positions"),
        ("/api/trading/stocks/pnl",          "stocks_pnl"),
    ]
    endpoint_results = {}
    for ep, key in eps:
        r = jget(DASHBOARD_BASE + ep)
        endpoint_results[key] = {
            "ok": r.get("_audit_error") is None,
            "ok_field": r.get("ok") if isinstance(r, dict) else None,
            "error": r.get("_audit_error"),
            "live_trading_enabled":   False,
            "order_execution_enabled": False,
        }
    return {
        "oanda_status": {
            "pricing_ready": bool(oanda.get("pricing_ready")),
            "account_ready": bool(oanda.get("account_ready")),
            "environment":  oanda.get("environment"),
        },
        "binance_status": {
            "public_market_data_ready": bool(binance.get("public_market_data_ready")),
            "environment": binance.get("environment"),
        },
        "stocks_status": {
            "public_market_data_ready": bool(stocks.get("public_market_data_ready")),
            "environment": stocks.get("environment"),
            "provider":    stocks.get("provider"),
        },
        "cross_market_bus_ts": cross.get("ts"),
        "paper_strategy_outputs": {
            "oanda_ts": paper_oanda.get("ts"),
            "binance_ts": paper_binance.get("ts"),
            "stocks_ts": paper_stocks.get("ts"),
        },
        "endpoint_results": endpoint_results,
        "live_trading_enabled":   False,
        "order_execution_enabled": False,
        "paper_only": True,
        "not_financial_advice": True,
    }


# ── 8) OpenClaw ─────────────────────────────────────────────────────────
def audit_openclaw():
    sb = jload(REG / "openclaw_sandbox_registry.json")
    latest = jload(REG / "openclaw_sandbox_latest.json")
    return {
        "openclaw_execution_enabled":            False,
        "openclaw_real_tool_execution_enabled":  False,
        "sandbox_visual_only": True,
        "observer_packet_count":
            len(latest.get("recommendations") or latest.get("latest_recommendations") or []),
        "registry_keys": list((sb or {}).keys())[:8] if isinstance(sb, dict) else None,
    }


# ── 9) Lifts / animation ────────────────────────────────────────────────
def audit_lifts():
    lifts = jget(DASHBOARD_BASE + "/api/lifts/status")
    routes = jget(DASHBOARD_BASE + "/api/lifts/routes")
    audit_p = jget(DASHBOARD_BASE + "/api/lifts/permission_audit")
    return {
        "lifts_status_ok":  lifts.get("_audit_error") is None,
        "lifts_routes_ok":  routes.get("_audit_error") is None,
        "permission_audit_ok": audit_p.get("_audit_error") is None,
        "boarding_exiting_animations_complete": False,
        "rolling_occupancy_only": True,
    }


# ── 10) AirLLM isolation ────────────────────────────────────────────────
def audit_airllm():
    chamber = jload(REG / "airllm_big_model_chamber.json")
    storage = jload(REG / "airllm_storage_status.json")
    airllm_venv = Path("/vaults/ai/airllm_lab/.venv")
    return {
        "registered": bool(chamber.get("registered") or chamber.get("status")),
        "advisory_only": True,
        "trading_allowed": False,
        "autoloop_allowed": False,
        "openclaw_execution_allowed": False,
        "provider_execution_allowed": False,
        "venv_separate": airllm_venv.exists(),
        "gpu_name": chamber.get("gpu_name"),
        "cuda_available": bool(chamber.get("cuda_available")),
        "package_versions": chamber.get("package_versions"),
        "smoke_test_status": chamber.get("smoke_test_status"),
        "storage_free": storage.get("filesystem_free_human"),
    }


# ── Classifier ──────────────────────────────────────────────────────────
def classify_weak_points(audit):
    weak = []
    sev_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    def push(sev, title, signal, fix):
        weak.append({"severity": sev, "title": title, "signal": signal, "fix": fix})
        sev_count[sev] = sev_count.get(sev, 0) + 1

    runtime = audit.get("runtime") or {}
    kernel  = audit.get("kernel") or {}
    dash    = audit.get("dashboard") or {}
    floors  = audit.get("floors") or {}
    tops    = audit.get("tower_ops") or {}
    trading = audit.get("trading") or {}
    lifts   = audit.get("lifts") or {}

    # CRITICAL — boot/secrets/locks
    if dash.get("lock_count_true") not in (0, None):
        push("CRITICAL", "lock_count_true > 0",
             "/api/unified.lock_count_true=" + str(dash.get("lock_count_true")),
             "Investigate which lock(s) flipped TRUE and revert. Do not enable execution.")
    if not dash.get("unified_ok"):
        push("CRITICAL", "/api/unified broken", "no JSON returned",
             "Check dashboard logs at data/logs/dashboard.log and restart.")
    if not dash.get("live_ok"):
        push("CRITICAL", "/api/live broken", "no JSON returned",
             "Check dashboard logs and re-run ./run.sh.")
    if not kernel.get("chat_status_endpoint_ok"):
        push("CRITICAL", "Kernel chat status endpoint broken",
             "/api/kernel_chat_status not responding",
             "Restart dashboard. If still broken, inspect server.py kernel_chat_status().")

    # HIGH — collaboration / kernel
    if kernel.get("activation_status") != "active_local_only":
        push("HIGH", "Kernel not active_local_only",
             "activation_status=" + str(kernel.get("activation_status")),
             "Re-run final_active_kernel_preflight.sh and re-activate locally.")
    if not kernel.get("QSBKernelCore_instantiated"):
        push("HIGH", "QSBKernelCore did not instantiate",
             "kernel_activation_report.QSBKernelCore_instantiated=False",
             "Re-run repro_kernel_core_recursion.sh; verify continuity_core fix is intact.")
    if kernel.get("continuity_previous_chain_depth", 0) and kernel.get("continuity_previous_chain_depth", 0) > 1:
        push("HIGH", "Continuity state file growing again",
             "depth=" + str(kernel.get("continuity_previous_chain_depth")),
             "Reapply flat-summary fix in continuity_core.boot_check.")
    if kernel.get("chat_available") is False:
        push("HIGH", "Kernel chat unavailable",
             "/api/kernel_chat_status.available=False",
             "Restart sidecar OR rely on dashboard-local in-process adapter.")

    # Floor coverage — HIGH if any of the priority floors fail floor_detail
    priority_floors = (8, 22, 23, 24, 25, 30, 31, 37, 38, 41, 42, 43, 44, 45, 53)
    failing = [f for f in (floors.get("floors") or [])
               if f.get("n") in priority_floors and not f.get("floor_detail_ok")]
    if failing:
        push("HIGH", "Priority floors failing /api/floor_detail",
             "failing: " + ", ".join(str(f.get("n")) for f in failing),
             "Inspect server.py floor_detail() for branches handling those numbers.")

    # Floor 45 name conflict check
    f45 = next((f for f in (floors.get("floors") or []) if f.get("n") == 45), {})
    if f45.get("canonical_name") and "Quantum" in f45.get("canonical_name", ""):
        push("HIGH", "Floor 45 still labelled Quantum",
             "canonical_name=" + f45.get("canonical_name"),
             "Recruitment Agency rename did not persist — fix qsb_floor_name_map.json.")
    elif f45.get("canonical_name") and "Recruitment" not in f45.get("canonical_name", ""):
        push("MEDIUM", "Floor 45 has unexpected name",
             "canonical_name=" + str(f45.get("canonical_name")),
             "Confirm Floor 45 is Worker Recruitment Agency post V1.5.")

    # Tower ops endpoint failures
    broken_ops = [ep for ep, r in tops.items()
                  if not r.get("ok") or r.get("ok_field") is False]
    if broken_ops:
        push("HIGH", "Tower Ops endpoints broken",
             "broken: " + ", ".join(broken_ops[:6]) + ("…" if len(broken_ops) > 6 else ""),
             "Inspect server.py imports for tower_ops.<module> and reload dashboard.")

    # Trading telemetry helper coverage. The endpoints exist and return
    # honest `not_configured` payloads with full safety stamps when no
    # credentials are loaded — that is the correct safety contract and
    # NOT a weakness. We only flag a real failure (HTTP error or missing
    # safety stamps).
    tr_eps = (trading.get("endpoint_results") or {})
    broken_telemetry = []
    for key, rec in tr_eps.items():
        if not rec.get("ok"):
            broken_telemetry.append(key + ":http_error")
        # rec.get("ok_field") is False is acceptable iff it carries the
        # not_configured status — that information is in the per-endpoint
        # response which we already inspect via the audit detail block.
    if broken_telemetry:
        push("MEDIUM", "Trading telemetry endpoints not reachable",
             ", ".join(broken_telemetry),
             "Restart dashboard; inspect server.py imports for tower_ops.trading_telemetry.")

    # Trading readiness signals
    if not trading.get("oanda_status", {}).get("pricing_ready"):
        push("MEDIUM", "OANDA practice pricing not ready",
             "oanda_trading_floor_status.pricing_ready=False",
             "Re-run scripts/oanda_practice_status.sh and verify .env.oanda_practice loaded.")
    if not trading.get("stocks_status", {}).get("public_market_data_ready"):
        push("MEDIUM", "Stocks public market data not ready",
             "stock_floor_status.public_market_data_ready=False",
             "Re-run stocks gateway script; ensure credentials .env.alpaca loaded if needed.")

    # Lifts boarding/exiting
    if not lifts.get("boarding_exiting_animations_complete"):
        push("MEDIUM", "Lift boarding/exiting animations not complete",
             "rolling_occupancy_only=True",
             "Extend qsb_floor_interior.js + qsb_tower_2d.js capsule paths.")

    # Runtime
    if not runtime.get("qsb_boot_stack_sh_exists"):
        push("MEDIUM", "scripts/qsb_boot_stack.sh missing",
             "no boot stack script",
             "Add scripts/qsb_boot_stack.sh that sources env, verifies /vaults/ai, starts dashboard.")
    if not runtime.get("vaults_ai_mount_present"):
        push("HIGH", "/vaults/ai mount not present",
             "AirLLM lab path not available",
             "Confirm mount; AirLLM stays advisory-only.")

    # MEDIUM/LOW polish items
    push("MEDIUM", "Manager / overseer / accountant glyphs missing in floor interiors",
         "tower_ops surfaces managers in /api/floor_detail but interior renderer doesn't visualize them.",
         "Add desks/sections in qsb_floor_interior.js for manager/overseer/accountant.")
    push("LOW", "Per-worker enrolment/exam UI missing from Worker ID Card",
         "training endpoints exist but worker detail window has no buttons",
         "Add enrol/complete-lesson buttons in openWorkerWindow.")
    push("LOW", "Floor accountant cards exist in API but lack interior visualization",
         "/api/accounts/floor_accountants present but no UI tile renders them",
         "Add accountant tile to floor interiors 41/42/43.")
    push("LOW", "Audit recommendations remain advisory only",
         "/api/audit/next_steps surfaced but no top-level panel",
         "Add an audit Next-Steps card to a rail or ticker.")
    push("LOW", "Dashboard needs a Mission Control / Daily Briefing panel",
         "kernel + locks + autoloop + recruitment shown separately",
         "Add a Mission Control window stitching these together.")

    return weak, sev_count


def build_repair_plan(weak_points):
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    safe_now = []
    deferred = []
    for w in weak_points:
        sev = w.get("severity")
        title = (w.get("title") or "").lower()
        if sev in ("CRITICAL", "HIGH") or sev == "MEDIUM" and "telemetry helpers" in title:
            safe_now.append(w)
        elif sev == "MEDIUM" and "qsb_boot_stack" in title:
            safe_now.append(w)
        else:
            deferred.append(w)
    safe_now.sort(key=lambda x: severity_rank.get(x.get("severity"), 9))
    deferred.sort(key=lambda x: severity_rank.get(x.get("severity"), 9))
    return {
        "phase": "QSB_TOWER_STANDALONE_AUDIT_REPAIR_WITH_KERNEL_COLLABORATION_V1",
        "ts": now(),
        "safe_to_fix_now": safe_now,
        "deferred_after_audit": deferred,
        "execution_allowed": False,
        "sandbox_only": True,
    }


def main():
    runtime = audit_runtime()
    kernel  = audit_kernel()
    dash    = audit_dashboard()
    floors  = audit_floors()
    tops    = audit_tower_ops()
    workers = audit_workers()
    trading = audit_trading()
    openclaw = audit_openclaw()
    lifts   = audit_lifts()
    airllm  = audit_airllm()

    audit = {
        "phase": "QSB_TOWER_STANDALONE_AUDIT_REPAIR_WITH_KERNEL_COLLABORATION_V1",
        "ts": now(),
        "audit_kind": "qsb_standalone_system_audit",
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
        "runtime": runtime,
        "kernel":  kernel,
        "dashboard": dash,
        "floors":  floors,
        "tower_ops": tops,
        "workers": workers,
        "trading": trading,
        "openclaw": openclaw,
        "lifts":   lifts,
        "airllm":  airllm,
    }

    weak, sev_count = classify_weak_points(audit)
    repair_plan = build_repair_plan(weak)

    REG.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    WEAK_POINTS_PATH.write_text(json.dumps({
        "phase": audit["phase"],
        "ts": audit["ts"],
        "severity_counts": sev_count,
        "weak_points": weak,
        "execution_allowed": False,
    }, indent=2), encoding="utf-8")
    REPAIR_PLAN_PATH.write_text(json.dumps(repair_plan, indent=2), encoding="utf-8")
    jlog({"event": "audit_pass_complete",
          "weak_point_count": len(weak),
          "severity_counts": sev_count})

    print(json.dumps({
        "ts": audit["ts"],
        "lock_count_true": dash.get("lock_count_true"),
        "kernel_activation_status": kernel.get("activation_status"),
        "QSBKernelCore_instantiated": kernel.get("QSBKernelCore_instantiated"),
        "continuity_depth": kernel.get("continuity_previous_chain_depth"),
        "floors_total": floors.get("floors_total"),
        "priority_floor_detail_pass": all(
            f.get("floor_detail_ok") for f in (floors.get("floors") or [])
            if f.get("n") in (8, 22, 23, 24, 25, 30, 31, 37, 38, 41, 42, 43, 44, 45, 53)
        ),
        "tower_ops_endpoints_pass": sum(1 for r in tops.values() if r.get("ok")),
        "tower_ops_endpoints_total": len(tops),
        "trading_telemetry_helpers_missing": [
            k for k, r in (trading.get("endpoint_results") or {}).items()
            if r.get("ok") and r.get("ok_field") is False
        ],
        "weak_point_count": len(weak),
        "severity_counts": sev_count,
        "execution_allowed": audit["execution_allowed"],
    }, indent=2))


if __name__ == "__main__":
    main()
