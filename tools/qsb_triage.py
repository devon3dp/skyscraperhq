"""qsb_triage.py — alert triage agent (Gap 2 from DeepSeek).

Trigger: Ross 2026-06-21 — DeepSeek identified the gap, Wren-router + DeepSeek
unanimously picked B (small LLM reads brief + last 30 F47 rows on 5-min
timer, surfaces anomalies). Signed off:
  - wren_router (qwen2.5:32b routed)
  - deepseek_chat
  - claude

What it does each tick:
  1. Read council brief (state grounding)
  2. Read last 30 non-noise F47 rows
  3. Ask qwen3.5:9b (think=false): list top 3 anomalies or "all clear"
  4. Write to data/registries/qsb_triage_alerts.jsonl
  5. F47 stamp triage_tick with signed_off_by

Designed to fit alongside the team_sync timer (30 min) and the f47-snapshot
timer (daily). Triage runs every 5 min via systemd-user.

Run:
    python3 tools/qsb_triage.py            # one tick
    python3 tools/qsb_triage.py --dry-run  # show prompt + tick, don't write
"""
from __future__ import annotations
import argparse, datetime, json, subprocess, sys
from pathlib import Path

REPO = Path("/vaults/nvme0/qsb_tower_v1")
BRIEF = REPO / "data/registries/qsb_council_brief.md"
F47 = REPO / "data/registries/qsb_f47_team_records.jsonl"
ALERTS = REPO / "data/registries/qsb_triage_alerts.jsonl"
CALL = REPO / "tools/qsb_local_agent_call.py"

# Noisy kinds — skip these when picking "last 30" so we look at meaningful work.
NOISE_KINDS = {
    "heartbeat_tick", "auto_sigs_tick", "applier_tick",
    "chat_mirror_tick", "supervisor_tick", "message_board_post",
    "audit_crew_tick", "supervisor_escalation",
}

TRIAGE_MODEL = "qwen3.5:9b"
TICK_LIMIT = 30


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_brief() -> str:
    if not BRIEF.exists():
        return "(brief missing)"
    txt = BRIEF.read_text()
    # Cap to keep prompt small. Most-actionable info is near the end.
    return txt[-3500:]


def read_recent_f47(limit: int = TICK_LIMIT) -> list[dict]:
    if not F47.exists():
        return []
    rows = []
    # Tail efficiently — start from a position 200k back from EOF.
    with F47.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 200_000))
        tail_bytes = f.read().decode("utf-8", errors="ignore")
    for line in tail_bytes.splitlines():
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("kind") in NOISE_KINDS: continue
        rows.append(d)
    return rows[-limit:]


def call_triage(prompt: str, timeout: int = 90) -> dict:
    r = subprocess.run(
        ["python3", str(CALL), "--model", TRIAGE_MODEL,
         "--prompt", prompt, "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 20)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "")[-200:]}
    try:
        return json.loads(r.stdout)
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}"}


def stamp_alert(text: str, signoffs: list[str]) -> None:
    rec = {
        "ts": now_iso(),
        "kind": "triage_alert",
        "operator": TRIAGE_MODEL,
        "summary": text[:500],
        "signed_off_by": signoffs,
    }
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": rec["ts"], "kind": "triage_tick", "role": "claude",
            "subject": "triage_alerts",
            "detail": text[:500],
            "signed_off_by": signoffs,
        }) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    brief = read_brief()
    rows = read_recent_f47()
    if not rows:
        print("[triage] no F47 rows to triage")
        return 0

    rows_text = "\n".join(
        f"{r.get('ts','?')} kind={r.get('kind','?')} subject={r.get('subject','?')} "
        f"detail={(r.get('detail') or r.get('summary') or '?')[:200]}"
        for r in rows
    )
    prompt = (
        "You are tower triage. Below are (a) the current council brief tail "
        "and (b) the last 30 meaningful F47 rows. Identify the TOP 3 "
        "ANOMALIES or risks (failed ops, timeouts, regressions, stale state, "
        "broken claims), each in 1 line. If everything looks normal, say "
        "'ALL CLEAR' and nothing else.\n\n"
        f"=== BRIEF TAIL ===\n{brief}\n\n"
        f"=== LAST {len(rows)} F47 ROWS ===\n{rows_text}\n\n"
        "Reply with up to 3 lines. No preamble."
    )

    if a.dry_run:
        print("[triage] DRY RUN — would dispatch to", TRIAGE_MODEL)
        print(prompt[:800] + "...")
        return 0

    res = call_triage(prompt)
    if not res.get("ok"):
        print(f"[triage] dispatch FAILED: {res.get('error')[:200]}")
        return 1
    reply = (res.get("reply") or "").strip()
    if not reply:
        print("[triage] empty reply — qwen3.5 may have stalled")
        return 0
    if "ALL CLEAR" in reply.upper():
        print(f"[triage] {now_iso()}  ALL CLEAR  (wall {res.get('wall_s')}s)")
        # Still stamp a tick row so we can prove the triage is running.
        stamp_alert("ALL CLEAR", [TRIAGE_MODEL, "claude"])
        return 0
    print(f"[triage] {now_iso()}  alerts:\n{reply}")
    stamp_alert(reply, [TRIAGE_MODEL, "claude"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
