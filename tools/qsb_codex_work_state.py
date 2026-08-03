#!/usr/bin/env python3
"""Publish factual Floor 40 interactive work state; never infers or fabricates activity."""
import argparse, datetime, json, os
from pathlib import Path
ROOT=Path("/vaults/nvme0/qsb_tower_v1")
OUT=Path(os.environ.get("QSB_CODEX_WORK_STATE_PATH", str(ROOT/"data/registries/qsb_codex_floor40_current_job.json")))
STAGES=("TASK RECEIVED","RESEARCH","PLAN","LOCAL WORK","FILE OR ARTIFACT","TEST","RESULT","VERIFICATION","COMPLETE","IDLE","BLOCKED")
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
def main():
 p=argparse.ArgumentParser(); p.add_argument("stage",choices=STAGES); p.add_argument("--task-id",required=True); p.add_argument("--task",required=True); p.add_argument("--file-inspected"); p.add_argument("--file-modified"); p.add_argument("--tool"); p.add_argument("--blocker"); p.add_argument("--output"); p.add_argument("--test-status",default="NOT RUN"); p.add_argument("--evidence",action="append",default=[]); a=p.parse_args()
 old={}
 try: old=json.loads(OUT.read_text(encoding="utf-8"))
 except Exception: pass
 started=old.get("start_time") if old.get("task_id")==a.task_id else now(); active=a.stage not in ("COMPLETE","IDLE","BLOCKED")
 state={"schema":"qsb_codex_floor40_work/v1","principal_identity":"codex","physical_hostname":os.uname().nodename,"task_id":a.task_id,"current_task":a.task,"work_status":"WORKING" if active else a.stage,"start_time":started,"current_stage":a.stage,"stage_sequence":list(STAGES[:9]),"file_being_inspected":a.file_inspected,"file_being_modified":a.file_modified,"tool_being_used":a.tool,"current_blocker":a.blocker,"latest_output":a.output,"test_status":a.test_status,"evidence":a.evidence,"completion_status":a.stage if not active else "IN PROGRESS","active":active,"updated_at":now()}
 OUT.parent.mkdir(parents=True,exist_ok=True); tmp=OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8"); os.replace(tmp,OUT); print(json.dumps(state))
if __name__=="__main__": main()
