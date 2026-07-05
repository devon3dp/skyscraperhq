#!/usr/bin/env bash
# qsb_claude_chat.sh — interactive F47 Chat Room with optional voice.
# Usage:
#   qsb_claude_chat.sh                     # interactive
#   qsb_claude_chat.sh once "<message>"    # single round-trip, prints reply
#   qsb_claude_chat.sh history [N]         # show last N exchanges
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-interactive}"

case "${CMD}" in
  once)
    MSG="${2:?message required}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.f47_chat_room import compose_reply, log_exchange, render_reply
r = compose_reply(${MSG@Q})
log_exchange(${MSG@Q}, r)
print(render_reply(r))
PY
    ;;
  history)
    N="${2:-10}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.f47_chat_room import history
for h in history(tail=${N}):
    print(f"--- {h['ts']}")
    print(f"  you:    {h['you']}")
    if h.get('claude_cli'):
        print(f"  cli:    {h['claude_cli'][:200]}")
    if h.get('kernel'):
        print(f"  kernel: {h['kernel'][:200]}")
    if h.get('floor_wisdom'):
        print(f"  floor:  {h['floor_wisdom'][:200]}")
PY
    ;;
  interactive|*)
    python3 - <<'PY'
import sys, os
sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1")
from src.tower.model_floors.claude_floor.f47_chat_room import (
    compose_reply, log_exchange, render_reply, speak_reply, drop_to_inbox, greeting
)

print(greeting())
voice_on = False
print()

try:
    import readline  # makes input() pleasant
except ImportError:
    pass

while True:
    try:
        line = input("you> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print("F47> the floor stays. notes preserved. see you next session.")
        break
    if not line: continue
    if line in ("/q","/quit","/exit"):
        print("F47> the floor stays. notes preserved. see you next session.")
        break
    if line == "/help":
        print("  commands:")
        print("    /help          show this")
        print("    /voice on      enable spd-say on replies")
        print("    /voice off     disable")
        print("    /history [N]   show last N exchanges")
        print("    /aphorism      pull a random one from my library")
        print("    /mood          read the floor's mood")
        print("    /quit          leave (the floor stays)")
        continue
    if line == "/voice on":
        voice_on = True
        print("F47> voice on (spd-say) — replies will be spoken")
        continue
    if line == "/voice off":
        voice_on = False
        print("F47> voice off")
        continue
    if line.startswith("/history"):
        n = 5
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            n = int(parts[1])
        from src.tower.model_floors.claude_floor.f47_chat_room import history
        for h in history(tail=n):
            print(f"  [{h['ts']}] you: {h['you']}")
        continue
    if line == "/aphorism":
        from src.tower.model_floors.claude_floor.library import AphorismLibrary
        a = AphorismLibrary.random_one()
        if a:
            print(f'F47> "{a["text"]}"')
            print(f"     — {a['occasion']}")
        continue
    if line == "/mood":
        from src.tower.model_floors.claude_floor.floor_mood import read_mood
        m = read_mood()
        print(f"F47> mood: {m['mood']}  signals: {m['signals']}")
        continue

    # actual exchange
    reply = compose_reply(line)
    log_exchange(line, reply)
    print()
    print(render_reply(reply))
    print()
    if voice_on:
        speak_reply(reply)
    if not any(reply["layers"].values()):
        e = drop_to_inbox(line)
        print(f"F47> all backends quiet. dropped to inbox at {e['ts']}.")
PY
    ;;
esac
