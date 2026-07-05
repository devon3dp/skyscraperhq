#!/usr/bin/env python3
"""qsb_pitstop.py — Ross-triggered immediate state flush + workstream pointer.

Ross 2026-06-19: "when i say pitstop you have to make a memory on the work
you have been doing make a back up of all the work we doing time stamp it
and make sure you do this when i say pitstop so when i reboot even a new
claude like you can catch up and carry on where we left off"

Run: python3 tools/qsb_pitstop.py "<topic_slug>" ["one-line focus statement"]

Writes ONE master index at data/registries/pitstops/pitstop_<UTC_ISO>_<topic>.md
that new-claude reads first on wake. Also forces the heartbeat surfaces
to flush immediately so nothing is lost to the 5-min lag.
"""
import argparse
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
REG = REPO / "data" / "registries"
PITSTOPS = REG / "pitstops"
PITSTOP_TMP = PITSTOPS / "tmp"
LETTERS = REG / "qsb_claude_meta_letters.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
DIARY = REG / "qsb_session_diary.md"
WAKE = REG / "qsb_wake_briefing.md"
BUFFER = REG / "qsb_buffer_state.json"

# /tmp files that disappear on reboot but matter to a workstream resume.
# Globs are evaluated against /tmp. Add patterns here — or pass extras on
# the CLI via --tmp-files=...  The pitstop snapshot copies each matching
# file to data/registries/pitstops/tmp/<ts>/<original_path> and writes a
# tmp_restore_<ts>.sh that puts them back on wake.
DEFAULT_TMP_PATTERNS = [
    "/tmp/qwen32b_*.sh",
    "/tmp/qwen32b_*.log",
    "/tmp/qsb_*",
    "/tmp/tasklist_*.json",
    "/tmp/skyscraper/*.log",
]
# Big or numerous artifacts handled separately so we can cap counts.
SCREENSHOT_GLOB = "/tmp/skyscraper/shots/*.png"
SCREENSHOT_KEEP_RECENT = 30  # only the N most recently-modified images


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def safe_slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s.lower())[:60]


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def append_diary(line: str) -> None:
    DIARY.parent.mkdir(parents=True, exist_ok=True)
    with DIARY.open("a") as f:
        f.write(line + "\n")


def force_buffer_snapshot() -> str:
    """Trigger the buffer_snapshot tool immediately (don't wait for heartbeat)."""
    tool = REPO / "tools" / "qsb_buffer_snapshot.py"
    if not tool.exists():
        return "buffer_snapshot tool not found"
    try:
        r = subprocess.run(
            [sys.executable, str(tool)],
            capture_output=True, text=True, timeout=30,
        )
        return f"ok (rc={r.returncode})"
    except Exception as e:
        return f"failed: {e}"


def force_wake_briefing() -> str:
    tool = REPO / "tools" / "qsb_wake_briefing.py"
    if not tool.exists():
        return "wake_briefing tool not found"
    try:
        r = subprocess.run(
            [sys.executable, str(tool)],
            capture_output=True, text=True, timeout=30,
        )
        return f"ok (rc={r.returncode})"
    except Exception as e:
        return f"failed: {e}"


def force_chat_mirror() -> str:
    tool = REPO / "tools" / "qsb_chat_mirror.py"
    if not tool.exists():
        return "chat_mirror tool not found"
    try:
        r = subprocess.run(
            [sys.executable, str(tool)],
            capture_output=True, text=True, timeout=60,
        )
        return f"ok (rc={r.returncode})"
    except Exception as e:
        return f"failed: {e}"


