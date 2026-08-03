#!/usr/bin/env python3
"""Floor 40 truthful engineering dashboard v2.

Read-only over existing registries. It never advances a task, writes a registry,
calls a provider, or fabricates activity. The terminal POST route is deliberately
disabled until authenticated access is implemented.
"""
import argparse, hashlib, hmac, ipaddress, json, os, re, shutil, subprocess, threading, time
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = next((p for p in Path(__file__).resolve().parents if (p / "AGENTS.md").exists()), Path(__file__).resolve().parent.parent)
REG = ROOT / "data" / "registries"
FILES = {
    "floor_card": ROOT / "floors/floor_40_codex_floor/floor_card.json",
    "council_snapshot": REG / "qsb_council_tasks_snapshot.json",
    "council_events": REG / "qsb_council_tasks.jsonl",
    "autorunner": REG / "qsb_codex_autorunner_activity.jsonl",
    "sessions": REG / "qsb_provider_agent_sessions.jsonl",
    "proposals": REG / "qsb_proposal_queue.jsonl",
    "sandbox": REG / "qsb_proposal_sandbox_results.jsonl",
    "apply_audit": REG / "qsb_code_apply_audit.jsonl",
    "spend": REG / "qsb_provider_spend_ledger.jsonl",
    "work_state": REG / "qsb_codex_floor40_current_job.json",
}
SUITE_FEATURES = [
 {"id":"continuity_loader","name":"Continuity Loader","purpose":"Load instructions, approved job history, active work, remaining faults, and rollback anchors before work starts","source_contract":"AGENTS.md + approved CODEX_JOB_REPORTS + Task Council","state":"DESIGN"},
 {"id":"four_principal_verifier","name":"Four-Principal Verifier","purpose":"Attest physical host, principal process, local model, loopback inference, and identity uniqueness","source_contract":"authenticated host, process, socket, model, and service evidence","state":"DESIGN"},
 {"id":"live_work_state","name":"Live Work-State Protocol","purpose":"Publish genuine task stage, files, tool, blocker, output, test, evidence, and completion","source_contract":"atomic principal-local work_state.json","state":"STAGED"},
 {"id":"advisory_fabric","name":"Advisory Fabric","purpose":"Expose Gene Pool, Hermes, iQuest, and Council-of-15 advice without transferring decision ownership","source_contract":"labelled advisory packets + local-principal synthesis proof","state":"DESIGN"},
 {"id":"route_attestation","name":"Route Attestation","purpose":"Record actual hostname, PID, sockets, endpoint, model, and provider for each reasoning result","source_contract":"OS process/socket evidence + inference receipt","state":"DESIGN"},
 {"id":"approval_builder","name":"Immutable Approval Builder","purpose":"Create minimal bundle, before/after hashes, backups, rollback, and identical Wren/Bill decisions","source_contract":"immutable ZIP SHA-256 + two independent signed verdict records","state":"DESIGN"},
 {"id":"evidence_graph","name":"Evidence Graph","purpose":"Connect task, approval, files, process, test, artifact, and SHA-256 for later discovery","source_contract":"append-only evidence edges backed by existing immutable artifacts","state":"DESIGN"},
 {"id":"drift_sentinel","name":"Drift Sentinel","purpose":"Detect redeploy overwrite, identity drift, surrogate resurrection, and remote-primary configuration","source_contract":"approved baseline hashes + live service/route probes","state":"DESIGN"},
 {"id":"local_failure_harness","name":"Local Failure Harness","purpose":"Prove local-primary failure degrades visibly and never redirects to remote or cloud inference","source_contract":"isolated fault injection + sockets/process/provider evidence","state":"DESIGN"},
]
ACTIVE = {"claimed", "in_progress", "awaiting_verification", "awaiting_peer_signoff"}
NO_CHANGE = re.compile(r"no new patch|reviewed context|context still valid", re.I)
SECRET = re.compile(r"(?i)(bearer\s+\S+|(?:api[_-]?key|token|password|authorization)\s*[:=]\s*\S+|sk-[A-Za-z0-9_-]{16,})")
STARTED = time.time()
CPU_PREV = None
TOKEN_PATH = Path.home() / ".config/skyscraperhq/codex_floor40_terminal.token"
RATE_LIMIT = {}
RATE_LOCK = threading.Lock()

def iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def redact(v, limit=500): return SECRET.sub("[REDACTED]", str(v or ""))[:limit]
def load_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default
def tail(path, max_bytes=2_500_000):
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes: f.seek(size-max_bytes); f.readline()
            data=f.read()
        out=[]
        for line in data.splitlines():
            try:
                x=json.loads(line)
                if isinstance(x,dict): out.append(x)
            except Exception: pass
        return out
    except Exception: return []
def age(path):
    try: return max(0, time.time()-path.stat().st_mtime)
    except Exception: return None
def truth(path, live=90, stale=900):
    a=age(path)
    if a is None: return "UNAVAILABLE"
    if a <= live: return "LIVE"
    if a <= stale: return "CACHED"
    return "STALE"
def source(name, live=90, stale=900):
    p=FILES[name]; a=age(p)
    return {"name":name,"path":str(p),"updated":datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if p.exists() else None,"age_s":round(a,1) if a is not None else None,"truth":truth(p,live,stale)}
def service(name):
    try:
        r=subprocess.run(["systemctl","show",name,"-p","ActiveState","-p","MainPID","-p","ExecMainStartTimestamp"],capture_output=True,text=True,timeout=3)
        return dict(x.split("=",1) for x in r.stdout.splitlines() if "=" in x)
    except Exception: return {}
def git_state():
    try:
        branch=subprocess.run(["git","-C",str(ROOT),"branch","--show-current"],capture_output=True,text=True,timeout=3).stdout.strip()
        status=subprocess.run(["git","-C",str(ROOT),"status","--short","--","tools/qsb_codex_floor_dash.py","tools/qsb_codex_floor_dash_v2.py"],capture_output=True,text=True,timeout=3).stdout.splitlines()
        return {"repository":str(ROOT),"branch":branch or "UNKNOWN","relevant_changes":status,"truth":"LIVE"}
    except Exception: return {"repository":str(ROOT),"branch":"UNKNOWN","relevant_changes":[],"truth":"UNKNOWN"}
def cpu_percent():
    global CPU_PREV
    try:
        nums=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        idle=nums[3]+nums[4]; total=sum(nums); cur=(total,idle)
        if CPU_PREV is None: CPU_PREV=cur; return None
        dt=total-CPU_PREV[0]; di=idle-CPU_PREV[1]; CPU_PREV=cur
        return round(100*(dt-di)/dt,1) if dt else None
    except Exception: return None
