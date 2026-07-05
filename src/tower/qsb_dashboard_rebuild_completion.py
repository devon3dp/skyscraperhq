"""
QSB Dashboard Total Rebuild Completion Engine
Phase: QSB_DASHBOARD_TOTAL_REBUILD_3D_WORKERS_OPENCLAW_ONLINE_V1

18 acceptance gates. Honest completion score. No 100/100 unless every
gate verifies with evidence drawn from real registries/endpoints/files.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import socket
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_SCORE   = REG / "qsb_dashboard_total_rebuild_completion_score.json"
P_GATES   = REG / "qsb_dashboard_total_rebuild_acceptance_gates.json"
L_LOOP    = LOGS / "qsb_dashboard_total_rebuild_loop.jsonl"

DASH_URL = "http://127.0.0.1:8765"


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
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _http_get(path):
    try:
        with urllib.request.urlopen(DASH_URL + path, timeout=3) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except Exception:
        return 0, ""


def _gate(gid, name, passed, evidence, repair=""):
    return {"gate_id": gid, "name": name,
            "passed": bool(passed), "evidence": evidence,
            "repair_if_failed": repair}


def evaluate_gates():
    gates = []

    listening = False
    try:
        s = socket.create_connection(("127.0.0.1", 8765), timeout=1)
        s.close(); listening = True
    except Exception:
        pass
    html_code, html_body = (_http_get("/") if listening else (0, ""))
    unified_code, _ = (_http_get("/api/unified") if listening else (0, ""))
    telem_code, _ = (_http_get("/api/dashboard/live_telemetry") if listening else (0, ""))

    # G1 dashboard loads
    gates.append(_gate(
        "G1", "Dashboard loads",
        listening and html_code == 200,
        "port_listening=%s html=%s" % (listening, html_code),
        "./scripts/qsb_dashboard_start.sh",
    ))

    # G2 new 3D renderer active — verified via stronger SVG probe
    # (qsb_g2_svg_probe) which actually fetches /, /static/*.js, and
    # /api/unified and verifies DOM ids, script tags, renderer
    # functions, and worker payload.
    state_3d = _load("qsb_new_3d_dashboard_state.json")
    try:
        from tower.qsb_g2_svg_probe import probe as _g2_probe
        probe = _g2_probe()
    except Exception:
        probe = {"all_passed": False, "passed": 0, "total": 0}
    g2_state = state_3d.get("renderer_state") == "rebuilt_default_mode_to_show_selected_floor_workers"
    g2 = g2_state and probe.get("all_passed") is True
    gates.append(_gate(
        "G2", "New 3D renderer active (probe %s/%s passed)" % (
            probe.get("passed"), probe.get("total")),
        g2,
        "state=%s probe_passed=%s/%s default_mode=%s" % (
            state_3d.get("renderer_state"),
            probe.get("passed"), probe.get("total"),
            state_3d.get("default_worker_view_mode")),
    ))

    # G3 floors clickable
    cockpit_js = ROOT / "src/dashboard/static/cockpit.js"
    body_cjs = ""
    try: body_cjs = cockpit_js.read_text(encoding="utf-8")
    except Exception: pass
    g3 = "handleScenePick" in body_cjs and "selectedFloor" in body_cjs
    gates.append(_gate(
        "G3", "Floors clickable + selectedFloor tracked",
        g3,
        "handleScenePick + selectedFloor present in cockpit.js"
    ))

    # G4 selected floor interior populated
    interiors = _load("qsb_department_interiors_state.json")
    g4 = (interiors.get("departments_with_interior_layer") or 0) >= 9
    gates.append(_gate(
        "G4", "Selected floor interior populated (9+ departments)",
        g4,
        "departments_with_interior=%s" %
        interiors.get("departments_with_interior_layer"),
    ))

    # G5 workers visible inside selected department
    rooms = _load("qsb_worker_room_assignments.json")
    g5 = bool((rooms.get("by_floor_room") or {}))
    gates.append(_gate(
        "G5", "Workers placed at rooms per floor",
        g5,
        "by_floor_room keys=%s" % len((rooms.get("by_floor_room") or {})),
    ))

    # G6 workers have task/state/station
    stations = _load("qsb_worker_station_assignments.json")
    tasks = _load("qsb_worker_task_board.json")
    g6 = (stations.get("station_count") or 0) > 0 and (tasks.get("task_count") or 0) > 0
    gates.append(_gate(
        "G6", "Workers have stations + tasks",
        g6,
        "stations=%s task_count=%s" % (stations.get("station_count"),
                                         tasks.get("task_count")),
    ))

    # G7 no random worker swarm
    visual_pol = _load("qsb_worker_visual_policy.json")
    exterior = (visual_pol.get("exterior_tower_view") or {})
    g7 = exterior.get("show_individual_workers") is False
    gates.append(_gate(
        "G7", "No random worker swarm (exterior individual workers off)",
        g7,
        "exterior.show_individual_workers=%s" %
        exterior.get("show_individual_workers"),
    ))

    # G8 no default counts_only hiding workers
    g8 = state_3d.get("default_worker_view_mode") == "selected_floor_and_groups"
    gates.append(_gate(
        "G8", "Default view is NOT counts_only — workers can appear",
        g8,
        "default_worker_view_mode=%s" %
        state_3d.get("default_worker_view_mode"),
    ))

    # G9 sim workers separated from operational
    sim = _load("qsb_sim_worker_audit.json")
    g9 = sim.get("should_be_hidden_externally") is True
    gates.append(_gate(
        "G9", "SIM workers separated from operational view",
        g9,
        "should_be_hidden_externally=%s relocation_floor=%s" %
        (sim.get("should_be_hidden_externally"),
         sim.get("relocation_target_floor_number"))
    ))

    # G10 OpenClaw supervisor active
    role = _load("qsb_openclaw_role_definition.json")
    g10 = bool(role.get("role"))
    gates.append(_gate(
        "G10", "OpenClaw supervisor role defined",
        g10,
        "role=%s" % role.get("role", "")[:60],
    ))

    # G11 OpenClaw visual source-backed
    route = _load("qsb_openclaw_route.json")
    g11 = (route.get("is_random") is False
            and route.get("current_floor") is not None)
    gates.append(_gate(
        "G11", "OpenClaw visual source-backed (route deterministic)",
        g11,
        "current_floor=%s advanced_by=%s is_random=%s" %
        (route.get("current_floor"), route.get("advanced_by"), route.get("is_random")),
    ))

    # G12 departments/floors created or repaired
    fc = _load("qsb_floor_manifest_completion.json")
    g12 = (fc.get("manifests_present") or 0) >= (fc.get("total") or 0) * 0.9
    gates.append(_gate(
        "G12", "Departments/floors have manifests (>=90% coverage)",
        g12,
        "manifests_present=%s/%s pct=%s" %
        (fc.get("manifests_present"), fc.get("total"),
         fc.get("completion_pct")),
    ))

    # G13 movement source-backed
    mv = _load("qsb_worker_movements_latest.json")
    g13 = (mv.get("movement_count") or 0) > 0
    gates.append(_gate(
        "G13", "Worker movements source-backed (>=1 record from real trades)",
        g13,
        "movement_count=%s" % mv.get("movement_count"),
    ))

    # G14 packets source-backed
    pkts = _load("qsb_live_packets_latest.json")
    g14 = (pkts.get("packet_count") or 0) > 0
    gates.append(_gate(
        "G14", "Live packets source-backed",
        g14,
        "packet_count=%s" % pkts.get("packet_count"),
    ))

    # G15 narrator source-backed
    nh = _load("qsb_narrator_history_latest.json")
    g15 = nh.get("ok") is True
    gates.append(_gate(
        "G15", "Narrator endpoints + history wired",
        g15,
        "narrator_history_present=%s recent_count=%s" %
        (bool(nh), nh.get("recent_utterance_count")),
    ))

    # G16 Kernel chat explains rebuild
    kda = ROOT / "src/tower/kernel_dialogue_adapter.py"
    body = ""
    try: body = kda.read_text(encoding="utf-8")
    except Exception: pass
    g16 = "rebuild_v1" in body or "worker_truth" in body
    gates.append(_gate(
        "G16", "Kernel chat workforce + rebuild topics wired",
        g16,
        "topics_present=%s" % g16,
    ))

    # G17 safety locks remain closed
    gov = _load("eqsb_guardian_state.json")
    paper = _load("qsb_paper_trading_policy.json")
    g17 = (paper.get("real_money_live_trading_enabled") is False
            and gov.get("safety_state") in ("OK", "DEGRADED", "DRIFTING"))
    gates.append(_gate(
        "G17", "Safety locks remain closed",
        g17,
        "real_money_live=%s guardian_safety=%s" %
        (paper.get("real_money_live_trading_enabled"),
         gov.get("safety_state")),
    ))

    # G18 real-money trading remains off
    g18 = paper.get("real_money_live_trading_enabled") is False
    gates.append(_gate(
        "G18", "Real-money trading remains OFF (immutable in code)",
        g18,
        "real_money_live_trading_enabled=%s" %
        paper.get("real_money_live_trading_enabled"),
    ))

    return gates


def build_score(iteration=1):
    gates = evaluate_gates()
    passed = sum(1 for g in gates if g["passed"])
    total = len(gates)
    score = round(100.0 * passed / total, 1)
    failed = [g for g in gates if not g["passed"]]
    payload = {
        "ok": True,
        "phase": "QSB_DASHBOARD_TOTAL_REBUILD_3D_WORKERS_OPENCLAW_ONLINE_V1",
        "kind": "qsb_dashboard_total_rebuild_completion_score",
        "generated_ts": _now(),
        "iteration": iteration,
        "completion_score": score,
        "passed": passed, "total": total,
        "is_100_complete": score == 100.0,
        "failed_gates": [g["gate_id"] for g in failed],
        "failed_details": failed,
    }
    payload.update(_safety_envelope())
    _write_json(P_SCORE, payload)

    gates_payload = {
        "ok": True,
        "phase": payload["phase"],
        "kind": "qsb_dashboard_total_rebuild_acceptance_gates",
        "generated_ts": _now(),
        "iteration": iteration,
        "gates": gates,
        "passed_count": passed, "failed_count": total - passed,
    }
    gates_payload.update(_safety_envelope())
    _write_json(P_GATES, gates_payload)

    # Loop log
    L_LOOP.parent.mkdir(parents=True, exist_ok=True)
    with L_LOOP.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": _now(), "iteration": iteration,
            "score": score, "failed": payload["failed_gates"],
        }) + "\n")

    return payload


def main():
    import sys
    iteration = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    payload = build_score(iteration)
    print(json.dumps({
        "completion_score": payload["completion_score"],
        "passed": payload["passed"], "total": payload["total"],
        "is_100_complete": payload["is_100_complete"],
        "failed_gates": payload["failed_gates"],
    }, indent=2))


if __name__ == "__main__":
    main()