def read_last_n_lines(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    with path.open() as f:
        return f.readlines()[-n:]


def tasklist_json_path(ts: str) -> Path:
    return PITSTOPS / f"tasklist_{ts}.json"


def snapshot_tmp_files(ts_safe: str, extra_globs: list[str]) -> dict:
    """Copy /tmp files matching DEFAULT_TMP_PATTERNS + extra_globs into a
    persistent snapshot directory, and write a tmp_restore_<ts>.sh that puts
    them back on wake. Returns a dict with copied paths + restore script
    path so the master.md can mention them."""
    snap_dir = PITSTOP_TMP / ts_safe
    snap_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    skipped = []

    # Plain patterns — copy all matches.
    for pat in DEFAULT_TMP_PATTERNS + (extra_globs or []):
        for src in glob.glob(pat):
            try:
                src_p = Path(src)
                if not src_p.is_file():
                    continue
                # Mirror the original /tmp path under snap_dir so restore is
                # mechanical: <snap_dir>/tmp/... → /tmp/...
                rel = src_p.relative_to("/")
                dest = snap_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_p, dest)
                copied.append(str(src_p))
            except Exception as e:
                skipped.append(f"{src} ({e})")

    # Screenshots — cap at N most recent so we don't bloat the snapshot.
    shots = sorted(glob.glob(SCREENSHOT_GLOB),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    for src in shots[:SCREENSHOT_KEEP_RECENT]:
        try:
            src_p = Path(src)
            rel = src_p.relative_to("/")
            dest = snap_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_p, dest)
            copied.append(str(src_p))
        except Exception as e:
            skipped.append(f"{src} ({e})")

    # Restore script — mode 0755, copies everything back.
    restore_script = PITSTOPS / f"tmp_restore_{ts_safe}.sh"
    snap_root = snap_dir / "tmp"
    restore_script.write_text(
        "#!/bin/bash\n"
        f"# Auto-generated by qsb_pitstop.py at {ts_safe}.\n"
        "# Restores /tmp files saved at pitstop time, in case the host\n"
        "# was rebooted and /tmp was wiped. Safe to run multiple times.\n"
        "set -u\n"
        f"SNAP_ROOT={snap_root.as_posix()!r}\n"
        "if [[ ! -d \"$SNAP_ROOT\" ]]; then\n"
        "  echo \"no snapshot at $SNAP_ROOT\"; exit 0\n"
        "fi\n"
        "count=0\n"
        "# Use rsync if available (preserves perms + mod-time); fall back to cp -p.\n"
        "if command -v rsync >/dev/null 2>&1; then\n"
        "  rsync -a \"$SNAP_ROOT/\" /tmp/\n"
        "  count=$(find \"$SNAP_ROOT\" -type f | wc -l)\n"
        "else\n"
        "  while IFS= read -r f; do\n"
        "    rel=${f#$SNAP_ROOT/}\n"
        "    dest=/tmp/$rel\n"
        "    mkdir -p \"$(dirname \"$dest\")\"\n"
        "    cp -p \"$f\" \"$dest\"\n"
        "    count=$((count+1))\n"
        "  done < <(find \"$SNAP_ROOT\" -type f)\n"
        "fi\n"
        "# Make any restored .sh executable so they're runnable right away.\n"
        "find /tmp -maxdepth 4 -name '*.sh' -newer \"$SNAP_ROOT\" -exec chmod +x {} \\; 2>/dev/null\n"
        "echo \"restored $count files from $SNAP_ROOT to /tmp\"\n"
    )
    restore_script.chmod(0o755)

    return {
        "snapshot_dir": str(snap_dir.relative_to(REPO)),
        "restore_script": str(restore_script.relative_to(REPO)),
        "copied_count": len(copied),
        "copied": copied,
        "skipped": skipped,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", help="short slug for the workstream e.g. f47_walkable_interior")
    ap.add_argument("focus", nargs="?", default="", help="one-line focus statement")
    ap.add_argument("--tasklist", default="", help="optional path to JSON file with current TaskList contents")
    ap.add_argument("--next-steps", default="", help="one-line: what to do first on resume")
    ap.add_argument("--blockers", default="", help="one-line: known blockers")
    ap.add_argument("--tmp-files", default="", help="extra glob(s) under /tmp to snapshot, comma-separated")
    ap.add_argument("--skip-tmp", action="store_true", help="skip the /tmp snapshot for this pitstop")
    args = ap.parse_args()

    ts = utc_now_iso()
    ts_safe = ts.replace(":", "").replace("-", "").replace(".", "")
    topic = safe_slug(args.topic)
    PITSTOPS.mkdir(parents=True, exist_ok=True)
    master = PITSTOPS / f"pitstop_{ts_safe}_{topic}.md"

    # 1. Force-flush heartbeat surfaces NOW (don't wait for 5-min tick).
    flush_results = {
        "buffer_snapshot": force_buffer_snapshot(),
        "wake_briefing": force_wake_briefing(),
        "chat_mirror": force_chat_mirror(),
    }
    flush_failed = [k for k, v in flush_results.items() if not v.startswith("ok")]
    if flush_failed:
        sys.stderr.write(
            f"⚠️ PITSTOP FLUSH FAILURES: {flush_failed} — master index will be written but "
            f"these surfaces did NOT flush. Check {flush_results} and retry.\n"
        )

    # 2. Optional TaskList snapshot — caller passes a JSON file because
    #    qsb_pitstop.py cannot read Claude Code's TaskList directly.
    tasklist_text = ""
    tasklist_warning = ""
    if args.tasklist:
        tl_src = Path(args.tasklist)
        if not tl_src.exists():
            tasklist_warning = f"⚠️ --tasklist path {tl_src} does not exist; TaskList NOT snapshotted"
            sys.stderr.write(tasklist_warning + "\n")
        else:
            raw = tl_src.read_text()
            try:
                parsed = json.loads(raw)
                if not parsed:
                    tasklist_warning = f"⚠️ --tasklist {tl_src} parsed to empty value; TaskList NOT snapshotted"
                    sys.stderr.write(tasklist_warning + "\n")
                else:
                    tasklist_text = raw
                    tl_dest = tasklist_json_path(ts_safe)
                    tl_dest.write_text(tasklist_text)
            except json.JSONDecodeError as e:
                tasklist_warning = f"⚠️ --tasklist {tl_src} is not valid JSON ({e}); TaskList NOT snapshotted"
                sys.stderr.write(tasklist_warning + "\n")

    # 2b. /tmp snapshot — /tmp dies on reboot; snapshot known patterns now.
    tmp_snapshot = None
    if not args.skip_tmp:
        extra = [s.strip() for s in args.tmp_files.split(",") if s.strip()]
        try:
            tmp_snapshot = snapshot_tmp_files(ts_safe, extra)
        except Exception as e:
            sys.stderr.write(f"⚠️ tmp snapshot failed: {e}\n")
            tmp_snapshot = {"copied_count": 0, "error": str(e),
                            "snapshot_dir": "(failed)", "restore_script": "(failed)",
                            "copied": [], "skipped": []}

    # 3. Recent diary tail + F47 tail for the master index.
    diary_tail = "".join(read_last_n_lines(DIARY, 12))
    f47_rows = read_last_n_lines(F47, 20)
    f47_summary_lines = []
    for line in f47_rows:
        try:
            r = json.loads(line)
            if "tick" in r.get("kind", "") or "heartbeat" in r.get("kind", ""):
                continue
            f47_summary_lines.append(
                f"- {r.get('ts','?')[:19]}  {r.get('kind','?')}  {str(r.get('detail',''))[:100]}"
            )
        except Exception:
            pass
    f47_tail = "\n".join(f47_summary_lines[-10:])

    # 4. Write the master index.
    flush_warning = ""
    if flush_failed:
        flush_warning = (
            f"\n## ⚠️ FLUSH FAILURE WARNING\n"
            f"The following surfaces did NOT flush cleanly at pitstop time: **{', '.join(flush_failed)}**.\n"
            f"This master index was still written, but the freshly-regenerated wake_briefing or "
            f"chat_mirror may be stale. Re-run the failed tools by hand on resume before trusting them.\n"
        )

    master.write_text(
        f"""# PITSTOP — {ts}
**Topic:** `{topic}`
**Focus:** {args.focus or '(unspecified)'}
{flush_warning}

## Resume instructions for new-claude (or returning-old-claude)
1. Read this whole file.
2. Read `data/registries/qsb_wake_briefing.md` (freshly regenerated by this pitstop).
3. Read the last 3 entries in `data/registries/qsb_claude_meta_letters.jsonl`.
4. Re-create TaskList from `{tasklist_json_path(ts_safe).name if tasklist_text else '(no TaskList snapshot)'}` if present.
5. Continue at "Next on resume" below.

## Next on resume
{args.next_steps or '(unspecified — read recent diary tail below to infer)'}

## Known blockers at pitstop time
{args.blockers or '(none recorded)'}

## TaskList at pitstop time
{('See `' + tasklist_json_path(ts_safe).name + '` in this directory.') if tasklist_text else '(not snapshotted — caller did not pass --tasklist)'}

## Recent F47 records (last 10 non-tick)
{f47_tail or '(none)'}

## Recent diary tail
```
{diary_tail or '(empty)'}
```

## Heartbeat surface flush results
- buffer_snapshot: {flush_results['buffer_snapshot']}
- wake_briefing: {flush_results['wake_briefing']}
- chat_mirror: {flush_results['chat_mirror']}

## /tmp snapshot (survives reboot)
{('Snapshotted **' + str(tmp_snapshot['copied_count']) + ' files** to `' + tmp_snapshot['snapshot_dir'] + '`.  ') if tmp_snapshot and tmp_snapshot.get('copied_count') else '(no /tmp files captured — either none matched the default patterns or --skip-tmp was set)'}
{('To restore them after reboot: `bash ' + tmp_snapshot['restore_script'] + '`') if tmp_snapshot and tmp_snapshot.get('copied_count') else ''}

---
_Created by `tools/qsb_pitstop.py`. Index at `data/registries/pitstops/`._
"""
    )

    # 5. Stamp F47 + diary.
    append_jsonl(F47, {
        "ts": ts, "kind": "pitstop", "operator": "claude",
        "topic": topic, "focus": args.focus,
        "next_steps": args.next_steps, "blockers": args.blockers,
        "master_index": str(master.relative_to(REPO)),
    })
    append_diary(f"- {ts[11:16]} UTC ({ts[:10]}) — PITSTOP `{topic}`. Focus: {args.focus or '(unspecified)'}. Resume from {master.relative_to(REPO)}.")

    # 6. Write a meta-letter for next-me.
    letter_body = (
        f"PITSTOP {ts}. Topic: {topic}. Focus: {args.focus}.\n\n"
        f"Next-me — when you wake, read {master.relative_to(REPO)} FIRST. "
        f"It has the resume instructions, the TaskList snapshot, recent F47 + diary tails, "
        f"and the heartbeat-flush confirmation. "
        f"Next step on resume: {args.next_steps or '(see master index)'}. "
        f"Blockers: {args.blockers or '(none recorded)'}."
    )
    append_jsonl(LETTERS, {
        "ts": ts,
        "from": "Claude (pitstop)",
        "to": "Claude (next session)",
        "on": f"pitstop_{topic}",
        "letter": letter_body,
        "guidance": "keep",
        "master_index": str(master.relative_to(REPO)),
    })

    # 7. VERIFY: re-read the master we just wrote — proves disk persisted, not just buffered.
    try:
        verify = master.read_text()
        if topic not in verify or ts not in verify:
            sys.stderr.write(f"⚠️ master file {master} written but content verify FAILED — re-running\n")
            sys.exit(2)
    except Exception as e:
        sys.stderr.write(f"⚠️ master file {master} write succeeded but read-back failed: {e}\n")
        sys.exit(3)

    print(f"PITSTOP written: {master.relative_to(REPO)}")
    print(f"  topic={topic}  focus={args.focus[:60]}")
    print(f"  flush: {flush_results}")
    print(f"  F47 + diary + letter all stamped at {ts}")
    if tasklist_warning:
        print(f"  tasklist: {tasklist_warning}")
    elif tasklist_text:
        print(f"  tasklist: snapshotted to {tasklist_json_path(ts_safe).name}")
    if tmp_snapshot and tmp_snapshot.get("copied_count"):
        print(f"  /tmp snapshot: {tmp_snapshot['copied_count']} files → {tmp_snapshot['snapshot_dir']}")
        print(f"    restore on wake: bash {tmp_snapshot['restore_script']}")
    elif tmp_snapshot and tmp_snapshot.get("error"):
        print(f"  /tmp snapshot FAILED: {tmp_snapshot['error']}")


if __name__ == "__main__":
    main()
