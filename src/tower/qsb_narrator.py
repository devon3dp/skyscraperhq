"""
QSB Tower Command Center — Running Commentary Narrator
Phase: QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1

Produces TEXT-ONLY narration that the browser speechSynthesis API can
speak. No server-side TTS is used. No external audio dependencies.

Endpoints (read-only):
  /api/narrator/tower
  /api/narrator/floor/<floor_id>
  /api/narrator/worker/<worker_id>
  /api/narrator/profit
  /api/narrator/openclaw
  /api/narrator/kernel

Every utterance is composed from real registry data. If the source
is missing the narrator says so honestly ("No live data for floor X.").
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import re

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "speech_method": "browser_web_speech_synthesis",
        "real_money_live_trading_enabled": False,
    }


def _floor_label(n):
    m = _load("qsb_floor_name_map.json", {})
    nm = (m.get("name_map") or {}) if isinstance(m, dict) else {}
    label = nm.get(str(n))
    if not label:
        label = "Floor " + str(n)
    return label


def _wrap(reason, text, extra=None):
    payload = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_narrator_utterance",
        "generated_ts": _now(),
        "reason": reason,
        "text": text,
        "speech_settings": {
            "rate": 1.0,
            "pitch": 1.0,
            "volume": 0.95,
            "lang": "en-US",
            "voice_hint": "Google US English",
        },
        "char_count": len(text),
    }
    if extra:
        payload.update(extra)
    payload.update(_safety_envelope())
    # Persist every utterance to qsb_narrator_history.jsonl.
    try:
        from tower.qsb_live_telemetry_repairs import record_narrator_utterance
        record_narrator_utterance(payload)
    except Exception:
        pass
    return payload


# ── Tower-level commentary ─────────────────────────────────────────────

def narrate_tower():
    cw = _load("qsb_canonical_workers.json", {})
    oc = _load("qsb_openclaw_state.json", {})
    learning = _load("qsb_trade_learning.json", {})
    open_ = _load("qsb_open_paper_trades.json", {})
    discipline = _load("qsb_worker_discipline.json", {})
    eqsb_intro = _load("eqsb_kernel_introspection_latest.json", {})

    safety_state = (eqsb_intro.get("guardian") or {}).get("safety_state") or "unknown"
    entropy_score = (eqsb_intro.get("entropy") or {}).get("entropy_score")

    parts = []
    parts.append("Tower status report.")
    parts.append("EQSB Kernel is active, local only. Guardian safety state %s. "
                 "Entropy score %s." % (safety_state, entropy_score))
    parts.append("Workforce: %d canonical workers, %d active and reporting, "
                 "%d newly employed." % (
                     cw.get("total_canonical_workers") or 0,
                     cw.get("total_active_workers") or 0,
                     cw.get("total_newly_employed_workers") or 0))
    parts.append("Paper trading desk: %d open trades out of %d allowed. "
                 "Realized PnL %s across %d closed trades, %d lessons learned." %
                 (open_.get("open_trade_count") or 0,
                  open_.get("max_open_trades") or 20,
                  learning.get("total_realized_pnl") or 0,
                  learning.get("closed_trade_count") or 0,
                  learning.get("lesson_count") or 0))
    parts.append("OpenClaw is %s with %d diagnostic tickets." %
                 (oc.get("status") or "unknown",
                  oc.get("diagnostic_ticket_count") or 0))
    on_warn = discipline.get("total_on_warning") or 0
    if on_warn:
        parts.append("Discipline alert: %d worker(s) on warning." % on_warn)
    else:
        parts.append("No discipline alerts. The skyscraper is steady.")
    parts.append("Real-money trading remains disabled. "
                  "Execution gates are locked.")
    return _wrap("tower_summary", " ".join(parts))


# ── Floor-level commentary ─────────────────────────────────────────────

def _floor_num_from_id(floor_id):
    if floor_id is None:
        return None
    if isinstance(floor_id, int):
        return floor_id
    s = str(floor_id)
    if s.isdigit():
        return int(s)
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def narrate_floor(floor_id):
    n = _floor_num_from_id(floor_id)
    if n is None:
        return _wrap("floor_summary",
                     "I do not recognise that floor identifier.")

    label = _floor_label(n)
    cw = _load("qsb_canonical_workers.json", {})
    workers = (cw.get("workers") or [])
    on_floor = [w for w in workers
                 if w.get("home_floor") and (("_" + str(n) + "_") in str(w.get("home_floor"))
                                              or str(w.get("home_floor")).endswith("_" + str(n))
                                              or str(w.get("home_floor")) == str(n)
                                              or (str(w.get("home_floor")).startswith("floor_")
                                                   and str(w.get("home_floor"))[6:].lstrip("0").startswith(str(n))))]

    parts = ["Floor %d, %s." % (n, label)]
    parts.append("Worker count: %d." % len(on_floor))

    role_counts = {}
    for w in on_floor:
        r = w.get("role") or "unassigned"
        role_counts[r] = role_counts.get(r, 0) + 1
    if role_counts:
        top_roles = sorted(role_counts.items(), key=lambda kv: -kv[1])[:3]
        parts.append("Top roles: " + ", ".join(
            "%s (%d)" % (r, c) for r, c in top_roles) + ".")

    # Department-level PnL
    profit = _load("qsb_profit_command.json", {})
    matching = []
    for dept in (profit.get("by_department") or []):
        d = str(dept.get("department") or "")
        if (("_" + str(n) + "_") in d or d.endswith("_" + str(n))
                or d == ("floor_" + str(n).zfill(2))
                or d == ("floor_" + str(n))):
            matching.append(dept)
    if matching:
        m = matching[0]
        parts.append("Realized PnL contribution: %s across %d profitable and %d losing paper trades. "
                     "Lessons learned: %d." %
                     (m.get("realized_pnl"),
                      m.get("profitable_trades"),
                      m.get("loss_trades"),
                      m.get("lessons_learned")))

    # OpenClaw current focus
    oc_route = _load("qsb_dashboard_live_telemetry.json", {}).get("openclaw_route") or {}
    if oc_route.get("current_floor") == n:
        parts.append("OpenClaw is currently inspecting this floor.")

    if len(on_floor) == 0 and not matching:
        parts.append("No live activity data for this floor.")
    return _wrap("floor_summary", " ".join(parts))


# ── Worker-level commentary ────────────────────────────────────────────

def narrate_worker(worker_id):
    sc = _load("qsb_worker_scorecards.json", {})
    card = next((c for c in (sc.get("scorecards") or [])
                 if c.get("worker_id") == worker_id), None)
    if not card:
        return _wrap("worker_summary",
                     "I have no scorecard for worker %s." % worker_id)
    parts = ["%s, role %s, floor %s." % (card["name"], card["role"], card["floor"])]
    parts.append("Rank %s with %d reward points." % (card["rank"], card["reward_points"]))
    if card["profitable_contributions"] > 0 or card["loss_contributions"] > 0:
        parts.append("%d profitable trades, %d losing trades, realized PnL %s." %
                     (card["profitable_contributions"],
                      card["loss_contributions"],
                      card["realized_pnl_contribution"]))
    if card["lessons_learned"] > 0:
        parts.append("%d lesson(s) recorded." % card["lessons_learned"])
    if card["strikes"] > 0:
        parts.append("Discipline: %d strike(s)." % card["strikes"])
    if card.get("promotion_eligible"):
        parts.append("This worker is currently eligible for promotion to %s." %
                     card.get("next_rank"))
    return _wrap("worker_summary", " ".join(parts),
                  extra={"worker_id": worker_id})


# ── Profit Command commentary ──────────────────────────────────────────

def narrate_profit():
    p = _load("qsb_profit_command.json", {})
    parts = ["Profit Command report."]
    parts.append("Mode: %s. Gateway: %s." %
                 (p.get("trading_mode"), p.get("gateway_status")))
    parts.append("Open trades %s of %s. Realized PnL %s. Closed trades %s. Lessons %s." %
                 (p.get("open_trade_count"),
                  p.get("max_open_trades"),
                  p.get("total_realized_pnl"),
                  p.get("closed_trade_count"),
                  p.get("lesson_count")))
    best = p.get("best_department_by_contribution")
    if best and (best.get("realized_pnl") or 0) > 0:
        parts.append("Best department by contribution: %s with PnL %s." %
                     (best["department"], best["realized_pnl"]))
    top = p.get("top_workers") or []
    if top:
        names = ", ".join(t["name"] for t in top[:3])
        parts.append("Top workers: %s." % names)
    actions = p.get("next_profit_focused_actions") or []
    for a in actions[:3]:
        parts.append(a)
    parts.append("Real-money trading remains disabled.")
    return _wrap("profit_summary", " ".join(parts))


# ── OpenClaw commentary ────────────────────────────────────────────────

def narrate_openclaw():
    oc = _load("qsb_openclaw_state.json", {})
    route = _load("qsb_dashboard_live_telemetry.json", {}).get("openclaw_route") or {}
    parts = ["OpenClaw report."]
    parts.append("Status %s. Visual %s. Sandbox %s. Trade supervision %s. "
                 "Diagnostic ticketing %s." %
                 (oc.get("status") or "unknown",
                  oc.get("openclaw_visual_enabled"),
                  oc.get("openclaw_sandbox_enabled"),
                  oc.get("openclaw_trade_supervision_enabled"),
                  oc.get("openclaw_diagnostic_ticketing_enabled")))
    parts.append("OpenClaw real tool execution remains %s." %
                 oc.get("openclaw_real_tool_execution_enabled"))
    if route.get("current_floor") is not None:
        parts.append("OpenClaw is currently inspecting floor %s, advanced by %s." %
                     (route.get("current_floor"), route.get("advanced_by")))
    parts.append("Diagnostic tickets open: %s." %
                 (oc.get("diagnostic_ticket_count") or 0))
    return _wrap("openclaw_summary", " ".join(parts))


# ── Kernel / Penthouse commentary ──────────────────────────────────────

def narrate_kernel():
    eqsb = _load("eqsb_kernel_introspection_latest.json", {})
    sa = _load("eqsb_kernel_self_audit.json", {})
    parts = ["Penthouse Kernel report."]
    ident = (eqsb.get("identity") or {})
    parts.append("Kernel %s, mode %s." % (ident.get("name") or "EQSB",
                                            ident.get("mode") or "active_local_only"))
    parts.append("Self-audit verdict %s." % sa.get("verdict"))
    g = eqsb.get("guardian") or {}
    parts.append("Guardian safety state %s with default verdict %s." %
                 (g.get("safety_state"), g.get("default_verdict_for_read_only")))
    e = eqsb.get("entropy") or {}
    parts.append("Entropy %s, stability %s, drift %s." %
                 (e.get("entropy_score"), e.get("stability_score"),
                  e.get("drift_score")))
    qs = eqsb.get("quantum_signal") or {}
    parts.append("Quantum signal mode %s. Real hardware: %s. Qiskit: %s. IBM Quantum: %s." %
                 (qs.get("mode"),
                  qs.get("real_quantum_source_connected"),
                  qs.get("qiskit_connected"),
                  qs.get("ibm_quantum_connected")))
    return _wrap("kernel_summary", " ".join(parts))


# ── Critical-only commentary ───────────────────────────────────────────

def narrate_critical():
    cont_alerts = []
    eqsb = _load("eqsb_kernel_introspection_latest.json", {})
    cont = (eqsb.get("continuity_state") or {})
    if cont.get("drift_alerts"):
        cont_alerts.extend(cont["drift_alerts"])
    if cont.get("stale_memory_flags"):
        for f in cont["stale_memory_flags"]:
            cont_alerts.append("stale " + str(f.get("path")))

    discipline = _load("qsb_worker_discipline.json", {})
    contradictions = _load("eqsb_contradiction_report.json", {})

    parts = ["Critical alerts only."]
    critical = []
    if discipline.get("total_on_warning") or 0:
        critical.append("%d worker(s) on warning." % discipline["total_on_warning"])
    if discipline.get("total_restricted") or 0:
        critical.append("%d worker(s) restricted." % discipline["total_restricted"])
    if discipline.get("total_suspended") or 0:
        critical.append("%d worker(s) suspended." % discipline["total_suspended"])
    sev = (contradictions.get("by_severity") or {})
    if sev.get("critical"):
        critical.append("%d critical contradiction(s)." % sev["critical"])
    for a in cont_alerts[:4]:
        critical.append(str(a))
    if not critical:
        parts.append("No critical alerts. The skyscraper is steady.")
    else:
        parts.extend(critical)
    return _wrap("critical_only", " ".join(parts))


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "tower").lower()
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "tower":     print(json.dumps(narrate_tower(),    indent=2))
    elif cmd == "floor":   print(json.dumps(narrate_floor(arg), indent=2))
    elif cmd == "worker":  print(json.dumps(narrate_worker(arg or ""), indent=2))
    elif cmd == "profit":  print(json.dumps(narrate_profit(),   indent=2))
    elif cmd == "openclaw":print(json.dumps(narrate_openclaw(), indent=2))
    elif cmd == "kernel":  print(json.dumps(narrate_kernel(),   indent=2))
    elif cmd == "critical":print(json.dumps(narrate_critical(), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "valid": ["tower", "floor", "worker",
                                     "profit", "openclaw", "kernel",
                                     "critical"]}, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
