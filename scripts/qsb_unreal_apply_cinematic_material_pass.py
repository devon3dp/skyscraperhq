#!/usr/bin/env python3
"""qsb_unreal_apply_cinematic_material_pass.py

Two-mode operation:

  MODE A — `--write-recipe-only`: write `/tmp/qsb_ue_material_pass.py` which is an
  UE-Python recipe (uses `import unreal`) that can be run INSIDE the editor's
  Python console or via `UnrealEditor -ExecutePythonScript=...`. It creates 11
  Material assets at /Game/QSB/Materials/ and a Material Instance per asset.

  MODE B — `--apply-via-tcp`: tries to call the (not-yet-built) plugin
  `execute_python_command` handler with the recipe; falls back to MODE A if the
  plugin doesn't expose it. Writes the same recipe to disk regardless.

The MCP plugin currently does NOT have a python-exec handler. This script writes
the recipe + status JSON; running the recipe requires either:
  (a) opening the UE editor's Python tab and executing it manually, OR
  (b) extending the plugin with an execute_python handler.
"""

import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
RECIPE_OUT = Path("/tmp/qsb_ue_material_pass.py")
STATUS_OUT = ROOT / "data/registries/qsb_unreal_cinematic_material_pass_status.json"
REPORT_OUT = ROOT / "data/logs/qsb_unreal_cinematic_material_pass_report.md"

MATERIALS = [
    ("M_QSB_DarkGlass",         {"base_color": (0.02, 0.02, 0.04), "metallic": 0.0, "roughness": 0.05, "opacity": 0.3, "translucent": True}),
    ("M_QSB_BlackMetal",        {"base_color": (0.05, 0.05, 0.06), "metallic": 1.0, "roughness": 0.35}),
    ("M_QSB_BrushedSteel",      {"base_color": (0.50, 0.50, 0.55), "metallic": 1.0, "roughness": 0.4}),
    ("M_QSB_NeonCyan",          {"emissive": (0.0, 8.0, 8.0)}),
    ("M_QSB_NeonViolet",        {"emissive": (4.5, 0.6, 8.0)}),
    ("M_QSB_GoldTrim",          {"base_color": (1.0, 0.78, 0.20), "metallic": 1.0, "roughness": 0.2}),
    ("M_QSB_EmissiveWindows",   {"emissive": (5.0, 4.5, 2.5)}),
    ("M_QSB_HologramBlue",      {"emissive": (0.3, 1.5, 3.0), "translucent": True, "opacity": 0.5}),
    ("M_QSB_DataStream",        {"emissive": (0.0, 1.0, 0.4), "translucent": True, "opacity": 0.7}),
    ("M_QSB_SelectedFloorGlow", {"emissive": (1.0, 0.8, 0.2), "fresnel": True}),
    ("M_QSB_LiftShaftGlass",    {"base_color": (0.05, 0.10, 0.15), "metallic": 0.0, "roughness": 0.05, "opacity": 0.35, "translucent": True}),
]


