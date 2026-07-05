#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib
import inspect
import json
import sys

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
REB_BASE = ROOT / "penthouse/kernel_installation_socket/rebased_kernel"
REB_KERNEL = REB_BASE / "kernel"
LOG = ROOT / "data/logs/kernel_talk.jsonl"

FORBIDDEN_ACTIVE_PATHS = [
    ROOT / "penthouse/kernel.py",
    ROOT / "penthouse/qsb_kernel_4_5.py",
    ROOT / "src/tower/kernel.py",
    ROOT / "src/tower/qsb_kernel_4_5.py",
]

DANGEROUS_FLAGS = [
    "worker_execution_enabled",
    "provider_execution_enabled",
    "model_inference_enabled",
    "live_dispatch_enabled",
    "autonomous_workers_enabled",
    "direct_provider_access",
]

MESSAGE_METHODS = [
    "talk",
    "chat",
    "ask",
    "respond",
    "reply",
    "process_message",
    "handle_message",
    "query",
    "reflect",
    "process",
]

STATUS_METHODS = [
    "dashboard",
    "status",
    "summary",
    "health",
]


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def safety_check():
    report = load_json(REG / "kernel_activation_report.json", {})

    required = {
        "kernel_installed": True,
        "QSBKernelCore_instantiated": True,
        "active_kernel_source": "rebased_kernel",
        "activation_status": "active_local_only",
    }

    failures = []
    for key, expected in required.items():
        if report.get(key) != expected:
            failures.append(f"{key}={report.get(key)!r}, expected {expected!r}")

    for key in DANGEROUS_FLAGS:
        if report.get(key) is not False:
            failures.append(f"{key} must remain false")

    for path in FORBIDDEN_ACTIVE_PATHS:
        if path.exists():
            failures.append(f"forbidden active path exists: {path}")

    if not REB_KERNEL.exists():
        failures.append(f"rebased kernel folder missing: {REB_KERNEL}")

    if failures:
        return False, failures, report

    return True, [], report


def load_kernel():
    sys.path.insert(0, str(REB_BASE))
    mod = importlib.import_module("kernel.kernel_core")
    cls = getattr(mod, "QSBKernelCore")
    obj = cls()
    return obj


def call_method(obj, method_name, message):
    fn = getattr(obj, method_name)
    sig = inspect.signature(fn)

    params = [
        p for p in sig.parameters.values()
        if p.default is inspect._empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]

    if len(params) == 0:
        return fn()

    return fn(message)


def kernel_reply(message):
    ok, failures, report = safety_check()
    if not ok:
        return {
            "ok": False,
            "error": "Kernel talk bridge blocked by safety check.",
            "failures": failures,
        }

    obj = load_kernel()

    public_callables = [
        name for name in dir(obj)
        if not name.startswith("_") and callable(getattr(obj, name, None))
    ]

    for name in MESSAGE_METHODS:
        if name in public_callables:
            try:
                result = call_method(obj, name, message)
                return {
                    "ok": True,
                    "bridge": "kernel_talk_bridge",
                    "method_used": name,
                    "message": message,
                    "reply": result,
                    "kernel_status": {
                        "kernel_installed": True,
                        "activation_status": "active_local_only",
                        "active_kernel_source": "rebased_kernel",
                        "workers_enabled": False,
                        "providers_enabled": False,
                        "model_inference_enabled": False,
                    },
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "bridge": "kernel_talk_bridge",
                    "method_attempted": name,
                    "error": str(exc),
                    "public_methods": public_callables,
                }

    for name in STATUS_METHODS:
        if name in public_callables:
            try:
                result = call_method(obj, name, message)
                return {
                    "ok": True,
                    "bridge": "kernel_talk_bridge",
                    "mode": "status_method_only",
                    "method_used": name,
                    "message": message,
                    "reply": result,
                    "note": "Kernel is active, but no direct chat/talk method is exposed yet.",
                    "public_methods": public_callables,
                }
            except Exception:
                pass

    return {
        "ok": True,
        "bridge": "kernel_talk_bridge",
        "mode": "active_kernel_no_chat_method_yet",
        "message": message,
        "reply": "Kernel is active local-only. No direct conversational method is exposed yet. Next step: add a kernel dialogue method or dashboard chat adapter.",
        "public_methods": public_callables,
        "kernel_status": {
            "kernel_installed": True,
            "QSBKernelCore_instantiated": True,
            "activation_status": "active_local_only",
            "active_kernel_source": "rebased_kernel",
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "model_inference_enabled": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Talk to active local-only QSB Kernel.")
    parser.add_argument("message", nargs="*", help="Message to send to the active local-only kernel.")
    parser.add_argument("--inspect", action="store_true", help="Inspect available public kernel methods.")
    args = parser.parse_args()

    ok, failures, report = safety_check()
    if not ok:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        raise SystemExit(1)

    if args.inspect:
        obj = load_kernel()
        methods = [
            name for name in dir(obj)
            if not name.startswith("_") and callable(getattr(obj, name, None))
        ]
        print(json.dumps({
            "ok": True,
            "kernel_active": True,
            "activation_status": report.get("activation_status"),
            "active_kernel_source": report.get("active_kernel_source"),
            "public_methods": methods,
        }, indent=2))
        return

    message = " ".join(args.message).strip()
    if not message:
        message = input("QSB Kernel > ").strip()

    result = kernel_reply(message)
    result["ts"] = datetime.now(timezone.utc).isoformat()
    append_log(result)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
