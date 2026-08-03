#!/usr/bin/env python3
"""Bounded, paper-only cohort refresh used by the evolution heartbeat."""
import json, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; STATE=ROOT/'data/registries/qsb_training_refresh_state.json'
now=time.time(); last=0
try:last=float(json.loads(STATE.read_text()).get('last_epoch',0))
except Exception:pass
if now-last < 6*3600:
    print(json.dumps({'skipped':'cooldown','age_seconds':round(now-last)})); raise SystemExit(0)
cmd=['python3','tools/qsb_train_and_trade_cohort.py','--cohort','10','--instrument','EUR_USD','--venue','oanda_practice','--units','10','--dry-run']
r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=180)
STATE.write_text(json.dumps({'last_epoch':now,'last_rc':r.returncode,'mode':'dry-run','cohort':10,'instrument':'EUR_USD'},indent=2)+'\n')
print(json.dumps({'ran':True,'rc':r.returncode,'tail':r.stdout[-300:]})); raise SystemExit(r.returncode)
