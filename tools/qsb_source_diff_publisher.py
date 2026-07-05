#!/usr/bin/env python3
"""qsb_source_diff_publisher.py — federated agent source sync.

Ross 2026-07-02: "all our agents need to work as a team from any of the pcs" +
"this way you all see the code thats new and been written like the agents keep
the updates organised in there own ways it works if you get me ?"

WATCHES tools/*.py for mtime changes.
On change:
  1. Appends a diff row to data/registries/qsb_tower_source_diff.jsonl
     shape: {ts, path, sha_before, sha_after, size_before, size_after, node}
  2. POSTs the new file bytes to every known peer's /file endpoint
     so their copy comes up to date.

Any agent (Sage, Forge, Wren, TP-Claude, iQuest) can tail the diff file
and organise the updates their own way — Sage adds new heuristics to its
knowledge, Wren updates her tool awareness, TP-Claude reads it into his
Watcher, etc. See docs at data/registries/qsb_agent_sync_protocol.md.

Run:
  python3 tools/qsb_source_diff_publisher.py           # daemon (30s tick)
  python3 tools/qsb_source_diff_publisher.py --once    # one snapshot pass
  python3 tools/qsb_source_diff_publisher.py --scan-only  # detect+log only (no push)

Real-money gates unchanged. Federation moves code, not orders.
"""
from __future__ import annotations
import argparse, hashlib, json, os, socket, sys, time
import urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TOOLS = ROOT / "tools"
DIFF_FILE = ROOT / "data/registries/qsb_tower_source_diff.jsonl"
STATE = ROOT / "data/registries/qsb_source_diff_state.json"

PEERS = [
    {"id": "thinkpad", "url": "http://192.168.0.10:9100"},
    # Acer added dynamically when node listener is up
]

WATCH_GLOBS = [
    "qsb_wren_sage.py",
    "qsb_wren_team.py",
    "qsb_wren_local_agent.py",
    "qsb_hq_claude_dash.py",
    "qsb_wren_dash.py",
    "qsb_boardroom_hub.py",
    "qsb_hermes_local_agent.py",
    "qsb_provider_agent.py",
    "qsb_consult_external.py",
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha_head(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:
        return ""


def load_state() -> dict:
    if not STATE.exists():
        return {"files": {}}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"files": {}}


def save_state(st: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2))


def append_diff(row: dict):
    DIFF_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DIFF_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def push_to_peer(peer: dict, rel: str, data: bytes) -> dict:
    url = f"{peer['url']}/file?name={rel}"
    try:
        req = urllib.request.Request(url, data=data, method="POST",
            headers={"Content-Type": "application/octet-stream"})
        r = urllib.request.urlopen(req, timeout=10)
        return {"peer": peer["id"], "ok": True, "resp": json.loads(r.read().decode())}
    except Exception as e:
        return {"peer": peer["id"], "ok": False, "error": str(e)[:200]}


def scan_and_publish(state: dict, *, push: bool = True) -> list:
    changes = []
    for name in WATCH_GLOBS:
        p = TOOLS / name
        if not p.exists():
            continue
        try:
            mtime = int(p.stat().st_mtime)
            size = p.stat().st_size
            cur_sha = sha_head(p)
        except Exception:
            continue
        prev = state["files"].get(name, {})
        prev_sha = prev.get("sha", "")
        prev_size = prev.get("size", 0)
        prev_mtime = prev.get("mtime", 0)
        if cur_sha != prev_sha and cur_sha:
            # A real change
            row = {
                "ts": utc_iso(),
                "node": socket.gethostname(),
                "path": f"tools/{name}",
                "sha_before": prev_sha,
                "sha_after": cur_sha,
                "size_before": prev_size,
                "size_after": size,
                "mtime": mtime,
                "author": os.environ.get("USER", "?"),
            }
            append_diff(row)
            change = {"file": name, "row": row, "pushes": []}
            if push:
                data = p.read_bytes()
                for peer in PEERS:
                    change["pushes"].append(push_to_peer(peer, f"tools/{name}", data))
            changes.append(change)
            state["files"][name] = {"sha": cur_sha, "size": size, "mtime": mtime,
                                     "last_pushed_at": utc_iso()}
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one scan pass then exit")
    ap.add_argument("--scan-only", action="store_true", help="detect + log, don't push")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--baseline", action="store_true", help="snapshot current state without emitting diff rows")
    a = ap.parse_args()

    state = load_state()

    if a.baseline:
        for name in WATCH_GLOBS:
            p = TOOLS / name
            if p.exists():
                state["files"][name] = {
                    "sha": sha_head(p),
                    "size": p.stat().st_size,
                    "mtime": int(p.stat().st_mtime),
                    "baseline_at": utc_iso(),
                }
        save_state(state)
        print(f"baseline written: {len(state['files'])} files at state {STATE}")
        return

    if a.once:
        changes = scan_and_publish(state, push=not a.scan_only)
        save_state(state)
        print(json.dumps({"ts": utc_iso(), "changes": len(changes), "detail": changes}, indent=2))
        return

    print(f"source_diff_publisher on {socket.gethostname()} — interval {a.interval}s — {len(WATCH_GLOBS)} files watched — {len(PEERS)} peer(s)")
    while True:
        try:
            changes = scan_and_publish(state, push=not a.scan_only)
            if changes:
                save_state(state)
                for c in changes:
                    print(f"[{utc_iso()}] {c['file']} sha {c['row']['sha_before']}→{c['row']['sha_after']}  pushes: {[(p['peer'], p['ok']) for p in c['pushes']]}")
            time.sleep(a.interval)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[{utc_iso()}] error: {e}", file=sys.stderr)
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
