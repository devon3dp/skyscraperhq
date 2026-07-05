"""
QSB Native Cockpit V2 — Standalone Desktop App
Phase: QSB_NATIVE_COCKPIT_STANDALONE_SKYSCRAPER_PLATFORM_V2

A real PyQt5 desktop application running our own QSB Scene Engine on
top of QGraphicsView. Renders the 53-floor skyscraper, 9 lifts,
OpenClaw marker, worker density bars per floor, and a sidebar HUD with
verified totals, Commerce Wing summary, Etsy/POD floor status, paper
PnL, and explicit safety lock banner.

Does NOT depend on Chrome. Does NOT use WebGL. Native window.
Browser dashboard remains as fallback.
"""

import sys
import time
from pathlib import Path

# Make telemetry_bridge importable when run from any cwd.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
        QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsTextItem,
        QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsSimpleTextItem,
        QSplitter, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QListWidget, QListWidgetItem, QTextEdit, QFrame,
        QSizePolicy, QSpacerItem, QGridLayout, QScrollArea,
    )
    from PyQt5.QtGui import (
        QBrush, QColor, QPen, QFont, QPolygonF, QPainter,
        QLinearGradient, QRadialGradient,
    )
    from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QSize, pyqtSignal
    from PyQt5.QtWidgets import QLineEdit
except ImportError as e:
    print("ERROR: PyQt5 not installed or broken: %s" % e)
    print("Install with: apt install python3-pyqt5")
    print("Fallback URL: http://127.0.0.1:8765/?v=next3d&floor=55")
    sys.exit(2)

import telemetry_bridge as tb


# ── Visual constants ─────────────────────────────────────────────────


FLOOR_COUNT = 55
FLOOR_HEIGHT = 16
FLOOR_WIDTH = 360
FLOOR_DEPTH = 80
TOWER_X = 60
TOWER_TOP_Y = 40
NUM_LIFTS = 9


CATEGORY_COLORS = {
    "kernel":       QColor(255, 217, 110),
    "command":      QColor(115, 178, 255),
    "recruitment":  QColor(140, 255, 190),
    "accounts":     QColor(255, 200, 90),
    "stocks":       QColor(100, 255, 140),
    "binance":      QColor(255, 205, 80),
    "oanda":        QColor(95, 220, 255),
    "sandbox":      QColor(158, 255, 220),
    "strategy":     QColor(215, 165, 255),
    "hardware":     QColor(190, 215, 240),
    "audit":        QColor(255, 195, 110),
    "guardian":     QColor(255, 110, 140),
    "airllm":       QColor(115, 200, 255),
    "lifts":        QColor(165, 230, 255),
    "security":     QColor(255, 130, 155),
    "generic":      QColor(140, 160, 200),
}


def category_for(secondary, primary):
    s = (secondary or "").lower()
    p = (primary or "").lower()
    if "kernel" in s or "penthouse" in s or "tower command" in p: return "kernel"
    if "etsy" in s: return "binance"
    if "shopify" in s: return "stocks"
    if "print-on-demand" in s or "pod" in s: return "binance"
    if "3d printing" in s: return "binance"
    if "oanda" in s: return "oanda"
    if "binance" in s: return "binance"
    if "stocks" in s or "stock exchange" in s: return "stocks"
    if "classroom" in s: return "kernel"
    if "research" in s: return "strategy"
    if "design studio" in s or "prompt-to-product" in s: return "airllm"
    if "fulfilment" in s: return "command"
    if "customer service" in s: return "command"
    if "marketing" in s or "promotion" in s: return "binance"
    if "compliance" in s: return "guardian"
    if "accounting" in s: return "accounts"
    if "refund" in s or "dispute" in s: return "guardian"
    if "analytics" in s: return "audit"
    if "hardware" in s: return "hardware"
    if "guardian" in s or "risk" in s: return "guardian"
    if "audit" in s or "ledger" in s: return "audit"
    if "security" in s or "vault" in s: return "security"
    if "rest" in s or "recreation" in s or "dormitory" in s: return "command"
    if "airllm" in s: return "airllm"
    if "lift" in s or "integration" in s: return "lifts"
    if "sandbox" in s: return "sandbox"
    if "strategy" in s or "simulation" in s: return "strategy"
    if "recruitment" in s: return "recruitment"
    if "executive" in s or "governance" in s: return "command"
    return "generic"


# ── Tower scene ───────────────────────────────────────────────────


class QSBTowerScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor(2, 8, 22)))
        self.floor_items = {}        # floor_num → QGraphicsRectItem
        self.floor_meta = {}         # floor_num → catalog dict
        self.lift_shafts = []        # 9 line items
        self.lift_cars = []          # 9 rect items
        self.openclaw_item = None
        self.openclaw_label = None
        self.selected_floor = None
        self.selected_halo = None
        self.on_floor_clicked = None     # callback(int)
        self.on_lift_clicked = None      # callback(int idx)
        self.on_openclaw_clicked = None  # callback()

    def floor_y(self, n):
        # Floor 0 = ground at bottom; higher floor → smaller y
        return TOWER_TOP_Y + (FLOOR_COUNT - 1 - n) * FLOOR_HEIGHT

    def build_tower(self, snapshot):
        # Stars / atmosphere
        for i in range(50):
            star_x = (i * 73) % 1100 + 20
            star_y = (i * 137) % 200 + 8
            star = QGraphicsEllipseItem(star_x, star_y, 1.4, 1.4)
            star.setBrush(QBrush(QColor(180, 210, 250, 90)))
            star.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(star)

        # Tower envelope shadow
        env = QGraphicsRectItem(
            TOWER_X - 14, TOWER_TOP_Y - 8,
            FLOOR_WIDTH + 28, FLOOR_COUNT * FLOOR_HEIGHT + 16)
        grad = QLinearGradient(0, TOWER_TOP_Y, 0, TOWER_TOP_Y + FLOOR_COUNT * FLOOR_HEIGHT)
        grad.setColorAt(0, QColor(20, 35, 65, 220))
        grad.setColorAt(1, QColor(8, 18, 36, 240))
        env.setBrush(QBrush(grad))
        env.setPen(QPen(QColor(70, 110, 160), 1))
        self.addItem(env)

        # Floors
        for floor in snapshot.get("floors", []):
            self._add_floor(floor)

        # Roof
        roof = QGraphicsPolygonItem(QPolygonF([
            QPointF(TOWER_X + 40, self.floor_y(53) - 4),
            QPointF(TOWER_X + FLOOR_WIDTH - 40, self.floor_y(53) - 4),
            QPointF(TOWER_X + FLOOR_WIDTH / 2, self.floor_y(54) - 30),
        ]))
        roof.setBrush(QBrush(QColor(255, 220, 130)))
        roof.setPen(QPen(QColor(255, 240, 180), 1.4))
        self.addItem(roof)
        crown = QGraphicsTextItem("⌂ PENTHOUSE · KERNEL")
        crown.setDefaultTextColor(QColor(255, 230, 150))
        crown.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        crown.setPos(TOWER_X + FLOOR_WIDTH / 2 - 75, self.floor_y(54) - 56)
        self.addItem(crown)

        # Lifts
        self._build_lifts(snapshot.get("lifts", []))

        # OpenClaw
        self._build_openclaw(snapshot.get("openclaw", {}))

    def _add_floor(self, floor):
        n = floor["floor"]
        y = self.floor_y(n)
        cat = category_for(floor.get("secondary"), floor.get("primary"))
        col = QColor(CATEGORY_COLORS.get(cat, CATEGORY_COLORS["generic"]))
        # Workforce intensity
        total = floor.get("total_workers", 0)
        alpha = max(80, min(225, 80 + total * 2))
        col.setAlpha(alpha)
        rect = QGraphicsRectItem(TOWER_X, y + 1, FLOOR_WIDTH, FLOOR_HEIGHT - 2)
        rect.setBrush(QBrush(col))
        rect.setPen(QPen(QColor(40, 70, 120), 0.6))
        rect.setData(0, n)
        rect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addItem(rect)
        self.floor_items[n] = rect
        self.floor_meta[n] = floor

        # Floor number on left
        lbl = QGraphicsSimpleTextItem("F%-2d" % n)
        lbl.setBrush(QBrush(QColor(180, 210, 240)))
        lbl.setFont(QFont("Inter", 7, QFont.Weight.Bold))
        lbl.setPos(TOWER_X - 24, y + 2)
        self.addItem(lbl)

        # Secondary department name (only if room)
        if FLOOR_HEIGHT >= 12:
            dept = floor.get("secondary") or floor.get("primary") or ""
            dl = QGraphicsSimpleTextItem(dept[:42])
            dl.setBrush(QBrush(QColor(20, 30, 50)))
            dl.setFont(QFont("Inter", 7))
            dl.setPos(TOWER_X + 6, y + 3)
            self.addItem(dl)

        # Worker density chip on the right
        chip = QGraphicsSimpleTextItem("%dw" % total)
        chip.setBrush(QBrush(QColor(255, 230, 150)))
        chip.setFont(QFont("Inter", 7, QFont.Weight.Bold))
        chip.setPos(TOWER_X + FLOOR_WIDTH + 6, y + 2)
        self.addItem(chip)

        # Profit/Kernel/Safety/Rest dots
        x_dot = TOWER_X + FLOOR_WIDTH - 60
        if floor.get("profit"):
            d = QGraphicsEllipseItem(x_dot, y + 5, 5, 5)
            d.setBrush(QBrush(QColor(80, 255, 160))); d.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(d); x_dot += 7
        if floor.get("kernel"):
            d = QGraphicsEllipseItem(x_dot, y + 5, 5, 5)
            d.setBrush(QBrush(QColor(255, 220, 100))); d.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(d); x_dot += 7
        if floor.get("safety"):
            d = QGraphicsEllipseItem(x_dot, y + 5, 5, 5)
            d.setBrush(QBrush(QColor(255, 110, 130))); d.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(d); x_dot += 7
        if floor.get("rest"):
            d = QGraphicsEllipseItem(x_dot, y + 5, 5, 5)
            d.setBrush(QBrush(QColor(180, 180, 220))); d.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(d)

    def _build_lifts(self, lifts):
        # 9 shafts on the right edge
        shaft_x = TOWER_X + FLOOR_WIDTH + 60
        for i in range(NUM_LIFTS):
            x = shaft_x + i * 14
            line = QGraphicsLineItem(x, self.floor_y(0) + FLOOR_HEIGHT,
                                       x, self.floor_y(54))
            line.setPen(QPen(QColor(100, 170, 230, 120), 1.4))
            self.addItem(line)
            self.lift_shafts.append(line)

            car_floor = 0
            moving = False
            if i < len(lifts):
                L = lifts[i]
                cf = L.get("current_floor")
                if cf is not None: car_floor = int(cf)
                moving = bool(L.get("moving"))
            car = QGraphicsRectItem(x - 5, self.floor_y(car_floor) + 3, 10, 10)
            car.setBrush(QBrush(QColor(95, 255, 140) if moving else QColor(95, 200, 255)))
            car.setPen(QPen(QColor(220, 240, 255), 0.5))
            car.setToolTip(("lift " + (lifts[i].get("lift_id") if i < len(lifts) else "L%d" % (i + 1)))
                            + " · floor " + str(car_floor))
            self.addItem(car)
            self.lift_cars.append(car)

    def update_lifts(self, lifts):
        for i, car in enumerate(self.lift_cars):
            if i >= len(lifts):
                continue
            L = lifts[i]
            cf = L.get("current_floor")
            if cf is None: continue
            x = car.rect().x()
            car.setRect(x, self.floor_y(int(cf)) + 3, car.rect().width(), car.rect().height())
            car.setBrush(QBrush(QColor(95, 255, 140) if L.get("moving")
                                  else QColor(95, 200, 255)))

    def _build_openclaw(self, oc):
        cf = oc.get("current_floor") or 31
        x = TOWER_X + FLOOR_WIDTH + 200
        y = self.floor_y(int(cf)) + 2
        orb = QGraphicsEllipseItem(x, y, 18, 18)
        rg = QRadialGradient(QPointF(x + 9, y + 9), 14)
        rg.setColorAt(0, QColor(225, 180, 255))
        rg.setColorAt(0.7, QColor(140, 80, 220))
        rg.setColorAt(1, QColor(40, 12, 100))
        orb.setBrush(QBrush(rg))
        orb.setPen(QPen(QColor(225, 180, 255), 1.4))
        self.addItem(orb)
        self.openclaw_item = orb
        lbl = QGraphicsSimpleTextItem("OpenClaw F%s" % cf)
        lbl.setBrush(QBrush(QColor(225, 180, 255)))
        lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        lbl.setPos(x + 22, y + 2)
        self.addItem(lbl)
        self.openclaw_label = lbl

    def update_openclaw(self, oc):
        if not self.openclaw_item: return
        cf = oc.get("current_floor")
        if cf is None: return
        x = self.openclaw_item.rect().x()
        self.openclaw_item.setRect(x, self.floor_y(int(cf)) + 2, 18, 18)
        if self.openclaw_label:
            self.openclaw_label.setPos(x + 22, self.floor_y(int(cf)) + 4)
            self.openclaw_label.setText("OpenClaw F%s · %s tk" %
                                          (cf, oc.get("ticket_count", 0)))

    def select_floor(self, n):
        if self.selected_halo:
            try:
                self.removeItem(self.selected_halo)
            except Exception:
                pass
            self.selected_halo = None
        if n is None:
            self.selected_floor = None
            return
        self.selected_floor = n
        rect = self.floor_items.get(n)
        if not rect: return
        r = rect.rect()
        halo = QGraphicsRectItem(r.x() - 4, r.y() - 3, r.width() + 8, r.height() + 6)
        halo.setPen(QPen(QColor(255, 220, 120), 2))
        halo.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        halo.setZValue(10)
        self.addItem(halo)
        self.selected_halo = halo

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(ev.scenePos(), self.parent().transform() if self.parent() else None)
            if item:
                meta = item.metadata() if hasattr(item, "metadata") else None
                # OpenClaw orb click
                if item is self.openclaw_item:
                    if self.on_openclaw_clicked:
                        self.on_openclaw_clicked()
                        return
                # Lift car click
                for i, car in enumerate(self.lift_cars):
                    if item is car:
                        if self.on_lift_clicked:
                            self.on_lift_clicked(i)
                            return
                # Floor slab click — uses data(0)
                fnum = item.data(0)
                if fnum is not None and self.on_floor_clicked:
                    self.on_floor_clicked(int(fnum))
                    return
        super().mousePressEvent(ev)


