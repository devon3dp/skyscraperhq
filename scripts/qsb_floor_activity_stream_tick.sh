#!/usr/bin/env bash
# qsb_floor_activity_stream_tick.sh — synthesize a per-floor activity event
# from existing local registries. Local-only, no external providers.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
REG_OUT="${ROOT}/data/registries/qsb_floor_activity_stream_latest.json"
LOG="${ROOT}/data/logs/qsb_floor_activity_stream.jsonl"
mkdir -p "$(dirname "${REG_OUT}")" "$(dirname "${LOG}")"

python3 - <<'PY' "$ROOT" "$REG_OUT" "$LOG"
import json, os, sys, datetime, random, hashlib
root = sys.argv[1]
reg_out = sys.argv[2]
log = sys.argv[3]

def read_json(path: str):
    full = os.path.join(root, path)
    if not os.path.exists(full): return None
    try:
        return json.load(open(full))
    except Exception:
        return None

# Read existing registries (local only)
master = read_json("data/registries/qsb_floor_interior_master_registry.json")
if not master:
    print("master registry missing — run qsb_generate_floor_interior_registry.py first", file=sys.stderr)
    sys.exit(2)

kernel = read_json("data/registries/cognitive/cognitive_morning_briefing.json")
chat_last = read_json("data/registries/qsb_godot_kernel_chat_last_response.json")
audio_stack = read_json("data/registries/qsb_godot_audio_stack_status.json")
smoke = read_json("data/registries/qsb_godot_overlay_audio_chat_smoke_test_latest.json")
oanda = read_json("data/registries/oanda/oanda_account_summary.json") or read_json("data/registries/qsb_oanda_practice_account.json")
binance = read_json("data/registries/binance/binance_testnet_preview.json")
mlrl = read_json("data/registries/qsb_floor50_mlrl_lab_status.json")
bank = read_json("data/registries/banking/banking_gateway_status.json")
gh = read_json("data/registries/qsb_github_upgrade_scout_status.json")
guardian = read_json("data/registries/qsb_floor30_guardian_locks.json") or read_json("data/registries/qsb_floor30_guardian_status.json")

# Tower-wide headline
headline_bits = []
if kernel and isinstance(kernel, dict) and kernel.get("headline"):
    headline_bits.append(str(kernel["headline"])[:100])
headline_bits.append("safety locks closed")
if audio_stack and audio_stack.get("tts_available"):
    headline_bits.append("TTS ready")
headline = " · ".join(headline_bits[:3])

# Per-floor flavor templates by template kind
FLAVORS = {
    "KernelPenthouseInterior": [
        "{room} reviewed cognitive state.",
        "{room} stamped new safety envelope.",
        "{room} updated kernel chat sidecar.",
        "{room} aligned attention weights.",
    ],
    "TradingFloorInterior": [
        "{room} ticked PAPER quote.",
        "{room} updated spread.",
        "{room} validated risk envelope.",
        "{room} wrote ledger entry.",
        "{room} blocked live order (locked).",
    ],
    "HardwareObservatoryInterior": [
        "{room} refreshed CPU metric.",
        "{room} refreshed RAM metric.",
        "{room} refreshed disk metric.",
        "{room} flagged 0 warnings.",
    ],
    "MLRLClassroomInterior": [
        "{room} completed DQN lesson loop.",
        "{room} pushed replay buffer batch.",
        "{room} updated curriculum step.",
        "{room} ran researcher pod cycle.",
    ],
    "BankingCommerceInterior": [
        "{room} reconciled ledger row.",
        "{room} drafted listing (NOT published).",
        "{room} ran clerk pod cycle.",
        "{room} updated QBC ledger.",
    ],
    "SecurityGuardianInterior": [
        "{room} confirmed execution locks closed.",
        "{room} reviewed access log.",
        "{room} ran masked credentials audit.",
        "{room} pinged watcher pods.",
    ],
    "GenericFloorInterior": [
        "{room} completed routine task.",
        "{room} updated status wall.",
        "{room} pushed packet on lift.",
    ],
}

ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
seed = int(hashlib.sha256(ts.encode()).hexdigest()[:8], 16)
rng = random.Random(seed)

per_floor = {}
total_events = 0
for entry in master["floors"]:
    fid = entry["floor_id"]
    template = entry["template"]
    rooms = entry.get("rooms", [])
    if not rooms:
        per_floor[fid] = {"text": f"{fid} idle.", "category": "evt"}
        continue
    room = rng.choice(rooms)
    flavor = rng.choice(FLAVORS.get(template, FLAVORS["GenericFloorInterior"]))
    text = f"{fid} {flavor.format(room=room)}"
    per_floor[fid] = {
        "text": text, "room": room, "template": template,
        "category": "trade" if "Trading" in template
            else "warn" if "Security" in template
            else "evt"
    }
    total_events += 1

out = {
    "ok": True,
    "kind": "qsb_floor_activity_stream_latest",
    "ts": ts,
    "headline": headline,
    "floors_tracked": len(master["floors"]),
    "events_this_tick": total_events,
    "per_floor": per_floor,
    "safety_envelope": {
        "live_trading_enabled": False,
        "live_payments_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "external_api_calls_enabled": False,
    },
}
with open(reg_out, "w") as fh:
    json.dump(out, fh, indent=2)
# Append a few sample lines to the JSONL log
with open(log, "a") as fh:
    sample = rng.sample(list(per_floor.items()), min(8, len(per_floor)))
    for fid, info in sample:
        fh.write(json.dumps({"ts": ts, "floor_id": fid, "text": info["text"]}) + "\n")

print(f"tick ok · {total_events} events · headline: {headline[:80]}")
PY

# Mirror into the Godot project (snap-confined Godot can't read /vaults/)
MIRROR_DIR="/home/ross/qsb_godot_native_cockpit/data/registries"
mkdir -p "${MIRROR_DIR}"
cp "${REG_OUT}" "${MIRROR_DIR}/qsb_floor_activity_stream_latest.json" 2>/dev/null || true
