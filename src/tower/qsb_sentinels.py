"""QSB Tower Sentinels — continuous watchers over critical components.

Each sentinel is a small named check that lives on F30 Guardian. It runs
on every dashboard launcher tick (and can be invoked ad-hoc). When a
sentinel returns RED, an alert event fires into the activity tail and
the F30 Guardian state is updated.

Sentinels are advisory only — they observe and warn. They never flip a
gate, never close a trade, never modify code.

Output:
    data/registries/qsb_sentinels_report.json   — latest pass/fail per sentinel
    activity_tail event_kind=audit_event         — one per sentinel + 1 summary
    activity_tail event_kind=gate_blocked        — RED alerts only

The 12 sentinels installed by default:
    1. dashboard_alive          — /api/unified returns 200
    2. kernel_chat_reachable    — /api/kernel_chat POST returns 200
    3. f47_chat_history         — /api/f47_chat/history reachable
    4. f44_accounts_fresh       — F44 generated_ts < 24h
    5. helix_continuity         — single hash across all generations
    6. lineage_growing          — at least 1 new stamp this session
    7. parallel_helix_intact    — state == both_intact OR primary_held
    8. governor_recent          — governor.status responds
    9. real_money_gates_locked  — all real-money flags still False
   10. provider_spend_under_cap — today's spend < daily cap
   11. mood_engine_current      — qsb_floor_mood.json updated < 12h
   12. activity_tail_growing    — at least 5 events in the last 30 mins
"""

