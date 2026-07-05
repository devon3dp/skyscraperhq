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
