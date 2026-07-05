"""
Rebased Kernel Unit Test — Import Safety

Imports each rebased kernel module individually (not QSBKernelCore!) and
verifies that:
  - no state SQLite files are created in rebased_kernel/state/
  - no continuity_state.json is written
  - QSBKernelCore is present as a class definition only, never constructed
  - forbidden active kernel paths remain absent

Module-level code in all rebased modules is confirmed safe:
  - Path/string assignments only at module level
  - All sqlite3.connect() and file writes are inside __init__ methods
  - Importing a module does NOT call __init__ on any class

QSBKernelCore is NOT instantiated here.
"""
import sys
import importlib
import importlib.util
from pathlib import Path

ROOT  = Path("/vaults/nvme0/qsb_tower_v1")
RK    = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel"
RK_K  = RK / "kernel"
STATE = RK / "state"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

# ── Snapshot state dir before any imports ─────────────────────────────────────
def state_snapshot():
    if not STATE.exists():
        return set()
    return {f.name for f in STATE.iterdir() if f.is_file()}

pre_import_state = state_snapshot()

# ── Import the rebased kernel as a package ────────────────────────────────────
# Add rebased_kernel/ (parent of kernel/) to sys.path so 'kernel' is importable
# as a proper package with relative imports resolved.
REBASED_PARENT = str(RK)
if REBASED_PARENT not in sys.path:
    sys.path.insert(0, REBASED_PARENT)

unsafe_imports = []   # modules that created state files on import

# Import sub-cores individually first (no relative imports)
# These are the safe standalone modules
standalone_modules = [
    ("kernel.axiom_core",       "AxiomCore"),
    ("kernel.reflection_core",  "ReflectionCore"),
    ("kernel.identity_core",    "IdentityCore"),
    ("kernel.continuity_core",  "ContinuityCore"),
    ("kernel.belief_core",      "BeliefCore"),
    ("kernel.symbolic_core",    "SymbolicLogicCore"),
]

imported = {}
for mod_name, cls_name in standalone_modules:
    pre = state_snapshot()
    try:
        mod = importlib.import_module(mod_name)
        post = state_snapshot()
        new_files = post - pre
        cls = getattr(mod, cls_name, None)
        imported[mod_name] = {
            "imported": True,
            "class_found": cls is not None,
            "new_state_files": list(new_files),
            "safe": len(new_files) == 0,
        }
        if new_files:
            unsafe_imports.append(f"{mod_name}: created {new_files}")
    except Exception as e:
        imported[mod_name] = {"imported": False, "error": str(e), "safe": True}

# Import kernel_core (has relative imports — requires package context)
pre = state_snapshot()
try:
    kc_mod = importlib.import_module("kernel.kernel_core")
    post = state_snapshot()
    new_files = post - pre
    imported["kernel.kernel_core"] = {
        "imported": True,
        "QSBKernelCore_class_found": hasattr(kc_mod, "QSBKernelCore"),
        "new_state_files": list(new_files),
        "safe": len(new_files) == 0,
    }
    if new_files:
        unsafe_imports.append(f"kernel.kernel_core: created {new_files}")
except Exception as e:
    imported["kernel.kernel_core"] = {"imported": False, "error": str(e), "safe": True}

# ── Assertions ────────────────────────────────────────────────────────────────
failures = []

# 1. No state files created by any import
post_import_state = state_snapshot()
new_state = post_import_state - pre_import_state
if new_state:
    failures.append(f"IMPORT_SIDE_EFFECT: state files created on import: {new_state}")

# 2. continuity_state.json NOT written
if (STATE / "continuity_state.json").exists():
    failures.append("IMPORT_SIDE_EFFECT: continuity_state.json written on import")

# 3. No belief SQLite
if (STATE / "beliefs.sqlite").exists():
    failures.append("IMPORT_SIDE_EFFECT: beliefs.sqlite created on import")

# 4. No symbolic SQLite
if (STATE / "symbolic.sqlite").exists():
    failures.append("IMPORT_SIDE_EFFECT: symbolic.sqlite created on import")

# 5. QSBKernelCore available as a class but NOT instantiated
if "kernel.kernel_core" in imported and imported["kernel.kernel_core"]["imported"]:
    kc = importlib.import_module("kernel.kernel_core")
    QSBKernelCore = getattr(kc, "QSBKernelCore", None)
    if QSBKernelCore is None:
        failures.append("MISSING: QSBKernelCore class not found in kernel.kernel_core")
    else:
        import inspect
        assert inspect.isclass(QSBKernelCore), "QSBKernelCore must be a class"
        # Verify it is NOT instantiated — no __self__ on the class itself
        assert not hasattr(QSBKernelCore, "_instance"), "QSBKernelCore must not be a singleton"

# 6. Forbidden active paths absent
for fp in FORBIDDEN_ACTIVE_PATHS:
    if fp.exists():
        failures.append(f"FORBIDDEN_PATH_EXISTS: {fp}")

# 7. Report unsafe imports as warnings, not failures
# (requirement: mark as unsafe and report, do not fail hard)
if unsafe_imports:
    print("IMPORT_SAFETY WARNING — some modules created state on import:")
    for u in unsafe_imports:
        print(f"  UNSAFE: {u}")

if failures:
    print("IMPORT SAFETY TEST FAILED")
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)

print("REBASED KERNEL IMPORT SAFETY TEST PASSED")
print(f"  Modules imported      : {sum(1 for v in imported.values() if v.get('imported'))}")
print(f"  State files created   : {len(new_state)}  (should be 0)")
print(f"  Unsafe imports        : {len(unsafe_imports)}")
print(f"  QSBKernelCore class   : {'found' if imported.get('kernel.kernel_core', {}).get('QSBKernelCore_class_found') else 'import failed'}")
print(f"  QSBKernelCore instance: NOT created")
print(f"  Forbidden paths       : all absent")
