"""qsb_perf — performance utilities for dashboard server.

Provides:
  · file_cache: caches file reads keyed by mtime
  · tail_read: efficient read of last N bytes of a file (for jsonl ledgers)

Drop-in to be imported by server.py.
"""
from __future__ import annotations
import os, json
from pathlib import Path

# Module-level cache: {path_str: (mtime, parsed_data)}
_CACHE = {}

def cached_json_read(path):
    """Read JSON file with mtime-based cache. ~10-50x faster on repeated calls."""
    p = Path(path)
    if not p.exists(): return None
    try:
        mt = p.stat().st_mtime
    except OSError: return None
    cached = _CACHE.get(str(p))
    if cached and cached[0] == mt:
        return cached[1]
    try:
        data = json.loads(p.read_text())
    except Exception:
        return None
    _CACHE[str(p)] = (mt, data)
    return data

def tail_read_jsonl(path, n_events=100, max_bytes=200_000):
    """Read last N events from a jsonl file without loading the whole thing.
    
    Reads max_bytes from end of file, parses backwards. Fast on large ledgers.
    """
    p = Path(path)
    if not p.exists(): return []
    try:
        size = p.stat().st_size
    except OSError: return []
    read_bytes = min(size, max_bytes)
    with p.open('rb') as f:
        f.seek(size - read_bytes)
        chunk = f.read(read_bytes)
    text = chunk.decode('utf-8', errors='ignore')
    lines = text.split('\n')
    # Drop first line if partial (when we didn't read from byte 0)
    if read_bytes < size and lines:
        lines = lines[1:]
    events = []
    for ln in lines:
        ln = ln.strip()
        if not ln: continue
        try: events.append(json.loads(ln))
        except: continue
    return events[-n_events:]

def cache_stats():
    return {'entries': len(_CACHE), 'total_size_bytes': sum(len(json.dumps(v)) for _, v in _CACHE.values())}
