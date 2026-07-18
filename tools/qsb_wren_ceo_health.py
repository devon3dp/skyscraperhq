#!/usr/bin/env python3
"""Wren's CEO health-check tool.

Ross 2026-07-07: Wren checks that HQ + TP + Acer are online, present, and available
for work. If a CEO is missing or lost, Wren books a fix-task on the council board
and (with Ross-granted authority 2026-07-07) may write code to restore the missing
CEO.

Usage:
  python3 tools/qsb_wren_ceo_health.py            # print status report
  python3 tools/qsb_wren_ceo_health.py --json     # JSON output
  python3 tools/qsb_wren_ceo_health.py --if-broken-propose   # book a repair task
                                                             # when quorum is broken
"""
import json, sys, time, subprocess, argparse, urllib.request

CEOS = ["hq_claude", "tp_pip", "acer_cass"]
HUB  = "http://127.0.0.1:8852"
PING = "One line: are you online and available for work? Reply exactly YES or NO."


def ping_ceo(ceo: str, timeout_s: int = 25) -> dict:
    t0 = time.time()
    body = json.dumps({"prompt": PING}).encode()
    try:
        req = urllib.request.Request(f"{HUB}/ceo_mind/{ceo}",
                                     data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        r = urllib.request.urlopen(req, timeout=timeout_s)
        data = json.loads(r.read().decode())
        latency_s = round(time.time() - t0, 2)
        reply = (data.get("reply") or "").strip()[:200]
        err   = data.get("error", "")
        mind  = data.get("mind", "?")
        online = bool(reply and not err and "rc=" not in reply)
        available = online and "YES" in reply.upper()
        return {"ceo": ceo, "online": online, "available": available,
                "latency_s": latency_s, "mind": mind, "reply": reply,
                "error": err}
    except Exception as e:
        return {"ceo": ceo, "online": False, "available": False,
                "latency_s": round(time.time() - t0, 2),
                "mind": "?", "reply": "", "error": str(e)[:200]}


def check_all() -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = [ping_ceo(c) for c in CEOS]
    online_count = sum(1 for r in results if r["online"])
    quorum_met = online_count == len(CEOS)
    return {
        "ts": now,
        "checked_by": "wren",
        "ceos": results,
        "online_count": f"{online_count}/{len(CEOS)}",
        "quorum_met": quorum_met,
        "missing": [r["ceo"] for r in results if not r["online"]],
    }


def propose_repair(missing: list) -> dict:
    sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
    from qsb_council_tasks import propose
    title = f"Wren: restore missing CEO(s) — {', '.join(missing)}"
    desc  = (f"Wren CEO health-check detected quorum broken. Missing: {missing}. "
             f"Ross 2026-07-07 gave Wren code-fix authority. Wren proposes this "
             f"repair task. Fix path: peer comms (SSH direct + LAN sweep + "
             f"dashboards) to locate + restore.")
    return propose(title=title, description=desc, actor="wren", priority="high")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--if-broken-propose", action="store_true")
    args = ap.parse_args()

    r = check_all()

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"═══ Wren CEO health-check @ {r['ts']} ═══")
        print(f"  online: {r['online_count']}  quorum: {'✓' if r['quorum_met'] else '✗ BROKEN'}")
        for c in r["ceos"]:
            ok = "✓" if c["online"] else "✗"
            av = " · AVAILABLE" if c["available"] else ""
            print(f"  {ok} [{c['ceo']}] {c['latency_s']}s mind={c['mind']}{av}")
            if c["reply"]:
                print(f"    reply: {c['reply'][:120]}")
            if c["error"]:
                print(f"    error: {c['error'][:120]}")
        if r["missing"]:
            print(f"  missing: {r['missing']}")

    if args.if_broken_propose and not r["quorum_met"]:
        p = propose_repair(r["missing"])
        print(f"  → repair task booked: {p}")


if __name__ == "__main__":
    main()
