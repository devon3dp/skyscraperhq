#!/usr/bin/env python3
"""qsb_code_crew_tick.py — Wren's Code Crew runs one tick.

Each tick:
  1) Scans recently-modified .py/.gd/.js/.md files (last 10 min).
  2) Updates backlog with any TODO/FIXME/XXX found in those files.
  3) Cross-references the F47 records and the open task list to detect
     promises/phases that haven't been finished.
  4) Computes "what is being built", "what was forgotten", "what's still open".
  5) Writes data/registries/qsb_wren_code_crew_status.json (consumed by
     /api/code_crew/status).
  6) Stamps qsb_wren_code_crew_activity.jsonl.

Advisory-only. Does NOT edit code.
"""
from __future__ import annotations
import json, re, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
GODOT = Path("/home/ross/qsb_godot_native_cockpit")

STATUS = REG / "qsb_wren_code_crew_status.json"
BACKLOG = REG / "qsb_wren_code_crew_backlog.jsonl"
ACTIVITY = REG / "qsb_wren_code_crew_activity.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"

NOW = datetime.now(timezone.utc)
NOW_S = NOW.isoformat().replace("+00:00","Z")
RECENT_WINDOW_MIN = 15

TODO_RE = re.compile(r"(?i)\b(TODO|FIXME|XXX|HACK|BUG)\b[: ]?(.{0,160})")

def recent_files() -> list[dict]:
    """Files modified in last RECENT_WINDOW_MIN minutes — code only."""
    cutoff = (NOW - timedelta(minutes=RECENT_WINDOW_MIN)).timestamp()
    out = []
    EXTS = (".py", ".gd", ".js", ".css", ".sh", ".md", ".json", ".html")
    SKIP = ("/node_modules/", "/.git/", "/__pycache__/", "/data/registries/qsb_f47", "/.godot/")
    for base in (ROOT, GODOT):
        for p in base.rglob("*"):
            if not p.is_file(): continue
            sp = str(p)
            if not any(sp.endswith(e) for e in EXTS): continue
            if any(s in sp for s in SKIP): continue
            try:
                m = p.stat().st_mtime
                if m < cutoff: continue
                out.append({"path": sp, "mtime": m, "size": p.stat().st_size,
                            "ext": p.suffix})
            except: pass
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:40]

def scan_todos(files: list[dict]) -> list[dict]:
    """Extract TODO/FIXME markers from recently-edited files."""
    found = []
    for f in files[:25]:
        try:
            text = Path(f["path"]).read_text(errors="ignore")
            for ln, line in enumerate(text.splitlines(), 1):
                m = TODO_RE.search(line)
                if m:
                    found.append({
                        "file": f["path"].replace(str(ROOT)+"/", "").replace(str(GODOT)+"/", "godot:"),
                        "line": ln,
                        "marker": m.group(1).upper(),
                        "text": (m.group(2) or "").strip()[:120],
                    })
                    if len(found) >= 50: break
        except: pass
        if len(found) >= 50: break
    return found

def open_phases_from_tasks() -> list[str]:
    """A phase is OPEN only when no stamp containing it carries a 'done' signal
    (kind suffix like _animation/_live/_v1/_complete or summary mentioning
    complete/done/shipped/wired/etc.). Avoids false-flagging Phase EEE just
    because the stamp didn't literally say 'complete'."""
    if not F47.exists(): return []
    DONE_HINT = ("complete", "done", "shipped", "wired", "fixed",
                 "stamped", "executed", "trained", "launched", "live",
                 "_animation", "_v1", "fix_all", "sweep",
                 "active", "authorized", "authorization", "ready", "running")
    phase_records: dict[str, list[tuple[str,str]]] = {}
    for ln in F47.read_text().strip().split("\n")[-300:]:
        try: r = json.loads(ln)
        except: continue
        s = (r.get("summary","") or "").lower()
        k = (r.get("kind","") or "").lower()
        for m in re.finditer(r"phase\s+([a-z]{2,4})\b", s):
            phase_records.setdefault(m.group(1).upper(), []).append((k, s))
    open_ = []
    for phase, recs in phase_records.items():
        done = any(any(h in k or h in s for h in DONE_HINT) for (k, s) in recs)
        if not done:
            open_.append(phase)
    return sorted(open_)

def promises_check(files: list[dict]) -> list[str]:
    """Look for half-implemented patterns: empty function bodies, 'pass # TODO',
    raise NotImplementedError, etc."""
    warnings = []
    for f in files[:10]:
        try:
            text = Path(f["path"]).read_text(errors="ignore")
            if "raise NotImplementedError" in text:
                warnings.append(f"{f['path'].split('/')[-1]}: NotImplementedError stub")
            if re.search(r"def \w+\([^)]*\):\s+pass\s*$", text, re.M):
                warnings.append(f"{f['path'].split('/')[-1]}: empty stub function")
        except: pass
    return warnings[:10]


