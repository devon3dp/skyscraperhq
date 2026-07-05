#!/usr/bin/env python3
"""qsb_whatsapp_send.py — send a WhatsApp message to a phone number via the
Galaxy receptionist phone (com.whatsapp).

Mechanism: open a wa.me intent with the message pre-filled, locate the Send
floating-action-button via uiautomator dump, and tap it. Returns the result
back to the caller as JSON. Audited to data/registries/qsb_whatsapp_sends.jsonl.

  python3 tools/qsb_whatsapp_send.py --to +447481057362 --text "hello"

Hard rules:
  - Phone numbers must be E.164 (+CC...) — no spaces, no leading 0.
  - 1000-char cap per message (WhatsApp limit is higher but keep it sane).
  - Audited even on failure.
  - Returns non-zero exit on any leg failure.
"""

from __future__ import annotations
import argparse, json, re, subprocess, sys, time, urllib.parse
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
AUDIT = ROOT / "data/registries/qsb_whatsapp_sends.jsonl"
DUMP_DEVICE = "/sdcard/window_dump.xml"
DUMP_LOCAL = Path("/tmp/qsb_whatsapp_dump.xml")
WA_PKG = "com.whatsapp"

E164_RE = re.compile(r"^\+\d{8,15}$")


def now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def adb(*args, timeout=10) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          timeout=timeout)


def audit(row: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT, "a") as f:
        f.write(json.dumps(row) + "\n")


def find_send_button_bounds() -> tuple[int, int] | None:
    """uiautomator dump → parse → return (cx, cy) of the Send FAB.

    WhatsApp's send button has resource-id "com.whatsapp:id/send" or
    content-desc="Send" depending on version. Try both.
    """
    r = adb("shell", "uiautomator", "dump", DUMP_DEVICE, timeout=15)
    if r.returncode != 0:
        return None
    p = adb("pull", DUMP_DEVICE, str(DUMP_LOCAL), timeout=10)
    if p.returncode != 0:
        return None
    try:
        xml = DUMP_LOCAL.read_text()
    except Exception:
        return None
    # WhatsApp's actual send-FAB id is `conversation_entry_action_button`
    # (verified by uiautomator dump 2026-06-17 on SM-A156E v2.26.23.74).
    # Try content-desc="Send" first — it's the most stable across versions.
    patterns = [
        r'content-desc="Send"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*content-desc="Send"',
        r'resource-id="com\.whatsapp:id/conversation_entry_action_button"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'resource-id="com\.whatsapp:id/send"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]
    for pat in patterns:
        m = re.search(pat, xml)
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


def send(to: str, text: str, dry_run: bool = False) -> dict:
    t0 = time.time()
    row = {"ts": now_iso(), "to": to, "text_head": text[:120],
           "text_len": len(text), "dry_run": dry_run, "ok": False,
           "stages": []}
    if not E164_RE.match(to):
        row["error"] = f"to not E.164: {to!r}"
        audit(row)
        return row
    if not text or len(text) > 1000:
        row["error"] = f"text len out of range: {len(text)}"
        audit(row)
        return row
    # Ensure device + WhatsApp present
    d = adb("get-state", timeout=5)
    if d.returncode != 0 or "device" not in d.stdout:
        row["error"] = "adb device not present"
        audit(row)
        return row
    pkg_check = adb("shell", "pm", "list", "packages", WA_PKG, timeout=5)
    if WA_PKG not in pkg_check.stdout:
        row["error"] = "com.whatsapp not installed"
        audit(row)
        return row

    if dry_run:
        row["ok"] = True
        row["stages"].append("dry_run")
        row["wall_s"] = round(time.time() - t0, 1)
        audit(row)
        return row

    # Step 1: open wa.me intent with prefilled text
    # Strip leading + for wa.me (it expects raw digits)
    digits = to.lstrip("+")
    url = f"https://wa.me/{digits}?text={urllib.parse.quote(text)}"
    open_r = adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
                 "-d", url, timeout=15)
    if open_r.returncode != 0:
        row["error"] = f"am start failed: {open_r.stderr[-200:]}"
        audit(row)
        return row
    row["stages"].append("intent_opened")
    # Give WhatsApp time to load
    time.sleep(4.5)

    # Step 2: find + tap Send button
    coords = find_send_button_bounds()
    if not coords:
        # Last-resort fallback: on SM-A156E v2.26.23.74 the Send FAB sits
        # at (997, 2123) — verified by uiautomator dump 2026-06-17. Earlier
        # fallback (1010, 1820) tapped dead chat space and silently dropped
        # messages — do not regress to that.
        coords = (997, 2123)
        row["stages"].append("send_button_fallback_coords")
    else:
        row["stages"].append("send_button_located")
    cx, cy = coords
    tap_r = adb("shell", "input", "tap", str(cx), str(cy), timeout=8)
    if tap_r.returncode != 0:
        row["error"] = f"tap failed: {tap_r.stderr[-200:]}"
        audit(row)
        return row
    row["stages"].append(f"send_tapped_{cx}_{cy}")
    time.sleep(1.5)

    # Step 3: return to home so receptionist doesn't get stuck in WhatsApp UI
    adb("shell", "input", "keyevent", "3", timeout=5)
    row["stages"].append("home_pressed")

    row["ok"] = True
    row["wall_s"] = round(time.time() - t0, 1)
    audit(row)
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="E.164 phone, e.g. +447481057362")
    p.add_argument("--text", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    res = send(a.to, a.text, dry_run=a.dry_run)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
