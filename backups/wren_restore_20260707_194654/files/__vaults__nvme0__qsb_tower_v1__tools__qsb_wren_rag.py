#!/usr/bin/env python3
"""qsb_wren_rag.py — tier-3 RAG over the tower codebase for offline-Wren.

Plain numpy + sqlite + nomic-embed-text via Ollama. No new deps.
Index lives at data/registries/wren_rag/{vectors.npy, chunks.sqlite, manifest.json}.

Index whitelist (NOT whole repo):
  - src/tower/**/*.py
  - floors/**/floor_card.json + *.md
  - tools/qsb_*.py
  - CLAUDE.md, docs/**/*.md, *.md at root
  - data/registries/*.json (NOT .jsonl — those are activity logs, 4.8GB)
  - qsb_session_diary.md + MEMORY.md

Excludes: __pycache__, archive/, .jsonl, galaxy_apks/, SAFETY_DENY paths.

Usage:
    python3 tools/qsb_wren_rag.py build       # build index
    python3 tools/qsb_wren_rag.py stats        # show index stats
    python3 tools/qsb_wren_rag.py retrieve "how does compose_reply work" -k 6
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys, time, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
RAG_DIR = REG / "wren_rag"
VEC = RAG_DIR / "vectors.npy"
DB = RAG_DIR / "chunks.sqlite"
MAN = RAG_DIR / "manifest.json"
WREN_GATE = REG / "qsb_wren_local_agentic_gate.json"
MEMORY_INDEX = Path("/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md")

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200


def _safety_deny() -> set[str]:
    try:
        g = json.loads(WREN_GATE.read_text())
        return set(g.get("safety_deny_paths", []))
    except Exception:
        return set()


def _is_excluded(p: Path, deny: set[str]) -> bool:
    rel = str(p.relative_to(ROOT))
    if any(part in {"__pycache__", "archive", "galaxy_apks", ".git", ".venv", "node_modules"} for part in p.parts):
        return True
    if p.suffix == ".jsonl": return True
    for d in deny:
        if rel == d or rel.startswith(d.rstrip("/")+"/"): return True
    return False


def _collect_files() -> list[Path]:
    deny = _safety_deny()
    out: list[Path] = []
    # src/tower code
    for p in (ROOT/"src"/"tower").rglob("*.py"): out.append(p)
    # floors
    for p in (ROOT/"floors").rglob("floor_card.json"): out.append(p)
    for p in (ROOT/"floors").rglob("*.md"): out.append(p)
    # tools
    for p in (ROOT/"tools").glob("qsb_*.py"): out.append(p)
    # docs + root markdown
    if (ROOT/"docs").exists():
        for p in (ROOT/"docs").rglob("*.md"): out.append(p)
    for p in ROOT.glob("*.md"): out.append(p)
    # registries .json only
    for p in REG.glob("*.json"): out.append(p)
    # memory + diary
    if MEMORY_INDEX.exists(): out.append(MEMORY_INDEX)
    diary = ROOT/"qsb_session_diary.md"
    if diary.exists(): out.append(diary)
    # filter
    seen, kept = set(), []
    for p in out:
        try:
            p_resolved = p.resolve()
            if p_resolved in seen: continue
            seen.add(p_resolved)
            # for files outside ROOT (memory index), don't apply ROOT exclusions
            if not str(p_resolved).startswith(str(ROOT.resolve())):
                kept.append(p); continue
            if _is_excluded(p, _safety_deny()): continue
            if p.stat().st_size > 200_000: continue
            kept.append(p)
        except Exception: continue
    return kept


def _chunk_text(path: Path, text: str) -> list[tuple[int, int, str]]:
    """Return list of (line_start, line_end, chunk_text). Plain windowed chunking."""
    out = []
    lines = text.splitlines(keepends=True)
    if not lines: return out
    i = 0
    char_cursor = 0
    while i < len(lines):
        # accumulate up to CHUNK_CHARS
        start_line = i + 1
        buf = []
        size = 0
        j = i
        while j < len(lines) and size + len(lines[j]) <= CHUNK_CHARS:
            buf.append(lines[j]); size += len(lines[j]); j += 1
        if not buf:  # single line longer than chunk
            buf.append(lines[i][:CHUNK_CHARS]); j = i + 1
        end_line = j
        out.append((start_line, end_line, "".join(buf)))
        # advance with overlap
        if j >= len(lines): break
        # back up ~overlap chars worth of lines
        back_size, back = 0, j
        while back > i and back_size < CHUNK_OVERLAP:
            back -= 1; back_size += len(lines[back])
        i = max(j - max(1, (j-back)//2), j-3)
        if i <= start_line - 1: i = j  # progress
    return out


def _embed(texts: list[str], endpoint: str = "http://127.0.0.1:11434/api/embeddings") -> list[list[float]]:
    """Call Ollama /api/embeddings for each text. Returns list of vectors."""
    out = []
    for t in texts:
        body = json.dumps({"model": EMBED_MODEL, "prompt": t}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, method="POST")
        req.add_header("Content-Type","application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        emb = r.get("embedding") or []
        if len(emb) != EMBED_DIM:
            raise RuntimeError(f"unexpected embedding dim {len(emb)}")
        out.append(emb)
    return out


def _db_init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists(): DB.unlink()
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, path TEXT, line_start INT, line_end INT, text TEXT)")
    c.commit()
    return c


def cmd_build():
    import numpy as np
    t0 = time.time()
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    files = _collect_files()
    print(f"[{int(time.time()-t0)}s] {len(files)} files to index")
    c = _db_init()
    all_chunks = []  # list of (chunk_id, path, ls, le, text)
    cid = 0
    for fp in files:
        try: txt = fp.read_text(errors="replace")
        except Exception as e: print(f"  skip {fp}: {e}"); continue
        if not txt.strip(): continue
        try:
            rel = str(fp.relative_to(ROOT))
        except Exception:
            rel = str(fp)
        chunks = _chunk_text(fp, txt)
        for ls, le, chunk in chunks:
            cid += 1
            all_chunks.append((cid, rel, ls, le, chunk))
    print(f"[{int(time.time()-t0)}s] {len(all_chunks)} chunks. embedding ...")
    BATCH = 8
    vectors = np.zeros((len(all_chunks), EMBED_DIM), dtype=np.float32)
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i:i+BATCH]
        embs = _embed([row[4] for row in batch])
        for k, emb in enumerate(embs):
            vectors[i+k] = emb
        if i % 40 == 0:
            print(f"  [{int(time.time()-t0)}s] {i+len(batch)}/{len(all_chunks)}")
    # normalize for cosine via dot product
    norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    vectors = vectors / norms
    for row in all_chunks:
        c.execute("INSERT INTO chunks (id,path,line_start,line_end,text) VALUES (?,?,?,?,?)", row)
    c.commit(); c.close()
    np.save(VEC, vectors)
    MAN.write_text(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": len(files),
        "chunks": len(all_chunks),
        "vector_dim": EMBED_DIM,
        "embed_model": EMBED_MODEL,
        "build_seconds": round(time.time()-t0, 1),
    }, indent=2))
    print(f"[{int(time.time()-t0)}s] DONE — {len(all_chunks)} chunks, {VEC.stat().st_size//1024} KB vectors")


def cmd_stats():
    if not MAN.exists(): print("no index"); return
    print(MAN.read_text())


def retrieve(query: str, k: int = 6) -> list[dict]:
    import numpy as np
    if not VEC.exists() or not DB.exists():
        return [{"error":"no index — run: python3 tools/qsb_wren_rag.py build"}]
    vectors = np.load(VEC, mmap_mode="r")
    emb = _embed([query])[0]
    qv = np.array(emb, dtype=np.float32)
    qv = qv / (np.linalg.norm(qv) + 1e-9)
    sims = vectors @ qv  # cosine since both normalized
    top_idx = np.argsort(-sims)[:k]
    c = sqlite3.connect(DB)
    out = []
    for rank, i in enumerate(top_idx, 1):
        chunk_id = int(i) + 1  # sqlite ids are 1-based, matching insertion order
        row = c.execute("SELECT path,line_start,line_end,text FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        if not row: continue
        path, ls, le, txt = row
        out.append({
            "rank": rank, "score": float(sims[i]),
            "path": path, "lines": f"{ls}-{le}",
            "text": txt[:1200] + ("…" if len(txt) > 1200 else ""),
        })
    c.close()
    return out


def cmd_retrieve(query: str, k: int):
    results = retrieve(query, k=k)
    for r in results:
        if "error" in r: print(r); continue
        print(f"\n#{r['rank']} score={r['score']:.3f}  {r['path']}:{r['lines']}")
        print(r["text"][:500])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("build")
    sub.add_parser("stats")
    rr = sub.add_parser("retrieve")
    rr.add_argument("query"); rr.add_argument("-k", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "build": cmd_build()
    elif a.cmd == "stats": cmd_stats()
    elif a.cmd == "retrieve": cmd_retrieve(a.query, a.k)
    else: ap.print_help()

if __name__ == "__main__":
    main()
