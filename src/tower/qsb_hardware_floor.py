"""
QSB Hardware Systems Floor — Audit + Manifest Writer
Phase: EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1

Audits existing floors for a hardware/infrastructure layer. If none
exists, the Hardware Systems Floor is co-located on Floor 35
(Infrastructure Services Department) without overwriting its prior
manifest — the new manifest extends it.

Also stands up Floor 44 (Accounts / PnL) since the previous phase
left it as a vacant directory.

Writes:
  floors/floor_35_infrastructure_services_department/hardware_floor_manifest.json
  floors/floor_44_accounts_department/floor_manifest.json
  data/registries/qsb_hardware_systems_floor.json
  data/registries/qsb_hardware_floor_audit.json
  data/registries/qsb_accounts_floor_state.json

Read-only re: hardware. Never alters system services / drivers /
mounts.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
FLOORS = ROOT / "floors"

P_HW_FLOOR    = REG / "qsb_hardware_systems_floor.json"
P_HW_FLOOR_AUDIT = REG / "qsb_hardware_floor_audit.json"
P_ACCOUNTS    = REG / "qsb_accounts_floor_state.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "read_only": True,
        "real_money_live_trading_enabled": False,
    }


HARDWARE_FLOOR_WORKERS = [
    ("wrk_hardware_systems_manager", "Hardware Systems Manager",
     "Owns the Hardware Systems Floor; tracks every hardware report."),
    ("wrk_cpu_monitor", "CPU Monitor",
     "Reads CPU model / cores / threads / load average. Read-only."),
    ("wrk_gpu_monitor", "GPU Monitor",
     "Reads GPU model, NVIDIA driver, CUDA version, VRAM. Read-only."),
    ("wrk_memory_monitor", "Memory Monitor",
     "Reads RAM total/used/available, swap, memory pressure."),
    ("wrk_storage_monitor", "Storage Monitor",
     "Reads disk usage for /, /vaults/nvme0, /vaults/ai. Read-only."),
    ("wrk_process_monitor", "Process Monitor",
     "Tracks the dashboard server, Ollama, AirLLM venv presence."),
    ("wrk_port_monitor", "Port Monitor",
     "Lists local listening ports (ss -ltn). Read-only."),
    ("wrk_service_monitor", "Service Monitor",
     "Reads service presence (Ollama / dashboard pid file). Never modifies services."),
    ("wrk_performance_adviser", "Performance Adviser",
     "Builds advisory recommendations from memory pressure, VRAM headroom, disk space."),
    ("wrk_resource_accountant", "Resource Accountant",
     "Tracks data/logs and data/backups size growth."),
    ("wrk_kernel_hardware_liaison", "Kernel Hardware Liaison",
     "Routes hardware observatory state to the EQSB Kernel introspection."),
    ("wrk_code_observatory_liaison", "Code Observatory Liaison",
     "Routes code observatory state to the EQSB Kernel introspection."),
]

ACCOUNTS_FLOOR_WORKERS = [
    ("wrk_pnl_accountant", "PnL Accountant",
     "Aggregates realized + unrealized PnL across paper floors."),
    ("wrk_resource_accountant", "Resource Accountant",
     "Tracks data/logs and data/backups size growth."),
    ("wrk_trade_ledger_clerk", "Trade Ledger Clerk",
     "Keeps the paper-trade SQLite ledger consistent."),
    ("wrk_reward_accountant", "Reward Accountant",
     "Posts reward-point ledger entries from workforce scorecards."),
    ("wrk_loss_review_clerk", "Loss Review Clerk",
     "Routes losing paper trades into lesson_review queue."),
]


def audit_existing_hardware_floor():
    """Walk floors.json / floor_name_map / dashboard render model for
    any existing hardware/infrastructure floor."""
    floors_list = _load("floors.json", [])
    name_map_d = _load("qsb_floor_name_map.json", {})
    name_map = (name_map_d.get("name_map") or {}) if isinstance(name_map_d, dict) else {}

    candidates = []
    keywords = ("hardware", "system", "machine", "infrastructure",
                 "performance", "gpu", "cpu", "observatory")
    for entry in floors_list or []:
        if not isinstance(entry, dict):
            continue
        n = entry.get("number")
        if n is None:
            continue
        try: n = int(n)
        except Exception: continue
        label = name_map.get(str(n)) or ""
        for kw in keywords:
            if kw in label.lower():
                candidates.append({"floor": n, "label": label, "matched_keyword": kw})
                break

    # Floor 35 (Infrastructure Services) is the natural home.
    chosen = {"floor": 35,
               "label": name_map.get("35") or "Infrastructure Services Department",
               "reason": ("Floor 35 is the canonical Infrastructure Services "
                           "Department — co-locate Hardware Systems sub-departments here "
                           "without breaking its existing manifest.")}
    audit = {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "kind": "qsb_hardware_floor_audit",
        "generated_ts": _now(),
        "existing_candidates": candidates,
        "dedicated_hardware_floor_already_exists":
            any(c.get("matched_keyword") == "hardware" for c in candidates),
        "chosen_floor": chosen["floor"],
        "chosen_label": chosen["label"],
        "chosen_reason": chosen["reason"],
        "safe_floors_inspected": True,
        "important_floors_protected": [
            "30 (Permissions/Risk)", "31 (Audit/Ledger)",
            "37 (Sim Labs)", "38 (Sandbox)",
            "41 (OANDA)", "42 (Binance)", "43 (Stocks)",
            "44 (Accounts/PnL)", "45 (Recruitment)",
            "53 (Tower Command)",
        ],
    }
    audit.update(_safety_envelope())
    _write_json(P_HW_FLOOR_AUDIT, audit)
    return audit


def write_hardware_floor_manifest():
    base = FLOORS / "floor_35_infrastructure_services_department"
    base.mkdir(parents=True, exist_ok=True)
    # We do NOT overwrite the existing floor_manifest.json; we write a
    # parallel hardware_floor_manifest.json sub-manifest.
    hw_manifest = base / "hardware_floor_manifest.json"
    payload = {
        "ok": True,
        "kind": "hardware_floor_manifest",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "floor_id": "floor_35",
        "co_located_with_department": "Infrastructure Services Department",
        "sub_department": "Hardware Systems Floor",
        "purpose":
            "Read-only machine-room sub-department for CPU, GPU, RAM, disks, "
            "OS, services, ports, dashboard process, Ollama, AirLLM "
            "chamber, storage health, and performance bottlenecks.",
        "read_only": True,
        "advisory_only": True,
        "execution_allowed": False,
        "kernel_required": False,
        "models_required": False,
        "workers": [
            {"worker_id": wid, "display_name": name, "role_description": desc,
             "home_floor": "floor_35_infrastructure_services_department"}
            for wid, name, desc in HARDWARE_FLOOR_WORKERS
        ],
        "observatory_sources": {
            "cpu_profile":   "data/registries/eqsb_cpu_profile.json",
            "gpu_profile":   "data/registries/eqsb_gpu_profile.json",
            "memory_profile":"data/registries/eqsb_memory_profile.json",
            "storage_profile":"data/registries/eqsb_storage_profile.json",
            "os_environment":"data/registries/eqsb_os_environment.json",
            "services_profile":"data/registries/eqsb_services_profile.json",
            "ports_profile": "data/registries/eqsb_ports_profile.json",
            "model_lane_hardware_profile":
                "data/registries/eqsb_model_lane_hardware_profile.json",
            "hardware_understanding":
                "data/registries/eqsb_hardware_understanding.json",
            "performance_advice":
                "data/registries/eqsb_performance_advice.json",
        },
        "dashboard_endpoint": "/api/observatory/hardware",
    }
    payload.update(_safety_envelope())
    _write_json(hw_manifest, payload)
    return payload


def write_hardware_floor_registry():
    payload = {
        "ok": True,
        "kind": "qsb_hardware_systems_floor",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "floor_number": 35,
        "floor_label": "Hardware Systems Floor (co-located with Infrastructure Services Department)",
        "manifest_path":
            "floors/floor_35_infrastructure_services_department/hardware_floor_manifest.json",
        "purpose":
            "Real-data observatory for CPU/GPU/RAM/storage/OS/services/ports/model lanes.",
        "worker_count": len(HARDWARE_FLOOR_WORKERS),
        "workers": [
            {"worker_id": wid, "display_name": name,
             "role_description": desc,
             "home_floor": "floor_35_infrastructure_services_department"}
            for wid, name, desc in HARDWARE_FLOOR_WORKERS
        ],
        "read_only": True,
        "execution_allowed": False,
        "advisory_only": True,
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_FLOOR, payload)
    return payload


def write_accounts_floor_manifest():
    """Replace the floor_44_future_systems_vacant placeholder with a real
    Accounts / PnL Department directory + manifest. We never delete the
    legacy `floor_44_future_systems_vacant` directory in case other
    paths reference it; we add a new sibling directory and tag the old
    one as superseded inside its activation_hook."""
    new_dir = FLOORS / "floor_44_accounts_department"
    new_dir.mkdir(parents=True, exist_ok=True)
    manifest = new_dir / "floor_manifest.json"
    payload = {
        "ok": True,
        "kind": "floor_manifest",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "floor_id": "floor_44",
        "department": "Accounts / PnL Department",
        "version": "1.0",
        "role": "tower_pnl_and_accounting_layer",
        "kernel_required": False,
        "models_required": False,
        "execution_enabled": False,
        "hardwired_providers": False,
        "purpose":
            "Real-data accounting for paper-trade PnL, reward-point ledger, "
            "loss reviews, and resource accounting. Live trading remains disabled.",
        "workers": [
            {"worker_id": wid, "display_name": name, "role_description": desc,
             "home_floor": "floor_44_accounts_department"}
            for wid, name, desc in ACCOUNTS_FLOOR_WORKERS
        ],
        "notice": ("Replaces the floor_44_future_systems_vacant placeholder. "
                    "Accounts/PnL feeds Profit Command via "
                    "qsb_accounts_floor_state.json."),
    }
    payload.update(_safety_envelope())
    _write_json(manifest, payload)

    state = {
        "ok": True,
        "kind": "qsb_accounts_floor_state",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "floor_number": 44,
        "department": "Accounts / PnL Department",
        "manifest_path": "floors/floor_44_accounts_department/floor_manifest.json",
        "worker_count": len(ACCOUNTS_FLOOR_WORKERS),
        "workers": [
            {"worker_id": wid, "display_name": name, "home_floor": "floor_44_accounts_department"}
            for wid, name, _ in ACCOUNTS_FLOOR_WORKERS
        ],
        "previous_state": "floor_44_future_systems_vacant placeholder",
        "current_state": "active",
        "feeds_profit_command": True,
    }
    state.update(_safety_envelope())
    _write_json(P_ACCOUNTS, state)
    return payload


def update_floor_name_map():
    """Stamp canonical names + visual metadata for floors whose source-of-truth
    in floors.json lags behind reality. This file is THE single source of truth
    that both the web dashboard (qsb_tower_2d.js) and the Godot cockpit
    (TowerRenderer.gd, FloorDirectoryPopup.gd) read from."""
    nm = _load("qsb_floor_name_map.json", {})
    if not isinstance(nm, dict):
        nm = {}
    name_map = nm.get("name_map") or {}
    name_map["35"] = name_map.get("35") or "Infrastructure Services Department"
    # Tag floor 35 with a parenthetical so it shows up in /api/unified
    if "Hardware" not in name_map["35"]:
        name_map["35"] = name_map["35"] + " · Hardware Systems Floor"
    name_map["44"] = "Accounts / PnL Department"
    # Commerce wing + real-on-disk floors. F48 and F49 host live local sites
    # (Lumen AI at :8848, Tower Studio at :8849) — see src/tower/floors/.
    # F47 is the Claude embassy (helix-continuous, lineage stamped).
    name_map["46"] = "Commerce Wing"
    name_map["47"] = "Claude Embassy (Wren)"
    name_map["48"] = "Lumen AI"
    name_map["49"] = "Tower Studio"
    name_map["50"] = "ML / RL Classroom"
    nm["name_map"] = name_map
    # ── Visual metadata — shared by both renderers ───────────────────
    # emphasis_floors: render label larger + tinted; embassy + command zone.
    # accent_colors: band/accent color per floor (hex). Renderers may darken/
    #   blend these but the source palette is here. Missing keys → no band.
    # penthouse_floor: which floor number is the penthouse zone (kernel home).
    # roof_floor / ground_floor: structural markers above/below the stack.
    nm["emphasis_floors"] = [23, 25, 28, 30, 41, 42, 43, 46, 47, 48, 49, 50, 53]
    nm["accent_colors"] = {
        "23": "#c780ff",   # AirLLM — purple
        "25": "#99e6f2",   # Recruitment — teal
        "28": "#d94d4d",   # Security — crimson
        "30": "#f26666",   # Guardian — red
        "41": "#66d97f",   # OANDA — green
        "42": "#f2bf4d",   # Binance — gold
        "43": "#80b2ff",   # Stocks — blue
        "46": "#f28cbf",   # Commerce — pink
        "47": "#ff8c33",   # Claude Embassy — amber (Wren)
        "48": "#66f2b2",   # GPT Embassy — mint
        "49": "#8cccff",   # DeepSeek Embassy — pale blue
        "50": "#d9f266",   # ML/RL Classroom — chartreuse
        "53": "#ffd959",   # Tower Command — gold
    }
    nm["penthouse_floor"] = 55
    nm["roof_floor"] = 54
    nm["ground_floor"] = 0
    nm["updated_ts"] = _now()
    nm["phase"] = "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1"
    _write_json(REG / "qsb_floor_name_map.json", nm)
    return nm


def build_all():
    audit = audit_existing_hardware_floor()
    write_hardware_floor_manifest()
    write_hardware_floor_registry()
    write_accounts_floor_manifest()
    update_floor_name_map()
    return {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "hardware_floor": "floor_35 (co-located with Infrastructure Services)",
        "hardware_workers": len(HARDWARE_FLOOR_WORKERS),
        "accounts_floor": "floor_44 (Accounts / PnL Department)",
        "accounts_workers": len(ACCOUNTS_FLOOR_WORKERS),
        "audit_existed_dedicated_hw_floor":
            audit.get("dedicated_hardware_floor_already_exists"),
        **_safety_envelope(),
    }


def main():
    print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
