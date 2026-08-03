#!/usr/bin/env python3
"""
qsb_dispatcher.py — routes a work unit to the best available compute resource.

This is the building block the grinder / council can call to MOVE WORK to the
right box: given a work unit + its type, pick the best available resource using
  (1) the live resource map  (data/registries/qsb_resource_map.json)
  (2) the reputation data    (data/registries/qsb_worker_reputation.json)
  (3) current load           (busy/free from the resource map + council board)

HONESTY (R01): the routing decision is fully explained. Every factor in the
score is a real number from a real registry. If the chosen box is unreachable,
we say so and fall back. We prefer to OFFLOAD the main box (it is pinned 1-slot),
so worker boxes are strongly preferred for dispatchable work.

Work types & skill fit (from real reputation signals):
  - code / build      -> speed matters most     -> tp_pip (fast) favoured
  - verify / signoff  -> on-topic accuracy       -> acer_cass (on-topic strong)
  - research / note   -> on-topic + reaffirm      -> acer_cass favoured
  - default           -> balanced (rep * availability)

Usage:
  # route a real unit and print the decision (does NOT place work by itself):
  python3 tools/qsb_dispatcher.py route --type code   --unit "fix cockpit JS bug"
  python3 tools/qsb_dispatcher.py route --type verify --unit "verify F44 PnL snapshot"

  # importable:
  from tools.qsb_dispatcher import dispatch
  decision = dispatch("code", "fix cockpit JS bug")
"""
from __future__ import annotations
import argparse, datetime, json, subprocess, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
SNAP = REG / "qsb_resource_map.json"
REP = REG / "qsb_worker_reputation.json"
DISPATCH_LOG = REG / "qsb_dispatch_decisions.jsonl"

# real reputation signal weights per work type -> which signal dominates.
# code favours SPEED (tp_pip fast); verify/research favour ON-TOPIC (acer_cass).
# weights over four REAL reputation signals:
#   speed    (speed_class -> SPEED_SCORE)      : tp_pip's real edge (fast box)
#   on_topic (on_topic_rate)                   : acer_cass's real edge (0.975)
#   outcome  (outcome_rate)                    : both 1.0 today
#   reaffirm (reaffirm_score)                  : acer_cass's real edge (0.65 vs 0.36)
# verify/research lean on on_topic+reaffirm, which are acer_cass's real strengths;
# code/build lean on speed, which is tp_pip's real strength.
TYPE_PROFILE = {
    "code":     {"speed": 0.60, "on_topic": 0.15, "outcome": 0.15, "reaffirm": 0.10},
    "build":    {"speed": 0.60, "on_topic": 0.15, "outcome": 0.15, "reaffirm": 0.10},
    "verify":   {"speed": 0.05, "on_topic": 0.45, "outcome": 0.20, "reaffirm": 0.30},
    "signoff":  {"speed": 0.05, "on_topic": 0.45, "outcome": 0.20, "reaffirm": 0.30},
    "research": {"speed": 0.10, "on_topic": 0.40, "outcome": 0.20, "reaffirm": 0.30},
    "note":     {"speed": 0.10, "on_topic": 0.40, "outcome": 0.20, "reaffirm": 0.30},
    "default":  {"speed": 0.30, "on_topic": 0.30, "outcome": 0.20, "reaffirm": 0.20},
}

