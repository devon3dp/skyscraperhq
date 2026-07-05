#!/data/data/com.termux/files/usr/bin/bash
# qsb_galaxy_receptionist.sh — runs on the Samsung Galaxy under Termux.
#
# Ross 2026-06-13: "ok we going with the phone setting up the sim card now"
#
# This is the Galaxy-side bridge. The phone receives PSTN calls; this script
# auto-answers, captures the caller's speech via Android Speech Recognizer,
# POSTs text to the fortress F0 receptionist endpoint, gets a reply, and
# TTSes the reply through the phone's speaker.
#
# Prerequisites on the Galaxy:
#   pkg install termux-api jq curl
#   (Termux:API app from F-Droid — gives termux-* shell commands access to
#    the Android telephony, microphone, and TTS subsystems)
#
# Required permissions (granted via the Termux:API app):
#   - Phone (to detect + answer calls)
#   - Microphone (to record caller speech)
#   - SMS/Telephony (to read call state)
#
# Fortress URL: set via env QSB_FORTRESS, default 192.168.x.x:8765 over WiFi.
# Use ADB reverse port forward for USB-only mode:
#   adb reverse tcp:8765 tcp:8765 → then QSB_FORTRESS=http://127.0.0.1:8765

set -u
FORTRESS="${QSB_FORTRESS:-http://127.0.0.1:8765}"
GREETED_FILE="/data/data/com.termux/files/home/.qsb_iris_greeted"
LOG_FILE="${QSB_IRIS_LOG:-${HOME:-/data/data/com.termux/files/home}/iris.log}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"; }

log "iris polling loop started · fortress=$FORTRESS"

# Listen for incoming-call notifications via termux-notification-list.
# Samsung A14: termux-telephony-deviceinfo has no call_state field, and
# `dumpsys telephony.registry` denies non-system apps (need DUMP perm).
# The reliable path is the notification surface — the dialer posts an
# "incoming call" notification the moment the SIM rings. Termux:API must
# have Notification Access granted (see reference_galaxy_adb_automation.md).
DIALER_PKG_RE="${QSB_DIALER_PKG_RE:-dialer|incallui|com.android.phone|com.samsung.android.incallui|com.samsung.android.dialer}"
# Notifications to EXCLUDE — these are stale state notifications, not a ring.
# group "default_missed_call_group" stays in the tray after a missed ring and
# would re-trigger every poll if we don't exclude it.
EXCLUDE_GROUP_RE="${QSB_EXCLUDE_GROUP_RE:-missed|voicemail|recent_calls}"
# A notification only counts as ringing if it's from a dialer pkg AND its
# group/title/tickerText looks like a live incoming/ringing event.
INCOMING_RE="${QSB_INCOMING_RE:-incoming|ringing|calling}"
while true; do
    incoming=""
    notif="$(termux-notification-list 2>/dev/null || echo '[]')"
    if echo "$notif" | jq -e \
       --arg pkg "$DIALER_PKG_RE" \
       --arg ex  "$EXCLUDE_GROUP_RE" \
       --arg in  "$INCOMING_RE" \
       'map(
          select((.packageName // "") | test($pkg))
          | select(((.group // "") | test($ex; "i")) | not)
          | select(
              ((.group     // "") | test($in; "i"))
              or ((.title     // "") | test($in; "i"))
              or ((.tickerText // "") | test($in; "i"))
              or ((.content   // "") | test($in; "i"))
            )
        ) | length > 0' \
       >/dev/null 2>&1; then
        incoming="$(echo "$notif" | jq -r \
           --arg pkg "$DIALER_PKG_RE" \
           --arg ex  "$EXCLUDE_GROUP_RE" \
           --arg in  "$INCOMING_RE" \
           '[ .[]
              | select((.packageName // "") | test($pkg))
              | select(((.group // "") | test($ex; "i")) | not)
              | select(
                  ((.group     // "") | test($in; "i"))
                  or ((.title     // "") | test($in; "i"))
                  or ((.tickerText // "") | test($in; "i"))
                  or ((.content   // "") | test($in; "i"))
                )
            ] | .[0]
            | "notif:" + (.tickerText // .title // .content // "ringing")' \
           2>/dev/null)"
    fi

    if [ -n "$incoming" ]; then
        # Ringing — auto-answer via input tap on the green button.
        # Galaxy A15 5G coords: green answer button at (670, 500).
        log "incoming call detected — tapping answer button at (670,500)"
        input tap 670 500 2>/dev/null || true
        sleep 2

        # Enable speakerphone so caller hears TTS over the air.
        # Samsung incallui Speaker button: resource fourth_button, center (272, 1717).
        log "enabling speakerphone at (272,1717)"
        input tap 272 1717 2>/dev/null || true
        sleep 1

        # Pull caller id (best-effort)
        caller="$(dumpsys telephony.registry 2>/dev/null | \
                  grep -m1 'mCallIncomingNumber' | sed 's/.*=//' | tr -d ' ' )"
        caller="${caller:-anonymous}"
        log "caller=$caller"

        # Greet
        greeting="$(curl -s -m 5 -X POST "$FORTRESS/api/f0/greet" \
                    -H 'Content-Type: application/json' \
                    -d "{\"caller_id\":\"$caller\"}" | jq -r .text)"
        log "iris> $greeting"
        termux-tts-speak -- "$greeting" &

        # Conversation loop — each turn: 8s of listening, transcribe, converse
        for turn in 1 2 3 4 5; do
            # Record 8s mono pcm
            tmp="/data/data/com.termux/files/usr/tmp/qsb_rec_$$.wav"
            termux-microphone-record -l 8 -f "$tmp" 2>/dev/null
            sleep 8
            termux-microphone-record -q 2>/dev/null

            # Speech-to-text via Android SpeechRecognizer
            user_text="$(termux-speech-to-text -f "$tmp" 2>/dev/null | head -1)"
            user_text="${user_text:-}"
            rm -f "$tmp"
            log "caller> $user_text"

            if [ -z "$user_text" ]; then
                log "no speech detected — closing"
                break
            fi

            # Hand off to fortress. Build payload safely via jq to avoid
            # quoting bugs across nested $(...) and embedded apostrophes.
            payload=$(jq -nc \
                --arg cid "$caller" \
                --arg txt "$user_text" \
                '{caller_id:$cid, text:$txt}')
            reply=$(curl -s -m 8 -X POST "$FORTRESS/api/f0/converse" \
                       -H 'Content-Type: application/json' \
                       -d "$payload" | jq -r .text)
            reply="${reply:-Sorry the tower did not respond.}"
            log "iris> $reply"
            termux-tts-speak -- "$reply"
        done

        # Close
        curl -s -m 5 -X POST "$FORTRESS/api/f0/close" \
             -H 'Content-Type: application/json' \
             -d "{\"caller_id\":\"$caller\",\"summary\":\"galaxy turn loop ended\"}" >/dev/null
        log "call closed"

        # Hang up
        input keyevent KEYCODE_ENDCALL 2>/dev/null || true
        sleep 2
    fi

    sleep 2
done
