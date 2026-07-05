from pathlib import Path
from datetime import datetime, UTC
import json
import sqlite3
import subprocess
import shutil

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
DB = ROOT / "data" / "db" / "local_model_operations.sqlite"

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
CREATE TABLE IF NOT EXISTS local_models (
    name TEXT PRIMARY KEY,
    provider TEXT,
    primary_role TEXT,
    capabilities_json TEXT,
    size_hint TEXT,
    status TEXT,
    detected_ts TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS role_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    slot_id TEXT,
    recommended_model TEXT,
    role TEXT,
    reason TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS inventory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    event_type TEXT,
    provider TEXT,
    discovered_count INTEGER,
    details TEXT
);
"""

class LocalModelOperations:
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def classify(self, name):
        n = name.lower()
        caps = []

        if "embed" in n or "nomic" in n:
            caps.append("embedding")

        if "llava" in n or "vision" in n:
            caps.append("vision")

        if "coder" in n or "codellama" in n or "deepseek" in n:
            caps.append("coding")

        if "13b" in n or "40b" in n or "iquest" in n:
            caps.append("heavy_coding")

        if "mistral" in n or "qwen" in n or "neural" in n:
            caps.append("research")

        if "qwen" in n or "llama" in n or "mistral" in n or "neural" in n:
            caps.append("general_reasoning")

        if "1b" in n or "3.2" in n or "7b" in n:
            caps.append("fast_fallback")

        if not caps:
            caps.append("general_reasoning")

        priority = ["embedding", "vision", "coding", "heavy_coding", "research", "general_reasoning", "fast_fallback"]
        primary = next((r for r in priority if r in caps), caps[0])

        if "40b" in n:
            size_hint = "large"
        elif "13b" in n:
            size_hint = "medium_large"
        elif "7b" in n or "8b" in n or "9b" in n:
            size_hint = "medium"
        elif "3.2" in n or "1b" in n:
            size_hint = "small"
        elif "embed" in n or "nomic" in n:
            size_hint = "embedding"
        else:
            size_hint = "unknown"

        return primary, caps, size_hint

    def parse_ollama_list(self, output):
        models = []
        lines = output.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            primary, caps, size_hint = self.classify(name)
            models.append({
                "name": name,
                "provider": "ollama",
                "primary_role": primary,
                "capabilities": caps,
                "size_hint": size_hint,
                "status": "detected",
                "detected_ts": now(),
                "notes": "Detected from ollama list."
            })
        return models

    def detect_ollama(self):
        if shutil.which("ollama") is None:
            save_json("local_model_catalog.json", [])
            self.record_event("inventory_failed", "ollama", 0, {"note": "ollama command not found"})
            return {"available": False, "models": [], "note": "ollama command not found"}

        try:
            output = subprocess.check_output(
                ["ollama", "list"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10
            )
            models = self.parse_ollama_list(output)
            self.save_catalog(models)
            self.record_event("inventory_synced", "ollama", len(models), {"source": "ollama list"})
            self.recommend_bindings()
            return {"available": True, "models": models, "note": "local model inventory synced"}
        except Exception as e:
            self.record_event("inventory_failed", "ollama", 0, {"error": str(e)})
            return {"available": False, "models": [], "note": str(e)}

    def sync_from_existing_discovery(self):
        discovered = load_json("discovered_ollama_models.json", [])
        models = []
        for item in discovered:
            name = item.get("name")
            if not name:
                continue
            primary, caps, size_hint = self.classify(name)
            models.append({
                "name": name,
                "provider": "ollama",
                "primary_role": primary,
                "capabilities": caps,
                "size_hint": size_hint,
                "status": "detected",
                "detected_ts": item.get("detected_ts", now()),
                "notes": "Imported from discovered_ollama_models.json."
            })
        self.save_catalog(models)
        self.record_event("inventory_imported", "ollama", len(models), {"source": "discovered_ollama_models.json"})
        self.recommend_bindings()
        return {"available": bool(models), "models": models, "note": "imported existing discovery"}

    def save_catalog(self, models):
        save_json("local_model_catalog.json", models)
        for m in models:
            self.conn.execute(
                "INSERT OR REPLACE INTO local_models VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    m["name"],
                    m["provider"],
                    m["primary_role"],
                    json.dumps(m["capabilities"]),
                    m["size_hint"],
                    m["status"],
                    m["detected_ts"],
                    m.get("notes", "")
                )
            )
        self.conn.commit()

    def record_event(self, event_type, provider, count, details):
        self.conn.execute(
            "INSERT INTO inventory_events(ts, event_type, provider, discovered_count, details) VALUES (?, ?, ?, ?, ?)",
            (now(), event_type, provider, int(count), json.dumps(details))
        )
        self.conn.commit()

    def catalog(self):
        catalog = load_json("local_model_catalog.json", [])
        if catalog:
            return catalog

        rows = self.conn.execute("SELECT * FROM local_models ORDER BY primary_role, name").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            out.append(item)
        return out

    def role_summary(self):
        summary = {}
        for m in self.catalog():
            for cap in m.get("capabilities", []):
                summary[cap] = summary.get(cap, 0) + 1
        return summary

    def pick_model_for_role(self, role):
        models = self.catalog()

        exact = [m for m in models if m.get("primary_role") == role]
        if exact:
            return exact[0]

        capable = [m for m in models if role in m.get("capabilities", [])]
        if capable:
            return capable[0]

        if role == "general_reasoning":
            fallback = [m for m in models if "general_reasoning" in m.get("capabilities", [])]
            if fallback:
                return fallback[0]

        return None

    def recommend_bindings(self):
        slots = load_json("model_worker_slots.json", [])
        role_map = {
            "general_reasoning_slot": "general_reasoning",
            "coding_model_slot": "coding",
            "vision_model_slot": "vision",
            "research_model_slot": "research"
        }

        recommendations = []

        self.conn.execute("DELETE FROM role_recommendations")

        for slot in slots:
            slot_id = slot.get("id")
            wanted = role_map.get(slot_id)
            if not wanted:
                continue

            model = self.pick_model_for_role(wanted)
            if model:
                rec = {
                    "slot_id": slot_id,
                    "role": wanted,
                    "recommended_model": model["name"],
                    "status": "recommended_not_bound",
                    "reason": f"Model has capability for {wanted}. Binding is not automatic."
                }
            else:
                rec = {
                    "slot_id": slot_id,
                    "role": wanted,
                    "recommended_model": None,
                    "status": "no_candidate",
                    "reason": f"No local model candidate found for {wanted}."
                }

            recommendations.append(rec)
            self.conn.execute(
                "INSERT INTO role_recommendations(ts, slot_id, recommended_model, role, reason, status) VALUES (?, ?, ?, ?, ?, ?)",
                (now(), rec["slot_id"], rec["recommended_model"], rec["role"], rec["reason"], rec["status"])
            )

        self.conn.commit()
        save_json("local_model_role_recommendations.json", recommendations)
        return recommendations

    def recommendations(self):
        recs = load_json("local_model_role_recommendations.json", [])
        if recs:
            return recs

        rows = self.conn.execute("SELECT slot_id, recommended_model, role, reason, status FROM role_recommendations ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=10):
        rows = self.conn.execute("SELECT * FROM inventory_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def dashboard(self):
        catalog = self.catalog()
        if not catalog:
            self.sync_from_existing_discovery()
            catalog = self.catalog()

        return {
            "database": str(DB),
            "floor": "floor_27",
            "department": "Local Model Operations Department",
            "version": "1.1",
            "models_required": False,
            "kernel_required": False,
            "execution_enabled": False,
            "hardwired_models": False,
            "incoming_lift": "model_lift",
            "detected_models": len(catalog),
            "role_summary": self.role_summary(),
            "recommendations": self.recommendations(),
            "catalog": catalog,
            "recent_events": self.recent_events(10)
        }

if __name__ == "__main__":
    dept = LocalModelOperations()
    dept.sync_from_existing_discovery()
    print(json.dumps(dept.dashboard(), indent=2))
