#!/usr/bin/env bash
# qsb_godot_audio_test_sound.sh — play a short sound to verify output.
set -uo pipefail
if command -v paplay >/dev/null 2>&1 && [ -f /usr/share/sounds/freedesktop/stereo/complete.oga ]; then
  paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>&1 || true
  exit 0
fi
if command -v speaker-test >/dev/null 2>&1; then
  timeout 1 speaker-test -t sine -f 880 -l 1 2>&1 | head -3 || true
  exit 0
fi
echo "no audio test backend available"
exit 1