RECIPE_TEMPLATE = '''# qsb_ue_material_pass.py — run inside UE editor Python console
import unreal

MATERIALS = {materials_json}
PACKAGE_PATH = "/Game/QSB/Materials"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
material_factory = unreal.MaterialFactoryNew()

for name, props in MATERIALS:
    asset_path = f"{{PACKAGE_PATH}}/{{name}}"
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        print(f"skip exists: {{asset_path}}")
        continue
    mat = asset_tools.create_asset(asset_name=name, package_path=PACKAGE_PATH,
                                   asset_class=unreal.Material, factory=material_factory)
    bc = props.get("base_color")
    if bc:
        node = unreal.MaterialEditingLibrary.create_material_expression(mat,
            unreal.MaterialExpressionConstant3Vector, -300, 0)
        node.constant = unreal.LinearColor(bc[0], bc[1], bc[2], 1.0)
        unreal.MaterialEditingLibrary.connect_material_property(node, "",
            unreal.MaterialProperty.MP_BASE_COLOR)
    em = props.get("emissive")
    if em:
        en = unreal.MaterialEditingLibrary.create_material_expression(mat,
            unreal.MaterialExpressionConstant3Vector, -300, 200)
        en.constant = unreal.LinearColor(em[0], em[1], em[2], 1.0)
        unreal.MaterialEditingLibrary.connect_material_property(en, "",
            unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if "metallic" in props:
        mn = unreal.MaterialEditingLibrary.create_material_expression(mat,
            unreal.MaterialExpressionConstant, -300, 400)
        mn.r = props["metallic"]
        unreal.MaterialEditingLibrary.connect_material_property(mn, "",
            unreal.MaterialProperty.MP_METALLIC)
    if "roughness" in props:
        rn = unreal.MaterialEditingLibrary.create_material_expression(mat,
            unreal.MaterialExpressionConstant, -300, 600)
        rn.r = props["roughness"]
        unreal.MaterialEditingLibrary.connect_material_property(rn, "",
            unreal.MaterialProperty.MP_ROUGHNESS)
    if props.get("translucent"):
        mat.blend_mode = unreal.BlendMode.BLEND_TRANSLUCENT
        opn = unreal.MaterialEditingLibrary.create_material_expression(mat,
            unreal.MaterialExpressionConstant, -300, 800)
        opn.r = props.get("opacity", 0.5)
        unreal.MaterialEditingLibrary.connect_material_property(opn, "",
            unreal.MaterialProperty.MP_OPACITY)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    print(f"created: {{asset_path}}")

print(f"done: {{len(MATERIALS)}} materials processed")
'''


def write_recipe():
    RECIPE_OUT.write_text(
        RECIPE_TEMPLATE.format(
            materials_json=json.dumps(MATERIALS, indent=4)
        )
    )
    return RECIPE_OUT


def try_apply_via_tcp(recipe_path: Path) -> dict:
    try:
        s = socket.socket(); s.settimeout(8); s.connect(("127.0.0.1", 55557))
        s.sendall(json.dumps({"type": "execute_python_command",
                              "params": {"command": recipe_path.read_text()}}).encode())
        buf = b""
        while True:
            c = s.recv(65536)
            if not c: break
            buf += c
            try: return json.loads(buf.decode())
            except: pass
        return json.loads(buf.decode()) if buf else {"status": "no_response"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try: s.close()
        except: pass


def main():
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recipe_path = write_recipe()
    print(f"recipe written: {recipe_path} ({len(MATERIALS)} materials)")

    via_tcp = None
    if "--apply-via-tcp" in sys.argv:
        via_tcp = try_apply_via_tcp(recipe_path)
        print("apply via tcp:", via_tcp)

    status = {
        "ts": ts,
        "materials_count": len(MATERIALS),
        "recipe_path": str(recipe_path),
        "via_tcp_result": via_tcp,
        "via_tcp_supported": bool(via_tcp and via_tcp.get("status") == "success"),
        "note": ("Plugin does NOT yet have execute_python_command. Run the recipe "
                 "manually inside the UE editor Python console, or extend the "
                 "plugin to add the handler, or launch the editor with "
                 "-ExecutePythonScript=" + str(recipe_path)),
    }
    STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    STATUS_OUT.write_text(json.dumps(status, indent=2))
    REPORT_OUT.write_text(f"""# Cinematic Material Pass — {ts}

- {len(MATERIALS)} materials specified, recipe at `{recipe_path}`
- Via TCP attempt: {via_tcp}

## How to land the materials

1. Open the UE editor (already running per qsb_unreal_visible_build_status.sh)
2. Open Window → Python Console
3. Paste the contents of `{recipe_path}` or run:
   `exec(open('{recipe_path}').read())`

This will create all {len(MATERIALS)} Material assets at /Game/QSB/Materials/.

After they exist, the next pass (material assignment to actors) needs either:
- a plugin extension adding `set_actor_material`, OR
- another UE Python script that iterates `unreal.EditorActorSubsystem.get_all_level_actors()` and calls `set_static_mesh_component.set_material(0, mat)` per name pattern.
""")
    print(f"status: {STATUS_OUT}")
    print(f"report: {REPORT_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
