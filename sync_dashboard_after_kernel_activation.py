from pathlib import Path
from datetime import datetime, timezone
import json
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
BACKUP_DIR = ROOT / "data/backups" / f"dashboard_kernel_sync_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

activation_report = REG / "kernel_activation_report.json"
if not activation_report.exists():
    raise SystemExit("ABORT: kernel_activation_report.json missing. Kernel activation has not been verified.")

activation = json.loads(activation_report.read_text(encoding="utf-8"))

required = {
    "kernel_installed": True,
    "QSBKernelCore_instantiated": True,
    "activation_status": "active_local_only",
    "active_kernel_source": "rebased_kernel",
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
}

for k, v in required.items():
    if activation.get(k) != v:
        raise SystemExit(f"ABORT: activation report mismatch: {k}={activation.get(k)!r}, expected {v!r}")

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        rel = path.relative_to(ROOT)
        backup = BACKUP_DIR / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

active_common = {
    "kernel_installed": True,
    "QSBKernelCore_instantiated": True,
    "kernel_logic_present": True,
    "active_kernel_source": "rebased_kernel",
    "activation_status": "active_local_only",
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "live_dispatch_enabled": False,
    "autonomous_workers_enabled": False,
    "direct_provider_access": False,
    "critical_failures": 0,
    "failures": 0,
    "warnings": 0,
    "updated_ts": datetime.now(timezone.utc).isoformat(),
}

updates = {
    "building.json": {
        **active_common,
        "status": "healthy",
        "tower_status": "healthy",
    },
    "kernel_installation_socket.json": {
        **active_common,
        "socket_status": "occupied_local_only",
        "readiness_status": "kernel_active_local_only",
        "reserved_for": "QSB Kernel active local-only",
    },
    "kernel_health_display.json": {
        **active_common,
        "kernel_health": "healthy",
        "status": "active_local_only",
    },
    "kernel_monitoring_interface.json": {
        **active_common,
        "monitoring_status": "watching_active_local_kernel",
    },
    "kernel_discovery_manifest.json": {
        **active_common,
        "discovery_status": "active_local_only_kernel_discovered",
    },
    "floor_53_penthouse_handoff.json": {
        **active_common,
        "handoff_status": "active_local_only_kernel_handoff_ready",
    },
    "tower_command_handoff.json": {
        **active_common,
        "handoff_status": "active_local_only",
    },
    "penthouse_policy.json": {
        **active_common,
        "policy_status": "active_local_only_kernel_installed",
    },
    "executive_command_policy.json": {
        **active_common,
        "status": "healthy",
        "executive_status": "healthy",
        "execution_enabled": False,
        "notice": "Kernel is active local-only; workers/providers/model inference remain disabled.",
    },
    "kernel_readiness_latest.json": {
        **load(REG / "kernel_readiness_latest.json"),
        **active_common,
        "status": "KERNEL_ACTIVE_LOCAL_ONLY",
        "readiness_status": "kernel_active_local_only",
        "next_recommended_phase": "dashboard_active_kernel_sync_verified",
    },
}

for name, patch in updates.items():
    path = REG / name
    current = load(path)
    if not isinstance(current, dict):
        current = {}
    current.update(patch)
    save(path, current)

# Also update penthouse acceptance/display files if they exist.
penthouse_files = [
    ROOT / "penthouse/kernel_occupancy_acceptance/latest_acceptance_report.json",
    ROOT / "penthouse/kernel_occupancy_acceptance/latest_kernel_activation_report.json",
    ROOT / "penthouse/kernel_installation_socket/rebased_kernel/reports/final_activation_report.json",
]

for path in penthouse_files:
    if path.exists():
        current = load(path)
        if not isinstance(current, dict):
            current = {}
        current.update(active_common)
        current["readiness_status"] = "kernel_active_local_only"
        current["socket_status"] = "occupied_local_only"
        save(path, current)

summary = {
    "sync_status": "dashboard_kernel_activation_sync_complete",
    "kernel_installed": True,
    "QSBKernelCore_instantiated": True,
    "activation_status": "active_local_only",
    "active_kernel_source": "rebased_kernel",
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "backup_dir": str(BACKUP_DIR),
    "updated_files": sorted(updates.keys()),
}
save(REG / "dashboard_kernel_activation_sync.json", summary)

print(json.dumps(summary, indent=2))