# real speed-class -> normalized speed score (main box pinned => penalised for
# dispatch so we OFFLOAD it, not load it).
SPEED_SCORE = {"fast": 1.0, "steady": 0.6, "network": 0.4,
               "high_but_pinned": 0.2}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _ensure_fresh_map(max_age_s=90) -> dict:
    """Load the resource map; refresh it if stale/missing so we route on live
    data. Refresh is a real subprocess call to qsb_resource_map.py."""
    snap = _load_json(SNAP)
    stale = True
    if snap and snap.get("ts"):
        try:
            t = datetime.datetime.fromisoformat(snap["ts"].replace("Z", "+00:00"))
            age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
            stale = age > max_age_s
        except Exception:
            stale = True
    if stale:
        try:
            subprocess.run([sys.executable, str(ROOT / "tools/qsb_resource_map.py")],
                           cwd=str(ROOT), timeout=40,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            snap = _load_json(SNAP)
        except Exception:
            pass
    return snap or {"resources": {}}


def _rep_signals():
    """Return {worker_id: {'reputation','on_topic','outcome'}} from real rep file."""
    rep = _load_json(REP) or {}
    out = {}
    for row in rep.get("ranked", []):
        src = row.get("source")
        sig = row.get("signals", {})
        out[src] = {
            "reputation": row.get("reputation", 0.0),
            "on_topic": sig.get("on_topic_rate", 0.0),
            "outcome": sig.get("outcome_rate", 0.0),
            "reaffirm": sig.get("reaffirm_score", 0.0),
        }
    return out


def dispatch(work_type: str, unit: str) -> dict:
    """Pick the best available resource for `unit` of `work_type`. Returns a
    fully-explained decision dict. Does NOT itself place the work — it is the
    routing building block the grinder/council calls."""
    work_type = (work_type or "default").lower()
    profile = TYPE_PROFILE.get(work_type, TYPE_PROFILE["default"])
    snap = _ensure_fresh_map()
    reps = _rep_signals()

    candidates = []
    considered = []
    for name, r in snap.get("resources", {}).items():
        if r.get("role") != "worker_box":
            continue  # dispatch targets = worker boxes (offload the main box)
        wid = r.get("worker_id")
        rep = reps.get(wid, {"reputation": 0.5, "on_topic": 0.5,
                             "outcome": 0.5, "reaffirm": 0.5})
        speed = SPEED_SCORE.get(r.get("speed_class"), 0.5)
        reachable = bool(r.get("reachable"))
        busy = bool(r.get("busy"))
        # load factor: free=1.0, busy=0.5 (still eligible but penalised)
        load = 1.0 if not busy else 0.5
        # skill score = weighted real reputation signals per work-type profile
        skill = (profile["speed"] * speed
                 + profile["on_topic"] * rep["on_topic"]
                 + profile["outcome"] * rep["outcome"]
                 + profile.get("reaffirm", 0.0) * rep["reaffirm"])
        score = skill * load if reachable else 0.0
        row = {
            "resource": name, "worker_id": wid,
            "speed_class": r.get("speed_class"),
            "reachable": reachable, "busy": busy,
            "availability": r.get("availability"),
            "rep": round(rep["reputation"], 4),
            "on_topic": round(rep["on_topic"], 4),
            "outcome": round(rep["outcome"], 4),
            "reaffirm": round(rep["reaffirm"], 4),
            "speed_score": speed, "load_factor": load,
            "skill_score": round(skill, 4), "score": round(score, 4),
        }
        considered.append(row)
        if reachable:
            candidates.append(row)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    chosen = candidates[0] if candidates else None

    if chosen:
        reason = (
            f"type={work_type}: weighted real reputation signals "
            f"(speed×{profile['speed']}, on_topic×{profile['on_topic']}, "
            f"outcome×{profile['outcome']}). "
            f"{chosen['worker_id']} wins score={chosen['score']} "
            f"(rep={chosen['rep']}, on_topic={chosen['on_topic']}, "
            f"speed={chosen['speed_class']}, "
            f"{'FREE' if not chosen['busy'] else 'busy(-50% load)'}). "
            f"main_box excluded from dispatch (pinned — we offload it)."
        )
    else:
        reason = "no reachable worker box — cannot dispatch; boxes down."

    decision = {
        "ts": _now(), "schema": "qsb.dispatch.decision/1",
        "work_type": work_type, "unit": unit[:200],
        "profile": profile,
        "chosen": chosen,
        "chosen_box": (chosen or {}).get("resource"),
        "chosen_worker": (chosen or {}).get("worker_id"),
        "reason": reason,
        "considered": considered,
        "map_ts": snap.get("ts"),
    }
    return decision


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("route")
    p.add_argument("--type", required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--log", action="store_true", help="append decision to dispatch log")
    a = ap.parse_args()
    if a.cmd == "route":
        d = dispatch(a.type, a.unit)
        if a.log:
            with open(DISPATCH_LOG, "a") as f:
                f.write(json.dumps(d) + "\n")
        print(json.dumps(d, indent=2))


if __name__ == "__main__":
    main()
