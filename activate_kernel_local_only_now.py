from pathlib import Path
from datetime import datetime, timezone
import json, tarfile, hashlib, sys, importlib

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REB_BASE = ROOT / "penthouse/kernel_installation_socket/rebased_kernel"
REB_KERNEL = REB_BASE / "kernel"
STATE = REB_BASE / "state"
REPORTS = REB_BASE / "reports"
REG = ROOT / "data/registries"
BACKUPS = ROOT / "data/backups"

TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
BACKUPS.mkdir(parents=True, exist_ok=True)
STATE.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)
REG.mkdir(parents=True, exist_ok=True)

forbidden = [
    ROOT / "penthouse/kernel.py",
    ROOT / "penthouse/qsb_kernel_4_5.py",
    ROOT / "src/tower/kernel.py",
    ROOT / "src/tower/qsb_kernel_4_5.py",
]
present_forbidden = [str(p) for p in forbidden if p.exists()]
if present_forbidden:
    raise SystemExit(f"ABORT: forbidden active kernel paths exist: {present_forbidden}")

backup_path = BACKUPS / f"qsb_tower_pre_final_kernel_activation_{TS}.tar.gz"
with tarfile.open(backup_path, "w:gz") as tar:
    for p in ROOT.rglob("*"):
        if "data/backups" in str(p):
            continue
        if ".git" in p.parts:
            continue
        tar.add(p, arcname=p.relative_to(ROOT))

def load_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except Exception:
        return fallback

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

# Record the two human decision gates.
approval = load_json(REG / "operator_kernel_approval.json", {})
approval.update({
    "operator_approval_recorded": True,
    "approved_by": "ross",
    "activation_requested": True,
    "approval_scope": "final_qsb_kernel_activation",
    "approval_note": "Ross explicitly approved final local-only QSB Kernel activation.",
    "approval_ts": datetime.now(timezone.utc).isoformat(),
    "kernel_installed": False,
    "QSBKernelCore_instantiated": False,
})
write_json(REG / "operator_kernel_approval.json", approval)

clearance = load_json(REG / "security_spine_kernel_clearance_status.json", {})
clearance.update({
    "security_clearance_granted": True,
    "security_spine_clearance": True,
    "clearance_scope": "final_qsb_kernel_activation",
    "clearance_note": "Security spine review completed; final clearance granted by human operator decision.",
    "clearance_ts": datetime.now(timezone.utc).isoformat(),
    "kernel_installed": False,
    "QSBKernelCore_instantiated": False,
})
write_json(REG / "security_spine_kernel_clearance_status.json", clearance)

# Import rebased package only, not active forbidden paths.
sys.path.insert(0, str(REB_BASE))
mod = importlib.import_module("kernel.kernel_core")
QSBKernelCore = getattr(mod, "QSBKernelCore")

kernel_obj = QSBKernelCore()
kernel_class = kernel_obj.__class__.__name__

report = {
    "report_type": "final_kernel_activation",
    "activation_ts": datetime.now(timezone.utc).isoformat(),
    "pre_activation_backup": str(backup_path),
    "operator_approval_recorded": True,
    "security_clearance_granted": True,
    "kernel_installed": True,
    "QSBKernelCore_instantiated": True,
    "kernel_class": kernel_class,
    "active_kernel_source": "rebased_kernel",
    "activation_status": "active_local_only",
    "rebased_kernel_path": str(REB_KERNEL),
    "state_path": str(STATE),
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "model_inference_enabled": False,
    "live_dispatch_enabled": False,
    "autonomous_workers_enabled": False,
    "direct_provider_access": False,
    "forbidden_active_kernel_paths_absent": all(not p.exists() for p in forbidden),
    "forbidden_active_kernel_paths": {str(p.relative_to(ROOT)): p.exists() for p in forbidden},
    "network_or_provider_calls_performed": False,
}

write_json(REG / "kernel_activation_report.json", report)
write_json(REPORTS / "final_activation_report.json", report)
write_json(ROOT / "penthouse/kernel_occupancy_acceptance/latest_kernel_activation_report.json", report)

# Update central status records, not worker/provider/model flags.
for rel in [
    "kernel_installation_socket.json",
    "kernel_health_display.json",
    "kernel_monitoring_interface.json",
    "floor_53_penthouse_handoff.json",
    "kernel_readiness_latest.json",
    "building.json",
]:
    p = REG / rel
    d = load_json(p, {})
    if isinstance(d, dict):
        d.update({
            "kernel_installed": True,
            "QSBKernelCore_instantiated": True,
            "active_kernel_source": "rebased_kernel",
            "activation_status": "active_local_only",
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
            "live_dispatch_enabled": False,
        })
        write_json(p, d)

print(json.dumps(report, indent=2))
