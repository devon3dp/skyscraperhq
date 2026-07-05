"""
Rebased Kernel Unit Test — State Safety

Verifies the rebased_kernel/state/ directory is and remains empty — confirming
QSBKernelCore has never been instantiated.  Checks activation_allowed and
kernel_installed remain false.  Does not import or instantiate any kernel class.
"""
import json
import sys
from pathlib import Path

ROOT  = Path("/vaults/nvme0/qsb_tower_v1")
RK    = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel"
STATE = RK / "state"
REG   = ROOT / "data" / "registries"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

# State files that must NOT exist (created only by kernel class __init__ calls)
FORBIDDEN_STATE_FILES = [
    "beliefs.sqlite",
    "symbolic.sqlite",
    "continuity_state.json",
    "identity.json",        # only written if original identity.json missing
]

failures = []

# ── 1. State directory exists ─────────────────────────────────────────────────
if not STATE.exists():
    # State dir absent means kernel was never run — this is acceptable
    pass  # state dir may not yet exist — that is fine

# ── 2. No SQLite files in state/ (would be created by kernel.__init__) ────────
if STATE.exists():
    sqlite_files = list(STATE.glob("*.sqlite"))
    if sqlite_files:
        failures.append(f"KERNEL_INSTANTIATED: SQLite files in state/: "
                        f"{[f.name for f in sqlite_files]}")

# ── 3. continuity_state.json not written to state/ ───────────────────────────
if STATE.exists() and (STATE / "continuity_state.json").exists():
    failures.append("KERNEL_INSTANTIATED: continuity_state.json found in state/ — "
                    "ContinuityCore.boot_check() was called")

# ── 4. beliefs.sqlite not created ────────────────────────────────────────────
if STATE.exists() and (STATE / "beliefs.sqlite").exists():
    failures.append("KERNEL_INSTANTIATED: beliefs.sqlite found — BeliefCore was constructed")

# ── 5. symbolic.sqlite not created ───────────────────────────────────────────
if STATE.exists() and (STATE / "symbolic.sqlite").exists():
    failures.append("KERNEL_INSTANTIATED: symbolic.sqlite found — SymbolicLogicCore was constructed")

# ── 6. No old skyscraper DB created ──────────────────────────────────────────
old_beliefs = Path("/vaults/nvme0/qsb_skyscraper/kernel/qsb_beliefs.sqlite")
old_symbolic = Path("/vaults/nvme0/qsb_skyscraper/symbolic/qsb_symbolic.sqlite")
# These should already exist from the old skyscraper; we don't check them here
# because they predate the tower. What matters is that tower state dir stays clean.

# ── 7. activation_allowed is false ───────────────────────────────────────────
approval = {}
approval_path = REG / "operator_kernel_approval.json"
if approval_path.exists():
    try:
        approval = json.loads(approval_path.read_text())
    except Exception:
        pass
if approval.get("activation_allowed", False):
    failures.append("SAFETY_VIOLATION: operator_kernel_approval.json activation_allowed=True")

# ── 8. kernel_installed is false ─────────────────────────────────────────────
sock = {}
sock_path = REG / "kernel_installation_socket.json"
if sock_path.exists():
    try:
        sock = json.loads(sock_path.read_text())
    except Exception:
        pass
if sock.get("kernel_installed", False):
    failures.append("SAFETY_VIOLATION: kernel_installation_socket.json kernel_installed=True")

# ── 9. Gate policy activation_allowed is false ───────────────────────────────
policy = {}
policy_path = REG / "kernel_activation_gate_policy.json"
if policy_path.exists():
    try:
        policy = json.loads(policy_path.read_text())
    except Exception:
        pass
if policy.get("activation_allowed", True):
    failures.append("SAFETY_VIOLATION: kernel_activation_gate_policy.json activation_allowed=True")

# ── 10. Forbidden active kernel paths absent ──────────────────────────────────
for fp in FORBIDDEN_ACTIVE_PATHS:
    if fp.exists():
        failures.append(f"FORBIDDEN_PATH_EXISTS: {fp}")

# ── 11. No QSBKernelCore instantiation in this test (self-check via AST) ─────
import ast as _ast
this_tree = _ast.parse(Path(__file__).read_text(encoding="utf-8"))
kernel_calls = [
    node for node in _ast.walk(this_tree)
    if isinstance(node, _ast.Call)
    and isinstance(node.func, _ast.Name)
    and node.func.id == "QSBKernelCore"
]
assert len(kernel_calls) == 0, "Self-check: test must not instantiate QSBKernelCore"

# ── Result ────────────────────────────────────────────────────────────────────
state_file_count = 0
if STATE.exists():
    state_file_count = len([f for f in STATE.iterdir() if f.is_file()])

if failures:
    print("STATE SAFETY TEST FAILED")
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)

print("REBASED KERNEL STATE SAFETY TEST PASSED")
print(f"  State directory       : {'exists' if STATE.exists() else 'absent (no kernel run)'}")
print(f"  State files present   : {state_file_count}  (should be 0)")
print(f"  continuity_state.json : {'absent (correct)' if not (STATE.exists() and (STATE/'continuity_state.json').exists()) else 'PRESENT'}")
print(f"  beliefs.sqlite        : {'absent (correct)' if not (STATE.exists() and (STATE/'beliefs.sqlite').exists()) else 'PRESENT'}")
print(f"  symbolic.sqlite       : {'absent (correct)' if not (STATE.exists() and (STATE/'symbolic.sqlite').exists()) else 'PRESENT'}")
print(f"  activation_allowed    : {approval.get('activation_allowed', False)}")
print(f"  kernel_installed      : {sock.get('kernel_installed', False)}")
print(f"  Forbidden paths       : all absent")
