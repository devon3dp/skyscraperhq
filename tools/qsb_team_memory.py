#!/usr/bin/env python3
"""qsb_team_memory.py — independent memory for every team member.

Per Ross 2026-06-25: "all team players must have their own independent daily
hourly memory short term and long term you included".

Members: claude, wren, hermes, openai, deepseek
Memory layout per member at data/registries/team_memory/<member>/:
  hourly/   — 48h rolling
  daily/    — kept forever
  curated/  — high-signal lessons
  MEMORY.md — local index

Source of truth: F47 stamps + diary + bus journal.

DeepSeek-authored body (2026-06-25), Claude-completed imports/globals.
"""
import argparse, json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TEAM_MEMORY = ROOT / "data/registries/team_memory"
F47_PATH = ROOT / "data/registries/qsb_f47_team_records.jsonl"
DIARY_PATH = ROOT / "data/registries/qsb_session_diary.md"
BUS_JOURNAL = ROOT / "data/registries/qsb_bus_journal.jsonl"

MEMBERS = ["claude", "wren", "hermes", "iquest", "qwen3", "llava", "openai", "deepseek", "f47ops", "f166ops", "f41workers", "f42workers", "f43workers"]
STATELESS = {"openai", "deepseek"}
# iquest-coder-v1:40b-instruct via qsb_local_agent_call.py — 40B coding specialist


