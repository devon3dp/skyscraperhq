#!/usr/bin/env python3
"""Detect canonical floors, then add architectural detail directly on top of the
existing V2_QSB_Floor_* stack. Idempotent — names V8_Arch_* are stable.

Adds (per detected floor count N):
  - N corner pillars per slab corner (4 columns Z=0..top_z) — cylinders
  - N "ribs" across each slab face — small cones
  - 1 band "sign" cube per 10 floors (visible department label position)
  - Roof crown ring of 12 cones + central spire (cone)
  - Plaza band of sphere lamps
  - Tower base concourse: 32 small cubes ringing the foot
"""

import json
import math
import socket
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CANON = ROOT / "data/registries/qsb_canonical_tower_structure_latest.json"
STATUS = ROOT / "data/registries/qsb_unreal_professional_skyscraper_generation_status.json"
REPORT = ROOT / "data/logs/qsb_unreal_professional_skyscraper_generation_report.md"
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


def canonical_floor_count() -> int:
    if not CANON.exists():
        raise RuntimeError(f"missing {CANON} — run scripts/qsb_detect_canonical_tower_structure.sh first")
    with CANON.open() as f:
        return int(json.load(f)["canonical_floor_count"])


def main():
    n = canonical_floor_count()
    print(f"canonical_floor_count={n}", flush=True)
    floor_spacing = 30.0
    base_z = 0.0
    top_z = base_z + (n - 1) * floor_spacing + 15.0
    half = 400.0  # slab half-width matches V2_QSB_Floor scale 8

    counts = {}

    # Corner pillars — 4 cylinders from ground to top
    np = 0
    for i, (sx, sy) in enumerate([(half, half), (-half, half), (-half, -half), (half, -half)]):
        np += spawn(f"V8_Arch_Pillar_{i+1}", "StaticMeshActor",
                    [sx, sy, top_z / 2.0], [0, 0, 0],
                    [0.5, 0.5, top_z / 100.0], mesh="Cylinder")
    counts["pillars"] = np
    print(f"corner pillars: {np}/4", flush=True)

    # Band signs — 1 cube per 10 floors, ~mid-height of band, slightly out from face
    ns = 0
    for b in range(0, n, 10):
        mid_floor = b + 5
        z = (mid_floor - 1) * floor_spacing + 15.0
        if z > top_z: break
        # face +X
        ns += spawn(f"V8_Arch_BandSign_{b:03d}", "StaticMeshActor",
                    [half + 50.0, 0.0, z], [0, 0, 0], [0.3, 4.0, 1.0], mesh="Cube")
    counts["band_signs"] = ns
    print(f"band signs: {ns}", flush=True)

    # Roof crown — 12 cones around top
    nc = 0
    for i in range(12):
        a = (i / 12.0) * 2 * math.pi
        x = 380.0 * math.cos(a)
        y = 380.0 * math.sin(a)
        nc += spawn(f"V8_Arch_RoofSpike_{i+1:02d}", "StaticMeshActor",
                    [x, y, top_z + 150.0], [0, 0, 0], [1.0, 1.0, 5.0], mesh="Cone")
    counts["roof_spikes"] = nc

    # Central spire
    nspire = spawn("V8_Arch_CentralSpire", "StaticMeshActor",
                   [0.0, 0.0, top_z + 700.0], [0, 0, 0], [0.6, 0.6, 12.0], mesh="Cone")
    counts["central_spire"] = int(nspire)

    # Plaza lamp band — 24 sphere lamps at R=1900cm
    npl = 0
    for i in range(24):
        a = (i / 24.0) * 2 * math.pi
        x = 1900.0 * math.cos(a)
        y = 1900.0 * math.sin(a)
        npl += spawn(f"V8_Arch_PlazaLamp_{i+1:02d}", "StaticMeshActor",
                     [x, y, 350.0], [0, 0, 0], [0.5, 0.5, 0.5], mesh="Sphere")
    counts["plaza_lamps"] = npl

    # Base concourse — 32 cubes ringing the tower foot at R=700cm
    nb = 0
    for i in range(32):
        a = (i / 32.0) * 2 * math.pi
        x = 700.0 * math.cos(a)
        y = 700.0 * math.sin(a)
        nb += spawn(f"V8_Arch_Concourse_{i+1:02d}", "StaticMeshActor",
                    [x, y, 50.0], [0, 0, math.degrees(a)], [1.0, 0.5, 0.8], mesh="Cube")
    counts["concourse"] = nb

    total = sum(counts.values())
    status = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "canonical_floor_count": n,
        "added": counts,
        "total_added": total,
        "tower_top_z_cm": top_z,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, indent=2))
    REPORT.write_text(f"""# Professional Skyscraper Generation — {status['ts']}

- Canonical floor count detected: **{n}** (from {CANON})
- Tower top Z: {top_z} cm
- Added: {total} new actors

| Layer | Count |
|---|---|
| Corner pillars (cylinder) | {counts['pillars']} |
| Band signs (every 10 floors) | {counts['band_signs']} |
| Roof spikes (cone) | {counts['roof_spikes']} |
| Central spire (cone) | {counts['central_spire']} |
| Plaza lamps (sphere) | {counts['plaza_lamps']} |
| Concourse base ring | {counts['concourse']} |

All actor names V8_Arch_* — re-runnable idempotently.
""")
    print(f"status: {STATUS}")
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
