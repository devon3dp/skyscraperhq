from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_skyscraper")

def write(path, text):
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text.lstrip(), encoding="utf-8")

# ------------------------------------------------------------
# Create proper kernel directory
# ------------------------------------------------------------
(ROOT / "kernel").mkdir(parents=True, exist_ok=True)
(ROOT / "kernel" / "__init__.py").write_text("", encoding="utf-8")

# ------------------------------------------------------------
# Promote symbolic logic into kernel namespace
# ------------------------------------------------------------
old_symbolic = ROOT / "symbolic" / "symbolic_core.py"
new_symbolic = ROOT / "kernel" / "symbolic_core.py"

if old_symbolic.exists():
    new_symbolic.write_text(old_symbolic.read_text(encoding="utf-8"), encoding="utf-8")
else:
    raise FileNotFoundError("Missing symbolic/symbolic_core.py. Install symbolic logic first.")

# ------------------------------------------------------------
# Kernel Identity Core
# ------------------------------------------------------------
write("kernel/identity_core.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
IDENTITY_FILE = ROOT / "kernel" / "identity.json"

DEFAULT_IDENTITY = {
    "name": "QSB Kernel",
    "full_name": "Quantum Symbolic Brain Kernel",
    "version": "4.6-offline-kernel-symbolic",
    "role": "Locked Penthouse Kernel",
    "principle": "Models are workers. QSB is the kernel.",
    "architecture": "Penthouse kernel above floors, lifts, departments, and local model workers.",
    "created_or_verified": None
}

class IdentityCore:
    def __init__(self):
        IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not IDENTITY_FILE.exists():
            data = dict(DEFAULT_IDENTITY)
            data["created_or_verified"] = datetime.now(UTC).isoformat()
            IDENTITY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def status(self):
        return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
''')

# ------------------------------------------------------------
# Kernel Axiom Core
# ------------------------------------------------------------
write("kernel/axiom_core.py", r'''
class AxiomCore:
    AXIOMS = [
        "QSB is not a model.",
        "QSB is the persistent kernel above models.",
        "Models are replaceable workers.",
        "Departments are modular floors.",
        "Lifts are controlled communication buses.",
        "Memory must persist across boots.",
        "Symbolic logic belongs inside the locked Penthouse kernel.",
        "Knowledge Graph stores relationships, but the kernel interprets meaning.",
        "Upgrades must preserve continuity.",
        "Cloud calls remain disabled unless explicitly enabled later."
    ]

    def list_axioms(self):
        return self.AXIOMS

    def check(self, text):
        lower = text.lower()
        warnings = []

        if "delete memory" in lower or "wipe memory" in lower:
            warnings.append("Memory deletion request detected. Continuity protection should review this.")

        if "cloud" in lower and "enable" in lower:
            warnings.append("Cloud enablement request detected. Offline-first rule requires explicit confirmation.")

        if "symbolic floor" in lower:
            warnings.append("Architecture correction: symbolic logic is kernel-level, not a normal floor.")

        return {
            "passed": len(warnings) == 0,
            "warnings": warnings,
            "axioms_checked": len(self.AXIOMS)
        }
''')

# ------------------------------------------------------------
# Kernel Continuity Core
# ------------------------------------------------------------
write("kernel/continuity_core.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import json
import hashlib

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
STATE_FILE = ROOT / "kernel" / "continuity_state.json"

class ContinuityCore:
    def __init__(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, path):
        p = ROOT / path
        if not p.exists():
            return "missing"
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def boot_check(self):
        current = {
            "ts": datetime.now(UTC).isoformat(),
            "identity_hash": self._hash_file("kernel/identity.json"),
            "constitution_hash": self._hash_file("config/constitution.md"),
            "symbolic_hash": self._hash_file("kernel/symbolic_core.py"),
            "penthouse_hash": self._hash_file("executive/penthouse.py"),
            "memory_db_exists": (ROOT / "memory" / "qsb_memory.sqlite").exists(),
            "knowledge_db_exists": (ROOT / "knowledge" / "qsb_knowledge.sqlite").exists(),
            "mission_db_exists": (ROOT / "missions" / "qsb_missions.sqlite").exists(),
            "lift_db_exists": (ROOT / "bus" / "qsb_lifts.sqlite").exists()
        }

        previous = None
        status = "FIRST_KERNEL_BOOT"

        if STATE_FILE.exists():
            previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            drift = []
            for key in ["identity_hash", "constitution_hash", "symbolic_hash"]:
                if previous.get(key) != current.get(key):
                    drift.append(key)
            status = "CONTINUITY_CONFIRMED" if not drift else "CONTROLLED_KERNEL_DRIFT"
            current["drift"] = drift

        current["status"] = status
        current["previous"] = previous
        STATE_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
''')

