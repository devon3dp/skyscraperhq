"""
EQSB System Observatory — Code + Hardware + Phase History + Graph
Phase: EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1

Read-only. Builds:

  Pre/post-change snapshot:
    data/registries/eqsb_phase_prechange_snapshot.json
    data/registries/eqsb_phase_postchange_snapshot.json (when invoked
                                                          with 'post')
    data/registries/eqsb_phase_changes_latest.json
    data/logs/eqsb_phase_prechange_snapshot.txt

  Code observatory:
    data/registries/eqsb_code_observatory.json
    data/registries/eqsb_code_map.json
    data/registries/eqsb_code_risk_report.json
    data/registries/eqsb_code_dependency_graph.json
    data/registries/eqsb_code_ownership_map.json
    data/logs/eqsb_code_observatory.jsonl

  Hardware observatory:
    data/registries/eqsb_hardware_observatory.json
    data/registries/eqsb_cpu_profile.json
    data/registries/eqsb_gpu_profile.json
    data/registries/eqsb_memory_profile.json
    data/registries/eqsb_storage_profile.json
    data/registries/eqsb_os_environment.json
    data/registries/eqsb_services_profile.json
    data/registries/eqsb_ports_profile.json
    data/registries/eqsb_model_lane_hardware_profile.json
    data/registries/eqsb_hardware_understanding.json
    data/registries/eqsb_performance_advice.json
    data/logs/eqsb_hardware_observatory.jsonl

  Claude upgrade ledger:
    data/registries/eqsb_claude_upgrade_ledger.json
    data/registries/eqsb_last_claude_change_summary.json
    data/registries/eqsb_phase_history.json
    data/registries/eqsb_upgrade_risk_history.json
    data/logs/eqsb_claude_changes.jsonl

  System understanding graph + learning loop:
    data/registries/eqsb_system_understanding_graph.json
    data/registries/eqsb_kernel_learning_loop.json
    data/registries/eqsb_kernel_lessons_learned.json
    data/registries/eqsb_code_assistance_policy.json
    data/registries/eqsb_code_patch_proposals.json
    data/logs/eqsb_kernel_learning_loop.jsonl

Hard rules:
  * read-only re: hardware / services / drivers
  * never invokes pip install / apt / nvidia-smi modify flags
  * redacts .env values; never copies API keys, tokens, secrets
  * never overwrites source code
  * advisory recommendations only
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

# Pre/post snapshot
P_PRE  = REG / "eqsb_phase_prechange_snapshot.json"
P_POST = REG / "eqsb_phase_postchange_snapshot.json"
P_CHANGES_LATEST = REG / "eqsb_phase_changes_latest.json"
L_PRE  = LOGS / "eqsb_phase_prechange_snapshot.txt"

# Code observatory
P_CODE_OBS  = REG / "eqsb_code_observatory.json"
P_CODE_MAP  = REG / "eqsb_code_map.json"
P_CODE_RISK = REG / "eqsb_code_risk_report.json"
P_CODE_DEPS = REG / "eqsb_code_dependency_graph.json"
P_CODE_OWN  = REG / "eqsb_code_ownership_map.json"
L_CODE      = LOGS / "eqsb_code_observatory.jsonl"

# Hardware observatory
P_HW_OBS  = REG / "eqsb_hardware_observatory.json"
P_HW_CPU  = REG / "eqsb_cpu_profile.json"
P_HW_GPU  = REG / "eqsb_gpu_profile.json"
P_HW_MEM  = REG / "eqsb_memory_profile.json"
P_HW_DISK = REG / "eqsb_storage_profile.json"
P_HW_OS   = REG / "eqsb_os_environment.json"
P_HW_SVC  = REG / "eqsb_services_profile.json"
P_HW_PORTS= REG / "eqsb_ports_profile.json"
P_HW_LANES= REG / "eqsb_model_lane_hardware_profile.json"
P_HW_UND  = REG / "eqsb_hardware_understanding.json"
P_HW_ADV  = REG / "eqsb_performance_advice.json"
L_HW      = LOGS / "eqsb_hardware_observatory.jsonl"

# Claude upgrade ledger
P_LEDGER  = REG / "eqsb_claude_upgrade_ledger.json"
P_LAST_CHANGE = REG / "eqsb_last_claude_change_summary.json"
P_HIST    = REG / "eqsb_phase_history.json"
P_RISKS   = REG / "eqsb_upgrade_risk_history.json"
L_LEDGER  = LOGS / "eqsb_claude_changes.jsonl"

# Graph + learning + code assistance
P_GRAPH   = REG / "eqsb_system_understanding_graph.json"
P_LOOP    = REG / "eqsb_kernel_learning_loop.json"
P_LESSONS = REG / "eqsb_kernel_lessons_learned.json"
P_CODE_AP = REG / "eqsb_code_assistance_policy.json"
P_PATCHES = REG / "eqsb_code_patch_proposals.json"
L_LOOP    = LOGS / "eqsb_kernel_learning_loop.jsonl"


# ── Helpers ─────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "read_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _safe_run(cmd, timeout=8):
    """Run a read-only command and capture stdout. Returns (stdout, ok).
    Never raises. Empty string + False on failure."""
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str),
                            capture_output=True, text=True,
                            timeout=timeout, env=os.environ.copy())
        return (p.stdout or "").strip(), p.returncode == 0
    except Exception:
        return "", False


def _redact(text):
    """Redact obvious secrets. We never copy raw env values."""
    if not text:
        return text
    patterns = [
        r'(?i)(api[_-]?key|secret|token|password|passwd|authorization)\s*[:=]\s*[^\s"\']+',
        r'(?i)Bearer\s+\S+',
    ]
    for p in patterns:
        text = re.sub(p, "<redacted>", text)
    return text


def _sha256(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record); record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


# ── Section 1 — Pre/post-change snapshot ───────────────────────────────

# We index a curated set of file groups (whole-tree sha-ing would be slow).
SNAPSHOT_GROUPS = [
    ("src",            ROOT / "src",             [".py"]),
    ("scripts",        ROOT / "scripts",         [".sh"]),
    ("dashboard_static", ROOT / "src/dashboard/static",
                                                 [".html", ".css", ".js"]),
    ("registries",     REG,                       [".json"]),
    ("floors",         ROOT / "floors",          [".json"]),
    ("penthouse",      ROOT / "penthouse",       [".py", ".json"]),
    ("rebased_kernel", ROOT / "penthouse/kernel_installation_socket/rebased_kernel",
                                                 [".py", ".json"]),
]


def _snapshot_index():
    snap = {}
    for label, base, exts in SNAPSHOT_GROUPS:
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            # Skip noise
            dirs[:] = [d for d in dirs if d not in
                        ("__pycache__", "node_modules", ".venv", ".git",
                         "vendor")]
            for fn in files:
                if not any(fn.endswith(e) for e in exts):
                    continue
                p = Path(root) / fn
                try:
                    stat = p.stat()
                except Exception:
                    continue
                rel = str(p.relative_to(ROOT))
                snap[rel] = {
                    "group": label,
                    "size_bytes": stat.st_size,
                    "modified_ts": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc).isoformat(),
                    "sha256": _sha256(p),
                }
    return snap


def capture_snapshot(stage="prechange"):
    """stage = 'prechange' | 'postchange'."""
    snap_index = _snapshot_index()
    cw = _load("qsb_canonical_workers.json", {})
    live = _load("qsb_dashboard_live_telemetry.json", {})
    floor44 = (ROOT / "floors/floor_44_future_systems_vacant").exists()
    payload = {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "kind": "eqsb_phase_" + stage + "_snapshot",
        "stage": stage,
        "generated_ts": _now(),
        "snapshot_id": stage + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "file_count": len(snap_index),
        "files": snap_index,
        "summary": {
            "canonical_workers": cw.get("total_canonical_workers"),
            "newly_employed":    cw.get("total_newly_employed_workers"),
            "live_telemetry_present": bool(live),
            "live_visual_mode":  live.get("dashboard_visual_mode"),
            "worker_movements_count":
                len(live.get("worker_movements") or []),
            "lift_movements_count":
                len(live.get("lift_movements") or []),
            "narrator_routes_present":
                bool(live.get("narrator_routes")),
            "scorecards_total":
                (live.get("workforce") or {}).get("scorecards_total"),
            "floor_44_vacant_dir_exists": floor44,
            "hardware_floor_registry_exists":
                (REG / "qsb_hardware_systems_floor.json").exists(),
        },
    }
    payload.update(_safety_envelope())
    out_path = P_PRE if stage == "prechange" else P_POST
    _write_json(out_path, payload)

    if stage == "prechange":
        with L_PRE.open("w", encoding="utf-8") as f:
            f.write("EQSB Phase Prechange Snapshot\n")
            f.write("=" * 40 + "\n")
            f.write("ts: " + payload["generated_ts"] + "\n")
            f.write("snapshot_id: " + payload["snapshot_id"] + "\n")
            f.write("file_count: " + str(payload["file_count"]) + "\n")
            for k, v in payload["summary"].items():
                f.write("  %-44s %s\n" % (k, v))
    _append_jsonl(L_LEDGER, {
        "event": "capture_snapshot", "stage": stage,
        "file_count": payload["file_count"],
        "snapshot_id": payload["snapshot_id"],
    })
    return payload


def compare_snapshots():
    """Compare prechange vs postchange snapshot to surface what Claude
    actually changed. Writes eqsb_phase_changes_latest.json."""
    pre = _load(P_PRE.name)
    post = _load(P_POST.name)
    if not pre or not post:
        return {"ok": False, "error": "snapshots_missing"}
    pre_files = pre.get("files") or {}
    post_files = post.get("files") or {}
    added = [p for p in post_files if p not in pre_files]
    deleted = [p for p in pre_files if p not in post_files]
    modified = [p for p in post_files
                 if p in pre_files and
                    pre_files[p].get("sha256") != post_files[p].get("sha256")]
    payload = {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "kind": "eqsb_phase_changes_latest",
        "generated_ts": _now(),
        "pre_snapshot_id":  pre.get("snapshot_id"),
        "post_snapshot_id": post.get("snapshot_id"),
        "files_created":   sorted(added),
        "files_modified":  sorted(modified),
        "files_deleted":   sorted(deleted),
        "counts": {"created": len(added), "modified": len(modified),
                    "deleted": len(deleted)},
    }
    payload.update(_safety_envelope())
    _write_json(P_CHANGES_LATEST, payload)
    return payload


# ── Section 2 — Code Observatory ───────────────────────────────────────

PY_DEF_RE = re.compile(r"^\s*(?:def|class)\s+(\w+)", re.MULTILINE)
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
EP_RE     = re.compile(r'path\s*==\s*["\']([^"\']+)["\']|'
                        r'path\.startswith\(\s*["\']([^"\']+)["\']')

CODE_AREAS = {
    "src/dashboard/server.py": "dashboard",
    "src/dashboard/static":    "dashboard_frontend",
    "src/tower/eqsb_":         "kernel_eqsb",
    "src/tower/kernel_":       "kernel_dialogue",
    "src/tower/qsb_paper":     "trading",
    "src/tower/qsb_openclaw":  "openclaw",
    "src/tower/qsb_workforce": "workforce",
    "src/tower/qsb_profit":    "profit_command",
    "src/tower/qsb_narrator":  "narrator",
    "src/tower/qsb_workers":   "workers",
    "src/tower/qsb_dashboard": "dashboard_backend",
    "src/tower/eqsb_observatory":"observatory",
    "scripts/":                "scripts",
    "floors/":                 "floors",
    "penthouse/":              "penthouse",
    "src/tower_ops/":          "tower_ops",
}


def _module_area(rel):
    for prefix, area in CODE_AREAS.items():
        if rel.startswith(prefix):
            return area
    if rel.endswith(".json"):
        return "registries"
    return "unknown"


def _py_summary(text):
    defs = PY_DEF_RE.findall(text or "")
    imports = sorted(set(IMPORT_RE.findall(text or "")))
    return {"top_defs": defs[:12], "imports": imports[:24]}


def _endpoints_in(text):
    out = set()
    if not text:
        return []
    for m in EP_RE.finditer(text):
        for grp in m.groups():
            if grp and grp.startswith("/api/"):
                out.add(grp)
    return sorted(out)[:80]


def _risk_flags_for(rel, text):
    flags = []
    if rel.endswith(".py") and text:
        if "Math.random" in text or " random." in text:
            # We accept random helpers in Python — flag only if hardware/code observatory writes
            if any(k in rel for k in ("observatory", "live_telemetry")):
                flags.append("random_in_observatory_code")
        if "subprocess" in text and "shell=True" in text:
            flags.append("subprocess_shell_true")
        if rel.endswith("cockpit.js") and len(text) > 100000:
            flags.append("very_large_file_above_100kb")
        if "TODO" in text or "FIXME" in text:
            flags.append("has_todo_or_fixme")
    return flags


def build_code_observatory():
    """Walk the curated tree. Sha256 + size + summary + endpoints + risk."""
    files = []
    by_area = {}
    risks = []
    deps = {}     # path -> [imports]
    owners = {}   # path -> owner_department
    for label, base, exts in SNAPSHOT_GROUPS:
        if not base.exists():
            continue
        for root, dirs, fnames in os.walk(base):
            dirs[:] = [d for d in dirs if d not in
                        ("__pycache__", "node_modules", ".venv",
                         ".git", "vendor")]
            for fn in fnames:
                if not any(fn.endswith(e) for e in exts):
                    continue
                p = Path(root) / fn
                rel = str(p.relative_to(ROOT))
                try:
                    stat = p.stat()
                except Exception:
                    continue
                text = None
                if stat.st_size < 200_000:
                    try:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        text = None
                area = _module_area(rel)
                rec = {
                    "path": rel,
                    "file_type": fn.rsplit(".", 1)[-1],
                    "module_area": area,
                    "size_bytes": stat.st_size,
                    "sha256": _sha256(p),
                    "modified_ts": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc).isoformat(),
                    "risk_flags": _risk_flags_for(rel, text or ""),
                    "owner_department": area,
                    "last_seen_phase":
                        "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
                }
                if fn.endswith(".py") and text is not None:
                    rec["python_summary"] = _py_summary(text)
                    deps[rel] = rec["python_summary"]["imports"]
                if fn.endswith(".py") and text is not None and "server" in rel:
                    rec["endpoints"] = _endpoints_in(text)
                if fn.endswith(".sh") and text is not None:
                    # script purpose: take the first non-shebang comment line
                    purp = ""
                    for line in text.splitlines()[:10]:
                        line = line.strip()
                        if line.startswith("#") and not line.startswith("#!"):
                            purp = line.lstrip("# ").strip()
                            if purp:
                                break
                    rec["script_purpose"] = purp[:160]
                if fn.endswith(".json") and text is not None:
                    rec["registry_purpose"] = "see kind/phase fields inside"
                if fn.endswith(".js") and text is not None:
                    rec["dashboard_component_summary"] = (
                        (text.splitlines()[1] if len(text.splitlines()) > 1 else "")
                        .lstrip("/ *").strip()[:160]
                    )
                if rec["risk_flags"]:
                    risks.append({"path": rel, "flags": rec["risk_flags"]})
                owners[rel] = area
                files.append(rec)
                by_area[area] = by_area.get(area, 0) + 1

    obs = {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "kind": "eqsb_code_observatory",
        "generated_ts": _now(),
        "total_files": len(files),
        "by_area_counts": by_area,
        "secret_safety": "No .env values copied. No tokens/passwords stored.",
        "fields_per_file": [
            "path", "file_type", "module_area", "size_bytes", "sha256",
            "modified_ts", "python_summary", "endpoints",
            "script_purpose", "registry_purpose",
            "dashboard_component_summary", "risk_flags",
            "owner_department", "last_seen_phase",
        ],
        "files": files,
    }
    obs.update(_safety_envelope())
    _write_json(P_CODE_OBS, obs)

    # code_map: compact path -> area lookup
    code_map = {
        "ok": True,
        "phase": obs["phase"],
        "kind": "eqsb_code_map",
        "generated_ts": _now(),
        "areas": sorted(by_area.keys()),
        "by_area": {a: [f["path"] for f in files if f["module_area"] == a]
                    for a in by_area},
        "by_area_counts": by_area,
    }
    code_map.update(_safety_envelope())
    _write_json(P_CODE_MAP, code_map)

    # code_risk_report
    risk_summary = {
        "ok": True,
        "kind": "eqsb_code_risk_report",
        "generated_ts": _now(),
        "phase": obs["phase"],
        "risk_file_count": len(risks),
        "risks": risks,
    }
    risk_summary.update(_safety_envelope())
    _write_json(P_CODE_RISK, risk_summary)

    # dependency_graph
    dep_payload = {
        "ok": True,
        "kind": "eqsb_code_dependency_graph",
        "generated_ts": _now(),
        "phase": obs["phase"],
        "edges_count": sum(len(v) for v in deps.values()),
        "dependencies": deps,
    }
    dep_payload.update(_safety_envelope())
    _write_json(P_CODE_DEPS, dep_payload)

    # ownership_map
    own_payload = {
        "ok": True,
        "kind": "eqsb_code_ownership_map",
        "generated_ts": _now(),
        "phase": obs["phase"],
        "owners": owners,
    }
    own_payload.update(_safety_envelope())
    _write_json(P_CODE_OWN, own_payload)

    _append_jsonl(L_CODE, {"event": "build_code_observatory",
                            "total_files": len(files),
                            "by_area_counts": by_area})
    return obs


# ── Section 3 — Hardware Observatory ───────────────────────────────────

def _cpu_profile():
    out_uname, _ = _safe_run(["uname", "-a"])
    out_lscpu, ok_lscpu = _safe_run(["lscpu"])
    loadavg = ""
    try:
        loadavg = Path("/proc/loadavg").read_text(encoding="utf-8").strip()
    except Exception:
        loadavg = ""
    # Parse a few well-known fields from lscpu
    fields = {}
    for line in (out_lscpu or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    payload = {
        "ok": True,
        "kind": "eqsb_cpu_profile",
        "generated_ts": _now(),
        "uname": out_uname,
        "model_name":   fields.get("Model name"),
        "vendor":       fields.get("Vendor ID"),
        "architecture": fields.get("Architecture"),
        "sockets":      fields.get("Socket(s)"),
        "cores_per_socket": fields.get("Core(s) per socket"),
        "threads_per_core": fields.get("Thread(s) per core"),
        "cpus":         fields.get("CPU(s)"),
        "max_mhz":      fields.get("CPU max MHz"),
        "min_mhz":      fields.get("CPU min MHz"),
        "loadavg":      loadavg,
        "raw_lscpu_present": ok_lscpu,
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_CPU, payload)
    return payload


def _gpu_profile():
    nvidia_smi = shutil.which("nvidia-smi")
    payload = {
        "ok": True,
        "kind": "eqsb_gpu_profile",
        "generated_ts": _now(),
        "nvidia_smi_present": bool(nvidia_smi),
        "nvidia_driver":        None,
        "cuda_version":         None,
        "cuda_available_python":False,
        "gpu_models":           [],
        "vram_mib":             [],
        "utilization_pct":      [],
        "temperature_c":        [],
        "suitability": {
            "dashboard_rendering":   "CPU-only OK; no GPU needed for SVG/Babylon on browser side.",
            "local_models_ollama":   "Adequate on CPU; small models (llama3.2:latest) run locally.",
            "airllm_advisory_chamber":"Needs separate VRAM if GPU present; AirLLM runs in its own venv.",
        },
    }
    if nvidia_smi:
        out, ok = _safe_run([nvidia_smi,
                              "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                              "--format=csv,noheader,nounits"], timeout=4)
        if ok:
            for line in (out or "").splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    payload["gpu_models"].append(parts[0])
                    payload["nvidia_driver"] = parts[1]
                    try:
                        payload["vram_mib"].append({
                            "total": int(parts[2]),
                            "used":  int(parts[3]),
                            "free":  int(parts[4]),
                        })
                        payload["utilization_pct"].append(int(parts[5]))
                        payload["temperature_c"].append(int(parts[6]))
                    except Exception:
                        pass
        # `cuda_version` isn't a query-gpu field. Pull it from
        # nvidia-smi's plain output header instead.
        ns_out, _ = _safe_run([nvidia_smi], timeout=3)
        for line in (ns_out or "").splitlines():
            m = re.search(r"CUDA Version:\s*([\d\.]+)", line)
            if m:
                payload["cuda_version"] = m.group(1)
                break
    # Detect CUDA in active Python env
    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if spec:
            try:
                import torch  # noqa: F401  -- only checked, not used at runtime
                payload["cuda_available_python"] = bool(torch.cuda.is_available())
            except Exception:
                payload["cuda_available_python"] = False
    except Exception:
        pass
    payload.update(_safety_envelope())
    _write_json(P_HW_GPU, payload)
    return payload


def _memory_profile():
    free_out, ok = _safe_run(["free", "-h"])
    bytes_out, _ = _safe_run(["free", "-b"])
    swap_used = None; mem_avail = None; mem_total = None
    for line in (bytes_out or "").splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            if len(parts) >= 7:
                try:
                    mem_total = int(parts[1])
                    mem_avail = int(parts[6])
                except Exception:
                    pass
        if line.lower().startswith("swap:"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    swap_used = int(parts[2])
                except Exception:
                    pass
    pressure = None
    if mem_total and mem_avail:
        used_pct = 100.0 * (mem_total - mem_avail) / mem_total
        if used_pct > 90:
            pressure = "high"
        elif used_pct > 75:
            pressure = "medium"
        else:
            pressure = "low"
    payload = {
        "ok": True, "kind": "eqsb_memory_profile",
        "generated_ts": _now(),
        "free_h":     free_out,
        "mem_total_bytes":     mem_total,
        "mem_available_bytes": mem_avail,
        "swap_used_bytes":     swap_used,
        "memory_pressure":     pressure,
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_MEM, payload)
    return payload


def _storage_profile():
    df_out, _ = _safe_run(["df", "-h", "/", "/vaults/nvme0", "/vaults/ai"])
    lsblk_out, _ = _safe_run(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE", "-J"], timeout=5)
    # Compute project sizes
    def _du_mb(path):
        if not Path(path).exists():
            return None
        try:
            out, ok = _safe_run(["du", "-sm", path], timeout=15)
            if ok and out:
                return int(out.split()[0])
        except Exception:
            pass
        return None
    payload = {
        "ok": True, "kind": "eqsb_storage_profile",
        "generated_ts": _now(),
        "df_h": df_out,
        "lsblk_json_present": bool(lsblk_out),
        "qsb_project_mb":      _du_mb(str(ROOT)),
        "qsb_data_mb":         _du_mb(str(ROOT / "data")),
        "qsb_data_backups_mb": _du_mb(str(ROOT / "data/backups")),
        "qsb_data_db_mb":      _du_mb(str(ROOT / "data/db")),
        "qsb_data_logs_mb":    _du_mb(str(ROOT / "data/logs")),
        "vaults_ai_present":   Path("/vaults/ai").exists(),
        "vaults_ai_airllm_lab_present": Path("/vaults/ai/airllm_lab").exists(),
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_DISK, payload)
    return payload


def _os_environment():
    payload = {
        "ok": True, "kind": "eqsb_os_environment",
        "generated_ts": _now(),
        "hostname":       (_safe_run(["hostname"])[0] or "").strip() or None,
        "uname_a":        (_safe_run(["uname", "-a"])[0] or "").strip() or None,
        "kernel_release": (_safe_run(["uname", "-r"])[0] or "").strip() or None,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "venv_active":     os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX"),
        "qsb_root":        str(ROOT),
        "ollama_present":  shutil.which("ollama") is not None,
    }
    # Best-effort pip summary
    pip_out, _ = _safe_run([sys.executable, "-m", "pip", "list", "--format=freeze"], timeout=6)
    if pip_out:
        pkgs = [line for line in pip_out.splitlines() if "==" in line][:60]
        payload["pip_top_60"] = pkgs
        payload["pip_total_lines"] = len(pip_out.splitlines())
    payload.update(_safety_envelope())
    _write_json(P_HW_OS, payload)
    return payload


def _services_profile():
    payload = {
        "ok": True, "kind": "eqsb_services_profile",
        "generated_ts": _now(),
    }
    # Dashboard process
    dash_pid = None
    pid_file = ROOT / "data/runtime/dashboard.pid"
    if pid_file.exists():
        try:
            dash_pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(dash_pid, 0)
            payload["dashboard_pid_running"] = True
        except Exception:
            dash_pid = None
            payload["dashboard_pid_running"] = False
    payload["dashboard_pid"] = dash_pid
    # Ollama detection (read-only)
    ollama_out, ok = _safe_run(["pgrep", "-fa", "ollama"], timeout=3)
    payload["ollama_processes"] = ollama_out.splitlines() if ok else []
    # AirLLM chamber path
    air = Path("/vaults/ai/airllm_lab/.venv")
    payload["airllm_venv_present"] = air.exists()
    payload.update(_safety_envelope())
    _write_json(P_HW_SVC, payload)
    return payload


def _ports_profile():
    payload = {
        "ok": True, "kind": "eqsb_ports_profile",
        "generated_ts": _now(),
        "listening": [],
    }
    out, ok = _safe_run(["ss", "-ltn"], timeout=3)
    if ok:
        # First line is header
        lines = out.splitlines()[1:]
        for line in lines[:30]:
            payload["listening"].append(line.strip())
    payload.update(_safety_envelope())
    _write_json(P_HW_PORTS, payload)
    return payload


def _model_lane_hardware(cpu, gpu, mem):
    payload = {
        "ok": True, "kind": "eqsb_model_lane_hardware_profile",
        "generated_ts": _now(),
        "lanes": [
            {"lane_id": "lane_local_ollama",
             "supports_local_inference": True,
             "needs_gpu_for_acceptable_latency": False,
             "comment": "llama3.2:latest runs comfortably on CPU."},
            {"lane_id": "lane_local_llama",
             "supports_local_inference": True,
             "needs_gpu_for_acceptable_latency": (not gpu.get("nvidia_smi_present")),
             "comment": "Bigger Llama variants benefit from GPU VRAM."},
            {"lane_id": "lane_airllm_chamber",
             "supports_local_inference": False,
             "isolation": "/vaults/ai/airllm_lab/.venv",
             "comment": "AirLLM advisory chamber, isolated venv. Advisory only."},
            {"lane_id": "lane_future_locked_provider",
             "supports_local_inference": False,
             "comment": "External provider lane — remains locked."},
        ],
        "gpu_available": bool(gpu.get("nvidia_smi_present")),
        "cuda_available_python": bool(gpu.get("cuda_available_python")),
        "memory_pressure": mem.get("memory_pressure"),
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_LANES, payload)
    return payload


def _hardware_understanding(cpu, gpu, mem, disk, osinfo, svc, ports):
    payload = {
        "ok": True, "kind": "eqsb_hardware_understanding",
        "generated_ts": _now(),
        "summary": {
            "cpu_model":   cpu.get("model_name"),
            "cpu_cores":   cpu.get("cores_per_socket"),
            "cpu_threads": cpu.get("cpus"),
            "gpu_models":  gpu.get("gpu_models"),
            "cuda_version":gpu.get("cuda_version"),
            "cuda_available_python": gpu.get("cuda_available_python"),
            "mem_total_bytes": mem.get("mem_total_bytes"),
            "memory_pressure": mem.get("memory_pressure"),
            "qsb_project_mb":  disk.get("qsb_project_mb"),
            "qsb_data_logs_mb": disk.get("qsb_data_logs_mb"),
            "vaults_ai_present": disk.get("vaults_ai_present"),
            "vaults_ai_airllm_lab_present": disk.get("vaults_ai_airllm_lab_present"),
            "hostname": osinfo.get("hostname"),
            "kernel_release": osinfo.get("kernel_release"),
            "python_version": osinfo.get("python_version"),
            "dashboard_pid_running": svc.get("dashboard_pid_running"),
            "ollama_present": osinfo.get("ollama_present"),
            "ollama_processes_count": len(svc.get("ollama_processes") or []),
            "airllm_venv_present": svc.get("airllm_venv_present"),
            "listening_ports_count": len(ports.get("listening") or []),
        },
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_UND, payload)
    return payload


def _performance_advice(cpu, gpu, mem, disk):
    advice = []
    pressure = mem.get("memory_pressure")
    if pressure == "high":
        advice.append("Memory pressure HIGH — consider closing big browser tabs or rebooting AirLLM venv before opening Babylon 3D scene.")
    elif pressure == "medium":
        advice.append("Memory pressure MEDIUM — fine for SVG renderer; close idle apps before AirLLM advisory work.")
    if not gpu.get("nvidia_smi_present"):
        advice.append("No NVIDIA GPU detected — keep heavy AirLLM models offline; rely on small local Ollama models.")
    elif gpu.get("vram_mib"):
        free_mib = sum(v.get("free", 0) for v in gpu["vram_mib"])
        if free_mib < 4096:
            advice.append("Less than 4 GiB VRAM free — avoid concurrent Ollama + AirLLM loads.")
    if (disk.get("qsb_data_logs_mb") or 0) > 500:
        advice.append("data/logs exceeds 500 MiB — rotate or archive jsonl tails to keep dashboard reads fast.")
    if (disk.get("qsb_data_backups_mb") or 0) > 1024:
        advice.append("Dashboard backups exceed 1 GiB — prune old backup folders periodically.")
    if not advice:
        advice.append("System looks healthy at the moment. Maintain current cadence.")
    payload = {
        "ok": True, "kind": "eqsb_performance_advice",
        "generated_ts": _now(),
        "advice": advice,
        "advisory_only": True,
        "execution_allowed": False,
        "may_modify_system": False,
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_ADV, payload)
    return payload


def build_hardware_observatory():
    cpu = _cpu_profile()
    gpu = _gpu_profile()
    mem = _memory_profile()
    disk = _storage_profile()
    osinfo = _os_environment()
    svc = _services_profile()
    ports = _ports_profile()
    lanes = _model_lane_hardware(cpu, gpu, mem)
    und = _hardware_understanding(cpu, gpu, mem, disk, osinfo, svc, ports)
    adv = _performance_advice(cpu, gpu, mem, disk)
    payload = {
        "ok": True,
        "kind": "eqsb_hardware_observatory",
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "generated_ts": _now(),
        "cpu_summary":  cpu.get("model_name"),
        "gpu_summary":  ", ".join(gpu.get("gpu_models") or []) or "no_nvidia_gpu",
        "memory_pressure": mem.get("memory_pressure"),
        "qsb_data_mb": disk.get("qsb_data_mb"),
        "ollama_present": osinfo.get("ollama_present"),
        "airllm_venv_present": svc.get("airllm_venv_present"),
        "advice_count": len(adv.get("advice") or []),
        "read_only_commands_used": [
            "uname", "hostname", "lscpu", "free", "df", "lsblk",
            "nvidia-smi (if present)", "ss", "ps/pgrep", "du",
        ],
    }
    payload.update(_safety_envelope())
    _write_json(P_HW_OBS, payload)
    _append_jsonl(L_HW, {"event": "build_hardware_observatory",
                           "cpu_summary": payload["cpu_summary"],
                           "memory_pressure": payload["memory_pressure"]})
    return payload


# ── Section 4 — Claude Upgrade Ledger / Phase History ──────────────────

PHASE_RECORD_FIELDS = (
    "phase_name", "timestamp", "before_snapshot_id", "after_snapshot_id",
    "files_created", "files_modified", "files_deleted",
    "registries_created", "registries_modified",
    "endpoints_added", "scripts_added", "dashboard_files_changed",
    "compile_results", "validation_results",
    "dashboard_health_result", "kernel_chat_result",
    "risks_introduced", "lessons_learned", "rollback_point",
    "next_recommended_review",
)


KNOWN_PHASES = [
    {
        "phase_name": "EQSB_KERNEL_MAJOR_DEEP_SYMBOLIC_QUANTUM_CORE_V1",
        "summary": "Built 16-layer EQSB Kernel architecture (axioms, Guardian, cadence, memory, beliefs, symbols, graph, entropy, quantum, hypotheses, contradictions, model governance, introspection, replay ledger, self-audit)."
    },
    {
        "phase_name": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "summary": "Activated OpenClaw supervision limb (visual+sandbox+trade-supervision+ticketing), built paper-trade lifecycle SQLite + open/close/PnL/learning, 19 V2 workers, V2 right-rail panel + HUD."
    },
    {
        "phase_name": "QSB_V2_FULL_SYSTEM_RECHECK_AND_DASHBOARD_REPAIR_V1",
        "summary": "Reverted random #qsbTower2D background, defensive try/catch wrappers on V2 scripts, dashboard health-check + start scripts."
    },
    {
        "phase_name": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2",
        "summary": "Eliminated random orbits + random lifts; deterministic anchored workers; LIVE_DATA_ONLY mode; /api/dashboard/live_telemetry; 16 V3 dashboard workers; V3 panel + 'no live data' badges."
    },
    {
        "phase_name": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "summary": "Profit Command + Workforce HR (scorecards/rewards/discipline/promotions) + Running Commentary narrator (/api/narrator/*) + Floor 44 placeholder + Command Center audit/decision."
    },
    {
        "phase_name": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "summary": "Hardware Systems Floor + Code Observatory + Hardware Observatory + Claude Upgrade Ledger + System Understanding Graph + Telemetry Repairs A-H."
    },
]


def build_phase_history():
    # If a prior history exists, keep it and append. Idempotent on name.
    prior = _load(P_HIST.name, {"phases": []})
    existing_names = {p.get("phase_name") for p in (prior.get("phases") or [])}
    phases = list(prior.get("phases") or [])
    changes = _load(P_CHANGES_LATEST.name, {})
    pre = _load(P_PRE.name, {})
    post = _load(P_POST.name, {})
    for kp in KNOWN_PHASES:
        if kp["phase_name"] in existing_names:
            continue
        rec = {
            "phase_name": kp["phase_name"],
            "summary": kp["summary"],
            "timestamp": _now(),
            "files_created":  [],
            "files_modified": [],
            "files_deleted":  [],
            "endpoints_added": [],
            "scripts_added":  [],
            "lessons_learned": [],
            "rollback_point": None,
        }
        # Decorate the CURRENT phase with measured changes if available
        if kp["phase_name"] == "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1":
            rec["before_snapshot_id"] = pre.get("snapshot_id")
            rec["after_snapshot_id"]  = post.get("snapshot_id")
            rec["files_created"]  = changes.get("files_created")  or []
            rec["files_modified"] = changes.get("files_modified") or []
            rec["files_deleted"]  = changes.get("files_deleted")  or []
        phases.append(rec)
    payload = {
        "ok": True,
        "kind": "eqsb_phase_history",
        "generated_ts": _now(),
        "phase_count": len(phases),
        "phases": phases,
    }
    payload.update(_safety_envelope())
    _write_json(P_HIST, payload)
    return payload


def build_claude_upgrade_ledger():
    history = build_phase_history()
    last = next((p for p in reversed(history["phases"])
                  if p["phase_name"] ==
                  "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1"),
                 history["phases"][-1] if history["phases"] else None)
    ledger = {
        "ok": True,
        "kind": "eqsb_claude_upgrade_ledger",
        "generated_ts": _now(),
        "phase_count": history["phase_count"],
        "latest_phase": last["phase_name"] if last else None,
        "latest_summary": last.get("summary") if last else None,
        "latest_files_created":  last.get("files_created", []) if last else [],
        "latest_files_modified": last.get("files_modified", []) if last else [],
        "fields_per_phase_record": list(PHASE_RECORD_FIELDS),
        "phase_history_link": str(P_HIST.relative_to(ROOT)),
    }
    ledger.update(_safety_envelope())
    _write_json(P_LEDGER, ledger)

    last_change = {
        "ok": True, "kind": "eqsb_last_claude_change_summary",
        "generated_ts": _now(),
        "phase": last["phase_name"] if last else None,
        "summary": last.get("summary") if last else None,
        "files_created":  (last.get("files_created") or []),
        "files_modified": (last.get("files_modified") or []),
        "files_deleted":  (last.get("files_deleted")  or []),
    }
    last_change.update(_safety_envelope())
    _write_json(P_LAST_CHANGE, last_change)

    # Risk history — derived from code_risk_report + named lessons
    risk_report = _load(P_CODE_RISK.name, {})
    risks_payload = {
        "ok": True, "kind": "eqsb_upgrade_risk_history",
        "generated_ts": _now(),
        "current_risk_file_count": risk_report.get("risk_file_count"),
        "current_risks": risk_report.get("risks") or [],
        "lessons_so_far": [
            "Random animations were eliminated in V3; visual contract is LIVE_DATA_ONLY.",
            "Worker counts mismatched because no canonical registry existed pre-V2.",
            "Floor 44 Accounts/PnL needed a real manifest — added by this phase.",
            "Discipline strikes are reserved for rule violations, never paper losses.",
            "Hardware observatory is read-only; recommendations require operator approval.",
            "Browser SpeechSynthesis handles narration — no server-side TTS dependency.",
        ],
    }
    risks_payload.update(_safety_envelope())
    _write_json(P_RISKS, risks_payload)

    _append_jsonl(L_LEDGER, {
        "event": "build_claude_upgrade_ledger",
        "phase_count": history["phase_count"],
        "latest_phase": last["phase_name"] if last else None,
    })
    return ledger


# ── Section 5 — System Understanding Graph + Learning Loop + Patches ───

def build_system_understanding_graph():
    hw = _load(P_HW_UND.name, {})
    code = _load(P_CODE_MAP.name, {})
    cw = _load("qsb_canonical_workers.json", {})
    nodes = []
    edges = []

    # Hardware nodes
    nodes.append({"id": "hardware_floor", "kind": "hardware_floor",
                   "label": "Hardware Systems Floor"})
    nodes.append({"id": "cpu", "kind": "cpu",
                   "label": hw.get("summary", {}).get("cpu_model") or "CPU"})
    nodes.append({"id": "gpu", "kind": "gpu",
                   "label": ", ".join(hw.get("summary", {}).get("gpu_models") or ["no_gpu"])})
    nodes.append({"id": "ram", "kind": "ram",
                   "label": "RAM " + str(hw.get("summary", {}).get("memory_pressure") or "—")})
    nodes.append({"id": "qsb_project_storage", "kind": "disk_mount",
                   "label": "/vaults/nvme0/qsb_tower_v1"})
    nodes.append({"id": "vaults_ai_storage", "kind": "disk_mount",
                   "label": "/vaults/ai"})
    edges.append({"source": "hardware_floor", "relation": "hardware_floor_observes_cpu", "target": "cpu"})
    edges.append({"source": "hardware_floor", "relation": "hardware_floor_observes_gpu", "target": "gpu"})
    edges.append({"source": "hardware_floor", "relation": "hardware_floor_observes_ram", "target": "ram"})
    edges.append({"source": "hardware_floor", "relation": "hardware_floor_observes_storage", "target": "qsb_project_storage"})
    edges.append({"source": "hardware_floor", "relation": "hardware_floor_observes_storage", "target": "vaults_ai_storage"})

    # Dashboard / kernel components
    for cname, kind in [
        ("dashboard_server",       "dashboard_component"),
        ("dashboard_static",       "dashboard_component"),
        ("kernel_dialogue_adapter","kernel_component"),
        ("eqsb_kernel_core_ext",   "kernel_component"),
        ("eqsb_introspection",     "kernel_component"),
        ("openclaw_supervision",   "openclaw_component"),
        ("qsb_paper_trading",      "trading_component"),
        ("qsb_workforce",          "worker_component"),
        ("qsb_profit_command",     "worker_component"),
        ("qsb_narrator",           "kernel_component"),
        ("qsb_dashboard_live_telemetry", "dashboard_component"),
    ]:
        nodes.append({"id": cname, "kind": kind, "label": cname})
        edges.append({"source": "hardware_floor",
                       "relation": "hardware_supports_dashboard",
                       "target": cname})

    # Model lanes
    for lane in ["lane_local_ollama", "lane_local_llama",
                  "lane_airllm_chamber", "lane_future_locked_provider"]:
        nodes.append({"id": lane, "kind": "model_lane", "label": lane})
        edges.append({"source": "hardware_floor",
                       "relation": "hardware_supports_model_lane",
                       "target": lane})
    if "gpu" in {n["id"] for n in nodes}:
        edges.append({"source": "gpu", "relation": "GPU_supports_local_model",
                       "target": "lane_local_ollama"})
        edges.append({"source": "gpu", "relation": "GPU_supports_local_model",
                       "target": "lane_local_llama"})
    edges.append({"source": "ram", "relation": "RAM_limits_model_lane",
                   "target": "lane_airllm_chamber"})
    edges.append({"source": "vaults_ai_storage", "relation": "storage_supports_airllm",
                   "target": "lane_airllm_chamber"})

    # Add Claude phases
    hist = _load(P_HIST.name, {})
    for p in (hist.get("phases") or []):
        pid = "phase_" + p["phase_name"][:48]
        nodes.append({"id": pid, "kind": "claude_phase",
                       "label": p["phase_name"]})
        for f in (p.get("files_modified") or [])[:6]:
            fid = "file_" + f[:60]
            nodes.append({"id": fid, "kind": "source_file", "label": f})
            edges.append({"source": pid, "relation": "Claude_phase_modified_file", "target": fid})

    # Compact dedupe
    seen = set()
    uniq_nodes = []
    for n in nodes:
        if n["id"] not in seen:
            uniq_nodes.append(n); seen.add(n["id"])

    payload = {
        "ok": True, "kind": "eqsb_system_understanding_graph",
        "generated_ts": _now(),
        "node_count": len(uniq_nodes),
        "edge_count": len(edges),
        "node_kinds": sorted({n["kind"] for n in uniq_nodes}),
        "relations_in_use": sorted({e["relation"] for e in edges}),
        "nodes": uniq_nodes,
        "edges": edges,
    }
    payload.update(_safety_envelope())
    _write_json(P_GRAPH, payload)
    return payload


def build_learning_loop():
    payload = {
        "ok": True, "kind": "eqsb_kernel_learning_loop",
        "generated_ts": _now(),
        "loop": [
            "capture_prechange_snapshot",
            "claude_performs_upgrade",
            "capture_postchange_snapshot",
            "compare_changes",
            "update_code_observatory",
            "update_hardware_observatory_if_relevant",
            "update_system_understanding_graph",
            "record_risks",
            "record_lessons_learned",
            "update_kernel_introspection",
            "recommend_next_review",
        ],
        "learn_from": [
            "files_changed", "tests_passed_failed",
            "dashboard_broken_fixed", "endpoints_added",
            "scripts_added", "registries_changed",
            "worker_counts_changed", "performance_changed",
            "hardware_pressure_changed", "user_feedback",
        ],
    }
    payload.update(_safety_envelope())
    _write_json(P_LOOP, payload)

    lessons = {
        "ok": True, "kind": "eqsb_kernel_lessons_learned",
        "generated_ts": _now(),
        "lessons": [
            "Visuals must be data-driven (LIVE_DATA_ONLY) — random orbits looked alive but lied.",
            "Hire one canonical workforce registry before letting subsystems publish counts.",
            "Add try/catch around every dashboard fetch — one panel must not break the cockpit.",
            "Idempotent reconcilers + start scripts pay back fast.",
            "Hardware observation is advisory; never modify drivers/services.",
            "Browser SpeechSynthesis is enough — no server-side TTS dependency.",
            "Strikes punish discipline violations, not paper losses.",
            "Always capture a pre-change snapshot so phase diffs are explicit.",
        ],
    }
    lessons.update(_safety_envelope())
    _write_json(P_LESSONS, lessons)
    _append_jsonl(L_LOOP, {"event": "build_learning_loop",
                            "loop_steps": len(payload["loop"]),
                            "lessons_count": len(lessons["lessons"])})
    return payload


def build_code_assistance_policy():
    payload = {
        "ok": True, "kind": "eqsb_code_assistance_policy",
        "generated_ts": _now(),
        "may_propose": [
            "patch plans", "refactor plans", "risk reviews",
            "file ownership maps", "dashboard fix plans",
            "test plans", "rollback plans", "optimization plans",
        ],
        "may_not_directly_overwrite_code": True,
        "execution_allowed": False,
        "requires_human_approval_for_all_writes": True,
    }
    payload.update(_safety_envelope())
    _write_json(P_CODE_AP, payload)

    proposals = {
        "ok": True, "kind": "eqsb_code_patch_proposals",
        "generated_ts": _now(),
        "proposals": [
            {
                "proposal_id": "patch_001",
                "problem": "cockpit.js is 2700+ LOC and dense — refactor risk grows with each phase.",
                "affected_files": ["src/dashboard/static/cockpit.js"],
                "suggested_changes": "Extract per-tab panel renderers (kernel/locks/strategy/oanda/binance/...) into dedicated files; cockpit.js orchestrates only.",
                "expected_benefit": "Lower regression risk, faster reviews.",
                "risks": ["Module load order matters; risk of breaking existing tabs."],
                "validation_steps": ["frontend health check", "tab smoke-click on each section"],
                "rollback_plan": "Restore cockpit.js from data/backups/dashboard_rebuild_<ts>/.",
                "requires_human_approval": True,
                "execution_allowed": False,
            },
            {
                "proposal_id": "patch_002",
                "problem": "Logs directory grows unbounded.",
                "affected_files": ["data/logs/*.jsonl"],
                "suggested_changes": "Add a daily log rotator (logrotate config) capped at 30 days.",
                "expected_benefit": "Faster dashboard reads; predictable disk usage.",
                "risks": ["Lose long-tail history if rotated too aggressively."],
                "validation_steps": ["spot-check log sizes after rotation", "verify ledger registries still resolve"],
                "rollback_plan": "Disable rotation; restore from backups.",
                "requires_human_approval": True,
                "execution_allowed": False,
            },
        ],
    }
    proposals.update(_safety_envelope())
    _write_json(P_PATCHES, proposals)
    return payload


# ── Orchestrator ───────────────────────────────────────────────────────

def build_all(stage="postchange"):
    """Build everything except the post-change snapshot (which we capture
    AFTER edits in the canonical script flow)."""
    if stage == "prechange":
        capture_snapshot("prechange")
    build_code_observatory()
    build_hardware_observatory()
    build_phase_history()
    build_claude_upgrade_ledger()
    build_system_understanding_graph()
    build_learning_loop()
    build_code_assistance_policy()
    if stage == "postchange":
        capture_snapshot("postchange")
        compare_snapshots()
        # Re-run ledger to pull in the change diff
        build_phase_history()
        build_claude_upgrade_ledger()
    return {
        "ok": True,
        "phase": "EQSB_SYSTEM_OBSERVATORY_HARDWARE_FLOOR_LIVE_TELEMETRY_REPAIR_V1",
        "code_observatory": "rebuilt",
        "hardware_observatory": "rebuilt",
        "phase_history": "rebuilt",
        "claude_upgrade_ledger": "rebuilt",
        "system_understanding_graph": "rebuilt",
        "kernel_learning_loop": "rebuilt",
        "code_assistance_policy": "rebuilt",
        **_safety_envelope(),
    }


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if cmd == "prechange":
        print(json.dumps(capture_snapshot("prechange"), indent=2))
    elif cmd == "postchange":
        print(json.dumps(capture_snapshot("postchange"), indent=2))
    elif cmd == "compare":
        print(json.dumps(compare_snapshots(), indent=2))
    elif cmd == "code":
        out = build_code_observatory()
        print(json.dumps({"total_files": out["total_files"],
                          "by_area_counts": out["by_area_counts"]}, indent=2))
    elif cmd == "hardware":
        print(json.dumps(build_hardware_observatory(), indent=2))
    elif cmd == "ledger":
        print(json.dumps(build_claude_upgrade_ledger(), indent=2))
    elif cmd == "graph":
        out = build_system_understanding_graph()
        print(json.dumps({"node_count": out["node_count"],
                          "edge_count": out["edge_count"]}, indent=2))
    elif cmd == "learning":
        print(json.dumps(build_learning_loop(), indent=2))
    elif cmd == "patches":
        print(json.dumps(build_code_assistance_policy(), indent=2))
    elif cmd == "all":
        print(json.dumps(build_all("postchange"), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "valid": ["prechange", "postchange", "compare",
                                     "code", "hardware", "ledger", "graph",
                                     "learning", "patches", "all"]},
                         indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
