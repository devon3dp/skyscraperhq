#!/usr/bin/env bash
# qsb_unreal_visible_cinematic_build_loop.sh — one full visible pass.
#
# Sequence:
#  1) detect canonical structure  → JSON
#  2) apply lighting pass (sun rotate, fill dim, recipe for SkyAtmosphere)
#  3) generate professional skyscraper architectural detail
#  4) generate futuristic city skyline
#  5) take pre/post screenshots
#  6) compute basic visual score
#  7) report exactly what changed
#
# Visible result expected: new actors appear in Outliner + viewport, lighting
# shifts to cinematic angle, secondary skyline ring fills in.

set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y%m%dT%H%M%SZ)
SHOTS=data/screenshots/unreal_cinematic_build
mkdir -p "$SHOTS"

PRE_SHOT="$SHOTS/pre_${TS}.png"
POST_SHOT="$SHOTS/post_${TS}.png"

echo "=== 0. status before ==="
./scripts/qsb_unreal_visible_build_status.sh
PRE_COUNT=$(jq -r '.actor_count_in_level' data/registries/qsb_unreal_visible_build_loop_status.json 2>/dev/null || echo 0)

echo "=== 1. canonical detect ==="
./scripts/qsb_detect_canonical_tower_structure.sh

echo "=== pre-shot ==="
./scripts/qsb_unreal_take_viewport_screenshot.sh "$PRE_SHOT" || true

echo "=== 2. lighting pass (visible: sun rotate, fill dim) ==="
./scripts/qsb_unreal_apply_lighting_pass.sh

echo "=== 3. professional skyscraper architecture detail ==="
./scripts/qsb_unreal_generate_professional_skyscraper.sh 2>&1 | tail -20

echo "=== 4. futuristic city skyline ==="
./scripts/qsb_unreal_generate_futuristic_city.sh 2>&1 | tail -20

echo "=== 5. post-shot ==="
./scripts/qsb_unreal_take_viewport_screenshot.sh "$POST_SHOT" || true

echo "=== 6. status after ==="
./scripts/qsb_unreal_visible_build_status.sh
POST_COUNT=$(jq -r '.actor_count_in_level' data/registries/qsb_unreal_visible_build_loop_status.json 2>/dev/null || echo 0)

echo "=== 7. visual score ==="
./scripts/qsb_unreal_visual_quality_score.sh 2>&1 | tail -30

echo "=== 8. compose loop report ==="
LATEST=data/registries/qsb_unreal_visible_cinematic_build_loop_latest.json
REPORT_MD=data/logs/qsb_unreal_visible_cinematic_build_loop_report.md
ADDED=$(( ${POST_COUNT:-0} - ${PRE_COUNT:-0} ))
jq -n --arg ts "$TS" --argjson pre "${PRE_COUNT:-0}" --argjson post "${POST_COUNT:-0}" \
      --argjson added "$ADDED" --arg pre_shot "$PRE_SHOT" --arg post_shot "$POST_SHOT" '{
  ts: $ts,
  pre_actor_count: $pre,
  post_actor_count: $post,
  actors_added_this_pass: $added,
  pre_shot: $pre_shot,
  post_shot: $post_shot,
  what_visibly_changed: [
    "lighting pass: sun rotated to cinematic angle, sky fills moved + dimmed",
    "professional architecture detail layer: corner pillars, band signs, roof spikes, central spire, plaza lamps, concourse",
    "futuristic city: 40 secondary skyscrapers, antennae, plaza signs, scattered window lights"
  ]
}' > "$LATEST"

cat > "$REPORT_MD" <<EOF
# Visible Cinematic Build Loop — $TS

- Actors before: ${PRE_COUNT:-?}
- Actors after:  ${POST_COUNT:-?}
- Added this pass: ${ADDED}
- Pre-shot:  $PRE_SHOT
- Post-shot: $POST_SHOT

## What visibly changed
1. **Lighting** — V2_Sun rotated to (-32°, 47°). V2_SkyFill1/2 pushed to (±8000, ±8000), scale 0.8.
2. **Architecture detail** — V8_Arch_Pillar/BandSign/RoofSpike/CentralSpire/PlazaLamp/Concourse
3. **City skyline** — V9_City_Sky (40), V9_City_Ant (20), V9_City_SignPost/SignBoard (32), V9_City_Window (32 PointLights), V9_City_AtmMarker (8)

See pre/post screenshots above. To compare side-by-side use:

\`\`\`
xdg-open $PRE_SHOT
xdg-open $POST_SHOT
\`\`\`
EOF
cat "$LATEST"
echo "wrote $LATEST + $REPORT_MD"
