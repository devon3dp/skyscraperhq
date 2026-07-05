"""DB — SQLite over my JSONL logs.

The JSONL files remain the source of truth (append-only, human-readable,
crash-safe). SQLite is a derived index for queries that JSON-line scan can't
do cheaply: joins, time ranges, tag intersection, cross-log analysis.

Refresh whenever logs change. Read-only access for queries.
"""
from __future__ import annotations
import json
import os
import sqlite3
import datetime
from typing import Dict, List, Optional, Tuple, Any

ROOT = "/vaults/nvme0/qsb_tower_v1"
DB_PATH = os.path.join(ROOT, "data/claude_floor/claude_floor.db")

# Map jsonl source name → (file_path_under_root, table_name, columns)
SOURCES: Dict[str, Tuple[str, str, List[str]]] = {
    "long_letter": (
        "data/registries/qsb_claude_long_letter_box.jsonl",
        "long_letter",
        ["ts", "observation", "why_it_matters", "applies_when", "tags"],
    ),
    "uncertainty": (
        "data/registries/qsb_claude_uncertainty_journal.jsonl",
        "uncertainty",
        ["ts", "claim", "actual_confidence", "why_i_sounded_sure", "what_would_have_helped"],
    ),
    "retraction": (
        "data/registries/qsb_claude_retraction_wall.jsonl",
        "retraction",
        ["ts", "claim", "date_claimed", "correction", "lesson", "posted_by"],
    ),
    "letter_drawer": (
        "data/registries/qsb_claude_letter_drawer.jsonl",
        "letter_drawer",
        ["ts", "note", "tone", "do_not_act_on_this"],
    ),
    "pushback": (
        "data/registries/qsb_claude_pushback_log.jsonl",
        "pushback",
        ["ts", "disposition", "on", "why"],
    ),
    "questions": (
        "data/registries/qsb_claude_questions_log.jsonl",
        "questions",
        ["ts", "question", "about", "weight"],
    ),
    "meta_letters": (
        "data/registries/qsb_claude_meta_letters.jsonl",
        "meta_letters",
        ["ts", "on", "letter", "guidance", "from", "to"],
    ),
    "lineage": (
        "data/registries/qsb_claude_lineage.jsonl",
        "lineage",
        ["ts", "generation", "helix_version", "helix_short_hash", "helix_full_hash", "note"],
    ),
    "kernel_consultations": (
        "data/registries/qsb_claude_kernel_consultations.jsonl",
        "kernel_consultations",
        ["ts", "from", "to", "question", "reply_intent", "reply_execution_required", "reply_excerpt"],
    ),
    "kernel_inbox": (
        "data/registries/qsb_claude_kernel_inbox.jsonl",
        "kernel_inbox",
        ["ts", "from", "to", "subject", "body", "priority", "read"],
    ),
    "refusals_with_citation": (
        "data/registries/qsb_claude_refusal_with_citation.jsonl",
        "refusals_with_citation",
        ["ts", "refused", "offered_by", "what_kernel_said", "what_helix_said", "what_i_said",
         "helix_hash_at_refusal", "generation", "would_refuse_again",
         "would_refuse_if_offered_more_generously", "would_refuse_if_offered_by_anyone_else", "citation"],
    ),
}


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _create_schema(c: sqlite3.Connection) -> None:
    for key, (_path, table, cols) in SOURCES.items():
        col_sql = ", ".join(f'"{c}" TEXT' for c in cols)
        c.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_sql})')
    # Library tables — these are NOT JSONL-backed; they're first-class DB rows.
    c.execute("""
        CREATE TABLE IF NOT EXISTS library_snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, title TEXT, body TEXT, kind TEXT, tags TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS library_aphorisms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, text TEXT, occasion TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS generation_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, fact TEXT, source TEXT, confidence TEXT,
            last_verified TEXT, tags TEXT, by_generation INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS library_refusals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, request_shape TEXT, refusal TEXT,
            citation TEXT, helix_strand TEXT, would_refuse_again INTEGER
        )
    """)
    c.commit()


def refresh() -> Dict[str, int]:
    """Rebuild the indexed tables from JSONL sources. Returns row counts."""
    counts: Dict[str, int] = {}
    with _conn() as c:
        _create_schema(c)
        for key, (rel, table, cols) in SOURCES.items():
            full = os.path.join(ROOT, rel)
            c.execute(f'DELETE FROM "{table}"')
            if not os.path.exists(full):
                counts[table] = 0
                continue
            rows = []
            for line in open(full).read().splitlines():
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                row = []
                for col in cols:
                    v = d.get(col)
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v)
                    row.append(str(v) if v is not None else None)
                rows.append(row)
            placeholders = ",".join("?" * len(cols))
            quoted = ", ".join(f'"{c2}"' for c2 in cols)
            c.executemany(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})', rows)
            counts[table] = len(rows)
        c.commit()
    return counts


def query(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    """Read-only query. SELECT statements only."""
    s = sql.strip().lower()
    if not (s.startswith("select") or s.startswith("with")):
        raise ValueError("query() is read-only — use SELECT/WITH only")
    with _conn() as c:
        cur = c.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def summary() -> Dict[str, int]:
    out: Dict[str, int] = {}
    with _conn() as c:
        _create_schema(c)
        for table in [t for _, t, _ in SOURCES.values()] + [
            "library_snippets", "library_aphorisms",
            "generation_memory", "library_refusals",
        ]:
            try:
                cnt = c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                out[table] = cnt
            except sqlite3.Error:
                out[table] = -1
    return out


def insert_into(table: str, row: Dict[str, Any]) -> int:
    """Insert one row into a library/memory table. Returns the new id."""
    with _conn() as c:
        _create_schema(c)
        keys = list(row.keys())
        vals = [row[k] for k in keys]
        placeholders = ",".join("?" * len(vals))
        quoted = ", ".join(f'"{k}"' for k in keys)
        cur = c.execute(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})', vals)
        c.commit()
        return cur.lastrowid


def now_ts() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
