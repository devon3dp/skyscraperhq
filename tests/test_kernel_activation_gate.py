"""
Test the KernelActivationGate:
- compiles cleanly
- activation_allowed is always False
- kernel_installed is False
- QSBKernelCore_instantiated is False
- operator_approval_recorded is False
- all execution flags remain False
- forbidden active kernel paths absent
- no rebased kernel state files created by the gate
- gate never imports or instantiates QSBKernelCore
"""
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

# ── Syntax check ──────────────────────────────────────────────────────────────
py_compile.compile(str(ROOT / "src" / "tower" / "kernel_activation_gate.py"), doraise=True)

# ── Import must NOT pull in any kernel class ──────────────────────────────────
# Verify no 'import' or 'from' statement brings in QSBKernelCore as a live symbol.
# (The string "QSBKernelCore" may appear as a JSON key — that is fine.)
gate_src = (ROOT / "src" / "tower" / "kernel_activation_gate.py").read_text()
# Only real Python import statements start with 'import ' or 'from ' at the line level
import_lines = [
    l for l in gate_src.splitlines()
    if l.strip().startswith(("import ", "from ")) and "QSBKernelCore" in l
]
assert len(import_lines) == 0, f"Gate imports QSBKernelCore as a live symbol: {import_lines}"

# The gate must not import from the rebased kernel package directory
rebased_imports = [
    l for l in gate_src.splitlines()
    if l.strip().startswith(("import ", "from "))
    and ("rebased_kernel" in l or "kernel_core" in l or "from .kernel" in l)
]
assert len(rebased_imports) == 0, f"Gate imports from rebased kernel package: {rebased_imports}"

# ── Import the gate ───────────────────────────────────────────────────────────
from tower.kernel_activation_gate import KernelActivationGate

gate = KernelActivationGate()
r = gate.evaluate()
d = gate.dashboard()

# ── activation_allowed is always False ───────────────────────────────────────
assert r["activation_allowed"] is False,  "evaluate: activation_allowed must be False"
assert d["activation_allowed"] is False,  "dashboard: activation_allowed must be False"

# ── kernel_installed is False ─────────────────────────────────────────────────
assert r["kernel_installed"] is False,    "kernel_installed must be False"
assert d["kernel_installed"] is False

# ── QSBKernelCore not instantiated ───────────────────────────────────────────
assert r["QSBKernelCore_instantiated"] is False, "QSBKernelCore_instantiated must be False"
assert d["QSBKernelCore_instantiated"] is False

# No state SQLite files exist
state = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" / "state"
if state.exists():
    sqlite_files = list(state.glob("*.sqlite"))
    assert len(sqlite_files) == 0, \
        f"State SQLite files found after gate run: {[f.name for f in sqlite_files]}"
    assert not (state / "continuity_state.json").exists(), \
        "continuity_state.json written — ContinuityCore was called"

# ── Operator approval is False ────────────────────────────────────────────────
assert r["operator_approval_recorded"] is False, "operator_approval_recorded must be False"
assert d["operator_approval_recorded"] is False

# ── Execution flags are all False ────────────────────────────────────────────
assert r["worker_execution_enabled"]   is False
assert r["provider_execution_enabled"] is False
assert r["model_inference_enabled"]    is False
assert d["worker_execution_enabled"]   is False
assert d["provider_execution_enabled"] is False
assert d["model_inference_enabled"]    is False

# ── Forbidden paths absent ────────────────────────────────────────────────────
assert r["forbidden_paths_absent"] is True, "Forbidden kernel paths must be absent"
FORBIDDEN = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]
for f in FORBIDDEN:
    assert not f.exists(), f"FORBIDDEN path present: {f}"

# ── Rebased kernel present and path rebase complete ───────────────────────────
assert r["rebased_kernel_present"] is True,  "Rebased kernel must be present"
assert r["path_rebase_complete"]   is True,  "Path rebase must be complete"

# ── Security clearance is NOT auto-granted ────────────────────────────────────
assert r["security_spine_clearance"] is False, \
    "Security clearance must never be auto-granted by the gate"

# ── Gate evaluation structure ─────────────────────────────────────────────────
assert "checks" in r,              "evaluate() must return checks list"
assert "blocked_reasons" in r,     "evaluate() must return blocked_reasons"
assert r["gates_blocked"] >= 1,    "At least one gate must be blocked (no operator approval)"
assert r["gate_status"] == "BLOCKED", "Gate must be BLOCKED while any check fails"

# ── Registries exist ──────────────────────────────────────────────────────────
assert (ROOT / "data" / "registries" / "kernel_activation_gate_policy.json").exists()
assert (ROOT / "data" / "registries" / "operator_kernel_approval.json").exists()

import json
policy  = json.loads((ROOT / "data" / "registries" / "kernel_activation_gate_policy.json").read_text())
approval = json.loads((ROOT / "data" / "registries" / "operator_kernel_approval.json").read_text())

assert policy.get("activation_allowed") is False
assert policy.get("required_gates", {}).get("operator_approval_required") is True
assert approval.get("operator_approval_recorded") is False
assert approval.get("activation_allowed") is False

print("KERNEL ACTIVATION GATE TEST PASSED")
print(f"  gate_status              : {r['gate_status']}")
print(f"  activation_allowed       : {r['activation_allowed']}")
print(f"  gates_passed             : {r['gates_passed']}")
print(f"  gates_blocked            : {r['gates_blocked']}")
print(f"  kernel_installed         : {r['kernel_installed']}")
print(f"  QSBKernelCore_instantiated: {r['QSBKernelCore_instantiated']}")
print(f"  operator_approval        : {r['operator_approval_recorded']}")
print(f"  security_clearance       : {r['security_spine_clearance']}")
print(f"  forbidden_paths_absent   : {r['forbidden_paths_absent']}")
print(f"  next_phase               : {r['next_recommended_phase']}")
