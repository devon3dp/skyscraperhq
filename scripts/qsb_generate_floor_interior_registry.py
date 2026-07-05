#!/usr/bin/env python3
"""Generate qsb_floor_interior_master_registry.json with entries for F01..F55."""
from __future__ import annotations
import json, os, datetime, sys

ROOT = os.environ.get("QSB_ROOT", "/vaults/nvme0/qsb_tower_v1")
OUT = os.path.join(ROOT, "data/registries/qsb_floor_interior_master_registry.json")

# Specialized floor table — name, template, rooms (>=8 for special / >=10 for F55),
# worker count, openclaw_presence
SPECIAL: dict[int, dict] = {
    55: {
        "floor_name": "Penthouse / Kernel",
        "department": "Kernel",
        "template": "KernelPenthouseInterior",
        "rooms": [
            "Kernel Chamber", "Cognitive Status Desk", "Guardian Lock Console",
            "OpenClaw Command Rail", "Registry Wall", "Model Lane Gallery",
            "Memory Board", "Attention Board", "Reflection Board", "Kernel Chat Terminal",
        ],
        "worker_count": 8, "openclaw_presence": True,
        "manager": "Kernel (advisory)",
        "seer": "Cognitive Seer",
        "overseer": "Penthouse Overseer",
        "watcher": "OpenClaw Watcher",
    },
    41: {
        "floor_name": "OANDA Trading Floor",
        "department": "Trading · OANDA Paper",
        "template": "TradingFloorInterior",
        "rooms": [
            "OANDA Desk", "Spread Watcher Station", "Risk Console",
            "Paper Order Simulator", "Ledger Board", "Strategy Desk",
            "Worker Analyst Pods", "OpenClaw Risk Inspection Lane",
        ],
        "worker_count": 48, "openclaw_presence": True,
        "manager": "Floor Lead · OANDA",
        "seer": "Spread Seer", "overseer": "Trading Overseer",
        "watcher": "OpenClaw Watcher",
    },
    42: {
        "floor_name": "Binance (testnet preview)",
        "department": "Trading · Binance Testnet",
        "template": "TradingFloorInterior",
        "rooms": [
            "Testnet Market Screen", "Risk Console", "Paper Signal Desk",
            "Order-Locked Console", "Ledger Board", "Worker Analyst Pods",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 32, "openclaw_presence": True,
        "manager": "Floor Lead · Binance Testnet",
        "seer": "Testnet Seer", "overseer": "Trading Overseer",
        "watcher": "OpenClaw Watcher",
    },
    43: {
        "floor_name": "Stock Exchange (paper)",
        "department": "Trading · Stocks Paper",
        "template": "TradingFloorInterior",
        "rooms": [
            "Stocks Research Wall", "Paper Portfolio Desk", "Signal Review Desk",
            "Risk Console", "Analyst Pods", "Ledger Board",
            "OpenClaw Inspection Lane", "No-Live-Order Gate",
        ],
        "worker_count": 28, "openclaw_presence": True,
        "manager": "Floor Lead · Stocks Paper",
        "seer": "Equity Seer", "overseer": "Trading Overseer",
        "watcher": "OpenClaw Watcher",
    },
    44: {
        "floor_name": "Accounts / PnL",
        "department": "Banking · Accounts / PnL",
        "template": "TradingFloorInterior",
        "rooms": [
            "PnL Board", "QBC Ledger", "Audit Desk", "Reconciliation Desk",
            "Lesson Review Wall", "Risk Review Desk", "Worker Clerk Pods",
            "OpenClaw Audit Lane",
        ],
        "worker_count": 22, "openclaw_presence": True,
        "manager": "PnL Lead",
        "seer": "PnL Seer", "overseer": "Audit Overseer",
        "watcher": "OpenClaw Watcher",
    },
    35: {
        "floor_name": "Hardware Systems",
        "department": "Hardware Observatory",
        "template": "HardwareObservatoryInterior",
        "rooms": [
            "CPU Observatory", "GPU Observatory", "RAM Monitor", "Storage Wall",
            "Server Rack Lane", "Process Watch Desk", "Maintenance Desk",
            "OpenClaw Hardware Inspection Lane",
        ],
        "worker_count": 18, "openclaw_presence": True,
        "manager": "Hardware Lead",
        "seer": "System Seer", "overseer": "Observatory Overseer",
        "watcher": "OpenClaw Watcher",
    },
    50: {
        "floor_name": "ML / RL Lab",
        "department": "ML / RL Classroom",
        "template": "MLRLClassroomInterior",
        "rooms": [
            "DQN Classroom", "PPO Classroom", "RL Sandbox", "Curriculum Desk",
            "Replay Buffer Wall", "Reward Console", "Researcher Pods",
            "OpenClaw Inspection Lane",
        ],
        "worker_count": 36, "openclaw_presence": True,
        "manager": "Lab Director", "seer": "Curriculum Seer",
        "overseer": "Research Overseer", "watcher": "OpenClaw Watcher",
    },
    8: {
        "floor_name": "Training Academy",
        "department": "Classrooms",
        "template": "MLRLClassroomInterior",
        "rooms": [
            "Trading Classroom", "Commerce Classroom", "Etsy Classroom",
            "Teacher Lounge", "Certification Desk", "Curriculum Desk",
            "Worker Pods", "OpenClaw Audit Lane",
        ],
        "worker_count": 24, "openclaw_presence": True,
        "manager": "Academy Head", "seer": "Curriculum Seer",
        "overseer": "Training Overseer", "watcher": "OpenClaw Watcher",
    },
    37: {
        "floor_name": "Strategy Labs",
        "department": "ML / RL Strategy",
        "template": "MLRLClassroomInterior",
        "rooms": [
            "Strategy Desk", "Research Wall", "Replay Console", "Reward Desk",
            "Backtest Pods", "Curriculum Desk", "Worker Pods", "OpenClaw Inspection Lane",
        ],
        "worker_count": 28, "openclaw_presence": True,
        "manager": "Strategy Lead", "seer": "Strategy Seer",
        "overseer": "Research Overseer", "watcher": "OpenClaw Watcher",
    },
    23: {
        "floor_name": "AirLLM Chamber",
        "department": "Model Lanes",
        "template": "MLRLClassroomInterior",
        "rooms": [
            "Model Lane Console", "Token Telemetry Wall", "Steward Desk",
            "Layer-Stream Board", "Inference Sandbox", "Researcher Pods",
            "Audit Desk", "OpenClaw Inspection Lane",
        ],
        "worker_count": 14, "openclaw_presence": True,
        "manager": "Model Lane Steward", "seer": "Token Seer",
        "overseer": "Models Overseer", "watcher": "OpenClaw Watcher",
    },
    30: {
        "floor_name": "Guardian / Risk",
        "department": "Security · Guardian",
        "template": "SecurityGuardianInterior",
        "rooms": [
            "Execution Lock Matrix", "Permission Console", "Risk Desk",
            "Audit Trail Wall", "Watcher Pods", "Alert Board",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 16, "openclaw_presence": True,
        "manager": "Guardian Lead", "seer": "Risk Seer",
        "overseer": "Guardian Overseer", "watcher": "OpenClaw Watcher",
    },
    28: {
        "floor_name": "Security / Secrets",
        "department": "Security · Secrets Vault",
        "template": "SecurityGuardianInterior",
        "rooms": [
            "Secret Vault", "Access Log", "Masked Credentials",
            "Watcher Pods", "Audit Desk", "Encryption Console",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 10, "openclaw_presence": True,
        "manager": "Vault Lead", "seer": "Secrets Seer",
        "overseer": "Security Overseer", "watcher": "OpenClaw Watcher",
    },
    31: {
        "floor_name": "Audit / Ledger",
        "department": "Banking · Audit",
        "template": "BankingCommerceInterior",
        "rooms": [
            "Ledger Wall", "Audit Desk", "Reconciliation Desk",
            "QBC Counter", "Clerk Pods", "Risk Review Desk",
            "OpenClaw Audit Lane", "Safety Lock Wall",
        ],
        "worker_count": 18, "openclaw_presence": True,
        "manager": "Audit Lead", "seer": "Audit Seer",
        "overseer": "Banking Overseer", "watcher": "OpenClaw Watcher",
    },
    46: {
        "floor_name": "Commerce Wing",
        "department": "Commerce",
        "template": "BankingCommerceInterior",
        "rooms": [
            "Listing Drafts", "Approval Gate (manual)", "Digital Product Studio",
            "Print-on-Demand Desk", "Shop Opportunities Wall", "Clerk Pods",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 22, "openclaw_presence": True,
        "manager": "Commerce Lead", "seer": "Commerce Seer",
        "overseer": "Commerce Overseer", "watcher": "OpenClaw Watcher",
    },
    14: {
        "floor_name": "Print-on-Demand",
        "department": "Commerce · POD",
        "template": "BankingCommerceInterior",
        "rooms": [
            "Product Pipeline", "Listing Drafts", "Approval Gate (manual)",
            "Print-on-Demand Desk", "Shop Opportunities Wall", "Clerk Pods",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 16, "openclaw_presence": True,
        "manager": "POD Lead", "seer": "Listings Seer",
        "overseer": "Commerce Overseer", "watcher": "OpenClaw Watcher",
    },
    6: {
        "floor_name": "Etsy Shop Floor",
        "department": "Commerce · Etsy",
        "template": "BankingCommerceInterior",
        "rooms": [
            "Listing Drafts", "Approval Gate (manual)", "Studio",
            "Print-on-Demand Desk", "Shop Opportunities Wall", "Clerk Pods",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 14, "openclaw_presence": True,
        "manager": "Etsy Lead", "seer": "Listings Seer",
        "overseer": "Commerce Overseer", "watcher": "OpenClaw Watcher",
    },
    45: {
        "floor_name": "Worker Recruitment",
        "department": "Recruitment",
        "template": "GenericFloorInterior",
        "rooms": [
            "Recruitment Desk", "Worker Onboarding", "Skill Assessment",
            "Lineage Board", "Training Pods", "OpenClaw Inspection Lane",
            "Clerk Pods", "Safety Lock Wall",
        ],
        "worker_count": 24, "openclaw_presence": True,
        "manager": "Worker Recruitment Head", "seer": "Lineage Seer",
        "overseer": "Recruitment Overseer", "watcher": "OpenClaw Watcher",
    },
    22: {
        "floor_name": "Lifts Department",
        "department": "Lifts",
        "template": "GenericFloorInterior",
        "rooms": [
            "Lift Control Console", "Lift Maintenance", "Packet Routing Desk",
            "Lift Status Wall", "Worker Pods", "Audit Desk",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 12, "openclaw_presence": True,
        "manager": "Lifts Lead", "seer": "Routing Seer",
        "overseer": "Lifts Overseer", "watcher": "OpenClaw Watcher",
    },
    38: {
        "floor_name": "Sandbox Operations",
        "department": "Sandbox / Ops",
        "template": "GenericFloorInterior",
        "rooms": [
            "Sandbox Console", "Sim Desk", "Risk Review Desk",
            "Ops Wall", "Worker Pods", "Audit Desk", "Lab Desk", "OpenClaw Inspection Lane",
        ],
        "worker_count": 18, "openclaw_presence": True,
        "manager": "Sandbox Lead", "seer": "Sim Seer",
        "overseer": "Ops Overseer", "watcher": "OpenClaw Watcher",
    },
    53: {
        "floor_name": "Tower Command",
        "department": "Tower Command",
        "template": "GenericFloorInterior",
        "rooms": [
            "Command Desk", "Status Wall", "Comm Console",
            "Briefing Desk", "Worker Pods", "Watcher Desk",
            "OpenClaw Inspection Lane", "Safety Lock Wall",
        ],
        "worker_count": 8, "openclaw_presence": True,
        "manager": "Tower Commander", "seer": "Tower Seer",
        "overseer": "Command Overseer", "watcher": "OpenClaw Watcher",
    },
}

GENERIC_ROOMS = [
    "Main Hall", "Operations Desk", "Status Wall", "Worker Pods",
    "Quiet Room", "Storage", "Manager Office", "Lobby",
]

def generic_floor(idx: int) -> dict:
    return {
        "floor_name": f"Floor {idx}",
        "department": f"Floor {idx} · Operations",
        "template": "GenericFloorInterior",
        "rooms": list(GENERIC_ROOMS[:5]),  # 5 rooms minimum
        "worker_count": 12,
        "openclaw_presence": False,
        "manager": "Floor Manager",
        "seer": "Floor Seer",
        "overseer": "Floor Overseer",
        "watcher": "Floor Watcher",
    }

def build_entry(idx: int) -> dict:
    base = SPECIAL.get(idx)
    inferred = base is None
    if inferred:
        base = generic_floor(idx)
    entry = {
        "floor_id": f"F{idx:02d}",
        "floor_name": base["floor_name"],
        "department": base["department"],
        "template": base["template"],
        "rooms": base["rooms"],
        "worker_count": base["worker_count"],
        "workers": [
            {"id": f"F{idx:02d}.W{n:02d}", "role": "worker"} for n in range(min(base["worker_count"], 8))
        ],
        "manager": base["manager"],
        "watcher": base["watcher"],
        "seer": base["seer"],
        "overseer": base["overseer"],
        "openclaw_presence": base["openclaw_presence"],
        "telemetry_sources": [
            "data/registries/cognitive/cognitive_morning_briefing.json",
            "data/registries/qsb_godot_kernel_chat_last_response.json",
        ],
        "animations": [
            "idle","walking","working","inspecting","teaching","researching",
            "auditing","monitoring","carrying_packet","warning",
        ],
        "click_route": f"FloorClickRouter -> enter_interior({idx})",
        "interior_status": "implemented",
        "inferred": inferred,
        "safety_locks_visible": True,
    }
    return entry

def main() -> int:
    floors = [build_entry(i) for i in range(1, 56)]
    out = {
        "ok": True,
        "kind": "qsb_floor_interior_master_registry",
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "floor_count": len(floors),
        "templates_used": sorted({f["template"] for f in floors}),
        "openclaw_present_count": sum(1 for f in floors if f["openclaw_presence"]),
        "inferred_count": sum(1 for f in floors if f["inferred"]),
        "floors": floors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {OUT} · {len(floors)} floors")
    return 0

if __name__ == "__main__":
    sys.exit(main())
