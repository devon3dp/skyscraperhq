"""UE Python — author the 11 QSB materials at /Game/QSB/Materials/ + iterate scene actors.

Materials authored:
  M_QSB_DarkGlass, M_QSB_BlackMetal, M_QSB_BrushedSteel,
  M_QSB_NeonCyan, M_QSB_NeonViolet, M_QSB_GoldTrim,
  M_QSB_EmissiveWindows, M_QSB_HologramBlue, M_QSB_DataStream,
  M_QSB_SelectedFloorGlow, M_QSB_LiftShaftGlass
Then assigns by actor-name pattern. Idempotent.
"""
import unreal

PKG = "/Game/QSB/Materials"

MATERIALS = {
    "M_QSB_DarkGlass":         {"basecolor": (0.02, 0.02, 0.03), "metallic": 0.0, "rough": 0.05, "emissive": (0,0,0)},
    "M_QSB_BlackMetal":        {"basecolor": (0.04, 0.04, 0.04), "metallic": 1.0, "rough": 0.35, "emissive": (0,0,0)},
    "M_QSB_BrushedSteel":      {"basecolor": (0.55, 0.55, 0.6), "metallic": 1.0, "rough": 0.4, "emissive": (0,0,0)},
    "M_QSB_NeonCyan":          {"basecolor": (0.0, 1.0, 1.0), "metallic": 0.0, "rough": 0.5, "emissive": (0.0, 12.0, 12.0)},
    "M_QSB_NeonViolet":        {"basecolor": (0.7, 0.2, 1.0), "metallic": 0.0, "rough": 0.5, "emissive": (8.0, 2.0, 12.0)},
    "M_QSB_GoldTrim":          {"basecolor": (0.85, 0.65, 0.15), "metallic": 1.0, "rough": 0.2, "emissive": (0,0,0)},
    "M_QSB_EmissiveWindows":   {"basecolor": (1.0, 0.85, 0.5), "metallic": 0.0, "rough": 0.7, "emissive": (4.0, 3.5, 2.0)},
    "M_QSB_HologramBlue":      {"basecolor": (0.0, 0.5, 1.0), "metallic": 0.0, "rough": 0.5, "emissive": (0.0, 5.0, 14.0)},
    "M_QSB_DataStream":        {"basecolor": (0.0, 0.8, 0.6), "metallic": 0.0, "rough": 0.4, "emissive": (0.0, 8.0, 6.0)},
    "M_QSB_SelectedFloorGlow": {"basecolor": (1.0, 0.9, 0.3), "metallic": 0.0, "rough": 0.4, "emissive": (12.0, 9.0, 1.5)},
    "M_QSB_LiftShaftGlass":    {"basecolor": (0.05, 0.05, 0.15), "metallic": 0.0, "rough": 0.05, "emissive": (0.2, 0.3, 0.8)},
}


def make_or_get(name: str, spec: dict) -> unreal.Material | None:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = f"{PKG}/{name}"
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset:
        unreal.log(f"qsb: material exists {name}")
        return asset
    factory = unreal.MaterialFactoryNew()
    asset = asset_tools.create_asset(name, PKG, unreal.Material, factory)
    if not asset:
        unreal.log(f"qsb: FAILED to create {name}")
        return None
    # Set base scalar/vector parameters via property expressions
    try:
        bc = unreal.LinearColor(*spec["basecolor"], 1.0)
        em = unreal.LinearColor(*spec["emissive"], 1.0)
        # Constant nodes via Material editing (lightweight)
        # Use unreal.MaterialEditingLibrary
        mel = unreal.MaterialEditingLibrary
        node_bc = mel.create_material_expression(asset, unreal.MaterialExpressionVectorParameter, -300, 0)
        node_bc.set_editor_property("parameter_name", "BaseColor")
        node_bc.set_editor_property("default_value", bc)
        mel.connect_material_property(node_bc, "", unreal.MaterialProperty.MP_BASE_COLOR)
        node_em = mel.create_material_expression(asset, unreal.MaterialExpressionVectorParameter, -300, 200)
        node_em.set_editor_property("parameter_name", "Emissive")
        node_em.set_editor_property("default_value", em)
        mel.connect_material_property(node_em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        # scalar metallic / roughness
        sc_m = mel.create_material_expression(asset, unreal.MaterialExpressionScalarParameter, -300, 400)
        sc_m.set_editor_property("parameter_name", "Metallic")
        sc_m.set_editor_property("default_value", spec["metallic"])
        mel.connect_material_property(sc_m, "", unreal.MaterialProperty.MP_METALLIC)
        sc_r = mel.create_material_expression(asset, unreal.MaterialExpressionScalarParameter, -300, 550)
        sc_r.set_editor_property("parameter_name", "Roughness")
        sc_r.set_editor_property("default_value", spec["rough"])
        mel.connect_material_property(sc_r, "", unreal.MaterialProperty.MP_ROUGHNESS)
        mel.recompile_material(asset)
        unreal.EditorAssetLibrary.save_asset(path)
        unreal.log(f"qsb: created material {name}")
    except Exception as e:
        unreal.log(f"qsb: material setup error {name}: {e}")
    return asset


# Mapping actor-name prefix → material name
ASSIGN_MAP = [
    ("V2_QSB_Floor_",       "M_QSB_DarkGlass"),
    ("V2_WStrip_",          "M_QSB_EmissiveWindows"),
    ("V2_Band_Trading",     "M_QSB_NeonCyan"),
    ("V2_Band_Labs",        "M_QSB_NeonViolet"),
    ("V2_Band_Accommodation","M_QSB_EmissiveWindows"),
    ("V2_Band_Penthouse",   "M_QSB_GoldTrim"),
    ("V2_Flag_OANDA",       "M_QSB_NeonCyan"),
    ("V2_Flag_Binance",     "M_QSB_NeonCyan"),
    ("V2_Flag_Alpaca",      "M_QSB_NeonCyan"),
    ("V2_PenthouseSpike",   "M_QSB_GoldTrim"),
    ("V2_CrownRing_",       "M_QSB_GoldTrim"),
    ("V2_Neighbor_",        "M_QSB_BrushedSteel"),
    ("V2_Ground",           "M_QSB_BlackMetal"),
    ("VU_LiftShaft_",       "M_QSB_LiftShaftGlass"),
    ("VU_CrownDeck",        "M_QSB_GoldTrim"),
    ("VU_CrownTip_",        "M_QSB_GoldTrim"),
    ("VU_SkyTower_",        "M_QSB_BrushedSteel"),
    ("V6_Road_",            "M_QSB_BlackMetal"),
    ("V6_RingSeg_",         "M_QSB_BlackMetal"),
    ("V6_Car_",             "M_QSB_BrushedSteel"),
    ("V7_Tree_",            "M_QSB_DataStream"),  # placeholder until we have green
    ("V8_Arch_",            "M_QSB_DarkGlass"),
    ("V9_City_",            "M_QSB_EmissiveWindows"),
]


def assign_all():
    mats = {}
    for name, spec in MATERIALS.items():
        mats[name] = make_or_get(name, spec)

    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    n = 0
    for a in actors:
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        an = a.get_name()
        for prefix, mname in ASSIGN_MAP:
            if an.startswith(prefix):
                m = mats.get(mname)
                if m:
                    smc = a.get_component_by_class(unreal.StaticMeshComponent)
                    if smc:
                        smc.set_material(0, m)
                        n += 1
                break
    unreal.log(f"qsb: assigned material to {n} actors")
    unreal.EditorLevelLibrary.save_current_level()


assign_all()
