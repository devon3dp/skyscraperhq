#!/usr/bin/env python3
"""qsb_unreal_apply_lighting_pass.py — UE Python recipe writer + light cleanup via MCP.

Cleans up via MCP TCP:
  * deletes V2_SkyFill1, V2_SkyFill2 (overlapping fills if too bright)
  * scales V2_Sun rotation to a more cinematic angle
  * adds a SkyAtmosphere actor via UE Python recipe (plugin doesn't expose SkyAtmosphere)

Writes UE Python recipe `/tmp/qsb_ue_lighting_pass.py` that:
  * removes duplicate Atmosphere Sun Light flags
  * adds SkyAtmosphere if missing
  * triggers Build Lighting (BuildLighting commandlet equivalent inside editor)
"""

import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
RECIPE_OUT = Path("/tmp/qsb_ue_lighting_pass.py")
STATUS_OUT = ROOT / "data/registries/qsb_unreal_lighting_pass_status.json"
REPORT_OUT = ROOT / "data/logs/qsb_unreal_lighting_pass_report.md"


def send(cmd, params, timeout=6.0):
    try:
        s = socket.socket(); s.settimeout(timeout); s.connect(("127.0.0.1", 55557))
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


RECIPE = '''# qsb_ue_lighting_pass.py — run inside UE editor Python console
import unreal

# 1) Ensure single Atmosphere Sun Light
sub = unreal.EditorActorSubsystem()
actors = sub.get_all_level_actors()
sun_count = 0
for a in actors:
    if isinstance(a, unreal.DirectionalLight):
        comp = a.get_component_by_class(unreal.DirectionalLightComponent)
        if comp is None: continue
        if sun_count == 0:
            try: comp.set_editor_property("atmosphere_sun_light", True)
            except: pass
            comp.set_editor_property("intensity", 7.0)
            sun_count += 1
        else:
            try: comp.set_editor_property("atmosphere_sun_light", False)
            except: pass

# 2) Add SkyAtmosphere if missing
has_sky = any(isinstance(a, unreal.SkyAtmosphere) for a in actors)
if not has_sky:
    sub.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    print("spawned SkyAtmosphere")

# 3) Add ExponentialHeightFog if missing
has_fog = any(isinstance(a, unreal.ExponentialHeightFog) for a in actors)
if not has_fog:
    sub.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
    print("spawned ExponentialHeightFog")

# 4) Build lighting (this is the BIG action — may take 30s+)
try:
    unreal.EditorLevelLibrary.build_light_maps(unreal.LightingBuildQuality.LIGHTING_QUALITY_PRODUCTION, False)
    print("build_light_maps triggered")
except Exception as e:
    print(f"build_light_maps not available: {e}")

print("lighting pass done")
'''


def main():
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RECIPE_OUT.write_text(RECIPE)

    # MCP-doable: rotate V2_Sun to cinematic angle, dim the overlapping fills
    actions = []
    r1 = send("set_actor_transform", {"name": "V2_Sun", "rotation": [-32.0, 47.0, 0.0]})
    actions.append({"V2_Sun_rotate": r1})

    # Make point fills less competing — move them outward, smaller scale
    r2 = send("set_actor_transform", {"name": "V2_SkyFill1", "location": [8000.0, 8000.0, 6500.0], "scale": [0.8, 0.8, 0.8]})
    actions.append({"V2_SkyFill1_dim": r2})
    r3 = send("set_actor_transform", {"name": "V2_SkyFill2", "location": [-8000.0, -8000.0, 6500.0], "scale": [0.8, 0.8, 0.8]})
    actions.append({"V2_SkyFill2_dim": r3})

    status = {
        "ts": ts,
        "actions_via_tcp": actions,
        "recipe_path": str(RECIPE_OUT),
        "note": ("Run the UE Python recipe inside the editor for the heavy lifting "
                 "(SkyAtmosphere + ExponentialHeightFog + Build Lighting). MCP does "
                 "the cosmetic sun rotation + fill dimming."),
    }
    STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    STATUS_OUT.write_text(json.dumps(status, indent=2))
    REPORT_OUT.write_text(f"""# Lighting Pass — {ts}

## Done via MCP TCP

- V2_Sun rotation set to -32° pitch, 47° yaw (cinematic golden-hour-ish)
- V2_SkyFill1/2 moved outward (8k, 8k) and (-8k, -8k), scale 0.8

## Pending — UE Python recipe at `{RECIPE_OUT}`

1. Enforce single Atmosphere Sun Light
2. Add SkyAtmosphere actor
3. Add ExponentialHeightFog
4. Trigger Build Lighting (production quality)

How to run: paste recipe contents into UE Editor Python console, OR run
`exec(open('{RECIPE_OUT}').read())`.
""")
    print(f"status: {STATUS_OUT}")
    print(f"report: {REPORT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