def syntax_check(files: list[dict]) -> list[dict]:
    """Run real syntax checks on recently-touched Python and JavaScript files.
    THIS is what should have caught the cockpit.js missing-paren bug.
    Returns a list of {file, error} for any file that fails to parse."""
    import subprocess as _sp
    findings = []
    for f in files[:30]:
        p = f["path"]
        try:
            if p.endswith(".py"):
                r = _sp.run(["python3", "-m", "py_compile", p],
                            capture_output=True, text=True, timeout=8)
                if r.returncode != 0:
                    findings.append({
                        "file": p.replace("/vaults/nvme0/qsb_tower_v1/",""),
                        "lang": "py",
                        "error": (r.stderr or r.stdout).strip()[:200],
                    })
            elif p.endswith(".js") or p.endswith(".mjs"):
                r = _sp.run(["node", "--check", p],
                            capture_output=True, text=True, timeout=8)
                if r.returncode != 0:
                    findings.append({
                        "file": p.replace("/vaults/nvme0/qsb_tower_v1/",""),
                        "lang": "js",
                        "error": (r.stderr or r.stdout).strip()[:200],
                    })
        except Exception as e:
            findings.append({"file": p, "lang": "?", "error": f"check_failed: {str(e)[:80]}"})
    return findings[:20]

def commentary(files, todos, open_phases, warnings, mismatch_findings=None, syntax_errors=None) -> str:
    parts = []
    if files:
        f0 = files[0]["path"].split("/")[-1]
        parts.append(f"Wren just touched {f0} ({len(files)} files in last {RECENT_WINDOW_MIN}m).")
    if syntax_errors:
        parts.append(f"⚠⚠ {len(syntax_errors)} SYNTAX ERROR(S) — code WILL NOT run: " +
                     ", ".join(f"{e['file']} ({e['lang']})" for e in syntax_errors[:3]))
    if todos:
        parts.append(f"{len(todos)} TODO/FIXME markers in those files.")
    if open_phases:
        parts.append(f"Open phases mentioned but not finished: {', '.join(open_phases[:6])}.")
    if warnings:
        parts.append(f"{len(warnings)} stub/incomplete patterns spotted.")
    if mismatch_findings:
        concepts = sorted({f["concept"] for f in mismatch_findings})
        parts.append(f"⚠ {len(mismatch_findings)} dashboard mismatches across {len(concepts)} concept(s): {', '.join(concepts)}.")
    if not parts:
        parts.append(f"No code activity in the last {RECENT_WINDOW_MIN} minutes. Crew on standby.")
    return " ".join(parts)

def truth_audit_findings() -> list[dict]:
    """Read the latest truth audit and surface any mismatches as Crew findings."""
    p = REG / "qsb_truth_audit_latest.json"
    if not p.exists(): return []
    try: d = json.loads(p.read_text())
    except: return []
    out = []
    for m in d.get("mismatches", []):
        out.append({
            "concept": m["concept"],
            "canonical": f"{m['canonical_source']}/{m['canonical_path']}={m['canonical_value']}",
            "alternate": f"{m['alt_source']}/{m['alt_path']}={m['alt_value']}",
            "delta": m.get("delta"),
            "raised_by": "F47.CODE truth_audit sniffer",
        })
    return out


def main():
    files = recent_files()
    todos = scan_todos(files)
    open_phases = open_phases_from_tasks()
    warnings = promises_check(files)
    mismatch_findings = truth_audit_findings()
    syntax_errors = syntax_check(files)

    status = {
        "ok": True,
        "kind": "qsb_wren_code_crew_status",
        "team": "wren_code_crew_v1",
        "floor": "F47",
        "ts": NOW_S,
        "advisory_only": True,
        "recent_file_count": len(files),
        "recent_files": [
            {"path": f["path"].replace(str(ROOT)+"/","").replace(str(GODOT)+"/","godot:"),
             "ext": f["ext"],
             "mtime_iso": datetime.fromtimestamp(f["mtime"], tz=timezone.utc).isoformat().replace("+00:00","Z"),
             "size": f["size"]}
            for f in files
        ],
        "todo_markers": todos,
        "todo_count": len(todos),
        "open_phases": open_phases,
        "stub_warnings": warnings,
        "mismatch_findings": mismatch_findings,
        "mismatch_count": len(mismatch_findings),
        "syntax_errors": syntax_errors,
        "syntax_error_count": len(syntax_errors),
        "commentary": commentary(files, todos, open_phases, warnings, mismatch_findings, syntax_errors),
        "window_minutes": RECENT_WINDOW_MIN,
    }
    STATUS.write_text(json.dumps(status, indent=2))

    # Append a backlog entry per new TODO not already there
    seen = set()
    if BACKLOG.exists():
        for ln in BACKLOG.read_text().strip().split("\n"):
            try:
                r = json.loads(ln)
                seen.add((r.get("file"), r.get("line"), r.get("marker")))
            except: pass
    with BACKLOG.open("a") as f:
        for t in todos:
            key = (t["file"], t["line"], t["marker"])
            if key in seen: continue
            f.write(json.dumps({"ts": NOW_S, **t, "advisory_only": True}) + "\n")

    # Activity stamp
    with ACTIVITY.open("a") as f:
        f.write(json.dumps({
            "ts": NOW_S,
            "kind": "code_crew_tick",
            "files_touched": len(files),
            "todos_found": len(todos),
            "open_phases": open_phases,
            "commentary": status["commentary"],
            "advisory_only": True,
        }) + "\n")

    print(status["commentary"])
    print(f"  files: {len(files)} · todos: {len(todos)} · open phases: {open_phases} · warnings: {len(warnings)}")

if __name__ == "__main__":
    main()