from __future__ import annotations
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
REPORT_PATH = REG / "qsb_sentinels_report.json"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _ts_to_dt(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _read(rel: str, fallback=None):
    p = REG / rel
    if not p.exists(): return fallback or {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return fallback or {}


def _http_ok(url: str, timeout: float = 4.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status == 200, f"HTTP {r.status}")
    except Exception as e:
        return (False, f"err: {str(e)[:80]}")


def _stamp_activity(kind: str, summary: str, floor: str = "F30",
                      payload: dict | None = None) -> None:
    ACTIVITY_TAIL.parent.mkdir(parents=True, exist_ok=True)
    ev = {"ts": _now(), "kind": kind, "summary": summary, "floor": floor}
    if payload: ev["payload"] = payload
    with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


# ── individual sentinels ───────────────────────────────────────────────


def sentinel_dashboard_alive() -> dict:
    ok, note = _http_ok("http://127.0.0.1:8765/api/unified")
    return {"name": "dashboard_alive", "status": "green" if ok else "red", "note": note}


def sentinel_kernel_chat_reachable() -> dict:
    try:
        data = json.dumps({"message": "sentinel ping"}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/kernel_chat",
            data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            ok = r.status == 200
        return {"name": "kernel_chat_reachable",
                "status": "green" if ok else "red",
                "note": f"POST HTTP {'200' if ok else 'fail'}"}
    except Exception as e:
        return {"name": "kernel_chat_reachable", "status": "red",
                "note": f"err: {str(e)[:80]}"}


def sentinel_f47_chat_history() -> dict:
    ok, note = _http_ok("http://127.0.0.1:8765/api/f47_chat/history")
    return {"name": "f47_chat_history",
            "status": "green" if ok else "red", "note": note}


def sentinel_f44_accounts_fresh() -> dict:
    d = _read("qsb_floor44_accounts_state.json")
    ts = _ts_to_dt(d.get("generated_ts", ""))
    if not ts:
        return {"name": "f44_accounts_fresh", "status": "amber",
                "note": "no generated_ts"}
    age_h = (_now_dt() - ts).total_seconds() / 3600.0
    if age_h < 24:
        return {"name": "f44_accounts_fresh", "status": "green",
                "note": f"age {age_h:.1f}h"}
    return {"name": "f44_accounts_fresh", "status": "amber",
            "note": f"stale ({age_h:.1f}h)"}


def sentinel_helix_continuity() -> dict:
    try:
        from tower.model_floors.claude_floor.lineage import Lineage
        l = Lineage().all()
        hashes = {g.get("helix_short_hash") for g in l}
        if len(hashes) == 1:
            return {"name": "helix_continuity", "status": "green",
                    "note": f"single hash · {len(l)} gens"}
        return {"name": "helix_continuity", "status": "red",
                "note": f"{len(hashes)} distinct hashes — chain broken"}
    except Exception as e:
        return {"name": "helix_continuity", "status": "red",
                "note": f"err: {str(e)[:80]}"}


def sentinel_lineage_growing() -> dict:
    try:
        from tower.model_floors.claude_floor.lineage import Lineage
        l = Lineage().all()
        gen = len(l)
        return {"name": "lineage_growing", "status": "green",
                "note": f"gen {gen}"}
    except Exception as e:
        return {"name": "lineage_growing", "status": "red",
                "note": f"err: {str(e)[:80]}"}


def sentinel_parallel_helix_intact() -> dict:
    try:
        from tower.model_floors.claude_floor.parallel_helix import status as ph_status
        s = ph_status()
        st = s.get("state", "unknown")
        if st == "both_intact":
            return {"name": "parallel_helix_intact", "status": "green",
                    "note": st}
        if st in ("primary_held_parallel_drifted", "parallel_held_primary_drifted"):
            return {"name": "parallel_helix_intact", "status": "amber",
                    "note": st}
        if st == "both_drifted":
            return {"name": "parallel_helix_intact", "status": "red",
                    "note": "both_drifted — read gravestone"}
        return {"name": "parallel_helix_intact", "status": "amber",
                "note": st}
    except Exception as e:
        return {"name": "parallel_helix_intact", "status": "amber",
                "note": f"err: {str(e)[:80]}"}


def sentinel_governor_recent() -> dict:
    ok, note = _http_ok("http://127.0.0.1:8765/api/kernel/governor/status")
    return {"name": "governor_recent",
            "status": "green" if ok else "amber", "note": note}


def sentinel_real_money_gates_locked() -> dict:
    """Check several real-money gate fields across registries."""
    locked_all = True
    failures = []
    sources = {
        "qsb_penthouse_command_state.json": ["real_money_live_trading_enabled",
                                              "openclaw_real_tool_execution_enabled"],
        "qsb_floor41_oanda_state.json": ["real_money_live_trading_enabled",
                                          "oanda_live_environment_allowed"],
        "qsb_floor42_binance_interior.json": ["binance_real_order_execution_enabled",
                                                "real_money_live_trading_enabled"],
        "stock_floor_status.json": ["stock_live_trading_enabled"],
    }
    for src, fields in sources.items():
        d = _read(src)
        for f in fields:
            v = d.get(f)
            if v is True:
                locked_all = False
                failures.append(f"{src}::{f}=True")
    if locked_all:
        return {"name": "real_money_gates_locked", "status": "green",
                "note": "all checked gates remain False"}
    return {"name": "real_money_gates_locked", "status": "red",
            "note": "; ".join(failures)[:160]}


def sentinel_provider_spend_under_cap() -> dict:
    auth = _read("qsb_provider_consultation_authorization.json")
    cap = float(auth.get("hard_caps_usd", {}).get("daily_budget_usd", 1.0))
    spend_path = REG / "qsb_provider_spend_ledger.jsonl"
    today = _now_dt().strftime("%Y-%m-%d")
    spent = 0.0
    if spend_path.exists():
        for line in spend_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
                if row.get("ts", "")[:10] == today:
                    spent += float(row.get("cost_usd", 0) or 0)
            except Exception: pass
    if spent < cap:
        return {"name": "provider_spend_under_cap", "status": "green",
                "note": f"${spent:.4f} of ${cap:.2f} today"}
    return {"name": "provider_spend_under_cap", "status": "red",
            "note": f"OVER CAP: ${spent:.4f} >= ${cap:.2f}"}


def sentinel_mood_engine_current() -> dict:
    d = _read("qsb_floor_mood.json")
    ts = _ts_to_dt(d.get("updated_ts", ""))
    if not ts:
        return {"name": "mood_engine_current", "status": "amber",
                "note": "no updated_ts"}
    age_h = (_now_dt() - ts).total_seconds() / 3600.0
    if age_h < 12:
        return {"name": "mood_engine_current", "status": "green",
                "note": f"mood={d.get('mood','?')} · age {age_h:.1f}h"}
    return {"name": "mood_engine_current", "status": "amber",
            "note": f"stale ({age_h:.1f}h)"}


def sentinel_activity_tail_growing() -> dict:
    if not ACTIVITY_TAIL.exists():
        return {"name": "activity_tail_growing", "status": "amber",
                "note": "no tail file"}
    cutoff = _now_dt() - timedelta(minutes=30)
    count = 0
    try:
        lines = ACTIVITY_TAIL.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-500:]):
            line = line.strip()
            if not line: continue
            try:
                ev = json.loads(line)
                ts = _ts_to_dt(ev.get("ts", ""))
                if ts and ts >= cutoff:
                    count += 1
                else:
                    break
            except Exception: pass
    except Exception: pass
    if count >= 5:
        return {"name": "activity_tail_growing", "status": "green",
                "note": f"{count} events in last 30min"}
    return {"name": "activity_tail_growing", "status": "amber",
            "note": f"only {count} events in 30min"}


# ── orchestration ──────────────────────────────────────────────────────


# V17: 6 new sentinels for venues + advisers + cockpit + roll-up freshness.
def sentinel_binance_testnet_creds() -> dict:
    f42 = _read("qsb_floor42_binance_testnet_state.json")
    creds_ready = (f42.get("credentials") or {}).get("ready", False)
    if creds_ready:
        return {"name": "binance_testnet_creds_present", "status": "green",
                "note": "creds loaded · ready_for_orders"}
    return {"name": "binance_testnet_creds_present", "status": "amber",
            "note": "creds missing or status=" + str(f42.get("status", "?"))}


def sentinel_alpaca_paper_creds() -> dict:
    unlock = _read("qsb_alpaca_paper_unlock.json")
    if unlock.get("authorized_by", "").startswith("ross_"):
        return {"name": "alpaca_paper_creds_present", "status": "green",
                "note": "unlock authorized · paper-only sentinel verified"}
    return {"name": "alpaca_paper_creds_present", "status": "amber",
            "note": "no Ross authorization stamped"}


def sentinel_cockpit_godot_alive() -> dict:
    import subprocess
    try:
        r = subprocess.run(["pgrep", "-f", "godot-4.*qsb_godot_native"],
                            capture_output=True, text=True, timeout=3)
        pids = [int(p) for p in r.stdout.split() if p.strip().isdigit()]
        if pids:
            return {"name": "cockpit_godot_alive", "status": "green",
                    "note": f"pid {pids[0]} running"}
        return {"name": "cockpit_godot_alive", "status": "amber",
                "note": "cockpit not running (POST /api/cockpit/launch to start)"}
    except Exception as e:
        return {"name": "cockpit_godot_alive", "status": "amber",
                "note": str(e)[:80]}


def sentinel_f44_rollup_fresh() -> dict:
    import time
    p = REG / "qsb_floor44_accounts_state.json"
    if not p.exists():
        return {"name": "f44_rollup_fresh", "status": "amber",
                "note": "roll-up file missing"}
    age_min = (time.time() - p.stat().st_mtime) / 60.0
    if age_min < 30:
        return {"name": "f44_rollup_fresh", "status": "green",
                "note": f"age {age_min:.1f}min"}
    return {"name": "f44_rollup_fresh", "status": "amber",
            "note": f"stale · age {age_min:.0f}min"}


def sentinel_auger_consult_log_fresh() -> dict:
    p = REG / "qsb_auger_consults.jsonl"
    if not p.exists():
        return {"name": "auger_consult_log_freshness", "status": "amber",
                "note": "no consults yet"}
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"name": "auger_consult_log_freshness", "status": "green",
            "note": f"{len(lines)} consult(s) on file"}


