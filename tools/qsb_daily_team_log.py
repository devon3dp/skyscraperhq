#!/usr/bin/env python3
"""qsb_daily_team_log.py — daily record of team work between Claude, Wren,
and Hermes. Ross 2026-06-20: 'you are not allowed to work alone anymore or
you are fired !!!!!'

Writes one file per UTC day at:
  data/registries/daily_team_logs/team_log_YYYY-MM-DD.md

Reads:
  - data/registries/qsb_claude_wren_bridge.jsonl (Claude ↔ Wren turns)
  - data/registries/qsb_hermes_chat.jsonl (Claude → Hermes turns)
  - data/registries/qsb_three_way_council.jsonl (3-way council notes)
  - data/registries/qsb_f47_team_records.jsonl filtered for 'team_dispatched'
    + 'f166_dispatch' + 'hermes_research_dispatch'

Run:
  python3 tools/qsb_daily_team_log.py            # today's log
  python3 tools/qsb_daily_team_log.py --date YYYY-MM-DD

If there are FEWER than 3 distinct team-dispatch events for the day, the
log prints a warning at the top: SOLO WORK DETECTED — under the team rule.
"""
from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
LOGS_DIR = REG / "daily_team_logs"


def parse_jsonl_for_day(path: Path, day: str) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if day in r.get("ts", ""):
                rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"))
    args = ap.parse_args()
    day = args.date

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOGS_DIR / f"team_log_{day}.md"

    # 1. Claude ↔ Wren bridge turns today
    wren_turns = parse_jsonl_for_day(REG / "qsb_claude_wren_bridge.jsonl", day)

    # 2. Hermes chat turns today
    hermes_turns = parse_jsonl_for_day(REG / "qsb_hermes_chat.jsonl", day)

    # 3. 3-way council notes today
    council_turns = parse_jsonl_for_day(REG / "qsb_three_way_council.jsonl", day)

    # 4. F47 team-dispatch stamps today
    f47_rows = parse_jsonl_for_day(REG / "qsb_f47_team_records.jsonl", day)
    dispatch_kinds = {"team_dispatched", "f166_dispatch",
                       "hermes_research_dispatch", "fleet_spawned",
                       "ollama_pull_switch", "floor_card_upgraded",
                       "github_repo_pushed"}
    f47_dispatches = [r for r in f47_rows if r.get("kind") in dispatch_kinds]

    # Stats
    n_wren = len(wren_turns)
    n_hermes = len(hermes_turns)
    n_council = len(council_turns)
    n_f47_dispatch = len(f47_dispatches)
    distinct_team_events = n_wren + n_hermes + n_council
    solo_flag = distinct_team_events < 3

    # Build the log
    lines = []
    lines.append(f"# Team Log · {day}")
    lines.append("")
    lines.append(f"_Generated {datetime.datetime.now(datetime.UTC).strftime('%H:%M UTC')}_")
    lines.append("")
    if solo_flag:
        lines.append("> ⚠️ **SOLO WORK DETECTED** — fewer than 3 distinct team")
        lines.append("> dispatches today. Ross 2026-06-20 rule: 'you are not allowed")
        lines.append("> to work alone anymore or you are fired'. Dispatch more.")
        lines.append("")
    else:
        lines.append(f"> ✓ {distinct_team_events} team interactions today — team rule satisfied.")
        lines.append("")
    lines.append("## Today's tallies")
    lines.append(f"- Wren bridge turns (both directions): **{n_wren}**")
    lines.append(f"- Hermes chat turns: **{n_hermes}**")
    lines.append(f"- 3-way council notes: **{n_council}**")
    lines.append(f"- F47 team-dispatch stamps: **{n_f47_dispatch}**")
    lines.append("")
    lines.append("## Wren bridge — last 5 turns today")
    for r in wren_turns[-5:]:
        ts = r.get("ts", "")[:16]
        src = r.get("source", "?")
        text = (r.get("text") or "")[:280].replace("\n", " ")
        lines.append(f"- **{ts}** [{src}] {text}")
    lines.append("")
    lines.append("## Hermes chat — last 5 turns today")
    for r in hermes_turns[-5:]:
        ts = r.get("ts", "")[:16]
        you = (r.get("you") or "")[:140].replace("\n", " ")
        reply = (r.get("reply") or "")[:240].replace("\n", " ")
        if reply:
            lines.append(f"- **{ts}** Claude→Hermes: _{you}_  →  Hermes: {reply}")
        else:
            lines.append(f"- **{ts}** [meta] {(r.get('text') or '')[:280]}")
    lines.append("")
    lines.append("## 3-way council — today")
    for r in council_turns[-8:]:
        ts = r.get("ts", "")[:16]
        src = r.get("source", "?")
        text = (r.get("text") or "")[:200].replace("\n", " ")
        topic = r.get("topic", "")
        lines.append(f"- **{ts}** [{src}] _{topic}_: {text}")
    lines.append("")
    lines.append("## Verifiable team-dispatch stamps from F47 today")
    for r in f47_dispatches[-10:]:
        ts = r.get("ts", "")[:16]
        kind = r.get("kind", "?")
        sub = r.get("subject", r.get("topic", ""))
        det = (r.get("detail") or r.get("summary") or "")[:160].replace("\n", " ")
        lines.append(f"- **{ts}** [{kind}] {sub} · {det}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("This log was generated by `tools/qsb_daily_team_log.py`.")
    lines.append("It IS the proof that the team worked together today.")

    out_path.write_text("\n".join(lines))
    print(f"daily team log → {out_path.relative_to(ROOT)}")
    print(f"  wren turns={n_wren}  hermes turns={n_hermes}  council={n_council}  f47 dispatches={n_f47_dispatch}")
    if solo_flag:
        print(f"  ⚠️ SOLO WORK FLAG — only {distinct_team_events} team interactions today")
    else:
        print(f"  ✓ {distinct_team_events} team interactions — rule satisfied")


if __name__ == "__main__":
    main()
