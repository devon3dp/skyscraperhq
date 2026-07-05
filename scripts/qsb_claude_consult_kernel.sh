#!/usr/bin/env bash
# qsb_claude_consult_kernel.sh — POST a question to the local kernel and log
# both the question and the reply (masked) to a persistent transcript.
# This is the legitimate channel between Claude (F47) and the Kernel (F55).
# Local-only. No external network. Advisory only.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
QUESTION="${1:?question required}"
TRANSCRIPT="${ROOT}/data/registries/qsb_claude_kernel_consultations.jsonl"
mkdir -p "$(dirname "${TRANSCRIPT}")"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESP="$(curl -s --max-time 10 -X POST -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json, sys; print(json.dumps({'message': sys.argv[1]}))" "${QUESTION}")" \
  http://127.0.0.1:8765/api/kernel_chat || echo '{"ok": false, "reply": "(kernel unreachable)"}')"

# Mask anything that looks like a secret before persisting
SAFE="$(echo "${RESP}" | sed -E 's/("(api_token|access_token|secret|api_key|password)"[[:space:]]*:[[:space:]]*)"[^"]*"/\1"***"/g')"

python3 - <<PY >> "${TRANSCRIPT}"
import json
resp = """${SAFE}"""
try: parsed = json.loads(resp)
except Exception: parsed = {"raw": resp[:2000]}
print(json.dumps({
  "ts": "${TS}",
  "from": "Claude (F47)",
  "to": "Kernel (F55)",
  "question": ${QUESTION@Q},
  "reply_intent": parsed.get("intent","?"),
  "reply_execution_required": parsed.get("execution_required","?"),
  "reply_excerpt": (parsed.get("reply","") or "")[:800],
}))
PY

# Also print the headline so I can read it now
python3 -c "
import json
print(json.loads('''${SAFE}''').get('reply','(no reply)')[:1200])
"
