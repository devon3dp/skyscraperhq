from pathlib import Path
import json
import hashlib
from datetime import datetime, UTC

OLD = Path("/vaults/nvme0/qsb_skyscraper")
NEW = Path("/vaults/nvme0/qsb_tower_v1")

def sha256(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}

def file_record(path):
    return {
        "path": str(path),
        "relative_to_old": str(path.relative_to(OLD)),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }

kernel_paths = [
    OLD / "kernel/kernel_core.py",
    OLD / "kernel/axiom_core.py",
    OLD / "kernel/continuity_core.py",
    OLD / "kernel/belief_core.py",
    OLD / "kernel/symbolic_core.py",
    OLD / "kernel/identity_core.py",
    OLD / "kernel/identity.json",
    OLD / "kernel/continuity_state.json",
    OLD / "kernel/README.md",
    OLD / "kernel/COGNITIVE_47_README.md",
    OLD / "executive/penthouse.py",
    OLD / "add_cognitive_kernel_47.py",
    OLD / "promote_symbolic_to_kernel.py",
]

existing = [p for p in kernel_paths if p.exists()]
missing = [str(p) for p in kernel_paths if not p.exists()]

identity = read_json(OLD / "kernel/identity.json") if (OLD / "kernel/identity.json").exists() else {}

manifest = {
    "ts": datetime.now(UTC).isoformat(),
    "source_system": str(OLD),
    "target_tower": str(NEW),
    "standby_kernel_detected": bool(existing),
    "detected_identity": identity,
    "detected_generation": "old_qsb_locked_cognitive_kernel_4_6_to_4_7",
    "original_target_note": "User remembered Kernel 4.5; discovered source appears evolved to 4.6/4.7.",
    "integration_mode_recommended": "adapter_import_not_direct_overwrite",
    "kernel_installed_into_new_tower": False,
    "new_tower_penthouse_should_remain_socket_until_import_plan_passes": True,
    "existing_files": [file_record(p) for p in existing],
    "missing_expected_files": missing,
    "recommended_next_step": "create compatibility adapter plan before copying kernel files",
    "safety": {
        "do_not_overwrite_new_penthouse": True,
        "do_not_enable_worker_execution": True,
        "do_not_enable_provider_execution": True,
        "do_not_enable_model_inference": True,
        "do_not_install_kernel_yet": True
    }
}

out = NEW / "data/registries/standby_kernel_import_manifest.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(json.dumps({
    "standby_kernel_detected": manifest["standby_kernel_detected"],
    "source": manifest["source_system"],
    "target": manifest["target_tower"],
    "detected_identity": manifest["detected_identity"],
    "existing_files": len(existing),
    "missing_expected_files": len(missing),
    "manifest": str(out),
    "kernel_installed_into_new_tower": False,
    "next": manifest["recommended_next_step"]
}, indent=2))
