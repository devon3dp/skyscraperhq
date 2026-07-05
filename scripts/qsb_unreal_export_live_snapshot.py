#!/usr/bin/env python3
"""QSB to Unreal Engine live data bridge. Schema v2.

Per Ross spec QSB_UNREAL_PROFESSIONAL_SKYSCRAPER_HUD_DASHBOARD_DIRECTION_V2 Stage 9.
DeepSeek-authored, Claude-integrated 2026-06-25.
Output: /vaults/nvme0/qsb_unreal_skyscraper/Saved/QSB/qsb_live_snapshot.json
"""
import json, time, urllib.request, urllib.error
from pathlib import Path

BASE = Path("/vaults/nvme0/qsb_tower_v1")
REGISTRIES = BASE / "data" / "registries"
OUT = Path("/vaults/nvme0/qsb_unreal_skyscraper/Saved/QSB") / "qsb_live_snapshot.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def load_json(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default if default is not None else {}


def load_tower():
    audit = load_json(REGISTRIES / "qsb_canonical_tower_structure_audit.json")
    floor_count = audit.get("canonical_floor_count", 169)
    floors = []
    for d in sorted(BASE.glob("floors/floor_*")):
        card = load_json(d / "floor_card.json")
        if not card:
            continue
        try:
            n = int(d.name.split("_")[1])
        except (ValueError, IndexError):
            continue
        floors.append({
            "n": n,
            "name": card.get("name", ""),
            "archetype": card.get("archetype", "auto"),
            "manager": card.get("manager", ""),
            "roster_size": card.get("roster_size", 0),
            "dir": d.name,
        })
    return floor_count, floors


def load_trading():
    empty = {
        "convergence_fire_count": 0, "convergence_total": 0,
        "tick_rates": {"oanda": 0.0, "binance": 0.0, "alpaca": 0.0},
        "open_positions_count": 0, "today_pnl": 0.0,
        "fleet": [], "performance_buckets": {"5m": 0, "30m": 0, "1h": 0, "today": 0},
    }
    try:
        req = urllib.request.Request("http://127.0.0.1:8847/api/traders_live",
                                       headers={"User-Agent": "QSB-Bridge/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception:
        return empty
    conv = data.get("convergence", []) or []
    tr = data.get("tick_rates", {}) or {}
    buckets = (data.get("performance_lens", {}) or {}).get("buckets", {}) or {}
    fleet = (data.get("health", {}) or {}).get("fleet", []) or []
    blp = data.get("broker_live_positions", {}) or {}
    open_n = 0
    for venue in ("oanda", "alpaca", "binance"):
        v = blp.get(venue)
        if isinstance(v, list):
            open_n += len(v)
        elif isinstance(v, dict):
            open_n += int(v.get("count", 0) or len(v))
    today_pnl = buckets.get("today")
    today_pnl = float(today_pnl) if isinstance(today_pnl, (int, float)) else 0.0
    return {
        "convergence_fire_count": sum(1 for w in conv if w.get("ok")),
        "convergence_total": len(conv),
        "tick_rates": {
            "oanda":   (tr.get("oanda")   or {}).get("rate_per_s", 0.0),
            "binance": (tr.get("binance") or {}).get("rate_per_s", 0.0),
            "alpaca":  (tr.get("alpaca")  or {}).get("rate_per_s", 0.0),
        },
        "open_positions_count": open_n,
        "today_pnl": today_pnl,
        "fleet": [{"name": f.get("name", "?"), "n_procs": f.get("n_procs", 0)} for f in fleet],
        "performance_buckets": {k: (buckets.get(k) if isinstance(buckets.get(k), (int, float)) else 0)
                                  for k in ("5m", "30m", "1h", "today")},
    }


def load_workers():
    census = load_json(REGISTRIES / "qsb_tower_census_latest.json")
    ts = census.get("tower_size", {}) or {}
    return {
        "total_unique": ts.get("total_unique_workers", 0),
        "active": ts.get("employed_active", 0),
        "per_floor_count": ts.get("floors_with_workers", 0),
    }


def load_smoke_tests():
    total = passed = failed = 0
    for f in REGISTRIES.glob("qsb_*_smoke_test_latest.json"):
        d = load_json(f)
        p = int(d.get("pass", 0) or 0)
        fl = int(d.get("fail", 0) or 0)
        passed += p; failed += fl; total += p + fl
    return {"total": total, "passed": passed, "failed": failed}


def load_events(limit=20):
    path = REGISTRIES / "qsb_bus_journal.jsonl"
    if not path.exists():
        return []
    try:
        lines = open(path).read().splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-limit*5:]:
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out[-limit:]


def main():
    floor_count, floors = load_tower()
    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schema_version": 2,
        "tower": {"canonical_floor_count": floor_count, "floors": floors},
        "trading": load_trading(),
        "workers": load_workers(),
        "ledgers": [],
        "smoke_tests": load_smoke_tests(),
        "voice_state": {"enabled": False, "wake_word": "Skyscraper",
                         "engine": "AlsaIO+whisper.cpp+piper"},
        "models": [
            {"name": "claude", "floor_hint": "TBD"},
            {"name": "gpt", "floor_hint": "TBD"},
            {"name": "deepseek", "floor_hint": "TBD"},
        ],
        "events": load_events(),
    }
    with open(OUT, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"OK snapshot written {OUT} ({OUT.stat().st_size} bytes, "
          f"{len(floors)} floors, {snapshot['trading']['convergence_fire_count']} "
          f"convergences firing)")


if __name__ == "__main__":
    main()
