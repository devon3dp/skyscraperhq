"""
Test the kernel dependency stubs:
- all 7 stub classes compile
- stubs implement the required interface methods
- stubs return safe empty/neutral data
- stubs do not call external systems (no network, no model, no DB write)
- stubs do not import from old qsb_skyscraper modules
- stubs do not import or instantiate QSBKernelCore
- make_reflection_deps() returns all 7 stubs
- stub_summary() returns descriptions for all 7
"""
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

# ── Syntax check ──────────────────────────────────────────────────────────────
py_compile.compile(str(ROOT / "src" / "tower" / "kernel_dependency_stubs.py"), doraise=True)

# ── Source safety check — no forbidden imports ───────────────────────────────
stub_src = (ROOT / "src" / "tower" / "kernel_dependency_stubs.py").read_text()

# Only check actual Python import statements (lines starting with 'import' or 'from')
import_only_lines = [
    (i + 1, l.strip())
    for i, l in enumerate(stub_src.splitlines())
    if l.strip().startswith(("import ", "from "))
]
FORBIDDEN_IMPORTS = [
    "qsb_skyscraper", "QSBKernelCore", "from kernel.",
    "ollama", "requests", "httpx", "aiohttp", "openai", "anthropic",
    "workers.router", "memory.memory_core", "bus.lift_core",
]
for token in FORBIDDEN_IMPORTS:
    for lineno, stripped in import_only_lines:
        if token in stripped:
            raise AssertionError(
                f"Forbidden import token {token!r} in kernel_dependency_stubs.py:L{lineno}: {stripped[:80]}"
            )

# ── Import all stub classes ───────────────────────────────────────────────────
from tower.kernel_dependency_stubs import (
    MemoryDependencyStub,
    DepartmentDependencyStub,
    MissionDependencyStub,
    LiftDependencyStub,
    GraphDependencyStub,
    BeliefDependencyStub,
    SemanticDependencyStub,
    make_reflection_deps,
    stub_summary,
)

# ── MemoryDependencyStub ──────────────────────────────────────────────────────
mem = MemoryDependencyStub()
s = mem.summary()
assert isinstance(s, dict)
assert s.get("stub") is True
assert s.get("events") == 0
assert mem.recent() == []
mem.boot()
mem.add("key", "value")
assert mem.recall("key") is None
assert isinstance(mem.describe(), str)

# ── DepartmentDependencyStub ──────────────────────────────────────────────────
dept = DepartmentDependencyStub()
d = dept.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("department_count") == 0
assert dept.list_departments() == []

# ── MissionDependencyStub ─────────────────────────────────────────────────────
miss = MissionDependencyStub()
d = miss.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("active_missions") == 0
assert miss.list_missions() == []

# ── LiftDependencyStub ────────────────────────────────────────────────────────
lift = LiftDependencyStub()
d = lift.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("total_lift_events") == 0
lift.emit("bus", "src", "tgt", "event", {})   # must not raise
lift.send("lift_id", "src", "tgt", {})          # must not raise
assert lift.states() == []
assert lift.packets() == []

# ── GraphDependencyStub ───────────────────────────────────────────────────────
graph = GraphDependencyStub()
graph.add_edge("A", "relates", "B")     # must not raise
graph.add_node("concept")               # must not raise
graph.seed_core_architecture()          # must not raise
d = graph.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("nodes") == 0
assert graph.find("anything") == []

# ── BeliefDependencyStub ──────────────────────────────────────────────────────
bel = BeliefDependencyStub()
bel.assert_belief("some belief", 0.5, "evidence")  # must not raise
assert bel.list_beliefs() == []
d = bel.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("total_beliefs") == 0
assert "PROVISIONAL" in d["states"]

# ── SemanticDependencyStub ────────────────────────────────────────────────────
sem = SemanticDependencyStub()
sem.add("source", "text")   # must not raise — no Ollama call
assert sem.search("query") == []
d = sem.dashboard()
assert isinstance(d, dict)
assert d.get("stub") is True
assert d.get("embedding_model") == "none_stub"

# ── make_reflection_deps ──────────────────────────────────────────────────────
deps = make_reflection_deps()
required_keys = ["memory", "departments", "missions", "lifts", "graph", "beliefs", "semantic"]
for k in required_keys:
    assert k in deps, f"make_reflection_deps missing key: {k}"
assert isinstance(deps["memory"],      MemoryDependencyStub)
assert isinstance(deps["departments"], DepartmentDependencyStub)
assert isinstance(deps["missions"],    MissionDependencyStub)
assert isinstance(deps["lifts"],       LiftDependencyStub)
assert isinstance(deps["graph"],       GraphDependencyStub)
assert isinstance(deps["beliefs"],     BeliefDependencyStub)
assert isinstance(deps["semantic"],    SemanticDependencyStub)

# ── stub_summary ──────────────────────────────────────────────────────────────
summary = stub_summary()
assert len(summary) == 7
for k in required_keys:
    assert k in summary
    assert "description" in summary[k]
    assert "class" in summary[k]

# ── No state files written (stubs are stateless) ─────────────────────────────
state = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" / "state"
if state.exists():
    sqlite_files = list(state.glob("*.sqlite"))
    assert len(sqlite_files) == 0, \
        f"Stubs wrote SQLite files: {[f.name for f in sqlite_files]}"

# ── Stubs do not import from old vault ───────────────────────────────────────
OLD_VAULT = "/vaults/nvme0/qsb_skyscraper"
assert OLD_VAULT not in stub_src, "Stub source must not reference old vault path"

print("KERNEL DEPENDENCY STUBS TEST PASSED")
print(f"  Stubs created         : {len(deps)}")
for k, info in summary.items():
    print(f"  {k:20s}: {info['class']}")
print(f"  No external calls made: confirmed (stubs are stateless)")
print(f"  No state files written: confirmed")
print(f"  Old vault refs        : 0")
