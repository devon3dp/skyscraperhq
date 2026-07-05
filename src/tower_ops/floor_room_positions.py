"""Floor / room canonical positions (used by route engine + future renderer)."""

from .safety_contract import stamp_safe
from datetime import datetime, timezone


def _now(): return datetime.now(timezone.utc).isoformat()


# Map floor_id → list of rooms (used for route hops and lift queues)
ROOMS = {
    "floor_41": ["Pricing Desk", "Account Wall", "Open Trades Board", "Manual Confirm Desk",
                  "Practice Execution Desk", "Ledger Desk", "OpenClaw Practice Proposal Desk",
                  "Risk Guard Station", "Manager Office", "Overseer Balcony", "Lift Lobby"],
    "floor_42": ["Testnet Market Feed", "Account Wall", "Open Orders Desk",
                  "Crypto Spread Watch", "Risk Lock Station", "Ledger Desk",
                  "OpenClaw Observer", "Manager Office", "Overseer Balcony", "Lift Lobby"],
    "floor_43": ["Market Data Desk", "Equity Strategy Desk", "Cross-Market Bus",
                  "Risk Checkpoint", "Audit Dispatch", "Account Wall",
                  "Manager Office", "Overseer Balcony", "Lift Lobby"],
    "floor_44": ["Chief Office", "Ledger Desk", "OANDA Desk", "Binance Desk",
                  "Stocks Desk", "Paper Ledger Desk", "Not Configured Board",
                  "Manager Office", "Lift Lobby"],
    "floor_30": ["Lock Matrix", "Inbound from Trading", "Outbound to Audit",
                  "Safety Pulse", "Manager Office", "Lift Lobby"],
    "floor_31": ["Ledger Counter", "Latest Entries", "Audit Pulse", "Outbound to Command",
                  "Manager Office", "Lift Lobby"],
    "floor_37": ["Strategy Intelligence", "Cross-Market Inputs", "Paper Signals",
                  "Simulation Outbound", "Manager Office", "Lift Lobby"],
    "floor_38": ["Reception Desk", "Interview Rooms", "Training Room",
                  "Capability Board", "Roster Wall", "OpenClaw Review Gate",
                  "Dispatch Queue", "Audit Desk", "Manager Office", "Lift Lobby"],
    "floor_28": ["Access Control Desk", "Lock Matrix Wall", "OpenClaw Gate Guard",
                  "Incident Board", "Manager Office", "Lift Lobby"],
    "floor_33": ["Service Health Desk", "Port Monitor Wall", "Disk Mount Monitor",
                  "Worker Heartbeat Desk", "Manager Office", "Lift Lobby"],
    "floor_35": ["Network Operations Center", "Local Ports Map", "API Gateway Desk",
                  "Sidecar Router Desk", "Manager Office", "Lift Lobby"],
    "floor_08": ["Reception", "Safety and Locks Classroom", "Trading Telemetry Classroom",
                  "OpenClaw Readiness Classroom", "Exam Room", "Certification Board",
                  "Manager Office", "Lift Lobby"],
    "floor_03": ["Research Intake Desk", "Source Quality Desk", "Architecture Desk",
                  "AirLLM Liaison Desk", "Report Writing Desk", "Manager Office", "Lift Lobby"],
    "floor_22": ["Lift Operations Office", "Lift-01 Console", "Lift-02 Console",
                  "Lift-03 Console", "Lift-04 Console", "Routing Desk", "Lift Lobby"],
    "floor_23": ["Big Model Chamber", "Advisory Desk", "Future Manual Ask Lane",
                  "Manager Office", "Lift Lobby"],
    "floor_45": ["Reactor Room", "Entropy Monitor", "Symbolic Desk",
                  "Safety Gate", "Manager Office", "Lift Lobby"],
    "floor_14": ["Media Routing Desk", "Speech Floor Link", "Manager Office", "Lift Lobby"],
    "floor_15": ["TTS Output Desk", "STT Intake Desk", "Speech Route Desk",
                  "Manager Office", "Lift Lobby"],
    "floor_53": ["Tower Summary", "Inbound from Audit", "Floor Status Strip",
                  "Kernel Review Route", "Manager Office", "Lift Lobby"],
    "penthouse": ["Concierge Reception", "Butler Station", "Kernel Core",
                   "Kernel Liaison Office", "Speech Attendant", "Report Clerk Desk",
                   "Colonel Observation Wall"],
}


def rooms_for(floor_id):
    return ROOMS.get(floor_id, ["Main Floor", "Lift Lobby"])


def room_positions():
    return stamp_safe({"ok": True, "ts": _now(),
                        "rooms_by_floor": ROOMS,
                        "execution_allowed": False})
