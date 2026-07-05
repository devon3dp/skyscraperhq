#!/usr/bin/env bash
# qsb_godot_audio_test_voice.sh — speak a test line via local TTS.
set -uo pipefail
MSG="${1:-Lumen voice test. Local only.}"
if command -v spd-say >/dev/null 2>&1; then
  spd-say --rate 10 "${MSG}" &
  exit 0
fi
if command -v espeak-ng >/dev/null 2>&1; then
  espeak-ng "${MSG}" &
  exit 0
fi
if command -v espeak >/dev/null 2>&1; then
  espeak "${MSG}" &
  exit 0
fi
echo "no TTS backend"
exit 1
