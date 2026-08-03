#!/usr/bin/env python3
"""
qsb_tower_transit_map.py — LIVE SkyscraperHQ Tube Map (:8875).

2026-07-28, Ross: "like a tube station underground network ... carriages on the move ...
Bill + Wren need a track to everyone everywhere ... the gene pool needs its own SUB-TRACKS
to show what it's doing with who."

Stations = hubs/floors + the gene pool's PROVIDER sub-stations. Trains = real tasks /
routing / messages. A busy line works; a still line doesn't. No demo motion.

TRUTH RULES (2026-07-28, after 3 adversarial audits proved the map faked motion):
  - AGE-GATE: every animated train is <=900s old. Stale events do NOT move. When
    nothing real is happening on a line it stays STILL.
  - NO liveprobe fabrication: a health-probe pass gives a provider a green
    "reachable" RING only — NOT a train. Only providers with REAL recent routing
    jobs (from qsb_brain_router_calls.jsonl) get moving trains.
  - HONEST connectivity: two separate numbers — STRUCTURAL (the drawn lattice) and
    OBSERVED (only edges that carried a real train in the last 15m). Isolated
    stations are reported truthfully (codex/lumen/oracle/f46_bench show isolated).
  - DE-DUPE: identical (from,to,label) trains collapse to one before animating.

REAL sources:
  - gene-pool routing : qsb_brain_router_calls.jsonl  (caller -> Gene Pool -> provider)
  - council flow       : qsb_council_tasks.jsonl
  - comms mesh         : leadership_comms/room.jsonl + acks.jsonl + dm/*.jsonl
  - presence (online)  : leadership_comms/presence.json
  - provider reachable : qsb_gene_pool_key_health.json  (ring only, NOT a train)
Read-only. systemd qsb-transit-map.service.
"""
import json, argparse, time, glob
from collections import deque, Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
LC = REG / "leadership_comms"
CALLS = REG / "qsb_brain_router_calls.jsonl"
COUNCIL = REG / "qsb_council_tasks.jsonl"
ROOM = LC / "room.jsonl"
ACKS = LC / "acks.jsonl"
PRESENCE = LC / "presence.json"
# ── STAGING3 (2026-07-30): three real, fresh registries the live map never reads.
#    boardroom_commentary = the tower's main dialogue (who -> boardroom, directional).
#    delivered/*.jsonl    = PROVEN delivery receipts {from,to,ts,delivered_at} — the
#                           reverse-leg evidence the two-way classifier was starving for.
#    hub_activity         = boardroom hub compose events (worker/hub roll-up, directional).
#    All age-gated + de-duped + capped exactly like every other train (R01: no fabrication).
BOARDROOM_COMMENTARY = REG / "qsb_boardroom_commentary.jsonl"
DELIVERED_DIR = LC / "delivered"
HUB_ACTIVITY = REG / "qsb_boardroom_hub_activity.jsonl"
KEY_HEALTH = REG / "qsb_gene_pool_key_health.json"
# ── TRADING-FLOOR real event sources (added 2026-07-28) ──
OANDA_HIST = REG / "qsb_oanda_history.jsonl"           # real practice fills
BELIEF_DIR = REG / "cognitive"                          # 51 live trader-brain belief_state files
POT_FILE = REG / "qsb_portfolio_pot.json"               # real pot / PnL snapshot
# ── SHARED TRAFFIC FEED (2026-07-29) ─────────────────────────────────────────
# Sibling tools append real worker/routed/lift/system traffic rows here so the map can
# render trains ACROSS the whole building (not just the curated-left trunks). Append-only.
# Each row: {ts, from, to, cat, label, real, source} where from/to are floor NUMBERS (e.g.
# 43) or hub node-ids (e.g. "wren"/"task_council"). We READ it, age-gate it, resolve the
# endpoints to station coords, and draw a train. R01: a train is emitted ONLY for a real
# row (real!=false) with a parseable ts inside the age window — no fabrication.
MAP_FEED = REG / "qsb_map_traffic_feed.jsonl"
VER = str(int(time.time()))
AGE_MAX = 900  # seconds — trains older than this NEVER animate (honest stillness)
# GHOST window (2026-07-29): a station with NO train inside AGE_MAX but a REAL event
# inside GHOST_MAX renders DIM ("idle · Xm ago") instead of fully dark — so an
# idle-but-recently-alive node is visibly distinct from a genuinely dead provider.
GHOST_MAX = 3600  # seconds — had a real event within the last hour == idle-ghost, not dead
# STOCK market-closed detection: if the freshest stock belief tick is staler than this,
# the stock floor is WAITING (after-hours), not broken — labelled "market closed".
STOCK_STALE = 900  # seconds

# provider live/dead status buckets (from qsb_gene_pool_key_health.json)
STATUS_LIVE = {"LIVE"}
STATUS_AMBER = {"NO_CREDIT", "QUOTA"}
STATUS_DEAD = {"BLOCKED", "ENDPOINT_GONE", "NO_KEY", "BAD_KEY"}
# health-file key -> map station key (health uses nvidia_nim; station fan has no nvidia_nim)
HEALTH_ALIAS = {"nvidia_nim": "nvidia_nim"}

STATIONS = {
    # ════════════════════════════════════════════════════════════════════════════
    # CLEAN TUBE-MAP GRID (2026-07-29 FINAL layout). SIX evenly-spaced vertical
    # columns, left→right, so every trunk line runs vertical (within a column),
    # horizontal (column↔spine at a shared row), or a clean 45° — never a long
    # shallow diagonal across the middle. This is what kills the central knot.
    #   col X:  120     320       520        720          920         1120
    #           TRADE   CEOs/AIs  SPINE      SPECIALISTS  GENE-POOL    PROVIDERS
    #   The specialists (col 4) sit BETWEEN the spine and the gene pool so their
    #   short rails don't cross the CEO↔spine rails. Gene Pool (col 5) is the sole
    #   on-ramp to the provider fan (col 6). Row pitch = clean 100px.
    # ════════════════════════════════════════════════════════════════════════════
    # ── COL 1 · TRADING FLOORS — clean vertical cluster, left edge (x=120).
    #    F10 Traders is the interchange; F44 PnL/Pot the shared sink. ──
    "f44_pnl":      {"x": 120, "y": 100, "label": "F44 · PnL/Pot", "trade": True},
    "f41_oanda":    {"x": 120, "y": 230, "label": "F41 · OANDA",   "trade": True},
    "f10_traders":  {"x": 120, "y": 360, "label": "F10 · Traders", "big": True, "trade": True},
    "f42_binance":  {"x": 120, "y": 490, "label": "F42 · Binance", "trade": True},
    "f43_stocks":   {"x": 120, "y": 620, "label": "F43 · Stock Exchange", "trade": True},
    # ── COL 2 · CEOs / AIs — one tidy vertical column x=320, evenly stacked ──
    "wren":         {"x": 320, "y": 100, "label": "Wren · 46", "big": True},
    "bill":         {"x": 320, "y": 210, "label": "Bill · Mac F47"},
    "tp_pip":       {"x": 320, "y": 320, "label": "TP-Pip"},
    "acer_cass":    {"x": 320, "y": 430, "label": "Asa"},
    "codex":        {"x": 320, "y": 540, "label": "Codex · 40"},
    "lumen":        {"x": 320, "y": 650, "label": "Lumen · 48", "offline": True,
                     "offline_reason": ":8848 down — service offline"},
    # ── STAGING3 (2026-07-30): real boardroom-dialogue + delivery-receipt participants that
    #    had NO station on the live map, so their real traffic was invisible. Coords here are
    #    placeholders — the zone-grid layout (see CURATED_ZONE) assigns the final x/y. ──
    "hq":           {"x": 320, "y": 760, "label": "HQ Mind"},
    "ross":         {"x": 320, "y": 870, "label": "Ross · Operator"},
    "forge":        {"x": 720, "y": 280, "label": "Forge", "sub": True},
    "worker_needs": {"x": 320, "y": 980, "label": "Worker-Needs Q"},
    # ── COL 3 · CENTRAL SPINE (hubs) — single column x=520, evenly stacked so the
    #    spine reads as one clean vertical trunk; every CEO joins it horizontally. ──
    "town_square":  {"x": 520, "y": 100, "label": "Town Square · 74",  "big": True},
    "boardroom":    {"x": 520, "y": 250, "label": "Boardroom Hub",      "big": True},
    "task_council": {"x": 520, "y": 400, "label": "Task Council · 77",  "big": True},
    "council15":    {"x": 520, "y": 550, "label": "Council of 15 · 75", "big": True},
    "oracle":       {"x": 520, "y": 670, "label": "Oracle · Cloud VM",  "big": True},
    # ── COL 4 · SPECIALIST CLUSTER (x=720) — short rails off the spine. Wren's brain
    #    + bench sit up top near Wren's row; the council-15 specialists stack below
    #    council15's row so their rails are near-horizontal, no long diagonals. ──
    "wren_brain":   {"x": 720, "y": 100, "label": "qwen14b",   "sub": True},
    "f46_bench":    {"x": 720, "y": 190, "label": "F46 Bench",  "sub": True},
    "tc_sandbox":   {"x": 720, "y": 400, "label": "Sandbox",    "sub": True},
    "iquest_40b":   {"x": 720, "y": 500, "label": "iQuest-40B", "sub": True},
    "qwen_worker":  {"x": 720, "y": 570, "label": "qwen worker","sub": True},
    "claude_acct":  {"x": 720, "y": 640, "label": "Claude",     "sub": True},
    "hermes":       {"x": 720, "y": 710, "label": "Hermes",     "sub": True},
    # ── COL 5 · GENE POOL interchange (x=920) — sole on-ramp to the provider fan ──
    "gene_pool":    {"x": 920, "y": 320, "label": "Gene Pool · 24", "big": True},
    # ── COL 6 · PROVIDERS fan — clean vertical stack x=1120, labels to the right ──
    "kimi":         {"x": 1120, "y": 90,  "label": "kimi",     "prov": True},
    "openai":       {"x": 1120, "y": 165, "label": "openai",   "prov": True},
    "deepseek":     {"x": 1120, "y": 240, "label": "deepseek", "prov": True},
    "cohere":       {"x": 1120, "y": 315, "label": "cohere",   "prov": True},
    "gemini":       {"x": 1120, "y": 390, "label": "gemini",   "prov": True},
    "groq":         {"x": 1120, "y": 465, "label": "groq",     "prov": True},
    "grok":         {"x": 1120, "y": 540, "label": "grok",     "prov": True},
    "nvidia_nim":   {"x": 1120, "y": 615, "label": "nvidia",   "prov": True},
    "openrouter":   {"x": 1120, "y": 690, "label": "openrouter", "prov": True},
    "sambanova":    {"x": 1120, "y": 765, "label": "sambanova", "prov": True},
}

# ════════════════════════════════════════════════════════════════════════════
# ALL-FLOORS ELEVATION (2026-07-29, Ross-authorized): the tower has 170 floors,
# but the curated map above shows only ~6 as real floor stations. This block
# MERGES every one of the 170 canonical floors onto the map as a station — dim /
# idle by default, lighting up ONLY on real activity — WITHOUT touching any of
# the 34 curated stations, their coords, labels, flags, LINES, _TRUNK or trains.
#
# HONESTY (R01): a floor station carries NO train and NO drawn line of its own.
# It is a labelled, clickable roundel that renders DIM unless a real activity
# index (data/registries/qsb_floor_activity_index.json, built by a sibling tool)
# marks it active with a real timestamp. Absent index -> every floor dim. We never
# invent a train for a floor; the existing live-traffic layer is 100% unchanged.
#
# LAYOUT — a real "building elevation" parked to the RIGHT of the curated network
# (curated stations live at x=120..1120; the elevation starts at x=1300), so it
# NEVER overlaps them. viewBox is widened to fit (see draw()). Floors are laid out
# in numeric bands as a tall multi-column grid: floor 1 at the BOTTOM (building
# base), floor 170 at the TOP, columns filled bottom-up in bands of ELEV_BAND
# floors. Deterministic x/y from floor number alone — same every build.
#
# The 13 floor NUMBERS already represented by a curated station (10,24,40,41,42,
# 43,44,46,47,48,74,75,77) are NOT re-added — the elevation reuses the curated
# station for those, so there are zero duplicate floors.
# ════════════════════════════════════════════════════════════════════════════
CANON_REG = REG / "qsb_canonical_floor_registry_1_170.json"
FLOOR_ACT = REG / "qsb_floor_activity_index.json"  # {floor_id:{active,last_ts,source}} (optional)
FLOOR_ZONES = REG / "qsb_floor_zones.json"          # per-floor {label,zone,color,number} (optional)
FLOOR_LIFTS = REG / "qsb_floor_lift_lines.json"     # [{lift_id,label,color,serves,real_or_proposed}] (optional)

# floor-number -> existing curated station id. These floors are ALREADY on the map;
# the elevation must reuse them (no duplicate dot).
CURATED_FLOOR_NUM = {
    10: "f10_traders", 41: "f41_oanda", 42: "f42_binance", 43: "f43_stocks",
    44: "f44_pnl", 46: "f46_bench", 24: "gene_pool", 74: "town_square",
    75: "council15", 77: "task_council", 40: "codex", 47: "bill", 48: "lumen",
}

# elevation geometry (all to the RIGHT of the curated x=1120 provider fan)
# Column pitch is wide enough (150px) that a floor's short label sits fully inside its own
# column and never bleeds into the next — the readability fix after the first render showed
# 92px pitch let ~18-char labels collide across columns. 7 columns * 150 = a 2380-wide canvas.
ELEV_X0 = 1300      # left edge of the first elevation column
ELEV_COL_W = 150    # horizontal pitch between columns (wide enough for the label not to bleed)
ELEV_Y_TOP = 70     # y of the TOP row (highest floors)
ELEV_Y_BOT = 760    # y of the BOTTOM row (floor 1)
ELEV_BAND = 24      # floors per column (7 full columns + a short one = 170)


def _floor_slug(label):
    """Short ascii slug from a floor label, for the station id fN_<slug>."""
    s = "".join(c.lower() if c.isalnum() else "_" for c in (label or ""))
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:22] or "floor"


def _short_label(label, n):
    """A compact station label 'F<n> · <short name>' (trim long department names).
    IDEMPOTENT: if the incoming label already starts with its 'F<n> ·' prefix (the zones
    registry supplies pre-prefixed labels), don't double it."""
    lab = (label or "Floor").strip()
    pref = f"F{n} ·"
    if lab.startswith(pref):
        lab = lab[len(pref):].strip()
    # short cap so each label fits inside its 150px elevation column without bleeding into
    # the next (the full name is always in the station tooltip/click target).
    if len(lab) > 15:
        lab = lab[:14].rstrip() + "…"
    return f"F{n} · {lab}"


def _elev_xy(n):
    """Deterministic elevation coordinate for floor number n (1..170).
    Column = (n-1)//ELEV_BAND left->right; row within column places floor 1 at the
    bottom of column 0 and the highest floor at the top. Every floor gets a stable,
    non-overlapping slot to the right of the curated map."""
    col = (n - 1) // ELEV_BAND
    idx = (n - 1) % ELEV_BAND               # 0 at band base
    x = ELEV_X0 + col * ELEV_COL_W
    # within a band: idx 0 sits at the bottom, idx ELEV_BAND-1 near the top
    span = ELEV_Y_BOT - ELEV_Y_TOP
    y = ELEV_Y_BOT - (idx * (span / (ELEV_BAND - 1)))
    return int(x), int(y)


def _load_json_safe(path, default):
    """Self-contained JSON read (usable at import time, before _load is defined)."""
    try:
        return json.loads(Path(path).read_text(errors="ignore"))
    except Exception:
        return default


def _load_floor_registry():
    """Return {number:int -> label:str} for floors 1..170 from the canonical registry."""
    d = _load_json_safe(CANON_REG, {}) or {}
    fl = d.get("floors", {}) if isinstance(d, dict) else {}
    out = {}
    if isinstance(fl, dict):
        for k, v in fl.items():
            try:
                n = int(k)
            except Exception:
                continue
            lab = (v or {}).get("label") if isinstance(v, dict) else str(v)
            out[n] = lab or f"Floor {n}"
    return out


def _load_floor_zones():
    """Optional enrichment: {number:int -> {label,zone,color}} from qsb_floor_zones.json.
    Real schema: top-level 'floors' dict keyed 'floor_<n>' -> {number,label,zone,color}
    (label already carries the 'F<n> ·' prefix — _short_label is idempotent about it).
    Also tolerant of a floor-number-string dict or a list of records. Missing file / floor
    -> {} (graceful fallback to the canonical registry + numeric bands)."""
    d = _load_json_safe(FLOOR_ZONES, None)
    if d is None:
        return {}
    rows = d.get("floors") if isinstance(d, dict) and "floors" in d else d
    out = {}
    it = rows.items() if isinstance(rows, dict) else (
        ((str(r.get("number")), r) for r in rows) if isinstance(rows, list) else [])
    for k, v in it:
        if not isinstance(v, dict):
            continue
        # number can come from the record, else parsed from a 'floor_<n>' or '<n>' key
        num = v.get("number")
        if num is None:
            ks = str(k).replace("floor_", "").strip()
            try:
                num = int(ks)
            except Exception:
                continue
        try:
            n = int(num)
        except Exception:
            continue
        out[n] = {"label": v.get("label"), "zone": v.get("zone"), "color": v.get("color")}
    return out


# Build the elevation floor stations ONCE at import and MERGE (never overwrite an
# existing curated key). Records the id set so build() can flag them idle-by-default.
# If qsb_floor_zones.json is present it supplies the clean label + zone + zone color and
# GROUPS floors by zone into contiguous columns (readable clusters). Absent -> numeric
# bands from the canonical registry (graceful fallback, still readable).
FLOOR_STATION_IDS = set()
FLOOR_NUM_TO_ID = {}            # floor number -> station id (curated OR elevation) for lift wiring
for _n, _sid in CURATED_FLOOR_NUM.items():
    FLOOR_NUM_TO_ID[_n] = _sid
_FLOOR_REG = _load_floor_registry()
_FLOOR_ZONES = _load_floor_zones()
_ZONE_USED = bool(_FLOOR_ZONES)

# floors we must place (all 170 minus the 13 curated numbers)
_ELEV_NUMS = [n for n in sorted(_FLOOR_REG) if n not in CURATED_FLOOR_NUM]

# ── zone-grouped ordering (readability): when zones are available, order floors by
#    (zone, number) so each column holds one zone's floors contiguously; else plain
#    numeric order (floor 1 first). The _elev_xy slot is assigned along this order so
#    a zone reads as a solid vertical band. ──
if _ZONE_USED:
    def _zk(n):
        z = (_FLOOR_ZONES.get(n) or {}).get("zone") or "~"
        return (str(z), n)
    _ELEV_ORDER = sorted(_ELEV_NUMS, key=_zk)
else:
    _ELEV_ORDER = _ELEV_NUMS

for _slot, _n in enumerate(_ELEV_ORDER):
    _z = _FLOOR_ZONES.get(_n) or {}
    _lab = _z.get("label") or _FLOOR_REG.get(_n) or f"Floor {_n}"
    # strip any 'F<n> ·' prefix from the label before slugging so the id reads f<n>_<name>
    # (not f<n>_f<n>_<name>) when the zones registry supplies pre-prefixed labels.
    _slug_src = _lab
    _pref = f"F{_n} ·"
    if _slug_src.startswith(_pref):
        _slug_src = _slug_src[len(_pref):].strip()
    _sidk = f"f{_n}_{_floor_slug(_slug_src)}"
    if _sidk in STATIONS:
        continue  # never clobber an existing curated station
    # slot-based coord keeps zone columns contiguous when zones are used; falls back to
    # numeric-band coord (floor 1 at base) when they aren't. Both are deterministic.
    if _ZONE_USED:
        col = _slot // ELEV_BAND
        idx = _slot % ELEV_BAND
        _x = ELEV_X0 + col * ELEV_COL_W
        _span = ELEV_Y_BOT - ELEV_Y_TOP
        _y = int(ELEV_Y_BOT - (idx * (_span / (ELEV_BAND - 1))))
    else:
        _x, _y = _elev_xy(_n)
    _st = {
        "x": _x, "y": _y,
        "label": _short_label(_lab, _n),
        "floor": True,        # marks an elevation floor station (presence-only)
        "floor_num": _n,
        "idle": True,         # dim by default; build() lights it only on real activity
    }
    if _z.get("zone"):
        _st["zone"] = _z["zone"]
    if _z.get("color"):
        _st["zone_color"] = _z["color"]
    STATIONS[_sidk] = _st
    FLOOR_STATION_IDS.add(_sidk)
    FLOOR_NUM_TO_ID[_n] = _sidk


# ════════════════════════════════════════════════════════════════════════════
# ZONE-ORGANISED UNIFORM GRID (2026-07-29 FINAL v2 — Ross: "traffic needs to be all
# the way through the skyscraper ... better organized, better layout").
#
# THE FIX: the old layout stacked ALL 34 curated stations (which are the high-cadence
# real-traffic sources) into the FIRST 3 columns, so ~51% of trains pooled in x<600 while
# the 157 floor stations spread across cols 3-13 carried only sparse floor traffic. This
# block instead assigns EVERY station — curated AND floor — to its DEPARTMENT ZONE (from
# qsb_floor_zones.json) and lays the zones out left→right as contiguous, labelled column
# BLOCKS. Curated hubs live INSIDE their zone (trading floors in Trading, CEOs in Executive,
# gene pool + providers in Providers, specialists in R&D …), so the bright trunk traffic is
# interspersed across the whole width instead of piled on the left.
#
# ONE SIZE + ONE SPACING preserved: x/y still come ONLY from (col*PITCH_X, row*PITCH_Y)
# with the same uniform pitch everywhere — a zone is just a contiguous run of columns.
# Every station id keeps its wiring (LINES/_TRUNK/trains reference ids), so the same node
# pairs stay connected; only coordinates move. Zone header labels are emitted for the
# frontend to draw legible department blocks.
# ════════════════════════════════════════════════════════════════════════════
GRID_PITCH_X = 210   # px between column centres (uniform everywhere — roomy, not cramped)
GRID_PITCH_Y = 132   # px between row centres    (uniform everywhere — roomy, not cramped)
GRID_X0     = 130    # x of column 0 centre (left margin for labels)
GRID_Y0     = 150    # y of row 0 centre (leaves a band at the very top for zone headers)
GRID_ROWS_PER_COL = 13   # stations stacked per column before wrapping to the next column

# ── Assign a DEPARTMENT ZONE to every curated (non-floor) station. Floor stations already
#    carry s["zone"] from qsb_floor_zones.json; curated ones don't, so map them by hand into
#    the same zone vocabulary so they cluster with the floors they actually work with. ──
CURATED_ZONE = {
    # Trading Floors — the trading cluster
    "f44_pnl": "Trading Floors", "f41_oanda": "Trading Floors", "f10_traders": "Trading Floors",
    "f42_binance": "Trading Floors", "f43_stocks": "Trading Floors",
    # Executive & Council — CEOs/AIs + the central spine hubs
    "wren": "Executive & Council", "bill": "Executive & Council", "tp_pip": "Executive & Council",
    "acer_cass": "Executive & Council", "codex": "Executive & Council", "lumen": "Executive & Council",
    "town_square": "Executive & Council", "boardroom": "Executive & Council",
    "task_council": "Executive & Council", "council15": "Executive & Council",
    "oracle": "Executive & Council",
    # STAGING3: HQ mind + Ross the operator are executive-council participants
    "hq": "Executive & Council", "ross": "Executive & Council",
    # R&D / Labs — the specialist/bench/sandbox cluster
    "wren_brain": "R&D / Labs", "f46_bench": "R&D / Labs", "tc_sandbox": "R&D / Labs",
    "iquest_40b": "R&D / Labs", "qwen_worker": "R&D / Labs", "claude_acct": "R&D / Labs",
    "hermes": "R&D / Labs", "forge": "R&D / Labs",
    # STAGING3: the worker-needs roll-up sits with core operations/monitoring
    "worker_needs": "Core Operations",
    # Providers & Integration — gene pool interchange + the provider fan
    "gene_pool": "Providers & Integration", "kimi": "Providers & Integration",
    "openai": "Providers & Integration", "deepseek": "Providers & Integration",
    "cohere": "Providers & Integration", "gemini": "Providers & Integration",
    "groq": "Providers & Integration", "grok": "Providers & Integration",
    "nvidia_nim": "Providers & Integration", "openrouter": "Providers & Integration",
    "sambanova": "Providers & Integration",
}
# stamp the zone onto every curated station so it is grouped like the floors
for _cid, _cz in CURATED_ZONE.items():
    if _cid in STATIONS and not STATIONS[_cid].get("floor"):
        STATIONS[_cid]["zone"] = _cz

