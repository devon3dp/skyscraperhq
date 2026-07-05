#!/usr/bin/env bash
# QSB Tower V1 — Read-only kernel core recursion reproduction.
# Imports kernel.kernel_core exactly the way tower.kernel_dialogue_adapter does,
# tries to instantiate QSBKernelCore inside a guarded try/except, and reports
# whether the underlying constructor recurses.
#
# This script is READ ONLY:
#   - never writes any project file
#   - never enables execution
#   - never calls any external provider
#   - never opens a new port or sidecar
set -u
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

python3 - <<'PY'
import importlib
import inspect
import json
import sys
import traceback
from datetime import datetime, timezone

REB_BASE = "/vaults/nvme0/qsb_tower_v1/penthouse/kernel_installation_socket/rebased_kernel"

report = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "phase": "QSB_KERNEL_CORE_RECURSION_FIX_V1",
    "read_only": True,
    "execution_allowed": False,
    "rebased_kernel_base": REB_BASE,
}

# 1) Same import path the adapter uses.
sys.path.insert(0, REB_BASE)
try:
    mod = importlib.import_module("kernel.kernel_core")
    report["import_module"] = "kernel.kernel_core"
    report["import_path"]   = getattr(mod, "__file__", "<no __file__>")
    report["import_ok"]     = True
except Exception as exc:
    report["import_ok"]     = False
    report["import_error"]  = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    print(json.dumps(report, indent=2))
    sys.exit(0)

# 2) Resolve the class.
cls = getattr(mod, "QSBKernelCore", None)
if cls is None:
    report["class_resolved"] = None
    print(json.dumps(report, indent=2))
    sys.exit(0)
report["class_resolved"] = "%s.%s" % (cls.__module__, cls.__name__)
try:
    src_file = inspect.getsourcefile(cls)
    src_line = inspect.getsourcelines(cls)[1]
    report["class_source_file"] = src_file
    report["class_source_line"] = src_line
except Exception:
    pass

# 3) Try to instantiate inside a guarded try/except. Keep the recursion limit
#    relatively low so the trace is short and the stack is comprehensible.
default_limit = sys.getrecursionlimit()
sys.setrecursionlimit(120)
try:
    instance = cls()
    report["instantiation_ok"] = True
    report["instance_class"]   = type(instance).__name__
    # Probe for the introspection methods we care about.
    report["has_status"]       = callable(getattr(instance, "status", None))
    report["has_analyze"]      = callable(getattr(instance, "analyze", None))
    if report["has_status"]:
        try:
            s = instance.status()
            # Just record the keys + types so we don't dump megabytes.
            report["status_keys"] = sorted(list((s or {}).keys()))
        except Exception as exc:
            report["status_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    if report["has_analyze"]:
        try:
            a = instance.analyze("list floor 30 locks")
            report["analyze_keys"] = sorted(list((a or {}).keys()))
        except Exception as exc:
            report["analyze_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
except RecursionError as exc:
    report["instantiation_ok"]  = False
    report["recursion_error"]   = "RecursionError: %s" % (str(exc)[:160] or "max depth")
    # The stack at the point we ran out of frames — first/last few entries
    # are usually enough to fingerprint the offending pair of frames.
    tb = traceback.extract_tb(exc.__traceback__)
    summary = []
    seen_pairs = {}
    for fr in tb:
        summary.append({
            "file":  fr.filename,
            "line":  fr.lineno,
            "func":  fr.name,
        })
        key = (fr.filename, fr.name)
        seen_pairs[key] = seen_pairs.get(key, 0) + 1
    # Keep first 6 + last 12 frames so the top of the recursion is visible.
    report["stack_total_frames"] = len(summary)
    report["stack_head"] = summary[:6]
    report["stack_tail"] = summary[-12:]
    # Show which (file, function) pair repeated the most — the recursion cycle.
    repeated = sorted(seen_pairs.items(), key=lambda kv: -kv[1])[:6]
    report["repeating_frames"] = [{
        "file": k[0], "func": k[1], "count": v,
    } for k, v in repeated]
except Exception as exc:
    report["instantiation_ok"] = False
    report["construction_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    tb = traceback.extract_tb(exc.__traceback__)
    report["stack_tail"] = [{
        "file": fr.filename, "line": fr.lineno, "func": fr.name,
    } for fr in tb[-12:]]
finally:
    sys.setrecursionlimit(default_limit)

print(json.dumps(report, indent=2))
PY
