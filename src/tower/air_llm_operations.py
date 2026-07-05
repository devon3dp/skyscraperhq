from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "air_llm_operations.sqlite"

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_health (
    provider TEXT PRIMARY KEY,
    display_name TEXT,
    socket_id TEXT,
    location TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER,
    last_checked_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS provider_capabilities (
    provider TEXT PRIMARY KEY,
    display_name TEXT,
    socket_id TEXT,
    capabilities_json TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER
);

CREATE TABLE IF NOT EXISTS handoff_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    provider TEXT,
    source_floor TEXT,
    target_floor TEXT,
    socket_id TEXT,
    status TEXT,
    details TEXT
);
"""

class AirLLMOperations:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sync(self):
        caps = load_json("external_provider_capabilities.json", [])
        sockets = load_json("provider_sockets.json", [])

        socket_by_provider = {}
        for s in sockets:
            if s.get("building_floor") == "floor_23":
                socket_by_provider[s.get("provider")] = s

        for cap in caps:
            provider = cap["provider"]
            sock = socket_by_provider.get(provider, {})
            socket_id = cap.get("socket_id") or sock.get("id")
            display = cap.get("display_name", provider)
            location = cap.get("location", sock.get("location", "external_provider"))
            status = cap.get("status", sock.get("status", "not_connected"))

            self.conn.execute(
                "INSERT OR REPLACE INTO provider_health VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    display,
                    socket_id,
                    location,
                    status,
                    int(bool(cap.get("execution_enabled", False))),
                    int(bool(cap.get("hardwired", False))),
                    now(),
                    "Socket registered. External execution disabled."
                )
            )

            self.conn.execute(
                "INSERT OR REPLACE INTO provider_capabilities VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    display,
                    socket_id,
                    json.dumps(cap.get("capabilities", [])),
                    status,
                    int(bool(cap.get("execution_enabled", False))),
                    int(bool(cap.get("hardwired", False)))
                )
            )

        self.conn.commit()

    def health(self):
        rows = self.conn.execute("SELECT * FROM provider_health ORDER BY provider").fetchall()
        return [dict(r) for r in rows]

    def capabilities(self):
        rows = self.conn.execute("SELECT * FROM provider_capabilities ORDER BY provider").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            output.append(item)
        return output

    def handoff_paths(self):
        return load_json("external_handoff_paths.json", [])

    def record_handoff(self, provider, source_floor="floor_24", target_floor="floor_23", details=None):
        details = details or {}
        socket = None
        for cap in self.capabilities():
            if cap["provider"] == provider:
                socket = cap.get("socket_id")
                break

        status = "prepared_not_executed"
        self.conn.execute(
            "INSERT INTO handoff_events(ts, provider, source_floor, target_floor, socket_id, status, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now(), provider, source_floor, target_floor, socket, status, json.dumps(details))
        )
        self.conn.commit()

        return {
            "provider": provider,
            "source_floor": source_floor,
            "target_floor": target_floor,
            "socket_id": socket,
            "status": status,
            "execution_enabled": False
        }

    def recent_handoffs(self, limit=20):
        rows = self.conn.execute("SELECT * FROM handoff_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def refresh_provider_health(self):
        self.sync()
        results = []
        for h in self.health():
            status = h["status"]
            if h["provider"] == "future_models":
                status = "expansion_ready"
            elif h["provider"] == "air_llm_cloud":
                status = "socket_ready_not_connected"
            else:
                status = "socket_ready_not_connected"

            self.conn.execute(
                "UPDATE provider_health SET status=?, last_checked_ts=?, notes=? WHERE provider=?",
                (status, now(), "Health simulated. No external call performed.", h["provider"])
            )
            results.append({
                "provider": h["provider"],
                "status": status,
                "external_call_performed": False
            })

        self.conn.commit()
        return results

    def dashboard(self):
        self.sync()
        health = self.health()
        caps = self.capabilities()
        paths = self.handoff_paths()

        return {
            "database": str(DB),
            "floor": "floor_23",
            "department": "AIR LLM Operations Department",
            "version": "1.1",
            "providers_are_external": True,
            "execution_enabled": False,
            "hardwired_providers": False,
            "models_required": False,
            "kernel_required": False,
            "incoming_lift": "model_lift",
            "roof_link": "AIR LLM Cloud external layer",
            "provider_count": len(health),
            "socket_count": len([p for p in health if p.get("socket_id")]),
            "health": health,
            "capabilities": caps,
            "handoff_paths": paths,
            "recent_handoffs": self.recent_handoffs(10)
        }

if __name__ == "__main__":
    dept = AirLLMOperations()
    print(json.dumps(dept.dashboard(), indent=2))
