#!/usr/bin/env python3
"""
qsb_ceo_workers.py — use TP-Pip and Asa (Acer-Cass) as real workers on the live Underground.

2026-07-28, Ross: "use tp and acer as workers as well". Both run their own cockpit (llama3.2)
on their own Windows box, reachable at :9120. This routes a REAL rotating work item straight
to each live cockpit, waits for the REAL reply, and ONLY THEN logs council events so the map
draws their work trains (wren<->tp_pip / council15<->tp_pip / tp_pip->task_council, same for
acer_cass). If a cockpit doesn't answer, NOTHING is logged (no fabricated train — R01 honesty).

Cockpit addresses are read LIVE from presence.json (reachable_addr) so a DHCP re-lease can't
strand them; falls back to the last-known IPs.

systemd: qsb-ceo-workers.timer (every 2 min). Run once: python3 tools/qsb_ceo_workers.py
"""
import json, time, uuid, urllib.request, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    import qsb_knowledge as KB          # the tower's learning layer
except Exception:
    KB = None
REG = ROOT / "data" / "registries"
PRESENCE = REG / "leadership_comms" / "presence.json"
BOARD = REG / "qsb_council_tasks.jsonl"

# CEO -> (relay identity in presence, station id on the map, fallback cockpit ip, display)
CEOS = [
    ("tp",  "tp_pip",     "192.168.1.91", "TP-Pip"),
    ("asa", "acer_cass",  "192.168.1.41", "Asa"),
]

WORK = [
    "In ONE sentence, name one operational risk in the autonomous trading fleet right now.",
    "In ONE sentence, one concrete way the council could complete tasks faster.",
    "In ONE sentence, one thing worth checking on the tower tonight.",
    "In ONE line, one signal that a background worker has silently died.",
]


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cockpit_ip(pres_key, fallback):
    try:
        p = json.loads(PRESENCE.read_text())
        return (p.get(pres_key, {}) or {}).get("reachable_addr") or fallback
    except Exception:
        return fallback


def _ask(ip, prompt, t=40):
    req = urllib.request.Request(f"http://{ip}:9120/api/chat",
                                 data=json.dumps({"prompt": prompt}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=t) as r:
        d = json.loads(r.read() or b"{}")
    return (d.get("reply") or d.get("response") or "").strip()


def _journal(rows):
    with open(BOARD, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _kind_for(work):
    w = work.lower()
    if "risk" in w:
        return "risk"
    if "died" in w or "silently" in w:
        return "insight"
    return "note"


def main():
    work = WORK[int(time.time() // 120) % len(WORK)]
    # RECALL (reward-loop closure 2026-07-29): surface prior learnings so the CEO builds
    # on them — but ordered by SOURCE REPUTATION (real council outcomes + KB on-topic/
    # reaffirm) so the higher-trust prior leads. Falls back to flat recall if the
    # reputation module isn't importable — never breaks the live path.
    recall = ""
    if KB:
        try:
            import qsb_worker_reputation as REP
            recall = REP.recall_context_reweighted(work, k=3)
        except Exception:
            recall = KB.recall_context(work, k=3)
    prompt = f"{recall}\n\n{work}" if recall else work
    for pres_key, station, fallback, disp in CEOS:
        ip = _cockpit_ip(pres_key, fallback)
        try:
            reply = _ask(ip, prompt)
        except Exception as e:
            print(f"[ceo-worker] {disp} @ {ip} unreachable ({e}) — NOTHING logged (no fake train).")
            continue
        # a real reply, but reject the bridge's own error sentinel so we never draw a fake train
        if not reply or reply.lower().startswith(("(cockpit", "local generation failed")) \
           or "unreachable" in reply.lower():
            print(f"[ceo-worker] {disp} gave no real answer — NOTHING logged.")
            continue
        tid = "CEOWORK_" + uuid.uuid4().hex[:8]
        ts = _utc()
        _journal([
            {"ts": ts, "event": "tool_selected", "actor": "wren", "task_id": tid,
             "text": f"owner uses {disp} (llama3.2 cockpit worker) for: {work[:50]}"},
            {"ts": ts, "event": "noted", "actor": station, "task_id": tid,
             "text": f"{disp} worker result: {reply[:120]}"},
        ])
        # LEARN: record the real answer as a knowledge entry (deduped, honest source).
        if KB:
            row = KB.add(reply, source=station, kind=_kind_for(work))
            if row:
                print(f"[ceo-worker] {disp} -> NEW learning {row['id']} [{row['topic']}]")
            else:
                print(f"[ceo-worker] {disp} -> learning was junk/dup (not stored / seen bumped)")
        print(f"[ceo-worker] {disp} @ {ip} answered: {reply[:70]!r} -> logged trains ({tid})")


if __name__ == "__main__":
    main()
