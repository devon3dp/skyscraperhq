#!/usr/bin/env bash
# qsb_detect_canonical_tower_structure.sh — detect the canonical floor count and surface stale claims.
# Output: data/registries/qsb_canonical_tower_structure_latest.json + data/logs/qsb_canonical_tower_structure_report.md

set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1

TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT_JSON=data/registries/qsb_canonical_tower_structure_latest.json
OUT_MD=data/logs/qsb_canonical_tower_structure_report.md
mkdir -p data/registries data/logs

# Authoritative source: floors/*/floor_card.json
FC_COUNT=$(find floors -maxdepth 2 -name floor_card.json 2>/dev/null | wc -l)
FLOOR_DIR_COUNT=$(ls -1d floors/floor_*/ 2>/dev/null | wc -l)
MIN_FLOOR=$(ls floors 2>/dev/null | grep '^floor_' | sed 's/^floor_\([0-9]*\)_.*/\1/' | sort -n | head -1)
MAX_FLOOR=$(ls floors 2>/dev/null | grep '^floor_' | sed 's/^floor_\([0-9]*\)_.*/\1/' | sort -n | tail -1)

# Secondary sources — look for any numeric "floor_count" or "total_floors" in registry JSONs
GREP_HITS=$(grep -rEo '"(floor_count|total_floors|n_floors|num_floors)"[[:space:]]*:[[:space:]]*[0-9]+' data/registries 2>/dev/null | sort -u)

CANONICAL=$FC_COUNT

# Stale/conflicting claims = anything that mentions a count != $CANONICAL
STALE=$(echo "$GREP_HITS" | grep -vE "[[:space:]]+${CANONICAL}\$" | head -20)

cat > "$OUT_JSON" <<EOF
{
  "ts": "${TS_UTC}",
  "canonical_floor_count": ${CANONICAL},
  "source": "floors/*/floor_card.json count",
  "floor_card_count": ${FC_COUNT},
  "floor_dir_count": ${FLOOR_DIR_COUNT},
  "min_floor_index": ${MIN_FLOOR:-0},
  "max_floor_index": ${MAX_FLOOR:-0},
  "stale_or_conflicting_hits": $(printf '%s' "$STALE" | jq -Rsc 'split("\n") | map(select(length > 0))')
}
EOF

cat > "$OUT_MD" <<EOF
# Canonical Tower Structure — ${TS_UTC}

- **Canonical floor count:** ${CANONICAL}
- **Authoritative source:** \`floors/<floor_NN_*>/floor_card.json\` (one card per floor)
- floor_card.json files found: ${FC_COUNT}
- floors/floor_* directories: ${FLOOR_DIR_COUNT}
- Floor index range: ${MIN_FLOOR:-?} .. ${MAX_FLOOR:-?}

## All "floor_count / total_floors / n_floors" mentions in registries

\`\`\`
$(printf '%s' "$GREP_HITS")
\`\`\`

## Stale / conflicting (non-canonical) hits

\`\`\`
$(printf '%s' "$STALE")
\`\`\`

## Rule

Every Unreal tower generator must read ${OUT_JSON} for the canonical count, not hardcode 169 or any other value.
EOF

echo "canonical floor count: ${CANONICAL}"
echo "wrote: ${OUT_JSON}"
echo "wrote: ${OUT_MD}"
