"""UE Python — spawn 8 lift-cab cubes that the live_pulse ticker can move."""
import unreal

W = unreal.EditorLevelLibrary.get_editor_world()
sm = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")

# Lift cabs at the 8 shaft locations (matches VU_LiftShaft positions in cinematic generator)
positions = [
    ( 410.0, 0.0), (-410.0, 0.0), (0.0,  410.0), (0.0, -410.0),
    ( 410.0, 410.0), (-410.0, 410.0), (410.0, -410.0), (-410.0, -410.0),
]
created = 0
for i, (x, y) in enumerate(positions, 1):
    name = f"V11_LiftCab_{i}"
    if unreal.EditorLevelLibrary.get_actor_reference(name):
        continue
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(x, y, 200.0), unreal.Rotator(0,0,0))
    if actor:
        actor.set_actor_label(name)
        actor.set_actor_scale3d(unreal.Vector(1.5, 1.5, 1.0))
        smc = actor.get_component_by_class(unreal.StaticMeshComponent)
        if smc and sm: smc.set_static_mesh(sm)
        created += 1

unreal.EditorLevelLibrary.save_current_level()
unreal.log(f"qsb: lift pass — {created} cabs spawned")
