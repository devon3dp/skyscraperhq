from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "adapter_systems.sqlite"

def now():
    return datetime.now(UTC).isoformat()

def load_json(name, fallback):
    path = REG / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS adapter_health (
    adapter TEXT PRIMARY KEY,
    socket_id TEXT,
    display_name TEXT,
    adapter_type TEXT,
    target_provider TEXT,
    target_floor TEXT,
    status TEXT,
    execution_enabled INTEGER,
    hardwired INTEGER,
    last_checked_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS adapter_capabilities (
    adapter TEXT PRIMARY KEY,
    socket_id TEXT,
    capabilities_json TEXT,
    execution_enabled INTEGER
);

CREATE TABLE IF NOT EXISTS adapter_handoff_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    adapter TEXT,
    source_floor TEXT,
    target_floor TEXT,
    socket_id TEXT,
    status TEXT,
    details TEXT
);
"""

class AdapterSystems:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.sync()

    def sockets(self):
        return load_json("adapter_sockets.json", [])

    def capability_registry(self):
        return load_json("adapter_capabilities.json", [])

    def handoff_paths(self):
        return load_json("adapter_handoff_paths.json", [])

    def policy(self):
        return load_json("adapter_policy.json", {})

    def sync(self):
        for s in self.sockets():
            self.conn.execute(
                """
                INSERT OR REPLACE INTO adapter_health
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["adapter"],
                    s["id"],
                    s["display_name"],
                    s["adapter_type"],
                    s["target_provider"],
                    s["target_floor"],
                    s["status"],
                    int(bool(s.get("execution_enabled", False))),
                    int(bool(s.get("hardwired", False))),
                    now(),
                    s.get("notes", "Adapter socket registered. Execution disabled.")
                )
            )

        for c in self.capability_registry():
            self.conn.execute(
                "INSERT OR REPLACE INTO adapter_capabilities VALUES (?, ?, ?, ?)",
                (
                    c["adapter"],
                    c["socket_id"],
                    json.dumps(c.get("capabilities", [])),
                    int(bool(c.get("execution_enabled", False)))
                )
            )

        self.conn.commit()

    def health(self):
        rows = self.conn.execute("SELECT * FROM adapter_health ORDER BY adapter").fetchall()
        return [dict(r) for r in rows]

    def capabilities(self):
        rows = self.conn.execute("SELECT * FROM adapter_capabilities ORDER BY adapter").fetchall()
        output = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            output.append(item)
        return output

    def refresh_health(self):
        self.sync()
        results = []
        for h in self.health():
            if h["adapter"] == "future_adapter":
                status = "expansion_ready"
            elif "local" in h["adapter"] or "filesystem" in h["adapter"]:
                status = "socket_ready_disabled"
            else:
                status = "socket_ready_not_connected"

            self.conn.execute(
                "UPDATE adapter_health SET status=?, last_checked_ts=?, notes=? WHERE adapter=?",
                (status, now(), "Health simulated. No adapter execution performed.", h["adapter"])
            )

            results.append({
                "adapter": h["adapter"],
                "status": status,
                "execution_performed": False
            })

        self.conn.commit()
        return results

    def prepare_handoff(self, adapter, source_floor="floor_24", target_floor=None, details=None):
        details = details or {}
        socket_id = None
        target = target_floor

        for s in self.sockets():
            if s["adapter"] == adapter:
                socket_id = s["id"]
                if target is None:
                    target = s["target_floor"]
                break

        status = "prepared_not_executed"

        self.conn.execute(
            """
            INSERT INTO adapter_handoff_events
            (ts, adapter, source_floor, target_floor, socket_id, status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now(), adapter, source_floor, target or "unknown", socket_id, status, json.dumps(details))
        )
        self.conn.commit()

        return {
            "adapter": adapter,
            "source_floor": source_floor,
            "target_floor": target,
            "socket_id": socket_id,
            "status": status,
            "execution_enabled": False
        }

    def recent_handoffs(self, limit=20):
        rows = self.conn.execute("SELECT * FROM adapter_handoff_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        self.sync()
        policy = self.policy()
        health = self.health()
        caps = self.capabilities()

        return {
            "database": str(DB),
            "floor": "floor_21",
            "department": "Adapter Systems Department",
            "version": "1.1",
            "role": "neutral_adapter_socket_layer",
            "execution_enabled": False,
            "hardwired_adapters": False,
            "models_required": False,
            "kernel_required": False,
            "providers_are_external": True,
            "adapter_count": len(health),
            "capability_records": len(caps),
            "handoff_paths": self.handoff_paths(),
            "health": health,
            "capabilities": caps,
            "recent_handoffs": self.recent_handoffs(10),
            "policy": policy
        }

if __name__ == "__main__":
    print(json.dumps(AdapterSystems().dashboard(), indent=2))
