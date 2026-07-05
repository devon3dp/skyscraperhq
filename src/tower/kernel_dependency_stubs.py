"""
QSB Tower V1.3 — Kernel Dependency Stubs

Inert placeholder classes for ReflectionCore dependency injection.

ReflectionCore.__init__ requires:
  memory, departments, missions, lifts, graph, beliefs, semantic

These stubs implement the minimum required interface using empty, safe
return values.  They MUST NOT:
  - call models, providers, workers, or external systems
  - import or instantiate any kernel class
  - import from old qsb_skyscraper modules
  - write to any database or file (all stubs are stateless)
  - call Ollama, Claude, OpenAI, or any network endpoint

They MAY:
  - return empty lists, dicts, or neutral status summaries
  - log nothing (silent)
  - expose a describe() method for inspection
"""


class MemoryDependencyStub:
    """Stub for memory.memory_core.MemoryCore."""

    def summary(self):
        return {
            "stub": True,
            "events": 0,
            "facts": 0,
            "status": "stub_no_memory_core_yet",
        }

    def recent(self, limit=10):
        return []

    def boot(self):
        pass

    def add(self, key, value):
        pass

    def recall(self, key):
        return None

    def describe(self):
        return "MemoryDependencyStub — inert placeholder, no data stored"


class DepartmentDependencyStub:
    """Stub for departments.department_core.DepartmentCore."""

    def dashboard(self):
        return {
            "stub": True,
            "department_count": 0,
            "average_health": 0,
            "departments": [],
            "status": "stub_no_department_core_yet",
        }

    def list_departments(self):
        return []

    def describe(self):
        return "DepartmentDependencyStub — inert placeholder, no department data"


class MissionDependencyStub:
    """Stub for missions.mission_core.MissionCore."""

    def dashboard(self):
        return {
            "stub": True,
            "active_missions": 0,
            "completed_missions": 0,
            "missions": [],
            "status": "stub_no_mission_core_yet",
        }

    def list_missions(self):
        return []

    def describe(self):
        return "MissionDependencyStub — inert placeholder, no mission data"


class LiftDependencyStub:
    """Stub for bus.lift_core.LiftSystem (old) / tower.lifts.LiftNetwork (new)."""

    def dashboard(self):
        return {
            "stub": True,
            "total_lift_events": 0,
            "lifts": [],
            "status": "stub_no_lift_system_yet",
        }

    def emit(self, bus, source, target, event, payload=None):
        # Old LiftSystem.emit signature — silently ignored
        pass

    def send(self, lift_id, source, target, payload=None):
        # New LiftNetwork.send signature — silently ignored
        pass

    def states(self):
        return []

    def packets(self):
        return []

    def describe(self):
        return "LiftDependencyStub — inert placeholder, no lift events emitted"


class GraphDependencyStub:
    """Stub for knowledge.graph_core.KnowledgeGraph."""

    def add_edge(self, subject, relation, obj, weight=1.0, source="stub"):
        # Silently ignored
        pass

    def add_node(self, name, node_type="concept"):
        pass

    def seed_core_architecture(self):
        pass

    def dashboard(self):
        return {
            "stub": True,
            "nodes": 0,
            "edges": 0,
            "status": "stub_no_knowledge_graph_yet",
        }

    def find(self, term, limit=10):
        return []

    def describe(self):
        return "GraphDependencyStub — inert placeholder, no graph edges stored"


class BeliefDependencyStub:
    """Stub for kernel.belief_core.BeliefCore (for ReflectionCore injection only)."""

    def assert_belief(self, belief, confidence=0.3, evidence="", seed=False):
        # Silently ignored — no database write
        pass

    def list_beliefs(self, limit=50):
        return []

    def dashboard(self):
        return {
            "stub": True,
            "total_beliefs": 0,
            "evidence_events": 0,
            "states": {
                "PROVISIONAL": 0, "ACTIVE": 0,
                "STRENGTHENED": 0, "DEPRECATED": 0, "RETIRED": 0,
            },
            "top_beliefs": [],
            "status": "stub_no_belief_engine_yet",
        }

    def describe(self):
        return "BeliefDependencyStub — inert placeholder, no beliefs stored"


class SemanticDependencyStub:
    """Stub for memory.semantic_memory.SemanticMemoryCore."""

    def add(self, source, text):
        # Silently ignored — no Ollama call, no database write
        pass

    def search(self, query, limit=5):
        return []

    def dashboard(self):
        return {
            "stub": True,
            "semantic_memories": 0,
            "embedding_model": "none_stub",
            "status": "stub_no_semantic_memory_yet",
        }

    def describe(self):
        return "SemanticDependencyStub — inert placeholder, no Ollama calls, no embeddings"


def make_reflection_deps():
    """
    Return all seven dependency stubs as a dict ready for ReflectionCore injection.
    All stubs are inert — no external calls, no database writes, no model calls.
    """
    return {
        "memory":      MemoryDependencyStub(),
        "departments": DepartmentDependencyStub(),
        "missions":    MissionDependencyStub(),
        "lifts":       LiftDependencyStub(),
        "graph":       GraphDependencyStub(),
        "beliefs":     BeliefDependencyStub(),
        "semantic":    SemanticDependencyStub(),
    }


def stub_summary():
    """Return a status summary of all stubs — safe to call at any time."""
    stubs = make_reflection_deps()
    return {
        name: {"class": type(stub).__name__, "description": stub.describe()}
        for name, stub in stubs.items()
    }
