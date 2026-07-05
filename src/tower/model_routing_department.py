from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "model_routing_department.sqlite"
CODING_DB = ROOT / "data" / "db" / "coding_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS route_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    source_system TEXT,
    source_request_id INTEGER,
    request_type TEXT,
    origin_floor TEXT,
    routing_floor TEXT,
    selected_target TEXT,
    selected_lift TEXT,
    selected_socket TEXT,
    selected_model TEXT,
    fallback_target TEXT,
    emergency_target TEXT,
    execution_enabled INTEGER,
    status TEXT,
    lift_receipt TEXT,
    notes TEXT,
    UNIQUE(source_system, source_request_id)
);

CREATE TABLE IF NOT EXISTS routing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    details TEXT
);
"""

class ModelRoutingDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def policies(self):
        return load_json("model_routing_policies.json", [])

    def worker_slots(self):
        return load_json("model_routing_worker_slots.json", [])

    def discovered_local_models(self):
        return load_json("discovered_ollama_models.json", [])

    def sockets(self):
        return load_json("provider_sockets.json", [])

    def policy_for(self, request_type):
        policies = self.policies()
        for p in policies:
            if p["request_type"] == request_type:
                return p
        for p in policies:
            if p["request_type"] == "general":
                return p
        return {
            "request_type": request_type,
            "origin_floor": "ground",
            "routing_floor": "floor_24",
            "preferred_target": "floor_27",
            "fallback_target": "floor_23",
            "emergency_target": "roof",
            "preferred_lift": "model_lift",
            "execution_enabled": False,
            "direct_provider_access": False,
            "selection_rule": "Default safe routing policy."
        }

    def choose_socket_and_model(self, request_type):
        models = self.discovered_local_models()
        names = [m.get("name", "") for m in models]

        coding_markers = ["coder", "codellama", "deepseek"]
        vision_markers = ["llava", "vision"]
        general_markers = ["qwen", "llama", "mistral", "neural"]

        if request_type in ["coding", "code_generation", "bug_fix", "refactor", "code_review", "test_generation"]:
            for name in names:
                if any(marker in name.lower() for marker in coding_markers):
                    return "floor_27", "ollama_local_socket", name

        if request_type == "vision":
            for name in names:
                if any(marker in name.lower() for marker in vision_markers):
                    return "floor_27", "ollama_local_socket", name

        if request_type == "claude_code_handoff":
            return "floor_23", "claude_socket", None

        for name in names:
            if any(marker in name.lower() for marker in general_markers):
                return "floor_27", "ollama_local_socket", name

        return "floor_23", "air_llm_cloud_socket", None

    def create_route_decision(self, source_system, source_request_id, request_type, origin_floor, title="", description=""):
        existing = self.conn.execute(
            "SELECT * FROM route_decisions WHERE source_system=? AND source_request_id=?",
            (source_system, source_request_id)
        ).fetchone()
        if existing:
            return dict(existing)

        policy = self.policy_for(request_type)
        selected_target, selected_socket, selected_model = self.choose_socket_and_model(request_type)

        fallback_target = policy.get("fallback_target", "floor_23")
        emergency_target = policy.get("emergency_target", "roof")
        selected_lift = policy.get("preferred_lift", "model_lift")

        receipt = "not_sent"
        try:
            from tower.lifts import LiftNetwork
            lift_result = LiftNetwork().send("floor_24", selected_target, selected_lift, int(5))
            receipt = json.dumps(lift_result)
        except Exception as e:
            receipt = json.dumps({"error": str(e)})

        notes = {
            "title": title,
            "description": description,
            "selection_rule": policy.get("selection_rule", ""),
            "provider_execution": "disabled",
            "routing_only": True
        }

        self.conn.execute(
            """
            INSERT INTO route_decisions
            (ts, source_system, source_request_id, request_type, origin_floor, routing_floor,
             selected_target, selected_lift, selected_socket, selected_model, fallback_target,
             emergency_target, execution_enabled, status, lift_receipt, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now(), source_system, int(source_request_id), request_type, origin_floor, "floor_24",
                selected_target, selected_lift, selected_socket, selected_model, fallback_target,
                emergency_target, 0, "routed_to_socket_layer", receipt, json.dumps(notes)
            )
        )
        self.conn.commit()

        return dict(self.conn.execute(
            "SELECT * FROM route_decisions WHERE source_system=? AND source_request_id=?",
            (source_system, source_request_id)
        ).fetchone())

    def coding_requests(self):
        if not CODING_DB.exists():
            return []
        c = sqlite3.connect(CODING_DB)
        c.row_factory = sqlite3.Row
        try:
            rows = c.execute("SELECT * FROM coding_requests ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            c.close()

    def process_coding_requests(self, limit=20):
        processed = []
        requests = self.coding_requests()
        for req in requests[:limit]:
            decision = self.create_route_decision(
                source_system="coding_department",
                source_request_id=req["id"],
                request_type=req.get("request_type", "coding"),
                origin_floor=req.get("origin_floor", "floor_05"),
                title=req.get("title", ""),
                description=req.get("description", "")
            )
            processed.append(decision)

        self.conn.execute(
            "INSERT INTO routing_events(ts, event_type, details) VALUES (?, ?, ?)",
            (now(), "process_coding_requests", json.dumps({"processed": len(processed)}))
        )
        self.conn.commit()
        return processed

    def recent_decisions(self, limit=20):
        rows = self.conn.execute("SELECT * FROM route_decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=20):
        rows = self.conn.execute("SELECT * FROM routing_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        total = self.conn.execute("SELECT COUNT(*) AS c FROM route_decisions").fetchone()["c"]
        by_target_rows = self.conn.execute(
            "SELECT selected_target, COUNT(*) AS c FROM route_decisions GROUP BY selected_target ORDER BY c DESC"
        ).fetchall()
        by_socket_rows = self.conn.execute(
            "SELECT selected_socket, COUNT(*) AS c FROM route_decisions GROUP BY selected_socket ORDER BY c DESC"
        ).fetchall()

        return {
            "database": str(DB),
            "floor": "floor_24",
            "department": "Model Routing Department",
            "version": "1.1",
            "execution_enabled": False,
            "direct_provider_access": False,
            "incoming_lift": "service_lift",
            "outgoing_lift": "model_lift",
            "route_decisions": total,
            "policies": self.policies(),
            "worker_slots": self.worker_slots(),
            "by_target": [dict(r) for r in by_target_rows],
            "by_socket": [dict(r) for r in by_socket_rows],
            "recent_decisions": self.recent_decisions(10),
            "recent_events": self.recent_events(10)
        }

if __name__ == "__main__":
    dept = ModelRoutingDepartment()
    print(json.dumps(dept.dashboard(), indent=2))
