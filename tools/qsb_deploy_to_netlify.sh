#!/usr/bin/env bash
# qsb_deploy_to_netlify.sh — deploy all 15 shop sites + master to Netlify.
# Requires: NETLIFY_AUTH_TOKEN env var (from netlify.com → User Settings → Applications → Personal Access Tokens).
# Optional: NETLIFY_SITE_ID for the master site to update an existing one.

set -euo pipefail

if ! command -v netlify >/dev/null 2>&1; then
  echo "installing netlify-cli locally..."
  npm install --no-save netlify-cli >/dev/null 2>&1 || {
    echo "npm not found. Install Node.js + run: npm install -g netlify-cli"
    exit 1
  }
  NETLIFY=./node_modules/.bin/netlify
else
  NETLIFY=netlify
fi

if [ -z "${NETLIFY_AUTH_TOKEN:-}" ]; then
  echo "set NETLIFY_AUTH_TOKEN env var first."
  echo "  https://app.netlify.com/user/applications → Personal Access Tokens → New token"
  exit 1
fi

ROOT=/vaults/nvme0/qsb_tower_v1
cd "$ROOT/web/shops"

echo "▶ Deploying master site (parent landing)..."
$NETLIFY deploy --prod --dir . --site=qsb-tower-master --auth="$NETLIFY_AUTH_TOKEN" 2>&1 | tail -5
echo

for FN in 61 62 63 64 65 154 155 156 157 158 159 160 161 162 163; do
  echo "▶ Deploying floor_$FN..."
  $NETLIFY deploy --prod --dir "floor_$FN" --site="qsb-shop-$FN" --auth="$NETLIFY_AUTH_TOKEN" 2>&1 | tail -3
  echo
done

echo "✓ all 16 deployments dispatched"
echo "  Wire subdomains in app.netlify.com → each site → Domain settings → add custom domain"
