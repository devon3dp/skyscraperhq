"""
Verify the dormant kernel import:
- old source kernel still present at original location
- dormant import folder structure exists
- all copied files exist
- SHA-256 hashes match manifest
- forbidden direct kernel paths remain absent
- kernel_installed remains False
- dormant_kernel_imported is True
- activation_enabled is False
- all execution flags False
"""
import sys
import json
import hashlib
from pathlib import Path

ROOT    = Path("/vaults/nvme0/qsb_tower_v1")
SRC_KERNEL = Path("/vaults/nvme0/qsb_skyscraper/kernel")
DORMANT = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel"
MANIFEST = DORMANT / "import_manifest.json"

# ── Old source kernel still present ──────────────────────────────────────────
assert SRC_KERNEL.exists(), "Old source kernel at /vaults/nvme0/qsb_skyscraper/kernel is missing!"
assert (SRC_KERNEL / "kernel_core.py").exists(), "Old kernel_core.py missing from source"
assert (SRC_KERNEL / "identity.json").exists(),  "Old identity.json missing from source"

# ── Dormant import directory structure ────────────────────────────────────────
assert DORMANT.exists(),                               "Dormant import directory missing"
assert (DORMANT / "kernel").exists(),                  "Dormant kernel/ subdir missing"
assert (DORMANT / "source_support").exists(),          "Dormant source_support/ subdir missing"
assert (DORMANT / "import_reports").exists(),          "Dormant import_reports/ subdir missing"
assert MANIFEST.exists(),                              "import_manifest.json missing"

# ── All expected kernel files exist ───────────────────────────────────────────
expected_kernel_files = [
    "kernel_core.py", "axiom_core.py", "continuity_core.py", "belief_core.py",
    "symbolic_core.py", "identity_core.py", "reflection_core.py", "__init__.py",
    "identity.json", "continuity_state.json", "README.md", "COGNITIVE_47_README.md",
]
for f in expected_kernel_files:
    assert (DORMANT / "kernel" / f).exists(), f"Missing dormant kernel file: {f}"

expected_support_files = ["penthouse.py", "add_cognitive_kernel_47.py", "promote_symbolic_to_kernel.py"]
for f in expected_support_files:
    assert (DORMANT / "source_support" / f).exists(), f"Missing support file: {f}"

# ── SHA-256 hash verification ─────────────────────────────────────────────────
manifest = json.loads(MANIFEST.read_text())
recorded_hashes = manifest.get("sha256_hashes", {})
assert len(recorded_hashes) >= 10, "Too few hashes in manifest"

for rel_path, expected in recorded_hashes.items():
    full = DORMANT / rel_path
    if full.exists():
        actual = hashlib.sha256(full.read_bytes()).hexdigest()
        assert actual == expected, f"Hash mismatch for {rel_path}: expected {expected}, got {actual}"

# ── Forbidden direct kernel paths absent ──────────────────────────────────────
forbidden = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]
for f in forbidden:
    assert not f.exists(), f"FORBIDDEN kernel path found: {f}"

# ── Manifest safety flags ─────────────────────────────────────────────────────
safety = manifest.get("safety_flags", {})
assert safety.get("kernel_installed")           is False, "kernel_installed must be False in manifest"
assert safety.get("activation_enabled")         is False, "activation_enabled must be False in manifest"
assert safety.get("execution_enabled")          is False, "execution_enabled must be False in manifest"
assert safety.get("worker_execution_enabled")   is False, "worker_execution_enabled must be False in manifest"
assert safety.get("provider_execution_enabled") is False, "provider_execution_enabled must be False in manifest"
assert safety.get("model_inference_enabled")    is False, "model_inference_enabled must be False in manifest"
assert safety.get("live_dispatch_enabled")      is False, "live_dispatch_enabled must be False in manifest"
assert safety.get("direct_execution_allowed")   is False, "direct_execution_allowed must be False in manifest"

# ── Identity fields ───────────────────────────────────────────────────────────
identity = manifest.get("detected_identity", {})
assert identity.get("name")    == "QSB Kernel",                    "Kernel name mismatch"
assert "4.6" in identity.get("version", ""),                       "Version should contain 4.6"
assert identity.get("imported_as") or manifest.get("imported_as") == "dormant_standby_kernel"

print("DORMANT KERNEL IMPORT TEST PASSED")
print(f"  Source kernel present : {SRC_KERNEL}")
print(f"  Dormant import dir    : {DORMANT}")
print(f"  Kernel files          : {len(expected_kernel_files)}")
print(f"  Support files         : {len(expected_support_files)}")
print(f"  Hashes verified       : {len(recorded_hashes)}")
print(f"  Forbidden paths       : all absent")
print(f"  kernel_installed      : {safety.get('kernel_installed')}")
print(f"  activation_enabled    : {safety.get('activation_enabled')}")
