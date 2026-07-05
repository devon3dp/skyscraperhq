from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_skyscraper")

def write(path, text):
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text.lstrip(), encoding="utf-8")

# ============================================================
# SEMANTIC MEMORY CORE
# ============================================================

write("memory/semantic_memory.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import sqlite3
import json
import math
import requests
import yaml

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
DB = ROOT / "memory" / "qsb_semantic_memory.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT,
    text TEXT NOT NULL,
    model TEXT,
    embedding_json TEXT
);
"""

class SemanticMemoryCore:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

        cfg_path = ROOT / "config" / "offline_models.yaml"
        cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
        self.ollama_url = cfg.get("qsb", {}).get("ollama_url", "http://127.0.0.1:11434")
        self.model = cfg.get("models", {}).get("memory", "nomic-embed-text:latest")

    def now(self):
        return datetime.now(UTC).isoformat()

    def embed(self, text):
        url = self.ollama_url.rstrip("/") + "/api/embeddings"
        payload = {"model": self.model, "prompt": text}
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        emb = data.get("embedding")
        if emb is None:
            emb = data.get("embeddings", [[]])[0]
        return emb

    def add(self, source, text):
        if not text or not text.strip():
            return None
        embedding = self.embed(text)
        self.conn.execute(
            "INSERT INTO semantic_memories(ts, source, text, model, embedding_json) VALUES (?, ?, ?, ?, ?)",
            (self.now(), source, text, self.model, json.dumps(embedding))
        )
        self.conn.commit()
        return {"source": source, "text": text, "model": self.model, "dimensions": len(embedding)}

    def cosine(self, a, b):
        if not a or not b:
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(y*y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query, limit=5):
        qemb = self.embed(query)
        rows = self.conn.execute(
            "SELECT id, ts, source, text, model, embedding_json FROM semantic_memories ORDER BY id DESC"
        ).fetchall()

        scored = []
        for r in rows:
            try:
                emb = json.loads(r["embedding_json"])
                score = self.cosine(qemb, emb)
                scored.append({
                    "id": r["id"],
                    "ts": r["ts"],
                    "source": r["source"],
                    "model": r["model"],
                    "score": round(score, 4),
                    "text": r["text"][:1000]
                })
            except Exception:
                continue

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def dashboard(self):
        count = self.conn.execute("SELECT COUNT(*) AS c FROM semantic_memories").fetchone()["c"]
        recent = self.conn.execute(
            "SELECT id, ts, source, model, text FROM semantic_memories ORDER BY id DESC LIMIT 10"
        ).fetchall()
        return {
            "database": str(DB),
            "embedding_model": self.model,
            "memories": count,
            "recent": [dict(r) for r in recent]
        }
''')

# ============================================================
# BELIEF ENGINE INSIDE LOCKED KERNEL
# ============================================================

write("kernel/belief_core.py", r'''
from pathlib import Path
from datetime import datetime, UTC
import sqlite3
import json

ROOT = Path("/vaults/nvme0/qsb_skyscraper")
DB = ROOT / "kernel" / "qsb_beliefs.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS beliefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    updated_ts TEXT NOT NULL,
    belief TEXT UNIQUE NOT NULL,
    state TEXT DEFAULT 'PROVISIONAL',
    confidence REAL DEFAULT 0.3,
    evidence_count INTEGER DEFAULT 0,
    counter_evidence_count INTEGER DEFAULT 0,
    last_evidence TEXT
);

CREATE TABLE IF NOT EXISTS belief_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    belief TEXT NOT NULL,
    evidence TEXT,
    delta REAL
);
"""

