"""
Rebased Kernel Unit Test — Dependency Contracts

Verifies that kernel_dependency_stubs.py provides all 7 required dependency
stubs, that each stub implements its expected interface, and that no stub
calls external systems (models, providers, databases, network).
"""
import sys
import ast
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

STUBS_FILE = ROOT / "src" / "tower" / "kernel_dependency_stubs.py"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse" / "kernel.py",
    ROOT / "penthouse" / "qsb_kernel_4_5.py",
    ROOT / "src"       / "tower" / "kernel.py",
    ROOT / "src"       / "tower" / "qsb_kernel_4_5.py",
]

# ── File exists ───────────────────────────────────────────────────────────────
assert STUBS_FILE.exists(), "kernel_dependency_stubs.py missing"

# ── Source safety: no live imports ───────────────────────────────────────────
stub_src = STUBS_FILE.read_text(encoding="utf-8")
import_lines = [
    l.strip() for l in stub_src.splitlines()
    if l.strip().startswith(("import ", "from "))
]
FORBIDDEN_IMPORT_TOKENS = {
    "requests", "httpx", "aiohttp", "openai", "anthropic",
    "ollama", "socket", "subprocess", "os.system",
    "workers.router", "memory.memory_core", "bus.lift_core",
    "qsb_skyscraper", "QSBKernelCore",
}
for line in import_lines:
    for token in FORBIDDEN_IMPORT_TOKENS:
        assert token not in line, \
            f"Forbidden token {token!r} in stub import: {line[:80]}"

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

# ── Verify each stub's interface and inert return values ─────────────────────

# MemoryDependencyStub
mem = MemoryDependencyStub()
s = mem.summary()
assert isinstance(s, dict) and s.get("stub") is True
assert s.get("events") == 0
assert isinstance(mem.recent(), list) and mem.recent() == []
mem.boot()                # must not raise
mem.add("k", "v")         # must not raise, no DB write
assert mem.recall("k") is None
desc = mem.describe()
assert isinstance(desc, str) and len(desc) > 0

# DepartmentDependencyStub
dept = DepartmentDependencyStub()
d = dept.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("department_count") == 0
assert isinstance(dept.list_departments(), list)

# MissionDependencyStub
miss = MissionDependencyStub()
d = miss.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("active_missions") == 0
assert isinstance(miss.list_missions(), list)

# LiftDependencyStub (old LiftSystem.emit + new LiftNetwork.send interfaces)
lift = LiftDependencyStub()
d = lift.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("total_lift_events") == 0
lift.emit("bus", "src", "tgt", "event", {})   # old API — must not raise
lift.send("lid", "src", "tgt", {})             # new API — must not raise
assert isinstance(lift.states(), list)
assert isinstance(lift.packets(), list)

# GraphDependencyStub
graph = GraphDependencyStub()
graph.add_edge("A", "rel", "B", 1.0, "test")  # must not raise
graph.add_node("concept")                        # must not raise
graph.seed_core_architecture()                    # must not raise
d = graph.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("nodes") == 0
assert isinstance(graph.find("term"), list)

# BeliefDependencyStub
bel = BeliefDependencyStub()
bel.assert_belief("belief text", 0.5, "evidence")  # must not raise
assert isinstance(bel.list_beliefs(), list)
d = bel.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("total_beliefs") == 0
assert "PROVISIONAL" in d.get("states", {})
assert isinstance(d.get("top_beliefs"), list)

# SemanticDependencyStub — must not call Ollama or any model
sem = SemanticDependencyStub()
sem.add("source", "some text")           # must not make network call
assert isinstance(sem.search("query"), list)
d = sem.dashboard()
assert isinstance(d, dict) and d.get("stub") is True
assert d.get("embedding_model") == "none_stub"
assert d.get("semantic_memories") == 0

# ── make_reflection_deps ──────────────────────────────────────────────────────
deps = make_reflection_deps()
REQUIRED_KEYS = ["memory", "departments", "missions", "lifts", "graph", "beliefs", "semantic"]
assert len(deps) == 7, f"Expected 7 deps, got {len(deps)}"
for k in REQUIRED_KEYS:
    assert k in deps, f"Missing dependency key: {k}"

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
for k in REQUIRED_KEYS:
    assert k in summary
    assert isinstance(summary[k].get("description"), str)
    assert isinstance(summary[k].get("class"), str)

# ── Stubs must not create state files ────────────────────────────────────────
STATE = ROOT / "penthouse" / "kernel_installation_socket" / "rebased_kernel" / "state"
if STATE.exists():
    sqlite_files = list(STATE.glob("*.sqlite"))
    assert len(sqlite_files) == 0, \
        f"Stubs created SQLite state files: {[f.name for f in sqlite_files]}"

# ── Forbidden active kernel paths absent ─────────────────────────────────────
for fp in FORBIDDEN_ACTIVE_PATHS:
    assert not fp.exists(), f"FORBIDDEN path found: {fp}"

print("REBASED KERNEL DEPENDENCY CONTRACT TEST PASSED")
print(f"  Stubs verified        : {len(REQUIRED_KEYS)}")
for k in REQUIRED_KEYS:
    print(f"  {k:20s}: {summary[k]['class']}")
print(f"  make_reflection_deps  : returns all 7")
print(f"  No external calls     : confirmed")
print(f"  No state files written: confirmed")
print(f"  No forbidden imports  : confirmed")
