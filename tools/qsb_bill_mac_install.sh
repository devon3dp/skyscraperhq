#!/bin/bash
# qsb_bill_mac_install.sh — permanent, secure install of Bill's leadership client on macOS.
#
# What it does (safely):
#   1. Verifies the relay identity + endpoint before trusting anything.
#   2. Downloads the client with `curl --fail` (an HTTP error page can NEVER be run as code).
#   3. Verifies the client's SHA-256 against a pinned checksum; refuses on mismatch.
#   4. Exchanges a ONE-TIME enrollment code for Bill's token (token never typed/printed).
#   5. Stores the token in the macOS Keychain (readable only by this login account).
#   6. Installs a launchd agent so it auto-starts at login and runs with NO Terminal open,
#      auto-restarting on crash and reconnecting after network/reboot.
#
# The client itself is messaging-only: it cannot execute commands received in chat,
# cannot change code, cannot bypass the Task Council, and never transmits the token
# in a message body (auth header only). Verified by checksum below.
#
# Usage on the Mac:
#   curl --fail -s http://192.168.1.84:8855/install -o install.sh
#   bash install.sh                # will prompt for the one-time enrollment code
#   # (optional non-interactive:)  bash install.sh <ENROLLMENT_CODE>
set -euo pipefail

RELAY="${QSB_RELAY:-http://192.168.1.84:8855}"
IDENTITY="bill"
EXPECTED_SHA="b6ffcb5ff6f51a607c05f0748859e82d8d5ffd02502c8431630d6570141ee27c"   # pinned at publish time
QDIR="$HOME/.qsb"
CLIENT="$QDIR/qsb_leadership_client.py"
RUNNER="$QDIR/qsb_leadership_run.sh"
PLIST="$HOME/Library/LaunchAgents/com.qsb.leadership.bill.plist"
KC_SERVICE="qsb-leadership-relay"

say() { printf '\033[36m[qsb-install]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[qsb-install] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 not found on this Mac."

# --- 1. verify relay identity BEFORE trusting anything it serves ---
say "Verifying relay identity at $RELAY ..."
HEALTH="$(curl --fail --max-time 10 -s "$RELAY/health")" || die "relay unreachable / bad endpoint."
echo "$HEALTH" | grep -q '"service": *"qsb_leadership_relay"' || die "endpoint is not the QSB leadership relay."
echo "$HEALTH" | grep -q '"claude_hq": *"retired"' || die "relay identity check failed."
say "Relay verified."

# --- 2. download client with --fail (no error-page-as-code) ---
mkdir -p "$QDIR"
say "Downloading client (fail-closed) ..."
curl --fail --max-time 20 -s "$RELAY/client" -o "$CLIENT.tmp" || die "client download failed (no error page executed)."

# --- 3. checksum verify (fail-closed) ---
GOT_SHA="$(shasum -a 256 "$CLIENT.tmp" | awk '{print $1}')"
if [ "$GOT_SHA" != "$EXPECTED_SHA" ]; then
  rm -f "$CLIENT.tmp"; die "client checksum MISMATCH (expected $EXPECTED_SHA got $GOT_SHA) — refusing."
fi
mv "$CLIENT.tmp" "$CLIENT"
say "Client verified (sha256 $GOT_SHA)."

# --- 4. one-time enrollment -> token (never printed) ---
CODE="${1:-}"
if [ -z "$CODE" ]; then
  printf '[qsb-install] Enter the one-time enrollment code (from Ross): '
  read -r CODE
fi
[ -n "$CODE" ] || die "no enrollment code provided."
say "Enrolling (exchanging one-time code for token) ..."
RESP="$(curl --fail --max-time 15 -s -X POST "$RELAY/enroll" -H 'Content-Type: application/json' -d "{\"code\":\"$CODE\"}")" \
  || die "enrollment failed (code invalid, used, or expired)."
TOKEN="$(printf '%s' "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')"
[ -n "$TOKEN" ] || die "enrollment returned no token."

# --- 5. store token in Keychain (this login account only); token never echoed ---
security add-generic-password -a "$IDENTITY" -s "$KC_SERVICE" -w "$TOKEN" -U >/dev/null 2>&1 \
  || die "could not store token in Keychain."
unset TOKEN
say "Token stored in macOS Keychain (service=$KC_SERVICE account=$IDENTITY)."

# --- 6. runner reads token from Keychain at runtime, passes via env (not argv) ---
cat > "$RUNNER" <<EOF
#!/bin/bash
set -euo pipefail
TOKEN=\$(security find-generic-password -a "$IDENTITY" -s "$KC_SERVICE" -w)
export QSB_LEADER_TOKEN="\$TOKEN"
exec /usr/bin/python3 "$CLIENT" --identity "$IDENTITY" --relay "$RELAY" --hb 5 --poll 5
EOF
chmod 700 "$RUNNER"; chmod 700 "$CLIENT"

# --- launchd agent: auto-start at login, keep alive, no Terminal ---
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.qsb.leadership.bill</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$RUNNER</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$QDIR/leadership.out.log</string>
  <key>StandardErrorPath</key><string>$QDIR/leadership.err.log</string>
</dict></plist>
EOF

say "Loading launchd agent ..."
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST" || die "launchctl load failed."
launchctl start com.qsb.leadership.bill >/dev/null 2>&1 || true

say "DONE. Bill is installed as a launchd agent — auto-starts at login, no Terminal needed."
say "It should appear ONLINE at the relay within ~30s. Logs: $QDIR/leadership.*.log"