def _ensure_member_dir(member: str):
    for sub in ("hourly", "daily", "curated"):
        (TEAM_MEMORY / member / sub).mkdir(parents=True, exist_ok=True)
    idx = TEAM_MEMORY / member / "MEMORY.md"
    if not idx.exists():
        idx.write_text(f"# {member.upper()} Memory Index\n\n")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hour_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def _today_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_f47(limit: int = 50) -> list:
    events = []
    if F47_PATH.exists():
        with open(F47_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return events[-limit:]


def _read_diary() -> str:
    if DIARY_PATH.exists():
        return DIARY_PATH.read_text()
    return ""


def _read_bus(limit: int = 30) -> list:
    entries = []
    if BUS_JOURNAL.exists():
        try:
            with open(BUS_JOURNAL) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
    return entries[-limit:]


def _scan_hour_sources(hour: str) -> str:
    events = _read_f47()
    diary = _read_diary()
    bus = _read_bus()
    hour_prefix = hour[:13]
    context_lines = []
    for e in events:
        ts = e.get("ts", "") or e.get("timestamp", "")
        if ts.startswith(hour_prefix):
            ev = e.get("event", "?")
            body = (e.get("body","") or "")[:80]
            context_lines.append(f"F47: {ev} {body}")
    for line in diary.split("\n"):
        if hour_prefix in line:
            context_lines.append(f"Diary: {line.strip()[:120]}")
    for entry in bus:
        ts = entry.get("ts", entry.get("timestamp", ""))
        if ts.startswith(hour_prefix):
            n = entry.get("name", "?")
            context_lines.append(f"Bus: {n}")
    if not context_lines:
        return f"[{hour}] No activity detected"
    seen = set(); unique = []
    for line in context_lines:
        if line not in seen:
            seen.add(line); unique.append(line)
    summary = "\n  - ".join(unique[:8])
    extra = f" (+{len(unique)-8} more)" if len(unique) > 8 else ""
    return f"[{hour}]\n  - {summary}{extra}"


def _promote_high_signal(source_text: str, member: str) -> list:
    curated = []
    signals = [
        r"(?i)(lesson|learned|always|never|critical|important|must|blocker|bug|fix)",
        r"(?i)(pattern|systematic|recurring|consistently|invariant)",
        r"(?i)(architectur|design|contract|decision|rationale)",
    ]
    for line in source_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sig in signals:
            if re.search(sig, line) and len(line) > 30:
                curated.append(line); break
    if curated:
        curated_dir = TEAM_MEMORY / member / "curated"
        curated_file = curated_dir / f"curated_{_today_stamp()}.md"
        with open(curated_file, "a") as f:
            for c in curated:
                f.write(f"- {c}\n")
    return curated


def _update_index(member: str, action: str, path: str):
    index_path = TEAM_MEMORY / member / "MEMORY.md"
    with open(index_path, "a") as f:
        f.write(f"- {_now_ts()} | {action} | {path}\n")


def write_hourly(member: str):
    _ensure_member_dir(member)
    hour = _hour_stamp()
    summary = _scan_hour_sources(hour)
    fname = f"hourly_{hour}.md"
    fpath = TEAM_MEMORY / member / "hourly" / fname
    fpath.write_text(f"# Hourly Summary — {member} — {hour}\n\n{summary}\n")
    _update_index(member, "write_hourly", str(fpath))
    print(f"OK {member} hourly {hour}: wrote {fpath}")


def write_daily(member: str):
    _ensure_member_dir(member)
    today = _today_stamp()
    hourly_dir = TEAM_MEMORY / member / "hourly"
    today_lines = []
    for f in sorted(hourly_dir.glob(f"hourly_{today}T*.md")):
        today_lines.append(f.read_text())
    if not today_lines:
        print(f"{member} no hourly data for {today}")
        return
    daily_path = TEAM_MEMORY / member / "daily" / f"daily_{today}.md"
    with open(daily_path, "w") as f:
        f.write(f"# Daily Memory Rollup — {member} — {today}\n\n")
        for line in today_lines:
            f.write(line + "\n\n")
    curated = _promote_high_signal("\n".join(today_lines), member)
    _update_index(member, "write_daily", str(daily_path))
    print(f"OK {member} daily {today}: {len(today_lines)} hours, {len(curated)} curated")


def read_recent(member: str) -> str:
    _ensure_member_dir(member)
    out = [f"# {member.upper()} — Recent Memory Context", f"Generated: {_now_ts()}", ""]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    hourly_dir = TEAM_MEMORY / member / "hourly"
    out.append("## HOURLY (last 24h)")
    for f in sorted(hourly_dir.glob("hourly_*.md"), reverse=True):
        m = re.search(r"hourly_(\d{4}-\d{2}-\d{2}T\d{2})", f.name)
        if m:
            hour_dt = datetime.strptime(m.group(1), "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
            if hour_dt >= cutoff:
                out.append(f.read_text())
    daily_dir = TEAM_MEMORY / member / "daily"
    out.append("\n## DAILY (last 7 days)")
    for f in sorted(daily_dir.glob("daily_*.md"), reverse=True)[:7]:
        out.append(f"### {f.name}")
        out.append(f.read_text()[:500] + "...")
    curated_dir = TEAM_MEMORY / member / "curated"
    out.append("\n## CURATED LESSONS")
    # 2026-06-27 fix: was missing floors_knowledge_*.md and any future naming;
    # now globs *.md in curated/ so all knowledge files reach the model.
    curated_files = sorted(
        list(curated_dir.glob("*.md")),
        key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    for f in curated_files:
        out.append(f"### {f.name}")
        # 2026-06-26 fix: 1200 chars cut off the LATE SESSION block where today's
        # actual events are appended. Raised to 4000 to fit a full day of lessons.
        out.append(f.read_text()[:4000])
    return "\n".join(out)


def inject_provider_header(member: str) -> str:
    if member not in STATELESS:
        return ""
    recent = read_recent(member)
    lines = recent.split("\n")
    condensed = []
    wc = 0
    # 2026-06-26: was capped at 200 words — too tight, providers couldn't recall
    # today's events. Raised to 800 words (≈3200 chars) — still under per-call cost cap.
    for line in lines:
        w = len(line.split())
        if wc + w > 800:
            break
        condensed.append(line); wc += w
    header = f"""# {member.upper()} — MEMORY INJECTION (2026-06-25 team-memory subsystem)
Timestamp: {_now_ts()}
You are stateless — this context was injected from your team-memory file.

"""
    header += "\n".join(condensed)
    header += f"\n\n({wc} words injected)"
    return header


def cli():
    p = argparse.ArgumentParser(description="QSB Team Memory")
    p.add_argument("member", choices=MEMBERS + ["all"])
    p.add_argument("action", choices=["write_hourly","write_daily","read_recent","inject_provider_header"])
    p.add_argument("--output")
    args = p.parse_args()
    members = MEMBERS if args.member == "all" else [args.member]
    for m in members:
        if args.action == "write_hourly":   write_hourly(m)
        elif args.action == "write_daily":  write_daily(m)
        elif args.action == "read_recent":
            r = read_recent(m)
            if args.output: Path(args.output).write_text(r)
            else: print(r)
        elif args.action == "inject_provider_header":
            r = inject_provider_header(m)
            if r:
                if args.output: Path(args.output).write_text(r)
                else: print(r)


if __name__ == "__main__":
    cli()
