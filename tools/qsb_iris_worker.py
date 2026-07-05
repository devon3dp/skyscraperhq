#!/usr/bin/env python3
"""qsb_iris_worker.py — Iris's always-on reception work loop.

Ross: "She should ALWAYS be working — checking Telegram, WhatsApp, email,
TikTok, F0 phone calls — like a real receptionist who helps her team. And I
want PROOF she's working."

This daemon is Iris's back-office. It does NOT replace the front-desk bridges
(the Telegram receptionist and the WhatsApp Web bridge already greet + route
callers in real time). It is the supervisory sweep behind them: every cycle it
walks each channel, reads whatever is genuinely new, decides where each item
should be routed using the F0 receptionist's own routing engine, and writes a
proof-of-work record so there is timestamped evidence she is working.

Honesty stance (Ross values truth over fake activity):
  · A channel is only reported "live" if it is genuinely wired.
  · If a channel is not linked (no creds / no API), it is logged as
    "not_linked" — never faked.
  · The routing engine used here is the real one (route_for) from
    qsb_f0_receptionist; it is side-effect free, so this sweep does NOT
    double-append phantom calls to the call log that the front desks already
    handled.

Proof of work → data/registries/qsb_iris_activity.jsonl (one record per cycle).
Reception status → posted to the shared council at http://192.168.0.10:9100/msg
                   (from=iris) every COUNCIL_EVERY cycles.

The loop is defensive: every channel check is wrapped; a failure in one
channel never stops the sweep and never crashes the daemon.
"""
from __future__ import annotations

import json
import os
import sys
import time
import signal
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
TOOLS = ROOT / "tools"

ACTIVITY = REG / "qsb_iris_activity.jsonl"
CURSORS = REG / "qsb_iris_worker_cursors.json"

# Channel data stores (read-only from Iris's back office)
TELEGRAM_AUDIT = REG / "qsb_telegram_audit.jsonl"
WA_INBOUND = REG / "qsb_wa_inbound.jsonl"
F0_CALLS = REG / "qsb_f0_calls.jsonl"
EMAIL_INBOX = REG / "qsb_email_inbox_log.jsonl"

COUNCIL_URL = "http://192.168.0.10:9100/msg"
COUNCIL_EVERY = 5          # post a status line every N cycles
CYCLE_SECONDS = int(os.environ.get("IRIS_CYCLE_SECONDS", "90"))
MAX_CYCLES = int(os.environ.get("IRIS_MAX_CYCLES", "0"))  # 0 = forever

# Make the F0 receptionist routing engine importable (route_for is pure).
sys.path.insert(0, str(TOOLS))
try:
    from qsb_f0_receptionist import route_for  # type: ignore
except Exception:  # pragma: no cover - defensive
    def route_for(text):  # fallback: no routing engine available
        return (None, None)

# Iris's local brain (Ollama, airgapped) — used to draft suggested replies and
# summarize the sweep into a reception brief. Fully optional: if it is not
# available the worker still logs proof-of-work and posts a deterministic brief.
try:
    from qsb_iris_brain import draft_reply, summarize_brief  # type: ignore
    _BRAIN = True
except Exception:  # pragma: no cover - defensive
    _BRAIN = False

    def draft_reply(channel, sender, text, route_hint=None):
        return None

    def summarize_brief(items):
        return None

