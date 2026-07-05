#!/usr/bin/env bash
# qsb_godot_kernel_chat_bridge.sh — safe local chat bridge.
# Takes a single argument, calls existing kernel_chat backend over HTTP,
# masks anything that looks like a token, writes last response to registry.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
MSG="${1:-Report dashboard status.}"
OUT="${ROOT}/data/registries/qsb_godot_kernel_chat_last_response.json"
mkdir -p "$(dirname "${OUT}")"

# Use the HTTP backend (already running on :8765) — safer than shelling out
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESP="$(curl -s --max-time 10 -X POST -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys; print(json.dumps({'message': sys.argv[1]}))" "${MSG}")" \
  http://127.0.0.1:8765/api/kernel_chat 2>&1 || true)"

# Mask anything that looks like a secret
SAFE="$(echo "${RESP}" | sed -E 's/("(api_token|access_token|secret|api_key|password)"[[:space:]]*:[[:space:]]*)"[^"]*"/\1"***"/g')"

python3 - <<PY > "${OUT}"
import json
resp = """${SAFE}"""
try:
    parsed = json.loads(resp)
except Exception:
    parsed = {"raw": resp[:2000]}
out = {
  "ok": True,
  "kind": "qsb_godot_kernel_chat_last_response",
  "ts": "${TS}",
  "prompt": ${MSG@Q},
  "response": parsed,
}
print(json.dumps(out, indent=2))
PY

# Print just the reply text for stdout
python3 -c "
import json
try:
    d = json.load(open('${OUT}'))
    r = d.get('response', {})
    if isinstance(r, dict) and 'reply' in r:
        print(r['reply'])
    else:
        print(json.dumps(r)[:1500])
except Exception as e:
    print('(chat bridge error: %s)' % e)
"
