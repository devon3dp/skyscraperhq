#!/usr/bin/env python3
"""qsb_wren_bug_catcher.py — Wren goes bug-hunting (2026-07-03).

Ross verbatim: "teach wren how to go collecting bugs in our systems ?
animated bug catcher u get me etc"

Wren was reflecting instead of shipping. This gives her a real role:
BUG CATCHER. Every evolution cycle where kind == action_bug_catcher, the
loop primes her prompt with a list of REAL bug candidates gathered from
across the tower's error surfaces, and she picks ONE to investigate +
propose a fix for.

Bug candidate sources (weighted by recency and severity):
  1. Python tracebacks in logs/ (last hour)
  2. F47 rows with kind ending _err
  3. Sage-audit flags (empty finals, loops, wall outliers)
  4. Recent tracker-vs-broker mismatches in event bus
  5. HTTP 5xx / 4xx in dashboard logs
  6. Broken jsonl lines (parse failures) in data/registries/

Each catch appends to data/registries/qsb_wren_bug_catches.jsonl:
    {ts, bug_id, source, severity, file, line, snippet, disposition,
     proposed_fix, session_id}

CLI:
  python3 tools/qsb_wren_bug_catcher.py --scan          # scan all sources, top N
  python3 tools/qsb_wren_bug_catcher.py --scan --n 5
  python3 tools/qsb_wren_bug_catcher.py --caught        # what she's caught today
  python3 tools/qsb_wren_bug_catcher.py --catch '{...}' # log a catch (invoked by loop)

The scan is READ-ONLY. No fixes are applied by this tool — Wren proposes
via wren_propose_patch under claude_signoff mode. Real-money gates untouched.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "logs"
F47 = REG / "qsb_f47_team_records.jsonl"
SAGE = REG / "qsb_wren_sage_audit.jsonl"
BUS = REG / "qsb_bus_journal.jsonl"
CATCHES = REG / "qsb_wren_bug_catches.jsonl"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds_ago(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return 9999999


def scan_tracebacks(max_hits: int = 12) -> list:
    """Find Python tracebacks in logs/ modified in the last hour."""
    out = []
    if not LOGS.exists(): return out
    now = datetime.now(timezone.utc).timestamp()
    for p in LOGS.rglob("*.log"):
        try:
            if now - p.stat().st_mtime > 3600 * 6: continue
            text = p.read_text(errors="ignore")
            for m in re.finditer(r"Traceback \(most recent call last\):.*?(?=\n\S|\Z)",
                                 text, flags=re.DOTALL):
                snippet = m.group(0).strip()[:400]
                # find the actual error line
                err_line = ""
                for line in snippet.splitlines()[::-1]:
                    if line and not line.startswith(" ") and ":" in line:
                        err_line = line
                        break
                out.append({
                    "source": "traceback",
                    "severity": "high" if "ERROR" in snippet or "CRITICAL" in snippet else "med",
                    "file": str(p.relative_to(ROOT)),
                    "err_line": err_line[:200],
                    "snippet": snippet,
                })
                if len(out) >= max_hits: return out
        except Exception:
            continue
    return out


def scan_f47_errs(max_hits: int = 8) -> list:
    """F47 rows with kind ending in _err."""
    if not F47.exists(): return []
    out = []
    for l in F47.read_text(errors="ignore").splitlines()[-2000:]:
        try:
            d = json.loads(l)
            kind = (d.get("kind") or "")
            if kind.endswith("_err") or "error" in kind.lower():
                out.append({
                    "source": "f47_err",
                    "severity": "med",
                    "kind": kind,
                    "operator": d.get("operator", "?"),
                    "ts": d.get("ts", ""),
                    "snippet": (d.get("summary") or "")[:400],
                })
        except Exception:
            continue
    return out[-max_hits:]


def scan_sage_flags(max_hits: int = 8) -> list:
    """Sage audit flags (empty finals, loops, wall outliers)."""
    if not SAGE.exists(): return []
    out = []
    for l in SAGE.read_text(errors="ignore").splitlines()[-500:]:
        try:
            d = json.loads(l)
            flags = d.get("flags", []) or []
            if flags:
                out.append({
                    "source": "sage_flag",
                    "severity": "low",
                    "flags": flags,
                    "session_id": d.get("session_id", ""),
                    "snippet": ", ".join(flags)[:200],
                })
        except Exception:
            continue
    return out[-max_hits:]


def scan_broken_jsonl(max_hits: int = 4) -> list:
    """JSONL files with parse errors — bounded: skip huge files, tail only."""
    out = []
    files = []
    for p in sorted(REG.glob("*.jsonl")):
        try:
            sz = p.stat().st_size
            if sz > 50 * 1024 * 1024: continue  # skip huge files (>50MB)
            files.append(p)
        except Exception: continue
    files = files[:8]
    for p in files:
        try:
            sz = p.stat().st_size
            with p.open("rb") as f:
                f.seek(max(0, sz - 20000))
                tail_bytes = f.read()
            lines = tail_bytes.decode("utf-8", errors="ignore").splitlines()[-100:]
            bad = 0
            first_bad = ""
            for i, l in enumerate(lines):
                if not l.strip(): continue
                try:
                    json.loads(l)
                except Exception as e:
                    bad += 1
                    if not first_bad:
                        first_bad = f"line {i}: {str(e)[:80]}"
            if bad > 0:
                out.append({
                    "source": "jsonl_corrupt",
                    "severity": "high" if bad > 5 else "low",
                    "file": str(p.relative_to(ROOT)),
                    "bad_count": bad,
                    "snippet": first_bad,
                })
                if len(out) >= max_hits: break
        except Exception:
            continue
    return out


def scan_dashboard_5xx(max_hits: int = 4) -> list:
    """Dashboard logs mentioning HTTP 5xx or connection errors."""
    dl = LOGS / "dashboards"
    if not dl.exists(): return []
    out = []
    for p in dl.glob("*.log"):
        try:
            text = p.read_text(errors="ignore")[-30000:]  # tail only
            for pattern in (r"HTTP 5\d\d", r"ConnectionRefused", r"Failed to connect"):
                for m in re.finditer(pattern, text):
                    start = max(0, m.start() - 80)
                    ctx = text[start:m.end()+120].replace("\n", " ")
                    out.append({
                        "source": "dash_5xx",
                        "severity": "med",
                        "file": str(p.relative_to(ROOT)),
                        "pattern": pattern,
                        "snippet": ctx.strip()[:300],
                    })
                    if len(out) >= max_hits: return out
        except Exception:
            continue
    return out[:max_hits]


def already_caught(source: str, snippet: str) -> bool:
    """Dedup — skip bugs already logged today."""
    if not CATCHES.exists(): return False
    today = utc_iso()[:10]
    for l in CATCHES.read_text(errors="ignore").splitlines():
        try:
            d = json.loads(l)
            if d.get("ts", "").startswith(today) and d.get("source") == source:
                if (d.get("snippet", "")[:80]) == snippet[:80]:
                    return True
        except Exception:
            continue
    return False


def gather(max_total: int = 12) -> list:
    """Aggregate all sources, dedupe against today's catches, rank by severity."""
    all_bugs = []
    all_bugs.extend(scan_tracebacks())
    all_bugs.extend(scan_f47_errs())
    all_bugs.extend(scan_sage_flags())
    all_bugs.extend(scan_broken_jsonl())
    all_bugs.extend(scan_dashboard_5xx())
    # dedupe
    fresh = [b for b in all_bugs if not already_caught(b["source"], b.get("snippet", ""))]
    # rank: high > med > low
    sev_rank = {"high": 0, "med": 1, "low": 2}
    fresh.sort(key=lambda b: sev_rank.get(b.get("severity","low"), 3))
    return fresh[:max_total]