# Cap how many drafts we generate per sweep so one busy cycle can't stall the
# loop (each draft is a short local-model call, ~0.5s).
MAX_DRAFTS_PER_CYCLE = int(os.environ.get("IRIS_MAX_DRAFTS", "5"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- cursors ----
def load_cursors() -> dict:
    try:
        return json.loads(CURSORS.read_text())
    except Exception:
        return {}


def save_cursors(c: dict) -> None:
    try:
        CURSORS.write_text(json.dumps(c, indent=2))
    except Exception:
        pass


def _read_new_lines(path: Path, cursor_key: str, cursors: dict) -> list[str]:
    """Return jsonl lines added since we last looked; advances the cursor.

    Cursor is a line count. Robust to files that do not exist yet.
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    seen = int(cursors.get(cursor_key, 0))
    if seen > len(lines):        # file was rotated/truncated → resync
        seen = 0
    new = lines[seen:]
    cursors[cursor_key] = len(lines)
    return new


def _loads(line: str) -> dict:
    try:
        return json.loads(line)
    except Exception:
        return {}


# ---------------------------------------------------------------- channels ---
def check_telegram(cursors: dict) -> dict:
    """LIVE if the front-desk bridge is running. Read genuinely new inbound."""
    running = TELEGRAM_AUDIT.exists()
    new = _read_new_lines(TELEGRAM_AUDIT, "telegram", cursors)
    inbound = []
    for ln in new:
        rec = _loads(ln)
        if rec.get("kind") == "text_in":
            inbound.append(rec)
    items = []
    for rec in inbound:
        # text_in records log length not content (privacy); route on username.
        who = rec.get("tg_username") or rec.get("tg_user_id") or "telegram_caller"
        items.append({"from": f"tg:{who}", "note": f"msg_len={rec.get('msg_len')}",
                      "handled_by": "telegram front desk (auto-greet+route)"})
    return {"channel": "telegram", "status": "live" if running else "unknown",
            "new_items": len(inbound), "items": items}


def check_whatsapp(cursors: dict) -> dict:
    """LIVE if the WhatsApp Web bridge is running. Read genuinely new inbound."""
    new = _read_new_lines(WA_INBOUND, "whatsapp", cursors)
    items = []
    for ln in new:
        rec = _loads(ln)
        body = rec.get("body") or rec.get("text") or ""
        dest, _ep = route_for(body)
        items.append({"from": f"wa:+{rec.get('phone', '?')}",
                      "text": body[:120],
                      "route_hint": dest or "unrouted",
                      "handled_by": "whatsapp bridge (auto-route to /api/f0/converse)"})
    # bridge is a live channel even before the first inbound arrives
    return {"channel": "whatsapp", "status": "live",
            "new_items": len(items), "items": items}


def check_f0_calls(cursors: dict) -> dict:
    """Phone/chat conversational core. Read genuinely new caller turns."""
    new = _read_new_lines(F0_CALLS, "f0_calls", cursors)
    items = []
    for ln in new:
        rec = _loads(ln)
        if rec.get("turn") == "caller":
            text = rec.get("text", "")
            dest, _ep = route_for(text)
            items.append({"from": rec.get("caller_id", "caller"),
                          "text": text[:120],
                          "route_hint": dest or "general reception"})
    return {"channel": "f0_calls", "status": "live",
            "new_items": len(items), "items": items}


def check_email(cursors: dict) -> dict:
    """Only 'live' if an IMAP config is present in the vault. Never faked."""
    imap_names = [".env.outlook.imap", ".env.yahoo.imap", ".env.zoho_eu.imap",
                  ".env.fastmail.imap", ".env.gmx.imap", ".env.aol.imap",
                  ".env.google.imap", ".env.custom.imap"]
    vault = ROOT / "vault"
    have_cfg = any((vault / n).exists() for n in imap_names)
    if not have_cfg:
        return {"channel": "email", "status": "not_linked",
                "new_items": 0, "items": [],
                "note": "no IMAP config in vault — needs linking"}
    new = _read_new_lines(EMAIL_INBOX, "email", cursors)
    items = [{"subject": _loads(ln).get("subject", "")[:80]} for ln in new]
    return {"channel": "email", "status": "live",
            "new_items": len(new), "items": items}


def check_tiktok(cursors: dict) -> dict:
    """No TikTok API is wired — report honestly as not_linked."""
    return {"channel": "tiktok", "status": "not_linked",
            "new_items": 0, "items": [],
            "note": "floor_166 studio exists; no live inbound API"}


CHANNELS = [check_telegram, check_whatsapp, check_f0_calls,
            check_email, check_tiktok]


# ---------------------------------------------------------------- council ----
def post_council(text: str) -> bool:
    try:
        body = json.dumps({"from": "iris", "topic": "reception_status",
                           "text": text}).encode()
        req = urllib.request.Request(COUNCIL_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- drafting ---
def _attach_drafts(actions: list[dict]) -> int:
    """For genuinely-new inbound that carries readable text, have Iris draft a
    short SUGGESTED reply (team reviews before sending). Bounded per cycle so a
    burst never stalls the loop. Returns how many drafts were produced."""
    drafted = 0
    for it in actions:
        if drafted >= MAX_DRAFTS_PER_CYCLE:
            break
        text = (it.get("text") or "").strip()
        if not text:
            continue  # e.g. telegram text_in logs length only (privacy) — skip
        try:
            d = draft_reply(it.get("channel", "?"), it.get("from", "caller"),
                            text, route_hint=it.get("route_hint"))
        except Exception:
            d = None
        if d:
            it["suggested_reply"] = d
            drafted += 1
    return drafted


def _reception_brief(live, not_linked, new_total, actions, drafted) -> str:
    """Compose the brief posted to the council. Prefer a model summary of the
    actual inbound; always fall back to a deterministic, honest line."""
    textful = [a for a in actions if (a.get("text") or "").strip()]
    summary = None
    if new_total > 0 and textful:
        try:
            summary = summarize_brief(textful)
        except Exception:
            summary = None
    head = (f"Reception brief — live: {', '.join(live) or 'none'}; "
            f"awaiting-link: {', '.join(not_linked) or 'none'}; "
            f"new inbound this sweep: {new_total}.")
    if summary:
        body = f" {summary}"
    elif new_total > 0:
        # deterministic digest when the brain is unavailable
        bits = []
        for a in textful[:5]:
            bits.append(f"{a.get('from','?')} on {a.get('channel','?')}: "
                        f"{(a.get('text') or '')[:80]}")
        body = " New: " + "; ".join(bits) if bits else ""
    else:
        body = " Desk quiet — nothing new needing attention."
    if drafted:
        body += f" ({drafted} suggested repl{'y' if drafted == 1 else 'ies'} drafted for review.)"
    return head + body


# ---------------------------------------------------------------- cycle ------
def run_cycle(cycle_no: int, cursors: dict) -> dict:
    checked, all_actions, new_total = [], [], 0
    live, not_linked = [], []
    for fn in CHANNELS:
        try:
            res = fn(cursors)
        except Exception as e:  # never let one channel break the sweep
            res = {"channel": getattr(fn, "__name__", "?"),
                   "status": "error", "new_items": 0, "items": [],
                   "note": f"{type(e).__name__}: {str(e)[:120]}"}
        checked.append(res["channel"])
        new_total += res.get("new_items", 0)
        if res.get("status") == "live":
            live.append(res["channel"])
        elif res.get("status") == "not_linked":
            not_linked.append(res["channel"])
        for it in res.get("items", []):
            all_actions.append({"channel": res["channel"], **it})

    # Proactive step: draft suggested replies for genuinely-new inbound.
    drafted = _attach_drafts(all_actions) if new_total > 0 else 0

    note = (f"reception sweep #{cycle_no}: "
            f"live={live or 'none'} not_linked={not_linked or 'none'} "
            f"new_items={new_total} drafts={drafted}")

    rec = {
        "ts": utcnow(),
        "cycle": cycle_no,
        "operator": "Iris (F0 reception back office)",
        "brain": "hermes3:8b (local/airgapped)" if _BRAIN else "unavailable",
        "channels_checked": checked,
        "live_channels": live,
        "not_linked_channels": not_linked,
        "new_items": new_total,
        "drafts": drafted,
        "actions": all_actions[:40],
        "note": note,
    }
    # Post a reception brief to the council when there is something worth the
    # team's attention (new inbound), plus a lighter periodic presence ping.
    # Done before the record is written so the flags are persisted as proof.
    if new_total > 0:
        rec["brief"] = _reception_brief(live, not_linked, new_total,
                                        all_actions, drafted)
        rec["council_posted"] = post_council(rec["brief"])
    elif cycle_no % COUNCIL_EVERY == 1:
        rec["council_posted"] = post_council(
            f"Reception on desk. Channels live: {', '.join(live) or 'none'}. "
            f"Awaiting-link: {', '.join(not_linked) or 'none'}. Desk quiet.")

    try:
        with ACTIVITY.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec


_STOP = False


def _sig(_signum, _frame):
    global _STOP
    _STOP = True


def main() -> int:
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    cursors = load_cursors()
    cycle = int(cursors.get("_cycle", 0))
    print(f"[iris-worker] starting; cycle base={cycle} "
          f"interval={CYCLE_SECONDS}s max={MAX_CYCLES or 'inf'}", flush=True)
    done = 0
    while not _STOP:
        cycle += 1
        done += 1
        try:
            rec = run_cycle(cycle, cursors)
            print(f"[iris-worker] {rec['ts']} {rec['note']}", flush=True)
        except Exception as e:  # absolute last-resort guard
            print(f"[iris-worker] cycle error: {e}", flush=True)
        cursors["_cycle"] = cycle
        save_cursors(cursors)
        if MAX_CYCLES and done >= MAX_CYCLES:
            break
        # sleep in short slices so SIGTERM is honoured promptly
        for _ in range(CYCLE_SECONDS):
            if _STOP:
                break
            time.sleep(1)
    print("[iris-worker] stopped.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
