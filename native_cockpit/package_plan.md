# Native Cockpit V2 — Packaging Plan

## Standalone executable

```bash
pip install pyinstaller
cd native_cockpit/qt
pyinstaller --onefile \
  --name qsb_native_cockpit \
  --add-data "/vaults/nvme0/qsb_tower_v1/data/registries:registries" \
  main.py
```

Output: `dist/qsb_native_cockpit` (single executable, ~50 MB).

## AppImage (Linux desktop)

```bash
# Use linuxdeploy + appimagetool — out of scope for V2.
```

## Future engine swaps

The telemetry bridge produces a JSON snapshot consumed by the scene
engine. To swap from PyQt5 QGraphicsView to Qt3D:

1. `sudo apt install python3-pyqt5.qt3d`
2. Replace `QSBTowerScene` with a Qt3D scene built from the same snapshot.

To swap to Panda3D:

1. `pip install panda3d`
2. Build a Panda3D scene under `native_cockpit/panda3d/` consuming the
   same `telemetry_bridge.build_scene_snapshot()`.

To swap to Godot:

1. Install Godot 4.x.
2. Write a GDScript client that reads
   `http://127.0.0.1:8765/api/native_cockpit/state`.

## What V2 does NOT package

- No Qt3D meshes (would need apt install)
- No GPU shaders
- No installer wizard
- No code signing