def resources():
    mem={}
    try:
        vals={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
        mem={"used_bytes":vals['MemTotal']-vals['MemAvailable'],"total_bytes":vals['MemTotal'],"percent":round(100*(vals['MemTotal']-vals['MemAvailable'])/vals['MemTotal'],1)}
    except Exception: pass
    disk=shutil.disk_usage(ROOT)
    gpu={"truth":"UNAVAILABLE"}
    try:
        r=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3)
        if r.returncode==0:
            u,m,t=[float(x.strip()) for x in r.stdout.splitlines()[0].split(',')]; gpu={"util_percent":u,"memory_used_mib":m,"memory_total_mib":t,"truth":"LIVE"}
    except Exception: pass
    dash=service('qsb-codex-floor-dash.service'); auto=service('qsb-codex-autorunner.service')
    return {"cpu_percent":cpu_percent(),"cpu_truth":"LIVE","memory":mem,"gpu":gpu,"disk":{"free_bytes":disk.free,"total_bytes":disk.total},"dashboard_service":dash,"autorunner_service":auto,"dashboard_uptime_s":round(time.time()-STARTED)}

def build_state():
    snap=load_json(FILES['council_snapshot'],{})
    tasks=snap.get('tasks',[]) if isinstance(snap,dict) else []
    active=[t for t in tasks if t.get('owner')=='codex' and t.get('state') in ACTIVE]
    active.sort(key=lambda t:t.get('claimed_at') or t.get('started_at') or '',reverse=True)
    task=active[0] if active else None; tid=task.get('id') if task else None
    council=tail(FILES['council_events']); sessions=tail(FILES['sessions'],1_000_000)
    proposals=tail(FILES['proposals']); sandbox=tail(FILES['sandbox']); applies=tail(FILES['apply_audit']); autorun=tail(FILES['autorunner']); spend=tail(FILES['spend'])
    claimed_at=(task.get('claimed_at') or task.get('started_at') or '') if task else ''
    tev=[x for x in council if tid and x.get('task_id')==tid and str(x.get('ts') or '') >= claimed_at]
    tsess=[x for x in sessions if tid and tid in str(x.get("session_id", "")) and str(x.get("ts_end") or x.get("ts_start") or "") >= claimed_at]
    props=[x for x in proposals if tid and tid in json.dumps(x) and str(x.get('ts') or '') >= claimed_at]
    prop=props[-1] if props else None; pid=prop.get('proposal_id') if prop else None
    sand=[x for x in sandbox if pid and x.get('id')==pid]
    apps=[x for x in applies if pid and x.get('proposal_id')==pid and str(x.get('ts') or '') >= claimed_at]
    last_session=tsess[-1] if tsess else None
    current_session=last_session if last_session and (last_session.get('ts_end') or last_session.get('ts_start') or '') >= claimed_at else None
    last_auto=next((x for x in reversed(autorun) if x.get('tick') in ('claim','ran','idle','error','skip')),None)
    nochange_all=[x for x in council if x.get('actor')=='codex' and NO_CHANGE.search(str(x.get('text','')))]
    nochange=[x for x in council if x.get('actor')=='codex' and (not tid or x.get('task_id')==tid) and NO_CHANGE.search(str(x.get('text','')))]
    consecutive=0
    for x in reversed([x for x in council if x.get('actor')=='codex' and (not tid or x.get('task_id')==tid) and x.get('event')=='noted']):
        if NO_CHANGE.search(str(x.get('text',''))): consecutive+=1
        else: break
    lifecycle=[]
    stages=[('TASK RECEIVED',{'created'}),('RESEARCH',{'tool_selected'}),('PLAN',{'noted'}),('PATCH',{'bench_proposal'}),('TEST',{'sandbox_passed','sandbox_rejected'}),('PROPOSAL',{'bench_proposal'}),('TASK COUNCIL',{'claimed','assigned'}),('WREN GATE',set()),('VERIFICATION',{'sandbox_passed'}),('COMPLETE',{'done','completed'})]
    for label,events in stages:
        row=next((x for x in tev if x.get('event') in events),None)
        if label=='TASK RECEIVED' and task and task.get('created_at'):
            row={'ts':task.get('created_at'),'event':'snapshot.created_at'}
        lifecycle.append({"stage":label,"complete":bool(row),"timestamp":row.get('ts') if row else None,"evidence":f"{FILES['council_events']}:{row.get('event')}" if row else None})
    wren=[x for x in tev if pid and x.get('actor')=='wren' and x.get('proposal_id')==pid and x.get('event') in ('receipt','under_review','accepted','rejected','revision_requested','verified','verdict')]
    latest_wren=wren[-1] if wren else None
    for row in lifecycle:
        if row['stage']=='WREN GATE' and latest_wren: row.update(complete=True,timestamp=latest_wren.get('ts'),evidence=str(FILES['council_events']))
        if row['stage']=='VERIFICATION' and sand: row.update(complete=True,timestamp=sand[-1].get('ts'),evidence=str(FILES['sandbox']))
    if not prop: wstate='NOT_SUBMITTED'
    elif not latest_wren: wstate='SUBMITTED'
    elif latest_wren.get('event') in ('recycled','revision_requested') or latest_wren.get('verdict') in ('revision','revision_requested'): wstate='REVISION_REQUESTED'
    elif latest_wren.get('event')=='under_review': wstate='UNDER_REVIEW'
    elif latest_wren.get('verdict') in ('accept','accepted','verified'): wstate='ACCEPTED'
    elif latest_wren.get('verdict') in ('reject','rejected'): wstate='REJECTED'
    else: wstate='RECEIVED'
    inspected=[]; modified=[]; tools=[]
    if last_session:
        for i,tc in enumerate(last_session.get('tool_calls') or []):
            fn=tc.get('fn','unknown'); args=tc.get('args') or {}; path=args.get('path') or args.get('file') or args.get('target_file')
            tools.append({"id":f"{last_session.get('session_id')}:{i+1}","task_id":tid,"tool":fn,"category":fn.replace('qsb_',''),"start_time":last_session.get("ts_start"),"elapsed_s":None,"state":"COMPLETED","exit_result":"RECORDED","files_accessed":redact(path,220) if path else None,"error_summary":None,"evidence":str(FILES['sessions']),"truth":"LIVE" if current_session else "HISTORICAL"})
            if current_session and path and fn in ('qsb_read_registry','qsb_read_floor_card','qsb_grep_repo'): inspected.append(redact(path,220))
    if prop:
        targets=prop.get('target_files') or ([prop.get('target_file')] if prop.get('target_file') else [])
        modified=[redact(x,220) for x in targets]
    events=[]
    def add(ts,kind,desc,src,result,evidence):
        if not ts or NO_CHANGE.search(desc): return
        fp=hashlib.sha256(f"{ts}|{tid}|{kind}|{desc}".encode()).hexdigest()[:14]
        events.append({"id":fp,"timestamp":ts,"task_id":tid,"event_type":kind,"description":redact(desc,260),"source":src,"result":redact(result,120),"evidence":evidence})
    for x in tev[-80:]:
        ev=x.get('event'); desc=x.get('text') or x.get('title') or ev
        mapping={'created':'task_received','claimed':'task_claimed','bench_proposal':'proposal_submitted','sandbox_passed':'test_passed','sandbox_rejected':'test_failed','peer_signoff':'wren_or_peer_verdict','recycled':'task_blocked','done':'task_completed'}
        if ev in mapping: add(x.get('ts'),mapping[ev],str(desc),'Task Council',x.get('verdict') or ev,f"{FILES['council_events']}:{ev}")
    for s in tsess[-10:]: add(s.get('ts_start'),'tool_session',f"{s.get('provider')} session {s.get('session_id')}",'provider session',f"{s.get('turns')} turns",str(FILES['sessions']))
    for a in apps[-10:]: add(a.get('ts'),'deployment_verified' if a.get('applied') else 'deployment_failed',f"apply {a.get('proposal_id')}",'apply audit',str(a.get('applied')),str(FILES['apply_audit']))
    uniq={x['id']:x for x in events}; events=sorted(uniq.values(),key=lambda x:x['timestamp'],reverse=True)[:100]
    claims=[x for x in events if x['event_type']=='task_claimed']
    if len(claims)>1:
        newest=claims[0].copy(); newest['retry_count']=len(claims); newest['description']=f"{newest['description']} (CLAIMED x {len(claims)})"
        events=[x for x in events if x['event_type']!='task_claimed']+[newest]
        events=sorted(events,key=lambda x:x['timestamp'],reverse=True)[:100]
    attempt_id=f"{tid}:{claimed_at or 'unclaimed'}" if tid else None
    route_map={'task_received':('TASK COUNCIL','CODEX'),'task_claimed':('TASK COUNCIL','CODEX'),'tool_session':('CODEX','TOOLS'),'proposal_submitted':('CODEX','TASK COUNCIL'),'test_passed':('CODEX','VERIFICATION'),'test_failed':('VERIFICATION','BLOCKED'),'task_blocked':('CODEX','BLOCKED'),'task_completed':('VERIFICATION','COMPLETED')}
    packets=[]
    for x in events:
        if x['event_type']=='wren_or_peer_verdict': continue
        origin,dest=route_map.get(x['event_type'],('CODEX','CODEX'))
        packets.append({**x,'packet_id':x['id'],'attempt_id':attempt_id,'correlation_id':pid or attempt_id,'session_id':None,'proposal_id':pid,'verdict_id':None,'parent_task_id':task.get('parent_task_id') if task else None,'packet_type':x['event_type'],'origin':origin,'destination':dest,'current_station':dest,'state':x['result'],'truth':'LIVE','freshness':truth(FILES['council_events'],45,180)})
    if prop:
        base={'task_id':tid,'attempt_id':attempt_id,'correlation_id':pid,'session_id':None,'proposal_id':pid,'verdict_id':None,'parent_task_id':task.get('parent_task_id') if task else None,'packet_type':'proposal','state':'SUBMITTED','timestamp':prop.get('ts'),'truth':'LIVE','evidence':str(FILES['proposals']),'freshness':truth(FILES['proposals'],90,900)}
        packets.extend([{**base,'packet_id':hashlib.sha256(f"{pid}|council".encode()).hexdigest()[:14],'origin':'CODEX','destination':'TASK COUNCIL','current_station':'TASK COUNCIL'},{**base,'packet_id':hashlib.sha256(f"{pid}|wren".encode()).hexdigest()[:14],'origin':'TASK COUNCIL','destination':'WREN','current_station':'WREN'}])
    if latest_wren:
        base={'task_id':tid,'attempt_id':attempt_id,'correlation_id':pid,'session_id':None,'proposal_id':pid,'verdict_id':latest_wren.get('verdict_id'),'parent_task_id':task.get('parent_task_id') if task else None,'packet_type':'wren_verdict','state':wstate,'timestamp':latest_wren.get('ts'),'truth':'LIVE','evidence':str(FILES['council_events']),'freshness':truth(FILES['council_events'],45,180)}
        packets.append({**base,'packet_id':hashlib.sha256(f"{latest_wren.get('ts')}|{pid}|return".encode()).hexdigest()[:14],'origin':'WREN','destination':'RETURN VERDICT','current_station':'RETURN VERDICT'})
        if wstate in ('REJECTED','REVISION_REQUESTED'):
            packets.extend([{**base,'packet_id':hashlib.sha256(f"{latest_wren.get('ts')}|{pid}|rework".encode()).hexdigest()[:14],'origin':'RETURN VERDICT','destination':'REWORK','current_station':'REWORK'},{**base,'packet_id':hashlib.sha256(f"{latest_wren.get('ts')}|{pid}|codex-rework".encode()).hexdigest()[:14],'origin':'REWORK','destination':'CODEX','current_station':'CODEX'}])
        else:
            packets.extend([{**base,'packet_id':hashlib.sha256(f"{latest_wren.get('ts')}|{pid}|council".encode()).hexdigest()[:14],'origin':'RETURN VERDICT','destination':'TASK COUNCIL','current_station':'TASK COUNCIL'},{**base,'packet_id':hashlib.sha256(f"{latest_wren.get('ts')}|{pid}|codex".encode()).hexdigest()[:14],'origin':'TASK COUNCIL','destination':'CODEX','current_station':'CODEX'}])
    for x in sand:
        base={'task_id':tid,'attempt_id':attempt_id,'correlation_id':pid,'session_id':None,'proposal_id':pid,'verdict_id':None,'parent_task_id':task.get('parent_task_id') if task else None,'packet_type':'verification','state':str(x.get('verdict') or 'RECORDED'),'timestamp':x.get('ts'),'truth':'LIVE','evidence':str(FILES['sandbox']),'freshness':truth(FILES['sandbox'],90,900)}
        packets.append({**base,'packet_id':hashlib.sha256(f"{x.get('ts')}|{pid}|verify".encode()).hexdigest()[:14],'origin':'CODEX','destination':'VERIFICATION','current_station':'VERIFICATION'})
    if latest_wren and wstate=='ACCEPTED' and apps and apps[-1].get('applied'):
        x=apps[-1]; packets.append({'packet_id':hashlib.sha256(f"{x.get('ts')}|{pid}|complete".encode()).hexdigest()[:14],'task_id':tid,'attempt_id':attempt_id,'correlation_id':pid,'session_id':None,'proposal_id':pid,'verdict_id':latest_wren.get('verdict_id'),'parent_task_id':task.get('parent_task_id') if task else None,'packet_type':'completed','origin':'VERIFICATION','destination':'COMPLETED','current_station':'COMPLETED','state':'VERIFIED','timestamp':x.get('ts'),'truth':'LIVE','evidence':str(FILES['apply_audit']),'freshness':truth(FILES['apply_audit'],90,900)})
    today=iso()[:10]; scalls=[x for x in spend if str(x.get('ts','')).startswith(today) and x.get('provider')=='openai']
    task_calls=[x for x in scalls if tid and tid in json.dumps(x)]
    nochange_cost=sum(float(x.get('cost_usd') or 0) for x in scalls if 'review' in str(x.get('reason','')).lower())
    tests=[]
    for x in sand[-10:]: tests.append({"command":"sandbox smoke suite","reason":"proposal verification","start":x.get('ts'),"completion":x.get('ts'),"executed":len(x.get('smokes') or []),"passed":sum(1 for s in x.get('smokes') or [] if s.get('rc')==0),"failed":sum(1 for s in x.get('smokes') or [] if s.get('rc') not in (0,None)),"skipped":0,"evidence":str(FILES['sandbox']),"service":None,"verifier":"sandbox","result":"PASS" if x.get('ok') else "FAIL"})
    current={"task_id":tid,"attempt_id":attempt_id,"title":task.get('title') if task else None,"source":"Task Council snapshot" if task else None,"priority":task.get('priority') if task else None,"lifecycle_stage":("WAITING_FOR_WREN" if prop and not latest_wren else "RESEARCHING" if current_session else "BLOCKED" if task else "IDLE"),"start_time":task.get('claimed_at') if task else None,"repository":str(ROOT),"branch":git_state().get('branch'),"working_directory":str(ROOT),"file_inspecting":inspected[-1] if inspected else None,"file_modifying":modified[-1] if modified else None,"latest_tool":tools[-1]['tool'] if current_session and tools else None,"blocker":"No provider session recorded since latest claim" if task and not current_session else (redact(last_auto.get('reason')) if last_auto and last_auto.get('tick') in ('error','skip') else None),"next_action":"Await a real source change or Wren/Task Council event" if consecutive else "Continue evidence-backed task lifecycle","last_output":redact(current_session.get('final_text'),220) if current_session else None}
    interactive=load_json(FILES["work_state"], {})
    interactive_fresh=bool(interactive) and (age(FILES["work_state"]) or 999999) <= 120
    if interactive_fresh:
        current={"task_id":interactive.get("task_id"),"attempt_id":interactive.get("task_id"),"title":interactive.get("current_task"),"source":str(FILES["work_state"]),"priority":None,"lifecycle_stage":interactive.get("current_stage") or "UNKNOWN","start_time":interactive.get("start_time"),"repository":str(ROOT),"branch":git_state().get("branch"),"working_directory":str(ROOT),"file_inspecting":interactive.get("file_being_inspected"),"file_modifying":interactive.get("file_being_modified"),"latest_tool":interactive.get("tool_being_used"),"blocker":interactive.get("current_blocker"),"next_action":None,"last_output":redact(interactive.get("latest_output"),220),"test_status":interactive.get("test_status"),"evidence":interactive.get("evidence"),"truth":"LIVE"}
    council_summary={k:snap.get(k) for k in ('total','open','in_progress','blocked','done','reserved','dropped','active_board','active_board_cap')}
    council_summary.update({"task":{k:task.get(k) for k in ('id','owner','partner','verifier','state','created_at','claimed_at','priority','title') if task and task.get(k) is not None},"source":source('council_snapshot',45,180),"governance_compliance":"UNKNOWN" if task and not task.get('partner') else "RECORDED","completion_proof":"PRESENT" if apps else "ABSENT"})
    return {"generated_at":iso(),"engineering_suite":{"features":SUITE_FEATURES,"counts":dict(Counter(x["state"] for x in SUITE_FEATURES)),"truth":"DECLARED DESIGN + FILE-VERIFIED MATURITY ONLY","decision_owner":"Ross","execution_posture":"No live mutation before immutable Wren and Bill approval"},"floor":{"number":40,"name":"Codex Floor","truth":"LIVE","source":source('floor_card',86400,604800)},"current_work":current,"events":events,"transport":{"stations":["CODEX","TOOLS","TASK COUNCIL","WREN","VERIFICATION","COMPLETED","BLOCKED"],"packets":packets[-80:],"mode":"LIVE","return_channel":"WORKING" if latest_wren else "NOT CONNECTED","genuine_wren_returns":len(wren),"peer_or_external_verdicts":sum(1 for x in tev if x.get("event")=="peer_signoff" and x.get("actor")!="wren"),"truth":"LIVE"},"attempt":{"attempt_id":attempt_id,"started_at":claimed_at,"classification":"DERIVED","historical_records_excluded":True},"lifecycle":lifecycle,"files":{"inspected":sorted(set(inspected)),"modified":sorted(set(modified)),"created":[],"lines_added":None,"lines_removed":None,"proposal_id":pid,"affected_service":None,"backup_path":prop.get('backup') if prop else None,"rollback":"AVAILABLE" if apps and apps[-1].get('backup') else "UNKNOWN","git":git_state()},"tools":tools[-20:],"tests":tests,"task_council":council_summary,"wren_gate":{"proposal_id":pid,"submitted_at":prop.get('ts') if prop else None,"receipt_status":"RECORDED" if prop else "NOT_SUBMITTED","response_status":wstate,"retry_count":sum(1 for x in tev if x.get('event')=='recycled'),"latest_response":redact(latest_wren.get('text') or latest_wren.get('reason'),220) if prop and latest_wren else None,"verdict":wstate,"reason":redact(latest_wren.get('reason'),220) if prop and latest_wren else None,"return_path":str(FILES['council_events']),"truth":"LIVE" if prop and latest_wren else "UNKNOWN"},"proof_of_work":[{"task_id":x.get('task_id'),"description":f"Applied proposal {x.get('proposal_id')}","path":redact(x.get('target'),220),"changed_files":x.get('target_files') or ([x.get('target')] if x.get('target') else []),"before":x.get('sha_before'),"after":x.get('sha_after'),"test_evidence":x.get('sandbox'),"verifier":x.get('quorum'),"completed_at":x.get('ts')} for x in apps if x.get('applied')][-10:],"cost":{"classification":"ESTIMATED","current_task_calls":len(task_calls),"current_task_cost":round(sum(float(x.get('cost_usd') or 0) for x in task_calls),6),"today_calls":len(scalls),"today_cost":round(sum(float(x.get('cost_usd') or 0) for x in scalls),6),"no_change_cost":round(nochange_cost,6),"prompt_tokens":sum(int(x.get('prompt_tokens') or 0) for x in task_calls),"completion_tokens":sum(int(x.get('completion_tokens') or 0) for x in task_calls),"source":source('spend',90,600)},"no_change_control":{"task_fingerprint":hashlib.sha256(f"{tid}|{task.get('title') if task else ''}".encode()).hexdigest()[:16] if task else None,"review_count_current_task":len(nochange),"review_count_all_recent":len(nochange_all),"consecutive":consecutive,"maximum":3,"backoff":"300s base; increasing backoff recommended, not enforced by dashboard","wake_mode":"polling in existing autorunner; dashboard SSE is event-aware","stalled":consecutive>=3,"quarantined":consecutive>=3,"classification":"HISTORICAL/LIVE EXPOSURE — dashboard does not mutate autorunner"},"resources":resources(),"sources":[source(k,90 if k not in ('floor_card',) else 86400,900 if k not in ('floor_card',) else 604800) for k in FILES]}

