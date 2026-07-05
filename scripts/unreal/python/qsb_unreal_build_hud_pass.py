"""UE Python — author UMG widget assets at /Game/QSB/Widgets/ as scaffolding.

Creates empty widget blueprints (visual styling happens in-editor):
  WBP_QSB_TopBar, WBP_QSB_LeftRail, WBP_QSB_RightPanel, WBP_QSB_BottomDock
"""
import unreal

WIDGETS = [
    "WBP_QSB_TopBar",
    "WBP_QSB_LeftRail",
    "WBP_QSB_RightPanel",
    "WBP_QSB_BottomDock",
    "WBP_QSB_WorkerWindow",
    "WBP_QSB_LedgerWindow",
    "WBP_QSB_PnLWindow",
    "WBP_QSB_ModelResponseWindow",
    "WBP_QSB_SmokeTestWindow",
    "WBP_QSB_FloorActivityWindow",
    "WBP_QSB_OpenClawWindow",
    "WBP_QSB_BuildProgressWindow",
]
PKG = "/Game/QSB/Widgets"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
created = []
for name in WIDGETS:
    path = f"{PKG}/{name}"
    if unreal.EditorAssetLibrary.load_asset(path):
        unreal.log(f"qsb: widget exists {name}")
        continue
    try:
        factory = unreal.WidgetBlueprintFactory()
        wb = asset_tools.create_asset(name, PKG, None, factory)
        if wb:
            unreal.EditorAssetLibrary.save_asset(path)
            created.append(name)
            unreal.log(f"qsb: created widget {name}")
    except Exception as e:
        unreal.log(f"qsb: widget create error {name}: {e}")

unreal.log(f"qsb: HUD pass — {len(created)} new widgets")
