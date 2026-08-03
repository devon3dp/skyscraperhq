"""situational_awareness_brief — one fused key-player briefing for Wren.

Composes the four sibling read-only skills into a single grounded picture and
a one-paragraph human brief. Every field traces to a real registry (R01).
"""
import importlib.util
import json
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent  # skills/wren/


def _load(name):
    p = SKILLS / name / "skill.py"
    spec = importlib.util.spec_from_file_location(f"wren_sib_{name}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(needs_n: int = 5, council_n: int = 5):
    parts = {}
    for key, name, kwargs in [
        ("tower", "live_tower_status", {}),
        ("worker_needs", "worker_needs_digest", {"n": needs_n}),
        ("trading", "trading_desk_briefing", {}),
        ("council", "council_board_digest", {"n": council_n}),
    ]:
        try:
            parts[key] = _load(name).run(**kwargs)
        except Exception as e:
            parts[key] = {"ok": False, "error": str(e)}

    t = parts["tower"]
    tr = parts["trading"]
    wn = parts["worker_needs"]
    co = parts["council"]

    top_need = None
    if wn.get("ok") and wn.get("top_needs"):
        tn = wn["top_needs"][0]
        top_need = f"F{tn.get('floor')}: {tn.get('need')} (x{tn.get('reported_by_count')})"

    brief = (
        f"TOWER: {t.get('services_up')}/{t.get('services_total')} services up, "
        f"{t.get('traders_alive')} traders alive, disk {t.get('root_disk_pct')}, load {t.get('load_1m')}. "
        f"PNL: £{tr.get('realized_pnl_gbp_all_venues')} realized (advisory, no real money); "
        f"fleet exposure £{tr.get('belief_fleet_open_exposure_gbp')}. "
        f"COUNCIL: {co.get('totals',{}).get('open')} open / "
        f"{co.get('totals',{}).get('in_progress')} in-progress. "
        f"WORKERS: {wn.get('distinct_needs_total')} distinct needs; loudest -> {top_need}."
    )

    return {
        "ok": all(p.get("ok") for p in parts.values()),
        "brief": brief,
        "tower": t,
        "trading": tr,
        "worker_needs": wn,
        "council": co,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
