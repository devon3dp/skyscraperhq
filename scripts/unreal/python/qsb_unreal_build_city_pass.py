"""UE Python — add 20 background skyline towers via spawn_actor pattern.

Used as an in-editor builder (the MCP plugin also does this — this version
runs from inside the editor and saves the level).
"""
import unreal
import math

W = unreal.EditorLevelLibrary.get_editor_world()
sm = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")
created = 0
for i in range(20):
    a = (i / 20.0) * 2 * math.pi
    r = 14000.0 + (i % 4) * 700.0
    x = r * math.cos(a)
    y = r * math.sin(a)
    h = 28.0 + (i * 5) % 32
    name = f"V10_BgTower_{i+1:02d}"
    if unreal.EditorLevelLibrary.get_actor_reference(name) is not None:
        continue
    loc = unreal.Vector(x, y, h * 50.0)
    rot = unreal.Rotator(0, 0, 0)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
    if not actor:
        continue
    actor.set_actor_label(name)
    actor.set_actor_scale3d(unreal.Vector(10.0, 10.0, h))
    smc = actor.get_component_by_class(unreal.StaticMeshComponent)
    if smc and sm:
        smc.set_static_mesh(sm)
    created += 1
unreal.EditorLevelLibrary.save_current_level()
unreal.log(f"qsb: city pass added {created} background towers")
