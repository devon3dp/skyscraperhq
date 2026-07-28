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
KEY_HEALTH = REG / "qsb_gene_pool_key_health.json"
VER = str(int(time.time()))
AGE_MAX = 900  # seconds — trains older than this NEVER animate (honest stillness)

# provider live/dead status buckets (from qsb_gene_pool_key_health.json)
STATUS_LIVE = {"LIVE"}
STATUS_AMBER = {"NO_CREDIT", "QUOTA"}
STATUS_DEAD = {"BLOCKED", "ENDPOINT_GONE", "NO_KEY", "BAD_KEY"}
# health-file key -> map station key (health uses nvidia_nim; station fan has no nvidia_nim)
HEALTH_ALIAS = {"nvidia_nim": "nvidia_nim"}

STATIONS = {
    # ── CENTRAL SPINE (hubs) — single column x=600, evenly stacked on 40px grid ──
    "town_square":  {"x": 600, "y": 80,  "label": "Town Square · 74",  "big": True},
    "boardroom":    {"x": 600, "y": 240, "label": "Boardroom Hub",      "big": True},
    "task_council": {"x": 600, "y": 400, "label": "Task Council · 77",  "big": True},
    "council15":    {"x": 600, "y": 560, "label": "Council of 15 · 75", "big": True},
    # ── LEFT BLOCK: CEOs / AIs — two tidy columns (x=140, x=300) ──
    "bill":         {"x": 140, "y": 120, "label": "Bill · Mac F47"},
    "tp_pip":       {"x": 140, "y": 240, "label": "TP-Pip"},
    "acer_cass":    {"x": 140, "y": 360, "label": "Asa"},
    "codex":        {"x": 140, "y": 480, "label": "Codex · 40"},
    "wren":         {"x": 300, "y": 240, "label": "Wren · 46", "big": True},
    "lumen":        {"x": 300, "y": 480, "label": "Lumen · 48", "offline": True,
                     "offline_reason": ":8848 down — service offline"},
    # ── WREN / C15 SPECIALIST CLUSTER — around Wren + bottom-left cluster ──
    "wren_brain":   {"x": 300, "y": 120, "label": "Wren·qwen14b", "sub": True},
    "f46_bench":    {"x": 440, "y": 160, "label": "F46 Bench",    "sub": True},
    "iquest_40b":   {"x": 300, "y": 620, "label": "iQuest-40B",   "sub": True},
    "qwen_worker":  {"x": 420, "y": 620, "label": "qwen worker",  "sub": True},
    "hermes":       {"x": 540, "y": 660, "label": "Hermes",       "sub": True},
    "claude_acct":  {"x": 180, "y": 620, "label": "Claude",       "sub": True},
    "tc_sandbox":   {"x": 460, "y": 460, "label": "Sandbox",      "sub": True},
    # ── ORACLE — distinct node, tunnels up the spine ──
    "oracle":       {"x": 600, "y": 660, "label": "Oracle · Cloud VM", "big": True},
    # ── GENE POOL — interchange node, then an 8-way fan on the right ──
    "gene_pool":    {"x": 880,  "y": 320, "label": "Gene Pool · 24", "big": True},
    "kimi":         {"x": 1060, "y": 100, "label": "kimi",     "prov": True},
    "openai":       {"x": 1120, "y": 180, "label": "openai",   "prov": True},
    "deepseek":     {"x": 1140, "y": 260, "label": "deepseek", "prov": True},
    "cohere":       {"x": 1160, "y": 340, "label": "cohere",   "prov": True},
    "gemini":       {"x": 1140, "y": 420, "label": "gemini",   "prov": True},
    "groq":         {"x": 1120, "y": 500, "label": "groq",     "prov": True},
    "grok":         {"x": 1060, "y": 580, "label": "grok",     "prov": True},
    "claude":       {"x": 1000, "y": 640, "label": "claude",   "prov": True},
    "nvidia_nim":   {"x": 980,  "y": 200, "label": "nvidia",   "prov": True},
}
PROV = {"openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok", "claude",
        "nvidia_nim", "ollama_lan", "ollama_local"}

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
KNOWN_DEAD = {"oracle", "lumen", "f46_bench"}
KNOWN_DEAD_REASON = {
    "oracle": "dead VM — no event source",
    "lumen": ":8848 offline — no event source",
    "f46_bench": "no event source",
}

