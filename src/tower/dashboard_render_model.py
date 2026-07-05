#!/usr/bin/env python3
"""
QSB Tower V1.3 — Dashboard Render Model V1

Phase: QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1

Read-only inventory + render-model builder. Reads the live system
(floors.json, lifts.json, every floor_manifest.json that exists, the
trading-floor + AirLLM + cross-market registries) and produces:

  data/registries/qsb_full_system_inventory.json   — full software recap
  data/registries/qsb_floor_name_map.json          — 53-floor canonical
                                                     {number: real_name}
  data/registries/qsb_dashboard_render_model.json  — render plan the
                                                     frontend consumes

Hard contract: read-only / advisory-only. No execution flag is ever
written by this module. Stamps execution_allowed=false, paper_only=true,
not_financial_advice=true on every published record.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os


ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"
LOG  = ROOT / "data/logs/qsb_full_system_inventory.jsonl"

INVENTORY_PATH = REG / "qsb_full_system_inventory.json"
NAME_MAP_PATH  = REG / "qsb_floor_name_map.json"
RENDER_PATH    = REG / "qsb_dashboard_render_model.json"


# ── Floor-number → category map (derived from each floor's role) ──────────
FLOOR_CATEGORY = {
    1:  "infrastructure",   2:  "infrastructure",   3:  "infrastructure",
    4:  "infrastructure",   5:  "worker_coordination",
    6:  "worker_coordination", 7:  "infrastructure", 8:  "infrastructure",
    9:  "infrastructure",   10: "trading_fx",       11: "monitoring",
    12: "risk",             13: "infrastructure",   14: "infrastructure",
    15: "infrastructure",   16: "infrastructure",   17: "infrastructure",
    18: "infrastructure",   19: "infrastructure",   20: "infrastructure",
    21: "infrastructure",   22: "infrastructure",
    23: "advisory_model",   24: "routing",          25: "worker_coordination",
    26: "model_lane",       27: "model_lane",       28: "infrastructure",
    29: "infrastructure",   30: "risk",             31: "audit",
    32: "audit",            33: "monitoring",       34: "monitoring",
    35: "infrastructure",   36: "infrastructure",   37: "strategy",
    38: "sandbox",          39: "sandbox",          40: "sandbox",
    41: "trading_fx",       42: "trading_crypto",   43: "trading_equities",
    44: "vacant",           45: "vacant",
    46: "command",          47: "command",          48: "command",
    49: "command",          50: "command",          51: "command",
    52: "command",          53: "command",
}

# Category palette
CATEGORY_COLOR = {
    "kernel":            {"color": "#ffd24c", "glow": 1.20, "label_color": "#ffe080"},
    "command":           {"color": "#6ab8ff", "glow": 1.10, "label_color": "#a8d0ff"},
    "trading_fx":        {"color": "#5ce0ff", "glow": 1.05, "label_color": "#bde6ff"},
    "trading_crypto":    {"color": "#ffb86c", "glow": 1.05, "label_color": "#ffd39a"},
    "trading_equities":  {"color": "#eaf2ff", "glow": 1.10, "label_color": "#f2f6ff"},
    "model_lane":        {"color": "#5ce0ff", "glow": 0.90, "label_color": "#bbe7ff"},
    "advisory_model":    {"color": "#7fc8ff", "glow": 1.05, "label_color": "#bfe0ff"},
    "routing":           {"color": "#8aa8ff", "glow": 0.85, "label_color": "#bcd0ff"},
    "worker_coordination": {"color": "#4dffb0", "glow": 0.85, "label_color": "#a8ffd0"},
    "risk":              {"color": "#b08aff", "glow": 1.00, "label_color": "#d6c0ff"},
    "audit":             {"color": "#ffc940", "glow": 1.00, "label_color": "#ffe080"},
    "strategy":          {"color": "#5ce0ff", "glow": 0.95, "label_color": "#bde6ff"},
    "sandbox":            {"color": "#4dffb0", "glow": 0.90, "label_color": "#a8ffd0"},
    "monitoring":        {"color": "#88a3c2", "glow": 0.55, "label_color": "#b6c8e0"},
    "infrastructure":    {"color": "#5b78a4", "glow": 0.45, "label_color": "#9ab0c8"},
    "vacant":            {"color": "#3a5070", "glow": 0.20, "label_color": "#7a8da8"},
    "locked_external":   {"color": "#b08aff", "glow": 0.45, "label_color": "#d6c0ff"},
}


def _load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ── Inventory builders ────────────────────────────────────────────────────
def build_inventory():
    floors_reg = _load_json(REG / "floors.json", [])
    lifts_reg  = _load_json(REG / "lifts.json", [])

    # Floor manifests on disk
    manifests = []
    floors_dir = ROOT / "floors"
    if floors_dir.is_dir():
        for d in sorted(floors_dir.iterdir()):
            mf = d / "floor_manifest.json"
            if mf.is_file():
                manifests.append({
                    "manifest_path": str(mf),
                    "directory": d.name,
                    "manifest": _load_json(mf, {}),
                })

    # Tower modules
    tower_modules = []
    tower_dir = ROOT / "src/tower"
    if tower_dir.is_dir():
        for p in sorted(tower_dir.iterdir()):
            if p.suffix == ".py" and not p.name.startswith("__"):
                tower_modules.append(p.name)

    # Scripts (skip per-floor activate_*)
    scripts = []
    scripts_dir = ROOT / "scripts"
    if scripts_dir.is_dir():
        for p in sorted(scripts_dir.iterdir()):
            if p.suffix == ".sh" and not p.name.startswith("activate_floor_"):
                scripts.append(p.name)

    # Registries (top-level *.json under data/registries)
    registries = []
    if REG.is_dir():
        for p in sorted(REG.iterdir()):
            if p.suffix == ".json" and not p.name.startswith("."):
                registries.append(p.name)

    # AirLLM chamber
    air_chamber = _load_json(REG / "airllm_big_model_chamber.json", {})
    air_status_md_path = Path("/vaults/ai/airllm_lab/AIRLLM_CHAMBER_STATUS.md")
    air_env_sh_path    = Path("/vaults/ai/airllm_env.sh")
    air_venv_path      = Path("/vaults/ai/airllm_lab/.venv")
    air_lock_path      = Path("/vaults/ai/airllm_lab/requirements_airllm_locked.txt")

    airllm_chamber = {
        "registered": bool(air_chamber),
        "status": air_chamber.get("status") or "unknown",
        "chamber_name": air_chamber.get("chamber_name") or "AirLLM Big Model Chamber",
        "home_floor": "floor_23",
        "advisory_only": True,
        "execution_allowed": False,
        "trading_allowed": False,
        "autoloop_allowed": False,
        "openclaw_execution_allowed": False,
        "provider_execution_allowed": False,
        "direct_provider_access": False,
        "path": str(air_chamber.get("path") or "/vaults/ai/airllm_lab"),
        "venv_path": str(air_chamber.get("venv_path") or air_venv_path),
        "env_file": str(air_chamber.get("env_file") or air_env_sh_path),
        "status_doc_exists": air_status_md_path.is_file(),
        "lockfile_exists": air_lock_path.is_file(),
        "venv_exists": air_venv_path.is_dir(),
        "separate_from_qsb_venv": True,
    }

    # Trading floors
    oanda_status   = _load_json(REG / "oanda_trading_floor_status.json", {})
    binance_status = _load_json(REG / "binance_floor_status.json", {})
    stock_status   = _load_json(REG / "stock_floor_status.json", {})
    cross_bus      = _load_json(REG / "cross_market_bus_latest.json", {})

    market_floors = {
        "oanda_floor_41": {
            "installed": True,
            "department": "OANDA Trading Floor",
            "phase": oanda_status.get("phase") or "OANDA_FLOOR_41_PRACTICE_V1",
            "environment": oanda_status.get("environment") or "practice",
            "paper_only": True, "execution_allowed": False, "not_financial_advice": True,
        },
        "binance_floor_42": {
            "installed": True,
            "department": "Binance Trading Floor",
            "phase": binance_status.get("phase") or "BINANCE_FLOOR_42_TRADING_FLOOR_V1",
            "environment": binance_status.get("environment") or "testnet",
            "public_market_data_ready": bool(binance_status.get("public_market_data_ready")),
            "paper_only": True, "execution_allowed": False, "not_financial_advice": True,
        },
        "stock_floor_43": {
            "installed": bool(stock_status),
            "department": "Stock Exchange Trading Floor",
            "phase": stock_status.get("phase") or "FLOOR_43_CONNECTED_STOCK_EXCHANGE_FLOOR_V1",
            "provider": stock_status.get("provider") or "alpaca",
            "environment": stock_status.get("environment") or "paper",
            "public_market_data_ready": bool(stock_status.get("public_market_data_ready")),
            "paper_only": True, "execution_allowed": False, "not_financial_advice": True,
        },
    }
    cross_market_bus = {
        "installed": bool(cross_bus),
        "bus": cross_bus.get("bus") or "QSB Cross-Market Bus V1",
        "advisory_only": True,
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
    }

    # Workers from the sandbox registry
    workers_reg = _load_json(REG / "worker_sandbox_registry.json", {})
    worker_summary = [{
        "id": w.get("id"),
        "name": w.get("name"),
        "role": w.get("role"),
        "home_floor": w.get("home_floor"),
        "sandbox_only": True,
        "execution_enabled": False,
    } for w in (workers_reg.get("workers") or []) if isinstance(w, dict)]

    # Sidecars (tower module files that end with _sidecar.py)
    sidecars = [m for m in tower_modules if m.endswith("_sidecar.py")]

    inventory = {
        "ts": _now(),
        "phase": "QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1",
        "qsb_root": str(ROOT),
        "kernel_active_local_only_required": True,
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
        "counts": {
            "floors_in_registry": len(floors_reg),
            "floor_manifests_on_disk": len(manifests),
            "lifts_in_registry": len(lifts_reg),
            "tower_modules": len(tower_modules),
            "tower_sidecars": len(sidecars),
            "scripts": len(scripts),
            "registries": len(registries),
            "workers": len(worker_summary),
        },
        "floors_registry": [
            {
                "number": f.get("number"),
                "id": f.get("id"),
                "department": f.get("department"),
                "zone": f.get("zone"),
                "vacant": bool(f.get("vacant")),
                "highlight": bool(f.get("highlight")),
                "highlight_label": f.get("highlight_label") or "",
                "lift_access": bool(f.get("lift_access")),
                "workers": f.get("workers") or [],
                "has_manifest": any(m["directory"].startswith(f.get("id") or "_") for m in manifests),
            }
            for f in floors_reg
        ],
        "lifts_registry": lifts_reg,
        "floor_manifest_index": [
            {
                "directory": m["directory"],
                "floor_id": (m.get("manifest") or {}).get("floor_id"),
                "number": (m.get("manifest") or {}).get("number"),
                "department": (m.get("manifest") or {}).get("department"),
                "phase": (m.get("manifest") or {}).get("phase"),
                "status": (m.get("manifest") or {}).get("status"),
            }
            for m in manifests
        ],
        "tower_modules": tower_modules,
        "tower_sidecars": sidecars,
        "scripts_top_level": scripts,
        "registry_files": registries,
        "airllm_chamber": airllm_chamber,
        "market_floors": market_floors,
        "cross_market_bus": cross_market_bus,
        "workers_sandbox_registry_summary": worker_summary,
        "locks_must_remain_false": [
            "live_trading_enabled", "order_execution_enabled",
            "practice_order_execution_enabled",
            "binance_order_execution_enabled", "binance_live_trading_enabled",
            "stock_order_execution_enabled", "stock_live_trading_enabled",
            "stock_paper_order_execution_enabled",
            "cross_market_execution_enabled",
            "worker_execution_enabled", "provider_execution_enabled",
            "external_provider_execution_enabled",
            "openclaw_execution_enabled", "openclaw_real_tool_execution_enabled",
            "autonomous_dispatch_enabled", "live_dispatch_enabled",
            "direct_provider_access",
        ],
    }

    _write_json(INVENTORY_PATH, inventory)
    _append_log({
        "ts": inventory["ts"],
        "phase": inventory["phase"],
        "counts": inventory["counts"],
        "execution_allowed": False,
        "paper_only": True,
    })
    return inventory


def build_floor_name_map(inventory):
    name_map = {}
    for f in inventory.get("floors_registry") or []:
        n = f.get("number")
        if isinstance(n, int) and 1 <= n <= 53:
            name_map[str(n)] = f.get("department") or ("Floor " + str(n))
    name_map["0"]  = "Ground / Reception Lobby"
    name_map["54"] = "Roof — External Providers (LOCKED)"
    name_map["55"] = "Penthouse — QSB Kernel"   # alias if any consumer uses 55 to mean penthouse-on-top
    out = {
        "ts": _now(),
        "phase": "QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1",
        "name_map": name_map,
        "source": "data/registries/floors.json (department field) + canonical penthouse/roof/ground",
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
    }
    _write_json(NAME_MAP_PATH, out)
    return out


def build_render_model(inventory, name_map):
    floors_reg = {f.get("number"): f for f in inventory.get("floors_registry") or []}

    floors_out = []
    for n in range(1, 54):
        info = floors_reg.get(n) or {}
        cat = FLOOR_CATEGORY.get(n, "infrastructure")
        if n == 53:
            cat = "command"
        if info.get("vacant"):
            cat = "vacant"
        palette = CATEGORY_COLOR.get(cat, CATEGORY_COLOR["infrastructure"])
        name = info.get("department") or name_map["name_map"].get(str(n)) or ("Floor " + str(n))
        floors_out.append({
            "number": n,
            "id": "floor_{:02d}".format(n),
            "name": name,
            "zone": info.get("zone") or "—",
            "category": cat,
            "status": "vacant" if info.get("vacant") else "active",
            "highlight": bool(info.get("highlight")),
            "color": palette["color"],
            "label_color": palette["label_color"],
            "glow": palette["glow"],
            "visible_label": name,
            "short_label": _abbrev(name),
            "workers": info.get("workers") or [],
        })

    # roof + penthouse + ground
    extra = [
        {
            "number": 54, "id": "roof_lock", "name": "Roof — External Providers (LOCKED)",
            "zone": "ROOF", "category": "locked_external", "status": "locked",
            "highlight": True, "color": "#b08aff", "label_color": "#d6c0ff", "glow": 0.45,
            "visible_label": "Roof — External Providers (LOCKED)", "short_label": "ROOF", "workers": [],
        },
        {
            "number": 0, "id": "ground", "name": "Ground / Reception Lobby",
            "zone": "GROUND", "category": "infrastructure", "status": "active",
            "highlight": False, "color": "#6ab8ff", "label_color": "#bde6ff", "glow": 0.55,
            "visible_label": "Ground / Reception Lobby", "short_label": "GND", "workers": [],
        },
    ]

    # Highlighted floor numbers (always include known QSB key floors plus anything marked highlight in registry)
    canonical_highlight = {23, 24, 25, 30, 31, 37, 38, 41, 42, 43, 53}
    extra_highlight = {f["number"] for f in floors_out if f["highlight"]}
    highlight_set = sorted(canonical_highlight | extra_highlight)

    # Lift shafts (9 lanes) - synthesized from real lifts.json categories
    lifts_reg = inventory.get("lifts_registry") or []
    shafts = []
    for i in range(9):
        ref = lifts_reg[i] if i < len(lifts_reg) else {}
        shafts.append({
            "shaft_index": i,
            "lift_id": ref.get("id") or "shaft_{}".format(i),
            "name":    ref.get("name") or "Lift {}".format(i + 1),
            "type":    ref.get("type") or "main",
            "status":  ref.get("status") or "online",
            "serves":  ref.get("serves") or [],
        })

    # Routes (paper-only / advisory visualization only)
    market = inventory.get("market_floors") or {}
    stock_installed = bool(market.get("stock_floor_43", {}).get("installed"))

    def route(src, dst, kind, color, advisory=False):
        return {
            "source_floor": src,
            "target_floor": dst,
            "route_type": kind,
            "color": color,
            "advisory_only": advisory,
            "paper_only": True,
            "execution_allowed": False,
        }

    routes = [
        route("floor_41", "floor_37", "strategy",  "cyan"),
        route("floor_42", "floor_37", "strategy",  "orange"),
    ]
    if stock_installed:
        routes.append(route("floor_43", "floor_37", "strategy", "white"))
    routes += [
        route("floor_37", "floor_38", "worker",    "green"),
        route("floor_38", "floor_30", "openclaw",  "purple"),
        route("floor_30", "floor_31", "ledger",    "gold"),
        route("floor_31", "floor_53", "ledger",    "gold"),
        route("floor_53", "penthouse","kernel",    "blue"),
        # AirLLM advisory lane
        route("floor_23", "penthouse","airllm",    "cyan", advisory=True),
        route("floor_24", "floor_23", "routing",   "blue"),
        # OpenClaw sandbox cross-routes
        route("floor_38", "floor_31", "openclaw",  "purple"),
        route("floor_38", "floor_53", "openclaw",  "purple"),
        route("floor_30", "floor_53", "ledger",    "gold"),
        # market-to-audit logging
        route("floor_41", "floor_31", "ledger",    "gold"),
        route("floor_42", "floor_31", "ledger",    "gold"),
    ]
    if stock_installed:
        routes.append(route("floor_43", "floor_31", "ledger", "gold"))

    # Worker summary (from sandbox registry, plus canonical workers we expect)
    workers_summary = inventory.get("workers_sandbox_registry_summary") or []

    panels = [
        {"id": "kernel",     "title": "Kernel",                    "always_on": True},
        {"id": "locks",      "title": "Execution Lock Matrix",     "always_on": True},
        {"id": "counts",     "title": "Workers & Packets",         "always_on": True},
        {"id": "services",   "title": "Services",                  "always_on": True},
        {"id": "strategy",   "title": "Strategy / Trading",        "always_on": True},
        {"id": "oanda",      "title": "OANDA Floor 41",            "always_on": True},
        {"id": "binance",    "title": "Binance Floor 42",          "always_on": True},
        {"id": "stocks",     "title": "Stock Exchange Floor 43",   "always_on": stock_installed},
        {"id": "cross",      "title": "Cross-Market Bus",          "always_on": True},
        {"id": "airllm",     "title": "AirLLM Chamber (advisory)", "always_on": True},
        {"id": "openclaw",   "title": "OpenClaw Sandbox",          "always_on": True},
        {"id": "workers",    "title": "Workers",                   "always_on": True},
        {"id": "ledger",     "title": "Event Ticker / Ledger",     "always_on": True},
    ]

    render = {
        "ts": _now(),
        "phase": "QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1",
        "render_hints": {
            "primary_renderer": "svg_2d_pseudo_3d",
            "enhancement_renderer": "webgl_3d_optional",
            "rotation_default_on": True,
            "rotation_period_sec": 24,
            "highlighted_floor_glow_loop_sec": 3.0,
            "background": "deep_space",
            "show_all_floor_names": False,
            "search_directory_default_open": False,
        },
        "floors": extra + floors_out,
        "highlighted_floors": ["floor_{:02d}".format(n) for n in highlight_set],
        "lift_shafts": shafts,
        "routes": routes,
        "workers": workers_summary,
        "panels": panels,
        "locks_summary": {
            "lock_keys": inventory.get("locks_must_remain_false") or [],
            "expected_lock_count_true": 0,
        },
        "market_floors": inventory.get("market_floors") or {},
        "model_lanes": {
            "local_ollama": "active_local_only_expected",
            "airllm_big_model_chamber": "installed_advisory_only",
            "external_providers": "locked",
            "direct_provider_access": "off",
        },
        "airllm_chamber": inventory.get("airllm_chamber") or {},
        "cross_market_bus_installed": bool((inventory.get("cross_market_bus") or {}).get("installed")),
        "warnings": [],
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
        "advisory_only": True,
    }
    _write_json(RENDER_PATH, render)
    return render


def _abbrev(name):
    if not name:
        return ""
    parts = [p for p in name.replace("/", " ").split() if p]
    if len(parts) == 1:
        return parts[0][:10]
    return "".join(p[0] for p in parts)[:6].upper()


def build():
    inv = build_inventory()
    name_map = build_floor_name_map(inv)
    render = build_render_model(inv, name_map)
    return {"inventory": inv, "name_map": name_map, "render_model": render}


def dashboard():
    return {
        "inventory_path": str(INVENTORY_PATH),
        "name_map_path":  str(NAME_MAP_PATH),
        "render_model_path": str(RENDER_PATH),
        "floor_name_map_count": len(_load_json(NAME_MAP_PATH, {}).get("name_map") or {}),
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
    }


if __name__ == "__main__":
    out = build()
    print(json.dumps({
        "phase": "QSB_TOWER_FULL_RECAP_AND_3D_DASHBOARD_REBUILD_V1",
        "counts": out["inventory"]["counts"],
        "floor_name_map_count": len(out["name_map"]["name_map"]),
        "render_model_floors": len(out["render_model"]["floors"]),
        "render_model_routes": len(out["render_model"]["routes"]),
        "highlighted_floors": out["render_model"]["highlighted_floors"],
        "execution_allowed": False,
        "paper_only": True,
        "not_financial_advice": True,
    }, indent=2))
