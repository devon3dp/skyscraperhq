"""
Rebased Kernel Unit Test — Static Safety

Verifies the rebased kernel files are structurally sound without importing or
instantiating any kernel class.  All checks are pure file inspection (text
scan + py_compile).  No kernel code is executed.
"""
import ast
import py_compile
import sys
from pathlib import Path

ROOT  = Path("/vaults/nvme0/qsb_tower_v1")
RK_K  = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" / "kernel"

OLD_VAULT = "/vaults/nvme0/qsb_skyscraper"

# Imports that indicate live network / provider / execution capability
# Uses startswith-on-import-lines so path strings containing these words are ignored
FORBIDDEN_IMPORT_MODULES = {
    "requests", "httpx", "aiohttp", "openai", "anthropic",
    "google.generativeai", "ollama", "urllib.request",
    "subprocess", "socket",
}

FORBIDDEN_EXECUTION_PATTERNS = [
    "os.system(",
    "subprocess.run(",
    "subprocess.call(",
    "subprocess.Popen(",
    "exec(",
    "__import__(",
]

EXPECTED_FILES = [
    "__init__.py",
    "axiom_core.py",
    "belief_core.py",
    "continuity_core.py",
    "identity_core.py",
    "kernel_core.py",
    "reflection_core.py",
    "symbolic_core.py",
]

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

failures = []

# ── 1. Expected files exist ───────────────────────────────────────────────────
for fname in EXPECTED_FILES:
    if not (RK_K / fname).exists():
        failures.append(f"MISSING FILE: {fname}")

# ── 2. All Python files compile ───────────────────────────────────────────────
for fname in EXPECTED_FILES:
    if not fname.endswith(".py"):
        continue
    path = RK_K / fname
    if not path.exists():
        continue
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as e:
        failures.append(f"COMPILE FAIL: {fname}: {e}")

# ── 3. No old vault references ────────────────────────────────────────────────
for fname in EXPECTED_FILES:
    if not fname.endswith(".py"):
        continue
    path = RK_K / fname
    if not path.exists():
        continue
    src = path.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        if OLD_VAULT in line:
            failures.append(f"OLD_VAULT_REF: {fname}:L{i}: {line.strip()[:80]}")

# ── 4. No forbidden network/provider imports ──────────────────────────────────
for fname in EXPECTED_FILES:
    if not fname.endswith(".py"):
        continue
    path = RK_K / fname
    if not path.exists():
        continue
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
            else:
                top = node.names[0].name.split(".")[0] if node.names else ""
            if top in FORBIDDEN_IMPORT_MODULES:
                failures.append(f"FORBIDDEN_IMPORT: {fname}: imports '{top}'")

# ── 5. No subprocess / os.system / exec execution patterns ───────────────────
for fname in EXPECTED_FILES:
    if not fname.endswith(".py"):
        continue
    path = RK_K / fname
    if not path.exists():
        continue
    src = path.read_text(encoding="utf-8")
    for pat in FORBIDDEN_EXECUTION_PATTERNS:
        if pat in src:
            failures.append(f"EXEC_PATTERN: {fname}: contains '{pat}'")

# ── 6. No forbidden active kernel paths referenced ───────────────────────────
FORBIDDEN_PATH_STRINGS = [
    "penthouse/kernel.py",
    "penthouse/qsb_kernel_4_5.py",
    "src/tower/kernel.py",
    "src/tower/qsb_kernel_4_5.py",
]
for fname in EXPECTED_FILES:
    if not fname.endswith(".py"):
        continue
    path = RK_K / fname
    if not path.exists():
        continue
    src = path.read_text(encoding="utf-8")
    for pat in FORBIDDEN_PATH_STRINGS:
        if pat in src:
            failures.append(f"FORBIDDEN_PATH_REF: {fname}: references '{pat}'")

# ── 7. Forbidden active kernel paths physically absent ───────────────────────
for fp in FORBIDDEN_ACTIVE_PATHS:
    if fp.exists():
        failures.append(f"FORBIDDEN_PATH_EXISTS: {fp}")

# ── 8. QSBKernelCore not instantiated in this test (self-check via AST) ──────
this_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
kernel_calls = [
    node for node in ast.walk(this_tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Name)
    and node.func.id == "QSBKernelCore"
]
assert len(kernel_calls) == 0, "Self-check: test must not instantiate QSBKernelCore"

# ── Result ────────────────────────────────────────────────────────────────────
if failures:
    print("STATIC SAFETY TEST FAILED")
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)

print("REBASED KERNEL STATIC SAFETY TEST PASSED")
print(f"  Files checked         : {len(EXPECTED_FILES)}")
print(f"  Compile results       : all_pass")
print(f"  Old vault refs        : 0")
print(f"  Forbidden imports     : 0")
print(f"  Exec patterns         : 0")
print(f"  Forbidden path refs   : 0")
print(f"  Forbidden paths exist : 0")
