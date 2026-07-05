"""kernel_registry_answer_builder.py

Shared registry-loading helpers used by the kernel_dialogue_adapter
topic blocks (recent_upgrades, godot_native_status, missing_features,
learning_evidence) and the direct report scripts.

No execution. No external calls. No secrets.
"""

from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"


def load_registry(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def tail_jsonl(name, n=5):
    p = LOGS / name
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(L) for L in lines if L.strip()]
    except Exception:
        return []


def recent_upgrades_report():
    ledger = load_registry("eqsb_claude_upgrade_ledger.json")
    last = load_registry("eqsb_last_claude_change_summary.json")
    risk = load_registry("eqsb_upgrade_risk_history.json")
    history = tail_jsonl("eqsb_phase_history.jsonl", 8)
    return {
        "registries_read": [
            "data/registries/eqsb_claude_upgrade_ledger.json",
            "data/registries/eqsb_last_claude_change_summary.json",
            "data/registries/eqsb_kernel_upgrade_plan.json",
            "data/registries/eqsb_upgrade_risk_history.json",
            "data/logs/eqsb_phase_history.jsonl",
            "data/logs/eqsb_claude_changes.jsonl",
        ],
        "phase_count": ledger.get("phase_count"),
        "latest_phase": ledger.get("latest_phase"),
        "latest_summary": ledger.get("latest_summary"),
        "latest_files_created": ledger.get("latest_files_created") or [],
        "latest_files_modified": ledger.get("latest_files_modified") or [],
        "last_claude_change": {
            "phase": last.get("phase"),
            "summary": last.get("summary"),
            "files_created_count": len(last.get("files_created") or []),
            "files_modified_count": len(last.get("files_modified") or []),
        },
        "upgrade_risk": {
            "current_risk_file_count": risk.get("current_risk_file_count"),
            "current_risks": (risk.get("current_risks") or [])[:6],
        },
        "phase_history_tail": [
            {"ts": (rec.get("ts") or "")[:19],
             "phase": rec.get("phase") or rec.get("event")}
            for rec in history
        ],
    }


def godot_native_status_report():
    return {
        "registries_read": [
            "data/registries/qsb_3d_engine_status.json",
            "data/registries/qsb_godot_install_verified.json",
            "data/registries/qsb_godot_project_status.json",
            "data/registries/qsb_godot_visual_score.json",
            "data/registries/qsb_godot_visual_acceptance_gates.json",
            "data/registries/qsb_pyqt_admin_fallback_status.json",
            "data/registries/qsb_panda3d_fallback_status.json",
            "data/registries/qsb_native_cockpit_visual_failure_audit.json",
        ],
        "engine_status": load_registry("qsb_3d_engine_status.json"),
        "godot_install_verified": load_registry("qsb_godot_install_verified.json"),
        "godot_project_status": load_registry("qsb_godot_project_status.json"),
        "godot_visual_score": load_registry("qsb_godot_visual_score.json"),
        "pyqt_fallback_status": load_registry("qsb_pyqt_admin_fallback_status.json"),
        "panda3d_fallback_status": load_registry("qsb_panda3d_fallback_status.json"),
        "visual_failure_audit_summary":
            load_registry("qsb_native_cockpit_visual_failure_audit.json").get("summary"),
        "launch_command": "./scripts/qsb_godot_run.sh",
        "panda3d_launch_command": "./scripts/qsb_panda3d_run.sh",
        "pyqt_admin_command": "./scripts/qsb_native_cockpit_run.sh",
    }


def missing_features_report():
    parity = load_registry("qsb_native_feature_parity_matrix.json")
    backlog = load_registry("qsb_native_missing_features_backlog.json")
    controls = load_registry("qsb_godot_original_controls_migration.json")
    gates = load_registry("qsb_godot_professional_dashboard_gates.json")
    rows = parity.get("rows") or []
    partial = [r for r in rows if isinstance(r, list) and len(r) >= 4
               and r[1] not in ("present", "added_v1", "migrated_v1",
                                  "done", "implemented")]
    return {
        "registries_read": [
            "data/registries/qsb_native_feature_parity_matrix.json",
            "data/registries/qsb_native_missing_features_backlog.json",
            "data/registries/qsb_godot_original_controls_migration.json",
            "data/registries/qsb_godot_professional_dashboard_gates.json",
        ],
        "feature_parity_summary": parity.get("summary"),
        "partial_or_missing_rows": [
            {"feature": r[0], "status": r[1], "action": r[3]}
            for r in partial[:18]
        ],
        "backlog_p1_to_migrate_next":
            backlog.get("p1_to_migrate_next") or backlog.get("missing_or_partial") or [],
        "backlog_p2_browser_fallback":
            backlog.get("p2_remain_browser_fallback") or [],
        "original_controls_status":
            {c.get("id"): c.get("status") for c in (controls.get("controls") or [])},
        "professional_gates_passed": gates.get("passed_count"),
        "professional_gates_total": gates.get("total"),
    }