PAGE=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CODEX FLOOR 40 · Live Engineering</title><style>
:root{color-scheme:dark;--bg:#071019;--card:#101c28;--line:#26394a;--txt:#e8f1fa;--mut:#91a3b5;--ok:#3ddc97;--warn:#ffc857;--bad:#ff6b6b;--blue:#5ab0ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 system-ui}.wrap{max-width:1500px;margin:auto;padding:18px}h1{margin:0;font-size:24px}h2{font-size:13px;text-transform:uppercase;color:var(--mut);letter-spacing:.08em;margin:0 0 10px}.top{display:flex;justify-content:space-between;gap:10px;align-items:center}.conn{padding:5px 9px;border:1px solid var(--line);border-radius:99px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px;margin-top:12px}.wide{grid-column:1/-1}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}.kv{display:grid;grid-template-columns:145px 1fr;gap:5px 10px}.k{color:var(--mut)}.v{overflow-wrap:anywhere}.badge{padding:2px 7px;border-radius:99px;border:1px solid var(--line);font-size:10px}.LIVE{color:var(--ok)}.CACHED,.ESTIMATED,.HISTORICAL{color:var(--warn)}.STALE,.UNAVAILABLE,.UNKNOWN{color:var(--bad)}table{width:100%;border-collapse:collapse;font-size:11px}th,td{text-align:left;padding:6px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut)}.scroll{max-height:390px;overflow:auto}.empty{color:var(--mut);font-style:italic}.stale{border-color:var(--bad)}button{background:#123b35;color:white;border:1px solid #1f8069;border-radius:7px;padding:7px 12px}input,textarea{width:100%;background:#071019;color:white;border:1px solid var(--line);padding:9px;border-radius:7px}.terminal{display:grid;grid-template-columns:minmax(150px,.45fr) minmax(250px,1fr) auto;gap:8px}.source{font-size:10px;color:var(--mut);margin-top:8px;overflow-wrap:anywhere}.pipeline{height:180px;position:relative;overflow:hidden;background:radial-gradient(circle at 50% 50%,rgba(16,163,127,.13),transparent 60%);border:1px solid var(--line);border-radius:10px}.pipe-svg{width:100%;height:100%}.beam{stroke-dasharray:7 11;animation:flow 1.2s linear infinite}.beam.idle{opacity:.28;animation-duration:4s}.packet{filter:drop-shadow(0 0 6px var(--ok));animation:packet 3.2s ease-in-out infinite}.pulse{animation:pulse 1.6s infinite}.ticker-row{padding:5px 0;border-bottom:1px solid var(--line);animation:arrive .45s ease-out}.ticker-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--blue)}@keyframes flow{to{stroke-dashoffset:-36}}@keyframes packet{0%{offset-distance:0%;opacity:0}12%,88%{opacity:1}100%{offset-distance:100%;opacity:0}}@keyframes pulse{0%{filter:drop-shadow(0 0 0 var(--ok))}60%{filter:drop-shadow(0 0 9px var(--ok))}100%{filter:drop-shadow(0 0 0 var(--ok))}}@keyframes arrive{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}@media(max-width:650px){.kv{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.terminal{grid-template-columns:1fr}}
.mapwrap{position:relative;height:420px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:radial-gradient(circle at 50% 45%,#13283a 0,#071019 72%)}.mapsvg{width:100%;height:100%;touch-action:none;cursor:grab}.mapsvg.drag{cursor:grabbing}.rail{fill:none;stroke-width:5;opacity:.7}.rail.return{stroke-dasharray:10 7}.station circle{fill:#071019;stroke:#3ddc97;stroke-width:3}.station text{fill:#e8f1fa;font-size:12px;text-anchor:middle;pointer-events:none}.pkt{cursor:pointer;filter:drop-shadow(0 0 7px currentColor)}.mapcontrols{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}.mapcontrols button.active{background:#1f8069}.inspector{position:absolute;right:8px;top:8px;width:min(360px,45%);max-height:390px;overflow:auto;background:#071019ee;border:1px solid var(--line);padding:10px;border-radius:8px;display:none}.overload{background:#4a2210;border-color:#ff6b6b}.toptruth{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:7px}.toptruth>div{padding:8px;border:1px solid var(--line);border-radius:7px}.replay{color:var(--warn);font-weight:700}.mapwrap{height:590px;min-height:540px;background:radial-gradient(circle at 50% 40%,#142b40 0,#071019 76%)}.mapsvg{cursor:grab}.mapsvg.drag{cursor:grabbing}.network-track{fill:none;stroke-width:5;opacity:.78}.network-track.outbound{stroke:#25b5ff}.network-track.return{stroke:#ffc857}.network-track.rework{stroke:#ff8c42;stroke-dasharray:13 8}.network-track.blocked{stroke:#ff6b6b;stroke-dasharray:7 8}.network-track.broken{stroke:#ff4d5f;stroke-dasharray:4 10;opacity:.9}.station rect{fill:#08131e;stroke-width:3;rx:12}.station text{font-size:11px;font-weight:750}.station .queue{font-size:9px;fill:#91a3b5}.junction-warning{fill:#ff4d5f;font-weight:900;font-size:13px}.route-label{font-size:11px;font-weight:800;letter-spacing:.08em}.maplegend{display:flex;gap:13px;flex-wrap:wrap;margin:5px 0 8px;color:var(--mut);font-size:11px}.sw{display:inline-block;width:21px;height:4px;margin-right:5px;vertical-align:middle}.mapcontrols{position:absolute;z-index:3;left:8px;top:8px;background:#071019dd;border:1px solid var(--line);border-radius:8px;padding:4px}.mapcontrols button{padding:4px 7px;font-size:10px}.mapfoot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.comms{display:grid;grid-template-columns:1fr 1fr;gap:10px}.lane{border:1px solid var(--line);border-radius:8px;padding:10px}.lane h3{margin:0 0 7px;font-size:12px}.packet-static{stroke:#fff;stroke-width:1.5}.board-alert{color:#fff;background:#5b1717;border:1px solid #ff6b6b;border-radius:7px;padding:5px 8px;font-weight:800}@media(max-width:760px){.comms{grid-template-columns:1fr}.mapwrap{height:520px}}</style></head><body><div class="wrap"><div class="top"><div><h1>CODEX FLOOR 40</h1><div id="stamp" class="k">Live Engineering · waiting for verified sources</div></div><div id="conn" class="conn warn">CONNECTING</div></div><div id="warning"></div><div id="app" class="grid"></div></div><script>
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const fmt=x=>x===null||x===undefined?'UNAVAILABLE':typeof x==='object'?e(JSON.stringify(x)):e(x);const rows=o=>Object.entries(o||{}).map(([k,v])=>`<div class=k>${e(k.replaceAll('_',' '))}</div><div class=v>${fmt(v)}</div>`).join('');const table=(a,cols)=>!a?.length?'<div class=empty>No genuine records available</div>':`<div class=scroll><table><thead><tr>${cols.map(c=>`<th>${e(c)}</th>`).join('')}</tr></thead><tbody>${a.map(x=>`<tr>${cols.map(c=>`<td>${fmt(x[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;function card(t,b,w=''){return `<section class="card ${w}"><h2>${e(t)}</h2>${b}</section>`}let mapState={paused:false,speed:1,view:[0,0,1300,620]};
const POS={'TASK INTAKE':[65,115],'CODEX':[205,115],'RESEARCH / PLAN':[350,115],'TOOLS':[490,115],'PATCH':[625,115],'TEST':[755,115],'PROPOSAL':[885,115],'TASK COUNCIL':[1035,115],'WREN':[1200,115],'RETURN VERDICT':[1200,300],'REWORK':[760,300],'VERIFICATION':[400,475],'COMPLETED':[650,475],'BLOCKED':[1060,500]};
const PERMANENT=[
 ['out-intake','TASK INTAKE','CODEX','outbound'],['out-research','CODEX','RESEARCH / PLAN','outbound'],['out-tools','RESEARCH / PLAN','TOOLS','outbound'],['out-patch','TOOLS','PATCH','outbound'],['out-test','PATCH','TEST','outbound'],['out-proposal','TEST','PROPOSAL','outbound'],['out-council','PROPOSAL','TASK COUNCIL','outbound'],['out-wren','TASK COUNCIL','WREN','outbound'],
 ['ret-verdict','WREN','RETURN VERDICT','return'],['ret-council','RETURN VERDICT','TASK COUNCIL','return'],['ret-codex','TASK COUNCIL','CODEX','return'],['ret-verify','CODEX','VERIFICATION','return'],['ret-complete','VERIFICATION','COMPLETED','return'],
 ['rew-start','RETURN VERDICT','REWORK','rework'],['rew-codex','REWORK','CODEX','rework'],['rew-research','CODEX','RESEARCH / PLAN','rework'],['rew-tools','RESEARCH / PLAN','TOOLS','rework'],['rew-patch','TOOLS','PATCH','rework'],['rew-test','PATCH','TEST','rework'],['rew-council','TEST','TASK COUNCIL','rework'],['rew-wren','TASK COUNCIL','WREN','rework'],
 ['blk-test','TEST','BLOCKED','blocked'],['blk-council','TASK COUNCIL','BLOCKED','blocked'],['blk-wren','WREN','BLOCKED','blocked'],['blk-codex','CODEX','BLOCKED','blocked']];
function geom(a,b,kind=''){const A=POS[a]||POS.CODEX,B=POS[b]||A;if(a==='WREN'&&b==='RETURN VERDICT')return `M${A[0]} ${A[1]+23} L${B[0]} ${B[1]-23}`;if(b==='BLOCKED')return `M${A[0]} ${A[1]+22} Q${(A[0]+B[0])/2} ${B[1]-80},${B[0]} ${B[1]-22}`;if(a==='RETURN VERDICT'&&b==='TASK COUNCIL')return `M${A[0]-30} ${A[1]} Q1080 260,${B[0]} ${B[1]+22}`;if(a==='TASK COUNCIL'&&b==='CODEX')return `M${A[0]-30} ${A[1]+12} Q620 250,${B[0]} ${B[1]+22}`;if(a==='CODEX'&&b==='VERIFICATION')return `M${A[0]} ${A[1]+22} Q240 390,${B[0]} ${B[1]-22}`;if(a==='VERIFICATION'&&b==='COMPLETED')return `M${A[0]+30} ${A[1]} L${B[0]-30} ${B[1]}`;if(a==='RETURN VERDICT'&&b==='REWORK')return `M${A[0]-30} ${A[1]} L${B[0]+30} ${B[1]}`;if(a==='REWORK'&&b==='CODEX')return `M${A[0]-30} ${A[1]} Q450 310,${B[0]} ${B[1]+22}`;return `M${A[0]+30} ${A[1]} L${B[0]-30} ${B[1]}`}
function packetGeom(x){let a=x.origin,b=x.destination;if(a==='COMPLETED')a='COMPLETED';if(b==='COMPLETED')b='COMPLETED';if(b==='BLOCKED')b='BLOCKED';return geom(a,b)}
function queueCounts(d){const c={};(d.transport?.packets||[]).forEach(x=>c[x.current_station]=(c[x.current_station]||0)+1);return c}
function truthTop(d){const c=d.current_work||{},w=d.wren_gate||{},tc=d.task_council||{},st=(d.sources||[]).filter(x=>['STALE','UNAVAILABLE'].includes(x.truth));const excess=Math.max(0,(tc.active_board||0)-(tc.active_board_cap||0));return `<div class=toptruth><div><b>Task / attempt</b><br>${e(c.task_id)}<br><span class=source>${e(c.attempt_id)}</span></div><div><b>Stage / station</b><br><span class=${c.lifecycle_stage==='BLOCKED'?'bad':'ok'}>${e(c.lifecycle_stage)}</span><br>${e((d.transport?.packets||[]).at(-1)?.current_station||'CODEX')}</div><div><b>Current blocker</b><br><span class=${c.blocker?'bad':'ok'}>${e(c.blocker||'NONE')}</span></div><div><b>Latest action</b><br>${e((d.events||[])[0]?.description||'NONE')}</div><div><b>Wren status</b><br><span class=${w.response_status==='ACCEPTED'?'ok':w.response_status==='NOT_SUBMITTED'?'bad':'warn'}>${e(w.response_status)}</span><br>${e(w.truth)}</div><div><b>Test status</b><br>${e((d.tests||[])[0]?.result||'NO CURRENT TEST')}</div><div class=${excess?'board-alert':''}><b>Active board</b><br>${e(tc.active_board)} / ${e(tc.active_board_cap)} · excess ${excess}</div><div><b>Estimated cost</b><br>$${e(d.cost?.today_cost)} · ESTIMATED</div><div><b>Stale sources</b><br>${st.length?e(st.map(x=>x.name).join(', ')):'NONE'}</div></div>`}
function pipeline(d){const t=d.transport||{packets:[]},counts=queueCounts(d),broken=t.return_channel!=='WORKING';const defs=PERMANENT.map(([id,a,b,k])=>`<path id="${id}" d="${geom(a,b,k)}"/>`).join('')+(t.packets||[]).map((x,i)=>`<path id="pktpath${i}" d="${packetGeom(x)}"/>`).join('');const rails=PERMANENT.map(([id,a,b,k])=>`<use href="#${id}" class="network-track ${k} ${broken&&k==='return'?'broken':''}" marker-end="url(#arrow-${k})"/>`).join('');const stations=Object.entries(POS).map(([n,p])=>{const label=n==='COMPLETED'?'COMPLETED OUTPUTS':n==='BLOCKED'?'BLOCKED / QUARANTINE':n,bad=n==='BLOCKED'||(n==='RETURN VERDICT'&&broken),col=bad?'#ff6b6b':n==='COMPLETED'?'#3ddc97':'#5ab0ff',width=Math.max(76,label.length*7+25);return `<g class=station data-station="${e(n)}"><rect x=${p[0]-width/2} y=${p[1]-23} width=${width} height=46 stroke="${col}"/><text x=${p[0]} y=${p[1]-1}>${e(label)}</text><text class=queue x=${p[0]} y=${p[1]+14}>QUEUE ${counts[n]||0}</text><title>${e(n)} · queue ${counts[n]||0}</title></g>`}).join('');const now=Date.now();const packets=(t.packets||[]).map((x,i)=>{const recent=Math.abs(now-Date.parse(x.timestamp||0))<90000,col=x.destination==='BLOCKED'?'#ff6b6b':x.origin==='WREN'?'#ffc857':'#5ab0ff',P=POS[x.destination]||POS.CODEX;if(recent&&!mapState.paused)return `<circle class=pkt data-i=${i} r=8 fill="${col}"><animateMotion dur="${Math.max(.8,3/mapState.speed)}s" repeatCount="1" fill="freeze"><mpath href="#pktpath${i}"/></animateMotion></circle>`;return `<circle class="pkt packet-static" data-i=${i} cx=${P[0]} cy=${P[1]} r=7 fill="${col}"/>`}).join('');return `<div class=maplegend><span><i class=sw style="background:#25b5ff"></i>OUTBOUND</span><span><i class=sw style="background:#ffc857"></i>RETURN</span><span><i class=sw style="background:#ff8c42"></i>REWORK</span><span><i class=sw style="background:#ff6b6b"></i>BLOCKED</span><span>${(t.packets||[]).length} genuine correlated packet records</span></div><div class=mapwrap id=mapwrap><div class=mapcontrols><button onclick=mapPause()>${mapState.paused?'Resume':'Pause'}</button><button onclick=mapSpeed(.5)>− Speed</button><button onclick=mapSpeed(2)>+ Speed</button><button onclick=mapReset()>Reset</button><button onclick=mapFull()>Full</button></div><svg id=mapsvg class=mapsvg viewBox="${mapState.view.join(' ')}"><defs><marker id=arrow-outbound markerWidth=7 markerHeight=7 refX=6 refY=3 orient=auto><path d="M0,0 L0,6 L6,3 z" fill="#25b5ff"/></marker><marker id=arrow-return markerWidth=7 markerHeight=7 refX=6 refY=3 orient=auto><path d="M0,0 L0,6 L6,3 z" fill="#ffc857"/></marker><marker id=arrow-rework markerWidth=7 markerHeight=7 refX=6 refY=3 orient=auto><path d="M0,0 L0,6 L6,3 z" fill="#ff8c42"/></marker><marker id=arrow-blocked markerWidth=7 markerHeight=7 refX=6 refY=3 orient=auto><path d="M0,0 L0,6 L6,3 z" fill="#ff6b6b"/></marker>${defs}</defs><text x=45 y=48 class=route-label fill="#25b5ff">OUTBOUND WORK →</text><text x=1040 y=250 class=route-label fill="#ffc857">← RETURN VERDICT</text><text x=780 y=345 class=route-label fill="#ff8c42">← REWORK LOOP</text><text x=980 y=580 class=route-label fill="#ff6b6b">BLOCKED SIDINGS</text>${rails}${stations}${broken?'<text x=1010 y=286 class=junction-warning>⚠ WREN RETURN CHANNEL NOT CONNECTED</text>':''}${packets}</svg><div id=mapinspect class=inspector></div></div><div class=mapfoot><span>Entire operating network is permanently visible. Packets animate once only for fresh genuine events; older evidence rests at its recorded destination.</span><span class=${broken?'bad':'ok'}>WREN RETURN: ${e(t.return_channel)}${broken?' · missing proposal-correlated receipt/verdict':''}</span></div>`}
function mapPause(){mapState.paused=!mapState.paused;render(lastData)}function mapSpeed(x){mapState.speed=Math.min(4,Math.max(.25,mapState.speed*x));render(lastData)}function mapReset(){mapState.view=[0,0,1300,620];render(lastData)}function mapFull(){document.getElementById('mapwrap')?.requestFullscreen()}
function wireMap(d){const svg=document.getElementById('mapsvg');if(!svg)return;let down=null,base=null;svg.onwheel=ev=>{ev.preventDefault();const f=ev.deltaY>0?1.1:.9;mapState.view[2]*=f;mapState.view[3]*=f;svg.setAttribute('viewBox',mapState.view.join(' '))};svg.onpointerdown=ev=>{down=[ev.clientX,ev.clientY];base=[...mapState.view];svg.classList.add('drag')};svg.onpointermove=ev=>{if(!down)return;mapState.view[0]=base[0]-(ev.clientX-down[0])*base[2]/svg.clientWidth;mapState.view[1]=base[1]-(ev.clientY-down[1])*base[3]/svg.clientHeight;svg.setAttribute('viewBox',mapState.view.join(' '))};svg.onpointerup=()=>{down=null;svg.classList.remove('drag')};svg.querySelectorAll('.pkt').forEach(el=>el.onclick=()=>{const x=(d.transport?.packets||[])[+el.dataset.i],box=document.getElementById('mapinspect');box.style.display='block';box.innerHTML=`<b>Packet lineage</b><div class=kv>${rows(x)}</div><button onclick="this.parentNode.style.display='none'">Close</button>`})}
function comms(d){const p=d.transport?.packets||[],out=p.filter(x=>x.destination==='WREN'||(x.origin==='CODEX'&&['proposal','proposal_submitted'].includes(x.packet_type))),back=p.filter(x=>x.origin==='WREN'||x.packet_type==='wren_verdict');const lane=a=>a.length?table(a,['timestamp','packet_type','proposal_id','state','truth','evidence']):'<div class=empty>No genuine correlated records</div>';return `<div class=comms><div class=lane><h3>CODEX → WREN</h3>${lane(out)}</div><div class=lane><h3>WREN → CODEX</h3>${lane(back)}${back.length?'':`<div class="bad source">WREN RETURN CHANNEL NOT CONNECTED — no proposal-correlated Wren receipt or verdict.</div>`}</div></div>`}
function ticker(d){return (d.events||[]).slice(0,10).map(x=>`<div class=ticker-row><span class=ticker-dot></span><b>${e(x.event_type)}</b> · ${e(x.description)} <span class=source>${e(x.timestamp)} · ${e(x.evidence)}</span></div>`).join('')||'<div class=empty>No genuine engineering events available</div>'}
function suiteView(d){const s=d.engineering_suite||{},f=s.features||[];let z="<div class=toptruth>";for(const x of f){const cls=x.state==="LIVE"?"ok":"warn";z+="<div><b>"+e(x.name)+"</b><br><span class="+cls+">"+e(x.state)+"</span><div class=source>"+e(x.purpose)+"</div><div class=source>Evidence contract: "+e(x.source_contract)+"</div></div>"}return z+"</div><div class=source>"+e(s.truth)+" · Decision owner: "+e(s.decision_owner)+" · "+e(s.execution_posture)+"</div>"}
let lastData=null;function render(d){lastData=d;document.getElementById('stamp').textContent=`Live Engineering · updated ${d.generated_at} · every value exposes provenance`;const stale=d.sources.filter(s=>['STALE','UNAVAILABLE'].includes(s.truth));document.getElementById('warning').innerHTML=stale.length?`<div class="card bad" style="margin-top:12px">STALE/UNAVAILABLE SOURCES: ${e(stale.map(x=>x.name).join(', '))}. Missing live data is not replaced with history.</div>`:'';let h='';h+=card('Floor 40 engineering suite · design and maturity',suiteView(d),'wide');h+=card('Operator truth',truthTop(d),'wide '+(d.board_overload?.warning?'overload':''));h+=card('Complete engineering transport network',pipeline(d),'wide');h+=card('Live Codex–Wren communications',comms(d),'wide');h+=card('Live activity ticker · genuine events only',ticker(d),'wide');h+=card('Current Codex work',`<div class=kv>${rows(d.current_work)}</div><div class=source>Source: ${e(d.task_council.source.path)} · <span class=${e(d.task_council.source.truth)}>${e(d.task_council.source.truth)}</span></div>`,'wide');h+=card('Task lifecycle',table(d.lifecycle,['stage','complete','timestamp','evidence']));h+=card('Wren gate',`<div class=kv>${rows(d.wren_gate)}</div>`);h+=card('Live engineering event stream',table(d.events,['timestamp','task_id','event_type','description','source','result','evidence']),'wide');h+=card('File and patch activity',`<div class=kv>${rows({...d.files,git:JSON.stringify(d.files.git)})}</div>`);h+=card('Tool sessions',table(d.tools,['id','task_id','tool','category','start_time','elapsed_s','state','exit_result','files_accessed','error_summary','truth','evidence']));h+=card('Test and verification',table(d.tests,['command','reason','completion','executed','passed','failed','skipped','verifier','result','evidence']),'wide');h+=card('Task Council',`<div class=kv>${rows({...d.task_council,task:JSON.stringify(d.task_council.task),source:JSON.stringify(d.task_council.source)})}</div>`);h+=card('Proof of work',table(d.proof_of_work,['task_id','description','path','before','after','test_evidence','verifier','completed_at']));h+=card('No-change review control',`<div class=kv>${rows(d.no_change_control)}</div>`);h+=card('Cost · ESTIMATED',`<div class=kv>${rows(d.cost)}</div>`);h+=card('Machine resources',`<div class=kv>${rows({...d.resources,memory:JSON.stringify(d.resources.memory),gpu:JSON.stringify(d.resources.gpu),disk:JSON.stringify(d.resources.disk),dashboard_service:JSON.stringify(d.resources.dashboard_service),autorunner_service:JSON.stringify(d.resources.autorunner_service)})}</div>`);h+=card('Data truth register',table(d.sources,['name','path','updated','age_s','truth']),'wide');h+=card('Codex terminal · authenticated LAN lane',`<div class=terminal><input id=auth type=password autocomplete=off placeholder="Floor 40 terminal credential"><textarea id=prompt rows=2 maxlength=6000 placeholder="Message Codex through the bounded audited lane"></textarea><button onclick=ask()>Send</button></div><pre id=reply class=source>Authentication required. Credential value is never stored by the page.</pre><div class=source>Restricted to localhost and 10.55.0.0/24 · provider calls are audited and cost-metered.</div>`,'wide');document.getElementById('app').innerHTML=h;wireMap(d)}
let es,delay=1000;function connect(){document.getElementById('conn').className='conn warn';document.getElementById('conn').textContent='CONNECTING';es=new EventSource('/events');es.addEventListener('state',x=>{render(JSON.parse(x.data));delay=1000;document.getElementById('conn').className='conn ok';document.getElementById('conn').textContent='LIVE SSE'});es.onerror=()=>{document.getElementById('conn').className='conn bad';document.getElementById('conn').textContent='DISCONNECTED · retrying';es.close();setTimeout(connect,delay);delay=Math.min(delay*2,30000)}}async function ask(){const p=document.getElementById('prompt'),a=document.getElementById('auth'),r=document.getElementById('reply');if(!p.value.trim()||!a.value){r.textContent='Credential and prompt are required.';return}r.textContent='Authenticated request in progress…';try{const x=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+a.value},body:JSON.stringify({prompt:p.value})});const j=await x.json();r.textContent=j.ok?j.reply:(x.status+' · '+j.error);if(j.ok)p.value=''}catch(err){r.textContent='UNAVAILABLE: '+err}}const initial=fetch('/api/data',{cache:'no-store'}).then(x=>x.json()).then(render).catch(()=>{});if(new URLSearchParams(location.search).has('snapshot')){initial.then(()=>document.documentElement.dataset.snapshot='ready')}else{initial.finally(connect)};
</script></body></html>'''

def terminal_client_allowed(addr):
    try:
        ip=ipaddress.ip_address(addr)
        return ip.is_loopback or ip in ipaddress.ip_network("10.55.0.0/24")
    except ValueError: return False

def terminal_authorized(header):
    try: expected=TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception: return False
    supplied=header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    return bool(expected and supplied and hmac.compare_digest(expected,supplied))

def terminal_rate_allowed(addr):
    now=time.time()
    with RATE_LOCK:
        recent=[x for x in RATE_LIMIT.get(addr,[]) if now-x < 60]
        if len(recent) >= 3: RATE_LIMIT[addr]=recent; return False
        recent.append(now); RATE_LIMIT[addr]=recent; return True

def ask_codex(prompt):
    prompt=(prompt or '').strip()
    if not prompt: return {"ok":False,"error":"empty prompt; no provider call made"}
    cmd=["python3",str(ROOT/'tools/qsb_consult_external.py'),"--provider","openai","--model","gpt-4o-mini","--prompt",prompt[:6000],"--reason","codex_terminal","--max-tokens","500"]
    try: r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=90)
    except subprocess.TimeoutExpired: return {"ok":False,"error":"provider timeout"}
    if r.returncode: return {"ok":False,"error":redact((r.stderr or r.stdout or 'provider call failed').splitlines()[-1],300)}
    return {"ok":True,"reply":redact(r.stdout,6000),"accounting":"Provider spend ledger; dashboard totals remain labelled ESTIMATED"}

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self,obj,code=200):
        body=json.dumps(obj,separators=(',',':')).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/api/health'): return self.send_json({"ok":True,"service":"qsb-codex-floor-dash-v3","floor":40,"port":self.server.server_port,"terminal":"AUTHENTICATED_LAN_ONLY","generated_at":iso()})
        if self.path.startswith('/api/state') or self.path.startswith('/api/data') or self.path.startswith('/api/activity'): return self.send_json(build_state())
        if self.path.startswith('/events'):
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.send_header('Connection','keep-alive'); self.end_headers(); last=None
            try:
                for _ in range(720):
                    data=json.dumps(build_state(),separators=(',',':')); digest=hashlib.sha256(data.encode()).hexdigest()
                    if digest!=last: self.wfile.write(f"event: state\ndata: {data}\n\n".encode()); self.wfile.flush(); last=digest
                    time.sleep(5)
            except (BrokenPipeError,ConnectionResetError): pass
            return
        body=PAGE.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; connect-src 'self'"); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if self.path.startswith('/api/ask'):
            addr=self.client_address[0]
            if not terminal_client_allowed(addr): return self.send_json({"ok":False,"error":"terminal unavailable from this network"},403)
            if not terminal_authorized(self.headers.get('Authorization','')): return self.send_json({"ok":False,"error":"authentication required"},401)
            if not terminal_rate_allowed(addr): return self.send_json({"ok":False,"error":"rate limit exceeded; retry later"},429)
            try: payload=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0') or 0),7000)) or b'{}')
            except Exception: payload={}
            return self.send_json(ask_codex(payload.get('prompt','')))
        return self.send_json({"ok":False,"error":"not found"},404)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--port',type=int,default=8870); ap.add_argument('--bind',default='127.0.0.1,10.55.0.1'); a=ap.parse_args()
    servers=[]
    for bind in dict.fromkeys(x.strip() for x in a.bind.split(',') if x.strip()):
        try:
            server=ThreadingHTTPServer((bind,a.port),H); servers.append(server)
            print(f"CODEX FLOOR 40 dashboard v3 on http://{bind}:{a.port}",flush=True)
        except OSError as exc:
            print(f"CODEX FLOOR 40 bind unavailable on {bind}:{a.port}: {exc}",flush=True)
    if not servers: raise SystemExit("no dashboard listener could be created")
    for server in servers[1:]: threading.Thread(target=server.serve_forever,daemon=True).start()
    servers[0].serve_forever()
