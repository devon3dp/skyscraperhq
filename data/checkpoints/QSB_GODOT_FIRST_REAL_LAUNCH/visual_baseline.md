# QSB Godot First Real Launch — Visual Baseline

- Window title: QSB Godot Native Cockpit — Real 3D Skyscraper
- 53 floor slabs stacked vertically
- 9 lift cylinders (back-right column) + 9 lift cars
- OpenClaw purple emissive sphere with label
- Penthouse crown box at top + "QSB PROFESSIONAL 3D SKYSCRAPER" billboard
- HUD top-left: workforce 2,191 · lifts 9 · selected floor pill · safety locks
- Keyboard nav: UP/DOWN floor, 1=F41, 2=F42, 3=F55, mouse wheel zoom
- Auto-orbit (orbit_angle += delta * 0.08)
- Renderer: gl_compatibility (forced because GPU is software-rendered llvmpipe)

## Known limitations
- Prototype-looking flat materials
- No mouse-click floor picking
- No control bar with original dashboard buttons
- No in-app Kernel chat
- No event ticker
- No floor interiors yet
- Auto-orbit can't be paused
