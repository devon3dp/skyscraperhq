#!/usr/bin/env bash
# qsb_unreal_data_bridge_status.sh — print bridge state
# Per Ross spec Stage 9.
SNAPSHOT="/vaults/nvme0/qsb_unreal_skyscraper/Saved/QSB/qsb_live_snapshot.json"
if [ ! -f "$SNAPSHOT" ]; then
    echo "NO SNAPSHOT at $SNAPSHOT"
    exit 1
fi
echo "SNAPSHOT:     $SNAPSHOT"
echo "SIZE:         $(stat -c%s "$SNAPSHOT" 2>/dev/null) bytes"
echo "LAST REFRESH: $(stat -c%y "$SNAPSHOT" 2>/dev/null)"
echo ""
python3 << PYEOF
import json
with open("$SNAPSHOT") as f:
    d = json.load(f)
print(f"FLOORS: {len(d['tower']['floors'])} (canonical={d['tower']['canonical_floor_count']})")
print("FIRST 3 FLOORS:")
for fl in d['tower']['floors'][:3]:
    print(f"  Floor {fl['n']:>3}: {fl['name'][:30]:<30}  archetype={fl['archetype']}")
t = d['trading']
print(f"\nTRADING: {t['convergence_fire_count']}/{t['convergence_total']} firing, "
      f"PnL today=£{t['today_pnl']:.2f}, opens={t['open_positions_count']}")
print(f"WORKERS: {d['workers']['active']} active / {d['workers']['total_unique']} unique")
print(f"SMOKE:   {d['smoke_tests']['passed']} passed / {d['smoke_tests']['failed']} failed / {d['smoke_tests']['total']} total")
print(f"EVENTS:  {len(d['events'])} latest")
print(f"VOICE:   wake='{d['voice_state']['wake_word']}', engine={d['voice_state']['engine']}")
PYEOF
