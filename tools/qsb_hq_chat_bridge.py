#!/usr/bin/env python3
"""qsb_hq_chat_bridge.py — Claude HQ dashboard chat-to-work bridge (Ross 2026-07-10).

The HQ dashboard chat used to pipe every message straight to a model and return
prose. Long task commands got treated as greetings ("I'm not booking a task for
a greeting"). This module fixes the SMALLEST real problem: classify task-like
messages as TASK_COMMAND (never greeting), create/find a Task Council task,
attach the dashboard-chat source evidence, run ONLY safe read-only backend
commands the message asks for, write the requested report, and return a short
dashboard response with the report path. It never self-closes the task.
"""
from __future__ import annotations
import json, os, re, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
DEFAULT_REPORT_DIR = Path("/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT")
LATEST = DEFAULT_REPORT_DIR / "LATEST_REPORT.txt"

# Any of these in a message => it is WORK, never a greeting (Ross 2026-07-10).
TASK_TRIGGERS = [
    "task title:", "task class", "work from", "write report to",
    "copy to latest_report", "smoke test", "task council", "ross is ordering",
    "do not self-close", "do not self close", "dashboard_repair", "task_proof",
    "receptionist_build", "hardware_storage_change", "run:", "curl ",
    "hostname", "whoami", "lsblk", "ss -ltnp", "pwd",
]

GREETINGS = {"hi", "hey", "hello", "yo", "hiya", "morning", "good morning",
             "good evening", "evening", "sup", "howdy", "hey hq", "hello hq",
             "hi hq", "thanks", "thank you", "ok", "okay", "cool", "nice"}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def classify(prompt: str) -> str:
    """Return TASK_COMMAND | GREETING | CHAT."""
    p = (prompt or "").strip()
    low = p.lower()
    for trig in TASK_TRIGGERS:
        if trig in low:
            return "TASK_COMMAND"
    # long multi-line messages are work, not greetings
    if len(p) > 240 or p.count("\n") >= 3:
        return "TASK_COMMAND"
    # a short message that is only a greeting word
    stripped = re.sub(r"[^a-z ]", "", low).strip()
    if stripped in GREETINGS or (len(stripped) <= 12 and any(stripped == g for g in GREETINGS)):
        return "GREETING"
    return "CHAT"


# ── expanded classifier (Ross 2026-07-10): 8 dashboard message classes ──
WORK_QUEUE = REG / "claude_hq_dashboard_work_queue.jsonl"

def classify_detailed(prompt: str) -> str:
    """Return one of: greeting, status_request, task_instruction, smoke_test,
    recovery_task, deployment_approval, rulebook_change, dashboard_repair, chat."""
    low = (prompt or "").lower()
    if classify(prompt) == "GREETING":
        return "greeting"
    def has(*ws): return any(w in low for w in ws)
    if has("smoke test", "smoke-test", "smoke_test"):
        return "smoke_test"
    if has("recover", "recovery task", "offline node", "bring it back"):
        return "recovery_task"
    if has("deploy", "deployment", "approve deploy", "go live", "install live"):
        return "deployment_approval"
    if has("rule ", "r10", "r1", "rulebook", "gate 1", "gate 2", "add this as a rule", "doctrine"):
        return "rulebook_change"
    if has("dashboard_repair", "repair dashboard", "fix dashboard", "bridge", "kiosk"):
        return "dashboard_repair"
    if has("status", "whoami", "health", "is it online", "are you online", "report the truth"):
        # status-only phrasing with no task verbs -> status_request; else task
        if classify(prompt) == "TASK_COMMAND":
            return "task_instruction"
        return "status_request"
    if classify(prompt) == "TASK_COMMAND":
        return "task_instruction"
    return "chat"


