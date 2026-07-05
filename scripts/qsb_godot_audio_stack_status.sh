#!/usr/bin/env bash
# qsb_godot_audio_stack_status.sh — probe local audio + TTS availability.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

probe() {
  local name="$1"; local bin="$2"
  if command -v "${bin}" >/dev/null 2>&1; then
    echo "  ✓ ${name}: $(command -v "${bin}")"
    return 0
  else
    echo "  ✗ ${name}: not installed"
    return 1
  fi
}

echo "============================================================"
echo "  QSB Godot · Local audio + TTS stack"
echo "============================================================"
SOUND=0; TTS=0
probe "PulseAudio (pactl)"   pactl       && SOUND=1
probe "PipeWire"             pipewire    && SOUND=1
probe "speaker-test"         speaker-test
probe "spd-say (speech-d)"   spd-say     && TTS=1
probe "espeak-ng"            espeak-ng   && TTS=1
probe "espeak"               espeak      && TTS=1
PYTTSX=0
if python3 -c "import pyttsx3" >/dev/null 2>&1; then
  echo "  ✓ python pyttsx3: importable"
  PYTTSX=1
else
  echo "  ✗ python pyttsx3: not importable"
fi

DEFAULT_SINK="$(pactl info 2>/dev/null | awk -F': ' '/Default Sink/ {print $2}' | head -1)"

cat > "${ROOT}/data/registries/qsb_godot_audio_stack_status.json" <<EOF
{
  "ok": true,
  "kind": "qsb_godot_audio_stack_status",
  "ts": "${TS}",
  "sound_available": $([ "${SOUND}" -eq 1 ] && echo true || echo false),
  "tts_available":   $([ "${TTS}" -eq 1 ] && echo true || echo false),
  "default_sink":    "${DEFAULT_SINK:-(unknown)}",
  "tools": {
    "pactl":        $(command -v pactl >/dev/null && echo true || echo false),
    "pipewire":     $(command -v pipewire >/dev/null && echo true || echo false),
    "speaker_test": $(command -v speaker-test >/dev/null && echo true || echo false),
    "spd_say":      $(command -v spd-say >/dev/null && echo true || echo false),
    "espeak_ng":    $(command -v espeak-ng >/dev/null && echo true || echo false),
    "espeak":       $(command -v espeak >/dev/null && echo true || echo false),
    "pyttsx3":      $([ "${PYTTSX}" -eq 1 ] && echo true || echo false)
  },
  "policy": "Local-only. No cloud voice. No external provider. No microphone capture in this scaffold."
}
EOF
echo
echo "Registry: data/registries/qsb_godot_audio_stack_status.json"
[ "${SOUND}" -eq 1 ] && [ "${TTS}" -eq 1 ] && exit 0 || exit 1
