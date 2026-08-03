#!/usr/bin/env python3
"""
qsb_knowledge.py — the tower's LEARNING / KNOWLEDGE layer.

2026-07-29, Ross: "make the tower LEARN, not just do ephemeral work". Until now a worker
answered a question, logged a train on the Underground, and it evaporated — nothing compounded.
This is an append-only, deduplicated store of GENUINE learnings the workers + council actually
produce (real risk/insight lines, real audit findings, real task outcomes). Every entry carries
its real source id + a UTC timestamp. Nothing is fabricated here: callers pass real worker output
and this module ONLY decides whether it's substantive + non-duplicate, then persists it.

Store: data/registries/qsb_knowledge.jsonl  (one JSON object per line, append-only)
Row shape:
    {"id": "<sha1-12>", "ts": "<utc>", "source": "<worker/council id>",
     "kind": "risk|insight|finding|outcome|note", "text": "<real learning>",
     "topic": "<coarse bucket>", "tags": ["..."], "seen": <int>, "last_ts": "<utc>"}

Public API:
    add(text, source, kind="note", topic=None, tags=None)  -> dict|None (None if junk/dup)
    search(query, k=5, topic=None)                          -> [rows] most relevant
    recent(n=20, source=None, topic=None)                   -> [rows] newest first
    summary()                                               -> dict of real counts
    recall_context(query, k=3, topic=None)                  -> str  (compact context block)

Dedup: near-identical entries (same normalized text, or high token-overlap with an existing
entry from a compatible source) are NOT re-appended — instead the existing row's `seen` counter
and `last_ts` are bumped (rewrites the file, still lossless). This keeps the store from bloating
when the same worker keeps producing the same one-liner every cycle.

CLI:
    python3 tools/qsb_knowledge.py add   "text" --source wren --kind insight
    python3 tools/qsb_knowledge.py search "risk fleet" [-k 5]
    python3 tools/qsb_knowledge.py recent [-n 20]
    python3 tools/qsb_knowledge.py summary
    python3 tools/qsb_knowledge.py recall "duplicated trades"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "registries" / "qsb_knowledge.jsonl"

# ---- honesty / quality gate: what is NOT a real learning ---------------------
# We refuse error sentinels, empties, and trivially short strings so the store only
# ever holds substantive, real worker output.
_MIN_CHARS = 12
_MIN_WORDS = 3
_JUNK_PREFIXES = (
    "(cockpit", "local generation failed", "error", "traceback", "none",
    "n/a", "no answer", "unreachable", "no real answer", "no response",
)
_JUNK_SUBSTR = ("unreachable", "did not answer", "no real answer", "no train")

# Dedup: two texts are "the same learning" if their normalized forms match, OR if their
# word-set Jaccard similarity is >= this (catches "one risk is X" vs "a risk here is X").
_DUP_JACCARD = 0.70

_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "is", "are", "for", "and", "or", "one",
    "that", "this", "it", "with", "as", "be", "by", "at", "if", "so", "no", "not",
    "there", "here", "could", "would", "should", "can", "may", "might", "right", "now",
    "line", "sentence", "name", "thing", "way", "check",
}

# Coarse topic buckets — deterministic keyword routing, no model, no fabrication.
_TOPIC_KEYWORDS = {
    "trading": ("trade", "trading", "oanda", "pnl", "position", "order", "fleet",
                "trader", "ccy", "currency", "broker", "binance", "profit", "loss"),
    "reliability": ("worker", "died", "dead", "silent", "crash", "restart", "service",
                    "systemd", "watchdog", "heartbeat", "timeout", "stall"),
    "council": ("council", "task", "quorum", "signoff", "verify", "sandbox", "queue"),
    "tower": ("tower", "disk", "gpu", "load", "memory", "cpu", "node", "box", "vm"),
    "quality": ("test", "bug", "audit", "finding", "regression", "code", "review"),
}


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- normalization + similarity ---------------------------------------------
def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokens(text: str) -> set:
    return {w for w in _norm(text).split() if w not in _STOP and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _topic_of(text: str) -> str:
    toks = _tokens(text)
    best, best_hits = "general", 0
    for topic, kws in _TOPIC_KEYWORDS.items():
        hits = sum(1 for k in kws if k in toks)
        if hits > best_hits:
            best, best_hits = topic, hits
    return best


def _is_junk(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < _MIN_CHARS:
        return True
    if len([w for w in t.split() if w]) < _MIN_WORDS:
        return True
    low = t.lower()
    if low.startswith(_JUNK_PREFIXES):
        return True
    if any(s in low for s in _JUNK_SUBSTR):
        return True
    return False


def _clean(text: str) -> str:
    """Trim boilerplate the worker prompts induce, so stored learnings read cleanly."""
    t = (text or "").strip()
    # strip a leading "In one sentence," / "In one line," style echo the models add
    t = re.sub(r"^(in\s+(one|a)\s+(short\s+)?(sentence|line)[:,]?\s*)", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---- storage ----------------------------------------------------------------
def _load_all() -> list:
    if not STORE.exists():
        return []
    rows = []
    for line in STORE.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _atomic_rewrite(rows: list) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STORE.parent), prefix=".qsb_knowledge_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, STORE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _append(row: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE, "a") as f:
        f.write(json.dumps(row) + "\n")


def _find_dup(rows: list, text: str):
    """Return an existing row that represents the same learning, or None."""
    norm = _norm(text)
    toks = _tokens(text)
    for r in rows:
        rtext = r.get("text", "")
        if _norm(rtext) == norm:
            return r
        if _jaccard(_tokens(rtext), toks) >= _DUP_JACCARD:
            return r
    return None


# ---- public API -------------------------------------------------------------
def add(text: str, source: str, kind: str = "note", topic: str = None, tags=None):
    """Record a GENUINE learning. Returns the stored/updated row, or None if the text is
    junk (error sentinel / too short) or a near-duplicate handled by bumping `seen`.

    Callers MUST pass real worker output only — this module does not invent text."""
    text = _clean(text)
    if _is_junk(text):
        return None
    rows = _load_all()
    dup = _find_dup(rows, text)
    if dup is not None:
        dup["seen"] = int(dup.get("seen", 1)) + 1
        dup["last_ts"] = utc()
        # keep the longer/richer phrasing if the new one is more complete
        if len(text) > len(dup.get("text", "")):
            dup["text"] = text
        _atomic_rewrite(rows)
        return None
    row = {
        "id": hashlib.sha1(_norm(text).encode()).hexdigest()[:12],
        "ts": utc(),
        "source": source,
        "kind": kind,
        "text": text,
        "topic": topic or _topic_of(text),
        "tags": list(tags) if tags else [],
        "seen": 1,
        "last_ts": utc(),
    }
    _append(row)
    return row


def search(query: str, k: int = 5, topic: str = None) -> list:
    """Relevance search over stored learnings (token overlap + recency tiebreak)."""
    rows = _load_all()
    if topic:
        rows = [r for r in rows if r.get("topic") == topic]
    q = _tokens(query)
    if not q:
        return recent(k, topic=topic)
    scored = []
    for r in rows:
        overlap = len(_tokens(r.get("text", "")) & q)
        if overlap == 0:
            continue
        # weight by overlap, then by how often it's been reaffirmed (seen), then recency
        score = overlap * 10 + min(int(r.get("seen", 1)), 5) + (r.get("last_ts", "") > "" )
        scored.append((score, r.get("last_ts", ""), r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:k]]


def recent(n: int = 20, source: str = None, topic: str = None) -> list:
    rows = _load_all()
    if source:
        rows = [r for r in rows if r.get("source") == source]
    if topic:
        rows = [r for r in rows if r.get("topic") == topic]
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return rows[:n]


def summary() -> dict:
    rows = _load_all()
    by_source = Counter(r.get("source", "?") for r in rows)
    by_topic = Counter(r.get("topic", "?") for r in rows)
    by_kind = Counter(r.get("kind", "?") for r in rows)
    reaffirmed = sum(1 for r in rows if int(r.get("seen", 1)) > 1)
    total_seen = sum(int(r.get("seen", 1)) for r in rows)
    days = Counter((r.get("ts", "")[:10] or "?") for r in rows)
    return {
        "total_entries": len(rows),
        "total_observations": total_seen,   # entries + dedup hits = raw learnings absorbed
        "reaffirmed_entries": reaffirmed,    # learnings seen more than once (dedup working)
        "by_source": dict(by_source.most_common()),
        "by_topic": dict(by_topic.most_common()),
        "by_kind": dict(by_kind.most_common()),
        "by_day": dict(sorted(days.items())),
        "first_ts": min((r.get("ts", "") for r in rows), default=""),
        "last_ts": max((r.get("ts", "") for r in rows), default=""),
    }


def recall_context(query: str, k: int = 3, topic: str = None) -> str:
    """A compact, human-readable block of the most relevant prior learnings, for injecting
    into a new worker/council prompt so answers BUILD on prior ones instead of repeating.
    Returns "" when nothing relevant is stored yet."""
    hits = search(query, k=k, topic=topic)
    if not hits:
        return ""
    lines = ["Known so far (prior tower learnings — build on these, don't repeat them):"]
    for r in hits:
        seen = int(r.get("seen", 1))
        tag = f" (seen x{seen})" if seen > 1 else ""
        lines.append(f"- [{r.get('source', '?')}] {r.get('text', '').strip()}{tag}")
    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------
def _main(argv) -> int:
    if not argv:
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "add":
        text = argv[1] if len(argv) > 1 else ""
        source, kind, topic = "cli", "note", None
        a = argv[2:]
        while a:
            if a[0] == "--source" and len(a) > 1:
                source = a[1]; a = a[2:]
            elif a[0] == "--kind" and len(a) > 1:
                kind = a[1]; a = a[2:]
            elif a[0] == "--topic" and len(a) > 1:
                topic = a[1]; a = a[2:]
            else:
                a = a[1:]
        row = add(text, source, kind=kind, topic=topic)
        print(json.dumps(row, indent=2) if row else "[knowledge] junk or duplicate — not added (seen bumped if dup)")
        return 0
    if cmd == "search":
        q = argv[1] if len(argv) > 1 else ""
        k = int(argv[argv.index("-k") + 1]) if "-k" in argv else 5
        for r in search(q, k=k):
            print(f"[{r.get('source')}/{r.get('topic')}] {r.get('text')}  (seen x{r.get('seen',1)}, {r.get('ts')})")
        return 0
    if cmd == "recent":
        n = int(argv[argv.index("-n") + 1]) if "-n" in argv else 20
        for r in recent(n):
            print(f"{r.get('ts')}  [{r.get('source')}/{r.get('topic')}/{r.get('kind')}] {r.get('text')}  (seen x{r.get('seen',1)})")
        return 0
    if cmd == "summary":
        print(json.dumps(summary(), indent=2))
        return 0
    if cmd == "recall":
        q = argv[1] if len(argv) > 1 else ""
        print(recall_context(q) or "(nothing relevant stored yet)")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
