"""QSB Panda3D Fallback Cockpit — real 3D, used only if Godot blocked.

Renders the 53-floor skyscraper with real Panda3D primitives (CardMaker,
LineSegs, NodePath transforms), orbit camera, and HUD text. Reads QSB
state via the local telemetry bridge.
"""

import sys, math, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from panda3d.core import (
        Vec3, Vec4, Point3, CardMaker, LineSegs, TextNode,
        AmbientLight, DirectionalLight, NodePath, WindowProperties,
        LVector3, BitMask32, CollisionRay, CollisionNode, CollisionTraverser,
        CollisionHandlerQueue, GeomNode,
    )
    from direct.showbase.ShowBase import ShowBase
    from direct.task import Task
except Exception as exc:
    print("ERROR: Panda3D not importable: %s" % exc)
    print("Activate venv: source native_cockpit/.venv_3d/bin/activate")
    sys.exit(2)

import telemetry_bridge as tb

FLOOR_H = 1.0
FLOOR_GAP = 0.06
FLOOR_W = 12.0
FLOOR_D = 8.0


def floor_y(n):
    return n * (FLOOR_H + FLOOR_GAP) + FLOOR_H / 2


def category_color(secondary, primary):
    s = (secondary or "").lower()
    if "kernel" in s or "penthouse" in s: return (1.0, 0.85, 0.40, 1)
    if "tower command" in s: return (0.45, 0.70, 1.0, 1)
    if "etsy" in s or "binance" in s: return (1.0, 0.78, 0.30, 1)
    if "stocks" in s or "shopify" in s: return (0.40, 1.0, 0.55, 1)
    if "oanda" in s: return (0.36, 0.85, 1.0, 1)
    if "compliance" in s or "guardian" in s or "risk" in s: return (1.0, 0.40, 0.55, 1)
    if "hardware" in s: return (0.75, 0.85, 0.95, 1)
    if "audit" in s or "ledger" in s: return (1.0, 0.78, 0.45, 1)
    if "research" in s or "strategy" in s: return (0.85, 0.65, 1.0, 1)
    if "training" in s or "classroom" in s: return (1.0, 0.85, 0.40, 1)
    if "rest" in s or "recreation" in s: return (0.70, 0.70, 0.85, 1)
    if "security" in s: return (1.0, 0.50, 0.60, 1)
    return (0.55, 0.65, 0.80, 1)


def make_box(parent, w, h, d, x, y, z, color):
    """Build a six-sided cuboid out of CardMaker cards."""
    cm = CardMaker("box_side")
    cm.setFrame(-w/2, w/2, -h/2, h/2)
    node = parent.attachNewNode("box_%.2f_%.2f" % (y, z))
    # Front (z+)
    front = node.attachNewNode(cm.generate())
    front.setPos(0, d/2, 0)
    front.setH(180)
    # Back
    back = node.attachNewNode(cm.generate())
    back.setPos(0, -d/2, 0)
    # Top
    cm.setFrame(-w/2, w/2, -d/2, d/2)
    top = node.attachNewNode(cm.generate())
    top.setPos(0, 0, h/2); top.setP(-90)
    bot = node.attachNewNode(cm.generate())
    bot.setPos(0, 0, -h/2); bot.setP(90)
    # Sides
    cm.setFrame(-d/2, d/2, -h/2, h/2)
    left = node.attachNewNode(cm.generate())
    left.setPos(-w/2, 0, 0); left.setH(-90)
    right = node.attachNewNode(cm.generate())
    right.setPos(w/2, 0, 0); right.setH(90)
    node.setPos(x, y, z)
    node.setColor(*color)
    node.setTwoSided(True)
    return node