# ── ZONE ORDER (left→right across the building). Curated-heavy zones lead so the trunk
#    traffic starts on the left but the zones themselves fan across the whole width. Any
#    zone present in the data but not listed here is appended (nothing dropped). ──
ZONE_ORDER = [
    "Reception & Lobby", "Trading Floors", "Commerce & Retail", "Core Operations",
    "Executive & Council", "R&D / Labs", "Media & Creative", "Amenities & Culture",
    "Security & Governance", "Infrastructure & Ops", "Providers & Integration",
    "Penthouse / Kernel",
]
ZONE_COLORS = {
    "Reception & Lobby": "#94a3b8", "Trading Floors": "#f59e0b", "Commerce & Retail": "#eab308",
    "Core Operations": "#38bdf8", "Executive & Council": "#6366f1", "R&D / Labs": "#22c55e",
    "Media & Creative": "#ec4899", "Amenities & Culture": "#14b8a6",
    "Security & Governance": "#ef4444", "Infrastructure & Ops": "#0ea5e9",
    "Providers & Integration": "#a78bfa", "Penthouse / Kernel": "#d4af37",
}
# a station whose zone is missing/unknown -> a catch-all bucket at the far right
_UNZONED = "Other"


def _station_zone(sid):
    z = STATIONS[sid].get("zone")
    return z if z else _UNZONED


# group every station id by zone
_ZONE_MEMBERS = {}
for _sid_all in STATIONS:
    _ZONE_MEMBERS.setdefault(_station_zone(_sid_all), []).append(_sid_all)

# within a zone: curated stations first (they anchor the department, drawn bigger reading),
# then floor stations by number — so a zone reads top-to-bottom hubs→floors.
def _within_zone_key(sid):
    s = STATIONS[sid]
    is_floor = 1 if s.get("floor") else 0
    return (is_floor, s.get("floor_num", 0), sid)
for _z in _ZONE_MEMBERS:
    _ZONE_MEMBERS[_z].sort(key=_within_zone_key)

# final zone order = ZONE_ORDER (those present) + any leftover zones + Other last
_ZONES_PRESENT = [z for z in ZONE_ORDER if z in _ZONE_MEMBERS]
for _z in _ZONE_MEMBERS:
    if _z not in _ZONES_PRESENT:
        _ZONES_PRESENT.append(_z)
if _UNZONED in _ZONES_PRESENT:   # push the catch-all to the far right
    _ZONES_PRESENT = [z for z in _ZONES_PRESENT if z != _UNZONED] + [_UNZONED]

# ── LAY OUT: each zone gets a contiguous run of columns; fill each zone column-major
#    (fill a column top→bottom to GRID_ROWS_PER_COL, then start the next column in the
#    same zone). A new zone always starts on a FRESH column, so zones never share a
#    column — the department blocks read as clean vertical bands. ──
ZONE_BLOCKS = []          # [{zone, color, col0, col1, x0, x1, count}] for the frontend headers
_col_cursor = 0           # next free grid column
for _z in _ZONES_PRESENT:
    members = _ZONE_MEMBERS[_z]
    if not members:
        continue
    _zcol0 = _col_cursor
    for _mi, _msid in enumerate(members):
        _col_in_zone = _mi // GRID_ROWS_PER_COL
        _row = _mi % GRID_ROWS_PER_COL
        _gcol = _zcol0 + _col_in_zone
        STATIONS[_msid]["x"] = GRID_X0 + _gcol * GRID_PITCH_X
        STATIONS[_msid]["y"] = GRID_Y0 + _row * GRID_PITCH_Y
    _zcols = (len(members) + GRID_ROWS_PER_COL - 1) // GRID_ROWS_PER_COL
    _col_cursor = _zcol0 + _zcols   # next zone starts on a fresh column
    ZONE_BLOCKS.append({
        "zone": _z, "color": ZONE_COLORS.get(_z, "#5a6577"),
        "col0": _zcol0, "col1": _col_cursor - 1,
        "x0": GRID_X0 + _zcol0 * GRID_PITCH_X,
        "x1": GRID_X0 + (_col_cursor - 1) * GRID_PITCH_X,
        "count": len(members),
    })

_GRID_USED_COLS = _col_cursor
_GRID_ROWS = GRID_ROWS_PER_COL
# Exact viewBox: fit the used columns/rows + a right margin for the labels that sit to the
# RIGHT of their roundel, + a small pad. Header band already reserved by GRID_Y0.
GRID_VIEW_W = GRID_X0 + (_GRID_USED_COLS - 1) * GRID_PITCH_X + 160   # +label margin
GRID_VIEW_H = GRID_Y0 + (_GRID_ROWS - 1) * GRID_PITCH_Y + 60
GRID_VIEWBOX = f"0 0 {GRID_VIEW_W} {GRID_VIEW_H}"

# ════════════════════════════════════════════════════════════════════════════
# ONE-SIZE RESTORE (2026-07-30 ONESIZE pass — Ross: 'one size, one spacing').
# The METRO-CORRIDOR override that previously sat here re-laid stations onto
# hardcoded backbone coords + a variable _ELEV2_COLW=152 per-department elevation
# and widened the canvas to ~3770px. That BROKE the absolute one-size rule, so it
# is removed. The authoritative layout is the ZONE-ORGANISED UNIFORM GRID above:
# every station at (GRID_X0+col*GRID_PITCH_X, GRID_Y0+row*GRID_PITCH_Y), one pitch
# everywhere (210 x 132). GRID_VIEWBOX/ZONE_BLOCKS from that block stand unchanged.
# This ONESIZE pass then ADDS overlays only (department lines + lift tracks +
# interchange markers) that TRACE the existing grid positions — no station moves.
# ════════════════════════════════════════════════════════════════════════════


def _load_lift_lines():
    """Optional: lift topology from qsb_floor_lift_lines.json -> list of drawable lift lines.
    Each source row {lift_id,label,color,serves:[floor_nums],real_or_proposed}. We translate
    each consecutive served-floor pair into a (a_id,b_id,'lift') edge, carrying color + proposed
    flag. Floors not on the map (or missing) are skipped gracefully. Returns []
    when the file is absent — the map then simply draws no lift lines (fallback).
    Real schema row: {lift_id,label,color,serves:['floor_01'…],serves_num:[1…],
    real_or_proposed,status}. Prefers serves_num; falls back to parsing 'floor_<n>'
    strings out of serves. Floors not on the map (e.g. floor 0) are skipped gracefully."""
    d = _load(FLOOR_LIFTS, None)
    if d is None:
        return []
    rows = d.get("lifts") if isinstance(d, dict) and "lifts" in d else d
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        nums = r.get("serves_num")
        if not isinstance(nums, list):
            nums = []
            for f in (r.get("serves") or []):
                try:
                    nums.append(int(str(f).replace("floor_", "").strip()))
                except Exception:
                    pass
        color = r.get("color")
        proposed = str(r.get("real_or_proposed", "real")).lower().startswith("prop")
        lift_id = r.get("lift_id") or r.get("id") or "lift"
        ids = []
        for fn in nums:
            try:
                sid = FLOOR_NUM_TO_ID.get(int(fn))
            except Exception:
                sid = None
            if sid:
                ids.append(sid)
        for a, b in zip(ids, ids[1:]):
            if a != b:
                out.append({"a": a, "b": b, "cat": "lift", "lift_id": lift_id,
                            "color": color, "proposed": proposed})
    return out


# ════════════════════════════════════════════════════════════════════════════
# ONESIZE OVERLAYS (2026-07-30) — OVERLAY-ONLY, ZERO layout change. Both builders
# read the stations' CURRENT (x,y) — which derive ONLY from col*GRID_PITCH_X /
# row*GRID_PITCH_Y — so nothing is moved. Sources are real registries:
#   · department lines  <- qsb_floor_zones.json (station 'zone' / 'zone_color')
#   · lift interchanges <- qsb_floor_lift_lines.json (via _load_lift_lines)
# ════════════════════════════════════════════════════════════════════════════
def _department_line_overlays():
    """Per-department coloured polyline that THREADS a zone's stations exactly as they
    already sit on the uniform grid, so a viewer can TRACE that department's route. Every
    point is a real station's current (x,y); no station is repositioned. Zones come from
    qsb_floor_zones.json (floors carry s['zone']) + the curated CURATED_ZONE map."""
    out = []
    for z in _ZONES_PRESENT:
        members = [sid for sid in _ZONE_MEMBERS.get(z, [])
                   if sid in STATIONS and STATIONS[sid].get("x") is not None]
        if len(members) < 2:
            continue
        color = ZONE_COLORS.get(z) or STATIONS[members[0]].get("zone_color") or "#5a6577"
        out.append({"zone": z, "color": color,
                    "pts": [[STATIONS[sid]["x"], STATIONS[sid]["y"]] for sid in members],
                    "ids": members, "count": len(members)})
    return out


def _lift_interchanges():
    """A station served by >=2 DISTINCT lifts is a lift crossing. But the service_lift,
    security_lift and emergency_stairwell serve ~every floor, so counting them makes a THIRD
    of all floors look like interchanges (noise). A MEANINGFUL (major) interchange is where a
    rider must CHANGE between ROUTE lifts — i.e. >=2 NON-universal lifts meet. 'Universal' is
    detected data-driven (a lift serving >=75% of the busiest lift's floor count). We return
    every >=2-lift crossing honestly (n = all distinct lifts) and flag `major` for the frontend
    to mark prominently. Sources: qsb_floor_lift_lines.json via _load_lift_lines()."""
    edges = _load_lift_lines()
    # per-lift served-station counts, to detect the universal (all-floors) shafts
    served = {}
    for L in edges:
        lid = L.get("lift_id")
        served.setdefault(lid, set()).update((L["a"], L["b"]))
    _max = max((len(v) for v in served.values()), default=0)
    universal = {lid for lid, v in served.items() if _max and len(v) >= 0.75 * _max}
    touch = {}
    for L in edges:
        for _end in (L["a"], L["b"]):
            touch.setdefault(_end, set()).add(L.get("lift_id"))
    out = []
    for sid, lifts in touch.items():
        if len(lifts) >= 2 and sid in STATIONS and STATIONS[sid].get("x") is not None:
            route_lifts = sorted(l for l in lifts if l and l not in universal)
            out.append({"id": sid, "x": STATIONS[sid]["x"], "y": STATIONS[sid]["y"],
                        "n": len(lifts), "lifts": sorted(l for l in lifts if l),
                        "route_lifts": route_lifts, "route_n": len(route_lifts),
                        "major": len(route_lifts) >= 2})
    out.sort(key=lambda r: (-r["route_n"], -r["n"], r["id"]))
    return out


# Positions are static (fixed at import by the uniform-grid layout), but _lift_interchanges
# needs _load() which is defined further down — so compute lazily and cache on first use.
_DEPT_LINES_CACHE = None
_LIFT_INTERCHANGES_CACHE = None


def _dept_lines_cached():
    global _DEPT_LINES_CACHE
    if _DEPT_LINES_CACHE is None:
        _DEPT_LINES_CACHE = _department_line_overlays()
    return _DEPT_LINES_CACHE


def _interchanges_cached():
    global _LIFT_INTERCHANGES_CACHE
    if _LIFT_INTERCHANGES_CACHE is None:
        _LIFT_INTERCHANGES_CACHE = _lift_interchanges()
    return _LIFT_INTERCHANGES_CACHE


PROV = {"openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok",
        "nvidia_nim", "ollama_lan", "ollama_local", "openrouter", "sambanova"}

# ── STATION VALIDITY (item 1) ─────────────────────────────────────────────────
# A station is VALID (operational — can send/receive real traffic) or INVALID
# (honestly cannot). Rule (best-effort, no fabrication):
#   VALID if  (provider whose key-health status is LIVE)
#         OR  (not a provider AND not in the known-dead set)
#   INVALID otherwise:
#     - provider with a NON-LIVE key-health status (dead/amber/no-key) -> blocked
#     - a known-dead non-provider node {oracle, lumen, f46_bench} -> no live event source
# NOTE: a station also counts VALID if it has EVER appeared as a real train endpoint
# in the current window (computed at build()-time), so anything that lights becomes
# valid even if the static rule missed it (e.g. iquest_40b once it carries traffic).
# f46_bench REMOVED from known-dead (2026-07-28): it now has a REAL event source —
# the council-specialist liveness driver runs a genuine F46 bench proposal through the
# sandbox each tick and emits a `bench_proposal` event, so f46_bench carries real trains.
# oracle REMOVED from known-dead (2026-07-29): the Oracle Cloud VM (sky · 145.241.225.163)
# is now a LIVE worker — qsb_oracle_worker.py SSHes into it every ~2 min and logs REAL
# tool_selected + noted(actor=oracle) events (only when the SSH round-trip returns data),
# so oracle carries genuine age-gated trains. lumen is probed live on :8848 (see build()).
KNOWN_DEAD = set()
KNOWN_DEAD_REASON = {}

CORE = ["wren", "tp_pip", "acer_cass", "bill", "codex", "lumen"]
HUBS = ["boardroom", "town_square", "task_council", "council15", "gene_pool"]
PROVIDERS = ["openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok", "nvidia_nim", "openrouter", "sambanova"]
LINES = []
# EVERYONE connects with EVERYONE — full mesh among the AIs/CEOs
for i, a in enumerate(CORE):
    for b in CORE[i + 1:]:
        LINES.append((a, b, "comms"))
# every AI -> every hub (gene-pool access for ALL, council, comms, interchange)
for a in CORE:
    for h in HUBS:
        cat = "route" if h == "gene_pool" else ("council" if h in ("task_council", "council15")
              else ("comms" if h == "town_square" else "hub"))
        LINES.append((a, h, cat))
# hubs interconnect (every hub to every hub)
for i, a in enumerate(HUBS):
    for b in HUBS[i + 1:]:
        LINES.append((a, b, "hub"))
# gene-pool SUB-TRACKS -> every provider
for p in PROVIDERS:
    LINES.append(("gene_pool", p, "provider"))
# dedupe (keep first category)
_seen = set(); _L = []
for a, b, c in LINES:
    k = tuple(sorted((a, b)))
    if k not in _seen:
        _seen.add(k); _L.append((a, b, c))
LINES = _L
# SUB-TRACKS: Council of 15, Wren, and Task Council each get their own internal lines
LINES += [
    ("council15", "iquest_40b", "c15"), ("council15", "qwen_worker", "c15"),
    ("council15", "hermes", "c15"), ("council15", "claude_acct", "c15"), ("council15", "gene_pool", "c15"),
    ("wren", "wren_brain", "wrensub"), ("wren", "f46_bench", "wrensub"),
    ("wren", "hermes", "wrensub"), ("wren", "iquest_40b", "wrensub"),
    # Wren can wield ANY specialist _tool_station() may return (qwen_worker / claude_acct),
    # so give those a rail too — otherwise a "Wren wields qwen_worker" train animates over a
    # blank edge with no drawn track under it (bug #2 coherence: train edge with no line).
    ("wren", "qwen_worker", "wrensub"), ("wren", "claude_acct", "wrensub"),
    ("task_council", "tc_sandbox", "council"), ("task_council", "council15", "council"),
    # Oracle Cloud VM — tunnels into the tower
    ("oracle", "boardroom", "hub"), ("oracle", "gene_pool", "route"),
    ("oracle", "town_square", "comms"), ("oracle", "wren", "comms"),
    # TRADING FLOORS: F10 Traders hub -> each venue floor; every venue -> F44 PnL/Pot sink.
    # F10 also links into the tower spine (task_council) so the cluster is one hop from the core.
    ("f10_traders", "f41_oanda", "trade"), ("f10_traders", "f42_binance", "trade"),
    ("f10_traders", "f43_stocks", "trade"), ("f10_traders", "f44_pnl", "trade"),
    ("f41_oanda", "f44_pnl", "trade"), ("f42_binance", "f44_pnl", "trade"),
    ("f43_stocks", "f44_pnl", "trade"), ("f10_traders", "task_council", "trade"),
    # 2026-07-29 Ross MUST-HAVE ("where's the tracks from codex to traders and wren to traders?"):
    # the worker→trading-floor tracks must be CATEGORISED `trade` (orange trunk), not swallowed by
    # the faint hidden mesh. Wren is the traders' GOVERNOR; Bill + Codex do trading-check work.
    # Adding them here (before the mesh-fill loop) makes them real drawn trade lines, always visible.
    ("wren", "f10_traders", "trade"), ("codex", "f10_traders", "trade"),
    ("bill", "f10_traders", "trade"),
]
# ── EVERYONE → TASK COUNCIL (Ross: "everyone needs a track to the task council") ──
# Explicit, bright council spurs so no station is more than one hop from task_council.
# CEOs/AIs + gene_pool go direct; providers reach it via gene_pool→task_council;
# the sub-specialists reach it via council15→task_council.
_COUNCIL_SPUR = [
    "wren", "tp_pip", "acer_cass", "bill", "codex", "lumen",
    "boardroom", "town_square", "council15", "gene_pool", "oracle",
]
for _s in _COUNCIL_SPUR:
    LINES.append((_s, "task_council", "council"))
# provider-facing obviousness: gene_pool is the on-ramp; make gene_pool→task_council a council spur
# (dedupe below keeps first category; force it council so it draws as a bright council track)
LINES.append(("gene_pool", "task_council", "council"))
# re-dedupe after adding council spurs, but PREFER the council category for any task_council edge
_seen2 = {}; _L2 = []
for a, b, c in LINES:
    k = tuple(sorted((a, b)))
    to_council = "task_council" in (a, b)
    if k not in _seen2:
        _seen2[k] = len(_L2); _L2.append([a, b, c])
    elif to_council and c == "council":
        _L2[_seen2[k]][2] = "council"  # upgrade an existing task_council edge to bright council
LINES = [tuple(x) for x in _L2]
# ── COMPLETE MESH (Ross: "everyone needs to connect to everything and everyone") ──
# After the meaningful categorized tracks, add a direct track between EVERY remaining pair
# of stations, so every node connects DIRECTLY to every other (graph diameter = 1). These
# render as the faint dashed "mesh" lattice; real traffic still lights the bright tracks on top.
_have = {tuple(sorted((a, b))) for a, b, *_ in LINES}
_all_st = list(STATIONS)
for _i, _a in enumerate(_all_st):
    for _b in _all_st[_i + 1:]:
        if tuple(sorted((_a, _b))) not in _have:
            LINES.append((_a, _b, "mesh"))
# NOTE: no "liveprobe" colour — health-probe passes are a RING, never a train (audit fix #2).
CAT_COLOR = {"route": "#40b4ff", "provider": "#45f59b", "council": "#b98bff",
             "comms": "#ffc24b", "hub": "#6d7f98", "c15": "#2dd4bf", "wrensub": "#c4a3ff",
             "mesh": "#33465f", "trade": "#ff8f3f",  # trade = warm orange, the trading-floor line
             "lift": "#7ea6c9",  # lift = cool slate, the inter-floor lift lines (elevation)
             "floorflow": "#5eead4",  # floor-origin traffic = bright teal (floors talking, spread everywhere)
             "return": "#ff7ac2",  # DOWN-traffic return leg (hub→floor / lead→floor) = coral-pink, so the
                                   # 2-way round-trip reads distinctly from the up-leg it answers. HONEST:
                                   # only rows the sibling producer really appends as cat:"return" get this.
             "feed": "#40b4ff",  # shared-feed traffic default (rows usually carry their own cat)
             # STAGING3 (2026-07-30): boardroom dialogue = warm gold (the tower's main
             # conversation into the boardroom); delivery receipts = bright green (proven
             # delivered — the reverse-leg evidence that upgrades one-way to confirmed two-way).
             "boardroom": "#ffd166", "delivered": "#4ade80"}
# TRUNK LINES: the meaningful backbone drawn as proper coloured tube lines even when idle.
# Everything else in LINES is the faint "everyone-connects" mesh web (dim grey lattice).
#   - hub spine (town_square→boardroom→task_council→council15)
#   - each CEO/AI → Boardroom (home hub)
#   - Gene Pool → each provider (the right-hand fan)
#   - Council-15 → its specialists ; Oracle tunnels up the spine
_TRUNK = [
    ("town_square", "boardroom"), ("boardroom", "task_council"), ("task_council", "council15"),
    ("wren", "boardroom"), ("tp_pip", "boardroom"), ("acer_cass", "boardroom"),
    ("bill", "boardroom"), ("codex", "boardroom"), ("lumen", "boardroom"),
    ("gene_pool", "openai"), ("gene_pool", "deepseek"), ("gene_pool", "cohere"),
    ("gene_pool", "gemini"), ("gene_pool", "groq"), ("gene_pool", "kimi"),
    ("gene_pool", "grok"), ("gene_pool", "openrouter"), ("gene_pool", "nvidia_nim"),
    ("council15", "iquest_40b"), ("council15", "qwen_worker"),
    ("council15", "hermes"), ("council15", "claude_acct"), ("council15", "gene_pool"),
    ("oracle", "council15"), ("boardroom", "gene_pool"),
    # specialist / bench / sandbox connectors — dim backbone so these nodes never look
    # stranded even when idle (they're structurally one hop off the spine).
    ("wren", "wren_brain"), ("wren", "f46_bench"), ("task_council", "tc_sandbox"),
    # trading-floor backbone (always visible orange lines)
    ("f10_traders", "f41_oanda"), ("f10_traders", "f42_binance"), ("f10_traders", "f43_stocks"),
    ("f10_traders", "f44_pnl"), ("f41_oanda", "f44_pnl"), ("f42_binance", "f44_pnl"),
    ("f43_stocks", "f44_pnl"), ("f10_traders", "task_council"),
    # 2026-07-29 Ross: trading floors need tracks to the workers who oversee/act on them.
    # Wren is the traders' governor ("Wren · 46"); Bill + Codex do trading-check work.
    ("wren", "f10_traders"), ("bill", "f10_traders"), ("codex", "f10_traders"),
]
# every EVERYONE→TASK COUNCIL spur is a trunk line — always visible, never buried in the mesh
_TRUNK += [(s, "task_council") for s in _COUNCIL_SPUR] + [("gene_pool", "task_council")]
TRUNK_SET = {tuple(sorted(e)) for e in _TRUNK}
PRES_MAP = {"wren": "wren", "tp": "tp_pip", "asa": "acer_cass", "bill": "bill", "pip": "tp_pip"}
# comms logs use short names (asa/tp/pip); stations are keyed acer_cass/tp_pip. Resolve so
# TP↔Asa room posts, acks, and DM lines actually become trains ("everyone talking").
ALIAS = {"asa": "acer_cass", "tp": "tp_pip", "pip": "tp_pip", "tp_pip": "tp_pip",
         "acer_cass": "acer_cass", "wren": "wren", "bill": "bill",
         # STAGING3 (2026-07-30): boardroom-dialogue + delivery-receipt actor names.
         # claude/iquest reuse their existing specialist stations; hq/forge/ross/
         # worker_needs_queue resolve to the new stations added above. Actors that
         # can't map to a real station (system, iris, chain_reporting) are left OUT
         # here so _sid() drops them — honest: no station, no train.
         "claude": "claude_acct", "iquest": "iquest_40b", "hq": "hq",
         "forge": "forge", "ross": "ross", "worker_needs_queue": "worker_needs"}


def _sid(name):
    """Resolve a comms-log actor name to a station key, or None if not a station."""
    if not name:
        return None
    s = ALIAS.get(name, name)
    return s if s in STATIONS else None


