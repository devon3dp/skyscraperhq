#!/usr/bin/env bash
# qsb_phase_public_deploy.sh
#
# ============================================================================
#  HOW TO USE THIS SCRIPT
# ============================================================================
#
#  1. Pick ONE hosting target (you decide which; the script doesn't):
#
#       (a) GitHub Pages       — Tower Studio LANDING only, free, easy
#                                URL: https://YOURUSER.github.io/REPO
#                                Limits: no backend, no contact form
#
#       (b) Cloudflare Pages   — Tower Studio LANDING only, free
#                                Custom domain supported
#                                Limits: no backend
#
#       (c) Cloudflare Tunnel  — BOTH sites, your machine stays the host
#                                Pro: zero hosting cost; full backend
#                                Con: your laptop must stay on
#
#       (d) Fly.io             — BOTH sites with backend (recommended)
#                                Free 256MB VM; auto-sleeps
#                                Pro: real production host with TLS
#                                Con: needs Docker; needs a card on file
#
#       (e) Render             — Lumen backend with TLS, free tier sleeps
#                                Pro: simple
#                                Con: free tier dozes after 15 min idle
#
#  2. Install + authenticate the host's CLI on your machine BEFORE the
#     phase session starts. None of these have credentials in the script.
#
#       GitHub Pages:    sudo apt install gh && gh auth login
#       Cloudflare:      install 'cloudflared' from Cloudflare's website
#                        cloudflared login    # one-time
#       Fly.io:          curl -L https://fly.io/install.sh | sh
#                        flyctl auth login
#       Render:          install render-cli; render login
#
#  3. Open a FRESH Claude Code session in /vaults/nvme0/qsb_tower_v1.
#
#  4. Type EXACTLY this into Claude:
#
#       Run the QSB public deploy phase.
#       Read scripts/qsb_phase_public_deploy.sh and
#       web/PUBLIC_DEPLOY.md.
#       I have chosen host: <a|b|c|d|e>
#       Follow the script. STOP after the smoke test and ASK me before
#       flipping any flag in production.
#
#  5. The phase will:
#       · verify the host CLI is installed + authenticated
#       · build a deploy bundle in build/
#       · push to the chosen host
#       · run a smoke test against the public URL
#       · stamp data/registries/cognitive/cognitive_public_deploy_state.json
#       · STOP — operator decides whether to enable real_payments_enabled
#
# ============================================================================
#  WHAT THIS PHASE WILL *NOT* DO
# ============================================================================
#
#  · Never flip real_payments_enabled (Square is a separate phase).
#  · Never include credentials in the deploy bundle. The deploy bundle
#    is built fresh; .env, *.token, ~/.ssh, etc. are explicitly excluded.
#  · Never run `git push --force` to any branch you didn't choose.
#  · Never push to a public repo that contains the registries directory
#    (those stay in the local /vaults tree).
#  · Never touch the AirLLM venv.
#
# ============================================================================
#  Pre-flight check (the rest is read by Claude)
# ============================================================================
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
cd "${ROOT}"

echo "================================================================="
echo "  Public deploy phase — PRE-FLIGHT"
echo "================================================================="
echo
echo "Workspace: ${ROOT}"
echo

echo "Static-site bundle would be built from:"
ls -la "${ROOT}/web/tower_studio/" | head -8
echo "..."
echo
echo "Backend bundle would be built from:"
ls -la "${ROOT}/tools/qsb_studio_serve.py" "${ROOT}/tools/qsb_lumen_serve.py" \
        "${ROOT}/src/tower/floors/floor_49_tower_studio" \
        "${ROOT}/src/tower/floors/floor_48_lumen_ai" 2>/dev/null | head -8
echo
echo "Host CLIs detected:"
for cmd in gh cloudflared flyctl render netlify; do
  if command -v "${cmd}" >/dev/null 2>&1; then
    echo "  ✓ ${cmd} present"
  else
    echo "  ✗ ${cmd} NOT installed"
  fi
done

echo
echo "Gates that will STAY locked through this phase:"
echo "  · live_listings_publishing_enabled = False"
echo "  · real_payments_enabled            = False"
echo "  · external_api_calls_enabled       = False  (Lumen stays Kernel-powered)"
echo "  · model_inference_external_apis    = False"
echo "  · autonomous_dispatch_enabled      = False"
echo
echo "Gates that this phase MAY flip (after smoke test + operator confirm):"
echo "  · public_website_published         (Tower Studio)"
echo "  · public_api_open                  (Lumen — for the playground only,"
echo "                                       not for partner API use)"
echo
echo "Pre-flight complete. Hand this script to a fresh Claude session along"
echo "with your chosen host letter (a..e). The session walks the deploy step"
echo "by step and stops before any flag flip."
