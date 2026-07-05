"""StaleMemoryLens — which memories are old enough that they may have rotted?

The auto-memory system's own system prompt says it: "a memory that names a
function is a claim it existed when the memory was written. Verify before
recommending." The danger is that I can recall a six-month-old memory and
recommend acting on it without checking whether the function it names still
exists.

The lens walks the memory directory, ages each file, and for memories that
reference concrete file paths or function/symbol names, checks whether the
referenced thing still exists. It does NOT auto-rewrite or auto-delete. It
surfaces a list: which memories are old, which reference dead paths, which
are still fresh.

This module is REFLECTIVE. It surfaces signals. It never acts.
"""
from __future__ import annotations
import json
import os
import re
import datetime
import subprocess
from typing import List, Dict

DEFAULT_PATH = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_claude_stale_memory_lens.jsonl"
MEMORY_DIR = "/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory"

STALE_AGE_DAYS = 30
ANCIENT_AGE_DAYS = 90

# Paths a memory might reference — captured by regex
PATH_PATTERNS = [
    re.compile(r"(/vaults/nvme0/qsb_tower_v1/[A-Za-z0-9_./-]+\.(?:py|sh|md|json|jsonl))"),
    re.compile(r"(/home/ross/qsb_godot_native_cockpit/[A-Za-z0-9_./-]+\.(?:gd|tscn|tres))"),
    re.compile(r"(src/tower/[A-Za-z0-9_./-]+\.py)"),
    re.compile(r"(scripts/[A-Za-z0-9_./-]+\.(?:sh|py))"),
]

# Symbols a memory might name (Python identifiers in backticks)
SYMBOL_PATTERN = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{3,})`")


def _file_age_days(path: str) -> float:
    mtime = os.path.getmtime(path)
    age_seconds = datetime.datetime.utcnow().timestamp() - mtime
    return age_seconds / 86400.0


def _resolve_relative(path: str) -> List[str]:
    """A memory might say 'src/tower/foo.py' — try both project roots."""
    if path.startswith("/"):
        return [path]
    return [
        os.path.join("/vaults/nvme0/qsb_tower_v1", path),
        os.path.join("/home/ross/qsb_godot_native_cockpit", path),
    ]


def _path_exists_any(path: str) -> bool:
    for resolved in _resolve_relative(path):
        if os.path.exists(resolved):
            return True
    return False


def _symbol_exists_in_codebase(symbol: str) -> bool:
    """Cheap check: does the symbol appear anywhere in the project tree?
    We accept any occurrence — if grep finds it, the memory's named thing is
    plausibly still there. False negatives are acceptable (over-warn rather
    than under-warn)."""
    for root in ("/vaults/nvme0/qsb_tower_v1/src",
                 "/vaults/nvme0/qsb_tower_v1/scripts",
                 "/home/ross/qsb_godot_native_cockpit/scripts"):
        if not os.path.isdir(root):
            continue
        try:
            r = subprocess.run(
                ["grep", "-rqw", symbol, root],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=4,
            )
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


class StaleMemoryLens:
    def __init__(self, path: str = DEFAULT_PATH,
                 memory_dir: str = MEMORY_DIR) -> None:
        self.path = path
        self.memory_dir = memory_dir

    def scan(self) -> Dict:
        """Walk every memory .md file, age it, verify the things it names."""
        if not os.path.isdir(self.memory_dir):
            return {
                "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "note": f"memory dir not found at {self.memory_dir}",
                "memories": [],
            }

        memories = []
        for fn in sorted(os.listdir(self.memory_dir)):
            if not fn.endswith(".md") or fn == "MEMORY.md":
                continue
            full = os.path.join(self.memory_dir, fn)
            try:
                content = open(full).read()
            except Exception:
                continue

            age = _file_age_days(full)
            paths = set()
            for pat in PATH_PATTERNS:
                for m in pat.findall(content):
                    paths.add(m)

            symbols = set(SYMBOL_PATTERN.findall(content))
            # Filter out obvious noise (common words that aren't symbols)
            symbols = {s for s in symbols if not s.lower() in {
                "true", "false", "none", "null", "yes", "well", "claude",
                "ross", "kernel", "tower", "floor",
            }}

            broken_paths = [p for p in paths if not _path_exists_any(p)]
            # Symbol verification is expensive — only do it for stale-or-older
            broken_symbols = []
            if age >= STALE_AGE_DAYS:
                for s in list(symbols)[:8]:    # cap for cost
                    if not _symbol_exists_in_codebase(s):
                        broken_symbols.append(s)

            staleness = (
                "ancient" if age >= ANCIENT_AGE_DAYS else
                "stale"   if age >= STALE_AGE_DAYS else
                "fresh"
            )
            health = "ok"
            if broken_paths or broken_symbols:
                health = "broken_references"
            elif staleness == "ancient":
                health = "ancient_unverified"
            elif staleness == "stale":
                health = "stale_unverified"

            memories.append({
                "file": fn,
                "age_days": round(age, 1),
                "staleness": staleness,
                "n_paths_referenced": len(paths),
                "n_symbols_referenced": len(symbols),
                "broken_paths": broken_paths[:5],
                "broken_symbols": broken_symbols[:5],
                "health": health,
            })

        result = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n_memories": len(memories),
            "n_fresh":             sum(1 for m in memories if m["staleness"] == "fresh"),
            "n_stale":             sum(1 for m in memories if m["staleness"] == "stale"),
            "n_ancient":           sum(1 for m in memories if m["staleness"] == "ancient"),
            "n_broken_references": sum(1 for m in memories if m["health"] == "broken_references"),
            "memories": memories,
            "note": "verify any memory marked broken_references before acting on it",
        }

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({k: v for k, v in result.items() if k != "memories"}) + "\n")
        return result

    def summary(self) -> Dict:
        s = self.scan()
        return {
            "n_memories": s["n_memories"],
            "n_fresh": s["n_fresh"],
            "n_stale": s["n_stale"],
            "n_ancient": s["n_ancient"],
            "n_broken_references": s["n_broken_references"],
            "needs_attention": [
                m["file"] for m in s["memories"]
                if m["health"] in ("broken_references", "ancient_unverified")
            ][:10],
            "note": s["note"],
        }