def learning_evidence_report():
    learn = load_registry("eqsb_kernel_learning_loop.json")
    code_obs = load_registry("eqsb_code_observatory.json")
    hw_obs = load_registry("eqsb_hardware_observatory.json")
    ledger = load_registry("eqsb_claude_upgrade_ledger.json")
    changes_tail = tail_jsonl("eqsb_claude_changes.jsonl", 6)
    return {
        "registries_and_logs_read": [
            "data/registries/eqsb_kernel_learning_loop.json",
            "data/registries/eqsb_code_observatory.json",
            "data/registries/eqsb_hardware_observatory.json",
            "data/registries/eqsb_claude_upgrade_ledger.json",
            "data/logs/eqsb_claude_changes.jsonl",
            "data/logs/eqsb_phase_history.jsonl",
        ],
        "kernel_learning_loop": {
            "generated_ts": learn.get("generated_ts"),
            "loop": learn.get("loop"),
            "learn_from": learn.get("learn_from"),
        },
        "code_observatory": {
            "total_files": code_obs.get("total_files"),
            "by_area_counts": code_obs.get("by_area_counts"),
            "secret_safety": code_obs.get("secret_safety"),
        },
        "hardware_observatory": {
            "cpu_summary": hw_obs.get("cpu_summary"),
            "gpu_summary": hw_obs.get("gpu_summary"),
            "memory_pressure": hw_obs.get("memory_pressure"),
        },
        "upgrade_ledger": {
            "phase_count": ledger.get("phase_count"),
            "latest_phase": ledger.get("latest_phase"),
            "latest_files_created": len(ledger.get("latest_files_created") or []),
        },
        "claude_changes_log_tail": [
            {"ts": (r.get("ts") or "")[:19],
             "phase": r.get("phase") or r.get("event")}
            for r in changes_tail
        ],
    }


# ── Cognitive architecture reports (V1) ────────────────────────────────
# Surface what the 9 cognitive modules wrote in their registries. These
# helpers replace the canned identity fallback for cognitive questions.

_COGNITIVE_REGISTRY_FILES = [
    "qsb_kernel_perception_snapshot.json",
    "qsb_kernel_attention_state.json",
    "qsb_kernel_working_memory.json",
    "qsb_kernel_self_model.json",
    "qsb_kernel_reflection_state.json",
    "qsb_kernel_learning_assimilation_state.json",
    "qsb_kernel_goal_stack.json",
    "qsb_kernel_curiosity_queue.json",
    "qsb_kernel_opencore_supervision_state.json",
    "qsb_kernel_cognitive_tick_latest.json",
    "qsb_kernel_cognitive_smoke_test_latest.json",
]


