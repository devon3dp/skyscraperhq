#!/usr/bin/env python3
"""SkyscraperHQ Federation Briefing + Living Story — CARETAKER reporter.
Reads SAFE federation knowledge ONLY from the existing Pi APIs (Brain Router /status + /nodes,
Receptionist /api/status). Emits morning/evening briefings and appends the Federation's living
story. NO worker minds, memories, reasoning, credentials or identities are read or written.
This is a reporter over the EXISTING architecture - it creates no new architecture."""
import sys, json, datetime, urllib.request
PIS = ["192.168.1.24", "192.168.1.23"]
OUT = "/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT"
STORY = OUT + "/STORY_OF_THE_FEDERATION.txt"
def get(path):
    for ip in PIS:
        try: return json.load(urllib.request.urlopen("http://%s%s"%(ip,path), timeout=5))
        except Exception: continue
    return {}
def utc(): return datetime.datetime.now(datetime.timezone.utc)
def nodes_state():
    now=utc(); d=get(":8890/nodes"); rows=[]
    for n in d.get("nodes",[]):
        hb=n.get("last_heartbeat")
        try: age=int((now-datetime.datetime.fromisoformat(hb.replace("Z","+00:00"))).total_seconds())
        except: age=99999
        st="ONLINE" if age<45 else("STALE" if age<90 else "OFFLINE")
        rows.append((n["node_id"], st, age))
    return rows
def briefing(kind):
    now=utc(); b=get(":8890/status"); r=get(":8891/api/status"); rows=nodes_state()
    online=[x for x in rows if x[1]=="ONLINE"]; stale=[x for x in rows if x[1]=="STALE"]; off=[x for x in rows if x[1]=="OFFLINE"]
    L=[]
    L.append("SKYSCRAPERHQ FEDERATION — %s BRIEFING"%kind.upper())
    L.append("generated %s · SAFE federation knowledge only"%now.isoformat().replace("+00:00","Z"))
    L.append("="*72)
    L.append("FEDERATION HEALTH : %s"%("HEALTHY" if b.get("healthy") else "CHECK"))
    L.append("Brain Router      : %s (state=%s, local_first=%s, silent_paid_fallback=%s)"%(
        "ONLINE" if b.get("status")=="online" else "OFFLINE", b.get("state"), b.get("local_first"), b.get("silent_paid_fallback")))
    L.append("Receptionist      : %s"%("ONLINE" if r.get("healthy") else "OFFLINE"))
    L.append("Boardroom reachable: %s"%b.get("boardroom_reachable"))
    L.append("Nodes registered  : %s"%b.get("registered_nodes"))
    L.append("Online / Degraded(STALE) / Offline : %d / %d / %d"%(len(online),len(stale),len(off)))
    for nid,st,age in rows: L.append("   - %-20s %-8s (hb %ss)"%(nid,st,age))
    L.append("Queue size        : %s"%b.get("queue_size"))
    L.append("Waiting for Ross  : %s"%b.get("waiting_for_ross", r.get("messages_waiting_for_ross")))
    L.append("Failed routes     : %s"%b.get("failed_routes"))
    L.append("Requests today    : %s"%b.get("requests_today"))
    L.append("Messages received : %s"%r.get("messages_received"))
    if kind=="evening":
        L.append("-"*72); L.append("EVENING: completed-task + alert summary derived from routing counters above.")
    L.append("-"*72)
    L.append("LEADERSHIP TEAM (all via Pi): Bill, Wren, TP-Pip, Acer-Cass — status shown above.")
    L.append("Bill = Executive Concierge (safe knowledge only). Wren = Governor L1 (GovL2 OFF).")
    return "\n".join(L)+"\n"
def story_line():
    now=utc(); rows=nodes_state(); b=get(":8890/status")
    online=[x[0] for x in rows if x[1]=="ONLINE"]
    day=now.strftime("%d %B %Y")
    return ("%s — Federation health %s; online: %s; queue %s; waiting_for_Ross %s; failed_routes %s. "
            "Boardroom reachable=%s. Bill continues learning safe federation knowledge.\n"%(
            day, "HEALTHY" if b.get("healthy") else "CHECK", ", ".join(online) or "none",
            b.get("queue_size"), b.get("waiting_for_ross"), b.get("failed_routes"), b.get("boardroom_reachable")))
def main():
    kind = sys.argv[1] if len(sys.argv)>1 else "morning"
    date = utc().strftime("%Y%m%d")
    if kind=="story":
        open(STORY,"a").write(story_line()); print("appended story:", STORY); return
    txt=briefing(kind)
    fn="%s/FEDERATION_%s_BRIEFING_%s.txt"%(OUT,kind.upper(),date)
    open(fn,"w").write(txt); print(fn); print(txt)
    open(STORY,"a").write(story_line())
if __name__=="__main__": main()