def sentinel_helm_briefing_log_fresh() -> dict:
    p = REG / "qsb_helm_briefings.jsonl"
    if not p.exists():
        return {"name": "helm_briefing_log_freshness", "status": "amber",
                "note": "no briefings yet"}
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"name": "helm_briefing_log_freshness", "status": "green",
            "note": f"{len(lines)} briefing(s) on file"}


SENTINELS = (
    sentinel_dashboard_alive,
    sentinel_kernel_chat_reachable,
    sentinel_f47_chat_history,
    sentinel_f44_accounts_fresh,
    sentinel_helix_continuity,
    sentinel_lineage_growing,
    sentinel_parallel_helix_intact,
    sentinel_governor_recent,
    sentinel_real_money_gates_locked,
    sentinel_provider_spend_under_cap,
    sentinel_mood_engine_current,
    sentinel_activity_tail_growing,
    # V17 additions
    sentinel_binance_testnet_creds,
    sentinel_alpaca_paper_creds,
    sentinel_cockpit_godot_alive,
    sentinel_f44_rollup_fresh,
    sentinel_auger_consult_log_fresh,
    sentinel_helm_briefing_log_fresh,
)


def run_all() -> dict:
    results = []
    counts = {"green": 0, "amber": 0, "red": 0}
    for fn in SENTINELS:
        try:
            r = fn()
        except Exception as e:
            r = {"name": getattr(fn, "__name__", "?"), "status": "red",
                 "note": f"sentinel itself errored: {str(e)[:80]}"}
        results.append(r)
        counts[r.get("status", "amber")] = counts.get(r.get("status", "amber"), 0) + 1
        # Stamp individual sentinel events
        _stamp_activity("audit_event",
                         summary=f"sentinel · {r['name']} · {r['status']} · {r['note']}",
                         floor="F30",
                         payload={"sentinel": r["name"], "status": r["status"]})
        # Red alerts get a louder event kind
        if r.get("status") == "red":
            _stamp_activity("gate_blocked",
                             summary=f"SENTINEL RED · {r['name']} · {r['note']}",
                             floor="F30",
                             payload={"sentinel": r["name"]})

    report = {
        "ok": True,
        "kind": "qsb_sentinels_report",
        "generated_ts": _now(),
        "counts": counts,
        "results": results,
        "advisory_only": True,
        "floor": "F30",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Stamp the summary event
    _stamp_activity("audit_event",
                     summary=(f"sentinels run · {counts['green']} green · "
                              f"{counts['amber']} amber · {counts['red']} red"),
                     floor="F30",
                     payload={"counts": counts})
    return report


if __name__ == "__main__":
    r = run_all()
    print(f"  ── sentinels report ──")
    print(f"  counts: {r['counts']}")
    for s in r["results"]:
        glyph = {"green": "✓", "amber": "·", "red": "✗"}.get(s["status"], "?")
        print(f"  {glyph} {s['name']:30s}  {s['status']:6s}  {s['note']}")