def _feed_sid(v):
    """Resolve a traffic-feed endpoint to a station id, or None if it can't be placed.
    A feed endpoint is either a FLOOR NUMBER (int/str like 43 or "43"/"floor_43") that
    maps via FLOOR_NUM_TO_ID to a curated OR elevation floor station, or a HUB/actor NODE-ID
    (e.g. "wren", "task_council", "gene_pool", "openai") that is already a station key or a
    comms alias. Returns the station id so a feed train lands on a real coord — never a train
    for an endpoint the map can't place (honest: unplaceable rows are skipped, not faked)."""
    if v is None:
        return None
    # int floor number
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return FLOOR_NUM_TO_ID.get(v)
    s = str(v).strip()
    if not s:
        return None
    # already a station id
    if s in STATIONS:
        return s
    # comms alias (asa/tp/pip -> station)
    if s in ALIAS and ALIAS[s] in STATIONS:
        return ALIAS[s]
    # "floor_43" / "f43" / "43" -> floor number
    num_s = s.lower().replace("floor_", "").lstrip("f")
    if num_s.isdigit():
        return FLOOR_NUM_TO_ID.get(int(num_s))
    return None


def _tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [json.loads(x) for x in deque(f, maxlen=n) if x.strip()]
    except Exception:
        return []


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(errors="ignore"))
    except Exception:
        return d


def _tool_station(text):
    t = (text or "").lower()
    if "gene pool" in t: return "gene_pool"
    if "oracle" in t: return "oracle"   # "owner uses Oracle Cloud VM …" -> real oracle trains
    if "iquest" in t: return "iquest_40b"
    if "hermes" in t: return "hermes"
    if "claude" in t: return "claude_acct"
    if "bill" in t: return "bill"
    if "tp-pip" in t or "tp_pip" in t or "pip" in t: return "tp_pip"
    if "acer" in t or "asa" in t: return "acer_cass"
    if "qwen" in t: return "qwen_worker"
    return "qwen_worker"


_CRYPTO_QUOTES = ("USDT", "USDC", "BUSD")     # stablecoin quote suffixes -> crypto venue
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "LTC", "MATIC", "DOT"}


def _venue_station(instrument: str) -> str:
    """Infer the venue floor a trader instrument belongs to (HONEST, from the symbol shape):
      · crypto (…USDT/USDC, BTC_USDT underscore form, or a known crypto base) -> Binance testnet (f42_binance)
      · FX / commodities / indices (real X_Y underscore pairs) -> OANDA practice (f41_oanda)
      · plain uppercase equity ticker (AAPL/SPY/QQQ) -> Stocks paper (f43_stocks)
    Mirrors how the fleet actually routes these symbols across venues.

    Ordering matters: the crypto test runs BEFORE the underscore/FX test, so an
    underscore-form crypto pair (BTC_USDT, ETH_USDC) routes to Binance and does NOT
    fall through to OANDA. Real FX/commodity/index underscore pairs (EUR_USD, USD_JPY,
    XAU_USD, NAS100_USD) still route to OANDA because their halves aren't crypto."""
    s = (instrument or "").upper()
    if not s:
        return "f43_stocks"
    # split the underscore form once so we can inspect base/quote halves
    parts = s.split("_")
    base = parts[0]
    quote = parts[-1] if len(parts) > 1 else ""
    # CRYPTO FIRST — catch both compact (BTCUSDT) and underscore (BTC_USDT / ETH_USDC) forms,
    # plus bare legacy crypto-vs-USD pairs (BTCUSD / ETHUSD) and any known crypto base.
    if (s.endswith(_CRYPTO_QUOTES)               # BTCUSDT, ETH_USDC (endswith ignores the "_")
            or quote in _CRYPTO_QUOTES           # explicit underscore quote half
            or s in ("BTCUSD", "ETHUSD")         # legacy compact crypto-vs-USD
            or base in _CRYPTO_BASES):           # BTC_USD, SOL_USDT, ETH… -> crypto venue
        return "f42_binance"
    if "_" in s:  # EUR_USD, USD_JPY, XAU_USD, NAS100_USD, WTICO_USD, UK10YB_GBP …
        return "f41_oanda"
    return "f43_stocks"  # AAPL, MSFT, SPY, QQQ, NVDA, COIN, GLD, IWM, DIA, XLF, TSLA


def _parse_ts(ts):
    """Best-effort parse of an ISO-ish ts to epoch seconds; None on failure."""
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


import urllib.request as _probe_req

_PROBE_CACHE = {}  # url -> (epoch_checked, is_up) ; cheap, avoids probing every build()


def _http_up(url, ttl=15, timeout=1.2):
    """Honest liveness probe: is `url` returning HTTP 2xx/3xx right now? Cached for `ttl`s
    so we don't hammer a service on every 1s /api/data build. Returns True/False."""
    now = time.time()
    hit = _PROBE_CACHE.get(url)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    up = False
    try:
        req = _probe_req.Request(url, method="GET")
        with _probe_req.urlopen(req, timeout=timeout) as r:
            up = (200 <= getattr(r, "status", 200) < 400)
    except Exception:
        up = False
    _PROBE_CACHE[url] = (now, up)
    return up


def _provider_status():
    """Map station-key -> {status, detail} from qsb_gene_pool_key_health.json."""
    h = _load(KEY_HEALTH, {}) or {}
    provs = h.get("providers", {}) if isinstance(h, dict) else {}
    out = {}
    if isinstance(provs, dict):
        for name, info in provs.items():
            sid = HEALTH_ALIAS.get(name, name)
            if isinstance(info, dict):
                out[sid] = {"status": (info.get("status") or "UNKNOWN").upper(),
                            "detail": info.get("detail") or ""}
    return out


def _station_last_event():
    """Per-station last REAL-event epoch, from the SAME real logs the trains come from.
    This is INDEPENDENT of the animated-train category caps: a station can be crowded
    out of the capped animated set yet still have a genuine recent event here. Used for
    the IDLE-GHOST tier (item 1) — a station with a real event inside GHOST_MAX but no
    live train inside AGE_MAX renders DIM instead of fully dark. HONEST: only real,
    timestamped events count; a provider that never had an event gets nothing.

    Also returns the freshest stock-belief tick epoch so the caller can decide whether
    the stock floor is 'market closed' (item 2)."""
    last = {}
    stock_tick = None

    def bump(sid, ts):
        e = _parse_ts(ts)
        if e is None or sid is None or sid not in STATIONS:
            return
        if sid not in last or e > last[sid]:
            last[sid] = e

    # gene-pool routing (caller + provider)
    for r in _tail(CALLS, 200):
        bump(_sid(r.get("caller")), r.get("ts"))
        prov = (r.get("provider_used") or r.get("provider") or "").lower()
        if prov in STATIONS:
            bump(prov, r.get("ts"))
    # council flow: actor + any specialist named in a tool_selected + bench/sandbox
    for r in _tail(COUNCIL, 3000):
        ts = r.get("ts")
        bump(_sid(r.get("actor")), ts)
        ev = r.get("event")
        if ev == "tool_selected":
            bump(_tool_station(r.get("text")), ts)
        elif ev in ("sandbox_passed", "sandbox_rejected"):
            bump("tc_sandbox", ts)
            bump(_sid(r.get("submitter")), ts)
        elif ev == "bench_proposal":
            bump("f46_bench", ts); bump("wren", ts)
    # wren's local brain replies
    for r in _tail(REG / "qsb_wren_dash_chat.jsonl", 40):
        bump("wren_brain", r.get("ts")); bump("wren", r.get("ts"))
    # comms mesh
    for r in _tail(ROOM, 120):
        bump(_sid(r.get("from") or r.get("sender")), r.get("ts"))
    for r in _tail(ACKS, 120):
        bump(_sid(r.get("from")), r.get("ts")); bump(_sid(r.get("to")), r.get("ts"))
    for f in glob.glob(str(LC / "dm" / "*.jsonl")):
        nm = [_sid(x) for x in Path(f).stem.split("__")]
        for r in _tail(f, 12):
            for s in nm:
                bump(s, r.get("ts"))
    # trading floors: belief ticks -> venue floor; oanda fills; pot update
    for bf in glob.glob(str(BELIEF_DIR / "belief_state_belief_driven_*.json")):
        try:
            d = json.loads(Path(bf).read_text(errors="ignore"))
        except Exception:
            continue
        stem = Path(bf).stem
        sym = stem.split("__", 1)[1] if "__" in stem else ""
        venue = _venue_station(sym)
        tick_ts = (d.get("stream_evidence") or {}).get("last_tick_ts")
        bump(venue, tick_ts); bump("f10_traders", tick_ts)
        if venue == "f43_stocks":
            e = _parse_ts(tick_ts)
            if e is not None and (stock_tick is None or e > stock_tick):
                stock_tick = e
    for r in _tail(OANDA_HIST, 60):
        bump("f41_oanda", r.get("ts")); bump("f44_pnl", r.get("ts"))
    pot = _load(POT_FILE, {}) or {}
    if isinstance(pot, dict) and pot.get("updated_at"):
        bump("f44_pnl", pot.get("updated_at")); bump("f10_traders", pot.get("updated_at"))
    return last, stock_tick


def _feed_trains():
    """Read the shared traffic feed (qsb_map_traffic_feed.jsonl) into raw train dicts.
    Each real row becomes a train {from,to,ts,cat,label,source} once BOTH endpoints resolve
    to a station on the map. The age-gate + de-dupe + category caps in build() apply to these
    exactly like any other train, so a stale or unplaceable feed row never animates.

    HONESTY (R01): only rows with real!=false and a parseable ts and two placeable endpoints
    produce a train. Absent file -> []. Unknown category -> falls into a generic 'route' so it
    still draws, but the label always carries the row's own source so its origin is truthful.

    This is what spreads worker/routed/lift/system traffic ACROSS the whole building: feed rows
    reference floor numbers all over the tower, so their trains land on stations in every
    zone/column band, not just the curated-left trunks."""
    if not MAP_FEED.exists():
        return []
    out = []
    # tail generously — the age-gate downstream trims to the real window; the feed can be busy.
    for r in _tail(MAP_FEED, 4000):
        if not isinstance(r, dict):
            continue
        if r.get("real") is False:      # explicitly-marked non-real row -> never a train
            continue
        a = _feed_sid(r.get("from"))
        b = _feed_sid(r.get("to"))
        if not a or not b or a == b:    # both endpoints must place on the map, and differ
            continue
        cat = str(r.get("cat") or "route").strip().lower()
        if cat not in CAT_COLOR:        # unknown category -> generic route colour, still drawn
            cat = "route"
        src = r.get("source") or "feed"
        lab = r.get("label") or (str(r.get("from")) + " → " + str(r.get("to")))
        out.append({"from": a, "to": b, "ts": r.get("ts"), "cat": cat,
                    "label": str(lab)[:120], "source": str(src)[:40], "feed": True})
    return out


def _bfs_diameter(nodes, adj):
    """Return (all_reachable, diameter) for an undirected graph over `nodes`/`adj`.
    Diameter is measured over the connected component(s) that exist (unreachable
    pairs are ignored for the max-distance, but flagged via all_reachable)."""
    diam = 0
    reach_ok = True
    for s in nodes:
        d = {s: 0}
        q = deque([s])
        while q:
            x = q.popleft()
            for y in adj.get(x, ()):
                if y not in d:
                    d[y] = d[x] + 1
                    q.append(y)
        if len(d) < len(nodes):
            reach_ok = False
        if d:
            diam = max(diam, max(d.values()))
    return reach_ok, diam


# The connectivity report describes the CURATED network only (the 34 nodes wired by
# LINES). Elevation floor stations are presence-only (no LINES of their own), so
# including them would falsely report ~136 "isolated" nodes and inflate the station
# count. Connectivity is measured over the curated set exactly as before the merge.
def _curated_nodes():
    return {sid for sid in STATIONS if sid not in FLOOR_STATION_IDS}


def _connectivity():
    """STRUCTURAL connectivity: BFS over the hardcoded LINES lattice (the DRAWING).
    This is true of the drawn graph — NOT a claim that parties actually talk.
    Measured over the CURATED 34-node network (floor elevation stations excluded)."""
    nodes = _curated_nodes()
    adj = {}
    for a, b, *_ in LINES:
        if a in nodes and b in nodes:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    reach_ok, diam = _bfs_diameter(nodes, adj)
    edges = len({tuple(sorted((a, b))) for a, b, *_ in LINES if a in nodes and b in nodes})
    isolated = [n for n in nodes if not adj.get(n)]
    return {"stations": len(nodes), "edges": edges,
            "connected": reach_ok and not isolated, "diameter": diam,
            "isolated": isolated}


def _observed_connectivity(trains):
    """OBSERVED connectivity: BFS over ONLY the edges that carried a REAL (age-gated)
    train in the window. Reports how much of the tower is actually talking, which
    tracks carried traffic, how many CEO/hub pairs actually spoke, and which
    stations are genuinely isolated (codex/lumen/oracle/f46_bench WILL show up).
    Measured over the CURATED network (floor elevation stations excluded — they are
    presence-only and never carry a train)."""
    nodes = _curated_nodes()
    structural = {tuple(sorted((a, b))) for a, b, *_ in LINES if a in nodes and b in nodes}
    adj = {}
    live_edges = set()
    active_stations = set()
    for t in trains:
        a, b = t.get("from"), t.get("to")
        if a in nodes and b in nodes and a != b:
            e = tuple(sorted((a, b)))
            live_edges.add(e)
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
            active_stations.add(a); active_stations.add(b)
    reach_ok, diam = _bfs_diameter(active_stations or nodes, adj)
    isolated = sorted(n for n in nodes if n not in active_stations)
    # CEO/hub pairs actually talking: both endpoints are a CEO/AI or a hub (not a
    # degree-1 provider leaf) and the edge carried a real train.
    peers = set(CORE) | set(HUBS) | {"wren_brain", "task_council", "council15", "oracle"}
    talking_pairs = sorted(e for e in live_edges if e[0] in peers and e[1] in peers)
    tracks_used = len(live_edges & structural)
    return {"stations_total": len(nodes), "stations_active": len(active_stations),
            "tracks_drawn": len(structural), "tracks_used": tracks_used,
            "talking_pairs": len(talking_pairs), "diameter": diam,
            "all_active_reach": reach_ok, "isolated": isolated,
            "talking_pairs_list": ["↔".join(e) for e in talking_pairs]}


