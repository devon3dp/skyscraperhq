#!/usr/bin/env python3
"""qsb_unreal_apply_visual_upgrade_pass.py

ONE visual upgrade pass. Idempotent — names are stable, so re-running adds only
what is missing. Reads canonical floor count from
data/registries/qsb_canonical_tower_structure_latest.json (NOT hardcoded).

What this pass does (incremental, layer by layer):
  L1 Skyline depth — 24 background tall cubes at R=12000-18000 (varied heights)
  L2 Lift shafts — 4 vertical thin cubes per side of the tower (8 total)
  L3 Crown deck — wide plate above the penthouse
  L4 Plaza light columns — 16 cylinders at the entry plaza
  L5 Sky atmosphere markers — 16 high pointlights at R=10000 above tower

Materials and UMG aren't created here — that requires UE Python (PythonScriptPlugin).
This pass only uses the patched UnrealMCP plugin's create_actor with `mesh` param.

Status file: data/registries/qsb_unreal_visual_upgrade_pass_status.json
"""

import json
import math
import socket
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CANON = ROOT / "data/registries/qsb_canonical_tower_structure_latest.json"
STATUS = ROOT / "data/registries/qsb_unreal_visual_upgrade_pass_status.json"
HOST, PORT = "127.0.0.1", 55557


def send(cmd, params, timeout=8.0):
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
        return json.loads(buf.decode()) if buf else None
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try: s.close()
        except: pass


def spawn(name, type_, loc, rot, scale, mesh=None):
    p = {"name": name, "type": type_, "location": loc, "rotation": rot, "scale": scale}
    if mesh:
        p["mesh"] = mesh
    r = send("create_actor", p)
    return bool(r and r.get("status") == "success")


def canonical_floor_count() -> int:
    if not CANON.exists():
        return 169  # safe default — but CALLER must run qsb_detect_canonical_tower_structure.sh first
    with CANON.open() as f:
        return int(json.load(f)["canonical_floor_count"])


def main():
    n_floors = canonical_floor_count()
    print(f"canonical_floor_count={n_floors}", flush=True)
    floor_spacing = 30.0  # matches build_city_block_v2
    base_z = 0.0
    top_z = base_z + (n_floors - 1) * floor_spacing + 15.0

    counts = {}

    # L1 — skyline depth
    n_l1 = 0
    for i in range(24):
        ang = (i / 24.0) * 2 * math.pi
        r = 13000.0 + (i % 5) * 1000.0
        x = r * math.cos(ang)
        y = r * math.sin(ang)
        h = 25.0 + (i * 3) % 40
        n_l1 += spawn(f"VU_SkyTower_{i+1:02d}", "StaticMeshActor",
                      [x, y, h * 50.0], [0, 0, 0], [12.0, 12.0, h], mesh="Cube")
    counts["L1_SkyTowers"] = n_l1
    print(f"L1 skyline: {n_l1}/24", flush=True)

    # L2 — lift shafts: thin tall cubes at 4 corners of tower edge + 4 mid faces
    n_l2 = 0
    edge = 410.0  # just outside the 8m slab
    positions = [
        ( edge,     0.0),  # +X
        (-edge,     0.0),  # -X
        ( 0.0,   edge),    # +Y
        ( 0.0,  -edge),    # -Y
        ( edge,  edge),    # NE
        (-edge,  edge),    # NW
        ( edge, -edge),    # SE
        (-edge, -edge),    # SW
    ]
    for i, (x, y) in enumerate(positions):
        z = top_z / 2.0
        n_l2 += spawn(f"VU_LiftShaft_{i+1}", "StaticMeshActor",
                      [x, y, z], [0, 0, 0], [0.4, 0.4, top_z / 100.0], mesh="Cube")
    counts["L2_LiftShafts"] = n_l2
    print(f"L2 lift shafts: {n_l2}/8", flush=True)

    # L3 — crown deck: wide flat slab above penthouse + 8 cone tips around it
    n_l3 = 0
    deck_z = top_z + 800.0
    n_l3 += spawn("VU_CrownDeck", "StaticMeshActor",
                  [0, 0, deck_z], [0, 0, 0], [16.0, 16.0, 0.5], mesh="Cube")
    for i in range(8):
        ang = (i / 8.0) * 2 * math.pi
        x = 700.0 * math.cos(ang)
        y = 700.0 * math.sin(ang)
        n_l3 += spawn(f"VU_CrownTip_{i+1}", "StaticMeshActor",
                      [x, y, deck_z + 400.0], [0, 0, 0], [1.5, 1.5, 8.0], mesh="Cone")
    counts["L3_Crown"] = n_l3
    print(f"L3 crown: {n_l3}/9", flush=True)

    # L4 — plaza light columns at the entry plaza
    n_l4 = 0
    for i in range(16):
        ang = (i / 16.0) * 2 * math.pi
        x = 1700.0 * math.cos(ang)
        y = 1700.0 * math.sin(ang)
        # column = cylinder + sphere ball on top
        n_l4 += spawn(f"VU_PlazaCol_{i+1:02d}_Pole", "StaticMeshActor",
                      [x, y, 250.0], [0, 0, 0], [0.25, 0.25, 5.0], mesh="Cylinder")
        n_l4 += spawn(f"VU_PlazaCol_{i+1:02d}_Ball", "StaticMeshActor",
                      [x, y, 520.0], [0, 0, 0], [0.6, 0.6, 0.6], mesh="Sphere")
        n_l4 += spawn(f"VU_PlazaCol_{i+1:02d}_Light", "PointLight",
                      [x, y, 540.0], [0, 0, 0], [1, 1, 1])
    counts["L4_PlazaColumns"] = n_l4
    print(f"L4 plaza columns: {n_l4}/48", flush=True)

    # L5 — sky atmosphere ring of high point lights
    n_l5 = 0
    for i in range(16):
        ang = (i / 16.0) * 2 * math.pi
        x = 10000.0 * math.cos(ang)
        y = 10000.0 * math.sin(ang)
        n_l5 += spawn(f"VU_SkyLight_{i+1:02d}", "PointLight",
                      [x, y, 9000.0], [0, 0, 0], [3, 3, 3])
    counts["L5_SkyLights"] = n_l5
    print(f"L5 sky lights: {n_l5}/16", flush=True)

    total = sum(counts.values())
    status = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "canonical_floor_count": n_floors,
        "layers": counts,
        "total_added_attempts": total,
        "tower_top_z_cm": top_z,
        "notes": [
            "All names stable (VU_*) — re-running this pass adds only what failed before",
            "Materials not applied (plugin limit). Run UE Python to assign Materials when assets exist",
            "Lighting rebuild still required: Build > Build Lighting Only inside the editor",
        ],
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with STATUS.open("w") as f:
        json.dump(status, f, indent=2)
    print(f"\nstatus: {STATUS}")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
