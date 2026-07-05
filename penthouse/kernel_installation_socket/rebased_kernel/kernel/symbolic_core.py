# QSB Tower V1.3 — Rebased Kernel Package
# REBASE CHANGE: ROOT rebased from original source vault
# DB now writes to KERNEL_STATE_ROOT under tower penthouse socket.
from pathlib import Path
import sqlite3
import json
from datetime import datetime, UTC

KERNEL_STATE_ROOT = Path(
    "/vaults/nvme0/qsb_tower_v1/penthouse/kernel_installation_socket/rebased_kernel/state"
)
DB = KERNEL_STATE_ROOT / "symbolic.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS symbolic_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT,
    text TEXT,
    symbols TEXT,
    inferred_relations TEXT,
    meaning TEXT
);

CREATE TABLE IF NOT EXISTS symbolic_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT UNIQUE,
    description TEXT,
    strength REAL DEFAULT 1.0
);
"""

class SymbolicLogicCore:
    CONCEPTS = {
        "qsb": {
            "terms": ["qsb", "quantum symbolic brain"],
            "description": "The local offline cognitive kernel and skyscraper architecture."
        },
        "kernel": {
            "terms": ["kernel", "core", "foundation"],
            "description": "The persistent operating layer that survives model changes."
        },
        "identity": {
            "terms": ["identity", "self", "who am i"],
            "description": "The stable definition of what the QSB is."
        },
        "continuity": {
            "terms": ["continuity", "persistent", "reboot", "boot", "remember between"],
            "description": "The ability to survive shutdown and resume state."
        },
        "memory": {
            "terms": ["memory", "remember", "recall", "ledger", "history"],
            "description": "Persistent storage of events, facts, and context."
        },
        "department": {
            "terms": ["department", "floor", "office", "worker floor"],
            "description": "A functional floor inside the QSB skyscraper."
        },
        "mission": {
            "terms": ["mission", "goal", "objective", "task"],
            "description": "Long-running work tracked by the Mission Floor."
        },
        "lift": {
            "terms": ["lift", "bus", "elevator", "communication", "route"],
            "description": "Internal communication between QSB floors."
        },
        "knowledge_graph": {
            "terms": ["knowledge graph", "relationship", "node", "edge", "understand structure"],
            "description": "A graph of relationships between concepts."
        },
        "symbolic_logic": {
            "terms": ["symbolic", "symbolic logic", "meaning", "understand better", "deeper logic"],
            "description": "Concept-level interpretation beyond plain text routing."
        },
        "model": {
            "terms": ["model", "ollama", "llama", "mistral", "qwen", "llava"],
            "description": "A local worker model used by the QSB."
        },
        "offline_ai": {
            "terms": ["offline", "local", "no cloud", "local ai"],
            "description": "Local-first AI operation without cloud dependency."
        },
        "skyscraper": {
            "terms": ["skyscraper", "penthouse", "floors", "building"],
            "description": "The QSB architecture metaphor: Penthouse, floors, lifts, workers."
        },
        "upgrade": {
            "terms": ["upgrade", "evolve", "improve", "deeper", "next version"],
            "description": "A controlled extension of the kernel without destroying continuity."
        }
    }

    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.seed_concepts()

    def now(self):
        return datetime.now(UTC).isoformat()

    def seed_concepts(self):
        for symbol, data in self.CONCEPTS.items():
            self.conn.execute(
                """
                INSERT INTO symbolic_concepts(ts, symbol, description, strength)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET description=excluded.description
                """,
                (self.now(), symbol, data["description"], 1.0)
            )
        self.conn.commit()

    def analyze(self, text):
        lower = text.lower()
        symbols = []

        for symbol, data in self.CONCEPTS.items():
            if any(term in lower for term in data["terms"]):
                symbols.append(symbol)

        relations = []

        if "memory" in symbols and "continuity" in symbols:
            relations.append(["memory", "supports", "continuity"])

        if "department" in symbols and "mission" in symbols:
            relations.append(["mission", "can_be_assigned_to", "department"])

        if "lift" in symbols and "department" in symbols:
            relations.append(["lift", "connects", "department"])

        if "knowledge_graph" in symbols and "symbolic_logic" in symbols:
            relations.append(["knowledge_graph", "strengthens", "symbolic_logic"])

        if "kernel" in symbols and "upgrade" in symbols:
            relations.append(["upgrade", "evolves", "kernel"])

        if "qsb" in symbols and "skyscraper" in symbols:
            relations.append(["qsb", "uses_architecture", "skyscraper"])

        if "model" in symbols and "department" in symbols:
            relations.append(["model", "acts_as_worker_for", "department"])

        if "offline_ai" in symbols and "qsb" in symbols:
            relations.append(["offline_ai", "powers", "qsb"])

        if not symbols:
            meaning = "general_input"
        else:
            meaning = " + ".join(symbols)

        return {
            "symbols": symbols,
            "inferred_relations": relations,
            "meaning": meaning
        }

    def observe(self, source, text):
        result = self.analyze(text)
        self.conn.execute(
            """
            INSERT INTO symbolic_observations(ts, source, text, symbols, inferred_relations, meaning)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.now(),
                source,
                text,
                json.dumps(result["symbols"], ensure_ascii=False),
                json.dumps(result["inferred_relations"], ensure_ascii=False),
                result["meaning"]
            )
        )
        self.conn.commit()
        return result

    def dashboard(self):
        obs = self.conn.execute("SELECT COUNT(*) AS c FROM symbolic_observations").fetchone()["c"]
        concepts = self.conn.execute("SELECT COUNT(*) AS c FROM symbolic_concepts").fetchone()["c"]
        recent = self.conn.execute(
            "SELECT * FROM symbolic_observations ORDER BY id DESC LIMIT 10"
        ).fetchall()

        rows = []
        for r in recent:
            item = dict(r)
            try:
                item["symbols"] = json.loads(item["symbols"])
                item["inferred_relations"] = json.loads(item["inferred_relations"])
            except Exception:
                pass
            rows.append(item)

        return {
            "database": str(DB),
            "concepts": concepts,
            "observations": obs,
            "recent": rows
        }

    def find(self, term, limit=20):
        like = f"%{term}%"
        rows = self.conn.execute(
            """
            SELECT * FROM symbolic_observations
            WHERE text LIKE ? OR symbols LIKE ? OR inferred_relations LIKE ? OR meaning LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (like, like, like, like, limit)
        ).fetchall()

        result = []
        for r in rows:
            item = dict(r)
            try:
                item["symbols"] = json.loads(item["symbols"])
                item["inferred_relations"] = json.loads(item["inferred_relations"])
            except Exception:
                pass
            result.append(item)
        return result
