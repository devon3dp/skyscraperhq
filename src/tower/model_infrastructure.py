from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3
import shutil
import subprocess

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "model_infrastructure.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_sockets (
    id TEXT PRIMARY KEY,
    provider TEXT,
    display_name TEXT,
    location TEXT,
    building_floor TEXT,
    status TEXT,
    hardwired INTEGER,
    execution_enabled INTEGER
);

CREATE TABLE IF NOT EXISTS model_worker_slots (
    id TEXT PRIMARY KEY,
    name TEXT,
    role TEXT,
    preferred_floor TEXT,
    bound_provider TEXT,
    bound_model TEXT,
    status TEXT,
    hardwired INTEGER
);

CREATE TABLE IF NOT EXISTS model_request_paths (
    id TEXT PRIMARY KEY,
    request_type TEXT,
    origin_floor TEXT,
    first_hop TEXT,
    first_lift TEXT,
    routing_floor TEXT,
    possible_targets_json TEXT,
    second_lift TEXT,
    sealed_packets INTEGER,
    direct_provider_access INTEGER,
    description TEXT
);
"""

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(name, obj):
    path = REG / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

class ModelInfrastructure:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sync(self):
        for s in load_json("provider_sockets.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO provider_sockets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (s["id"], s["provider"], s["display_name"], s["location"], s["building_floor"], s["status"], int(s["hardwired"]), int(s["execution_enabled"]))
            )

        for slot in load_json("model_worker_slots.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO model_worker_slots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (slot["id"], slot["name"], slot["role"], slot["preferred_floor"], slot.get("bound_provider"), slot.get("bound_model"), slot["status"], int(slot["hardwired"]))
            )

        for p in load_json("model_request_paths.json", []):
            self.conn.execute(
                "INSERT OR REPLACE INTO model_request_paths VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["request_type"], p["origin_floor"], p["first_hop"], p["first_lift"], p["routing_floor"], json.dumps(p["possible_targets"]), p["second_lift"], int(p["sealed_packets"]), int(p["direct_provider_access"]), p["description"])
            )

        self.conn.commit()

    def detect_ollama(self):
        if shutil.which("ollama") is None:
            save_json("discovered_ollama_models.json", [])
            return {"available": False, "models": [], "note": "ollama command not found"}

        try:
            output = subprocess.check_output(["ollama", "list"], text=True, stderr=subprocess.STDOUT, timeout=10)
            models = []
            for line in output.splitlines()[1:]:
                parts = line.split()
                if parts:
                    models.append({"name": parts[0], "provider": "ollama", "status": "detected", "detected_ts": now()})
            save_json("discovered_ollama_models.json", models)
            return {"available": True, "models": models, "note": "ollama inventory synced"}
        except Exception as e:
            save_json("discovered_ollama_models.json", [])
            return {"available": False, "models": [], "note": str(e)}

    def sockets(self):
        rows = self.conn.execute("SELECT * FROM provider_sockets ORDER BY building_floor, provider").fetchall()
        return [dict(r) for r in rows]

    def slots(self):
        rows = self.conn.execute("SELECT * FROM model_worker_slots ORDER BY preferred_floor, role").fetchall()
        return [dict(r) for r in rows]

    def paths(self):
        rows = self.conn.execute("SELECT * FROM model_request_paths ORDER BY request_type").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["possible_targets"] = json.loads(item.pop("possible_targets_json"))
            item["sealed_packets"] = bool(item["sealed_packets"])
            item["direct_provider_access"] = bool(item["direct_provider_access"])
            out.append(item)
        return out

    def route_plan(self, request_type):
        matches = [p for p in self.paths() if p["request_type"] == request_type]
        if not matches:
            return {"ok": False, "reason": "unknown_request_type", "request_type": request_type}
        path = matches[0]
        if request_type == "coding":
            wanted = ["coding", "coding_external_port"]
        elif request_type == "vision":
            wanted = ["vision"]
        else:
            wanted = ["general_reasoning", "research"]
        return {
            "ok": True,
            "request_type": request_type,
            "path": path,
            "candidate_slots": [s for s in self.slots() if s["role"] in wanted],
            "execution_enabled": False,
            "note": "Tower V1.1 plans routing only. Provider execution remains disabled."
        }

    def discovered_local_models(self):
        return load_json("discovered_ollama_models.json", [])

    def dashboard(self):
        return {
            "principle": "Models are temporary tenants. The tower owns the infrastructure.",
            "building_runs_without_models": True,
            "hardwired_providers": False,
            "execution_enabled": False,
            "sockets": self.sockets(),
            "worker_slots": self.slots(),
            "request_paths": self.paths(),
            "discovered_local_models": self.discovered_local_models()
        }

if __name__ == "__main__":
    print(json.dumps(ModelInfrastructure().dashboard(), indent=2))