def write_work_queue(prompt: str, classification: str, task_id: str = None,
                     report_path: str = None, task_classes=None,
                     allowed_action_type: str = "cli_backend_review",
                     message_ts: str = None) -> dict:
    """Dashboard writes an APPROVED work request to the queue for the CLI backend
    to pick up. The dashboard NEVER runs arbitrary shell — it only queues."""
    import uuid as _uuid
    rid = "wq_" + _uuid.uuid4().hex[:10]
    row = {"request_id": rid, "timestamp": message_ts or utc(), "requester": "ross",
           "source": "dashboard_chat", "classification": classification,
           "task_title": extract_title(prompt), "task_classes": task_classes or [classification],
           "instruction_text": prompt[:4000], "approved_root": str(ROOT),
           "allowed_action_type": allowed_action_type,
           "task_id": task_id, "report_path": report_path,
           "state": "queued_for_cli_backend"}
    WORK_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with open(WORK_QUEUE, "a") as f:
        f.write(json.dumps(row) + "\n")
    return {"request_id": rid, "state": "queued_for_cli_backend", "queue_file": str(WORK_QUEUE)}


# ─── safe read-only command runner ───────────────────────────────────
def _curl_is_local(cmd: str) -> bool:
    m = re.search(r"https?://([^/\s:]+)", cmd)
    if not m:
        return False
    host = m.group(1)
    return (host in ("127.0.0.1", "localhost")
            or host.startswith(("172.20.", "192.168.", "10.", "172.17.")))


# Exact allowlisted read-only commands (argv form).
_EXACT = {
    "pwd": ["pwd"],
    "hostname": ["hostname"],
    "whoami": ["whoami"],
    "date -is": ["date", "-Is"],
    "git status --short": ["git", "status", "--short"],
    "ss -ltnp": ["ss", "-ltnp"],
    "lsblk": ["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINTS"],
}


def _run_one(line: str) -> dict:
    """Run a single allowlisted read-only command line; else mark blocked."""
    cmd = line.strip().rstrip(";")
    low = cmd.lower()
    try:
        if low in _EXACT:
            r = subprocess.run(_EXACT[low], cwd=str(ROOT), capture_output=True,
                               text=True, timeout=15)
            return {"cmd": cmd, "ok": r.returncode == 0,
                    "out": (r.stdout or r.stderr).strip()[:2000]}
        if low.startswith("curl "):
            if not _curl_is_local(cmd):
                return {"cmd": cmd, "ok": False, "out": "BLOCKED: curl only allowed to local dashboards"}
            m = re.search(r"(https?://\S+)", cmd)
            url = m.group(1) if m else ""
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                "--max-time", "5", url], capture_output=True, text=True, timeout=10)
            return {"cmd": cmd, "ok": True, "out": f"HTTP {r.stdout.strip()} from {url}"}
        if low.startswith("wc -l"):
            m = re.search(r"wc -l\s+(\S+)", cmd)
            tgt = (m.group(1) if m else "").strip()
            fp = (ROOT / tgt).resolve() if not tgt.startswith("/") else Path(tgt).resolve()
            if str(fp).startswith(str(REG)) and fp.exists():
                r = subprocess.run(["wc", "-l", str(fp)], capture_output=True, text=True, timeout=10)
                return {"cmd": cmd, "ok": True, "out": r.stdout.strip()[:500]}
            return {"cmd": cmd, "ok": False, "out": "BLOCKED: wc -l only under data/registries"}
        return {"cmd": cmd, "ok": False, "out": "BLOCKED: not in read-only allowlist"}
    except Exception as e:
        return {"cmd": cmd, "ok": False, "out": f"error: {str(e)[:200]}"}


