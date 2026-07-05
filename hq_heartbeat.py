#!/usr/bin/env python3
"""HQ -> ThinkPad reciprocal heartbeat. Every 30s push HQ's live status to the
ThinkPad node so the CEO always has HQ's current picture (mutual continuous link)."""
import urllib.request, json, time
TP = "http://192.168.0.10:9100"
REG = "/vaults/nvme0/qsb_tower_v1/data/registries"
def jget(p, d=None):
    try: return json.load(open(p))
    except Exception: return d or {}
while True:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9100/status", timeout=4) as r:
            st = json.loads(r.read())
        sess = jget(REG + "/qsb_session_pnl_stop.json")
        bus = jget(REG + "/qsb_trader_pnl_bus_latest.json")
        tot = bus.get("totals", {}) if isinstance(bus, dict) else {}
        wins = tot.get("wins", 0); closes = tot.get("closes", 0) or 1
        body = ("HQ-HEARTBEAT " + json.dumps({
            "traders": st.get("fleet", {}).get("belief_traders"),
            "pot": round(st.get("pot", {}).get("committed_gbp", 0), 0),
            "realized": round(sess.get("realized_pnl", 0), 2),
            "win_pct": round(100.0*wins/closes, 1),
            "focus": "binance/oanda sizing + win-rate"}))
        payload = {"id": "hq-heartbeat", "from": "hq", "to": "thinkpad",
                   "kind": "heartbeat", "subject": "hq_status", "body": body}
        req = urllib.request.Request(TP + "/msg", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=6).read()
        open("/vaults/nvme0/qsb_tower_v1/data/logs/hq_heartbeat.log","a").write(time.strftime("%H:%M:%S")+" pushed\\n")
    except Exception:
        pass
    time.sleep(30)