# ------------------------------------------------------------
# Locked Kernel Core
# ------------------------------------------------------------
write("kernel/kernel_core.py", r'''
from kernel.identity_core import IdentityCore
from kernel.axiom_core import AxiomCore
from kernel.continuity_core import ContinuityCore
from kernel.symbolic_core import SymbolicLogicCore

class QSBKernelCore:
    def __init__(self):
        self.identity = IdentityCore()
        self.axioms = AxiomCore()
        self.continuity = ContinuityCore()
        self.symbols = SymbolicLogicCore()
        self.boot_state = self.continuity.boot_check()

    def status(self):
        return {
            "kernel": self.identity.status(),
            "continuity": self.boot_state,
            "axioms": self.axioms.list_axioms(),
            "symbolic_core": self.symbols.dashboard()
        }

    def analyze(self, text, source="kernel"):
        axiom_check = self.axioms.check(text)
        symbolic_result = self.symbols.observe(source, text)
        return {
            "axiom_check": axiom_check,
            "symbolic_result": symbolic_result
        }
''')

# ------------------------------------------------------------
# Patch Penthouse to use kernel core
# ------------------------------------------------------------
penthouse = ROOT / "executive" / "penthouse.py"
text = penthouse.read_text(encoding="utf-8")

text = text.replace(
    "from symbolic.symbolic_core import SymbolicLogicCore",
    "from kernel.kernel_core import QSBKernelCore"
)

if "from kernel.kernel_core import QSBKernelCore" not in text:
    text = text.replace(
        "from knowledge.graph_core import KnowledgeGraph",
        "from knowledge.graph_core import KnowledgeGraph\nfrom kernel.kernel_core import QSBKernelCore"
    )

text = text.replace(
    "    symbols = SymbolicLogicCore()",
    "    kernel = QSBKernelCore()\n    symbols = kernel.symbols"
)

if "    kernel = QSBKernelCore()" not in text:
    text = text.replace(
        "    graph = KnowledgeGraph()\n    graph.seed_core_architecture()",
        "    graph = KnowledgeGraph()\n    graph.seed_core_architecture()\n    kernel = QSBKernelCore()\n    symbols = kernel.symbols"
    )

text = text.replace(
    '    print("Symbolic Logic Floor online.")',
    '    print("Kernel Core online.")\n    print("Kernel Symbolic Core online.")'
)

text = text.replace(
    '    print("Symbolic commands: /symdash, /sym TEXT, /symfind TERM")',
    '    print("Kernel commands: /kernel, /axioms, /continuity")\n    print("Symbolic commands: /symdash, /sym TEXT, /symfind TERM")'
)

kernel_command_block = r'''
        if msg == "/kernel":
            print(json.dumps(kernel.status(), indent=2))
            continue

        if msg == "/axioms":
            print(json.dumps(kernel.axioms.list_axioms(), indent=2))
            continue

        if msg == "/continuity":
            print(json.dumps(kernel.boot_state, indent=2))
            continue

'''

if 'if msg == "/kernel":' not in text:
    marker = '        if msg == "/symdash":\n'
    text = text.replace(marker, kernel_command_block + marker)

text = text.replace(
    'symbolic_result = symbols.observe("prompt", prompt)',
    'kernel_analysis = kernel.analyze(prompt, source="prompt")\n        symbolic_result = kernel_analysis["symbolic_result"]'
)

# Update version label.
config = ROOT / "config" / "offline_models.yaml"
if config.exists():
    cfg = config.read_text(encoding="utf-8")
    cfg = cfg.replace("version: 4.6-offline-symbolic", "version: 4.6-offline-locked-kernel")
    cfg = cfg.replace("version: 4.6-offline", "version: 4.6-offline-locked-kernel")
    config.write_text(cfg, encoding="utf-8")

penthouse.write_text(text, encoding="utf-8")

# ------------------------------------------------------------
# Docs
# ------------------------------------------------------------
write("kernel/README.md", """
# QSB Locked Kernel Core

This upgrade promotes symbolic logic into the Penthouse kernel.

Correct architecture:

Penthouse / Locked Kernel:
- Identity Core
- Continuity Core
- Axiom Core
- Kernel Symbolic Core
- Executive routing authority

Floors:
- Memory Floor
- Department State Floor
- Mission Floor
- Knowledge Graph Floor
- Research Floor
- Software Floor
- Vision Floor
- Trading Floor
- Future AirLLM / model worker floors

Important correction:

Symbolic logic is not a normal department floor.
Symbolic logic belongs inside the locked QSB kernel.

The Knowledge Graph remains a storage/relationship service.
The Kernel Symbolic Core performs interpretation.
""")

print("QSB symbolic logic promoted into Locked Kernel Core.")
print("Run:")
print("cd /vaults/nvme0/qsb_skyscraper")
print("./run_penthouse.sh")
