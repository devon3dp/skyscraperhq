#!/usr/bin/env bash
# qsb_phase_square_integration.sh
#
# ============================================================================
#  HOW TO USE THIS SCRIPT
# ============================================================================
#
#  1. Open a FRESH Claude Code session in /vaults/nvme0/qsb_tower_v1.
#
#  2. Type EXACTLY this into Claude (and nothing else first):
#
#       Run the QSB Square integration phase.
#       Read scripts/qsb_phase_square_integration.sh and
#       data/registries/cognitive/cognitive_banking_gateway_scaffold.json
#       carefully. Follow the script step by step. Stop and ASK me
#       before touching any gate.
#
#  3. BEFORE that session starts running shell commands, YOU must export
#     these env vars IN YOUR SHELL (not in chat, not in this file):
#
#       export QSB_SQUARE_APPLICATION_ID=sq0idp-XXXXXXXXXXXX
#       export QSB_SQUARE_ACCESS_TOKEN=EAAAxxxxxxxxxxxxxxx
#       export QSB_SQUARE_LOCATION_ID=LXXXXXXXXX
#       export QSB_SQUARE_WEBHOOK_SIGNATURE_KEY=xxxxxxxxx
#       export QSB_SQUARE_ENV=sandbox             # NEVER 'production' on first run
#
#     The script REFUSES to run if these aren't set. The script never logs
#     their values; it only checks they exist.
#
#  4. Get Sandbox credentials from https://developer.squareup.com:
#       · Create an Application
#       · Open the Application → Sandbox tab → copy Access Token + App ID
#       · Sandbox → Locations → copy a Location ID
#       · Sandbox → Webhook Subscriptions → copy the Signature Key
#
# ============================================================================
#  WHAT THIS PHASE WILL DO
# ============================================================================
#
#  Step A — Pre-flight (read-only, no money, no API calls yet):
#    · verify env vars present
#    · read cognitive_banking_gateway_scaffold.json for the Square provider spec
#    · refuse to proceed if QSB_SQUARE_ENV != 'sandbox' on first run
#
#  Step B — Install the Square Python SDK locally:
#    · pip install --user squareup
#    · NOT into the AirLLM venv. NOT a system-wide install.
#
#  Step C — Build the Square adapter:
#    · src/tower/integrations/square_adapter.py
#    · read-only methods first (list_locations, list_payments_last_24h)
#    · the adapter NEVER writes a payment from itself
#
#  Step D — Sandbox smoke test (read-only):
#    · call list_locations and confirm location_id matches your env
#    · call list_payments_last_24h (expects 0 in a fresh sandbox)
#    · stamp results into data/logs/square_api_calls.jsonl
#
#  Step E — Wire Floor 49 commerce to Square sandbox:
#    · let Tower Studio's catalog produce a draft invoice
#    · CONFIRM with the operator before generating the invoice
#    · the invoice is created in Sandbox; the operator pays it themselves
#      in the Sandbox dashboard to verify the round-trip
#
#  Step F — Sandbox-to-Production gate (HARD):
#    · phase ENDS here. Production env requires a SEPARATE follow-up
#      session with QSB_SQUARE_ENV=production AND operator-typed kill-
#      switch verification AND reconciliation against a real statement.
#
# ============================================================================
#  WHAT THIS PHASE WILL *NOT* DO
# ============================================================================
#
#  · Never read or log the values of any env var.
#  · Never auto-charge any real money.
#  · Never flip live_payments_enabled or live_listings_publishing_enabled.
#  · Never touch the AirLLM venv at /vaults/ai/airllm_lab/.venv.
#  · Never run with QSB_SQUARE_ENV=production on first invocation.
#  · Never commit credentials to git.
#
# ============================================================================
#  Pre-flight script (the rest is read by Claude, not run here)
# ============================================================================
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
cd "${ROOT}"

PRE_FAIL=0

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "  ✗ ${name} not set"
    PRE_FAIL=1
  else
    echo "  ✓ ${name} present (value redacted)"
  fi
}

echo "================================================================="
echo "  Square integration phase — PRE-FLIGHT (no API calls yet)"
echo "================================================================="
echo
echo "Required env vars:"
require_env QSB_SQUARE_APPLICATION_ID
require_env QSB_SQUARE_ACCESS_TOKEN
require_env QSB_SQUARE_LOCATION_ID
require_env QSB_SQUARE_WEBHOOK_SIGNATURE_KEY
require_env QSB_SQUARE_ENV

if [ "${PRE_FAIL}" -eq 1 ]; then
  echo
  echo "Refusing to proceed. Export the missing vars in YOUR shell, then"
  echo "re-run this script. Example:"
  echo "  export QSB_SQUARE_APPLICATION_ID=sq0idp-..."
  exit 2
fi

if [ "${QSB_SQUARE_ENV:-}" != "sandbox" ]; then
  echo
  echo "✗ QSB_SQUARE_ENV is '${QSB_SQUARE_ENV}'. First run MUST be 'sandbox'."
  echo "  Production wiring is a SEPARATE follow-up session."
  exit 3
fi

echo
echo "Pre-flight OK. The rest of this phase is Claude-driven — Claude reads"
echo "the comment block at the top of this file and walks through steps"
echo "A→F, pausing to confirm with you before each consequential action."
echo
echo "Cognitive Kernel banking gateway scaffold:"
echo "  ${ROOT}/data/registries/cognitive/cognitive_banking_gateway_scaffold.json"
echo
echo "Once Claude finishes Step E (sandbox round-trip confirmed), STOP."
echo "Production wiring is intentionally a separate session."
