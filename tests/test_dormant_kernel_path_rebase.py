"""
Verify the dormant kernel path rebase:
- rebased kernel folder and files exist
- old /vaults/nvme0/qsb_skyscraper hardcoded root absent from all rebased Python files
- 'from kernel.' absolute imports absent (replaced with relative imports)
- all rebased files compile cleanly
- forbidden active kernel paths remain absent
- kernel_installed remains False
- activation_enabled / activation_allowed remain False
- all execution flags remain False
- QSBKernelCore was NOT instantiated (no state files written by this test)
- rebase manifest and report exist
"""
import sys
import json
import hashlib
import py_compile
from pathlib import Path

ROOT    = Path("/vaults/nvme0/qsb_tower_v1")
RK      = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel"
RK_K    = RK / "kernel"
STATE   = RK / "state"
MANIFEST = RK / "rebase_manifest.json"

OLD_VAULT      = "/vaults/nvme0/qsb_skyscraper"
OLD_ABS_IMPORT = "from kernel."    # old absolute import pattern

# ── Directory structure ───────────────────────────────────────────────────────
assert RK.exists(),   "rebased_kernel/ directory missing"
assert RK_K.exists(), "rebased_kernel/kernel/ directory missing"
assert (RK / "state").exists(),   "rebased_kernel/state/ directory missing"
assert (RK / "reports").exists(), "rebased_kernel/reports/ directory missing"

# ── All expected Python files exist ──────────────────────────────────────────
expected_py = [
    "__init__.py", "kernel_core.py", "axiom_core.py", "continuity_core.py",
    "belief_core.py", "symbolic_core.py", "identity_core.py", "reflection_core.py",
]
for f in expected_py:
    assert (RK_K / f).exists(), f"Missing rebased Python file: {f}"

# ── Old vault path absent from all rebased Python files ──────────────────────
for py in RK_K.glob("*.py"):
    src = py.read_text(encoding="utf-8")
    # Check every line — including comments — for the old vault path
    for i, line in enumerate(src.splitlines(), 1):
        assert OLD_VAULT not in line, (
            f"Old vault path found in rebased file {py.name}:L{i}: {line.strip()[:80]}"
        )

# ── Old absolute 'from kernel.' import pattern absent ────────────────────────
for py in RK_K.glob("*.py"):
    src = py.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        # Allow the comment header in __init__.py; only flag real import statements
        stripped = line.strip()
        if stripped.startswith("from kernel.") or stripped.startswith("import kernel."):
            raise AssertionError(
                f"Old absolute import found in {py.name}:L{i}: {stripped[:80]}"
            )

# ── All rebased Python files compile cleanly ─────────────────────────────────
for py in sorted(RK_K.glob("*.py")):
    try:
        py_compile.compile(str(py), doraise=True)
    except py_compile.PyCompileError as e:
        raise AssertionError(f"Compile failure in {py.name}: {e}")

# ── New tower path is present in each patched file ───────────────────────────
NEW_STATE = "rebased_kernel/state"
for fname in ["identity_core.py", "continuity_core.py", "belief_core.py", "symbolic_core.py"]:
    src = (RK_K / fname).read_text()
    assert NEW_STATE in src or "KERNEL_STATE_ROOT" in src, \
        f"{fname} does not reference new state path"

# ── Relative imports in kernel_core.py ───────────────────────────────────────
kc_src = (RK_K / "kernel_core.py").read_text()
assert "from .identity_core import" in kc_src, "kernel_core.py missing relative import for identity_core"
assert "from .axiom_core import"    in kc_src, "kernel_core.py missing relative import for axiom_core"
assert "from .continuity_core import" in kc_src
assert "from .symbolic_core import" in kc_src
assert "from .belief_core import"   in kc_src

# ── Rebase manifest exists and is valid ──────────────────────────────────────
assert MANIFEST.exists(), "rebase_manifest.json missing"
m = json.loads(MANIFEST.read_text())
sf = m.get("safety_flags", {})

assert sf.get("kernel_installed")           is False, "manifest: kernel_installed must be False"
assert sf.get("activation_enabled")         is False, "manifest: activation_enabled must be False"
assert sf.get("execution_enabled")          is False, "manifest: execution_enabled must be False"
assert sf.get("worker_execution_enabled")   is False, "manifest: worker_execution_enabled must be False"
assert sf.get("provider_execution_enabled") is False, "manifest: provider_execution_enabled must be False"
assert sf.get("model_inference_enabled")    is False, "manifest: model_inference_enabled must be False"
assert sf.get("qsb_kernel_core_instantiated") is False, "manifest: qsb_kernel_core_instantiated must be False"
assert sf.get("activation_allowed")         is False, "manifest: activation_allowed must be False"
assert m.get("old_path_references_remaining") == 0, "old_path_references_remaining must be 0"
assert m.get("import_rewiring_count", 0) >= 5, "Expected at least 5 import rewires"
assert m.get("compile_results", {}).get("all_pass") is True, "compile_results.all_pass must be True"

# ── Registry report exists ────────────────────────────────────────────────────
reg_report = ROOT / "data" / "registries" / "dormant_kernel_path_rebase_report.json"
assert reg_report.exists(), "dormant_kernel_path_rebase_report.json missing from registries"

# ── Forbidden active kernel paths absent ─────────────────────────────────────
FORBIDDEN = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]
for f in FORBIDDEN:
    assert not f.exists(), f"FORBIDDEN path found: {f}"

# ── QSBKernelCore was NOT instantiated (state dir should be empty — no DBs) ──
state_dbs = list(STATE.glob("*.sqlite"))
assert len(state_dbs) == 0, (
    f"State SQLite files found — kernel was instantiated: {[f.name for f in state_dbs]}"
)
# continuity_state.json in state/ must also not exist yet (only the copy in kernel/ is the dormant snapshot)
assert not (STATE / "continuity_state.json").exists(), (
    "continuity_state.json found in state/ — ContinuityCore.boot_check() was called"
)

# ── Original dormant import still intact ─────────────────────────────────────
dormant = ROOT / "penthouse" / "kernel_installation_socket" / "dormant_imported_kernel" / "kernel"
assert dormant.exists(), "Original dormant import kernel/ directory missing"
assert (dormant / "kernel_core.py").exists(), "Original dormant kernel_core.py missing"

py_count = len(list(RK_K.glob("*.py")))
print("DORMANT KERNEL PATH REBASE TEST PASSED")
print(f"  Rebased kernel dir        : {RK_K}")
print(f"  Python files              : {py_count}")
print(f"  Old vault refs remaining  : 0  (CLEAN)")
print(f"  Old absolute imports      : 0  (CLEAN)")
print(f"  Compile result            : ALL OK")
print(f"  State SQLite files        : {len(state_dbs)}  (kernel not instantiated)")
print(f"  kernel_installed          : {sf.get('kernel_installed')}")
print(f"  activation_allowed        : {sf.get('activation_allowed')}")
print(f"  Forbidden paths           : all absent")
print(f"  Next phase                : {m.get('next_recommended_phase')}")
