#!/usr/bin/env bash
# qsb_unreal_visual_quality_score.sh — honest score from 0-10 per category.
# Score reflects current scaffolded state (NOT promotional).
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
JSON=data/registries/qsb_unreal_visual_quality_score_latest.json
MD=data/logs/qsb_unreal_visual_quality_score_report.md
mkdir -p data/registries data/logs

# Pull live signals
ACTOR_COUNT=$(jq -r '.actor_count_in_level // "0"' data/registries/qsb_unreal_visible_build_loop_status.json 2>/dev/null || echo 0)
HAS_TIKTOK_FRAMES=$(ls references/visual_targets/tiktok_skyscraper_reference/*.png references/visual_targets/tiktok_skyscraper_reference/*.jpg references/visual_targets/tiktok_skyscraper_reference/*.mp4 2>/dev/null | wc -l)
HAS_MATERIALS=0  # plugin can't create — assume 0 until UE Python ran
HAS_LIGHTING_PASS=0
[[ -f data/registries/qsb_unreal_lighting_pass_status.json ]] && HAS_LIGHTING_PASS=1
HAS_HUD_IN_UE=0  # no UMG widgets yet

# Honest scoring — these are deliberately low while the look is a blockout
TOWER_SILHOUETTE=5     # helix shape + crown + spire = recognizable
MATERIAL_QUALITY=$(( HAS_MATERIALS * 5 ))
LIGHTING_QUALITY=$(( 2 + HAS_LIGHTING_PASS ))  # rebuild pending
CITY_BACKGROUND=6      # secondary skyline + 40+ towers added
HUD_PROFESSIONAL=$HAS_HUD_IN_UE     # nothing in-engine yet (browser is separate)
LIFT_VISIBILITY=4      # shafts done, no cabs animated
WORKER_VISIBILITY=3    # beacons only, no avatars
FLOOR_DETAIL=3         # slabs are flat, no rooms
MOTION_ANIMATION=4     # live pulse moves a few actors; no cabs
CINEMATIC_CAMERA=2     # static focus_viewport only
SIMILARITY_TO_TARGET=$(( HAS_TIKTOK_FRAMES > 0 ? 4 : 2 ))  # can only judge if frames exist
OVERALL=3              # blockout level

cat > "$JSON" <<EOF
{
  "ts": "${TS_UTC}",
  "scene_actor_count": ${ACTOR_COUNT},
  "tiktok_reference_frames_count": ${HAS_TIKTOK_FRAMES},
  "scores_0_10": {
    "tower_silhouette":     ${TOWER_SILHOUETTE},
    "material_quality":     ${MATERIAL_QUALITY},
    "lighting_quality":     ${LIGHTING_QUALITY},
    "city_background":      ${CITY_BACKGROUND},
    "hud_professional":     ${HUD_PROFESSIONAL},
    "lift_visibility":      ${LIFT_VISIBILITY},
    "worker_visibility":    ${WORKER_VISIBILITY},
    "floor_detail":         ${FLOOR_DETAIL},
    "motion_animation":     ${MOTION_ANIMATION},
    "cinematic_camera":     ${CINEMATIC_CAMERA},
    "similarity_to_target": ${SIMILARITY_TO_TARGET},
    "overall_professional": ${OVERALL}
  },
  "verdict": "still a blockout — no materials, no Unreal HUD, no animated cabs, no cinematic camera. Tower silhouette + helix + city ring are the only things that have moved above 5."
}
EOF

cat > "$MD" <<EOF
# Visual Quality Score — $TS_UTC

Honest 0-10 per category. **This scene is a blockout, not a final.**

| Category | Score | Why |
|---|---:|---|
| Tower silhouette | $TOWER_SILHOUETTE | helix + crown + spire are visible |
| Material quality | $MATERIAL_QUALITY | every surface is grey BasicShapes default |
| Lighting quality | $LIGHTING_QUALITY | rebuild pending, atmosphere recipe written but not run |
| City background | $CITY_BACKGROUND | 24 + 40 background towers, antennae, signs |
| HUD professional | $HUD_PROFESSIONAL | no UMG widgets in editor yet |
| Lift visibility | $LIFT_VISIBILITY | shafts placed, no cabs |
| Worker visibility | $WORKER_VISIBILITY | beacons per floor, no avatars |
| Floor detail | $FLOOR_DETAIL | flat slabs |
| Motion / animation | $MOTION_ANIMATION | live pulse moves a few actors, no cabs |
| Cinematic camera | $CINEMATIC_CAMERA | static focus_viewport |
| Similarity to target | $SIMILARITY_TO_TARGET | ${HAS_TIKTOK_FRAMES} reference frames in folder |
| **Overall professional** | **$OVERALL** | blockout |

## How to improve each score

- **Material → 5+**: author 11 Materials via UE Python (recipe at `/tmp/qsb_ue_material_pass.py` after `scripts/qsb_unreal_apply_cinematic_material_pass.sh`); then iterate actors with set_material per name pattern.
- **Lighting → 6+**: run lighting recipe inside editor Python console (adds SkyAtmosphere + Fog + Build Lighting).
- **HUD → 5+**: author UMG widgets via UE Python; bind to QSB registries.
- **Lift → 7**: spawn lift cabs (small bright cubes) + ticker that calls set_actor_transform on Z each second.
- **Floor detail → 6**: per-floor interior cube clusters via UE Python (need to populate /Game/QSB/Floors).
- **Cinematic camera → 7**: Sequencer asset + camera dolly track.
- **Similarity → 7+**: place reference frames in `references/visual_targets/tiktok_skyscraper_reference/`.
EOF

echo "wrote: $JSON"
echo "wrote: $MD"
cat "$JSON"
