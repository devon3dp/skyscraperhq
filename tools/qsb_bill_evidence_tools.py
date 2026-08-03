#!/usr/bin/env python3
"""Bounded read-only evidence tools for Bill's Linux Floor 47 embassy."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _inside_repo(raw: str) -> Path:
    p = (ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError("path outside repository refused")
    return p


def file_inventory(args: dict) -> str:
    root = _inside_repo(str(args.get("path", ".")))
    limit = min(max(int(args.get("max_files", 300)), 1), 1000)
    if not root.exists():
        return "ERROR: path not found"
    paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
    rows = []
    for p in paths[:limit]:
        rows.append({"path": str(p.relative_to(ROOT)), "size": p.stat().st_size,
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return json.dumps({"root": str(root.relative_to(ROOT)), "files": rows,
                       "truncated": len(paths) > limit}, indent=2)


def hash_verify(args: dict) -> str:
    p = _inside_repo(str(args.get("path", "")))
    expected = str(args.get("sha256", "")).lower()
    if not p.is_file() or len(expected) != 64:
        return "ERROR: existing file and 64-character sha256 required"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.dumps({"path": str(p.relative_to(ROOT)), "expected": expected,
                       "actual": actual, "verified": actual == expected})


def zip_inspect(args: dict) -> str:
    p = _inside_repo(str(args.get("path", "")))
    limit = min(max(int(args.get("max_entries", 300)), 1), 500)
    if not p.is_file():
        return "ERROR: ZIP not found"
    rows = []
    try:
        with zipfile.ZipFile(p) as zf:
            bad = zf.testzip()
            infos = zf.infolist()
            for info in infos[:limit]:
                digest = None if info.is_dir() else hashlib.sha256(zf.read(info)).hexdigest()
                rows.append({"name": info.filename, "size": info.file_size, "sha256": digest})
    except (zipfile.BadZipFile, OSError) as exc:
        return f"ERROR: {exc}"
    return json.dumps({"path": str(p.relative_to(ROOT)),
                       "archive_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                       "integrity": "PASS" if bad is None else "FAIL",
                       "bad_entry": bad, "entries": rows,
                       "truncated": len(infos) > limit}, indent=2)