def catch(bug: dict, session_id: str = "", disposition: str = "flagged", proposed_fix: str = ""):
    """Log a bug catch."""
    row = {
        "ts": utc_iso(),
        "bug_id": f"bug_{int(datetime.now(timezone.utc).timestamp())}",
        "source": bug.get("source", "?"),
        "severity": bug.get("severity", "low"),
        "file": bug.get("file", ""),
        "snippet": (bug.get("snippet") or bug.get("err_line") or "")[:400],
        "disposition": disposition,
        "proposed_fix": proposed_fix[:400],
        "session_id": session_id,
    }
    CATCHES.parent.mkdir(parents=True, exist_ok=True)
    with CATCHES.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def caught_today() -> list:
    if not CATCHES.exists(): return []
    today = utc_iso()[:10]
    out = []
    for l in CATCHES.read_text(errors="ignore").splitlines():
        try:
            d = json.loads(l)
            if d.get("ts", "").startswith(today):
                out.append(d)
        except Exception:
            continue
    return out


def caught_total() -> int:
    if not CATCHES.exists(): return 0
    return sum(1 for l in CATCHES.read_text(errors="ignore").splitlines() if l.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="scan sources, show candidates")
    ap.add_argument("--caught", action="store_true", help="show today's catches")
    ap.add_argument("--catch", help="log a catch (JSON body)")
    ap.add_argument("--n", type=int, default=6, help="max candidates in scan")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    a = ap.parse_args()

    if a.catch:
        try:
            body = json.loads(a.catch)
        except Exception as e:
            print(f"invalid --catch JSON: {e}", file=sys.stderr); sys.exit(2)
        row = catch(body,
                    session_id=body.get("session_id",""),
                    disposition=body.get("disposition","flagged"),
                    proposed_fix=body.get("proposed_fix",""))
        print(json.dumps(row, indent=2))
        return

    if a.caught:
        rows = caught_today()
        if a.json:
            print(json.dumps({"count": len(rows), "rows": rows}, indent=2))
            return
        print(f"═ Bug catches today: {len(rows)} (all time: {caught_total()}) ═")
        for r in rows[-10:]:
            print(f"  {r.get('ts','')[:19]}  {r.get('severity','?'):4} {r.get('source','?'):15}  {(r.get('snippet','') or '')[:100]}")
        return

    bugs = gather(a.n)
    if a.json:
        print(json.dumps({"count": len(bugs), "candidates": bugs}, indent=2))
        return
    print(f"═ Bug candidates ({len(bugs)}) — Wren picks ONE and proposes a fix ═\n")
    for i, b in enumerate(bugs):
        print(f"  [{i}] {b.get('severity','?'):4} {b.get('source','?'):15}  {(b.get('file','') or '')[:40]}")
        print(f"      {(b.get('snippet') or b.get('err_line') or '')[:220]}")
        print()


if __name__ == "__main__":
    main()