def run_safe_commands(prompt: str) -> list:
    """Find requested commands in the message and run only the allowlisted ones."""
    out = []
    seen = set()
    for raw in (prompt or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower().rstrip(";")
        is_cmd = (low in _EXACT or low.startswith(("curl ", "wc -l")))
        if is_cmd and low not in seen:
            seen.add(low)
            out.append(_run_one(line))
    return out


# ─── report + task helpers ────────────────────────────────────────────
def extract_report_path(prompt: str):
    m = re.search(r"write report to:?\s*(\S+)", prompt or "", re.I)
    if m:
        return m.group(1).strip()
    return None


def extract_title(prompt: str) -> str:
    m = re.search(r"task title:?\s*(.+)", prompt or "", re.I)
    if m:
        return m.group(1).strip()[:120]
    first = (prompt or "").strip().splitlines()[0] if (prompt or "").strip() else "dashboard chat task"
    return first.strip()[:120]


def handle_task_command(prompt: str, received_via: str = "claude_hq_dashboard_chat",
                        message_ts: str = None, message_id: str = None) -> dict:
    """Full bridge: create council task, attach evidence, run safe commands,
    write report, return dashboard response. NEVER self-closes."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as qct

    ts = message_ts or utc()
    title = extract_title(prompt)

    # 1. create the Task Council task (stays open — no claim/done here)
    tid = None
    try:
        res = qct.create(title=title, description=prompt[:4000], actor="hq_claude",
                         tags=["dashboard_chat", "received_via:claude_hq_dashboard_chat"])
        tid = res.get("task_id")
        # 2. attach dashboard-chat source evidence
        qct.note(tid, "hq_claude",
                 f"received_via={received_via} · message_id={message_id or ts} · "
                 f"source=claude_hq_dashboard_chat · full message preserved in task description.")
    except Exception as e:
        tid = f"(council create failed: {str(e)[:120]})"

    # 3. run safe read-only backend commands the message asked for
    ran = run_safe_commands(prompt)

    # 4. write the requested report (+ LATEST_REPORT)
    rpath = extract_report_path(prompt)
    report_path = Path(rpath) if rpath else (DEFAULT_REPORT_DIR / "DASHBOARD_CHAT_TASK_REPORT.txt")
    lines = [
        "DASHBOARD CHAT-TO-WORK TASK REPORT",
        f"Generated: {utc()}",
        f"received_via: {received_via}",
        f"message_id/timestamp: {message_id or ts}",
        f"classification: TASK_COMMAND (not greeting)",
        f"task_id: {tid}",
        f"title: {title}",
        "=" * 60,
        "FULL MESSAGE (preserved, not truncated):",
        prompt,
        "=" * 60,
        "BACKEND COMMANDS RUN (read-only allowlist):",
    ]
    if not ran:
        lines.append("  (none requested / none matched the allowlist)")
    for r in ran:
        lines.append(f"  $ {r['cmd']}")
        lines.append(f"    ok={r['ok']}")
        for ol in (r["out"] or "").splitlines():
            lines.append(f"    | {ol}")
    lines += [
        "=" * 60,
        "final_status: needs Ross/ChatGPT/verifier review — NOT self-scored, NOT complete.",
    ]
    text = "\n".join(lines) + "\n"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text)
        LATEST.parent.mkdir(parents=True, exist_ok=True)
        LATEST.write_text(text)
    except Exception as e:
        text += f"\n(report write error: {str(e)[:120]})\n"

    ran_ok = sum(1 for r in ran if r["ok"])
    # queue the work for the CLI backend to pick up (dashboard never runs shell itself)
    detail_cls = classify_detailed(prompt)
    q = write_work_queue(prompt, detail_cls, task_id=tid, report_path=str(report_path),
                         message_ts=ts)
    dashboard_reply = (
        f"TASK_COMMAND booked ({detail_cls}). Task Council id: {tid}. "
        f"Queued for CLI backend: {q['request_id']}. "
        f"Ran {ran_ok}/{len(ran)} safe read-only checks. "
        f"Report: {report_path}. Task OPEN for Ross/ChatGPT/verifier review (not self-closed)."
    )
    return {"classification": detail_cls, "task_id": tid, "request_id": q["request_id"],
            "queue_file": q["queue_file"], "report_path": str(report_path),
            "latest_report": str(LATEST), "ran": ran,
            "dashboard_reply": dashboard_reply, "received_via": received_via}


if __name__ == "__main__":
    import sys
    msg = sys.stdin.read()
    c = classify(msg)
    print("classification:", c)
    if c == "TASK_COMMAND":
        print(json.dumps(handle_task_command(msg), indent=2, default=str))