def build():
    trains = []
    prov_status = _provider_status()
    # LUMEN F48 liveness (2026-07-29): lumen was hard-coded offline (:8848 down). Probe the
    # real service — if :8848 answers, treat lumen as ONLINE/reachable, NOT offline/dead.
    # Honest: reflects the live probe, self-corrects both ways if the service stops again.
    lumen_up = _http_up("http://127.0.0.1:8848/")
    # 1) gene-pool routing: a real call is a ROUND TRIP — request goes out, the reply comes
    #    back (reply_head proves a real answer returned). Draw BOTH legs so tracks flow BOTH
    #    ways, not one-way blips: caller→gene_pool→provider (request) and provider→gene_pool→caller (reply).
    for r in _tail(CALLS, 70):
        caller = r.get("caller")
        frm = _sid(caller) or "boardroom"
        prov = (r.get("provider_used") or r.get("provider") or "").lower()
        ts = r.get("ts")
        got_reply = bool(r.get("reply_head"))
        # outbound request
        if frm != "gene_pool":
            trains.append({"from": frm, "to": "gene_pool", "ts": ts, "cat": "route",
                           "label": (caller or "?") + " → Gene Pool  (request)"})
        if prov in STATIONS:
            trains.append({"from": "gene_pool", "to": prov, "ts": ts, "cat": "provider",
                           "label": "Gene Pool → " + prov + "  (request)"})
            # return: the provider genuinely answered (reply_head) — reply travels back
            if got_reply:
                trains.append({"from": prov, "to": "gene_pool", "ts": ts, "cat": "provider",
                               "label": prov + " → Gene Pool  (reply)"})
        if got_reply and frm != "gene_pool":
            trains.append({"from": "gene_pool", "to": frm, "ts": ts, "cat": "route",
                           "label": "Gene Pool → " + (caller or "?") + "  (reply)"})
    # 2) council flow
    # 2026-07-29 (audit fix): widened 90 -> 1000. The live-workers daemon writes ~30-60
    # rows/min, which crowded lower-frequency real workers (codex ~1/min, wren_brain,
    # f46_bench) out of a 90-row window and made them look isolated. 1000 rows covers the
    # full 900s age-gate window at flood rate, so every real worker within it stays visible.
    for r in _tail(COUNCIL, 1000):
        ev, actor, tid = r.get("event"), r.get("actor"), r.get("task_id")
        seg = None
        if actor == "codex" and ev in ("created", "claimed", "assigned", "noted", "updated", "recycled", "done"):
            # codex does real work every tick (claim/note) — light his station like Wren's (fix: was created-only)
            seg = ("codex", "task_council")
        elif ev == "tool_selected":
            seg = ("task_council", "council15")
        elif ev in ("sandbox_passed", "awaiting_verification", "peer_signoff"):
            seg = ("task_council", "gene_pool")
        elif actor == "wren" and ev in ("claimed", "assigned", "blocked", "recycled", "done", "noted"):
            seg = ("wren", "task_council")
        elif actor == "bill":
            seg = ("bill", "task_council")
        elif actor == "oracle":
            # Oracle Cloud VM live worker (2026-07-29): its noted(actor=oracle) health event
            # lights oracle -> task_council. Real: only fires when the SSH round-trip returned.
            seg = ("oracle", "task_council")
        elif actor in ("tp_pip", "acer_cass"):
            seg = (actor, "task_council")
        if seg:
            trains.append({"from": seg[0], "to": seg[1], "ts": r.get("ts"), "cat": "council",
                           "label": (actor or "?") + " " + (ev or "") + " " + (tid or "")})
        # 2026-07-29 Ross: when a worker does real TRADING-related work, draw its track to the
        # trading hub F10 — a real worker->trading-floor train (honest: only on trading work).
        _txt = (r.get("text") or "").lower()
        if actor in ("bill", "codex", "tp_pip", "acer_cass") and \
           any(k in _txt for k in ("trad", "fleet", "pnl", "oanda", "broker", "trader")):
            trains.append({"from": actor, "to": "f10_traders", "ts": r.get("ts"),
                           "cat": "trade", "label": (actor or "?") + " → trading floors"})
        # SUB-TRACK trains
        if ev == "tool_selected":
            spec = _tool_station(r.get("text"))
            # ROUND TRIP: the specialist is wielded (send) AND returns its result (reply) — both legs real
            trains.append({"from": "council15", "to": spec, "ts": r.get("ts"), "cat": "c15",
                           "label": "Council of 15 → " + spec})
            trains.append({"from": spec, "to": "council15", "ts": r.get("ts"), "cat": "c15",
                           "label": spec + " → Council of 15 (result)"})
            trains.append({"from": "wren", "to": spec, "ts": r.get("ts"), "cat": "wrensub",
                           "label": "Wren wields " + spec})
            trains.append({"from": spec, "to": "wren", "ts": r.get("ts"), "cat": "wrensub",
                           "label": spec + " → Wren (result)"})
        elif ev in ("sandbox_passed", "sandbox_rejected"):
            # ROUND TRIP: submitter runs code through the sandbox (send) AND the sandbox returns
            # its pass/fail verdict (reply) — both are real events. Attribute to the real submitter.
            _sub = _sid(r.get("submitter")) or "task_council"
            _who = _sub if _sub != "task_council" else "council"
            trains.append({"from": _sub, "to": "tc_sandbox", "ts": r.get("ts"), "cat": "council",
                           "label": _who + " → sandbox " + (ev or "")})
            trains.append({"from": "tc_sandbox", "to": _sub, "ts": r.get("ts"), "cat": "council",
                           "label": "sandbox → " + _who + " verdict: " + (ev or "")})
        elif ev == "bench_proposal":
            # F46 workshop bench: Wren proposes code, runs it through the bench sandbox, and the
            # bench returns a real green/red verdict. ROUND TRIP: Wren -> F46 bench (proposal) and
            # F46 bench -> Wren (verdict). Both legs are REAL (a proposal was actually sandboxed).
            trains.append({"from": "wren", "to": "f46_bench", "ts": r.get("ts"), "cat": "wrensub",
                           "label": "Wren → F46 bench (proposal)"})
            trains.append({"from": "f46_bench", "to": "wren", "ts": r.get("ts"), "cat": "wrensub",
                           "label": "F46 bench → Wren (" + (r.get("text") or "verdict") + ")"})
        elif ev == "done":
            trains.append({"from": "task_council", "to": "wren", "ts": r.get("ts"), "cat": "council",
                           "label": "Wren gate: done " + (tid or "")})
    # Wren's own brain (her local qwen replies)
    for r in _tail(REG / "qsb_wren_dash_chat.jsonl", 20):
        if r.get("reply") or (r.get("role") or r.get("from") or "").lower() == "wren":
            # ROUND TRIP: Wren asks her local brain (send) and the thought returns (reply)
            trains.append({"from": "wren", "to": "wren_brain", "ts": r.get("ts", ""), "cat": "wrensub",
                           "label": "Wren thinking · qwen14b"})
            trains.append({"from": "wren_brain", "to": "wren", "ts": r.get("ts", ""), "cat": "wrensub",
                           "label": "qwen14b → Wren (thought)"})
    # 3) comms mesh: room -> town square, acks between members, DMs member<->member
    for r in _tail(ROOM, 60):
        frm = _sid(r.get("from") or r.get("sender")) or "boardroom"
        trains.append({"from": frm, "to": "town_square", "ts": r.get("ts", ""), "cat": "comms",
                       "label": STATIONS[frm]["label"].split(" ·")[0] + " → square"})
    for r in _tail(ACKS, 60):
        frm, to = _sid(r.get("from")), _sid(r.get("to"))
        if frm and to and frm != to:
            trains.append({"from": frm, "to": to, "ts": r.get("ts", ""), "cat": "comms",
                           "label": frm + " → " + to + " ack"})
    for f in glob.glob(str(LC / "dm" / "*.jsonl")):
        nm = [_sid(x) for x in Path(f).stem.split("__")]
        if len(nm) == 2 and nm[0] and nm[1] and nm[0] != nm[1]:
            for r in _tail(f, 8):
                frm = _sid(r.get("from")) or nm[0]
                to = nm[1] if frm == nm[0] else nm[0]
                trains.append({"from": frm, "to": to, "ts": r.get("ts", ""), "cat": "comms",
                               "label": frm + " ↔ " + to + " DM"})
    # 3a2) BOARDROOM DIALOGUE (STAGING3, 2026-07-30): qsb_boardroom_commentary.jsonl is the
    #     tower's MAIN conversation stream (231k rows, appended every few seconds) and the live
    #     map never read it. Each row {ts, who, kind, text} is a real post BY `who` INTO the
    #     boardroom — a directional who -> boardroom train, age-gated + de-duped like the rest.
    #     Only speakers that resolve to a real station ride (wren/ross/hq/claude/iquest/forge);
    #     unmappable speakers (system, iris, …) are DROPPED by _sid — never faked (R01).
    for r in _tail(BOARDROOM_COMMENTARY, 400):
        who = _sid(r.get("who") or r.get("speaker") or r.get("from"))
        if not who or who == "boardroom":
            continue
        txt = (r.get("text") or "").replace("\n", " ").strip()
        nm = STATIONS[who]["label"].split(" ·")[0]
        trains.append({"from": who, "to": "boardroom", "ts": r.get("ts", ""), "cat": "boardroom",
                       "label": nm + " → boardroom" + ((": " + txt[:56]) if txt else "")})
    # 3a3) DELIVERY RECEIPTS (STAGING3, 2026-07-30): leadership_comms/delivered/{owner}.jsonl
    #     rows are {msg_id, kind, from, to, ts, body, delivered_at} — a PROVEN delivery: message
    #     `from` was actually delivered to the file OWNER at delivered_at. This is the REVERSE-LEG
    #     evidence the two-way classifier was starving for: from -> owner is a real directional
    #     train. bill->wren (in delivered/wren) AND wren->bill (in delivered/bill) both exist on
    #     disk, so honest CONFIRMED two-way lands with real receipts — no invented return lane.
    #     The worker_needs_queue -> wren monitoring roll-up rides here for free (real `from`).
    for f in glob.glob(str(DELIVERED_DIR / "*.jsonl")):
        owner = _sid(Path(f).stem)
        if not owner:
            continue
        for r in _tail(f, 80):
            frm = _sid(r.get("from"))
            if not frm or frm == owner:
                continue
            ts = r.get("delivered_at") or r.get("ts")
            kind = r.get("kind") or "delivered"
            trains.append({"from": frm, "to": owner, "ts": ts, "cat": "delivered",
                           "label": frm + " → " + owner + " · " + kind + " delivered"})
    # 3b) TRADING FLOORS — REAL trader events only, age-gated by the shared gate below.
    #     · belief_state_*.json  : each live trader brain's last tick -> F10 → its venue floor
    #     · qsb_oanda_history.jsonl : each real practice fill -> F41 → F44 (PnL sink)
    #     · qsb_portfolio_pot.json  : a real pot/PnL update    -> F44 → F10 (result back)
    #     Instrument is embedded in the belief_state filename: ...belief_driven_<name>__<SYMBOL>.json
    _fleet_tick_max = None       # freshest real trader tick -> feeds the Wren-governor train
    for bf in sorted(glob.glob(str(BELIEF_DIR / "belief_state_belief_driven_*.json"))):
        try:
            d = json.loads(Path(bf).read_text(errors="ignore"))
        except Exception:
            continue
        stem = Path(bf).stem  # belief_state_belief_driven_<name>__<SYMBOL>
        sym = stem.split("__", 1)[1] if "__" in stem else ""
        venue = _venue_station(sym)
        tick_ts = (d.get("stream_evidence") or {}).get("last_tick_ts")
        wr = (d.get("strategy_fitness") or {}).get("win_rate")
        wtxt = f" · win {round(wr*100)}%" if isinstance(wr, (int, float)) else ""
        # a fresh belief tick is REAL live strategy activity: F10 dispatches → the venue floor.
        trains.append({"from": "f10_traders", "to": venue, "ts": tick_ts, "cat": "trade",
                       "label": sym + " belief tick → " + STATIONS[venue]["label"].split(" ·")[0] + wtxt})
        if tick_ts and (_fleet_tick_max is None or tick_ts > _fleet_tick_max):
            _fleet_tick_max = tick_ts
    # Wren is the traders' GOVERNOR ("Wren · 46"): a fresh fleet tick means the fleet reports
    # up to Wren and she oversees it — a REAL 2-way track F10 <-> Wren, age-gated like the rest.
    if _fleet_tick_max:
        trains.append({"from": "f10_traders", "to": "wren", "ts": _fleet_tick_max,
                       "cat": "trade", "label": "trader fleet → Wren (governor · 46)"})
        trains.append({"from": "wren", "to": "f10_traders", "ts": _fleet_tick_max,
                       "cat": "trade", "label": "Wren oversees the trading floors"})
    # real OANDA practice fills: each fill is a real train F41 → F44 (booked into the pot)
    for r in _tail(OANDA_HIST, 40):
        inst = r.get("instrument") or "?"
        pl = r.get("pl")
        pltxt = (f" pl {round(pl, 4)}" if isinstance(pl, (int, float)) else "")
        trains.append({"from": "f41_oanda", "to": "f44_pnl", "ts": r.get("ts"), "cat": "trade",
                       "label": "OANDA fill " + str(inst) + pltxt + " → PnL"})
    # real pot/PnL update: F44 → F10 (the pot result flows back to the trading hub)
    pot = _load(POT_FILE, {}) or {}
    if isinstance(pot, dict) and pot.get("updated_at"):
        committed = pot.get("committed_gbp"); cap = pot.get("cap_gbp")
        ptxt = (f" £{round(committed)}/£{round(cap)}" if isinstance(committed, (int, float))
                and isinstance(cap, (int, float)) else "")
        trains.append({"from": "f44_pnl", "to": "f10_traders", "ts": pot.get("updated_at"),
                       "cat": "trade", "label": "pot update" + ptxt + " → Traders"})

    # 3c) SHARED TRAFFIC FEED (2026-07-29): sibling tools stream real worker/routed/lift/
    #     system traffic into qsb_map_traffic_feed.jsonl referencing floor numbers + hub ids
    #     ALL OVER the tower. Rendering these is what spreads bright trains through the WHOLE
    #     building instead of just the curated-left trunk. Each row is age-gated + de-duped +
    #     capped downstream exactly like the curated trains, so nothing stale/fake animates.
    #     Tag them cat="feed" ONLY when the row didn't name a known category, so we can give
    #     feed traffic its own generous cap and it never gets crowded out by the curated caps.
    for _ft in _feed_trains():
        trains.append(_ft)

    # 4) NO liveprobe trains (audit fix #2). A health-probe pass is NOT routed work.
    #    Providers that pass the probe get a green "reachable" RING (station attribute,
    #    attached below), never a fabricated train. Only real routing jobs (step 1)
    #    produce provider trains.

    # ── AGE-GATE (audit fix #1): drop any train missing a ts or older than AGE_MAX.
    #    This is what makes a quiet line STILL. Attach age_s to every survivor.
    #    MUST run BEFORE the category balancer — otherwise the balancer's raw
    #    list-position slice throws away FRESH trains from a source that was
    #    appended early (room posts are built before acks/DMs, so a naive [-K:]
    #    kept 24 stale DMs and sliced off every recent Bill→town_square post
    #    before the age-gate ever saw it). Gate on real recency first. ──
    now = time.time()
    gated = []
    for t in trains:
        te = _parse_ts(t.get("ts"))
        if te is None:
            continue  # no ts -> cannot prove recency -> never animate
        age = now - te
        # PER-CATEGORY age gate (2026-07-29): routing/comms/council are high-cadence, so a 900s
        # window is right — a quiet line goes still fast. The TRADING floor is inherently
        # slower-cadence: the live 50-trader fleet (systemd, 48 procs proven up) only writes a
        # fresh belief tick when the market actually moves, and FX/commodity ticks can be sparse
        # (proven: 0 ticks <900s but 40 REAL ticks <1h right now — the fleet is ALIVE, just between
        # market moves). Gating `trade` at 900s made a genuinely-live fleet flicker fully dark
        # between ticks and dropped Ross's must-have wren/codex↔traders trains. So `trade` trains
        # get the GHOST window (3600s) — still a REAL, timestamped fleet event, and the label
        # carries its true age so nothing is misrepresented as "just now". No fabrication: a train
        # with no real backing event never enters this list at all.
        # trade + floorflow are inherently slower-cadence real sources (a floor writes an
        # activity row when it actually does work; the fleet ticks when the market moves), so
        # they get the GHOST window (3600s). Everything else uses the tight 900s window.
        cap = GHOST_MAX if t.get("cat") in ("trade", "floorflow") else AGE_MAX
        if age > cap or age < -60:  # too old for its category, or absurd future ts
            continue
        t["age_s"] = int(max(0, age))
        gated.append(t)
    trains = gated

    # ── DE-DUPLICATE (audit fix #5): collapse identical (from,to,label) to one,
    #    keeping the freshest instance, so a week-old DM can't fire ×7. ──
    _best = {}
    for t in trains:
        key = (t["from"], t["to"], t.get("label", ""))
        prev = _best.get(key)
        if prev is None or t.get("age_s", 1e9) < prev.get("age_s", 1e9):
            _best[key] = t
    trains = list(_best.values())

    # ── SPLIT feed traffic OUT of the curated caps (2026-07-29). The shared feed carries the
    #    tower-wide worker/routed/lift/system traffic that must spread across the WHOLE map;
    #    if it shared the curated route/comms K=24 buckets it would be crowded out and pool on
    #    the left again. So feed trains get their OWN generous per-edge-fair cap (below) and the
    #    curated caps only balance the curated sources. Both are still age-gated + de-duped. ──
    _feed_bucket = [t for t in trains if t.get("feed")]
    _curated = [t for t in trains if not t.get("feed")]
    # balance categories so routing traffic doesn't DROWN the comms mesh.
    # Cap by FRESHNESS (smallest age_s first), NOT list position, so a genuinely
    # recent room post always beats an older DM when the cap bites (bug #1 fix).
    _bc = {}
    for t in _curated:
        _bc.setdefault(t["cat"], []).append(t)
    trains = []
    # route/provider now carry BOTH request and reply legs — bigger cap so both directions show.
    # 2026-07-29 (hermes/iquest dark bug): c15/wrensub raised 8 -> 24. The specialist-liveness
    # daemon writes tool_selected for ~7 specialists (iquest/hermes/qwen_worker/claude_acct/…),
    # each a 2-leg round trip = ~14-18 real trains. The old cap of 8 kept only the 4 freshest
    # specialists and SLICED OFF hermes/iquest/claude_acct even though their events were fresh
    # (<900s) and real — making them look dark/isolated. All survivors are still age-gated, so
    # nothing fabricated enters; the cap now just stops crowding out real specialists.
    # PER-EDGE FAIRNESS: within c15/wrensub, keep the freshest train for EACH distinct edge
    # first (so every real specialist that fired gets its rail lit), then backfill by freshness.
    def _cap_fair(bucket, K):
        bucket = sorted(bucket, key=lambda t: t.get("age_s", 1e9))
        best_per_edge, rest = {}, []
        for t in bucket:
            e = (t["from"], t["to"])
            if e not in best_per_edge:
                best_per_edge[e] = t
            else:
                rest.append(t)
        out = list(best_per_edge.values())[:K]
        for t in rest:
            if len(out) >= K:
                break
            out.append(t)
        return out
    # STAGING3: boardroom + delivered get PER-EDGE-FAIR caps (like c15/wrensub) so EVERY real
    # speaker->boardroom edge and EVERY real reverse-leg delivery pair lights up — that per-edge
    # fairness is exactly what lets the two-way classifier see both legs where they genuinely
    # exist, instead of a freshness slice starving out a real reverse leg.
    for cat, K in (("route", 24), ("provider", 24), ("comms", 24),
                   ("council", 12), ("c15", 24), ("wrensub", 24), ("trade", 60),
                   ("boardroom", 30), ("delivered", 60)):
        bucket = _bc.get(cat, [])
        if cat in ("c15", "wrensub", "boardroom", "delivered"):
            trains += _cap_fair(bucket, K)
        else:
            trains += sorted(bucket, key=lambda t: t.get("age_s", 1e9))[:K]
    # any curated category NOT in the balanced tuple above (hub/lift/mesh) — keep it, capped,
    # so a real curated train of an unlisted category is never silently dropped.
    _balanced = {"route", "provider", "comms", "council", "c15", "wrensub", "trade",
                 "boardroom", "delivered"}
    for cat, bucket in _bc.items():
        if cat not in _balanced:
            trains += sorted(bucket, key=lambda t: t.get("age_s", 1e9))[:24]

    # ── FEED CAP (per-edge fair + anti-blob per-endpoint ceiling) — this is the tower-wide
    #    spread. First keep the freshest train for EACH distinct feed edge (so every station-pair
    #    the feed touched lights up SOMEWHERE on the map), but ENFORCE a per-endpoint ceiling so
    #    no single node becomes a pile-up blob: the real feed funnels ~all worker-need/chain rows
    #    at the F46 bench + Wren, which would pin 150+ trains on two nodes and re-cluster the map.
    #    Capping trains-per-endpoint keeps the distribution even AND stays honest (we still draw a
    #    representative real train for each busy edge; the true event counts live in the labels). ──
    def _cap_feed(bucket, per_edge_cap, per_node_cap, total_cap):
        bucket = sorted(bucket, key=lambda t: t.get("age_s", 1e9))
        node_ct = Counter()
        edge_ct = Counter()
        out = []
        for t in bucket:
            if len(out) >= total_cap:
                break
            e = (t["from"], t["to"])
            if edge_ct[e] >= per_edge_cap:
                continue
            # per-endpoint ceiling on BOTH ends -> no single station absorbs the whole feed
            if node_ct[t["from"]] >= per_node_cap or node_ct[t["to"]] >= per_node_cap:
                continue
            out.append(t)
            edge_ct[e] += 1
            node_ct[t["from"]] += 1
            node_ct[t["to"]] += 1
        return out
    trains += _cap_feed(_feed_bucket, per_edge_cap=2, per_node_cap=14, total_cap=400)

    trains.sort(key=lambda t: t.get("ts") or "")

    # presence -> online glow
    pres = _load(PRESENCE, {}) or {}
    online = {}
    for k, v in (pres.items() if isinstance(pres, dict) else []):
        if isinstance(v, dict) and v.get("last_heartbeat_epoch"):
            sid = PRES_MAP.get(k, k)
            if sid in STATIONS and (time.time() - v["last_heartbeat_epoch"]) < 120:
                online[sid] = True

    # `act` is now sourced ONLY from real, age-gated, de-duped trains (audit fix #4).
    act = Counter((t["from"], t["to"]) for t in trains)
    # stations that actually carried a real train in the window
    traffic_stations = set()
    for t in trains:
        traffic_stations.add(t["from"]); traffic_stations.add(t["to"])

    # ── IDLE-GHOST source (item 1) + STOCK market-closed source (item 2) ──
    # Per-station last-REAL-event epoch, computed from the SAME logs the trains come
    # from but WITHOUT the animated category caps — so a node crowded out of the
    # capped animated set still shows its true recency. A station with no live train
    # (has_traffic False) but a real event inside GHOST_MAX renders DIM ("Xm ago").
    last_event, stock_tick = _station_last_event()
    now_ge = time.time()
    # stock floor is "market closed" when its freshest belief tick is stale (after-hours).
    stock_closed = (stock_tick is None) or ((now_ge - stock_tick) > STOCK_STALE)

    # ── FLOOR ACTIVITY INDEX (2026-07-29) ────────────────────────────────────────
    # Honest lighting for the 170 elevation floors: a floor lights ONLY if the sibling
    # activity index marks it active with a real recent ts. The index is keyed by floor
    # STATION id (fN_slug); we also accept keying by "fN" / bare floor number as a
    # convenience. Absent file / absent floor -> that floor stays DIM (idle). We never
    # fabricate activity — no index entry means no light.
    _fa_raw = _load(FLOOR_ACT, {}) or {}
    # real schema: {'floors': {'floor_<n>': {active,last_ts,age_s,source,label,signal}}}
    floor_act = _fa_raw.get("floors", _fa_raw) if isinstance(_fa_raw, dict) else {}
    floor_num_by_id = {sid: STATIONS[sid].get("floor_num") for sid in FLOOR_STATION_IDS}

    def _floor_activity(sid):
        """Return (active_bool, last_ts) for a floor station from the index, honestly.
        Real index is keyed 'floor_<n>'. Tries that, then the station id, then 'f<num>'
        / bare number. A floor lights ONLY on a truthy `active` with a parseable ts inside
        GHOST_MAX — no index entry / no active flag == idle (never fabricated)."""
        if not isinstance(floor_act, dict):
            return False, None
        num = floor_num_by_id.get(sid)
        rec = None
        for key in (f"floor_{num}" if num is not None else None, sid,
                    f"f{num}" if num is not None else None,
                    str(num) if num is not None else None):
            if key and isinstance(floor_act.get(key), dict):
                rec = floor_act[key]; break
        if not isinstance(rec, dict):
            return False, None
        ts = rec.get("last_ts") or rec.get("ts")
        e = _parse_ts(ts)
        active = bool(rec.get("active")) and e is not None and (now_ge - e) <= GHOST_MAX
        return active, ts

    # attach LIVE/DEAD provider status + honest reachable/traffic flags to each station
    stations = {}
    for sid, s in STATIONS.items():
        s2 = dict(s)
        # ── ELEVATION FLOOR STATION: presence-only, dim by default, lit ONLY on real
        #    activity from the floor activity index. No provider status, no train logic,
        #    no silent/ghost misclassification. Fully honest: absent index -> idle. ──
        if s.get("floor"):
            active, last_ts = _floor_activity(sid)
            s2["idle"] = not active
            s2["has_traffic"] = False   # floors carry no trains of their own (honest)
            s2["valid"] = True
            if active:
                s2["floor_active"] = True
                s2["floor_last_ts"] = last_ts
                s2["has_traffic"] = True
                age = _parse_ts(last_ts)
                if age is not None:
                    a = int(max(0, now_ge - age))
                    s2["last_active_label"] = (f"{max(1, a // 60)}m ago" if a >= 60 else f"{a}s ago")
                # 2026-07-29 (Ross: "all floors live with their own trains"): each ACTIVE floor
                # emits its OWN real train toward the task-council work hub, sourced from the SAME
                # activity index that lit it (real last_ts + real signal). Idle floors stay dim —
                # no train is fabricated for a floor with no real signal (R01 / no sims).
                _rec = floor_act.get(f"floor_{floor_num_by_id.get(sid)}") if isinstance(floor_act, dict) else None
                _sig = (_rec or {}).get("signal") or (_rec or {}).get("source") or "activity"
                # route each floor's train to its NEAREST neighbour floor — short visible hops on
                # the uniform grid (floors talking floor-to-floor, spread across the building)
                # instead of 160+ piling invisibly on one hub. (2026-07-29, Ross: "wheres the trains")
                _sx, _sy = s.get("x", 0), s.get("y", 0)
                _to, _bd = None, None
                for _fid, _fs in STATIONS.items():
                    if _fid == sid or not _fs.get("floor") or _fs.get("x") is None:
                        continue
                    _dd = (_fs["x"] - _sx) ** 2 + (_fs["y"] - _sy) ** 2
                    if _bd is None or _dd < _bd:
                        _bd, _to = _dd, _fid
                # cat="floorflow": floor-origin traffic gets its OWN bright category (below) so
                # active floor tracks are as visually prominent as the curated trunks (Ross:
                # floor connections were too faint). Honest: only ACTIVE floors emit this.
                # These are appended AFTER the age-gate/dedupe, so we set age_s here directly
                # (from the same real last_ts that lit the floor) — the client stream engine
                # needs age_s to flow a carriage, and _floor_activity already proved recency.
                _fage = _parse_ts(last_ts)
                trains.append({"from": sid, "to": _to or "task_council", "ts": last_ts,
                               "cat": "floorflow", "label": f"{s.get('label', sid)} · {_sig}",
                               "age_s": int(max(0, now_ge - _fage)) if _fage is not None else 0})
            stations[sid] = s2
            continue
        # LUMEN live-probe override (2026-07-29): when :8848 answers, clear the hard-coded
        # offline flag + reachable ring so lumen reads ONLINE (honest, from the real probe).
        _is_known_dead = sid in KNOWN_DEAD
        if sid == "lumen" and lumen_up:
            s2.pop("offline", None); s2.pop("offline_reason", None)
            s2["reachable"] = True
            s2["probe_online"] = True
            _is_known_dead = False
        if s.get("prov"):
            ps = prov_status.get(sid)
            if ps:
                st = ps["status"]
                s2["status"] = st
                s2["status_detail"] = ps["detail"]
                s2["status_band"] = ("live" if st in STATUS_LIVE
                                     else "amber" if st in STATUS_AMBER
                                     else "dead" if st in STATUS_DEAD else "unknown")
            else:
                s2["status"] = "NO_KEY"; s2["status_detail"] = "not in key-health report"
                s2["status_band"] = "dead"
            # audit fix #2: probe-pass => green "reachable" RING, NOT a train.
            s2["reachable"] = (s2["status_band"] == "live")
        # real recent routing/comms traffic (drives train motion + bright rails)
        s2["has_traffic"] = sid in traffic_stations
        # ── VALIDITY (item 1): honest can-it-carry-real-traffic classification ──
        # VALID if (LIVE-keyed provider) OR (non-provider not in known-dead set)
        #          OR (ever appeared as a real train endpoint this window).
        # INVALID otherwise, with an honest reason.
        if s.get("prov"):
            band = s2.get("status_band", "unknown")
            if band == "live":
                s2["valid"] = True; s2["invalid_reason"] = ""
            else:
                st = s2.get("status", "?")
                s2["valid"] = False
                s2["invalid_reason"] = ("dead-key provider (" + str(st) + ")"
                                        + (" · " + s2["status_detail"] if s2.get("status_detail") else ""))
        elif _is_known_dead:
            s2["valid"] = False
            s2["invalid_reason"] = KNOWN_DEAD_REASON.get(sid, "known-dead node — no event source")
        else:
            s2["valid"] = True; s2["invalid_reason"] = ""
        # a station that carried a real train this window is VALID no matter what
        # the static rule said (it demonstrably sent/received real traffic).
        if s2["has_traffic"] and not s2["valid"]:
            s2["valid"] = True
            s2["invalid_reason"] = ""
        # audit fix #6: bill heartbeats on the comms relay but carries ~0 tower traffic.
        # Mark comms-online distinctly from a CEO actually carrying trains.
        if online.get(sid) and not s2["has_traffic"]:
            s2["comms_online"] = True
        # ── IDLE-GHOST tier (item 1) ────────────────────────────────────────────
        # A station with NO live train (has_traffic False) but a REAL event inside
        # GHOST_MAX is idle-but-alive: render DIM with an "Xm ago" label instead of
        # fully dark. HONEST — only a genuine, timestamped recent event qualifies.
        # A truly-dead provider (band != live: NO_KEY/QUOTA/BLOCKED) never ghosts even
        # if it once appeared; and a node with no event at all stays fully dark.
        le = last_event.get(sid)
        if (not s2["has_traffic"] and le is not None and (now_ge - le) <= GHOST_MAX
                and not (s.get("prov") and s2.get("status_band") != "live")):
            age = int(now_ge - le)
            s2["ghost"] = True
            s2["last_active_s"] = age
            s2["last_active_label"] = (str(max(1, age // 60)) + "m ago" if age >= 60
                                       else str(age) + "s ago")
        # ── STOCK market-closed badge (item 2) ──────────────────────────────────
        # f43_stocks goes dark after-hours because there are no fresh stock ticks.
        # Label it WAITING ("stocks · closed") rather than broken; it self-lights
        # when real ticks return. Detected honestly from stale belief ticks above.
        if sid == "f43_stocks" and stock_closed and not s2["has_traffic"]:
            s2["market_closed"] = True
            s2.pop("silent", None)   # not broken — waiting
        # audit fix #4: truly-silent station (no train, not online) -> dim/dashed roundel.
        # A ghosted or market-closed station is NOT "silent" (it's idle/waiting, honest).
        if (not s2["has_traffic"] and not online.get(sid) and not s.get("offline")
                and not s2.get("ghost") and not s2.get("market_closed")):
            s2["silent"] = True
        stations[sid] = s2

    # ── RECOMPUTE act / traffic_stations AFTER the floor-flow trains were appended inside the
    #    station loop above. Those floor-to-floor trains are REAL (age-gated floor-activity
    #    events) but were added after the first `act` pass, so without this recompute their
    #    rails would stay dark and the floors would look connected-but-faint (Ross: too faint).
    #    Recomputing here lights every active floor's rail as brightly as the curated trunks. ──
    act = Counter((t["from"], t["to"]) for t in trains)
    traffic_stations = set()
    for t in trains:
        traffic_stations.add(t["from"]); traffic_stations.add(t["to"])

    # HONEST LIVE badge (audit fix #3): all `trains` are already age-gated to AGE_MAX,
    # so recent == the animated set. No inflation.
    recent = len(trains)

    # ── STABLE TRAIN IDS (STAGING, UG-02): give every animated train a stable-per-tick id
    #    so the frontend can hit-test a carriage back to its exact event. ──
    for _i, _t in enumerate(trains):
        _t["id"] = "tr_%d" % _i

    # ════════════════════════════════════════════════════════════════════════════
    # HONEST DIRECTION ANALYSIS (STAGING, UG-02 — the KEY R01 upgrade)
    # UG-01 audit finding: the live map's `twoway_routes` (48/51) counts 19 "floorflow"
    # beacon pairs as two-way. Those are NOT communication — each active floor emits ONE
    # train toward its geometric nearest-neighbour floor; when two floors are mutual
    # nearest-neighbours and both tick in the same activity index, you get A→B and B→A
    # from ONE mirrored tick, not two messages. So a track is TWO-WAY CONFIRMED here ONLY
    # when it carried a real DIRECTIONAL message (cat != floorflow) in BOTH directions.
    # floorflow-both pairs are reclassified "co-active, awaiting proof". One-legged pairs
    # are "one-way (return lane drawn, awaiting reverse proof)". Numbers derived, not
    # trusted: this reproduces UG-01's honest ~29 confirmed / 19 co-active / ~193 one-way.
    # ════════════════════════════════════════════════════════════════════════════
    from collections import defaultdict as _dd
    _pair = _dd(lambda: {"ab": [], "ba": []})   # key = tuple(sorted(a,b))
    for t in trains:
        a, b = t.get("from"), t.get("to")
        if not a or not b or a == b:
            continue
        key = tuple(sorted((a, b)))
        leg = "ab" if (a, b) == key else "ba"
        _pair[key][leg].append(t)

    def _leg_stat(rows):
        """Directional evidence for one leg: count, freshest ts/age, whether ANY row is a
        real directional message (cat != floorflow), and freshest human label."""
        if not rows:
            return {"count": 0, "last_ts": None, "last_age": None, "label": "", "has_msg": False,
                    "cats": []}
        fresh = min(rows, key=lambda r: r.get("age_s", 1e9))
        return {"count": len(rows),
                "last_ts": fresh.get("ts"),
                "last_age": fresh.get("age_s"),
                "label": fresh.get("label", ""),
                "has_msg": any((r.get("cat") != "floorflow") for r in rows),
                "cats": sorted({r.get("cat", "") for r in rows})}

    pair_dir = {}   # "a↔b" -> {a,b,ab,ba,dir,status,twoway_confirmed}
    n_confirmed = n_coactive = n_oneway = 0
    twoway_confirmed_list, coactive_list, oneway_list = [], [], []
    for key, legs in _pair.items():
        a, b = key
        ab = _leg_stat(legs["ab"])   # a -> b
        ba = _leg_stat(legs["ba"])   # b -> a
        both = ab["count"] > 0 and ba["count"] > 0
        # CONFIRMED two-way requires a REAL directional message BOTH ways (not floorflow beacon).
        confirmed = both and ab["has_msg"] and ba["has_msg"]
        if confirmed:
            status, direction = "confirmed", "both"
            n_confirmed += 1
            twoway_confirmed_list.append(a + "↔" + b)
        elif both:
            # both legs ran but at least one direction is only a floorflow activity beacon
            status, direction = "coactive", "both"
            n_coactive += 1
            coactive_list.append(a + "↔" + b)
        elif ab["count"] > 0:
            status, direction = "oneway", "ab"
            n_oneway += 1
            oneway_list.append(a + "→" + b)
        else:
            status, direction = "oneway", "ba"
            n_oneway += 1
            oneway_list.append(b + "→" + a)
        pair_dir[a + "↔" + b] = {"a": a, "b": b, "ab": ab, "ba": ba,
                                      "dir": direction, "status": status,
                                      "twoway_confirmed": confirmed}

    # ── THE 8 REAL-TELEMETRY COUNTERS (item 2) ──────────────────────────────────
    # Every number is derived from the SAME real, age-gated, de-duped `trains` and
    # the drawn `LINES`/`STATIONS`. No inflation: total_real_trains == len(trains),
    # tracks_proven == count of lines whose act>0 (both computed here, not restated).
    def _line_row(a, b, c):
        key = tuple(sorted((a, b)))
        pk = key[0] + "↔" + key[1]
        pd = pair_dir.get(pk)
        row = {"id": pk, "a": a, "b": b, "cat": c,
               "act": act.get((a, b), 0) + act.get((b, a), 0),
               "trunk": key in TRUNK_SET}
        if pd:
            # attach honest directional classification (STAGING, UG-02)
            row["dir"] = pd["dir"]                 # 'both' | 'ab' | 'ba'
            row["dir_status"] = pd["status"]       # 'confirmed' | 'coactive' | 'oneway'
            row["ab"] = pd["ab"]                   # a->b leg stats
            row["ba"] = pd["ba"]                   # b->a leg stats
        else:
            row["dir"] = None
            row["dir_status"] = "idle"             # drawn track, no real train in window
        return row
    lines_out = [_line_row(a, b, c) for a, b, c in LINES]
    # ── LIFT LINES (2026-07-29): the building's lift topology drawn as a distinct 'lift'
    #    category connecting the floor stations each lift serves (CLAUDE.md: inter-floor
    #    comms travel through lifts, so lifts ARE the floor-to-floor lines). Optional file;
    #    absent -> no lift lines (fallback). Proposed lifts flagged so the frontend can
    #    style them dashed/dimmer. These carry NO trains — they're structural floor rails,
    #    kept fully separate from the live trading/comms trains (which stay exactly as-is). ──
    for L in _load_lift_lines():
        lines_out.append({"a": L["a"], "b": L["b"], "cat": "lift", "act": 0, "trunk": False,
                          "lift_id": L.get("lift_id"), "color": L.get("color"),
                          "proposed": bool(L.get("proposed"))})
    # directed leg presence for two-way detection: (a,b) present AND (b,a) present.
    directed = {(t["from"], t["to"]) for t in trains}
    twoway = {tuple(sorted((a, b))) for (a, b) in directed if (b, a) in directed and a != b}
    # VALID / INVALID partitions from the classified `stations` dict above.
    # Scope the CURATED-network telemetry (isolated/invalid/active) to the curated 34 nodes:
    # the 170 elevation floors are presence-only (never carry a train), so counting them as
    # "isolated valid" would be misleading. Floors get their own counters below.
    _cur = _curated_nodes()
    invalid_ids = sorted(sid for sid, s in stations.items() if sid in _cur and not s.get("valid", True))
    valid_ids = [sid for sid, s in stations.items() if sid in _cur and s.get("valid", True)]
    # isolated = VALID curated stations that carried ZERO real trains (invalid ones excluded
    # here — they're reported separately under failed_routes).
    isolated_valid = sorted(sid for sid in valid_ids if sid not in traffic_stations)
    # floor counters (honest): how many of the 170 elevation floors are lit vs idle right now.
    _floor_ids = sorted(FLOOR_STATION_IDS)
    floors_lit = sorted(sid for sid in _floor_ids if stations.get(sid, {}).get("floor_active"))
    floors_total = len(_floor_ids) + len(CURATED_FLOOR_NUM)  # elevation + curated-as-floor = 170
    # ── MEANINGFUL vs full-mesh track split (item 3) ──────────────────────────────
    # `total_tracks` (528) counts the hidden structural mesh that will NEVER carry a
    # train — misleading as a headline. `meaningful_tracks` = the TRUNK backbone +
    # categorised (non-mesh) lines, i.e. the real routes a train can actually run.
    # The full mesh count stays available as `total_tracks`/`mesh_tracks`, just not
    # the headline number.
    meaningful_tracks = sum(1 for L in lines_out if L["cat"] != "mesh")
    mesh_tracks = sum(1 for L in lines_out if L["cat"] == "mesh")
    telemetry = {
        "total_stations":    len(STATIONS),
        "active_stations":   len(traffic_stations),
        # ── ALL-FLOORS counters (2026-07-29): every one of the 170 tower floors is on the
        #    map now (curated + elevation). floors_lit = only those with REAL recent activity
        #    from the floor activity index; the rest are honestly idle/dim. ──
        "floors_total":      floors_total,
        "floors_elevation":  len(_floor_ids),
        "floors_lit":        len(floors_lit),
        "floors_lit_list":   floors_lit,
        "total_tracks":      len(lines_out),
        "meaningful_tracks": meaningful_tracks,
        "mesh_tracks":       mesh_tracks,
        "tracks_proven":     sum(1 for L in lines_out if L["act"] > 0),
        "total_real_trains": len(trains),
        "isolated_stations": len(isolated_valid),
        "isolated_list":     isolated_valid,
        "failed_routes":     len(invalid_ids),
        "failed_list":       [{"id": i, "reason": stations[i].get("invalid_reason", "")} for i in invalid_ids],
        # RAW detector (kept for parity with live :8875 — counts floorflow beacons too).
        # NOT the headline number on staging; the honest split below is.
        "twoway_routes":     len(twoway),
        "twoway_list":       ["↔".join(e) for e in sorted(twoway)],
        # ── HONEST TWO-WAY SPLIT (STAGING, UG-02) — the R01 correction ──────────────
        # twoway_confirmed = real directional message BOTH ways (cat != floorflow). This
        # is the number to trust (~29). coactive_awaiting = both legs ran but ≥1 is only a
        # floorflow activity beacon — co-active, NOT proven communication (~19). The 19
        # +  29 == the raw 48 the live map shows, split honestly. oneway_awaiting = a train
        # ran ONE way only; the return lane is drawn but unproven (~193).
        "twoway_confirmed":  n_confirmed,
        "twoway_confirmed_list": sorted(twoway_confirmed_list),
        "coactive_awaiting": n_coactive,
        "coactive_list":     sorted(coactive_list),
        "oneway_awaiting":   n_oneway,
        "oneway_list":       sorted(oneway_list),
        # HONEST SPLIT (item 5): dead PROVIDERS (no-key/quota/blocked — an EXPECTED state,
        # not a bug) reported separately from any other failed node, each with its real
        # provider status word so the map never conflates "dead provider" with "route bug".
        "dead_providers":    [{"id": i, "status": stations[i].get("status", "?"),
                               "detail": stations[i].get("status_detail", "")}
                              for i in invalid_ids if stations[i].get("prov")],
    }

    return {"ver": VER, "telemetry": telemetry, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stations": stations, "online": online, "viewbox": GRID_VIEWBOX,
            # ZONE BLOCKS (2026-07-29 v2): labelled department bands (x0..x1 per zone) so the
            # frontend can draw a legible header + tinted backdrop over each zone's columns —
            # the "better organized" layout that lets a viewer find things across the building.
            "zone_blocks": ZONE_BLOCKS, "grid_y0": GRID_Y0, "grid_view_h": GRID_VIEW_H,
            "grid_pitch_x": GRID_PITCH_X, "grid_pitch_y": GRID_PITCH_Y,
            # ONESIZE OVERLAYS (2026-07-30): department lines that trace each zone's stations
            # through the uniform grid + lift interchanges (>=2 lifts cross). Overlay-only —
            # positions come straight from the grid coords, nothing is moved.
            "dept_lines": _dept_lines_cached(), "interchanges": _interchanges_cached(),
            # LAYOUT (2026-07-29): mesh OFF by default so the categorised TRUNK lines read
            # clean; the full everyone-to-everyone lattice is still in `lines` (cat=="mesh")
            # and returns instantly if a client sets show_mesh true. Real connectivity data
            # is untouched — this only hides the faint dashed web from the default draw.
            "show_mesh": False,
            "lines": lines_out,
            # honest per-track direction detail (STAGING, UG-02) for the track/station panels
            "pair_dir": pair_dir,
            "trains": trains, "cat_color": CAT_COLOR, "moving": len(trains),
            "recent15": recent, "proof": _connectivity(),
            "observed": _observed_connectivity(trains),
            # AIs actually doing routing WORK (real trains), distinct from merely reachable.
            # Exclude gene_pool itself — it's the interchange HUB, not a routed provider AI
            # (the provider→gene_pool reply leg would otherwise mislabel the hub as an "AI").
            "routed_ais": sorted({t["to"] for t in trains
                                  if t["cat"] == "provider" and t["to"] != "gene_pool"}),
            "reachable_ais": sorted([sid for sid, s in stations.items() if s.get("reachable")]),
            "bill_gp": sum(1 for t in trains if t["from"] == "bill" and t["to"] == "gene_pool")}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>SkyscraperHQ · Tube Map · :8875</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0e16;--line:#233146;--txt:#e8f1ff;--dim:#8ba0ba}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:3000px;margin:0 auto;padding:14px}
h1{margin:0;font-size:20px}.sub{color:var(--dim);margin:2px 0 8px}
.hp{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12px;margin-left:8px}
.hp.ok{background:rgba(69,245,155,.15);color:#45f59b;border:1px solid #45f59b}
.hp.dead{background:rgba(255,93,125,.15);color:#ff5d7d;border:1px solid #ff5d7d}
/* uniform-grid map: BIG + roomy. aspect ~2980:1950. Width drives, height follows the
   aspect via the SVG viewBox so the single lattice is never squashed. Bigger + readable
   beats compact (Ross: "needs to be bigger") — the page scrolls if it overflows. */
#map{width:100%;aspect-ratio:2980/1950;background:radial-gradient(circle at 62% 44%,#0f1a2c,#080c14 72%);border:1px solid var(--line);border-radius:16px;cursor:grab;touch-action:none}
#map.panning{cursor:grabbing}
/* zoom controls (Ross: "i should have a zoom button") — fixed overlay, dark-UI styled */
.zbtn{width:38px;height:38px;border-radius:9px;border:1px solid #2c3a52;background:rgba(19,26,38,.92);color:#cfe0f5;font:700 22px/1 -apple-system,Segoe UI,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center}
.zbtn:hover{background:#1b2536;border-color:#40b4ff;color:#fff}
.zbtn:active{transform:scale(.94)}
.rail{fill:none;stroke-linecap:round;stroke-linejoin:round}
.roundel{fill:#0a0e16;stroke:#e8f1ff;stroke-width:3}
.roundel.big{stroke-width:3}.roundel.prov{stroke-width:3}
.on{stroke:#45f59b}
/* provider status roundels (item 1) */
.roundel.p-live{stroke:#45f59b;filter:drop-shadow(0 0 2.5px #45f59b)}
.roundel.p-amber{stroke:#ffb020}
.roundel.p-dead{stroke:#5a6577;fill:#161b26}
.roundel.p-unknown{stroke:#5a6577}
/* offline dead station (item 5) */
.roundel.off{stroke:#5a6577;stroke-dasharray:3 3;fill:#12161f;opacity:.6}
/* truly-silent station: drawn but no live signal (audit fix #4) */
.roundel.silent{stroke:#4a566b;stroke-dasharray:3 3;fill:#0d121c;opacity:.5}
/* IDLE-GHOST station (item 1): real event within the hour, no live train — DIM amber,
   warmer than dead-grey silent, so idle-but-alive reads distinct from truly-dead */
.roundel.ghost{stroke:#c98a2a;fill:#14100a;opacity:.72}
.stlabel.ghost{fill:#d6a24a}
/* MARKET-CLOSED station (item 2): stock floor waiting after-hours — calm blue, NOT broken */
.roundel.closed{stroke:#5b8fd6;stroke-dasharray:2 3;fill:#0c121d;opacity:.8}
.stlabel.closed{fill:#8fb4e6}
/* INVALID station (item 1): decommissioned / blocked — cannot carry real traffic */
.roundel.invalid{stroke:#ff5d7d;stroke-dasharray:4 3;fill:#1a0e14;opacity:.7}
.stlabel.invalid{fill:#ff8fa3}
/* telemetry strip (item 2) */
#telem{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
#telem .tc{background:#0f1726;border:1px solid #233146;border-radius:10px;padding:6px 12px;min-width:96px}
#telem .tc .v{font-size:20px;font-weight:800;line-height:1}
#telem .tc .l{color:#8ba0ba;font-size:10px;text-transform:uppercase;letter-spacing:.4px;margin-top:3px}
#telem .tc.warn .v{color:#ffb020}#telem .tc.bad .v{color:#ff5d7d}#telem .tc.good .v{color:#45f59b}
.stlabel.silent{fill:#5c6a80}
.stlabel.off{fill:#6a778c}
.stlabel{fill:#e8f1ff;font-size:11px;font-weight:600}
.stlabel.big{font-size:11px;font-weight:600}.stlabel.prov{fill:#8fe6b5;font-size:11px}
/* POLISH (UG-02b): tight, crisp carriage glow only — was 12px+4px white bloom that
   merged 1040 trains into a haze. A single small coloured shadow keeps each carriage a
   distinct lit dot without blooming into its neighbours. */
.train{filter:drop-shadow(0 0 2.5px currentColor)}
.legend{display:flex;gap:14px;color:var(--dim);font-size:12px;margin-top:8px;flex-wrap:wrap;align-items:center}
.k{display:inline-block;width:22px;height:5px;border-radius:3px;margin-right:6px;vertical-align:middle}
.kd{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle;border:2px solid}
/* ════════ STAGING (UG-02) interaction upgrade styling ════════ */
.stagebadge{display:inline-block;background:#8a5cf6;color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:800;margin-left:8px;vertical-align:middle}
/* clickable telemetry cards */
#telem .tc{cursor:pointer;transition:border-color .12s,background .12s}
#telem .tc:hover{border-color:#40b4ff;background:#132135}
#telem .tc.sel{border-color:#40b4ff;background:#152a44;box-shadow:0 0 0 1px #40b4ff}
/* control bar: search + filters */
#ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
#search{background:#0d1420;border:1px solid #2c3a52;border-radius:9px;color:#e8f1ff;padding:7px 11px;font:13px inherit;min-width:230px}
#search:focus{outline:none;border-color:#40b4ff}
.chip{background:#0f1726;border:1px solid #2c3a52;border-radius:999px;color:#9db3cc;padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer;user-select:none}
.chip:hover{border-color:#40b4ff;color:#cfe0f5}
.chip.on{background:#1d3550;border-color:#40b4ff;color:#eaf4ff}
.chip.tw{border-color:#45f59b}.chip.tw.on{background:#123c2b;color:#8dffc4}
.chip.co{border-color:#ffb020}.chip.co.on{background:#3a2c0c;color:#ffd489}
.chip.ow{border-color:#7f93ad}.chip.ow.on{background:#26313f;color:#cfe0f5}
.chip.fa{border-color:#ff5d7d}.chip.fa.on{background:#3a121d;color:#ff9fb2}
/* dim non-matching nodes when a search/filter is active */
.dimmed{opacity:.12 !important;transition:opacity .15s}
.selglow{filter:drop-shadow(0 0 8px #40b4ff)}
/* right inspector panel */
#insp{position:fixed;top:0;right:0;width:360px;max-width:92vw;height:100vh;background:#0c1320;border-left:1px solid #22304a;box-shadow:-8px 0 30px rgba(0,0,0,.45);z-index:70;transform:translateX(102%);transition:transform .18s ease;overflow-y:auto;padding:0}
#insp.open{transform:translateX(0)}
#insp .ihead{position:sticky;top:0;background:#0e1626;border-bottom:1px solid #22304a;padding:14px 16px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
#insp .ihead h3{margin:0;font-size:16px;line-height:1.25}
#insp .ihead .kind{color:#7f93ad;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-top:3px}
#insp .x{cursor:pointer;color:#8ba0ba;font-size:22px;line-height:1}
#insp .ibody{padding:14px 16px}
.irow{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid #16202f;font-size:12.5px}
.irow .lk{color:#8ba0ba}.irow .vv{color:#e8f1ff;text-align:right;font-weight:600;word-break:break-word}
.isec{margin-top:14px;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#647890;font-weight:700}
.pill{display:inline-block;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}
.pill.confirmed{background:rgba(69,245,155,.16);color:#45f59b;border:1px solid #45f59b}
.pill.coactive{background:rgba(255,176,32,.16);color:#ffb020;border:1px solid #ffb020}
.pill.oneway{background:rgba(127,147,173,.16);color:#9db3cc;border:1px solid #7f93ad}
.pill.idle{background:rgba(90,101,119,.16);color:#8ba0ba;border:1px solid #5a6577}
/* per-direction independent status rows (never collapsed) */
.dirbox{background:#0f1726;border:1px solid #22304a;border-radius:9px;padding:9px 11px;margin-top:7px}
.dirbox .dl{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12.5px;padding:3px 0}
.dirbox .dl b{color:#e8f1ff}.dirbox .dl .st{font-size:11px;font-weight:700}
.st.act{color:#45f59b}.st.q{color:#7f93ad}
.ilist{margin:6px 0 0;padding:0;list-style:none;font-size:12px}
.ilist li{padding:4px 0;border-bottom:1px solid #16202f;color:#b7c6d9;cursor:pointer}
.ilist li:hover{color:#eaf4ff}
.ibtn{background:#40b4ff;color:#04101f;border:0;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer;font-size:12px;margin-top:12px}
.ibtn.sec{background:#1b2536;color:#cfe0f5;border:1px solid #2c3a52}
</style></head><body><div class=wrap>
<h1>SkyscraperHQ · Underground <span style="color:#40b4ff">· :8875</span><span id=health class="hp ok">—</span></h1>
<div class=sub><b style="color:#7f93ad">STRUCTURAL:</b> <span id=proof style="color:#9db3cc"></span></div>
<div class=sub><b style="color:#45f59b">OBSERVED (last 15m):</b> <span id=observed style="color:#8fe6b5;font-weight:600"></span></div>
<div class=sub><span id=liveais style="color:#8fe6b5"></span> · every animated train is a REAL event ≤15m old — a quiet line stays still. Click any station · track · train to inspect.</div>
<div id=telem></div>
<div id=ctl>
  <input id=search placeholder="search station · AI · floor · service · train-id…" autocomplete=off>
  <span class=chip data-f=all>all</span>
  <span class="chip" data-f=active>active</span>
  <span class="chip tw" data-f=twoway>two-way (confirmed)</span>
  <span class="chip co" data-f=coactive>co-active (awaiting proof)</span>
  <span class="chip ow" data-f=oneway>one-way</span>
  <span class="chip fa" data-f=failed>failed / degraded</span>
  <span class="chip" data-f=ai>AI↔AI</span>
  <span class="chip" data-f=provider>provider traffic</span>
  <span class="chip on" id=tglDept style="border-color:#6366f1" title="trace each department's stations as a coloured line through the uniform grid">department lines</span>
  <span class="chip on" id=tglLift style="border-color:#7ea6c9" title="show lift shafts + interchange markers (where >=2 lifts cross)">lift shafts</span>
  <span class=chip id=clrsel style="border-color:#3a4a63">clear selection</span>
</div>
<div id=mapwrap style="position:relative">
  <svg id=map></svg>
  <div id=zoomctl style="position:absolute;top:12px;right:12px;display:flex;flex-direction:column;gap:6px;z-index:20">
    <button class=zbtn id=zin  title="zoom in">+</button>
    <button class=zbtn id=zout title="zoom out">−</button>
    <button class=zbtn id=zfit title="fit whole map" style="font-size:15px">⤢</button>
  </div>
  <div id=zhint style="position:absolute;bottom:10px;right:14px;color:#6d7f98;font-size:11px;z-index:20;pointer-events:none">scroll = zoom · drag = pan</div>
</div>
<div class=legend>
  <span><span class=k style="background:#40b4ff"></span>routing ⇄ Gene Pool (request+reply)</span>
  <span><span class=k style="background:#45f59b"></span>Gene-Pool ⇄ provider (2-way sub-track)</span>
  <span><span class=k style="background:#b98bff"></span>council (task-council spurs)</span>
  <span><span class=k style="background:#ffc24b"></span>comms mesh</span>
  <span><span class=k style="background:#6d7f98"></span>hub</span>
  <span><span class=k style="background:#2dd4bf"></span>Council-15</span>
  <span><span class=k style="background:#c4a3ff"></span>Wren sub</span>
  <span><span class=k style="background:#7ea6c9"></span>lift lines (inter-floor)</span>
  <span style="border-left:1px solid #233146;padding-left:12px"><span class=kd style="border-color:#8fb4e6;background:#0d121c"></span>tower floor · idle (dim by default)</span>
  <span><span class=kd style="border-color:#45f59b;background:#45f59b"></span>tower floor · ACTIVE (real activity)</span>
  <span style="border-left:1px solid #233146;padding-left:12px"><span class=kd style="border-color:#45f59b"></span>provider LIVE / reachable</span>
  <span><span class=kd style="border-color:#c98a2a;background:#14100a"></span>idle · alive (real event &lt;1h · "Xm ago")</span>
  <span><span class=kd style="border-color:#5b8fd6;background:#0c121d"></span>market closed (stocks after-hours)</span>
  <span><span class=kd style="border-color:#ffb020"></span>amber (no-credit/quota)</span>
  <span><span class=kd style="border-color:#5a6577"></span>dead (blocked/gone/no-key)</span>
  <span id=movetxt></span>
  <span style="color:#8ba0ba">· click any station · track · train to INSPECT (command is an explicit button in the panel)</span>
  <span style="border-left:1px solid #233146;padding-left:12px"><span style="display:inline-block;width:0;height:0;border-left:8px solid #45f59b;border-top:5px solid transparent;border-bottom:5px solid transparent;margin-right:5px;vertical-align:middle"></span>confirmed two-way (both ways)</span>
  <span><span style="display:inline-block;width:0;height:0;border-left:8px solid #ffb020;border-top:5px solid transparent;border-bottom:5px solid transparent;margin-right:5px;vertical-align:middle"></span>co-active beacon (awaiting proof)</span>
  <span><span style="display:inline-block;width:0;height:0;border-left:8px solid #9db3cc;border-top:5px solid transparent;border-bottom:5px solid transparent;margin-right:5px;vertical-align:middle"></span>one-way (awaiting reverse)</span>
</div>
<div id=insp>
  <div class=ihead>
    <div><h3 id=iTitle>—</h3><div class=kind id=iKind></div></div>
    <span class=x onclick="closeInsp()">×</span>
  </div>
  <div class=ibody id=iBody></div>
</div>
<div id=cmd style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:80" onclick="if(event.target===this)this.style.display='none'">
  <div style="max-width:460px;margin:80px auto;background:#131a26;border:1px solid #233146;border-radius:14px;padding:18px">
    <div style="display:flex;justify-content:space-between;align-items:center"><b id=cmdTitle style="font-size:16px"></b><span onclick="document.getElementById('cmd').style.display='none'" style="cursor:pointer;color:#8ba0ba;font-size:22px">×</span></div>
    <textarea id=cmdText rows=3 placeholder="message / task / job…" style="width:100%;margin-top:10px;background:#0d1420;border:1px solid #233146;border-radius:8px;color:#e8f1ff;padding:8px;font:13px inherit;resize:vertical"></textarea>
    <div id=cmdBtns style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap"></div>
    <div id=cmdRes style="margin-top:10px;color:#8ba0ba;font-size:12px"></div>
  </div>
</div>
</div><script>
function actionsFor(id){
  if(id==='gene_pool')return [['route_job','▶ Route a job through the pool'],['link_mc','🧬 Open Mission Control — the REAL Gene Pool']];
  if(id==='task_council'||id==='council15')return [['book_task','📋 Book a council task']];
  if(['wren','tp_pip','acer_cass','bill','codex','lumen','oracle','boardroom','town_square'].includes(id))return [['message','✉ Send a message']];
  return [];
}
function openCmd(id,label){
  const m=document.getElementById('cmd');document.getElementById('cmdTitle').textContent=label+' — command';
  document.getElementById('cmdText').value='';document.getElementById('cmdRes').textContent='';
  const acts=actionsFor(id);
  document.getElementById('cmdBtns').innerHTML=acts.length?acts.map(a=>a[0]==='link_mc'?`<a href="http://${location.hostname}:8852/proxy/gene_pool" target=_blank style="background:#8a5cf6;color:#fff;border-radius:8px;padding:8px 12px;font-weight:700;text-decoration:none">${a[1]}</a>`:`<button onclick="sendCmd('${id}','${a[0]}')" style="background:#40b4ff;color:#04101f;border:0;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer">${a[1]}</button>`).join(''):'<span style="color:#8ba0ba;font-size:12px">no direct command for this node</span>';
  m.style.display='block';
}
async function sendCmd(station,action){
  const text=document.getElementById('cmdText').value,res=document.getElementById('cmdRes');res.textContent='working…';
  try{const r=await(await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({station,action,text})})).json();
    res.textContent=r.ok?('✓ '+(r.result||'done')):('✕ '+(r.error||'failed'));}
  catch(e){res.textContent='✕ '+e}
}
const NS="http://www.w3.org/2000/svg";
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
const svg=document.getElementById("map");let ST={},TR=[],CC={},ON={};
// ── STAGING (UG-02) interaction state ──────────────────────────────────────────
let D=null;                 // latest full /api/data payload (for panels/search/filter)
let SEL=null;               // {kind:'station'|'track'|'train', id}
let FILTER='all';           // active filter chip
let SEARCH='';              // search query (lowercased)
function pkOf(a,b){return (String(a)<String(b))?(a+"↔"+b):(b+"↔"+a);}
function closeInsp(){document.getElementById('insp').classList.remove('open');SEL=null;applyVisibility();}
function labelOf(id){return (D&&D.stations[id]&&D.stations[id].label)||id;}
// ── ZOOM / PAN ENGINE (2026-07-29, Ross: "i should have a zoom button") ──────────
// The map is a big uniform grid; zoom/pan let Ross see the whole building AND dive into
// any floor cluster. Implemented by driving the SVG viewBox (crisp, no reflow). VIEW is
// the current window; BASE_VIEW is the server's fit-all box. draw() refreshes BASE_VIEW
// every tick but NEVER touches VIEW, so a zoomed/panned view survives the 1s poll.
let BASE_VIEW=null, VIEW=null;
const ZMIN=0.25, ZMAX=8;   // zoom-scale clamp (relative to fit-all)
function applyView(){ if(VIEW) svg.setAttribute("viewBox",`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`); }
function _curZoom(){ return BASE_VIEW && VIEW ? BASE_VIEW.w/VIEW.w : 1; }
// zoom around a focal point (cx,cy) in viewBox coords by factor f (>1 = zoom in)
function zoomAt(f,cx,cy){
  if(!VIEW||!BASE_VIEW)return;
  let nz=Math.min(ZMAX,Math.max(ZMIN,_curZoom()*f));
  const nw=BASE_VIEW.w/nz, nh=BASE_VIEW.h/nz;
  if(cx==null){cx=VIEW.x+VIEW.w/2; cy=VIEW.y+VIEW.h/2;}
  // keep the focal point stationary on screen
  const rx=(cx-VIEW.x)/VIEW.w, ry=(cy-VIEW.y)/VIEW.h;
  VIEW={x:cx-rx*nw, y:cy-ry*nh, w:nw, h:nh};
  applyView();
  if(typeof refreshView==="function")refreshView();   // LOD: reveal/hide labels by zoom
}
// screen (client) px -> viewBox coords
function _toVB(clientX,clientY){
  const r=svg.getBoundingClientRect();
  return {x:VIEW.x+((clientX-r.left)/r.width)*VIEW.w, y:VIEW.y+((clientY-r.top)/r.height)*VIEW.h};
}
function _fitView(){ if(BASE_VIEW){VIEW={...BASE_VIEW}; applyView(); if(typeof refreshView==="function")refreshView();} }
// buttons
document.getElementById("zin").addEventListener("click",()=>zoomAt(1.4));
document.getElementById("zout").addEventListener("click",()=>zoomAt(1/1.4));
document.getElementById("zfit").addEventListener("click",_fitView);
// wheel = zoom toward the cursor
svg.addEventListener("wheel",e=>{e.preventDefault(); if(!VIEW)return;
  const p=_toVB(e.clientX,e.clientY); zoomAt(e.deltaY<0?1.15:1/1.15,p.x,p.y);
},{passive:false});
// click-drag = pan
let _pan=null;
svg.addEventListener("pointerdown",e=>{ if(!VIEW)return; _pan={sx:e.clientX,sy:e.clientY,ox:VIEW.x,oy:VIEW.y};
  svg.classList.add("panning"); svg.setPointerCapture(e.pointerId); });
svg.addEventListener("pointermove",e=>{ if(!_pan||!VIEW)return;
  const r=svg.getBoundingClientRect();
  VIEW.x=_pan.ox-((e.clientX-_pan.sx)/r.width)*VIEW.w;
  VIEW.y=_pan.oy-((e.clientY-_pan.sy)/r.height)*VIEW.h;
  applyView(); });
function _endPan(e){ if(_pan){_pan=null; svg.classList.remove("panning"); try{svg.releasePointerCapture(e.pointerId);}catch(_){}} }
svg.addEventListener("pointerup",_endPan); svg.addEventListener("pointercancel",_endPan);
// ── LAYERED SVG (2026-07-29 FINAL): the map is redrawn every second WITHOUT wiping
// in-flight trains. Two persistent <g> layers: #railLayer (rails+roundels+labels,
// rebuilt each tick) and #trainLayer (moving carriages, NEVER cleared by a redraw).
// This removes the flicker/teleport the old svg.innerHTML="" caused every tick. ──
let railLayer=null, trainLayer=null;
function ensureLayers(){
  if(!railLayer){railLayer=el("g",{id:"railLayer"});svg.appendChild(railLayer);}
  if(!trainLayer){trainLayer=el("g",{id:"trainLayer"});svg.appendChild(trainLayer);}
  // keep trains ON TOP of freshly-rebuilt rails
  if(trainLayer!==svg.lastChild)svg.appendChild(trainLayer);
}
// LIVE-STREAM engine: every edge that carries a real (age-gated) train is registered
// as a continuously-flowing "route". A carriage is spawned on each live route on a
// steady cadence so the viewer ALWAYS sees motion on live tracks — a genuine stream,
// not a one-shot blip. Routes refresh from /api/data each tick; a route with no fresh
// real train (age>AGE_MAX) stops spawning and the line naturally goes still (honest).
let liveRoutes=new Map();   // key "from|to" -> {tr, col, nextSpawn}
let _clk=0;                 // stream clock (ms), advanced by the pump below
// ── PERF (STAGING2): signature-gated rebuild ──────────────────────────────────
// The rails/roundels/labels only change when the layout, a line's active flag, a
// station's status, or the zoom bucket flips. On the ~1s poll that is USUALLY
// identical, so we hash those inputs and SKIP the full ~700-node DOM teardown +
// rebuild when nothing structural changed — only the moving trains update. This is
// the primary render-cost cut (before: a full rebuild fired on every single tick).
let _lastSig=null;
function _layoutSig(d){
  let p=(d.viewbox||"")+"|"+Math.round((BASE_VIEW&&VIEW?BASE_VIEW.w/VIEW.w:1)*8);
  const L=d.lines||[];
  for(let i=0;i<L.length;i++){const x=L[i];if(x.cat==="mesh"&&!(x.act>0))continue;
    p+=(x.act>0?"1":"0")+(x.trunk?"t":"")+(x.dir_status||"");}
  const S=d.stations||{};
  for(const k in S){const s=S[k];
    p+=(s.has_traffic?"h":"")+(s.floor_active?"a":"")+(s.ghost?"g":"")+(s.offline?"o":"")
      +(s.market_closed?"c":"")+(s.status_band||"")+(s.reachable?"r":"");}
  let h=5381;for(let i=0;i<p.length;i++){h=((h<<5)+h+p.charCodeAt(i))|0;}
  return h;
}
// ── PERF (STAGING2): viewport culling — off-screen carriages/labels aren't rendered.
// deep-link starting view (STAGING2): "#backbone" frames the live trunk network;
// "#v=x,y,w,h" frames any rect. Lets an operator share a focused view + engages
// the carriage/label culling for that region.
function _applyHashView(){
  const h=(location.hash||"").replace("#","");
  if(h==="backbone"){VIEW={x:30,y:70,w:1720,h:990};}
  else if(h.startsWith("v=")){const p=h.slice(2).split(",").map(Number);
    if(p.length===4&&p.every(n=>!isNaN(n)))VIEW={x:p[0],y:p[1],w:p[2],h:p[3]};}
}
function _inView(x,y,m){const v=VIEW||BASE_VIEW;if(!v)return true;
  return x>=v.x-m&&x<=v.x+v.w+m&&y>=v.y-m&&y<=v.y+v.h+m;}
function _edgeInView(A,B){const m=90;
  return _inView(A.x,A.y,m)||_inView(B.x,B.y,m)||_inView((A.x+B.x)/2,(A.y+B.y)/2,m);}
// RIGHT-ANGLE tube router (2026-07-29 FINAL): the layout is column-based, so the
// cleanest track between two columns is a proper L — travel VERTICALLY inside the
// source column to the target's row, then HORIZONTALLY into the target. This makes
// every CEO→spine line share the spine's vertical lane and every spine→provider fan
// share a horizontal lane, collapsing the old diagonal spaghetti into clean elbows.
// Pure H / pure V pass straight through. A near-45° short hop stays diagonal (looks fine).
// METRO ELBOW (STAGING2): pick the corner of the L-route for one edge.
//  · DEFAULT: horizontal-into-the-target-column, then vertical — so convergent hubs
//    (spine, task-council) share ONE vertical lane instead of a fan of diagonals.
//  · PROVIDER FAN: for a Gene-Pool↔provider edge, corner at (hub.x, provider.y) so the
//    ten providers COMB off the gene-pool vertical at distinct rows — the fan spreads
//    into clean parallel horizontal taps instead of a knot of overlapping diagonals.
function elbowCorner(A,B){
  if((A.prov&&B.hub_fan)||(B.prov&&A.hub_fan)){
    const hub=A.hub_fan?A:B, prov=A.prov?A:B;
    return {x:hub.x, y:prov.y};
  }
  return {x:B.x, y:A.y};
}
function routePath(A,B){
  const dx=B.x-A.x, dy=B.y-A.y;
  if(Math.abs(dx)<2||Math.abs(dy)<2) return `M ${A.x} ${A.y} L ${B.x} ${B.y}`;      // pure H or V
  if(Math.abs(dx)<70 && Math.abs(dy)<70) return `M ${A.x} ${A.y} L ${B.x} ${B.y}`;  // tiny hop → diagonal ok
  const c=elbowCorner(A,B);
  return `M ${A.x} ${A.y} L ${c.x} ${c.y} L ${B.x} ${B.y}`;
}
// elbow midpoint so carriages follow the SAME right-angle track the rail was drawn on.
function routeMid(A,B){
  const dx=B.x-A.x, dy=B.y-A.y;
  if(Math.abs(dx)<2||Math.abs(dy)<2) return null;
  if(Math.abs(dx)<70 && Math.abs(dy)<70) return null;
  return elbowCorner(A,B);   // the corner of the L (same as the rail)
}
// ── STAGING (UG-02) DIRECTION ARROWS ───────────────────────────────────────────
// An explicit static arrow on each ACTIVE rail, coloured by the HONEST direction status:
//   confirmed two-way = green, both-ways chevrons · co-active(awaiting proof) = amber,
//   both-ways · one-way = grey single chevron pointing the ONE proven way. This makes
//   direction legible even when a carriage isn't mid-flight. Colour never claims two-way
//   for a floorflow beacon — those are amber "co-active", not green.
const DIR_COL={confirmed:"#45f59b",coactive:"#ffb020",oneway:"#9db3cc",idle:"#5a6577"};
function _chev(cx,cy,angRad,color){
  const g=el("g",{transform:`translate(${cx} ${cy}) rotate(${angRad*180/Math.PI})`});
  g.appendChild(el("path",{d:"M -4.5 -4.5 L 4.5 0 L -4.5 4.5 Z",fill:color,opacity:.96,
    stroke:"#04101f","stroke-width":.6,"pointer-events":"none"}));
  return g;
}
function dirArrow(R,A,B,L){
  const st=L.dir_status||"idle", col=DIR_COL[st]||"#9db3cc", dir=L.dir||"ab";
  const M=routeMid(A,B);
  const cx=M?M.x:(A.x+B.x)/2, cy=M?M.y:(A.y+B.y)/2;
  const ab=Math.atan2(B.y-A.y,B.x-A.x);        // A→B heading
  if(dir==="both"){                             // confirmed / co-active: opposing chevrons
    R.appendChild(_chev(cx-7,cy-7,ab,col));
    R.appendChild(_chev(cx+7,cy+7,ab+Math.PI,col));
  }else{                                        // one-way: single chevron the ONE proven way
    R.appendChild(_chev(cx,cy, dir==="ba"?ab+Math.PI:ab, col));
  }
}
// on-canvas legend, bottom-left corner (item 3): line categories + provider status colours
function drawLegend(){
  const rows=[
    ["line","#40b4ff","route ⇄ Gene Pool (request + reply, both legs)"],
    ["line","#45f59b","Gene-Pool ⇄ provider (real routed work, 2-way)"],
    ["line","#b98bff","council (→ Task Council)"],
    ["line","#ffc24b","comms mesh (room / acks / DMs)"],
    ["line","#2dd4bf","Council-15 sub"],
    ["line","#c4a3ff","Wren sub"],
    ["dash","#4a566b","track drawn · no live signal (dashed, dim)"],
    ["solid","#45f59b","solid green RING = online + carrying trains"],
    ["ringd","#3fbf8f","dashed green ring = comms-online, no traffic"],
    ["ring","#45f59b","provider RING = reachable (probed, NOT routing)"],
    ["dot","#ffb020","provider amber (no-credit / quota)"],
    ["dot","#5a6577","provider dead / silent (no traffic)"],
    ["ghost","#c98a2a","IDLE (alive) — real event within the hour, resting · 'Xm ago'"],
    ["closed","#5b8fd6","market closed — stock floor waiting after-hours"],
    ["inval","#ff5d7d","INVALID / decommissioned — cannot carry real traffic"],
  ];
  // 2026-07-29: legend moved off the LEFT edge (x0=18) — it was occluding the trading-floor
  // column (F42/F43 at x=120), hiding the F43 'market closed' badge behind the box. Parked in
  // the lower-CENTRE band (x0=560), the emptiest region of the map, so the trading floors and
  // their new ghost/closed badges stay fully visible. Semi-transparent box + the specialist
  // rails still read through it; the trading-floor occlusion (which hid a real badge) is gone.
  const x0=560, y0=778-rows.length*17-30, w=300, h=rows.length*17+26;
  const g=el("g",{});
  g.appendChild(el("rect",{x:x0-8,y:y0-6,width:w,height:h,rx:8,fill:"#0b1220",stroke:"#233146","stroke-width":1,opacity:.92}));
  const ttl=el("text",{x:x0,y:y0+8,class:"stlabel",fill:"#cfe0f5"});ttl.textContent="LEGEND";g.appendChild(ttl);
  rows.forEach((rw,i)=>{
    const y=y0+24+i*17;
    if(rw[0]==="line"){g.appendChild(el("rect",{x:x0,y:y-4,width:22,height:5,rx:2,fill:rw[1]}));}
    else if(rw[0]==="dash"){g.appendChild(el("line",{x1:x0,y1:y-1,x2:x0+22,y2:y-1,stroke:rw[1],"stroke-width":2,"stroke-dasharray":"3 3"}));}
    else if(rw[0]==="ring"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:7,fill:"none",stroke:rw[1],"stroke-width":2,"stroke-dasharray":"2 3"}));}
    else if(rw[0]==="solid"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:7,fill:"none",stroke:rw[1],"stroke-width":2}));}
    else if(rw[0]==="ringd"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:7,fill:"none",stroke:rw[1],"stroke-width":2,"stroke-dasharray":"3 4"}));}
    else if(rw[0]==="inval"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:6,fill:"#1a0e14",stroke:rw[1],"stroke-width":3,"stroke-dasharray":"4 3"}));}
    else if(rw[0]==="ghost"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:6,fill:"#14100a",stroke:rw[1],"stroke-width":2.4}));}
    else if(rw[0]==="closed"){g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:6,fill:"#0c121d",stroke:rw[1],"stroke-width":2.4,"stroke-dasharray":"2 3"}));}
    else{g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:6,fill:"#0a0e16",stroke:rw[1],"stroke-width":3}));}
    const t=el("text",{x:x0+30,y:y+2,class:"stlabel",fill:"#9db3cc","font-size":10});t.textContent=rw[2];g.appendChild(t);
  });
  (railLayer||svg).appendChild(g);
}
// ── ZONE BLOCK RENDERER (2026-07-29 v2): draw a tinted department backdrop spanning each
//    zone's columns + a bold zone header at the top. This is the "better organized" layout —
//    a viewer can find Trading / Executive / R&D / Providers / Amenities at a glance. Uses the
//    server-computed zone_blocks (x0,x1 = column-centre range) padded by half a column pitch.
// ── ONESIZE OVERLAYS (2026-07-30) — overlay-only draws over the uniform grid. ──
let SHOW_DEPT=true, SHOW_LIFT=true;
// DEPARTMENT LINES: a coloured polyline threading each zone's stations exactly as they
// sit on the uniform grid (points come straight from the server, computed from
// col*PITCH_X/row*PITCH_Y). Traces a department's route; moves nothing. Non-interactive
// so the station roundels underneath stay clickable. Drawn under rails + stations.
function drawDeptLines(d,R){
  if(!SHOW_DEPT)return;
  const dl=d.dept_lines||[]; if(!dl.length)return;
  dl.forEach(z=>{
    const pts=z.pts||[]; if(pts.length<2)return;
    const pstr=pts.map(p=>p[0]+","+p[1]).join(" ");
    R.appendChild(el("polyline",{points:pstr,fill:"none",stroke:z.color,"stroke-width":7,
      opacity:.10,"stroke-linejoin":"round","stroke-linecap":"round","pointer-events":"none"}));
    R.appendChild(el("polyline",{points:pstr,fill:"none",stroke:z.color,"stroke-width":3,
      opacity:.55,"stroke-linejoin":"round","stroke-linecap":"round","pointer-events":"none"}));
  });
}
// LIFT INTERCHANGES: a classic tube double-ring where >=2 lift shafts cross (from
// qsb_floor_lift_lines.json). Drawn on TOP so the crossing reads; non-interactive so the
// floor roundel underneath stays clickable.
function drawInterchanges(d,R){
  if(!SHOW_LIFT)return;
  const ix=d.interchanges||[]; if(!ix.length)return;
  ix.forEach(p=>{
    if(p.major){
      // MAJOR interchange: classic tube double-ring where >=2 ROUTE lifts hand over.
      const ro=7+Math.max(0,(p.route_n-2))*1.8;
      R.appendChild(el("circle",{cx:p.x,cy:p.y,r:ro,fill:"#0a0e16",stroke:"#e8eef7",
        "stroke-width":2.4,opacity:.97,"pointer-events":"none"}));
      R.appendChild(el("circle",{cx:p.x,cy:p.y,r:ro*0.42,fill:"#e8eef7",opacity:.92,"pointer-events":"none"}));
    }else{
      // minor crossing (a route lift + the universal service/stairwell shafts): a faint tick
      // so it reads as "on a lift line" without competing with the true handover interchanges.
      R.appendChild(el("circle",{cx:p.x,cy:p.y,r:3.2,fill:"none",stroke:"#7ea6c9",
        "stroke-width":1.1,opacity:.35,"pointer-events":"none"}));
    }
  });
}
function drawZones(d,R){
  const zb=d.zone_blocks||[]; if(!zb.length)return;
  const y0=d.grid_y0||150, vh=d.grid_view_h||1000;
  const top=18, bot=vh-8;
  // ONESIZE: zone_blocks x0/x1 are column-CENTRE coords on the uniform grid; pad by ~half a
  // column pitch so the tinted band frames its columns (nothing is moved — this is only the
  // backdrop rect extent, well within the existing viewBox right margin).
  const pad=(d.grid_pitch_x||210)*0.5;
  zb.forEach(z=>{
    const x0=z.x0-pad*0.9, x1=z.x1+pad*1.1, w=x1-x0;
    // faint tinted column backdrop for the whole zone (very low opacity so rails read through)
    R.appendChild(el("rect",{x:x0,y:top,width:w,height:bot-top,rx:14,
      fill:z.color,opacity:.045,stroke:z.color,"stroke-opacity":.22,"stroke-width":1}));
    // header pill
    const hx=x0+10, hy=top+8;
    R.appendChild(el("rect",{x:hx,y:hy,width:Math.min(w-20,z.zone.length*8.6+18),height:22,rx:11,
      fill:"#0b1220",stroke:z.color,"stroke-width":1.4,opacity:.92}));
    const tt=el("text",{x:hx+11,y:hy+15,class:"stlabel","font-size":12.5,fill:z.color,"font-weight":800});
    tt.textContent=z.zone.toUpperCase(); R.appendChild(tt);
    // small count tag under the header
    const ct=el("text",{x:hx+11,y:hy+34,class:"stlabel","font-size":9.5,fill:"#7d8da0"});
    ct.textContent=z.count+" stations"; R.appendChild(ct);
  });
}
function draw(d){
  D=d;ST=d.stations;CC=d.cat_color;ON=d.online||{};
  // ONE UNIFORM GRID (2026-07-29 FINAL): the server lays EVERY station on a single
  // uniform lattice (same x-pitch + y-pitch everywhere) and hands us the exact viewBox
  // that fits it — no huge empty margin, no cramped corner. Whole map is one scale.
  // ZOOM/PAN: capture the fit-all viewBox as BASE once; the live view is driven by the
  // zoom engine below, NOT reset every poll tick — so a zoomed/panned view survives the
  // 1s data refresh (only re-fit on first load or when the user hits the fit button).
  const vb=(d.viewbox||"0 0 2380 800").split(/\s+/).map(Number);
  BASE_VIEW={x:vb[0],y:vb[1],w:vb[2],h:vb[3]};
  // keep the SVG box aspect-ratio matched to the server viewBox so the zone-organised grid is
  // never vertically squashed (the layout width changes as zones/floors change).
  if(vb[2]&&vb[3])svg.style.aspectRatio=vb[2]+" / "+vb[3];
  if(!VIEW){VIEW={...BASE_VIEW}; _applyHashView();}
  applyView();
  ensureLayers();
  // PERF (STAGING2): skip the full rails/roundels/labels rebuild on ticks where nothing
  // structural changed — only the moving trains (below) update. Big CPU/FPS win.
  const _sig=_layoutSig(d);
  if(_sig!==_lastSig){
  _lastSig=_sig;
  railLayer.innerHTML="";           // rebuild rails/roundels only — trains persist
  const R=railLayer;                // rails/roundels/legend draw into the rail layer (not the whole svg)
  // ── ZONE BLOCKS (2026-07-29 v2): a tinted backdrop + header label over each department's
  //    columns, so the map reads as organised, findable blocks (trading / governance / R&D /
  //    providers / amenities …). Drawn FIRST so rails + stations sit on top. ──
  drawZones(d,R);
  // ONESIZE: department lines trace each zone's stations through the uniform grid (below rails).
  drawDeptLines(d,R);
  // ALL-LIVE MODE (Ross: "all tracks need to be live with trains"): draw ONLY tracks that
  // carry a REAL train in the window. Every rail on screen is therefore genuinely live — no
  // dead/quiet track is painted. (Toggle showMesh=true to also show the faint potential lattice.)
  const showMesh = (d.show_mesh === true);  // LAYOUT: mesh OFF by default (was ON = spaghetti).
  // Draw order for a clean tube map: (1) faint mesh lattice ONLY if explicitly toggled on,
  // (2) the categorised TRUNK backbone always visible (dim coloured lines so structure reads
  // even when idle), (3) bright live rails on top where a real train ran. This keeps the
  // primary category lines legible while the 300+ mesh edges stay hidden by default.
  const _z=_curZoom();                       // LOD: strengthen trunks / hide detail by zoom
  d.lines.forEach(L=>{const A=ST[L.a],B=ST[L.b];if(!A||!B)return;
    const act=L.act>0, mesh=(L.cat==="mesh"), pk=L.id||pkOf(L.a,L.b);
    // one helper attaches data-pk + a click→INSPECT (viewing-only, no command) to every rail
    const mkRail=(attrs,clickable)=>{
      const p=el("path",{class:"rail",d:routePath(A,B),"data-pk":pk,...attrs});
      if(clickable!==false){p.style.cursor="pointer";p.addEventListener("click",(e)=>{e.stopPropagation();selectTrack(pk);});}
      R.appendChild(p);return p;
    };
    // LIFT LINES (elevation): the building's inter-floor lift topology. Real lifts solid,
    // proposed lifts dashed — kept visually separate from the live coloured trunks. No trains.
    if(L.cat==="lift"){
      if(!SHOW_LIFT)return;
      const col=L.color||CC.lift||"#7ea6c9";
      mkRail({stroke:col,"stroke-width":L.proposed?1.6:2.4,opacity:L.proposed?.30:.5,
        ...(L.proposed?{"stroke-dasharray":"5 5"}:{})},false);
      return;
    }
    if(mesh){
      // a MESH edge carrying a REAL train (floor-to-floor feed) draws bright; idle mesh hidden.
      if(act){ mkRail({stroke:(CC.route||"#40b4ff"),"stroke-width":4,opacity:.82});
        if(_z>=0.9)dirArrow(R,A,B,L); return; }
      if(showMesh) mkRail({stroke:"#2b3c52","stroke-width":1.2,opacity:.12,"stroke-dasharray":"4 7"},false);
      return; }
    if(act){
      // TRUNK EMPHASIS (item 3): primary trunk lines render visibly STRONGER than secondary.
      // POLISH (UG-02b): thinner + slightly lower opacity so dense clusters read as distinct
      // lines/dots rather than a solid bright slab of colour.
      const w=L.trunk?6:4;
      mkRail({stroke:(CC[L.cat]||"#40b4ff"),"stroke-width":w,opacity:.82});
      if(_z>=0.9)dirArrow(R,A,B,L);   // explicit static direction arrow(s) — honest per dir_status
    } else if(L.trunk){  // idle TRUNK backbone: dim coloured line so the network shape reads
      // POLISH (UG-02b): idle infra pulled back (.30 -> .18) so idle structure is a faint
      // guide, not a competing glow.
      mkRail({stroke:(CC[L.cat]||"#40b4ff"),"stroke-width":2.4,opacity:.18});
    } else {  // idle non-trunk categorised track: reduced idle-infra brightness (item 6)
      mkRail({stroke:"#33465f","stroke-width":1.2,opacity:.10,"stroke-dasharray":"3 6"});
    }});
  Object.entries(ST).forEach(([id,s])=>{
    // ── ELEVATION FLOOR STATION (2026-07-29): a small roundel in the right-hand building
    //    elevation. DIM/idle by default (honest: quiet floors show quiet); lit only when the
    //    floor activity index marks it active (floor_active) — then it glows in its zone
    //    colour (or warm amber) with an "Xm ago" tag. No trains, no rings, no provider logic. ──
    if(s.floor){
      const fr=UNIT_R;                              // uniform floor roundel (same size as every node)
      const zc=s.zone_color||"#8fb4e6";             // zone colour if the zones registry provided one
      const lit=!!s.floor_active;
      if(lit){  // POLISH (UG-02b): tighter, dimmer lit halo (r+2, .45) — active floor still
                // pops out of the dim elevation but its ring no longer blooms into neighbours.
        R.appendChild(el("circle",{cx:s.x,cy:s.y,r:fr+2,fill:"none",stroke:zc,"stroke-width":1.3,opacity:.45}));
      }
      const fc=el("circle",{cx:s.x,cy:s.y,r:fr,
        fill: lit ? zc : "#0d121c",
        stroke: lit ? zc : (s.zone_color? s.zone_color : "#3a4a63"),
        "stroke-width": lit?1.6:1.1,
        // POLISH (UG-02b): idle floors pushed much dimmer (.42 -> .28) so the eye lands on
        // what's actually active; lit floors stay crisp/bright.
        opacity: lit?0.95:0.28,
        ...(lit?{}:{"stroke-dasharray":"1.5 2.5"}),
        id:"st_"+id});
      fc.style.cursor="pointer";fc.addEventListener("click",(e)=>{e.stopPropagation();selectStation(id);});
      const fti=el("title");
      fti.textContent = lit
        ? s.label+" — ACTIVE · last real event "+(s.last_active_label||"recently")
        : s.label+" — idle (no recent activity) · dim by default, lights on real floor activity";
      fc.appendChild(fti);R.appendChild(fc);
      // tiny label to the RIGHT of the floor roundel (elevation columns read cleanly this way).
      // Lit floors label brighter; idle floors dim grey. Zone-coloured when a zone is known.
      const ft=el("text",{x:s.x+fr+5,y:s.y+4,"text-anchor":"start",class:"stlabel",id:"lb_"+id,
        "font-size":11, fill: lit ? (s.zone_color||"#cfe0f5") : "#7d8da0", opacity: lit?1:.78});
      ft.textContent=s.label;R.appendChild(ft);
      return;   // floor stations are fully rendered here — skip all curated-node logic below
    }
    // UNIFORM STATION SIZE (2026-07-29, Ross: "the network map needs to be all one size").
    // EVERY station node renders at the SAME radius UNIT_R — the `big`/`prov`/`sub` flags no
    // longer change the drawn size (they're kept in the data only for interchange/category
    // semantics, not geometry). This matches the floor stations, which also use UNIT_R below.
    const r=UNIT_R,online=ON[id];
    // RING semantics (audit fix #2 & #6):
    //  - green solid ring = presence heartbeat AND actually carrying tower trains
    //  - green dashed ring = comms-online only (relay heartbeat, NO tower traffic) — e.g. Bill
    //  - provider "reachable" = passed the 15-min health probe: green ring = responds,
    //    but that is NOT routed work (only a real train means real work).
    // POLISH (UG-02b): tighter active rings (r+3, thinner, lower opacity) so the lit ring
    // hugs the node as a crisp halo instead of blooming out into neighbouring stations.
    if(online&&!s.offline&&s.has_traffic){
      R.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+3,fill:"none",stroke:"#45f59b","stroke-width":1.6,opacity:.6,id:"on_"+id}));
    } else if(s.comms_online&&!s.offline){
      R.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+3,fill:"none",stroke:"#3fbf8f","stroke-width":1.5,opacity:.5,"stroke-dasharray":"3 4",id:"on_"+id}));
    } else if(s.reachable){  // provider probed-reachable but not routing work
      R.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+3,fill:"none",stroke:"#45f59b","stroke-width":1.3,opacity:.4,"stroke-dasharray":"2 3",id:"rc_"+id}));
    }
    // roundel base class: invalid / offline / market-closed / ghost / silent / provider-band / online-solid
    // INVALID (item 1) wins: a decommissioned/blocked node draws as a red-dashed
    // roundel so it's visibly NOT part of the live network, even if it's a provider.
    // GHOST (item 1): idle-but-alive — a real event within the hour but no live train:
    //   render DIM (amber ghost) with an "Xm ago" label, NOT fully dark. Honest tier
    //   between LIT (train now) and DEAD (no event / blocked provider).
    // MARKET-CLOSED (item 2): stock floor waiting after-hours — a blue "closed" badge.
    let cls="roundel"+(s.big?" big":"")+(s.prov?" prov":"")+(online&&!s.offline&&s.has_traffic?" on":"");
    if(s.valid===false)cls+=" invalid";
    else if(s.offline)cls+=" off";
    else if(s.market_closed)cls+=" closed";
    else if(s.ghost)cls+=" ghost";
    else if(s.prov)cls+=" p-"+(s.status_band||"unknown");
    else if(s.silent)cls+=" silent";
    // idle-ghost ring: a faint amber dashed halo so an idle-but-alive node reads as
    // "recently active, resting" — visibly warmer than a dead grey dashed silent node.
    if(s.ghost&&!s.has_traffic&&!s.offline){
      R.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+3,fill:"none",stroke:"#c98a2a","stroke-width":1.3,opacity:.38,"stroke-dasharray":"2 4",id:"gh_"+id}));
    }
    const stc=el("circle",{cx:s.x,cy:s.y,r:r,class:cls,id:"st_"+id});
    stc.style.cursor="pointer";stc.addEventListener("click",(e)=>{e.stopPropagation();selectStation(id);});
    // HONEST tooltips
    const ti=el("title");
    if(s.valid===false)ti.textContent=s.label+" — DECOMMISSIONED / BLOCKED · "+(s.invalid_reason||"cannot carry real traffic")+" (NOT part of the live network)";
    else if(s.offline)ti.textContent=s.label+" — offline · "+(s.offline_reason||"service down");
    else if(s.market_closed)ti.textContent=s.label+" — MARKET CLOSED · no fresh stock ticks (after-hours). Self-lights when real ticks return.";
    else if(s.ghost)ti.textContent=s.label+" — IDLE (alive) · last real event "+(s.last_active_label||"recently")+" · resting, no live train right now";
    else if(s.comms_online)ti.textContent=s.label+" — comms-online (relay heartbeat) · no tower traffic";
    else if(s.prov)ti.textContent=s.label+" — "+(s.status||"?")+(s.status_detail?" · "+s.status_detail:"")+(s.reachable&&!s.has_traffic?" · reachable (probed), NOT routing work":"")+(s.has_traffic?" · routing real work":"");
    else if(s.silent)ti.textContent=s.label+" — no live signal (track drawn, no traffic in last 15m)";
    else ti.textContent=s.label;
    stc.appendChild(ti);R.appendChild(stc);
    // provider fan on the right: label to the RIGHT of the roundel so the fan stays clean.
    // everything else: label above the roundel, centred.
    let t;const inv=s.valid===false;
    const extra=(inv?" invalid":"")+(s.market_closed?" closed":"")+(s.ghost?" ghost":"");
    if(s.prov){t=el("text",{x:s.x+r+7,y:s.y+3,"text-anchor":"start",class:"stlabel prov"+extra});}
    else{t=el("text",{x:s.x,y:s.y-(UNIT_R+9),"text-anchor":"middle",class:"stlabel"+(s.big?" big":"")+(s.offline?" off":"")+extra});}
    // HONEST status tag (item 5): a dead/blocked provider shows its REAL reason word
    // (NO_KEY / QUOTA / BLOCKED / ENDPOINT_GONE) — so "isolated because the provider is
    // dead" is visibly distinct from "isolated because we failed to route to a live node".
    // Non-provider dead nodes (oracle) show "dead"; offline services (lumen) show "offline".
    let tag="";
    if(s.offline)tag=" · offline";                         // lumen (:8848 service down) — offline, not decommissioned
    else if(inv&&s.prov)tag=" · "+(s.status||"DEAD");      // e.g. claude · NO_KEY, kimi · QUOTA
    else if(inv)tag=" · dead";                             // oracle (dead Cloud VM)
    else if(s.market_closed)tag=" · closed";               // f43 stocks — market closed (waiting, item 2)
    else if(s.ghost)tag=" · "+(s.last_active_label||"idle");  // idle-ghost — last active Xm ago (item 1)
    t.setAttribute("id","lb_"+id);t.setAttribute("data-kind",(s.big||s.prov||s.trade)?"primary":"secondary");
    t.textContent=s.label+tag;R.appendChild(t);
  });
  // ONESIZE: lift interchange markers on TOP of the station roundels (where >=2 lifts cross).
  drawInterchanges(d,R);
  refreshView();   // apply LOD (label collision by zoom) + any active search/filter dimming
  }                // ── end signature-gated rebuild (PERF, STAGING2) ──
  // 2026-07-29: on-canvas legend REMOVED from the draw — wherever it sat it occluded a
  // real station (left edge hid F42/F43 + the new market-closed badge; centre hid oracle).
  // The full key now lives in the HTML legend BELOW the map (nothing overlaps the network).
  // drawLegend();  // intentionally not drawn on-canvas anymore
  TR=d.trains||[];
  // ── LIVE-STREAM ROUTE REGISTRATION (2026-07-29 FINAL) ──────────────────────────
  // Ross wants a genuine LIVE STREAM: trains CONTINUOUSLY flowing on every track that
  // has a real (age-gated) train — motion visible at all times, not a one-shot blip.
  // So every fresh real train registers a "route" that keeps spawning carriages on a
  // steady cadence. A route drops out the instant its backing train is no longer in the
  // real, age-gated feed — then that line goes STILL (honest: quiet source == still line).
  const seen=new Set();
  (d.trains||[]).forEach(t=>{
    const A=ST[t.from],B=ST[t.to];if(!A||!B)return;
    // per-category client guard mirrors the server: trade + floorflow use the slower 3600s
    // window (real but sparse fleet/floor events), everything else the 900s window. Stale
    // still never flows.
    const cap=(t.cat==='trade'||t.cat==='floorflow')?TRADE_AGE_MAX:AGE_MAX;
    if(t.age_s==null||t.age_s>cap)return;                     // honest: stale never flows
    const pv=A.prov?A:(B.prov?B:null);                        // never flow to a dead provider
    if(pv&&pv.status_band&&pv.status_band!=="live")return;
    const key=t.from+"|"+t.to;seen.add(key);
    const col=CC[t.cat]||"#40b4ff";
    const cur=liveRoutes.get(key);
    if(cur){cur.tr=t;cur.col=col;}                            // refresh label/ts, keep cadence
    else{liveRoutes.set(key,{tr:t,col,nextSpawn:_clk+Math.random()*STREAM_GAP});}
  });
  // retire routes whose real train aged out of the feed -> that line stops flowing
  for(const k of [...liveRoutes.keys()])if(!seen.has(k))liveRoutes.delete(k);
}
// UNIFORM STATION RADIUS (2026-07-29): one size for EVERY node on the map — curated
// hubs, CEOs, providers, sub-specialists AND all 170 tower-floor stations. Ross:
// "the network map needs to be all one size." Change this single value to rescale all.
const UNIT_R=14;
const AGE_MAX=900;    // seconds — client-side guard: never animate a stale/undated train
const TRADE_AGE_MAX=3600; // trade floor: slower-cadence real fleet ticks get the 1h window (server matches)
const STREAM_GAP=2200; // ms between carriages on ONE live route (steady stream cadence)
const RUN_MS=1800;     // ms a carriage takes to travel its edge (smooth, continuous)
// ── TWO-WAY LANE OFFSET (2026-07-29, Ross: "i dont see two way traffic to all floors") ──
// When a pair {a,b} carries BOTH an up-leg (from→to) and a down-leg / return (to→from),
// the two carriages must NOT ride the exact same line or they overlap into one and 2-way is
// invisible. So each carriage rides a lane offset PERPENDICULAR to its travel, with a SIGN
// derived from the pair's canonical order — so from→to always takes one side and to→from the
// opposite side. Result: a visible round-trip = two parallel tracks, trains passing in
// opposite directions. HONEST: this only shapes HOW a real train is drawn; a return train is
// still only drawn when the feed/real reader actually produced that (to→from / cat:return) row.
const LANE_OFF=6.5;   // px each carriage is nudged off the centre-line onto its own lane
// signed perpendicular lane vector for a carriage travelling A→B, keyed to the {a,b} pair so
// the two opposite directions always split to opposite sides (round-trip look).
function laneVec(fromId,toId,A,B){
  const dx=B.x-A.x, dy=B.y-A.y, len=Math.hypot(dx,dy)||1;
  // unit perpendicular (rotate travel vector 90°)
  let px=-dy/len, py=dx/len;
  // canonical sign: forward (from<to lexically) rides +perp, reverse rides -perp. Because the
  // perp is computed from THIS carriage's own travel vector (which flips for the reverse leg),
  // flipping the sign on the reverse leg keeps BOTH carriages on the SAME physical side pair —
  // i.e. genuinely parallel opposing lanes, not stacked. Undirected key so both legs agree.
  const s = (String(fromId) < String(toId)) ? 1 : -1;
  return {x:px*LANE_OFF*s, y:py*LANE_OFF*s};
}
// spawn ONE carriage travelling the routed track from A→B (through the elbow if it bends),
// nudged onto its own two-way lane so the return leg reads as a distinct parallel track.
function spawnCarriage(tr,col){
  const A=ST[tr.from],B=ST[tr.to];if(!A||!B)return;
  if(!_edgeInView(A,B))return;   // PERF: don't spawn a carriage whose whole edge is off-screen
  ensureLayers();
  const g=el("g",{class:"train"});g.style.color=col;
  const isRet=(tr.cat==="return");
  // return carriages get a subtle glow + are drawn as a single sleeker car so down-traffic
  // reads as an answering leg, not just "another blue train".
  // BIG + BRIGHT carriages so real traffic is unmistakable against the dense lattice
  // (Ross: "I don't see two way traffic"). Two cars + a white headlight core.
  g.appendChild(el("rect",{x:A.x-18,y:A.y-8,width:17,height:16,rx:4,fill:col,
    ...(isRet?{opacity:.98,"stroke":"#ffd6ec","stroke-width":1.2}:{})}));
  g.appendChild(el("rect",{x:A.x+2, y:A.y-8,width:17,height:16,rx:4,fill:col,
    "stroke":"#cfeee0","stroke-width":1.1,opacity:isRet?.82:.92}));
  g.appendChild(el("circle",{cx:A.x+10,cy:A.y,r:3,fill:"#ffffff",opacity:.82}));
  const ti=el("title");ti.textContent=(isRet?"↩ return · ":"")+tr.label;g.appendChild(ti);
  g.style.cursor="pointer";g.addEventListener("click",(e)=>{e.stopPropagation();selectTrain(tr);});
  trainLayer.appendChild(g);
  const M=routeMid(A,B);   // follow the same routed track the rail was drawn on
  const L=laneVec(tr.from,tr.to,A,B);   // perpendicular lane nudge (opposite sign for the opposite leg)
  const frames = M ? [{transform:`translate(${L.x}px,${L.y}px)`},
                      {transform:`translate(${M.x-A.x+L.x}px,${M.y-A.y+L.y}px)`},
                      {transform:`translate(${B.x-A.x+L.x}px,${B.y-A.y+L.y}px)`}]
                   : [{transform:`translate(${L.x}px,${L.y}px)`},
                      {transform:`translate(${B.x-A.x+L.x}px,${B.y-A.y+L.y}px)`}];
  const anim=g.animate(frames,{duration:RUN_MS,easing:"cubic-bezier(.35,0,.3,1)"});
  anim.onfinish=()=>{g.remove();
    const dst=document.getElementById("st_"+tr.to);
    if(dst){const rr=+dst.getAttribute("r");dst.animate([{r:rr},{r:rr*1.9},{r:rr}],{duration:520});}};
}
// ── CONTINUOUS STREAM PUMP: on a smooth 120ms tick, every live route that's due for
//    its next carriage spawns one. Because each real train registers a route (draw()),
//    live tracks show carriages flowing NON-STOP — a genuine live stream. A route that
//    the feed drops (source went quiet / aged out) stops spawning → that line goes still.
setInterval(()=>{
  _clk+=120;
  for(const r of liveRoutes.values()){
    if(_clk >= (r.nextSpawn||0)){
      r.nextSpawn=_clk+STREAM_GAP;
      spawnCarriage(r.tr,r.col);
    }
  }
},120);
// ── PERF HUD (STAGING2): live FPS + SVG-node + train count, so render health is
//    measurable and screenshot-able. rAF frame counter, DOM sampled 2×/sec. ──
// POLISH (UG-02b): GATED behind the `#perf` URL hash. In normal view the HUD is never
//    created (no overlay bloom bottom-right); a developer opens `…/#perf` to see it.
if(/perf/i.test(location.hash)){
  const _hud=document.createElement("div");
  _hud.id="perfhud";
  _hud.style.cssText="position:fixed;right:12px;bottom:12px;z-index:9999;font:12px/1.45 ui-monospace,SFMono-Regular,monospace;"
    +"background:rgba(6,12,22,.88);border:1px solid #2a3a52;border-radius:8px;padding:7px 11px;color:#8fe3b0;"
    +"box-shadow:0 2px 12px rgba(0,0,0,.55);pointer-events:none;";
  document.body.appendChild(_hud);
  let _frames=0,_fps=0,_lastT=performance.now();
  (function _hudFrame(t){
    _frames++;
    if(t-_lastT>=500){
      _fps=Math.round(_frames*1000/(t-_lastT));_frames=0;_lastT=t;
      const nodes=svg.getElementsByTagName("*").length, trains=(trainLayer?trainLayer.childElementCount:0);
      _hud.innerHTML='<b style="color:#cfe0f5">PERF</b> · '+_fps+' fps<br>'+nodes+' svg nodes<br>'+trains+' live trains';
    }
    requestAnimationFrame(_hudFrame);
  })(performance.now());
}
// ── AUTO-RECONNECT (item 4) ────────────────────────────────────────────────────
// The page polls /api/data every 1s AND survives a server restart without freezing.
// A failed fetch (service restarting) flips the header to a "reconnecting…" state and
// retries on a small exponential backoff (1s→max 5s); the instant the server answers
// again the poll resumes at 1s. If the server VERSION changes across a restart the page
// reloads to pick up any new page HTML. Ross never sees a frozen map after `systemctl
// restart qsb-transit-map`.
let _backoff=1000;              // current retry delay (ms), grows on failure
const _BOFF_MAX=5000;          // cap the backoff so recovery stays snappy
let _wasDown=false;            // were we in a failed/reconnecting state?
function _scheduleTick(ms){setTimeout(tick, ms);}
async function tick(){
  let d;
  try{
    const resp=await fetch("/api/data",{cache:"no-store"});
    if(!resp.ok)throw new Error("HTTP "+resp.status);
    d=await resp.json();
  }catch(e){
    // server down / restarting: show reconnecting, back off, and KEEP trying (no freeze)
    const h=document.getElementById("health");
    if(h){h.className="hp dead";h.textContent="○ reconnecting… (server restarting)";}
    _wasDown=true;
    _backoff=Math.min(_backoff*1.6, _BOFF_MAX);
    _scheduleTick(_backoff);
    return;
  }
  // recovered: reset backoff to the normal 1s cadence
  _backoff=1000;
  // VERSION change across a restart -> reload to pick up any new page HTML.
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  if(_wasDown){_wasDown=false;}   // came back — normal rendering resumes below
  draw(d);
  const h=document.getElementById("health");
  const n=d.recent15||0;  // == animated train count (all age-gated ≤15m)
  const flowing=liveRoutes.size;  // live tracks continuously streaming carriages
  if(n>0){h.className="hp ok";h.textContent="● LIVE STREAM · "+flowing+" tracks flowing · "+n+" real trains (≤15m)"}
  else{h.className="hp dead";h.textContent="○ IDLE — no live signal"}
  document.getElementById("movetxt").textContent=flowing+" live tracks streaming · "+n+" real trains ≤15m";
  // ── REAL-TELEMETRY STRIP (item 2): the 8 counters, all from real data ──
  const tm=d.telemetry||{};
  const isoTel=(tm.isolated_list||[]).join(", ")||"none";
  const fail=(tm.failed_list||[]).map(f=>f.id+" ("+f.reason+")").join("; ")||"none";
  const tw=(tm.twoway_list||[]).join(", ")||"none";
  const flit=(tm.floors_lit_list||[]).join(", ")||"none";
  const cards=[
    ["total_stations","Total Stations","",""],
    ["floors_total","Tower Floors","all 170 canonical floors on the map (curated + elevation)","good"],
    ["floors_lit","Floors Lit","floors with REAL recent activity (rest are idle/dim, honest): "+flit,(tm.floors_lit>0?"good":"")],
    ["active_stations","Active Stations","real train endpoint ≥1","good"],
    ["meaningful_tracks","Tracks","meaningful routes (trunk + category lines) that can carry a train — "+(tm.mesh_tracks||0)+" hidden structural mesh edges NOT counted",""],
    ["tracks_proven","Tracks Proven","carried a real train (15m)","good"],
    ["total_real_trains","Real Trains","age-gated ≤15m == animated","good"],
    ["isolated_stations","Isolated (valid)","valid, 0 trains: "+isoTel,(tm.isolated_stations>0?"warn":"")],
    ["failed_routes","Failed Routes","blocked/decommissioned: "+fail,(tm.failed_routes>0?"bad":"")],
    // ── HONEST TWO-WAY SPLIT (STAGING, UG-02): confirmed / co-active / one-way, NOT one
    //    inflated "48". confirmed = real message BOTH ways (cat != floorflow). ──
    ["twoway_confirmed","Two-way ✓","CONFIRMED bidirectional channels — a real directional message ran BOTH ways (floorflow beacons EXCLUDED). This is the honest number. "+((tm.twoway_confirmed_list||[]).join(", ")||"none"),"good"],
    ["coactive_awaiting","Co-active ⚠","both floors ticked in ONE mirrored activity tick — co-active, NOT proven communication (awaiting an addressed message): "+((tm.coactive_list||[]).join(", ")||"none"),"warn"],
    ["oneway_awaiting","One-way →","carried a train ONE way only; return lane drawn but reverse unproven (awaiting reverse proof). Count: "+(tm.oneway_awaiting||0),""],
  ];
  document.getElementById("telem").innerHTML=cards.map(c=>{
    const v=(tm[c[0]]!=null?tm[c[0]]:"—");
    return `<div class="tc ${c[3]||''}" data-key="${c[0]}" onclick="counterAction('${c[0]}')" title="${(c[2]||'').replace(/"/g,'&quot;')}"><div class=v>${v}</div><div class=l>${c[1]}</div></div>`;
  }).join("");
  if(SEL&&SEL.kind==="counter"){const el2=document.querySelector('#telem .tc[data-key="'+SEL.id+'"]');if(el2)el2.classList.add("sel");}
  // STRUCTURAL: the drawn lattice (true of the drawing, not a talk-claim)
  // Headline the MEANINGFUL tracks (item 3): the trunk backbone + category lines that
  // can actually carry a train — NOT the hidden structural mesh (that will never carry
  // one). The full mesh count is kept as a parenthetical so nothing is hidden dishonestly.
  const pf=d.proof||{};
  const meaningful=(tm.meaningful_tracks!=null?tm.meaningful_tracks:pf.edges);
  const mesh=(tm.mesh_tracks||0), proven=(tm.tracks_proven||0);
  document.getElementById("proof").textContent =
     pf.stations+" stations · "+meaningful+" meaningful tracks / "+proven+" carrying a train"
     +" ("+mesh+" more structural mesh edges hidden) · graph diameter ≤"+pf.diameter+" hops (all paths transit the Gene Pool hub)";
  // OBSERVED: only what real recent trains prove
  const ob=d.observed||{};
  const iso=(ob.isolated||[]);
  document.getElementById("observed").textContent =
     (ob.stations_active||0)+"/"+(ob.stations_total||0)+" stations active · "
     +(ob.tracks_used||0)+"/"+(ob.tracks_drawn||0)+" tracks carried a real train · "
     +(ob.talking_pairs||0)+" CEO/hub pairs actually talking"
     +(iso.length?("  ·  isolated: "+iso.join(", ")):"");
  // routed vs merely reachable (audit fix #2)
  const ra=d.routed_ais||[], rc=d.reachable_ais||[];
  document.getElementById("liveais").textContent =
     ra.length+" AI(s) doing real routing work: "+(ra.join(", ")||"—")
     +"  ·  "+rc.length+" reachable (probed, green ring, NOT routing): "+(rc.join(", ")||"—");
  // deep-link (viewing-only): #track=a↔b / #station=id / #counter=key opens the panel on
  // first load so a specific inspection can be linked/screenshotted. No side effects.
  if(location.hash&&!window._hashDone){window._hashDone=1;setTimeout(()=>{
    let m=location.hash.match(/#(track|station|counter)=(.+)/);
    if(!m)return;const k=decodeURIComponent(m[2]);
    if(m[1]==="track")selectTrack(k);else if(m[1]==="station")selectStation(k);else counterAction(k);
  },250);}
  // schedule the next poll — 1s cadence on success (Ross: 1-second refresh).
  _scheduleTick(1000);
}
// ════════════════════════════════════════════════════════════════════════════
// STAGING (UG-02) INTERACTION ENGINE — selection · inspector · search · filter · LOD
// Viewing-only: clicking a station/track/train opens a read-only detail panel. The
// COMMAND affordance is now a single explicit button inside the station panel, so
// exploring the map can never accidentally message a CEO or route a job.
// ════════════════════════════════════════════════════════════════════════════
function _kindOf(s){
  if(!s)return "station";
  if(s.floor)return "tower floor";
  if(s.prov)return "provider";
  if(s.sub)return "specialist";
  if(s.trade)return "trading floor";
  if(s.big)return "hub";
  return "station";
}
function _row(lk,vv){return `<div class=irow><span class=lk>${lk}</span><span class=vv>${vv}</span></div>`;}
function _ageTxt(a){if(a==null)return "—";return a<60?(a+"s ago"):(Math.round(a/60)+"m ago");}
function _statusPill(st){const lbl={confirmed:"CONFIRMED two-way",coactive:"co-active · awaiting proof",oneway:"one-way · awaiting reverse proof",idle:"idle (no train in window)"}[st]||st;return `<span class="pill ${st}">${lbl}</span>`;}
// which honest two-way pairs involve this station
function _pairsFor(id){
  const out=[];
  const pd=(D&&D.pair_dir)||{};
  for(const pk in pd){const p=pd[pk];
    if(p.a!==id&&p.b!==id)continue;
    let other,outLeg,inLeg;
    if(p.a===id){other=p.b;outLeg=p.ab;inLeg=p.ba;}else{other=p.a;outLeg=p.ba;inLeg=p.ab;}
    out.push({pk,other,outLeg,inLeg,status:p.status});
  }
  return out;
}
function selectStation(id){
  const s=D&&D.stations[id]; if(!s)return;
  SEL={kind:"station",id};
  const pairs=_pairsFor(id);
  const outb=pairs.filter(p=>p.outLeg.count>0), inb=pairs.filter(p=>p.inLeg.count>0);
  const tw=pairs.filter(p=>p.status==="confirmed");
  const recent=(D.trains||[]).filter(t=>t.from===id||t.to===id).sort((a,b)=>(a.age_s||1e9)-(b.age_s||1e9)).slice(0,8);
  const last=recent[0];
  let statusTxt="—";
  if(s.valid===false)statusTxt=`<span style="color:#ff5d7d">INVALID · ${s.invalid_reason||"cannot carry traffic"}</span>`;
  else if(s.offline)statusTxt=`<span style="color:#8ba0ba">offline · ${s.offline_reason||"service down"}</span>`;
  else if(s.market_closed)statusTxt=`<span style="color:#5b8fd6">market closed (after-hours)</span>`;
  else if(s.has_traffic)statusTxt=`<span style="color:#45f59b">ACTIVE · carrying real trains</span>`;
  else if(s.ghost)statusTxt=`<span style="color:#c98a2a">idle · last event ${s.last_active_label||"recently"}</span>`;
  else if(s.reachable)statusTxt=`<span style="color:#45f59b">reachable (probed) · not routing</span>`;
  else if(s.comms_online)statusTxt=`<span style="color:#3fbf8f">comms-online · no tower traffic</span>`;
  else statusTxt=`<span style="color:#8ba0ba">quiet (no live signal)</span>`;
  let html="";
  html+=_row("id",id);
  html+=_row("kind/floor",_kindOf(s)+(s.floor_num?(" · F"+s.floor_num):""));
  if(s.zone||s.zone_name)html+=_row("zone",s.zone_name||s.zone);
  if(s.prov)html+=_row("provider status",(s.status||"?")+(s.status_detail?(" · "+s.status_detail):""));
  html+=_row("status",statusTxt);
  html+=_row("online (presence)",(ON[id]?"yes":(s.comms_online?"comms only":"no")));
  if(last)html+=_row("last message",_ageTxt(last.age_s)+" · "+(last.cat||""));
  html+=_row("inbound tracks",inb.length);
  html+=_row("outbound tracks",outb.length);
  html+=`<div class=irow><span class=lk>verified two-way</span><span class=vv><span style="color:#45f59b;font-weight:800">${tw.length}</span></span></div>`;
  if(tw.length){html+=`<div class=isec>verified two-way channels</div><ul class=ilist>`+
    tw.map(p=>`<li onclick="selectTrack('${p.pk}')">↔ ${labelOf(p.other)}</li>`).join("")+`</ul>`;}
  html+=`<div class=isec>recent real trains (${recent.length})</div>`;
  if(recent.length)html+=`<ul class=ilist>`+recent.map(t=>`<li onclick="selectTrain(${JSON.stringify(t).replace(/"/g,'&quot;')})"><span style="color:${CC[t.cat]||'#40b4ff'}">●</span> ${_esc(t.label)} · ${_ageTxt(t.age_s)}</li>`).join("")+`</ul>`;
  else html+=`<div style="color:#8ba0ba;font-size:12px;margin-top:6px">no real train in the last 15m — this node is honestly quiet.</div>`;
  // COMMAND button (explicit, opt-in — the only way to command from the inspector)
  if(actionsFor(id).length)html+=`<button class="ibtn" onclick="openCmd('${id}','${_esc(s.label)}')">⚙ Command this node…</button> `;
  html+=`<button class="ibtn sec" onclick="focusStation('${id}')">◎ Center on map</button>`;
  _showInsp(s.label,_kindOf(s)+(s.floor_num?(" · F"+s.floor_num):""),html);
  highlightStations([id,...tw.map(p=>p.other)]);
}
function selectTrack(pk){
  if(!D)return;
  const p=(D.pair_dir||{})[pk];
  const line=(D.lines||[]).find(L=>(L.id===pk)||(pkOf(L.a,L.b)===pk));
  const a=p?p.a:(line?line.a:pk.split("↔")[0]), b=p?p.b:(line?line.b:pk.split("↔")[1]);
  SEL={kind:"track",id:pk};
  const st=p?p.status:"idle", cat=line?line.cat:"—";
  const ab=p?p.ab:{count:0}, ba=p?p.ba:{count:0};
  let html="";
  html+=_row("id",pk);
  html+=_row("origin",labelOf(a));
  html+=_row("dest",labelOf(b));
  html+=_row("category",cat);
  html+=`<div class=irow><span class=lk>direction</span><span class=vv>${_statusPill(st)}</span></div>`;
  // ── PER-DIRECTION, NEVER COLLAPSED (item 1). Each way shown independently with its own
  //    last-time / count / status. If one way is failing, it is NOT hidden behind the other.
  html+=`<div class=isec>each direction (independent)</div>`;
  const dline=(lab,leg)=>{const active=(leg.count>0&&leg.last_age!=null&&leg.last_age<=900);
    return `<div class=dl><b>${lab}</b><span class="st ${active?'act':'q'}">${leg.count>0?((active?'active ':'seen ')+_ageTxt(leg.last_age)+' · '+leg.count+'×'):'no traffic — awaiting proof'}</span></div>`;};
  html+=`<div class=dirbox>`+
        dline(_short(a)+"→"+_short(b),ab)+
        dline(_short(b)+"→"+_short(a),ba)+`</div>`;
  // reverse-route + evidence
  const revOk = ab.count>0 && ba.count>0;
  html+=_row("reverse route",revOk?`<span style="color:#45f59b">both legs ran</span>`:`<span style="color:#9db3cc">one-way so far</span>`);
  if(st==="coactive")html+=`<div style="color:#ffb020;font-size:12px;margin-top:6px">⚠ co-active floor beacons: both floors ticked in one shared activity tick (mirrored), NOT a real message. Awaiting an addressed message to confirm two-way.</div>`;
  const evc=[...new Set([...(ab.cats||[]),...(ba.cats||[])])].filter(Boolean).join(", ")||"—";
  html+=_row("evidence source",evc);
  html+=_row("latest a→b",ab.label?_esc(ab.label):"—");
  html+=_row("latest b→a",ba.label?_esc(ba.label):"—");
  _showInsp(_short(a)+" ↔ "+_short(b),"track · "+st,html);
  highlightStations([a,b]);highlightTrack(pk);
}
function selectTrain(tr){
  if(!tr)return;
  SEL={kind:"train",id:tr.id||("t_"+tr.from+"_"+tr.to)};
  const pk=pkOf(tr.from,tr.to), p=(D&&D.pair_dir||{})[pk];
  let html="";
  html+=_row("train id",tr.id||"—");
  html+=_row("event / label",_esc(tr.label||""));
  html+=_row("source",labelOf(tr.from));
  html+=_row("dest",labelOf(tr.to));
  html+=_row("event type",tr.cat||"—");
  html+=_row("departed",tr.ts||"—");
  html+=_row("age (latency window)",_ageTxt(tr.age_s));
  html+=_row("status",`<span style="color:#45f59b">delivered · real age-gated event ≤15m</span>`);
  if(p)html+=`<div class=irow><span class=lk>its track</span><span class=vv>${_statusPill(p.status)}</span></div>`;
  html+=`<button class="ibtn sec" onclick="selectTrack('${pk}')">↔ Inspect this track</button>`;
  _showInsp("train · "+_short(tr.from)+"→"+_short(tr.to),"train · "+(tr.cat||""),html);
  highlightStations([tr.from,tr.to]);highlightTrack(pk);
}
function _showInsp(title,kind,bodyHtml){
  document.getElementById("iTitle").textContent=title;
  document.getElementById("iKind").textContent=kind;
  document.getElementById("iBody").innerHTML=bodyHtml;
  document.getElementById("insp").classList.add("open");
}
function _esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function _short(id){const l=labelOf(id);return l.split(" ·")[0].split(" ")[0];}
// highlight = glow the given stations, dim everything else (until cleared)
function highlightStations(ids){
  const set=new Set(ids);
  Object.keys(ST||{}).forEach(id=>{
    const c=document.getElementById("st_"+id), lb=document.getElementById("lb_"+id);
    const on=set.has(id);
    if(c){c.classList.toggle("selglow",on);c.classList.toggle("dimmed",!on&&set.size>0);}
    if(lb)lb.classList.toggle("dimmed",!on&&set.size>0);
  });
}
function highlightTrack(pk){
  document.querySelectorAll('[data-pk]').forEach(p=>{
    p.classList.toggle("selglow",p.getAttribute("data-pk")===pk);
    p.classList.toggle("dimmed",p.getAttribute("data-pk")!==pk);
  });
}
function focusStation(id){const s=D&&D.stations[id];if(!s||!BASE_VIEW)return;
  const w=BASE_VIEW.w/3.2,h=BASE_VIEW.h/3.2;VIEW={x:s.x-w/2,y:s.y-h/2,w,h};applyView();refreshView();}
// ── SEARCH + FILTER + LOD ──────────────────────────────────────────────────────
function _matchSearch(id,s){
  if(!SEARCH)return true;const q=SEARCH;
  if(id.toLowerCase().includes(q))return true;
  if((s.label||"").toLowerCase().includes(q))return true;
  if(s.floor_num!=null&&(("f"+s.floor_num)===q||String(s.floor_num)===q||("floor "+s.floor_num).includes(q)))return true;
  if((s.zone||s.zone_name||"").toLowerCase().includes(q))return true;
  return false;
}
function _matchFilter(id,s){
  if(FILTER==="all")return true;
  if(FILTER==="active")return !!s.has_traffic||!!s.floor_active;
  if(FILTER==="failed")return s.valid===false||s.offline||(s.prov&&s.status_band&&s.status_band!=="live");
  if(FILTER==="provider")return !!s.prov;
  if(FILTER==="ai")return ["wren","bill","tp_pip","acer_cass","codex","oracle","gene_pool","council15","task_council","claude_acct","hermes","iquest_40b","qwen_worker","wren_brain"].includes(id);
  // two-way / co-active / one-way: station participates in a pair of that status
  const want={twoway:"confirmed",coactive:"coactive",oneway:"oneway"}[FILTER];
  if(want)return _pairsFor(id).some(p=>p.status===want);
  return true;
}
function refreshView(){
  if(!D)return;
  const z=_curZoom();
  const searching=(SEARCH||FILTER!=="all");
  const selecting=(SEL!=null);
  Object.entries(ST||{}).forEach(([id,s])=>{
    const c=document.getElementById("st_"+id), lb=document.getElementById("lb_"+id);
    // search/filter dim (skip while an explicit selection is highlighting)
    if(searching&&!selecting){
      const vis=_matchSearch(id,s)&&_matchFilter(id,s);
      if(c)c.classList.toggle("dimmed",!vis);
      if(lb)lb.classList.toggle("dimmed",!vis);
    }else if(!selecting){
      if(c)c.classList.remove("dimmed");
      if(lb)lb.classList.remove("dimmed");
    }
    // LOD label hiding (item 5): zoomed OUT hide secondary labels to kill overlap; zoomed IN show all
    if(lb&&!selecting&&!(searching)){
      const primary=(s.big||s.prov||s.trade||s.has_traffic||s.floor_active);
      let show=true;
      if(z<0.8)show=(s.big||s.has_traffic&&!s.floor); // very zoomed out: only hubs + live curated
      else if(z<1.15)show=primary;                    // medium: primary only
      else show=true;                                 // zoomed in: everything
      // PERF (STAGING2): when zoomed in, cull labels for stations off the current viewport.
      if(show&&z>1.2&&!_inView(s.x,s.y,70))show=false;
      lb.style.display=show?"":"none";
    } else if(lb){lb.style.display="";}
  });
}
// ── clickable telemetry counters → highlight the nodes/pairs they describe ──────
function counterAction(key){
  if(!D)return;const tm=D.telemetry||{};
  clearSel(true);
  if(key==="twoway_confirmed"){const ids=new Set();(tm.twoway_confirmed_list||[]).forEach(pk=>{const[a,b]=pk.split("↔");ids.add(a);ids.add(b);});highlightStations([...ids]);
    document.querySelectorAll('[data-pk]').forEach(p=>{const on=(tm.twoway_confirmed_list||[]).includes(p.getAttribute("data-pk"));p.classList.toggle("selglow",on);p.classList.toggle("dimmed",!on);});}
  else if(key==="coactive_awaiting"){const ids=new Set();(tm.coactive_list||[]).forEach(pk=>{const[a,b]=pk.split("↔");ids.add(a);ids.add(b);});highlightStations([...ids]);}
  else if(key==="oneway_awaiting"){const ids=new Set();(tm.oneway_list||[]).forEach(pk=>{const[a,b]=pk.split(/[→↔]/);ids.add(a);ids.add(b);});highlightStations([...ids]);}
  else if(key==="failed_routes")highlightStations((tm.failed_list||[]).map(f=>f.id));
  else if(key==="isolated_stations")highlightStations(tm.isolated_list||[]);
  else if(key==="floors_lit")highlightStations(tm.floors_lit_list||[]);
  else if(key==="active_stations"){const ids=Object.keys(ST).filter(id=>ST[id].has_traffic);highlightStations(ids);}
  SEL={kind:"counter",id:key};
}
function clearSel(keepPanel){
  SEL=null;
  document.querySelectorAll('.selglow').forEach(e=>e.classList.remove('selglow'));
  document.querySelectorAll('.dimmed').forEach(e=>e.classList.remove('dimmed'));
  document.querySelectorAll('#telem .tc.sel').forEach(e=>e.classList.remove('sel'));
  if(!keepPanel){document.getElementById('insp').classList.remove('open');}
  refreshView();
}
// wire controls once
document.getElementById("search").addEventListener("input",e=>{SEARCH=e.target.value.trim().toLowerCase();clearSel(true);refreshView();});
document.querySelectorAll("#ctl .chip[data-f]").forEach(ch=>ch.addEventListener("click",()=>{
  document.querySelectorAll("#ctl .chip[data-f]").forEach(c=>c.classList.remove("on"));
  ch.classList.add("on");FILTER=ch.getAttribute("data-f");clearSel(true);refreshView();
}));
document.getElementById("clrsel").addEventListener("click",()=>{SEARCH="";document.getElementById("search").value="";
  FILTER="all";document.querySelectorAll("#ctl .chip[data-f]").forEach(c=>c.classList.remove("on"));
  document.querySelector('#ctl .chip[data-f=all]').classList.add("on");clearSel(false);});
document.querySelector('#ctl .chip[data-f=all]').classList.add("on");
// ONESIZE overlay toggles: flip the draw flag, restyle the chip, force a rail rebuild.
function _wireOverlayToggle(id,get,set){const c=document.getElementById(id);if(!c)return;
  c.addEventListener("click",()=>{set(!get());c.classList.toggle("on",get());_lastSig=null;if(D)draw(D);});}
_wireOverlayToggle("tglDept",()=>SHOW_DEPT,v=>SHOW_DEPT=v);
_wireOverlayToggle("tglLift",()=>SHOW_LIFT,v=>SHOW_LIFT=v);
// clicking empty map space clears a selection
svg.addEventListener("click",e=>{if(e.target===svg||e.target.id==="railLayer")clearSel(false);});

tick();  // self-scheduling loop (item 4): 1s on success, backoff-and-retry on failure
</script></body></html>"""


import urllib.request as _urlreq


def _post(url, payload):
    try:
        req = _urlreq.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with _urlreq.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def command(payload):
    """Interactive control room: click a station -> a REAL command."""
    st = payload.get("station")
    action = payload.get("action")
    text = (payload.get("text") or "").strip()[:600]
    if action == "route_job":
        r = _post("http://127.0.0.1:8860/api/submit_job", {"task": text or "default"})
        return {"ok": r.get("ok", True), "result": "routed a job through the Gene Pool", "detail": str(r)[:220]}
    if action == "book_task":
        import sys
        sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
        try:
            import qsb_council_tasks as C
            r = C.create(text or "Ross task via control room", "", "ross_knechtel")
            tid = r.get("task_id") if isinstance(r, dict) else r
            return {"ok": True, "result": "booked Task Council task " + str(tid)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:160]}
    if action == "message":
        r = _post("http://127.0.0.1:8852/api/post", {"from": "ross", "target": st, "text": text or "hello from Ross"})
        return {"ok": r.get("ok", True), "result": "message sent to " + str(st)}
    return {"ok": False, "error": "unknown action"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path.startswith("/api/command"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            b = json.dumps(command(payload)).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/data"):
            b = json.dumps(build()).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8875)
    a = ap.parse_args()
    print(f"tower tube map on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