CORE = ["wren", "tp_pip", "acer_cass", "bill", "codex", "lumen"]
HUBS = ["boardroom", "town_square", "task_council", "council15", "gene_pool"]
PROVIDERS = ["openai", "deepseek", "cohere", "gemini", "groq", "kimi", "grok", "claude", "nvidia_nim"]
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
             "mesh": "#33465f"}
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
    ("gene_pool", "grok"), ("gene_pool", "claude"), ("gene_pool", "nvidia_nim"),
    ("council15", "iquest_40b"), ("council15", "qwen_worker"),
    ("council15", "hermes"), ("council15", "claude_acct"), ("council15", "gene_pool"),
    ("oracle", "council15"), ("boardroom", "gene_pool"),
]
# every EVERYONE→TASK COUNCIL spur is a trunk line — always visible, never buried in the mesh
_TRUNK += [(s, "task_council") for s in _COUNCIL_SPUR] + [("gene_pool", "task_council")]
TRUNK_SET = {tuple(sorted(e)) for e in _TRUNK}
PRES_MAP = {"wren": "wren", "tp": "tp_pip", "asa": "acer_cass", "bill": "bill", "pip": "tp_pip"}
# comms logs use short names (asa/tp/pip); stations are keyed acer_cass/tp_pip. Resolve so
# TP↔Asa room posts, acks, and DM lines actually become trains ("everyone talking").
ALIAS = {"asa": "acer_cass", "tp": "tp_pip", "pip": "tp_pip", "tp_pip": "tp_pip",
         "acer_cass": "acer_cass", "wren": "wren", "bill": "bill"}


def _sid(name):
    """Resolve a comms-log actor name to a station key, or None if not a station."""
    if not name:
        return None
    s = ALIAS.get(name, name)
    return s if s in STATIONS else None


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
    if "iquest" in t: return "iquest_40b"
    if "hermes" in t: return "hermes"
    if "claude" in t: return "claude_acct"
    if "qwen" in t: return "qwen_worker"
    return "qwen_worker"


def _parse_ts(ts):
    """Best-effort parse of an ISO-ish ts to epoch seconds; None on failure."""
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


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


