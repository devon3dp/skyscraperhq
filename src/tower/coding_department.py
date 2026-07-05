from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "coding_department.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS coding_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    title TEXT,
    request_type TEXT,
    priority INTEGER,
    description TEXT,
    origin_floor TEXT,
    routing_floor TEXT,
    first_lift TEXT,
    status TEXT,
    lift_receipt TEXT
);

CREATE TABLE IF NOT EXISTS patch_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS test_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    request_id INTEGER,
    title TEXT,
    status TEXT,
    notes TEXT
);
"""

class CodingDepartment:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def request_types(self):
        return load_json("coding_request_types.json", [])

    def workspaces(self):
        return load_json("coding_workspaces.json", [])

    def worker_slots(self):
        return load_json("coding_worker_slots.json", [])

    def create_request(self, title, request_type="code_generation", description="", priority=None, send_lift=True):
        types = {t["id"]: t for t in self.request_types()}
        if request_type not in types:
            request_type = "code_generation"

        cfg = types[request_type]
        if priority is None:
            priority = int(cfg.get("default_priority", 5))

        origin = "floor_05"
        routing = cfg.get("routes_to", "floor_24")
        first_lift = cfg.get("first_lift", "service_lift")
        receipt = "not_sent"

        if send_lift:
            try:
                from tower.lifts import LiftNetwork
                lift_result = LiftNetwork().send(origin, routing, first_lift, priority)
                receipt = json.dumps(lift_result)
            except Exception as e:
                receipt = json.dumps({"error": str(e)})

        self.conn.execute(
            """
            INSERT INTO coding_requests
            (ts, title, request_type, priority, description, origin_floor, routing_floor, first_lift, status, lift_receipt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now(), title, request_type, priority, description, origin, routing, first_lift, "queued_for_routing", receipt)
        )
        self.conn.commit()
        request_id = self.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

        queue_title = f"{request_type}: {title}"

        if request_type in ["bug_fix", "refactor", "code_generation", "claude_code_handoff"]:
            self.conn.execute(
                "INSERT INTO patch_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future coding worker.")
            )

        if request_type in ["code_review", "refactor", "claude_code_handoff"]:
            self.conn.execute(
                "INSERT INTO review_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future review worker.")
            )

        if request_type in ["test_generation", "bug_fix", "refactor"]:
            self.conn.execute(
                "INSERT INTO test_queue(ts, request_id, title, status, notes) VALUES (?, ?, ?, ?, ?)",
                (now(), request_id, queue_title, "pending", "Awaiting future test worker.")
            )

        self.conn.commit()
        return self.get_request(request_id)

    def get_request(self, request_id):
        row = self.conn.execute("SELECT * FROM coding_requests WHERE id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def recent_requests(self, limit=20):
        rows = self.conn.execute("SELECT * FROM coding_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def queue_rows(self, table, limit=20):
        rows = self.conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        req_count = self.conn.execute("SELECT COUNT(*) AS c FROM coding_requests").fetchone()["c"]
        patch_count = self.conn.execute("SELECT COUNT(*) AS c FROM patch_queue").fetchone()["c"]
        review_count = self.conn.execute("SELECT COUNT(*) AS c FROM review_queue").fetchone()["c"]
        test_count = self.conn.execute("SELECT COUNT(*) AS c FROM test_queue").fetchone()["c"]

        return {
            "database": str(DB),
            "floor": "floor_05",
            "department": "Coding Department",
            "version": "1.1",
            "direct_provider_access": False,
            "routes_through": "floor_24",
            "first_lift": "service_lift",
            "models_required": False,
            "kernel_required": False,
            "requests": req_count,
            "patch_queue": patch_count,
            "review_queue": review_count,
            "test_queue": test_count,
            "workspaces": self.workspaces(),
            "worker_slots": self.worker_slots(),
            "recent_requests": self.recent_requests(10)
        }

if __name__ == "__main__":
    dept = CodingDepartment()
    print(json.dumps(dept.dashboard(), indent=2))