class BeliefCore:
    SEED_BELIEFS = [
        ("QSB is not a model.", 0.95, "core axiom"),
        ("QSB is the persistent locked kernel above models.", 0.9, "core architecture"),
        ("Models are replaceable workers.", 0.9, "core architecture"),
        ("Symbolic logic belongs inside the locked Penthouse kernel.", 0.95, "architecture correction"),
        ("Memory supports continuity.", 0.85, "validated by recall after reboot"),
        ("Departments are modular skyscraper floors.", 0.8, "department state floor installed"),
        ("Lifts are controlled communication buses.", 0.8, "lift system installed"),
        ("Knowledge Graph stores relationships but the kernel interprets meaning.", 0.85, "architecture correction"),
        ("Upgrades must preserve continuity.", 0.9, "core axiom"),
        ("Cloud calls remain disabled unless explicitly enabled later.", 0.85, "offline-first rule")
    ]

    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.seed()

    def now(self):
        return datetime.now(UTC).isoformat()

    def seed(self):
        for belief, confidence, evidence in self.SEED_BELIEFS:
            self.assert_belief(belief, confidence, evidence, seed=True)

    def state_for(self, confidence):
        confidence = float(confidence)
        if confidence >= 0.85:
            return "STRENGTHENED"
        if confidence >= 0.6:
            return "ACTIVE"
        if confidence <= 0.2:
            return "DEPRECATED"
        return "PROVISIONAL"

    def assert_belief(self, belief, confidence=0.3, evidence="", seed=False):
        ts = self.now()
        row = self.conn.execute("SELECT * FROM beliefs WHERE belief=?", (belief,)).fetchone()

        if row:
            old = float(row["confidence"])
            new_conf = max(old, float(confidence)) if seed else min(1.0, old + float(confidence) * 0.05)
            state = self.state_for(new_conf)
            self.conn.execute(
                """
                UPDATE beliefs
                SET updated_ts=?, confidence=?, state=?, evidence_count=evidence_count+1, last_evidence=?
                WHERE belief=?
                """,
                (ts, new_conf, state, evidence, belief)
            )
        else:
            state = self.state_for(confidence)
            self.conn.execute(
                """
                INSERT INTO beliefs(ts, updated_ts, belief, state, confidence, evidence_count, counter_evidence_count, last_evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, ts, belief, state, float(confidence), 1, 0, evidence)
            )

        self.conn.execute(
            "INSERT INTO belief_evidence(ts, belief, evidence, delta) VALUES (?, ?, ?, ?)",
            (ts, belief, evidence, confidence)
        )
        self.conn.commit()

    def learn_from_symbolic(self, symbolic_result, evidence_text="symbolic inference"):
        for s, r, o in symbolic_result.get("inferred_relations", []):
            belief = f"{s} {r} {o}"
            self.assert_belief(belief, 0.45, evidence_text)

        for symbol in symbolic_result.get("symbols", []):
            belief = f"Symbol observed: {symbol}"
            self.assert_belief(belief, 0.2, evidence_text)

    def list_beliefs(self, limit=50):
        rows = self.conn.execute(
            "SELECT * FROM beliefs ORDER BY confidence DESC, updated_ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        states = {}
        for state in ["PROVISIONAL", "ACTIVE", "STRENGTHENED", "DEPRECATED", "RETIRED"]:
            states[state] = self.conn.execute(
                "SELECT COUNT(*) AS c FROM beliefs WHERE state=?",
                (state,)
            ).fetchone()["c"]

        total = self.conn.execute("SELECT COUNT(*) AS c FROM beliefs").fetchone()["c"]
        evidence = self.conn.execute("SELECT COUNT(*) AS c FROM belief_evidence").fetchone()["c"]

        return {
            "database": str(DB),
            "total_beliefs": total,
            "evidence_events": evidence,
            "states": states,
            "top_beliefs": self.list_beliefs(10)
        }
''')

# ============================================================
# REFLECTION ENGINE INSIDE LOCKED KERNEL
# ============================================================

write("kernel/reflection_core.py", r'''
from datetime import datetime, UTC

class ReflectionCore:
    def __init__(self, memory, departments, missions, lifts, graph, beliefs, semantic):
        self.memory = memory
        self.departments = departments
        self.missions = missions
        self.lifts = lifts
        self.graph = graph
        self.beliefs = beliefs
        self.semantic = semantic

    def now(self):
        return datetime.now(UTC).isoformat()

    def reflect(self):
        memory_summary = self.memory.summary()
        dept_summary = self.departments.dashboard()
        mission_summary = self.missions.dashboard()
        lift_summary = self.lifts.dashboard()

        lessons = []

        lessons.append(f"Memory contains {memory_summary.get('events', 0)} events and {memory_summary.get('facts', 0)} facts.")
        lessons.append(f"Department floor contains {dept_summary.get('department_count', 0)} departments with average health {dept_summary.get('average_health', 0)}.")
        lessons.append(f"Mission floor contains {mission_summary.get('active_missions', 0)} active missions.")
        lessons.append(f"Lift system has recorded {lift_summary.get('total_lift_events', 0)} internal events.")

        if memory_summary.get("events", 0) > 0:
            self.beliefs.assert_belief("QSB is accumulating persistent operational memory.", 0.5, "reflection over memory events")

        if dept_summary.get("department_count", 0) >= 5:
            self.beliefs.assert_belief("QSB skyscraper departments are structurally online.", 0.5, "reflection over department dashboard")

        if lift_summary.get("total_lift_events", 0) > 0:
            self.beliefs.assert_belief("QSB lift system is recording internal communication.", 0.5, "reflection over lift dashboard")

        if mission_summary.get("active_missions", 0) >= 1:
            self.beliefs.assert_belief("QSB mission floor is tracking long-running work.", 0.45, "reflection over mission dashboard")

        reflection_text = "\n".join(lessons)

        try:
            self.semantic.add("reflection", reflection_text)
        except Exception:
            pass

        self.graph.add_edge("Reflection Engine", "reviewed", "Memory Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Department State Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Mission Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Lift System", 1.0, "reflection")

        return {
            "ts": self.now(),
            "lessons": lessons,
            "belief_dashboard": self.beliefs.dashboard()
        }
''')

# ============================================================
# PATCH KERNEL CORE
# ============================================================

kernel_core = ROOT / "kernel" / "kernel_core.py"
text = kernel_core.read_text(encoding="utf-8")

if "from kernel.belief_core import BeliefCore" not in text:
    text = text.replace(
        "from kernel.symbolic_core import SymbolicLogicCore",
        "from kernel.symbolic_core import SymbolicLogicCore\nfrom kernel.belief_core import BeliefCore"
    )

if "self.beliefs = BeliefCore()" not in text:
    text = text.replace(
        "        self.symbols = SymbolicLogicCore()",
        "        self.symbols = SymbolicLogicCore()\n        self.beliefs = BeliefCore()"
    )

if '"beliefs": self.beliefs.dashboard()' not in text:
    text = text.replace(
        '            "symbolic_core": self.symbols.dashboard()',
        '            "symbolic_core": self.symbols.dashboard(),\n            "beliefs": self.beliefs.dashboard()'
    )

if "self.beliefs.learn_from_symbolic" not in text:
    text = text.replace(
        "        symbolic_result = self.symbols.observe(source, text)",
        "        symbolic_result = self.symbols.observe(source, text)\n        self.beliefs.learn_from_symbolic(symbolic_result, evidence_text=text)"
    )

kernel_core.write_text(text, encoding="utf-8")

# ============================================================
# REWRITE PENTHOUSE WITH COGNITIVE KERNEL 4.7 FEATURES
# ============================================================

write("executive/penthouse.py", r'''
from pathlib import Path
import sys
import json
from datetime import datetime, UTC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.router.router import QSBRouter
from memory.memory_core import MemoryCore
from memory.semantic_memory import SemanticMemoryCore
from departments.department_core import DepartmentCore
from missions.mission_core import MissionCore
from bus.lift_core import LiftSystem
from knowledge.graph_core import KnowledgeGraph
from kernel.kernel_core import QSBKernelCore
from kernel.reflection_core import ReflectionCore

SYSTEM = """You are the local offline QSB Penthouse.
You coordinate the skyscraper departments.
You only use local Ollama models.
You do not call cloud providers.
You preserve memory, continuity, department state, missions, lifts, knowledge graph, symbolic logic, beliefs, and semantic memory."""

def log(row):
    row["ts"] = datetime.now(UTC).isoformat()
    with open(ROOT / "logs" / "penthouse.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def main():
    router = QSBRouter()
    memory = MemoryCore()
    semantic = SemanticMemoryCore()
    departments = DepartmentCore()
    missions = MissionCore()
    lifts = LiftSystem()
    graph = KnowledgeGraph()
    graph.seed_core_architecture()
    kernel = QSBKernelCore()
    symbols = kernel.symbols
    beliefs = kernel.beliefs
    reflector = ReflectionCore(memory, departments, missions, lifts, graph, beliefs, semantic)

    memory.boot()

    lifts.emit("event_bus", "system", "penthouse", "boot", {"status": "Penthouse booted"})
    lifts.emit("memory_bus", "penthouse", "memory", "boot", {"status": "Memory Floor online"})
    lifts.emit("department_bus", "penthouse", "departments", "boot", {"status": "Department Floor online"})
    lifts.emit("mission_bus", "penthouse", "missions", "boot", {"status": "Mission Floor online"})
    lifts.emit("knowledge_bus", "penthouse", "knowledge", "boot", {"status": "Knowledge Graph Floor online"})
    lifts.emit("symbolic_bus", "penthouse", "kernel", "boot", {"status": "Kernel Symbolic Core online"})

    print("QSB Offline Penthouse online.")
    print("Memory Floor online.")
    print("Semantic Memory online.")
    print("Department State Floor online.")
    print("Mission Floor online.")
    print("Lift System online.")
    print("Knowledge Graph Floor online.")
    print("Kernel Core online.")
    print("Kernel Symbolic Core online.")
    print("Belief Engine online.")
    print("Reflection Engine online.")
    print("Commands: /health, /models, /constitution, /departments, /dept NAME, /deptdash, /memory, /recent, /semdash, /semadd TEXT, /semsearch TEXT, /missiondash, /missions, /mission ID, /newmission TITLE | DESCRIPTION | DEPARTMENT | PRIORITY, /assignmission ID DEPARTMENT, /closemission ID | OUTCOME, /liftdash, /lifts, /kgdash, /kgnodes, /kgedges, /kgfind TERM, /kgadd SUBJECT | RELATION | OBJECT, /kgseed, /kernel, /axioms, /continuity, /symdash, /sym TEXT, /symfind TERM, /beliefdash, /beliefs, /believe TEXT | CONFIDENCE | EVIDENCE, /reflect, /remember KEY=VALUE, /recall KEY, /exit")
    print("Prefixes: code: | heavy: | research: | vision: | penthouse:")

    while True:
        msg = input("Penthouse> ").strip()

        if msg in ["/exit", "exit", "quit"]:
            lifts.emit("event_bus", "user", "penthouse", "exit", {})
            break

        if msg == "/health":
            h = router.health()
            lifts.emit("provider_bus", "penthouse", "ollama", "health_check", h)
            print(json.dumps(h, indent=2))
            continue

        if msg == "/memory":
            s = memory.summary()
            print(json.dumps(s, indent=2))
            continue

        if msg == "/recent":
            print(json.dumps(memory.recent_events(10), indent=2))
            continue

        if msg == "/semdash":
            print(json.dumps(semantic.dashboard(), indent=2))
            continue

        if msg.startswith("/semadd "):
            text_to_store = msg.replace("/semadd ", "", 1).strip()
            try:
                result = semantic.add("manual", text_to_store)
                print(json.dumps(result, indent=2))
            except Exception as e:
                print(f"Semantic memory error: {e}")
            continue

        if msg.startswith("/semsearch "):
            query = msg.replace("/semsearch ", "", 1).strip()
            try:
                print(json.dumps(semantic.search(query, 5), indent=2))
            except Exception as e:
                print(f"Semantic search error: {e}")
            continue

        if msg == "/deptdash":
            print(json.dumps(departments.dashboard(), indent=2))
            continue

        if msg.startswith("/dept "):
            name = msg.replace("/dept ", "", 1).strip()
            info = departments.get_department(name)
            print(json.dumps(info, indent=2) if info else "Department not found.")
            continue

        if msg == "/missiondash":
            print(json.dumps(missions.dashboard(), indent=2))
            continue

        if msg == "/missions":
            print(json.dumps(missions.list_missions(20), indent=2))
            continue

        if msg.startswith("/mission "):
            try:
                mission_id = int(msg.replace("/mission ", "", 1).strip())
                info = missions.get_mission(mission_id)
                print(json.dumps(info, indent=2) if info else "Mission not found.")
            except ValueError:
                print("Use: /mission ID")
            continue

        if msg.startswith("/newmission "):
            payload = msg.replace("/newmission ", "", 1)
            parts = [p.strip() for p in payload.split("|")]
            title = parts[0] if len(parts) > 0 and parts[0] else "Untitled mission"
            description = parts[1] if len(parts) > 1 else ""
            department = parts[2] if len(parts) > 2 and parts[2] else "penthouse"
            try:
                priority = float(parts[3]) if len(parts) > 3 else 0.5
            except ValueError:
                priority = 0.5
            mission = missions.create_mission(title, description, department, priority)
            print(json.dumps(mission, indent=2))
            continue

        if msg.startswith("/assignmission "):
            parts = msg.replace("/assignmission ", "", 1).strip().split()
            if len(parts) < 2:
                print("Use: /assignmission ID DEPARTMENT")
                continue
            try:
                print(json.dumps(missions.assign_mission(int(parts[0]), parts[1]), indent=2))
            except ValueError:
                print("Use: /assignmission ID DEPARTMENT")
            continue

        if msg.startswith("/closemission "):
            payload = msg.replace("/closemission ", "", 1).strip()
            parts = [p.strip() for p in payload.split("|", 1)]
            try:
                mission = missions.close_mission(int(parts[0]), parts[1] if len(parts) > 1 else "")
                print(json.dumps(mission, indent=2))
            except ValueError:
                print("Use: /closemission ID | OUTCOME")
            continue

        if msg == "/liftdash":
            print(json.dumps(lifts.dashboard(), indent=2))
            continue

        if msg == "/lifts":
            print(json.dumps(lifts.recent(30), indent=2))
            continue

        if msg == "/kgdash":
            print(json.dumps(graph.dashboard(), indent=2))
            continue

        if msg == "/kgnodes":
            print(json.dumps(graph.nodes(50), indent=2))
            continue

        if msg == "/kgedges":
            print(json.dumps(graph.edges(50), indent=2))
            continue

        if msg.startswith("/kgfind "):
            print(json.dumps(graph.find(msg.replace("/kgfind ", "", 1).strip()), indent=2))
            continue

        if msg.startswith("/kgadd "):
            parts = [p.strip() for p in msg.replace("/kgadd ", "", 1).split("|")]
            if len(parts) < 3:
                print("Use: /kgadd SUBJECT | RELATION | OBJECT")
                continue
            graph.add_edge(parts[0], parts[1], parts[2], 1.0, "manual entry from Penthouse")
            print(f"Added: {parts[0]} --{parts[1]}--> {parts[2]}")
            continue

        if msg == "/kgseed":
            graph.seed_core_architecture()
            print("Knowledge Graph core architecture seeded.")
            continue

        if msg == "/kernel":
            print(json.dumps(kernel.status(), indent=2))
            continue

        if msg == "/axioms":
            print(json.dumps(kernel.axioms.list_axioms(), indent=2))
            continue

        if msg == "/continuity":
            print(json.dumps(kernel.boot_state, indent=2))
            continue

        if msg == "/symdash":
            print(json.dumps(symbols.dashboard(), indent=2))
            continue

        if msg.startswith("/sym "):
            text_to_parse = msg.replace("/sym ", "", 1).strip()
            result = kernel.analyze(text_to_parse, source="manual")
            symbolic_result = result["symbolic_result"]
            beliefs.learn_from_symbolic(symbolic_result, evidence_text=text_to_parse)

            for s, r, o in symbolic_result.get("inferred_relations", []):
                graph.add_edge(s, r, o, 1.0, "symbolic inference")

            print(json.dumps(result, indent=2))
            continue

        if msg.startswith("/symfind "):
            term = msg.replace("/symfind ", "", 1).strip()
            print(json.dumps(symbols.find(term), indent=2))
            continue

        if msg == "/beliefdash":
            print(json.dumps(beliefs.dashboard(), indent=2))
            continue

        if msg == "/beliefs":
            print(json.dumps(beliefs.list_beliefs(50), indent=2))
            continue

        if msg.startswith("/believe "):
            payload = msg.replace("/believe ", "", 1)
            parts = [p.strip() for p in payload.split("|")]
            belief = parts[0] if len(parts) > 0 else ""
            try:
                confidence = float(parts[1]) if len(parts) > 1 else 0.4
            except ValueError:
                confidence = 0.4
            evidence = parts[2] if len(parts) > 2 else "manual belief"
            beliefs.assert_belief(belief, confidence, evidence)
            print("Belief recorded.")
            continue

        if msg == "/reflect":
            print(json.dumps(reflector.reflect(), indent=2))
            continue

        if msg.startswith("/remember "):
            payload = msg.replace("/remember ", "", 1)
            if "=" not in payload:
                print("Use: /remember key=value")
                continue
            key, value = payload.split("=", 1)
            memory.set_fact(key.strip(), value.strip())
            print(f"Remembered: {key.strip()} = {value.strip()}")
            continue

        if msg.startswith("/recall "):
            key = msg.replace("/recall ", "", 1).strip()
            value = memory.get_fact(key)
            print(value if value is not None else "No memory found for that key.")
            continue

        if msg == "/models":
            print((ROOT / "config" / "offline_models.yaml").read_text())
            continue

        if msg == "/constitution":
            print((ROOT / "config" / "constitution.md").read_text())
            continue

        if msg == "/departments":
            names = [d["name"] for d in departments.list_departments()]
            print(json.dumps(names, indent=2))
            continue

        if not msg:
            continue

        task = "fast_chat"
        dept = "penthouse"
        prompt = msg

        if msg.startswith("code:"):
            task = "coding"
            dept = "software"
            prompt = msg.split("code:", 1)[1].strip()
        elif msg.startswith("heavy:"):
            task = "heavy_coding"
            dept = "software"
            prompt = msg.split("heavy:", 1)[1].strip()
        elif msg.startswith("research:"):
            task = "research"
            dept = "research"
            prompt = msg.split("research:", 1)[1].strip()
        elif msg.startswith("vision:"):
            task = "vision"
            dept = "vision"
            prompt = msg.split("vision:", 1)[1].strip()
        elif msg.startswith("penthouse:"):
            task = "penthouse"
            dept = "penthouse"
            prompt = msg.split("penthouse:", 1)[1].strip()

        lifts.emit("event_bus", "user", "penthouse", "prompt_received", {"task": task, "department": dept})

        kernel_analysis = kernel.analyze(prompt, source="prompt")
        symbolic_result = kernel_analysis["symbolic_result"]

        beliefs.learn_from_symbolic(symbolic_result, evidence_text=prompt)

        for s, r, o in symbolic_result.get("inferred_relations", []):
            graph.add_edge(s, r, o, 1.0, "automatic symbolic inference")

        for symbol in symbolic_result.get("symbols", []):
            graph.add_edge(dept, "observed_symbol", symbol, 1.0, "automatic symbolic observation")

        try:
            semantic.add("prompt", prompt)
        except Exception:
            pass

        departments.update_department(dept, status="working", health=98, last_task=prompt)
        lifts.emit("department_bus", "penthouse", dept, "assign_task", {"task": task, "prompt": prompt})

        result = router.ask(prompt, task, SYSTEM)

        departments.update_department(dept, status="online", health=100, last_task=prompt)
        lifts.emit("provider_bus", dept, result["model"], "model_response", {"provider": result["provider"], "task": task})

        missions.record_activity(department=dept, task=task, prompt=prompt, model=result["model"], note="Prompt routed through Cognitive Kernel 4.7")

        memory.remember_event(
            source="penthouse",
            task=task,
            model=result["model"],
            user_input=msg,
            response=result["response"]
        )

        try:
            semantic.add("response", result["response"])
        except Exception:
            pass

        lifts.emit("memory_bus", "penthouse", "memory", "remember_event", {"task": task, "model": result["model"]})
        lifts.emit("mission_bus", "penthouse", "missions", "record_activity", {"department": dept, "task": task})

        print(f"\n[{result['provider']} | {result['model']} | dept:{dept}]\n{result['response']}\n")

        log({
            "input": msg,
            "task": task,
            "department": dept,
            "model": result["model"],
            "response": result["response"]
        })

if __name__ == "__main__":
    main()
''')

# ============================================================
# CONFIG VERSION
# ============================================================

config = ROOT / "config" / "offline_models.yaml"
if config.exists():
    cfg = config.read_text(encoding="utf-8")
    if "version:" in cfg:
        import re
        cfg = re.sub(r"version: .*", "version: 4.7-cognitive-kernel", cfg)
    config.write_text(cfg, encoding="utf-8")

write("kernel/COGNITIVE_47_README.md", """
# QSB Cognitive Kernel 4.7

This upgrade adds:

- Semantic Memory using nomic-embed-text
- Kernel Belief Engine
- Kernel Reflection Engine
- Belief lifecycle states
- Semantic search
- Reflection command
- Integrated symbolic-to-belief learning

New Penthouse commands:

/semdash
/semadd TEXT
/semsearch TEXT
/beliefdash
/beliefs
/believe TEXT | CONFIDENCE | EVIDENCE
/reflect

The QSB can now remember semantically, form beliefs, and reflect over its current state.
""")

print("QSB Cognitive Kernel 4.7 upgrade installed.")
print("Run:")
print("cd /vaults/nvme0/qsb_skyscraper")
print("./run_penthouse.sh")