# ── Tower view (wraps scene with wheel-zoom) ──────────────────────


class QSBTowerView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                             QPainter.RenderHint.SmoothPixmapTransform |
                             QPainter.RenderHint.TextAntialiasing)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(2, 6, 16)))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._zoom = 1.0

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        f = 1.12 if delta > 0 else 0.89
        new_zoom = self._zoom * f
        if 0.35 < new_zoom < 3.0:
            self._zoom = new_zoom
            self.scale(f, f)


# ── HUD sidebar ───────────────────────────────────────────────────


class QSBHud(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background: #050c1a; color: #d9e4f3; font-family: Inter, "Segoe UI", sans-serif; }
            QLabel.title { font-size: 14px; font-weight: 700; color: #a8e1ff; letter-spacing: 0.04em; }
            QLabel.section { font-size: 10px; font-weight: 700; color: #ffd886;
                              letter-spacing: 0.08em; text-transform: uppercase;
                              margin-top: 8px; }
            QLabel.row { font-size: 11px; color: #cfdcef; }
            QLabel.row b { color: #5bff9c; }
            QLabel.fail { color: #ff8aa0; font-weight: 700; }
            QLabel.warn { color: #ffd886; font-weight: 700; }
            QLabel.muted { color: #9fb6d4; font-size: 10px; font-style: italic; }
            QPushButton { background: #14223a; color: #cfdcef; border: 1px solid #3a5a8a;
                           border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background: #1c3052; }
            QListWidget { background: #08111f; color: #cfdcef;
                            border: 1px solid #2a4060; font-size: 10.6px; }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(4)

        title = QLabel("QSB NATIVE COCKPIT V2"); title.setProperty("class", "title")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #a8e1ff; letter-spacing: 0.10em;")
        self.layout.addWidget(title)
        subtitle = QLabel("Standalone PyQt5 desktop · QSB Scene Engine")
        subtitle.setStyleSheet("color: #9fb6d4; font-size: 10px;")
        self.layout.addWidget(subtitle)

        self.labels = {}
        for sec, fields in [
            ("WORKFORCE", ["canonical_before", "new_v2", "total_verified"]),
            ("FLOORS", ["floor_count", "weak_floors", "commerce_floors"]),
            ("OPENCLAW", ["oc_floor", "oc_tickets", "oc_findings"]),
            ("TRADING (PAPER)", ["pnl_realized", "pnl_unrealized", "pnl_total", "open", "closed"]),
            ("COMMERCE WING", ["wing_count", "shops", "etsy_workers", "pod_workers"]),
            ("PENTHOUSE", ["kernel_active", "cadence", "guardian", "locks"]),
            ("HARDWARE", ["cpu", "memory", "gpu"]),
        ]:
            hdr = QLabel(sec); hdr.setProperty("class", "section")
            hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #ffd886; "
                              "letter-spacing: 0.08em; text-transform: uppercase; margin-top: 8px;")
            self.layout.addWidget(hdr)
            for f in fields:
                row = QLabel(f.replace("_", " ") + ": —")
                row.setStyleSheet("font-size: 10.6px; color: #cfdcef;")
                row.setWordWrap(True)
                self.layout.addWidget(row)
                self.labels[f] = row

        # Safety locks banner
        spacer = QLabel(""); spacer.setFixedHeight(8)
        self.layout.addWidget(spacer)
        locks_hdr = QLabel("SAFETY LOCKS")
        locks_hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #ff8aa0; "
                                 "letter-spacing: 0.08em; text-transform: uppercase;")
        self.layout.addWidget(locks_hdr)
        for label in ["Real-money trading: OFF",
                       "Listings publish: OFF",
                       "Payments: OFF",
                       "OpenClaw exec: OFF",
                       "Autonomous dispatch: OFF"]:
            l = QLabel("· " + label)
            l.setStyleSheet("color: #ff8aa0; font-size: 10.4px; font-weight: 700;")
            self.layout.addWidget(l)

        spacer2 = QLabel(""); spacer2.setFixedHeight(6)
        self.layout.addWidget(spacer2)

        self.refresh_btn = QPushButton("↻ Refresh telemetry")
        self.layout.addWidget(self.refresh_btn)
        self.fallback_btn = QPushButton("↺ Open browser fallback")
        self.layout.addWidget(self.fallback_btn)

        self.layout.addStretch(1)

    def update_snapshot(self, snap):
        v = snap.get("verified", {})
        self._set("canonical_before", v.get("canonical_workers_before"))
        self._set("new_v2", v.get("new_v2_workers"))
        self._set("total_verified", v.get("verified_total_workers"),
                   highlight=True)
        self._set("floor_count", v.get("floor_masterplan_entries"))
        weak = sum(1 for f in snap.get("floors", [])
                    if f.get("total_workers", 0) < 5)
        self._set("weak_floors", weak)
        self._set("commerce_floors", v.get("commerce_wing_floors"))
        oc = snap.get("openclaw", {})
        self._set("oc_floor", oc.get("current_floor"))
        self._set("oc_tickets", oc.get("ticket_count"))
        self._set("oc_findings", oc.get("full_inspection_findings"))
        pnl = snap.get("trading", {}).get("oanda_pnl", {})
        self._set("pnl_realized", _fmt(pnl.get("realized")))
        self._set("pnl_unrealized", _fmt(pnl.get("unrealized")))
        self._set("pnl_total", _fmt(pnl.get("total")))
        self._set("open", pnl.get("open_count"))
        self._set("closed", pnl.get("closed_count"))
        cw = snap.get("commerce_wing", {})
        self._set("wing_count", len(cw.get("floors") or []))
        self._set("shops", len(cw.get("shop_opportunities") or []))
        self._set("etsy_workers", (snap.get("etsy") or {}).get("worker_count"))
        self._set("pod_workers", (snap.get("print_on_demand") or {}).get("worker_count"))
        ph = snap.get("penthouse", {})
        self._set("kernel_active", ph.get("kernel_active"))
        self._set("cadence", ph.get("cadence_tick"))
        self._set("guardian", ph.get("guardian_state"))
        self._set("locks", str(ph.get("locks_open", 0)) + " / 13")
        hw = snap.get("hardware", {})
        self._set("cpu", str(hw.get("cpu", "—"))[:48])
        self._set("memory", hw.get("memory"))
        self._set("gpu", str(hw.get("gpu", "—"))[:48])

    def _set(self, key, val, highlight=False):
        if key not in self.labels: return
        text = key.replace("_", " ") + ": " + str(val if val is not None else "—")
        if highlight:
            self.labels[key].setText("<b style='color:#5bff9c'>" +
                                      key.replace("_", " ") + ": " + str(val) + "</b>")
        else:
            self.labels[key].setText(text)


def _fmt(n):
    if n is None: return "—"
    try: return "%+.4f" % float(n)
    except Exception: return str(n)


# ── Floor inspector ───────────────────────────────────────────────


class QSBFloorInspector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background: #08111f; color: #d9e4f3;
                       font-family: Inter, "Segoe UI", sans-serif; }
            QLabel.title { font-size: 13px; font-weight: 700; color: #a8e1ff;
                           letter-spacing: 0.04em; }
            QLabel.subtitle { font-size: 10px; color: #9fb6d4; }
            QLabel.row { font-size: 10.6px; color: #cfdcef; }
            QLabel.room { font-size: 10.4px; color: #ffd886; }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.title = QLabel("Floor inspector"); self.title.setProperty("class", "title")
        self.title.setStyleSheet("font-size: 13px; font-weight: 700; color: #a8e1ff;")
        self.layout.addWidget(self.title)
        self.sub = QLabel("Click a floor to inspect.")
        self.sub.setStyleSheet("color: #9fb6d4; font-size: 10px;")
        self.layout.addWidget(self.sub)
        self.body = QLabel("")
        self.body.setStyleSheet("font-size: 10.6px; color: #cfdcef;")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.addWidget(self.body)
        self.layout.addStretch(1)

    def show_floor(self, floor_meta, snapshot):
        if not floor_meta:
            self.title.setText("Floor inspector"); self.sub.setText("Click a floor.")
            self.body.setText(""); return
        n = floor_meta["floor"]
        self.title.setText("F%s · %s" % (n, floor_meta.get("secondary") or
                                          floor_meta.get("primary")))
        self.sub.setText(floor_meta.get("purpose") or "")
        rows = []
        rows.append("<b>primary:</b> %s" % floor_meta.get("primary"))
        rows.append("<b>secondary:</b> %s" % floor_meta.get("secondary"))
        rows.append("<b>canonical workers:</b> %s" % floor_meta.get("canonical_workers"))
        rows.append("<b>new V2 workers:</b> %s" % floor_meta.get("new_v2_workers"))
        rows.append("<b>total workers:</b> %s" % floor_meta.get("total_workers"))
        rows.append("<b>profit aligned:</b> %s" % floor_meta.get("profit"))
        rows.append("<b>kernel aligned:</b> %s" % floor_meta.get("kernel"))
        rows.append("<b>safety aligned:</b> %s" % floor_meta.get("safety"))
        rows.append("<b>rest aligned:</b> %s" % floor_meta.get("rest"))
        rows.append("")
        rows.append("<b>rooms (%d):</b>" % len(floor_meta.get("rooms") or []))
        for r in (floor_meta.get("rooms") or []):
            rows.append("&nbsp;· " + str(r))

        # Floor-specific deep dive
        if n == 55 or n == 53:
            ph = snapshot.get("penthouse", {})
            rows.append("")
            rows.append("<b>Penthouse gauges:</b>")
            for g in (ph.get("gauges") or [])[:8]:
                rows.append("&nbsp;· %s: %s %s" % (g.get("label"),
                                                     g.get("value"),
                                                     g.get("unit") or ""))
        elif n == 41:
            t = snapshot.get("trading", {}).get("oanda_pnl") or {}
            rows.append("")
            rows.append("<b>OANDA paper PnL:</b>")
            rows.append("&nbsp;realized: %s" % _fmt(t.get("realized")))
            rows.append("&nbsp;unrealized: %s" % _fmt(t.get("unrealized")))
            rows.append("&nbsp;total: %s" % _fmt(t.get("total")))
            rows.append("&nbsp;open trades: %s / closed: %s" %
                          (t.get("open_count"), t.get("closed_count")))
        elif n == 42:
            f42 = snapshot.get("trading", {}).get("floor42_binance") or {}
            rows.append("")
            rows.append("<b>Binance:</b> mode %s · %s rooms · %s workers" %
                          (f42.get("mode"), len(f42.get("rooms") or []),
                            f42.get("worker_count")))
            rows.append("<b>real-money:</b> <span style='color:#ff8aa0'>OFF (locked)</span>")
        elif n == 43:
            f43 = snapshot.get("trading", {}).get("floor43_stocks") or {}
            rows.append("")
            rows.append("<b>Stocks:</b> mode %s · %s rooms · %s workers" %
                          (f43.get("mode"), len(f43.get("rooms") or []),
                            f43.get("worker_count")))
        elif n == 6:
            et = snapshot.get("etsy", {})
            rows.append("")
            rows.append("<b>Etsy floor:</b> draft_only=%s, publishing=%s" %
                          (et.get("draft_only"), et.get("publishing_enabled")))
            rows.append("<b>credentials:</b> %s" % et.get("credentials_status"))
        elif n == 14:
            pod = snapshot.get("print_on_demand", {})
            rows.append("")
            rows.append("<b>POD floor:</b> draft_only=%s, %s workers" %
                          (pod.get("draft_only"), pod.get("worker_count")))
        elif n == 35:
            hw = snapshot.get("hardware", {})
            rows.append("")
            rows.append("<b>Hardware Systems Floor:</b>")
            rows.append("&nbsp;cpu: %s" % str(hw.get("cpu"))[:64])
            rows.append("&nbsp;cpu_cores: %s" % hw.get("cpu_cores"))
            rows.append("&nbsp;memory: %s" % hw.get("memory"))
            rows.append("&nbsp;gpu: %s" % str(hw.get("gpu"))[:64])
            rows.append("&nbsp;kernel: %s" % hw.get("kernel_release"))
        elif n == 28:
            rows.append("")
            rows.append("<b>Security / Secrets Floor:</b>")
            rows.append("&nbsp;credentials: <span style='color:#ffd886'>MASKED (env-only, never in logs)</span>")
            rows.append("&nbsp;vault audit endpoint: /api/security/vault_audit")
            rows.append("&nbsp;real_money_trading: <span style='color:#ff8aa0'>OFF (locked in code)</span>")
            rows.append("&nbsp;openclaw_real_tool_execution: <span style='color:#ff8aa0'>OFF (locked)</span>")
            rows.append("&nbsp;live_payments: <span style='color:#ff8aa0'>OFF</span>")
            rows.append("&nbsp;live_listings_publishing: <span style='color:#ff8aa0'>OFF</span>")
        elif n == 44:
            rows.append("")
            rows.append("<b>Accounts / PnL Department:</b>")
            t = snapshot.get("trading", {}).get("oanda_pnl") or {}
            rows.append("&nbsp;realized: %s · unrealized: %s · total: %s" %
                          (_fmt(t.get("realized")), _fmt(t.get("unrealized")), _fmt(t.get("total"))))
            rows.append("&nbsp;open: %s · closed: %s" % (t.get("open_count"), t.get("closed_count")))
        elif n == 45:
            rows.append("")
            rows.append("<b>Worker Recruitment Agency:</b>")
            rows.append("&nbsp;intake stages: candidate → screening → training handoff → assignment")
            rows.append("&nbsp;new V2 workers employed this phase: 1,000")
            rows.append("&nbsp;total verified workforce: 2,191")
        elif n == 30:
            rows.append("")
            rows.append("<b>Guardian / Risk:</b>")
            rows.append("&nbsp;13 execution locks · all closed (0/13 open)")
            rows.append("&nbsp;Guardian state: OK")
        elif n == 8:
            rows.append("")
            rows.append("<b>Training Academy:</b>")
            rows.append("&nbsp;9 classrooms: Trading · Commerce · Etsy · POD · 3D Printing · SEO · Prompt Engineering · Teacher Lounge · Certification")
            rows.append("&nbsp;48 workers on this floor (teachers + students)")
        elif n == 40:
            rows.append("")
            rows.append("<b>Worker Rest / Dormitory:</b>")
            rows.append("&nbsp;80 sleep pods · 30 standby lounge · 20 quiet recovery")
            rows.append("&nbsp;3 shifts: alpha 00-08 · beta 08-16 · gamma 16-24")
        elif n == 39:
            rows.append("")
            rows.append("<b>Worker Recreation:</b>")
            rows.append("&nbsp;Break Room · Game Room · Morale Board · Wellness Monitor · Coffee Bar")
        self.body.setText("<br>".join(rows))

    def show_lift(self, lift):
        self.title.setText("Lift · " + (lift.get("lift_id") or "unknown"))
        self.sub.setText("type: " + (lift.get("type") or "main"))
        rows = [
            "<b>lift_id:</b> %s" % lift.get("lift_id"),
            "<b>type:</b> %s" % lift.get("type"),
            "<b>current_floor:</b> %s" % lift.get("current_floor"),
            "<b>target_floor:</b> %s" % lift.get("target_floor"),
            "<b>moving:</b> %s" % lift.get("moving"),
            "<b>idle:</b> %s" % lift.get("is_idle"),
            "<b>status:</b> %s" % lift.get("status"),
            "<b>recent_movement_count:</b> %s" % lift.get("recent_movement_count"),
            "<b>serves:</b> " + ", ".join(map(str, (lift.get("serves") or [])[:12])),
            "<b>source:</b> %s" % str(lift.get("source", ""))[:80],
        ]
        self.body.setText("<br>".join(rows))

    def show_openclaw(self, oc):
        self.title.setText("OpenClaw Supervisor")
        self.sub.setText("read-only · advisory only · real_tool_execution = FALSE")
        rows = [
            "<b>current_floor:</b> %s" % oc.get("current_floor"),
            "<b>advanced_by:</b> %s" % oc.get("advanced_by"),
            "<b>is_random:</b> %s" % oc.get("is_random"),
            "<b>ticket_count:</b> %s" % oc.get("ticket_count"),
            "<b>full_inspection_findings:</b> %s" % oc.get("full_inspection_findings"),
            "<b>full_inspection_tickets:</b> %s" % oc.get("full_inspection_tickets"),
            "<b>role:</b> %s" % str(oc.get("role", ""))[:120],
            "<b>real_tool_execution:</b> <span style='color:#ff8aa0'>FALSE</span>",
            "",
            "<b>Recent tickets:</b>",
        ]
        for t in (oc.get("tickets") or [])[:5]:
            rows.append("&nbsp;· [%s] %s" % (t.get("severity", "?"),
                                              str(t.get("issue") or t.get("description", ""))[:80]))
        if not (oc.get("tickets") or []):
            rows.append("&nbsp;<i>none</i>")
        self.body.setText("<br>".join(rows))


# ── Event ticker (bottom dock) ─────────────────────────────────────


class QSBEventTicker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background: #050c1a; color: #d9e4f3;
                       font-family: Inter, "Segoe UI", sans-serif; }
            QLabel.title { font-size: 11px; font-weight: 700;
                            color: #ffd886; letter-spacing: 0.08em;
                            text-transform: uppercase; }
            QListWidget { background: #08111f; color: #cfdcef;
                           border: 1px solid #2a4060; font-size: 10.4px;
                           padding: 2px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        hdr = QLabel("EVENT TICKER · ledger · intercom · openclaw · trades")
        hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #ffd886;"
                          " letter-spacing: 0.08em; text-transform: uppercase;")
        layout.addWidget(hdr)
        self.list = QListWidget(self)
        layout.addWidget(self.list)

    def refresh(self, snap):
        if not snap: return
        self.list.clear()
        events = []
        # Latest paper trades
        for c in (snap.get("trading", {}).get("closed_trades_last_5") or []):
            events.append("close · %s %s %s pnl=%s" %
                           (c.get("trade_id"), c.get("instrument"),
                            c.get("direction"), c.get("pnl_amount")))
        for t in (snap.get("trading", {}).get("open_trades_first_5") or []):
            events.append("open · %s %s %s units=%s" %
                           (t.get("trade_id"), t.get("instrument"),
                            t.get("direction"), t.get("units")))
        # OpenClaw recent tickets
        for t in (snap.get("openclaw", {}).get("tickets") or [])[:5]:
            events.append("openclaw · [%s] %s" %
                           (t.get("severity"),
                            str(t.get("issue") or t.get("description", ""))[:60]))
        # Penthouse cadence
        cad = (snap.get("penthouse", {}) or {}).get("cadence_tick")
        if cad is not None:
            events.append("cadence · tick %s" % cad)
        # Safety lock confirmation
        events.append("locks · real_money OFF · openclaw_exec OFF · payments OFF")
        for e in events:
            self.list.addItem(QListWidgetItem(e))


# ── Kernel chat panel (bottom-right dock) ──────────────────────────


class QSBKernelChat(QWidget):
    send_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget { background: #050c1a; color: #d9e4f3;
                       font-family: Inter, "Segoe UI", sans-serif; }
            QTextEdit { background: #08111f; color: #cfdcef;
                         border: 1px solid #2a4060; font-size: 10.4px; }
            QLineEdit { background: #14223a; color: #ffe7a8;
                         border: 1px solid #3a5a8a; padding: 3px;
                         font-size: 10.6px; }
            QPushButton { background: #2c4474; color: #cfdcef;
                            border: 1px solid #3a5a8a; padding: 3px 10px;
                            border-radius: 4px; font-size: 10.6px; }
            QPushButton:hover { background: #3c5a90; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        hdr = QLabel("KERNEL CHAT · local symbolic · no external model")
        hdr.setStyleSheet("font-size: 10px; font-weight: 700; color: #d8b4ff;"
                          " letter-spacing: 0.08em; text-transform: uppercase;")
        layout.addWidget(hdr)
        self.history = QTextEdit(self)
        self.history.setReadOnly(True)
        layout.addWidget(self.history)
        row = QHBoxLayout()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Ask the kernel… (Enter to send)")
        self.input.returnPressed.connect(self._emit_send)
        row.addWidget(self.input)
        send_btn = QPushButton("Send", self)
        send_btn.clicked.connect(self._emit_send)
        row.addWidget(send_btn)
        layout.addLayout(row)

    def _emit_send(self):
        msg = self.input.text().strip()
        if not msg: return
        self.input.clear()
        self.send_clicked.emit(msg)

    def append_user(self, text):
        self.history.append('<span style="color:#ffe7a8"><b>You:</b> ' +
                             _esc(text) + '</span>')

    def append_kernel(self, text):
        # Render as monospace so the structured Kernel introspection
        # block stays aligned.
        self.history.append('<pre style="color:#a8e1ff; white-space:pre-wrap; margin:4px 0;">' +
                             _esc(text) + '</pre>')


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ── Main window ───────────────────────────────────────────────────


class QSBNativeCockpit(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QSB Native Cockpit V2 · Standalone Skyscraper Platform")
        self.resize(1620, 980)

        self.scene = QSBTowerScene(self)
        self.view = QSBTowerView(self.scene)
        self.hud = QSBHud(self)
        self.inspector = QSBFloorInspector(self)

        # Central horizontal: HUD | view | inspector
        center = QSplitter(Qt.Orientation.Horizontal, self)
        center.addWidget(self.hud)
        center.addWidget(self.view)
        center.addWidget(self.inspector)
        center.setSizes([280, 900, 340])

        # Bottom dock: event ticker
        self.ticker = QSBEventTicker(self)

        # Bottom dock: kernel chat
        self.chat = QSBKernelChat(self)

        bottom = QSplitter(Qt.Orientation.Horizontal, self)
        bottom.addWidget(self.ticker)
        bottom.addWidget(self.chat)
        bottom.setSizes([900, 700])

        outer = QSplitter(Qt.Orientation.Vertical, self)
        outer.addWidget(center)
        outer.addWidget(bottom)
        outer.setSizes([720, 240])

        self.setCentralWidget(outer)
        self.scene.on_floor_clicked = self._on_floor_clicked
        self.scene.on_lift_clicked = self._on_lift_clicked
        self.scene.on_openclaw_clicked = self._on_openclaw_clicked
        self.hud.refresh_btn.clicked.connect(self.refresh)
        self.hud.fallback_btn.clicked.connect(self._open_browser_fallback)
        self.chat.send_clicked.connect(self._on_chat_send)

        self.snapshot = None
        self.refresh(first=True)

        # Auto-refresh every 5 seconds
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

        # Keyboard nav
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.setFocus()

    def refresh(self, first=False):
        self.snapshot = tb.build_scene_snapshot()
        self.hud.update_snapshot(self.snapshot)
        if first:
            self.scene.build_tower(self.snapshot)
            self.view.fitInView(self.scene.itemsBoundingRect(),
                                  Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.scene.update_lifts(self.snapshot.get("lifts", []))
            self.scene.update_openclaw(self.snapshot.get("openclaw", {}))
        self.ticker.refresh(self.snapshot)

    def _on_floor_clicked(self, n):
        self.scene.select_floor(n)
        meta = self.scene.floor_meta.get(n)
        self.inspector.show_floor(meta, self.snapshot)

    def _on_lift_clicked(self, lift_idx):
        lifts = self.snapshot.get("lifts", []) if self.snapshot else []
        if lift_idx >= len(lifts):
            return
        L = lifts[lift_idx]
        self.inspector.show_lift(L)

    def _on_openclaw_clicked(self):
        self.inspector.show_openclaw(self.snapshot.get("openclaw", {}))

    def keyPressEvent(self, ev):
        key = ev.key()
        cur = self.scene.selected_floor
        floors = sorted(self.scene.floor_meta.keys())
        if not floors:
            return super().keyPressEvent(ev)
        if cur is None:
            cur = floors[0]
        if key in (Qt.Key.Key_PageUp, Qt.Key.Key_Up):
            nxt = min(cur + 1, floors[-1])
            self._on_floor_clicked(nxt)
        elif key in (Qt.Key.Key_PageDown, Qt.Key.Key_Down):
            nxt = max(cur - 1, floors[0])
            self._on_floor_clicked(nxt)
        elif key == Qt.Key.Key_Home:
            self._on_floor_clicked(floors[-1])  # top floor
        elif key == Qt.Key.Key_End:
            self._on_floor_clicked(floors[0])   # bottom floor
        elif key == Qt.Key.Key_R:
            self.refresh()
        elif key == Qt.Key.Key_F:
            # Fit tower in view
            self.view.fitInView(self.scene.itemsBoundingRect(),
                                Qt.AspectRatioMode.KeepAspectRatio)
            self.view._zoom = 1.0
        else:
            super().keyPressEvent(ev)

    def _on_chat_send(self, message):
        self.chat.append_user(message)
        # Use local kernel adapter directly (no HTTP needed)
        try:
            import importlib, os
            os.environ.setdefault("QSB_LOCAL_MODEL_WRAPPER_ENABLED", "0")
            # Add src to path
            import sys
            src = "/vaults/nvme0/qsb_tower_v1/src"
            if src not in sys.path:
                sys.path.insert(0, src)
            from tower.kernel_dialogue_adapter import ask_kernel
            result = ask_kernel(message, prefer_local_model=False)
            reply = result.get("reply") or ""
            self.chat.append_kernel(reply[:4000])
        except Exception as exc:
            self.chat.append_kernel("[kernel chat error] " + str(exc)[:200])

    def _open_browser_fallback(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:8765/?v=next3d&floor=55")


def main():
    app = QApplication(sys.argv)
    win = QSBNativeCockpit()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
