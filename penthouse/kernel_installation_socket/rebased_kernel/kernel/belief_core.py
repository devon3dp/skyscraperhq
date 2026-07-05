# QSB Tower V1.3 — Rebased Kernel Package
# REBASE CHANGE: ROOT rebased from original source vault
# DB now writes to KERNEL_STATE_ROOT under tower penthouse socket.
from pathlib import Path
from datetime import datetime, UTC
import sqlite3
import json

KERNEL_STATE_ROOT = Path(
    "/vaults/nvme0/qsb_tower_v1/penthouse/kernel_installation_socket/rebased_kernel/state"
)
DB = KERNEL_STATE_ROOT / "beliefs.sqlite"

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
