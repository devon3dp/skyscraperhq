#!/usr/bin/env python3
"""HQ→ThinkPad heartbeat — proves continuous live comms.

Posts a small status payload to ThinkPad's /msg every 60s.
Includes: fleet count, pot state, gate state, GPU state, last F47 ts.
"""
import json, time, urllib.request, urllib.error, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POT  = ROOT / "data/registries/qsb_portfolio_pot.json"
GATE = ROOT / "data/registries/qsb_100_online_hard_blockers.json"
F47  = ROOT / "data/registries/qsb_f47_team_records.jsonl"
LOG  = ROOT / "logs/intelligence/qsb_tp_heartbeat.log"
TP_URL = "http://192.168.0.10:9100/msg"
INTERVAL = 30

def log(msg):
    with LOG.open("a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")

def fleet_counts():
    try:
        ps = subprocess.run(["ps","-eo","cmd","ww"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    def cnt(needle):
        return sum(1 for l in ps.splitlines() if l.startswith(("python","/usr/bin/python")) and needle in l)
    return {
        "belief": cnt("qsb_belief_driven_trader"),
        "streams": cnt("qsb_f41_oanda_stream") + cnt("qsb_f42_binance_stream") + cnt("qsb_f43_alpaca_stream"),
        "helpers": cnt("qsb_belief_updater") + cnt("qsb_regime_detector") + cnt("qsb_thermal_guard"),
    }

def gpu_state():
    try:
        out = subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu,memory.used","--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=3).stdout.strip()
        if out:
            t, m = [s.strip() for s in out.split(",")]
            return {"temp_c": int(t), "vram_mib": int(m)}
    except Exception:
        pass
    return {"off_bus": True}

def f47_last_ts():
    try:
        with F47.open() as f:
            for line in f:
                pass
            return json.loads(line).get("ts","")
    except Exception:
        return ""

def post_heartbeat(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(TP_URL, data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.read().decode()[:120]
    except Exception as e:
        return f"ERR:{type(e).__name__}:{str(e)[:80]}"

def main():
    log("heartbeat start")
    n = 0
    while True:
        n += 1
        try:
            pot = json.loads(POT.read_text())
            gate = json.loads(GATE.read_text())
        except Exception:
            pot = {}; gate = {}
        payload = {
            "from": "hq-claude",
            "to": "thinkpad-claude",
            "kind": "heartbeat",
            "subject": f"HQ heartbeat #{n}",
            "body": json.dumps({
                "fleet": fleet_counts(),
                "pot": {
                    "open": len(pot.get("open_positions",{})),
                    "committed_gbp": round(pot.get("committed_gbp",0),2),
                    "cap_gbp": pot.get("cap_gbp",0),
                },
                "gate": {
                    "execution_allowed": gate.get("execution_allowed"),
                    "real_money": gate.get("real_money_live_trading_enabled"),
                },
                "gpu": gpu_state(),
                "last_f47_ts": f47_last_ts(),
                "seq": n,
            }, indent=2),
            "ts_iso": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        }
        resp = post_heartbeat(payload)
        log(f"#{n} resp={resp}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