def _connectivity():
    """STRUCTURAL connectivity: BFS over the hardcoded LINES lattice (the DRAWING).
    This is true of the drawn graph — NOT a claim that parties actually talk."""
    nodes = set(STATIONS)
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
    stations are genuinely isolated (codex/lumen/oracle/f46_bench WILL show up)."""
    nodes = set(STATIONS)
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
    for r in _tail(COUNCIL, 90):
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
        if seg:
            trains.append({"from": seg[0], "to": seg[1], "ts": r.get("ts"), "cat": "council",
                           "label": (actor or "?") + " " + (ev or "") + " " + (tid or "")})
        # SUB-TRACK trains
        if ev == "tool_selected":
            spec = _tool_station(r.get("text"))
            trains.append({"from": "council15", "to": spec, "ts": r.get("ts"), "cat": "c15",
                           "label": "Council of 15 → " + spec})
            trains.append({"from": "wren", "to": spec, "ts": r.get("ts"), "cat": "wrensub",
                           "label": "Wren wields " + spec})
        elif ev in ("sandbox_passed", "sandbox_rejected"):
            trains.append({"from": "task_council", "to": "tc_sandbox", "ts": r.get("ts"), "cat": "council",
                           "label": "sandbox " + (ev or "")})
        elif ev == "done":
            trains.append({"from": "task_council", "to": "wren", "ts": r.get("ts"), "cat": "council",
                           "label": "Wren gate: done " + (tid or "")})
    # Wren's own brain (her local qwen replies)
    for r in _tail(REG / "qsb_wren_dash_chat.jsonl", 20):
        if r.get("reply") or (r.get("role") or r.get("from") or "").lower() == "wren":
            trains.append({"from": "wren", "to": "wren_brain", "ts": r.get("ts", ""), "cat": "wrensub",
                           "label": "Wren thinking · qwen14b"})
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
        if age > AGE_MAX or age < -60:  # too old, or absurd future ts
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

    # balance categories so routing traffic doesn't DROWN the comms mesh.
    # Cap by FRESHNESS (smallest age_s first), NOT list position, so a genuinely
    # recent room post always beats an older DM when the cap bites (bug #1 fix).
    _bc = {}
    for t in trains:
        _bc.setdefault(t["cat"], []).append(t)
    trains = []
    # route/provider now carry BOTH request and reply legs — bigger cap so both directions show
    for cat, K in (("route", 24), ("provider", 24), ("comms", 24),
                   ("council", 12), ("c15", 8), ("wrensub", 8)):
        bucket = sorted(_bc.get(cat, []), key=lambda t: t.get("age_s", 1e9))
        trains += bucket[:K]

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

    # attach LIVE/DEAD provider status + honest reachable/traffic flags to each station
    stations = {}
    for sid, s in STATIONS.items():
        s2 = dict(s)
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
        elif sid in KNOWN_DEAD:
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
        # audit fix #4: truly-silent station (no train, not online) -> dim/dashed roundel.
        if not s2["has_traffic"] and not online.get(sid) and not s.get("offline"):
            s2["silent"] = True
        stations[sid] = s2

    # HONEST LIVE badge (audit fix #3): all `trains` are already age-gated to AGE_MAX,
    # so recent == the animated set. No inflation.
    recent = len(trains)

    # ── THE 8 REAL-TELEMETRY COUNTERS (item 2) ──────────────────────────────────
    # Every number is derived from the SAME real, age-gated, de-duped `trains` and
    # the drawn `LINES`/`STATIONS`. No inflation: total_real_trains == len(trains),
    # tracks_proven == count of lines whose act>0 (both computed here, not restated).
    lines_out = [{"a": a, "b": b, "cat": c, "act": act.get((a, b), 0) + act.get((b, a), 0),
                  "trunk": tuple(sorted((a, b))) in TRUNK_SET} for a, b, c in LINES]
    # directed leg presence for two-way detection: (a,b) present AND (b,a) present.
    directed = {(t["from"], t["to"]) for t in trains}
    twoway = {tuple(sorted((a, b))) for (a, b) in directed if (b, a) in directed and a != b}
    # VALID / INVALID partitions from the classified `stations` dict above.
    invalid_ids = sorted(sid for sid, s in stations.items() if not s.get("valid", True))
    valid_ids = [sid for sid, s in stations.items() if s.get("valid", True)]
    # isolated = VALID stations that carried ZERO real trains (invalid ones excluded
    # here — they're reported separately under failed_routes).
    isolated_valid = sorted(sid for sid in valid_ids if sid not in traffic_stations)
    telemetry = {
        "total_stations":    len(STATIONS),
        "active_stations":   len(traffic_stations),
        "total_tracks":      len(lines_out),
        "tracks_proven":     sum(1 for L in lines_out if L["act"] > 0),
        "total_real_trains": len(trains),
        "isolated_stations": len(isolated_valid),
        "isolated_list":     isolated_valid,
        "failed_routes":     len(invalid_ids),
        "failed_list":       [{"id": i, "reason": stations[i].get("invalid_reason", "")} for i in invalid_ids],
        "twoway_routes":     len(twoway),
        "twoway_list":       ["↔".join(e) for e in sorted(twoway)],
    }

    return {"ver": VER, "telemetry": telemetry, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stations": stations, "online": online,
            "lines": lines_out,
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
.wrap{max-width:1300px;margin:0 auto;padding:14px}
h1{margin:0;font-size:20px}.sub{color:var(--dim);margin:2px 0 8px}
.hp{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12px;margin-left:8px}
.hp.ok{background:rgba(69,245,155,.15);color:#45f59b;border:1px solid #45f59b}
.hp.dead{background:rgba(255,93,125,.15);color:#ff5d7d;border:1px solid #ff5d7d}
#map{width:100%;height:700px;background:radial-gradient(circle at 62% 44%,#0f1a2c,#080c14 72%);border:1px solid var(--line);border-radius:16px}
.rail{fill:none;stroke-linecap:round;stroke-linejoin:round}
.roundel{fill:#0a0e16;stroke:#e8f1ff;stroke-width:3}
.roundel.big{stroke-width:4}.roundel.prov{stroke-width:2}
.on{stroke:#45f59b}
/* provider status roundels (item 1) */
.roundel.p-live{stroke:#45f59b;filter:drop-shadow(0 0 6px #45f59b)}
.roundel.p-amber{stroke:#ffb020}
.roundel.p-dead{stroke:#5a6577;fill:#161b26}
.roundel.p-unknown{stroke:#5a6577}
/* offline dead station (item 5) */
.roundel.off{stroke:#5a6577;stroke-dasharray:3 3;fill:#12161f;opacity:.6}
/* truly-silent station: drawn but no live signal (audit fix #4) */
.roundel.silent{stroke:#4a566b;stroke-dasharray:3 3;fill:#0d121c;opacity:.5}
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
.stlabel.big{font-size:13px;font-weight:700}.stlabel.prov{fill:#8fe6b5;font-size:10px}
.train{filter:drop-shadow(0 0 6px currentColor)}
.legend{display:flex;gap:14px;color:var(--dim);font-size:12px;margin-top:8px;flex-wrap:wrap;align-items:center}
.k{display:inline-block;width:22px;height:5px;border-radius:3px;margin-right:6px;vertical-align:middle}
.kd{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle;border:2px solid}
</style></head><body><div class=wrap>
<h1>SkyscraperHQ · Underground <span style="color:#40b4ff">· :8875</span><span id=health class="hp ok">—</span></h1>
<div class=sub><b style="color:#7f93ad">STRUCTURAL:</b> <span id=proof style="color:#9db3cc"></span></div>
<div class=sub><b style="color:#45f59b">OBSERVED (last 15m):</b> <span id=observed style="color:#8fe6b5;font-weight:600"></span></div>
<div class=sub><span id=liveais style="color:#8fe6b5"></span> · every animated train is a REAL event ≤15m old — a quiet line stays still.</div>
<div id=telem></div>
<svg id=map></svg>
<div class=legend>
  <span><span class=k style="background:#40b4ff"></span>routing ⇄ Gene Pool (request+reply)</span>
  <span><span class=k style="background:#45f59b"></span>Gene-Pool ⇄ provider (2-way sub-track)</span>
  <span><span class=k style="background:#b98bff"></span>council (task-council spurs)</span>
  <span><span class=k style="background:#ffc24b"></span>comms mesh</span>
  <span><span class=k style="background:#6d7f98"></span>hub</span>
  <span><span class=k style="background:#2dd4bf"></span>Council-15</span>
  <span><span class=k style="background:#c4a3ff"></span>Wren sub</span>
  <span style="border-left:1px solid #233146;padding-left:12px"><span class=kd style="border-color:#45f59b"></span>provider LIVE</span>
  <span><span class=kd style="border-color:#ffb020"></span>amber (no-credit/quota)</span>
  <span><span class=kd style="border-color:#5a6577"></span>dead (blocked/gone/no-key)</span>
  <span id=movetxt></span>
  <span style="color:#8ba0ba">· click any station to command it</span>
</div>
<div id=cmd style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:60" onclick="if(event.target===this)this.style.display='none'">
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
const svg=document.getElementById("map");let ST={},TR=[],CC={},ON={},qi=0;
// Orthogonal / 45° router — replaces raw diagonals so tracks read like a tube map.
// straight when horiz/vert or a clean 45°; otherwise a single L-elbow (long axis first, 45° corner into B).
function routePath(A,B){
  const dx=B.x-A.x, dy=B.y-A.y;
  if(Math.abs(dx)<2||Math.abs(dy)<2) return `M ${A.x} ${A.y} L ${B.x} ${B.y}`;      // pure H or V
  if(Math.abs(Math.abs(dx)-Math.abs(dy))<8) return `M ${A.x} ${A.y} L ${B.x} ${B.y}`; // 45° diagonal
  const s=Math.sign, k=Math.min(Math.abs(dx),Math.abs(dy));
  if(Math.abs(dx)>Math.abs(dy)){const mx=B.x - s(dx)*k; return `M ${A.x} ${A.y} L ${mx} ${A.y} L ${B.x} ${B.y}`;}
  const my=B.y - s(dy)*k; return `M ${A.x} ${A.y} L ${A.x} ${my} L ${B.x} ${B.y}`;
}
// midpoint of a routed edge (the elbow) so carriages follow the same track, not a raw diagonal.
function routeMid(A,B){
  const dx=B.x-A.x, dy=B.y-A.y;
  if(Math.abs(dx)<2||Math.abs(dy)<2||Math.abs(Math.abs(dx)-Math.abs(dy))<8) return null;
  const s=Math.sign, k=Math.min(Math.abs(dx),Math.abs(dy));
  if(Math.abs(dx)>Math.abs(dy))return {x:B.x - s(dx)*k, y:A.y};
  return {x:A.x, y:B.y - s(dy)*k};
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
    ["inval","#ff5d7d","INVALID / decommissioned — cannot carry real traffic"],
  ];
  const x0=18, y0=700-rows.length*17-30, w=278, h=rows.length*17+26;
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
    else{g.appendChild(el("circle",{cx:x0+8,cy:y-1,r:6,fill:"#0a0e16",stroke:rw[1],"stroke-width":3}));}
    const t=el("text",{x:x0+30,y:y+2,class:"stlabel",fill:"#9db3cc","font-size":10});t.textContent=rw[2];g.appendChild(t);
  });
  svg.appendChild(g);
}
function draw(d){
  ST=d.stations;CC=d.cat_color;ON=d.online||{};svg.innerHTML="";svg.setAttribute("viewBox","0 0 1200 700");
  d.lines.forEach(L=>{const A=ST[L.a],B=ST[L.b];if(!A||!B)return;
    // TRUTH (audit fix #4): a rail is BRIGHT SOLID only if it carried a REAL train in the
    // last 15m (L.act>0). Everything else — potential-but-unused track — is faint DASHED grey.
    // This dashes ~59/78 edges: every gene_pool→kimi/grok/gemini/nvidia spoke, and all
    // codex/lumen/oracle edges, honestly showing they carry no live signal.
    const act=L.act>0;
    const col = act ? (CC[L.cat]||"#40b4ff") : "#4a627e";
    const w   = act ? 6 : 2.2;
    const op  = act ? 0.95 : 0.45;  // brighter mesh so "everyone connects to everyone" is visible
    const p=el("path",{class:"rail",d:routePath(A,B),stroke:col,"stroke-width":w,opacity:op});
    if(!act)p.setAttribute("stroke-dasharray","5 6");  // dashed = potential track, never used in window
    svg.appendChild(p);});
  Object.entries(ST).forEach(([id,s])=>{
    const r=s.big?13:((s.prov||s.sub)?7:9),online=ON[id];
    // RING semantics (audit fix #2 & #6):
    //  - green solid ring = presence heartbeat AND actually carrying tower trains
    //  - green dashed ring = comms-online only (relay heartbeat, NO tower traffic) — e.g. Bill
    //  - provider "reachable" = passed the 15-min health probe: green ring = responds,
    //    but that is NOT routed work (only a real train means real work).
    if(online&&!s.offline&&s.has_traffic){
      svg.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+5,fill:"none",stroke:"#45f59b","stroke-width":2,opacity:.8,id:"on_"+id}));
    } else if(s.comms_online&&!s.offline){
      svg.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+5,fill:"none",stroke:"#3fbf8f","stroke-width":2,opacity:.7,"stroke-dasharray":"3 4",id:"on_"+id}));
    } else if(s.reachable){  // provider probed-reachable but not routing work
      svg.appendChild(el("circle",{cx:s.x,cy:s.y,r:r+4,fill:"none",stroke:"#45f59b","stroke-width":1.6,opacity:.55,"stroke-dasharray":"2 3",id:"rc_"+id}));
    }
    // roundel base class: invalid / offline / silent / provider-band / online-solid
    // INVALID (item 1) wins: a decommissioned/blocked node draws as a red-dashed
    // roundel so it's visibly NOT part of the live network, even if it's a provider.
    let cls="roundel"+(s.big?" big":"")+(s.prov?" prov":"")+(online&&!s.offline&&s.has_traffic?" on":"");
    if(s.valid===false)cls+=" invalid";
    else if(s.offline)cls+=" off";
    else if(s.prov)cls+=" p-"+(s.status_band||"unknown");
    else if(s.silent)cls+=" silent";
    const stc=el("circle",{cx:s.x,cy:s.y,r:r,class:cls,id:"st_"+id});
    stc.style.cursor="pointer";stc.addEventListener("click",()=>openCmd(id,s.label));
    // HONEST tooltips
    const ti=el("title");
    if(s.valid===false)ti.textContent=s.label+" — DECOMMISSIONED / BLOCKED · "+(s.invalid_reason||"cannot carry real traffic")+" (NOT part of the live network)";
    else if(s.offline)ti.textContent=s.label+" — offline · "+(s.offline_reason||"service down");
    else if(s.comms_online)ti.textContent=s.label+" — comms-online (relay heartbeat) · no tower traffic";
    else if(s.prov)ti.textContent=s.label+" — "+(s.status||"?")+(s.status_detail?" · "+s.status_detail:"")+(s.reachable&&!s.has_traffic?" · reachable (probed), NOT routing work":"")+(s.has_traffic?" · routing real work":"");
    else if(s.silent)ti.textContent=s.label+" — no live signal (track drawn, no traffic in last 15m)";
    else ti.textContent=s.label;
    stc.appendChild(ti);svg.appendChild(stc);
    // provider fan on the right: label to the RIGHT of the roundel so the fan stays clean.
    // everything else: label above the roundel, centred.
    let t;const inv=s.valid===false;
    if(s.prov){t=el("text",{x:s.x+r+7,y:s.y+3,"text-anchor":"start",class:"stlabel prov"+(inv?" invalid":"")});}
    else{t=el("text",{x:s.x,y:s.y-(s.big?22:18),"text-anchor":"middle",class:"stlabel"+(s.big?" big":"")+(s.offline?" off":"")+(inv?" invalid":"")});}
    t.textContent=s.label+(inv?" · blocked":(s.offline?" · offline":""));svg.appendChild(t);
  });
  drawLegend();
  TR=d.trains||[];
}
const AGE_MAX=900; // seconds — client-side guard: never animate a stale/undated train (audit fix #1)
function launch(tr){
  const A=ST[tr.from],B=ST[tr.to];if(!A||!B)return;
  // AGE GUARD (audit fix #1): a train with no age_s, or older than 15m, NEVER moves.
  // build() already age-gates, but guard here too so a quiet line is provably still.
  if(tr.age_s==null||tr.age_s>AGE_MAX)return;
  // don't run carriages to a dead/amber provider — only LIVE provider lines carry trains
  const pv=A.prov?A:(B.prov?B:null);
  if(pv&&pv.status_band&&pv.status_band!=="live")return;
  const col=CC[tr.cat]||"#40b4ff";
  const g=el("g",{class:"train"});g.style.color=col;
  g.appendChild(el("rect",{x:A.x-12,y:A.y-5,width:11,height:10,rx:3,fill:col}));
  g.appendChild(el("rect",{x:A.x+1,y:A.y-5,width:11,height:10,rx:3,fill:col,opacity:.85}));
  const ti=el("title");ti.textContent=tr.label;g.appendChild(ti);svg.appendChild(g);
  // follow the routed track: through the elbow midpoint if the edge bends, else straight.
  const M=routeMid(A,B);
  const frames = M ? [{transform:"translate(0,0)"},{transform:`translate(${M.x-A.x}px,${M.y-A.y}px)`},
                      {transform:`translate(${B.x-A.x}px,${B.y-A.y}px)`}]
                   : [{transform:"translate(0,0)"},{transform:`translate(${B.x-A.x}px,${B.y-A.y}px)`}];
  g.animate(frames,{duration:1700,easing:"cubic-bezier(.35,0,.3,1)"}).onfinish=()=>{g.remove();
      const dst=document.getElementById("st_"+tr.to);if(dst){const rr=+dst.getAttribute("r");dst.animate([{r:rr},{r:rr*1.5},{r:rr}],{duration:450})}};
}
// fire several trains per tick so MANY carriages move at once (everyone talking, visibly)
setInterval(()=>{ if(!TR.length)return; for(let n=0;n<3;n++){ launch(TR[qi%TR.length]); qi++; } }, 300);
async function tick(){
  let d;try{d=await(await fetch("/api/data")).json()}catch(e){return}
  if(window.__v&&window.__v!==d.ver){location.reload();return}window.__v=d.ver;
  draw(d);
  const h=document.getElementById("health");
  const n=d.recent15||0;  // == animated train count (all age-gated ≤15m)
  if(n>0){h.className="hp ok";h.textContent="● LIVE · "+n+" real trains (≤15m)"}
  else{h.className="hp dead";h.textContent="○ IDLE — no live signal"}
  document.getElementById("movetxt").textContent=n+" real trains moving · Bill→GenePool: "+d.bill_gp;
  // ── REAL-TELEMETRY STRIP (item 2): the 8 counters, all from real data ──
  const tm=d.telemetry||{};
  const isoTel=(tm.isolated_list||[]).join(", ")||"none";
  const fail=(tm.failed_list||[]).map(f=>f.id+" ("+f.reason+")").join("; ")||"none";
  const tw=(tm.twoway_list||[]).join(", ")||"none";
  const cards=[
    ["total_stations","Total Stations","",""],
    ["active_stations","Active Stations","real train endpoint ≥1","good"],
    ["total_tracks","Total Tracks","drawn mesh",""],
    ["tracks_proven","Tracks Proven","carried a real train (15m)","good"],
    ["total_real_trains","Real Trains","age-gated ≤15m == animated","good"],
    ["isolated_stations","Isolated (valid)","valid, 0 trains: "+isoTel,(tm.isolated_stations>0?"warn":"")],
    ["failed_routes","Failed Routes","blocked/decommissioned: "+fail,(tm.failed_routes>0?"bad":"")],
    ["twoway_routes","Two-way Routes","both directions ran: "+tw,"good"],
  ];
  document.getElementById("telem").innerHTML=cards.map(c=>{
    const v=(tm[c[0]]!=null?tm[c[0]]:"—");
    return `<div class="tc ${c[3]||''}" title="${(c[2]||'').replace(/"/g,'&quot;')}"><div class=v>${v}</div><div class=l>${c[1]}</div></div>`;
  }).join("");
  // STRUCTURAL: the drawn lattice (true of the drawing, not a talk-claim)
  const pf=d.proof||{};
  document.getElementById("proof").textContent =
     pf.stations+" stations · "+pf.edges+" tracks drawn · graph diameter ≤"+pf.diameter+" hops (all paths transit the Gene Pool hub)";
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
}
tick();setInterval(tick,3000);  // Ross: 3-second refresh so trains stay current
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
