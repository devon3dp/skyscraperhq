#!/usr/bin/env python3
"""qsb_council_card_sync.py — GAP 6 fix.

Push operator cards to peer boxes via SSH ControlMaster. Peers get their own
card on their own machine so they can read it locally without hitting HQ.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CARDS = {
    "hq_claude": ROOT / "data/registries/qsb_hq_claude_operator_card.json",
    "wren":      ROOT / "data/registries/qsb_wren_operator_card.json",
    "tp_pip":    ROOT / "data/registries/qsb_tp_pip_operator_card.json",
    "acer_cass": ROOT / "data/registries/qsb_acer_cass_operator_card.json",
}
PEERS = {
    "tp_pip":    {"user": "budds", "host": "192.168.1.74", "remote_dir": "C:/Users/budds/qsb/"},
    "acer_cass": {"user": "budds", "host": "192.168.1.41", "remote_dir": "C:/Users/budds/qsb/"},
}
KEY = "/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.skyscraper_ssh"
CM_DIR = "/tmp/ssh_cm"


def scp_to_peer(peer_id, src, remote_name):
    p = PEERS.get(peer_id)
    if not p: return {"ok": False, "err": f"unknown peer {peer_id}"}
    dst = f"{p['user']}@{p['host']}:{p['remote_dir']}{remote_name}"
    cmd = ["scp", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ControlMaster=auto",
           "-o", "ControlPersist=1h", "-o", f"ControlPath={CM_DIR}/%r@%h:%p",
           str(src), dst]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return {"ok": r.returncode == 0, "err": r.stderr[:200] if r.returncode else None}
    except Exception as e:
        return {"ok": False, "err": str(e)[:200]}


def sync_all():
    results = {}
    # Each peer gets their OWN card + the peer roster (all 4 cards for context)
    for peer_id, cfg in PEERS.items():
        r = {"own": None, "roster": []}
        # own card
        own = CARDS.get(peer_id)
        if own and own.exists():
            r["own"] = scp_to_peer(peer_id, own, f"my_operator_card.json")
        # roster (all 4 cards, so peer can look up others)
        for ceo, card in CARDS.items():
            if card.exists():
                res = scp_to_peer(peer_id, card, f"peer_card_{ceo}.json")
                r["roster"].append({"ceo": ceo, **res})
        results[peer_id] = r
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=300, help="poll interval s")
    args = ap.parse_args()
    if args.once:
        print(json.dumps(sync_all(), indent=2))
        return
    print(f"[card_sync] polling every {args.interval}s")
    while True:
        r = sync_all()
        ok = sum(1 for x in r.values() if x.get("own", {}).get("ok"))
        print(f"[card_sync] {time.strftime('%H:%M:%S')} synced own-cards to {ok}/{len(PEERS)} peers")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
