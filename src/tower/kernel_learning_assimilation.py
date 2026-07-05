"""kernel_learning_assimilation.py

Cognitive Learning Assimilation layer for the QSB Kernel (advisory only).

Walks the existing learning loop registries/logs and produces a structured
"what was learned this tick" record. Writes both a current-state registry
and an append-only learning journal.

Writes:
    data/registries/qsb_kernel_learning_assimilation_state.json
    data/logs/qsb_kernel_learning_assimilation.jsonl
"""

from pathlib import Path
import json
import sys

from tower.kernel_cognitive_common import (
    LOGS, append_jsonl, load_registry, registry_exists,
    safety_block, utc_now_iso, write_registry,
)


def _tail_jsonl(name, n=8):
    p = LOGS / name
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(L) for L in lines if L.strip()]
    except Exception:
        return []


def run():
    learn = load_registry("eqsb_kernel_learning_loop.json")
    ledger = load_registry("eqsb_claude_upgrade_ledger.json")
    last_change = load_registry("eqsb_last_claude_change_summary.json")
    code_obs = load_registry("eqsb_code_observatory.json")
    hw_obs = load_registry("eqsb_hardware_observatory.json")
    smoke_v2 = load_registry("qsb_kernel_learning_smoke_test_v2_latest.json")
    probe = load_registry("qsb_kernel_thinking_upgrade_probe_latest.json")
    phase_tail = _tail_jsonl("eqsb_phase_history.jsonl", 8)
    changes_tail = _tail_jsonl("eqsb_claude_changes.jsonl", 8)

    assimilated = []
    if isinstance(ledger, dict) and ledger.get("latest_phase"):
        assimilated.append({
            "kind": "upgrade_ledger_latest_phase",
            "phase": ledger.get("latest_phase"),
            "summary": ledger.get("latest_summary"),
            "files_created": len(ledger.get("latest_files_created") or []),
            "files_modified": len(ledger.get("latest_files_modified") or []),
            "source": "data/registries/eqsb_claude_upgrade_ledger.json",
        })
    if isinstance(last_change, dict) and last_change.get("phase"):
        assimilated.append({
            "kind": "last_claude_change",
            "phase": last_change.get("phase"),
            "summary": last_change.get("summary"),
            "source": "data/registries/eqsb_last_claude_change_summary.json",
        })
    if isinstance(smoke_v2, dict) and smoke_v2.get("verdict"):
        assimilated.append({
            "kind": "learning_smoke_v2_result",
            "verdict": smoke_v2.get("verdict"),
            "passes": smoke_v2.get("passes"),
            "failures": smoke_v2.get("failures"),
            "log": smoke_v2.get("log"),
            "source": ("data/registries/"
                       "qsb_kernel_learning_smoke_test_v2_latest.json"),
        })
    if isinstance(probe, dict) and probe.get("timestamp_utc"):
        assimilated.append({
            "kind": "thinking_upgrade_probe",
            "timestamp_utc": probe.get("timestamp_utc"),
            "purpose": probe.get("purpose"),
            "log": probe.get("log"),
            "source": ("data/registries/"
                       "qsb_kernel_thinking_upgrade_probe_latest.json"),
        })
    if isinstance(code_obs, dict) and code_obs.get("total_files"):
        assimilated.append({
            "kind": "code_observatory_summary",
            "total_files": code_obs.get("total_files"),
            "by_area_counts": code_obs.get("by_area_counts"),
            "source": "data/registries/eqsb_code_observatory.json",
        })
    if isinstance(hw_obs, dict) and (hw_obs.get("cpu_summary")
                                     or hw_obs.get("gpu_summary")):
        assimilated.append({
            "kind": "hardware_observatory_summary",
            "cpu_summary": hw_obs.get("cpu_summary"),
            "gpu_summary": hw_obs.get("gpu_summary"),
            "memory_pressure": hw_obs.get("memory_pressure"),
            "source": "data/registries/eqsb_hardware_observatory.json",
        })

    sources_examined = [
        "data/registries/eqsb_kernel_learning_loop.json",
        "data/registries/eqsb_claude_upgrade_ledger.json",
        "data/registries/eqsb_last_claude_change_summary.json",
        "data/registries/eqsb_code_observatory.json",
        "data/registries/eqsb_hardware_observatory.json",
        "data/registries/qsb_kernel_learning_smoke_test_v2_latest.json",
        "data/registries/qsb_kernel_thinking_upgrade_probe_latest.json",
        "data/logs/eqsb_phase_history.jsonl",
        "data/logs/eqsb_claude_changes.jsonl",
    ]
    missing_sources = [
        s for s in sources_examined
        if not (Path("/vaults/nvme0/qsb_tower_v1") / s).exists()
    ]

    payload = {
        "module": "kernel_learning_assimilation",
        "purpose": ("Assimilate evidence from the learning loop and upgrade "
                    "ledger into a single structured tick record."),
        "timestamp_utc": utc_now_iso(),
        "assimilated_items": assimilated,
        "assimilated_item_count": len(assimilated),
        "phase_history_tail": [
            {"ts": (r.get("ts") or "")[:19],
             "phase": r.get("phase") or r.get("event")}
            for r in phase_tail
        ],
        "claude_changes_log_tail": [
            {"ts": (r.get("ts") or "")[:19],
             "phase": r.get("phase") or r.get("event")}
            for r in changes_tail
        ],
        "kernel_learning_loop_meta": {
            "generated_ts": (learn.get("generated_ts")
                              if isinstance(learn, dict) else None),
            "loop": (learn.get("loop")
                      if isinstance(learn, dict) else None),
            "learn_from": (learn.get("learn_from")
                            if isinstance(learn, dict) else None),
        },
        "source_file_list": sources_examined,
        "missing_sources": missing_sources,
        "confidence": (0.9 if assimilated and not missing_sources else 0.6),
        "warnings": ["missing_source:" + s for s in missing_sources],
        "safety": safety_block(),
    }

    rel = write_registry("qsb_kernel_learning_assimilation_state.json",
                          payload)
    append_jsonl("qsb_kernel_learning_assimilation.jsonl", {
        "ts": utc_now_iso(),
        "assimilated_item_count": len(assimilated),
        "missing_sources": len(missing_sources),
    })
    return {"written": rel,
            "assimilated_item_count": len(assimilated)}


def main():
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