def cognitive_uncertainty_report():
    """Answer the uncertainty question from registry evidence.

    Reads reflection, attention, perception, working memory, smoke v2,
    and cognitive smoke test. Never returns the canned identity block.
    """
    refl = load_registry("qsb_kernel_reflection_state.json")
    att = load_registry("qsb_kernel_attention_state.json")
    perc = load_registry("qsb_kernel_perception_snapshot.json")
    wm = load_registry("qsb_kernel_working_memory.json")
    smoke_v2 = load_registry("qsb_kernel_learning_smoke_test_v2_latest.json")
    cog_smoke = load_registry("qsb_kernel_cognitive_smoke_test_latest.json")

    return {
        "registries_read": [
            "data/registries/qsb_kernel_reflection_state.json",
            "data/registries/qsb_kernel_attention_state.json",
            "data/registries/qsb_kernel_perception_snapshot.json",
            "data/registries/qsb_kernel_working_memory.json",
            "data/registries/qsb_kernel_learning_smoke_test_v2_latest.json",
            "data/registries/qsb_kernel_cognitive_smoke_test_latest.json",
        ],
        "current_uncertainties": (refl.get("current_uncertainties") or []
                                   if isinstance(refl, dict) else []),
        "stale_sources": (refl.get("stale_sources") or []
                           if isinstance(refl, dict) else []),
        "missing_registries": (refl.get("missing_registries") or []
                                if isinstance(refl, dict) else []),
        "failed_tests": (refl.get("failed_tests") or []
                          if isinstance(refl, dict) else []),
        "next_repair_actions": (refl.get("next_repair_actions") or []
                                 if isinstance(refl, dict) else []),
        "evidence_sources": (refl.get("evidence_sources") or []
                              if isinstance(refl, dict) else []),
        "openclaw_inspection_suggestions": (
            refl.get("openclaw_inspection_suggestions") or []
            if isinstance(refl, dict) else []),
        "top5_attention": (
            [{"rank": it.get("priority_rank"),
              "issue": it.get("issue"),
              "severity": it.get("severity"),
              "action": it.get("recommended_action")}
             for it in (att.get("priority_items") or [])[:5]]
            if isinstance(att, dict) else []),
        "perception_summary": {
            "fresh_sources": (perc.get("fresh_sources") or [])[:8]
                              if isinstance(perc, dict) else [],
            "stale_sources": (perc.get("stale_sources") or [])[:8]
                              if isinstance(perc, dict) else [],
            "missing_sources": (perc.get("missing_sources") or [])[:8]
                                if isinstance(perc, dict) else [],
        },
        "working_memory_next_action": (
            wm.get("next_recommended_action")
            if isinstance(wm, dict) else None),
        "learning_smoke_v2_verdict": (
            smoke_v2.get("verdict") if isinstance(smoke_v2, dict) else None),
        "cognitive_smoke_test_verdict": (
            cog_smoke.get("verdict")
            if isinstance(cog_smoke, dict) else None),
        "execution_allowed": False,
        "advisory_only": True,
    }


def cognitive_architecture_report():
    """Describe how the kernel thinks now: the 9-module cognitive
    architecture, with the registry each module writes."""
    modules = [
        ("perception", "src/tower/kernel_perception_layer.py",
         "qsb_kernel_perception_snapshot.json"),
        ("attention", "src/tower/kernel_attention_layer.py",
         "qsb_kernel_attention_state.json"),
        ("working_memory", "src/tower/kernel_working_memory.py",
         "qsb_kernel_working_memory.json"),
        ("self_model", "src/tower/kernel_self_model.py",
         "qsb_kernel_self_model.json"),
        ("reflection", "src/tower/kernel_reflection_layer.py",
         "qsb_kernel_reflection_state.json"),
        ("learning_assimilation",
         "src/tower/kernel_learning_assimilation.py",
         "qsb_kernel_learning_assimilation_state.json"),
        ("goal_stack", "src/tower/kernel_goal_stack.py",
         "qsb_kernel_goal_stack.json"),
        ("curiosity_queue", "src/tower/kernel_curiosity_queue.py",
         "qsb_kernel_curiosity_queue.json"),
        ("opencore_supervision",
         "src/tower/kernel_opencore_supervision_bridge.py",
         "qsb_kernel_opencore_supervision_state.json"),
    ]
    present = {}
    for name, mod_path, reg in modules:
        d = load_registry(reg)
        present[name] = {
            "module": mod_path,
            "registry": "data/registries/" + reg,
            "registry_present": bool(d),
            "timestamp_utc": d.get("timestamp_utc") if isinstance(d, dict) else None,
            "confidence": d.get("confidence") if isinstance(d, dict) else None,
        }
    tick = load_registry("qsb_kernel_cognitive_tick_latest.json")
    return {
        "registries_read": [
            "data/registries/" + m[2] for m in modules
        ] + ["data/registries/qsb_kernel_cognitive_tick_latest.json"],
        "architecture_layers": [m[0] for m in modules],
        "modules": present,
        "cognitive_tick": {
            "timestamp_utc": tick.get("timestamp_utc")
                              if isinstance(tick, dict) else None,
            "module_results": tick.get("module_results")
                               if isinstance(tick, dict) else None,
        },
        "execution_allowed": False,
        "advisory_only": True,
    }


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if cmd == "recent":   out = recent_upgrades_report()
    elif cmd == "godot":  out = godot_native_status_report()
    elif cmd == "missing":out = missing_features_report()
    elif cmd == "learning": out = learning_evidence_report()
    elif cmd == "uncertainty": out = cognitive_uncertainty_report()
    elif cmd == "cognitive_architecture": out = cognitive_architecture_report()
    else:
        print("usage: kernel_registry_answer_builder.py "
              "{recent|godot|missing|learning|uncertainty|cognitive_architecture}")
        sys.exit(2)
    print(json.dumps(out, indent=2, default=str))