class QSBCockpit(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        props = WindowProperties()
        props.setTitle("QSB Panda3D Fallback Cockpit · Real 3D Skyscraper")
        props.setSize(1500, 880)
        self.win.requestProperties(props)
        self.setBackgroundColor(0.012, 0.025, 0.05, 1)
        self.disableMouse()  # we'll do our own orbit

        # Lights
        amb = AmbientLight("amb")
        amb.setColor((0.40, 0.50, 0.75, 1))
        amb_np = self.render.attachNewNode(amb)
        self.render.setLight(amb_np)
        sun = DirectionalLight("sun")
        sun.setColor((1.0, 0.95, 0.85, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-40, -60, 0)
        self.render.setLight(sun_np)

        # Telemetry
        self.snap = tb.build_scene_snapshot()

        # Build scene
        self._build_tower()
        self._build_lifts()
        self._build_openclaw()

        # Camera state (orbit)
        self.cam_target = Vec3(0, 18, 0)
        self.cam_radius = 80.0
        self.cam_yaw = math.pi * 1.45
        self.cam_pitch = 0.40
        self._apply_camera()

        # Input
        self._dragging = False
        self.accept("mouse2", self._begin_drag)
        self.accept("mouse2-up", self._end_drag)
        self.accept("mouse3", self._begin_drag)
        self.accept("mouse3-up", self._end_drag)
        self.accept("wheel_up", self._zoom_in)
        self.accept("wheel_down", self._zoom_out)
        self.accept("r", self._reset_camera)
        self.accept("escape", sys.exit)

        # HUD
        self._build_hud()

        # Tasks
        self.taskMgr.add(self._poll_input, "qsb-input")
        self.taskMgr.add(self._auto_refresh, "qsb-refresh")
        self._last_refresh = time.time()

    def _build_tower(self):
        # Ground
        cm = CardMaker("ground")
        cm.setFrame(-60, 60, -60, 60)
        g = self.render.attachNewNode(cm.generate())
        g.setP(-90); g.setColor(0.05, 0.10, 0.16, 1)

        for f in self.snap.get("floors", []):
            n = int(f.get("floor", 0))
            if n < 1 or n > 54: continue
            col = category_color(f.get("secondary"), f.get("primary"))
            w = FLOOR_W if n < 53 else 9.0
            d = FLOOR_D if n < 53 else 6.0
            total = f.get("total_workers", 0)
            boost = max(0.25, min(0.95, total / 280.0))
            tinted = (col[0] * boost, col[1] * boost, col[2] * boost, 1)
            make_box(self.render, w, FLOOR_H - 0.06, d, 0, 0, floor_y(n), tinted)
            # Label
            tn = TextNode("F%d" % n)
            tn.setText("F%-2d %s" % (n, str(f.get("secondary", ""))[:32]))
            tn.setTextColor(0.85, 0.92, 1.0, 1)
            tnp = self.render.attachNewNode(tn)
            tnp.setScale(0.18)
            tnp.setPos(-w * 0.55 - 4.5, -d * 0.5 - 0.5, floor_y(n))
            tnp.setBillboardPointEye()

        # Penthouse roof + crown
        make_box(self.render, 9, 0.5, 6, 0, 0, floor_y(54) + 0.30,
                 (0.40, 0.32, 0.10, 1))
        # Crown — small box on top
        make_box(self.render, 1.4, 2.6, 1.4, 0, 0, floor_y(54) + 2.3,
                 (1.0, 0.82, 0.35, 1))

    def _build_lifts(self):
        self.lift_cars = []
        positions = [
            (-FLOOR_W/2 - 0.9, -FLOOR_D/2 - 0.5),
            (-FLOOR_W/2 - 0.9, -FLOOR_D/4),
            (-FLOOR_W/2 - 0.9,  FLOOR_D/4),
            (-FLOOR_W/2 - 0.9,  FLOOR_D/2 + 0.5),
            ( FLOOR_W/2 + 0.9, -FLOOR_D/2 - 0.5),
            ( FLOOR_W/2 + 0.9, -FLOOR_D/4),
            ( FLOOR_W/2 + 0.9,  FLOOR_D/4),
            ( FLOOR_W/2 + 0.9,  FLOOR_D/2 + 0.5),
            (0, -FLOOR_D/2 - 1.4),
        ]
        lifts = self.snap.get("lifts", [])
        for i, (x, y) in enumerate(positions):
            # Shaft as a vertical thin box
            make_box(self.render, 0.30, 56.0, 0.30, x, y, 28,
                     (0.18, 0.30, 0.55, 1))
            cf = 0
            if i < len(lifts) and lifts[i].get("current_floor") is not None:
                cf = int(lifts[i]["current_floor"])
            car = make_box(self.render, 0.55, 0.55, 0.55, x, y, floor_y(cf),
                            (0.40, 0.85, 1.0, 1))
            self.lift_cars.append((car, cf))

    def _build_openclaw(self):
        cf = (self.snap.get("openclaw", {}) or {}).get("current_floor") or 30
        self.openclaw_orb = make_box(self.render, 1.2, 1.2, 1.2,
                                       8.0, 0, floor_y(int(cf)),
                                       (0.85, 0.40, 1.0, 1))

    def _build_hud(self):
        from direct.gui.OnscreenText import OnscreenText
        v = self.snap.get("verified", {})
        OnscreenText(text="QSB PANDA3D FALLBACK COCKPIT · REAL 3D",
                      pos=(-1.3, 0.93), scale=0.05, fg=(0.2, 1.0, 0.78, 1),
                      align=TextNode.ALeft, mayChange=False)
        OnscreenText(text="canonical %s · new V2 %s · TOTAL %s" %
                          (v.get("canonical_workers_before", "—"),
                            v.get("new_v2_workers", "—"),
                            v.get("verified_total_workers", "—")),
                      pos=(-1.3, 0.86), scale=0.04, fg=(0.80, 0.90, 1.0, 1),
                      align=TextNode.ALeft)
        OpenClaw_floor = (self.snap.get("openclaw") or {}).get("current_floor")
        OnscreenText(text="OpenClaw F%s · tickets %s" %
                          (OpenClaw_floor,
                            (self.snap.get("openclaw") or {}).get("ticket_count", 0)),
                      pos=(-1.3, 0.80), scale=0.04, fg=(0.85, 0.62, 1.0, 1),
                      align=TextNode.ALeft)
        OnscreenText(text="SAFETY · real-money OFF · listings OFF · payments OFF · openclaw exec OFF",
                      pos=(-1.3, -0.92), scale=0.04, fg=(1.0, 0.54, 0.62, 1),
                      align=TextNode.ALeft)
        OnscreenText(text="Right-drag to rotate · wheel to zoom · R to reset · ESC to quit",
                      pos=(-1.3, -0.97), scale=0.035, fg=(0.62, 0.74, 0.92, 1),
                      align=TextNode.ALeft)

    def _begin_drag(self):
        self._dragging = True
        if self.mouseWatcherNode.hasMouse():
            self._last_mouse = (self.mouseWatcherNode.getMouseX(),
                                  self.mouseWatcherNode.getMouseY())
        else:
            self._last_mouse = (0, 0)

    def _end_drag(self):
        self._dragging = False

    def _zoom_in(self):
        self.cam_radius = max(22.0, self.cam_radius * 0.92)
        self._apply_camera()

    def _zoom_out(self):
        self.cam_radius = min(180.0, self.cam_radius * 1.08)
        self._apply_camera()

    def _reset_camera(self):
        self.cam_target = Vec3(0, 18, 0)
        self.cam_radius = 80.0
        self.cam_yaw = math.pi * 1.45
        self.cam_pitch = 0.40
        self._apply_camera()

    def _apply_camera(self):
        x = self.cam_radius * math.cos(self.cam_pitch) * math.sin(self.cam_yaw)
        y = self.cam_radius * math.cos(self.cam_pitch) * math.cos(self.cam_yaw)
        z = self.cam_radius * math.sin(self.cam_pitch) + self.cam_target.z
        self.camera.setPos(x, y, z)
        self.camera.lookAt(self.cam_target)

    def _poll_input(self, task):
        if self._dragging and self.mouseWatcherNode.hasMouse():
            mx = self.mouseWatcherNode.getMouseX()
            my = self.mouseWatcherNode.getMouseY()
            dx = mx - self._last_mouse[0]
            dy = my - self._last_mouse[1]
            self.cam_yaw -= dx * 2.0
            self.cam_pitch = max(0.10, min(math.pi * 0.45, self.cam_pitch + dy * 1.5))
            self._last_mouse = (mx, my)
            self._apply_camera()
        return Task.cont

    def _auto_refresh(self, task):
        if time.time() - self._last_refresh > 5.0:
            self.snap = tb.build_scene_snapshot()
            self._last_refresh = time.time()
            # Update lift car positions
            lifts = self.snap.get("lifts", [])
            for i, (car, _) in enumerate(self.lift_cars):
                if i < len(lifts) and lifts[i].get("current_floor") is not None:
                    cf = int(lifts[i]["current_floor"])
                    car.setZ(floor_y(cf))
            # Update OpenClaw
            cf = (self.snap.get("openclaw") or {}).get("current_floor")
            if cf is not None:
                self.openclaw_orb.setZ(floor_y(int(cf)))
        return Task.cont


def main():
    app = QSBCockpit()
    app.run()


if __name__ == "__main__":
    main()
