#!/usr/bin/env python3
"""qsb_session_wakeup.py — surface critical context for a new Claude session.

Closes the memory-gap Ross flagged 2026-06-22: 'when i talk to you guys on a new
boot i still notice there are things you guys forget'. MEMORY.md caps at 200
lines, pitstops don't auto-load, F47 has too many tick records to scan.

This tool emits ONE markdown brief covering:
  1. Latest pitstop (path + topic + focus + next-on-resume)
  2. Last 15 HIGH-SIGNAL F47 stamps (drops triage_tick, hw_sample, build_forward_idle)
  3. Open tasks (still in_progress)
  4. Diary tail (last 10 lines)
  5. Most recent claude_meta_letter
  6. Fleet snapshot (bus + traders + ensembles + dash alive counts)

Usage:
  python3 tools/qsb_session_wakeup.py            # MD to stdout
  python3 tools/qsb_session_wakeup.py --json     # JSON to stdout
  python3 tools/qsb_session_wakeup.py --save     # write to data/registries/qsb_session_wakeup.md
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PITSTOPS = ROOT / "data/registries/pitstops"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
DIARY = ROOT / "data/registries/qsb_session_diary.md"
LETTERS = ROOT / "data/registries/qsb_claude_meta_letters.jsonl"
OUT_MD = ROOT / "data/registries/qsb_session_wakeup.md"

# F47 kinds that are NOISE (we drop them from the high-signal view)
NOISE_KINDS = {
    "triage_tick", "hw_sample", "assistant_reminder", "team_sync_auto",
    "build_forward_idle", "wren_local_agent_session", "hermes_local_agent_session",
    "oanda_history_pull", "classroom_evaluator_tick", "chat_mirror_tick",
    "kernel_chat_user_turn", "kernel_chat_reply",
}


def latest_pitstop() -> dict | None:
    if not PITSTOPS.exists():
        return None
    md = sorted(PITSTOPS.glob("pitstop_*.md"))
    if not md:
        return None
    last = md[-1]
    text = last.read_text()
    info = {"path": str(last), "name": last.name}
    # extract Topic / Focus / Next on resume
    for key, label in (("topic", r"\*\*Topic:\*\*\s*`([^`]+)`"),
                        ("focus", r"\*\*Focus:\*\*\s*(.+)"),
                        ("next",  r"## Next on resume\n([^\n]+)")):
        m = re.search(label, text)
        if m:
            info[key] = m.group(1).strip()
    return info


def f47_high_signal(limit: int = 15) -> list[dict]:
    if not F47.exists():
        return []
    rows = []
    with open(F47) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") in NOISE_KINDS:
                continue
            rows.append({
                "ts": r.get("ts"),
                "kind": r.get("kind"),
                "subject": r.get("subject", ""),
                "detail": r.get("detail", "")[:200],
                "sigs": r.get("signed_off_by", [])[:3],
            })
    return rows[-limit:]


def open_tasks() -> list[str]:
    """Read task storage if accessible (no direct API — fall back to stub)."""
    # Tasks live in the harness — we don't have a stable file. Skip if unavailable.
    return []


def diary_tail(lines: int = 10) -> list[str]:
    if not DIARY.exists():
        return []
    return DIARY.read_text().splitlines()[-lines:]


def last_letter() -> dict | None:
    if not LETTERS.exists():
        return None
    try:
        ll = LETTERS.read_text().splitlines()
        if not ll:
            return None
        for line in reversed(ll):
            try:
                return json.loads(line)
            except Exception:
                continue
    except Exception:
        return None


def fleet_snapshot() -> dict:
    ps = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True).stdout
    def n(pat: str) -> int:
        return len([l for l in ps.splitlines()
                     if re.search(pat, l) and "grep" not in l and "eval" not in l])
    return {
        "bus":            n(r"qsb_event_bus\.py"),
        "belief_updater": n(r"qsb_belief_updater\.py"),
        "regime_detector":n(r"qsb_regime_detector\.py"),
        "f41_oanda":      n(r"qsb_f41_oanda_stream\.py"),
        "f42_binance":    n(r"qsb_f42_binance_stream\.py"),
        "f43_alpaca":     n(r"qsb_f43_alpaca_stream\.py"),
        "traders":        n(r"qsb_belief_driven_trader\.py"),
        "ensembles":      n(r"qsb_ensemble_coordinator\.py"),
        "dashboard":      n(r"qsb_traders_live_serve\.py"),
    }


def render_md(data: dict) -> str:
    out = ["# QSB Session Wakeup"]
    from datetime import datetime, timezone
    out.append(f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}_\n")

    # Pitstop
    p = data["pitstop"]
    if p:
        out.append("## 1. Latest Pitstop")
        out.append(f"- **file**: `{p['path']}`")
        out.append(f"- **topic**: {p.get('topic','?')}")
        out.append(f"- **focus**: {p.get('focus','?')}")
        out.append(f"- **next on resume**: {p.get('next','?')}")
        out.append("")
    else:
        out.append("## 1. Latest Pitstop\n(no pitstops found)\n")

    # F47
    out.append("## 2. Recent High-Signal F47 Stamps")
    for r in data["f47"]:
        sigs = ", ".join(r["sigs"])
        out.append(f"- `{r['ts']}` **{r['kind']}** ({sigs})")
        out.append(f"  - {r['detail']}")
    out.append("")

    # Fleet
    f = data["fleet"]
    out.append("## 3. Fleet Snapshot")
    for k, v in f.items():
        marker = "✓" if v > 0 else "✗"
        out.append(f"- {marker} {k}: {v}")
    out.append("")

    # Diary
    out.append("## 4. Diary Tail")
    for ln in data["diary"]:
        out.append(f"  {ln}")
    out.append("")

    # Letter
    L = data["last_letter"]
    if L:
        out.append("## 5. Most Recent Meta-Letter")
        out.append(f"- `{L.get('ts','?')}` — _{L.get('subject', L.get('title', '?'))}_")
        body = L.get("body", L.get("text", L.get("detail", "")))[:500]
        out.append(f"  {body}")
        out.append("")

    out.append("---")
    out.append("_To regenerate: `python3 tools/qsb_session_wakeup.py --save`_")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--json", action="store_true", help="emit JSON instead of MD")
    p.add_argument("--save", action="store_true",
                    help="also write MD to data/registries/qsb_session_wakeup.md")
    p.add_argument("--limit", type=int, default=15)
    args = p.parse_args()

    data = {
        "pitstop":     latest_pitstop(),
        "f47":         f47_high_signal(args.limit),
        "fleet":       fleet_snapshot(),
        "diary":       diary_tail(),
        "last_letter": last_letter(),
    }
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        md = render_md(data)
        print(md)
        if args.save:
            OUT_MD.parent.mkdir(parents=True, exist_ok=True)
            OUT_MD.write_text(md)
            print(f"\n(saved to {OUT_MD})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
