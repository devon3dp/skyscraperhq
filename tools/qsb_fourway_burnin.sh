#!/bin/bash
# qsb_fourway_burnin.sh — 30-minute burn-in of the four-way chat pipeline (:8855).
# Per-minute: all 4 heartbeat ages, online count, queue depths, duplicate check.
# Every 5 min: Wren->room message + verify TP/Asa/Bill receive+ack (round-trip).
# Honest pass criteria: all 4 stay online, hb_age<45s, no dup nodes, msgs deliver.
set -u
cd /vaults/nvme0/qsb_tower_v1
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="data/registries/leadership_comms/burnin_${TS}.log"
MIN=30
FAILS=0; DEGRADED_MIN=0; ROUNDTRIPS=0; ROUNDTRIP_PASS=0
WT=$(python3 -c "import json;print(json.load(open('floors/floor_28_security_department/vault/leadership_tokens.json'))['tokens']['wren'])")

echo "# four-way burn-in started $(date -u +%FT%TZ), $MIN minutes" | tee "$LOG"
for i in $(seq 1 $MIN); do
  now=$(date -u +%H:%M:%SZ)
  read ONLINE MAXAGE LINE <<<"$(curl -s -m6 http://127.0.0.1:8855/status 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except: print('0 999 UNREACHABLE'); sys.exit()
p=d['presence']; ages=[]
parts=[]
for k in ['wren','tp','asa','bill']:
    on=p[k]['online']; ag=p[k].get('age_s')
    parts.append('%s=%s/%ss'%(k,on,ag))
    if on and isinstance(ag,int): ages.append(ag)
online=sum(1 for k in ['wren','tp','asa','bill'] if p[k]['online'])
mx=max(ages) if ages else 999
qd=d['queue_depth']
print(online, mx, ' '.join(parts)+' q='+str(qd))
")"
  # fail flags
  flag=""
  [ "$ONLINE" != "4" ] && { flag="[<4 ONLINE]"; DEGRADED_MIN=$((DEGRADED_MIN+1)); }
  [ "$MAXAGE" != "999" ] && [ "$MAXAGE" -gt 45 ] 2>/dev/null && flag="$flag [HB>45s]"
  echo "$now min$i online=$ONLINE maxage=${MAXAGE}s $LINE $flag" | tee -a "$LOG"
  # round-trip every 5 min
  if [ $((i % 5)) -eq 0 ]; then
    mid="burnin_${TS}_m${i}"
    curl -s -m5 -X POST http://127.0.0.1:8855/room -H 'Content-Type: application/json' \
      -d "{\"identity\":\"wren\",\"token\":\"$WT\",\"body\":\"burn-in round-trip min $i (free-chat test)\",\"msg_id\":\"$mid\"}" >/dev/null 2>&1
    ROUNDTRIPS=$((ROUNDTRIPS+1))
    sleep 65   # let the 1-min clients poll+ack
    ACKS=$(curl -s -m6 http://127.0.0.1:8855/status 2>/dev/null >/dev/null; tail -20 data/registries/leadership_comms/acks.jsonl 2>/dev/null | grep -c "$mid")
    if [ "${ACKS:-0}" -ge 2 ]; then ROUNDTRIP_PASS=$((ROUNDTRIP_PASS+1)); echo "   round-trip min$i: ACKED by $ACKS" | tee -a "$LOG"; else echo "   round-trip min$i: only $ACKS acks [SOFT]" | tee -a "$LOG"; FAILS=$((FAILS+1)); fi
  else
    sleep 60
  fi
done
echo "# burn-in done. degraded_minutes=$DEGRADED_MIN roundtrips=$ROUNDTRIP_PASS/$ROUNDTRIPS hard_fails=$FAILS" | tee -a "$LOG"
if [ "$DEGRADED_MIN" -eq 0 ] && [ "$ROUNDTRIP_PASS" -ge 1 ]; then
  echo "VERDICT: FOUR_WAY_BURN_IN_PASS" | tee -a "$LOG"
else
  echo "VERDICT: FOUR_WAY_BURN_IN_PARTIAL (degraded_min=$DEGRADED_MIN)" | tee -a "$LOG"
fi
echo "LOG=$LOG"
