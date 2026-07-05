"""Correction actions — the safe-to-apply repair recipes for the correction loop.

Each action returns a structured result dict. None of these actions toggles an
execution gate. None creates real workers. None calls an external provider.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
ARCHIVE_ROOT = ROOT / "archive"


def _now(): return datetime.now(timezone.utc).isoformat()


def _archive_dir():
    base = ARCHIVE_ROOT / "20260608_v15_cleanup"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_move(src: Path, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = dest_dir / f"{src.name}.dup_{ts}"
    shutil.move(str(src), str(dest))
    return str(dest)


def archive_dashboard_backups():
    """Move every src/dashboard/*.backup_* into the archive."""
    target = _archive_dir() / "dashboard_backups"
    moved = []
    for p in sorted((ROOT / "src/dashboard").glob("*.backup*")):
        moved.append({"from": str(p), "to": _safe_move(p, target)})
    return {"action": "archive_dashboard_backups",
            "moved_count": len(moved), "moved": moved, "ts": _now()}


def archive_tower_backups():
    target = _archive_dir() / "tower_backups"
    moved = []
    for p in sorted((ROOT / "src/tower").glob("*.backup*")):
        moved.append({"from": str(p), "to": _safe_move(p, target)})
    return {"action": "archive_tower_backups",
            "moved_count": len(moved), "moved": moved, "ts": _now()}


def archive_registry_backups():
    target = _archive_dir() / "registry_backups"
    moved = []
    reg = ROOT / "data/registries"
    for p in sorted(reg.glob("*.backup*")):
        moved.append({"from": str(p), "to": _safe_move(p, target)})
    for p in sorted(reg.glob("kernel_standby_*.txt")):
        moved.append({"from": str(p), "to": _safe_move(p, target)})
    return {"action": "archive_registry_backups",
            "moved_count": len(moved), "moved": moved, "ts": _now()}


def archive_static_backups():
    target = _archive_dir() / "static_backups"
    moved = []
    for p in sorted((ROOT / "src/dashboard/static").glob("*.backup*")):
        moved.append({"from": str(p), "to": _safe_move(p, target)})
    return {"action": "archive_static_backups",
            "moved_count": len(moved), "moved": moved, "ts": _now()}


def archive_duplicate_floor_shells():
    """Move floor_41/42/43_future_systems_vacant shells (now occupied elsewhere)
    into the archive. Safe because floors.json points to the occupied entries.
    """
    target = _archive_dir() / "duplicate_floor_shells"
    moved = []
    for name in ("floor_41_future_systems_vacant",
                 "floor_42_future_systems_vacant",
                 "floor_43_future_systems_vacant"):
        src = ROOT / "floors" / name
        if src.exists() and src.is_dir():
            moved.append({"from": str(src), "to": _safe_move(src, target)})
    return {"action": "archive_duplicate_floor_shells",
            "moved_count": len(moved), "moved": moved, "ts": _now()}


def write_archive_manifest():
    """Walk the archive root and write a manifest of every file inside."""
    manifest = {"ts": _now(),
                 "archive_root": str(ARCHIVE_ROOT),
                 "entries": []}
    if ARCHIVE_ROOT.exists():
        for p in sorted(ARCHIVE_ROOT.rglob("*")):
            if p.is_file():
                manifest["entries"].append({
                    "path": str(p),
                    "size": p.stat().st_size,
                    "rel":  str(p.relative_to(ARCHIVE_ROOT))})
    manifest["entry_count"] = len(manifest["entries"])
    out = ARCHIVE_ROOT / "20260608_v15_cleanup" / "archive_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    return {"action": "write_archive_manifest",
            "manifest_path": str(out),
            "entry_count": manifest["entry_count"], "ts": _now()}


# --- Compile/import smoke check --------------------------------------------

def py_compile_dashboard():
    import py_compile
    targets = [
        "src/dashboard/server.py",
        "src/tower_ops/correction_loop.py",
        "src/tower_ops/correction_actions.py",
        "src/tower_ops/correction_report.py",
        "src/tower_ops/worker_narration.py",
        "src/tower_ops/floor_narration.py",
        "src/tower_ops/colonel_audio.py",
        "src/tower_ops/security_enforcement.py",
        "src/tower_ops/oanda_dashboard.py",
        "src/tower_ops/binance_testnet.py",
        "src/tower_ops/stocks_paper.py",
        "src/tower_ops/talk.py",
        "src/tower_ops/not_working.py",
        "src/tower_ops/stale_language_audit.py",
        "src/tower/lifts.py",
    ]
    errors = []
    for t in targets:
        fp = ROOT / t
        if not fp.exists():
            errors.append({"target": t, "error": "missing"}); continue
        try:
            py_compile.compile(str(fp), doraise=True)
        except Exception as e:
            errors.append({"target": t, "error": str(e)[:240]})
    return {"action": "py_compile_dashboard",
            "compiled": len(targets) - len(errors),
            "errors": errors, "ts": _now()}


# --- Reconciliations --------------------------------------------------------

def reconcile_penthouse_kernel_policy():
    """Annotate the penthouse_policy.json + building.json with the V1.5 reconciled
    note. Does NOT toggle any execution gate. Does NOT remove the kernel artifact.
    """
    reg = ROOT / "data/registries"
    notes_applied = []
    pp = reg / "penthouse_policy.json"
    if pp.exists():
        d = json.loads(pp.read_text())
        d["v15_reconciliation_note"] = (
            "Inherited 4.6-offline-kernel-symbolic artifact is dormant/active_local_only. "
            "Kernel 4.5 has not been built. No execution gate is toggled by this note.")
        d["v15_reconciliation_ts"] = _now()
        pp.write_text(json.dumps(d, indent=2))
        notes_applied.append(str(pp))
    bj = reg / "building.json"
    if bj.exists():
        d = json.loads(bj.read_text())
        d["v15_reconciliation_note"] = (
            "Active kernel source is the rebased 4.6-offline-kernel-symbolic. "
            "All worker/provider/dispatch execution gates remain false.")
        d["v15_reconciliation_ts"] = _now()
        bj.write_text(json.dumps(d, indent=2))
        notes_applied.append(str(bj))
    return {"action": "reconcile_penthouse_kernel_policy",
            "files_annotated": notes_applied, "ts": _now()}


def promote_security_gate():
    """Promote penthouse/security_precheck/security_precheck.json to enforcing,
    but only for ROUTING/MOVEMENT — never for execution unlocks.
    """
    p = ROOT / "penthouse/security_precheck/security_precheck.json"
    if not p.exists():
        return {"action": "promote_security_gate", "skipped": True,
                "reason": "security_precheck.json not found", "ts": _now()}
    d = json.loads(p.read_text())
    d["security_gate"] = "enforcing_routing_only"
    d["execution_enabled"] = False
    d["enforcement_scope"] = [
        "lift_routing", "worker_movement", "floor_comms_broadcast",
        "manager_approval_actions", "practice_order_actions",
        "openclaw_practice_proposal_routing", "credential_screens",
    ]
    d["v15_note"] = (
        "Promoted by V1.5 correction loop. Enforcement covers routing/movement only. "
        "Execution gates remain locked elsewhere.")
    d["v15_promotion_ts"] = _now()
    p.write_text(json.dumps(d, indent=2))
    return {"action": "promote_security_gate", "ts": _now(),
            "promoted_to": "enforcing_routing_only",
            "path": str(p)}


# --- Audit endpoints --------------------------------------------------------

def collect_safe_corrections_inventory():
    """List the safe corrections this loop CAN apply, plus which still need
    Ross's manual decision."""
    return {
        "action": "collect_safe_corrections_inventory",
        "safe_to_apply_automatically": [
            "archive_dashboard_backups",
            "archive_tower_backups",
            "archive_registry_backups",
            "archive_static_backups",
            "archive_duplicate_floor_shells",
            "write_archive_manifest",
            "py_compile_dashboard",
            "reconcile_penthouse_kernel_policy",
            "promote_security_gate",
        ],
        "needs_ross_decision": [
            "remove inherited 4.6-symbolic kernel artifact from Penthouse",
            "enable Binance testnet placement (currently preview-only)",
            "enable Stocks paper placement (currently preview-only)",
            "promote OpenClaw practice proposals to real execution",
            "increase OANDA practice max units beyond 1000",
        ],
        "ts": _now(),
    }
