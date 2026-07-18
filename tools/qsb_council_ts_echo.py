#!/usr/bin/env python3
"""qsb_council_ts_echo.py — GAP 4 fix.

Poll town-square + push the last N unseen posts to each peer's /message as
kind=town_square_read. This closes the loop so peers see what other CEOs +
Ross have posted, without needing to poll town-square themselves.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TS   = ROOT / "data/registries/qsb_town_square.jsonl"
SEEN = Path("/tmp/qsb_council_ts_echo_seen.txt")
PEERS = {"tp_pip": 9110, "acer_cass": 9000, "wren": 11434}  # wren = local
KEY = "/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.skyscraper_ssh"
CM_DIR = "/tmp/ssh_cm"
SSH_HOSTS = {"tp_pip": "budds@192.168.1.91", "acer_cass": "budds@192.168.1.41"}


def read_seen():
    if SEEN.exists(): return set(SEEN.read_text().strip().splitlines())
    return set()


def write_seen(s):
    SEEN.write_text("\n".join(sorted(s)))


def get_new_posts():
    seen = read_seen()
    posts = []
    with TS.open() as f:
        for line in f:
            try:
                o = json.loads(line)
                key = o.get("ts", "") + "|" + o.get("from", "")
                if key not in seen:
                    posts.append(o); seen.add(key)
            except: pass
    write_seen(seen)
    return posts[-20:]  # cap at 20 per cycle


def push_to_peer(peer_id, posts):
    if not posts: return {"ok": True, "pushed": 0}
    # Compose one message with the batch
    text = "TOWN-SQUARE UPDATE — new posts since last echo:\n"
    for p in posts:
        text += f"  [{p.get('ts','?')[:16]}] {p.get('from','?')}: {p.get('text','')[:200]}\n"
    body = json.dumps({"from": "hq_ts_echo", "text": text}).encode()
    host = SSH_HOSTS.get(peer_id)
    port = PEERS.get(peer_id)
    if not host or not port:
        return {"ok": False, "err": "unknown peer"}
    # scp payload then curl via SSH
    with open("/tmp/ts_echo_body.json", "wb") as f: f.write(body)
    scp = ["scp", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ControlMaster=auto",
           "-o", "ControlPersist=1h", "-o", f"ControlPath={CM_DIR}/%r@%h:%p",
           "/tmp/ts_echo_body.json", f"{host}:C:/Users/budds/ts_echo.json"]
    subprocess.run(scp, capture_output=True, timeout=10)
    ssh_cmd = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-o", "ControlMaster=auto",
               "-o", "ControlPersist=1h", "-o", f"ControlPath={CM_DIR}/%r@%h:%p",
               host,
               f"curl.exe -s -m 30 -X POST -H \"Content-Type: application/json\" "
               f"--data-binary \"@C:\\Users\\budds\\ts_echo.json\" "
               f"http://127.0.0.1:{port}/message"]
    try:
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=40)
        return {"ok": r.returncode == 0, "pushed": len(posts), "resp_head": r.stdout[:150]}
    except Exception as e:
        return {"ok": False, "err": str(e)[:150]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=120)
    args = ap.parse_args()
    while True:
        posts = get_new_posts()
        if posts:
            for peer_id in ("tp_pip", "acer_cass"):
                r = push_to_peer(peer_id, posts)
                print(f"[ts_echo] {peer_id}: {r}")
        if args.once: break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
