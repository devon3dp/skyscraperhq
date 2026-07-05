"""PatternLibrary — shapes I've written 3+ times this evening. Pull them
into one place so the next phase doesn't restart from scratch.

Each helper is small. The point isn't a framework. The point is that I keep
typing `mkdir -p $(dirname $OUT); json.dump(...)` and that should be one line.
"""
from __future__ import annotations
import json
import os
import shutil
import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def utc_ts() -> str:
    """The one timestamp shape I keep retyping."""
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def safe_write_json(path: str, data: Dict[str, Any]) -> None:
    """mkdir -p + atomic-ish write to avoid a half-written registry file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def append_jsonl(path: str, entry: Dict[str, Any]) -> None:
    """The other shape I keep retyping. Append-only by design."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def mirror_to_godot_project(src_under_root: str,
                            *, godot_root: str = "/home/ross/qsb_godot_native_cockpit",
                            qsb_root: str = "/vaults/nvme0/qsb_tower_v1") -> Optional[str]:
    """The snap-confined Godot can't read /vaults/... — mirror a registry into
    the project tree so res:// resolution finds it. Returns the destination
    path, or None if the source doesn't exist."""
    src = os.path.join(qsb_root, src_under_root.lstrip("/"))
    if not os.path.exists(src):
        return None
    dst = os.path.join(godot_root, src_under_root.lstrip("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    return dst


# -------- Smoke test runner ----------------------------------------------

class SmokeCheck:
    """A single check. name + a callable that returns (ok, detail)."""
    def __init__(self, name: str, fn: Callable[[], Tuple[bool, str]]) -> None:
        self.name = name
        self.fn = fn


def run_smoke_checks(checks: Iterable[SmokeCheck], *,
                     write_to: Optional[str] = None,
                     kind: str = "qsb_generic_smoke_test_latest") -> Dict[str, Any]:
    """Run a list of smoke checks. Emit a registry-shaped result."""
    pass_n = 0; fail_n = 0
    results = []
    for c in checks:
        try:
            ok, detail = c.fn()
        except Exception as e:
            ok, detail = False, f"raised: {e!r}"
        results.append({"name": c.name, "ok": ok, "detail": detail})
        if ok: pass_n += 1
        else: fail_n += 1
    out = {
        "ok": fail_n == 0, "kind": kind, "ts": utc_ts(),
        "pass": pass_n, "fail": fail_n, "results": results,
    }
    if write_to:
        safe_write_json(write_to, out)
    return out


def check_file_exists(path: str) -> SmokeCheck:
    return SmokeCheck(f"file:{path}", lambda: (os.path.exists(path), path if os.path.exists(path) else "missing"))


def check_no_pattern_in_tree(root: str, pattern: str) -> SmokeCheck:
    """Walk a directory tree; assert no file contains a regex match. Used for
    secret-leak checks etc."""
    import re
    rx = re.compile(pattern)
    def _fn() -> Tuple[bool, str]:
        hits: List[str] = []
        for dirpath, _, files in os.walk(root):
            for name in files:
                p = os.path.join(dirpath, name)
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        if rx.search(f.read()):
                            hits.append(p)
                except (OSError, UnicodeError):
                    pass
        return (len(hits) == 0, f"{len(hits)} hits" if hits else "clean")
    return SmokeCheck(f"no_pattern:{pattern}@{root}", _fn)
