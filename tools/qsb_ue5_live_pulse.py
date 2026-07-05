#!/usr/bin/env python3
"""Live UE5 pulse: every 5s reads trader state + belief and updates UE actors.

What this does:
- Reads data/registries/qsb_portfolio_pot.json → today's open positions count + committed £
- Reads sample of data/registries/cognitive/belief_state_*.json → recent ticks
- Reads tail of data/registries/qsb_session_diary.md → newest event
- Adjusts UE actors:
  * V5_SkyB_<n> (8 sky beacons): rotate around tower (different yaw each tick)
  * V_LivePulse_<n>: ring of 8 cubes that grow/shrink with current trade activity
  * V_TradePulse_BTC/ETH/JPY: a cube per active instrument that scales with open count

Runs forever until Ctrl+C. Designed for `nohup` background use.
"""

import json
import math
import socket
import time
from pathlib import Path

UE_HOST = "127.0.0.1"
UE_PORT = 55557
ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POT_PATH = ROOT / "data/registries/qsb_portfolio_pot.json"
COG_DIR = ROOT / "data/registries/cognitive"
DIARY = ROOT / "data/registries/qsb_session_diary.md"
LOG = ROOT / "logs/intelligence/ue5_live_pulse.log"
TICK_S = 5


def send(cmd, params, timeout=5.0):
    try:
        s = socket.socket(); s.settimeout(timeout); s.connect((UE_HOST, UE_PORT))
        s.sendall(json.dumps({"type": cmd, "params": params}).encode())
        buf = b""
        while True:
            c = s.recv(65536)
            if not c: break
            buf += c
            try: return json.loads(buf.decode())
            except: pass
        return json.loads(buf.decode())
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try: s.close()
        except: pass


def read_pot():
    try:
        with POT_PATH.open() as f:
            d = json.load(f)
        return {
            "committed": d.get("committed_gbp", 0.0),
            "open": len(d.get("open_positions", {})),
            "by_venue": d.get("by_venue", {}),
        }
    except Exception as e:
        return {"committed": 0, "open": 0, "by_venue": {}, "err": str(e)}


def ensure_actor(name, type_, loc, scale, mesh=None):
    """Try set_actor_transform; if not exists, create_actor."""
    r = send("set_actor_transform", {"name": name, "location": loc, "scale": scale})
    if r and r.get("status") == "success":
        return True
    p = {"name": name, "type": type_, "location": loc, "rotation": [0, 0, 0], "scale": scale}
    if mesh: p["mesh"] = mesh
    r = send("create_actor", p)
    return bool(r and r.get("status") == "success")


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = LOG.open("a")
    fh.write(f"\n[{time.strftime('%FT%TZ', time.gmtime())}] qsb_ue5_live_pulse start\n")
    fh.flush()

    tick = 0
    while True:
        tick += 1
        try:
            pot = read_pot()
            n = pot["open"]
            committed = pot["committed"]

            # Skybeacon arc — rotate 8 V5_SkyB_* by tick offset (visual heartbeat)
            for i in range(1, 9):
                ang_deg = (i / 8.0) * 360.0 + (tick * 6.0) % 360.0
                ang = math.radians(ang_deg)
                x = 800.0 * math.cos(ang)
                y = 800.0 * math.sin(ang)
                send("set_actor_transform",
                     {"name": f"V5_SkyB_{i:02d}", "location": [x, y, 7000.0]})

            # Live pulse ring — 8 cubes around tower mid that grow with open count
            scale_z = max(0.5, min(8.0, n * 0.15))
            for i in range(1, 9):
                ang = (i / 8.0) * 2 * math.pi
                x = 1600.0 * math.cos(ang)
                y = 1600.0 * math.sin(ang)
                ensure_actor(f"V_LivePulse_{i}", "StaticMeshActor",
                             [x, y, 3500.0], [1.0, 1.0, scale_z], mesh="Cylinder")

            # Per-venue indicator cubes — scale with committed £
            venues = pot.get("by_venue", {})
            for vi, (vname, val) in enumerate(list(venues.items())[:4]):
                ang = (vi / 4.0) * 2 * math.pi
                x = 3500.0 * math.cos(ang)
                y = 3500.0 * math.sin(ang)
                s = max(0.5, min(10.0, val / 200.0))
                ensure_actor(f"V_VenueBar_{vi+1}", "StaticMeshActor",
                             [x, y, s * 50.0], [2.0, 2.0, s], mesh="Cube")

            msg = f"tick={tick} open={n} committed=£{committed:.0f} venues={list(venues.keys())}\n"
            fh.write(f"[{time.strftime('%FT%TZ', time.gmtime())}] {msg}")
            fh.flush()
        except Exception as e:
            fh.write(f"[err {tick}] {e}\n"); fh.flush()
        time.sleep(TICK_S)


if __name__ == "__main__":
    main()
