#!/usr/bin/env python3
"""Generate a futuristic city around the tower: varied skyline + signage + plazas.

Idempotent — actor names V9_City_*. Re-runnable adds only what is missing.
"""

import json
import math
import random
import socket
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATUS = ROOT / "data/registries/qsb_unreal_futuristic_city_generation_status.json"
REPORT = ROOT / "data/logs/qsb_unreal_futuristic_city_generation_report.md"
HOST, PORT = "127.0.0.1", 55557


def send(cmd, params, timeout=10.0):
    try:
        s = socket.socket(); s.settimeout(timeout); s.connect((HOST, PORT))
        s.sendall(json.dumps({"type": cmd, "params": params}).encode())
        buf = b""
        while True:
            c = s.recv(65536)
            if not c: break
            buf += c
            try: return json.loads(buf.decode())
            except: pass
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try: s.close()
        except: pass


def spawn(name, type_, loc, rot, scale, mesh=None):
    p = {"name": name, "type": type_, "location": loc, "rotation": rot, "scale": scale}
    if mesh: p["mesh"] = mesh
    r = send("create_actor", p)
    return bool(r and r.get("status") == "success")


def main():
    random.seed(2026)
    t0 = time.time()
    counts = {}

    # 40 secondary skyscrapers in a 2nd ring R=8000-9000
    n_sky = 0
    for i in range(40):
        a = (i / 40.0) * 2 * math.pi + random.uniform(-0.05, 0.05)
        r = 8500.0 + random.uniform(-700, 700)
        x = r * math.cos(a)
        y = r * math.sin(a)
        h = random.uniform(15.0, 45.0)
        w = random.uniform(4.0, 9.0)
        n_sky += spawn(f"V9_City_Sky_{i+1:02d}", "StaticMeshActor",
                       [x, y, h * 50.0], [0, 0, random.uniform(-20, 20)],
                       [w, w, h], mesh="Cube")
    counts["secondary_skyline"] = n_sky
    print(f"secondary skyline: {n_sky}/40", flush=True)

    # 20 "antennae" cones on top of secondary skyline (every 2nd)
    n_ant = 0
    for i in range(0, 40, 2):
        a = (i / 40.0) * 2 * math.pi
        r = 8500.0
        x = r * math.cos(a)
        y = r * math.sin(a)
        n_ant += spawn(f"V9_City_Ant_{i+1:02d}", "StaticMeshActor",
                       [x, y, 3500.0], [0, 0, 0], [0.4, 0.4, 8.0], mesh="Cone")
    counts["antennae"] = n_ant

    # 16 neon plaza signs (small thin cubes elevated on cylinder posts) — ring near tower
    n_sign = 0
    for i in range(16):
        a = (i / 16.0) * 2 * math.pi
        r = 3000.0
        x = r * math.cos(a)
        y = r * math.sin(a)
        n_sign += spawn(f"V9_City_SignPost_{i+1:02d}", "StaticMeshActor",
                        [x, y, 400.0], [0, 0, 0], [0.25, 0.25, 8.0], mesh="Cylinder")
        n_sign += spawn(f"V9_City_SignBoard_{i+1:02d}", "StaticMeshActor",
                        [x, y, 850.0], [0, 0, math.degrees(a) + 90], [0.2, 4.0, 1.5], mesh="Cube")
    counts["plaza_signs"] = n_sign

    # 32 emissive "window" cubes scattered on secondary skyline (use PointLight for emissive-look)
    n_win = 0
    for i in range(32):
        a = (i / 32.0) * 2 * math.pi
        r = 8500.0
        x = r * math.cos(a)
        y = r * math.sin(a)
        h = random.uniform(800.0, 2500.0)
        n_win += spawn(f"V9_City_Window_{i+1:02d}", "PointLight",
                       [x, y, h], [0, 0, 0], [1.5, 1.5, 1.5])
    counts["window_lights"] = n_win

    # 8 cinematic atmosphere markers high up
    n_atm = 0
    for i in range(8):
        a = (i / 8.0) * 2 * math.pi
        x = 6000.0 * math.cos(a)
        y = 6000.0 * math.sin(a)
        n_atm += spawn(f"V9_City_AtmMarker_{i+1}", "PointLight",
                       [x, y, 8000.0], [0, 0, 0], [4, 4, 4])
    counts["atm_markers"] = n_atm

    elapsed = time.time() - t0
    status = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "added": counts,
        "total_added": sum(counts.values()),
        "elapsed_s": elapsed,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, indent=2))
    REPORT.write_text(f"""# Futuristic City Generation — {status['ts']}

- Total added: {status['total_added']} actors in {elapsed:.1f}s
- {counts['secondary_skyline']} secondary skyscrapers (R=8.5km)
- {counts['antennae']} antennae cones
- {counts['plaza_signs']} plaza sign posts + boards
- {counts['window_lights']} scattered window lights
- {counts['atm_markers']} high atmosphere markers
""")
    print(f"status: {STATUS}")
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
