# QSB Native Cockpit V2

Standalone PyQt5 desktop app for the QSB Skyscraper. Runs as a native
window — no Chrome, no WebGL, no browser dependency.

## Run

```
./scripts/qsb_native_cockpit_run.sh
```

The browser dashboard at `http://127.0.0.1:8765/?v=next3d&floor=55`
remains as fallback.

## What you see

- 53-floor tower (depth-cued isometric, painted by our own scene engine)
- Floor color = department category, opacity = workforce density
- 9 lift shafts + 9 lift cars (green = moving, blue = idle)
- OpenClaw orb at its supervisor floor
- Selected-floor yellow halo + interior inspector card on the right
- HUD on the left: verified totals, OpenClaw, paper PnL, Commerce Wing,
  Penthouse gauges, Hardware — plus safety lock banner
- Click any floor slab to inspect it

## Architecture

```
native_cockpit/
  qt/
    main.py                  — PyQt5 entry, scene engine, HUD, inspector
    telemetry_bridge.py      — reads local QSB registries (no secrets)
    requirements.txt
  scenes/                    — future Qt3D/QML scene files
  assets/                    — future icons + materials
  scripts/                   — local helper scripts
  telemetry/                 — local cached telemetry snapshots
  logs/                      — runtime logs
  build/                     — PyInstaller output
  docs/                      — engine + architecture notes
```

## Engine choice (V2)

PyQt5 5.15 + QGraphicsView. Decision rationale in
`data/registries/qsb_native_graphics_engine_decision_v2.json`.

- Godot, Panda3D, PySide6, PyQt6 not usable on this machine right now.
- PyQt5 IS installed and stable.
- QGraphicsView gives a real hardware-accelerated 2.5D scene graph.

## Upgrade to true 3D (future)

```bash
sudo apt install python3-pyqt5.qt3d
# or
pip install panda3d
```

The scene engine is engine-agnostic at the data layer — the same
telemetry bridge can drive Qt3D `QEntity`/`QMesh`, Panda3D, or Godot.

## Safety

- No real-money trading
- No listings publishing
- No payments
- No live API calls
- No secrets in logs or registries
- All commerce floors in `safe / manual-approval` mode
