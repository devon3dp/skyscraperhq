#!/usr/bin/env python3
"""qsb_ceo_heartbeat.py — CEO proactive presence loop.

Ross 2026-07-07 12:03 UTC: no CEO was proactively working from board + rulebook.
This heartbeat makes each CEO visibly alive on town-square + polls the board
for tasks referencing their actor name.

Usage:
  python3 tools/qsb_ceo_heartbeat.py --actor hq_claude --hub http://192.168.1.72:8852
  python3 tools/qsb_ceo_heartbeat.py --actor tp_pip    --hub http://192.168.1.72:8852
  python3 tools/qsb_ceo_heartbeat.py --actor acer_cass --hub http://192.168.1.72:8852

Every 60s: reads board via /tasks/data, checks for tasks mentioning this actor
in title/description, and posts a status to town-square via /team_live/say.
"""
import argparse, json, time, urllib.request, urllib.parse

def post(hub, ceo, text):
    q = urllib.parse.urlencode({"ceo": ceo, "text": text})
    try:
        urllib.request.urlopen(f"{hub}/team_live/say?{q}", timeout=5).read()
        return True
    except Exception:
        return False

def read_board(hub):
    try:
        r = urllib.request.urlopen(f"{hub}/tasks/data", timeout=8)
        return json.loads(r.read())
    except Exception:
        return {"tasks": []}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", required=True)
    ap.add_argument("--hub", default="http://192.168.1.72:8852")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="fire once + exit")
    args = ap.parse_args()

    while True:
        d = read_board(args.hub)
        tasks = d.get("tasks", []) if isinstance(d, dict) else []
        open_count = sum(1 for t in tasks if t.get("state") == "open")
        # find tasks mentioning me
        mine = [t for t in tasks
                if args.actor in (t.get("title","") + " " + t.get("description","")).lower()
                and t.get("state") in ("open","pending_admission")]
        text = f"heartbeat · {args.actor} alive · board: {len(tasks)} tasks, {open_count} open, {len(mine)} touch me"
        post(args.hub, args.actor, text)
        if args.once: return
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
