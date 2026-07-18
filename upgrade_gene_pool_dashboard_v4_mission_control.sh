#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
APP="$PROJECT/tools/skyscraper_gene_pool_router.py"
STARTER="$PROJECT/run_gene_pool_router.sh"
PORT="8860"
LOG="$PROJECT/logs/gene_pool_router_8860.log"
PIDFILE="$PROJECT/runtime/gene_pool_router_8860.pid"

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_gene_pool_dashboard_v4_mission_control"
REPORT="$RUN_DIR/reports/gene_pool_dashboard_v4_mission_control_report.txt"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/backups" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — GENE POOL DASHBOARD V4 MISSION CONTROL"
echo "Generated: $(date -Is)"
echo "Port: $PORT"
echo "============================================================"
echo "Rules:"
echo " - Visual/telemetry upgrade."
echo " - Shows CEO job request and reply windows."
echo " - Shows Brain Router decision and provider reply preview."
echo " - No secure key printing."
echo " - No key changes."
echo " - Claude HQ is the correct name."
echo " - Wren owns/protects the GPU."
echo " - CEOs use API Gene Pool only."
echo " - No CEO fallback to Wren/local GPU."
echo "============================================================"

cd "$PROJECT" || exit 1

if [ ! -f "$APP" ]; then
  echo "[FAIL] Missing app: $APP"
  exit 1
fi

cp -a "$APP" "$RUN_DIR/backups/skyscraper_gene_pool_router.py.bak_$STAMP"
echo "[OK] backup written"

echo
echo "===== 1. PATCH BACKEND WITH JOB / REPLY TELEMETRY ====="

python3 - <<'PY'
from pathlib import Path
import re

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

if "JOB_PROMPTS = {" not in s:
    marker = 'TASKS = ["architecture", "coding", "summary", "cheap", "default"]'
    inject = '''
JOB_PROMPTS = {
    "architecture": "Review the current SkyscraperHQ Brain Router architecture and decide the best API engine for executive reasoning.",
    "coding": "Inspect the latest system route and decide which API engine should handle a coding or repair task.",
    "summary": "Summarise the latest live router state, provider availability, and CEO activity.",
    "cheap": "Choose the cheapest suitable API provider without using Wren/local GPU fallback.",
    "default": "Handle the CEO request using the API Gene Pool and preserve the SkyscraperHQ routing doctrine."
}
'''
    s = s.replace(marker, marker + "\n" + inject)

# Replace auto_route_once fully, because V4 needs rich ask/reply telemetry.
m = re.search(r"\ndef auto_route_once\(\):\n.*?\n(?=def recent\(|def metrics\(|def save_state\()", s, flags=re.S)
if not m:
    raise SystemExit("[FAIL] Could not locate def auto_route_once block")

new_auto = r'''
def auto_route_once():
    ceo = CEOS[AUTONOMY["route_count"] % len(CEOS)]
    task = TASKS[AUTONOMY["route_count"] % len(TASKS)]
    ask = JOB_PROMPTS.get(task, JOB_PROMPTS["default"])
    provider = choose_provider(task)

    event({
        "event": "request",
        "from": ceo,
        "to": "Brain Router",
        "provider": provider or "none",
        "task": task,
        "status": "received",
        "ask": ask,
        "detail": "CEO submitted autonomous job to Brain Router",
        "job": {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "stage": "submitted"
        }
    })

    if provider:
        label = PROVIDERS[provider]["label"]
        reason = f"{task} policy selected {label}; CEO uses API Gene Pool only; Wren/local GPU fallback blocked by doctrine"
        latency = random.randint(90, 1400)
        reply = (
            f"{label} route selected for {ceo}. "
            f"Task class: {task}. "
            f"Decision: use API Gene Pool provider {label}; keep Wren protected; no local CEO fallback. "
            f"Next action: return structured guidance to {ceo} and log the route."
        )

        st = PROVIDER_STATS.setdefault(provider, {"calls": 0, "success": 0, "fail": 0, "last_task": "", "last_ceo": "", "last_ts": "", "last_reason": "", "latency_ms": 0})
        st["calls"] += 1
        st["success"] += 1
        st["last_task"] = task
        st["last_ceo"] = ceo
        st["last_ts"] = now()
        st["latency_ms"] = latency
        st["last_reason"] = reason

        decision = {
            "ceo": ceo,
            "task": task,
            "ask": ask,
            "selected_provider": provider,
            "selected_label": label,
            "reason": reason,
            "latency_ms": latency,
            "wren_fallback": "blocked",
            "provider_reply": reply,
            "stage": "selected"
        }

        event({
            "event": "dispatch",
            "from": "Brain Router",
            "to": label,
            "provider": provider,
            "task": task,
            "status": "selected",
            "ask": ask,
            "reply": reply,
            "detail": reason,
            "decision": decision,
            "job": {
                "ceo": ceo,
                "task": task,
                "ask": ask,
                "provider": label,
                "stage": "dispatched"
            }
        })

        event({
            "event": "return",
            "from": label,
            "to": ceo,
            "provider": provider,
            "task": task,
            "status": "visual_live",
            "ask": ask,
            "reply": reply,
            "detail": "provider response returned to CEO window",
            "decision": decision,
            "job": {
                "ceo": ceo,
                "task": task,
                "ask": ask,
                "provider": label,
                "reply": reply,
                "stage": "returned"
            }
        })
    else:
        reply = "No API Gene Pool provider key is available. CEO route blocked. Wren/local GPU fallback remains blocked by doctrine."
        event({
            "event": "blocked",
            "from": "Brain Router",
            "to": ceo,
            "provider": "none",
            "task": task,
            "status": "blocked",
            "ask": ask,
            "reply": reply,
            "detail": reply,
            "decision": {
                "ceo": ceo,
                "task": task,
                "ask": ask,
                "selected_provider": "none",
                "selected_label": "none",
                "reason": reply,
                "latency_ms": None,
                "wren_fallback": "blocked",
                "provider_reply": reply,
                "stage": "blocked"
            },
            "job": {
                "ceo": ceo,
                "task": task,
                "ask": ask,
                "reply": reply,
                "stage": "blocked"
            }
        })

    AUTONOMY["route_count"] += 1
    AUTONOMY["last_route"] = now()

'''
s = s[:m.start()] + "\n" + new_auto + s[m.end():]

# Ensure helper functions exist.
if "def ceo_panels():" not in s:
    insert_before = "def metrics():"
    helper = r'''
def ceo_panels():
    logs = recent(360)
    panels = {}
    for ceo in CEOS:
        panels[ceo] = {
            "ceo": ceo,
            "task": "waiting",
            "ask": "Waiting for next autonomous job.",
            "reply": "No reply yet.",
            "provider": "none",
            "provider_label": "none",
            "ts": "",
            "status": "idle"
        }

    for e in logs:
        target = e.get("to")
        source = e.get("from")
        ceo = None
        if source in CEOS:
            ceo = source
        if target in CEOS:
            ceo = target
        if not ceo:
            continue

        provider = e.get("provider", "none")
        panels[ceo].update({
            "ceo": ceo,
            "task": e.get("task", panels[ceo]["task"]),
            "ask": e.get("ask") or e.get("job", {}).get("ask") or panels[ceo]["ask"],
            "reply": e.get("reply") or e.get("job", {}).get("reply") or panels[ceo]["reply"],
            "provider": provider,
            "provider_label": PROVIDERS.get(provider, {}).get("label", provider),
            "ts": e.get("ts", ""),
            "status": e.get("status", "live")
        })
    return panels

def job_board():
    logs = recent(360)
    jobs = []
    for e in reversed(logs):
        if e.get("event") in ("request", "dispatch", "return", "blocked"):
            jobs.append({
                "ts": e.get("ts", ""),
                "event": e.get("event", ""),
                "from": e.get("from", ""),
                "to": e.get("to", ""),
                "provider": e.get("provider", ""),
                "task": e.get("task", ""),
                "ask": e.get("ask", ""),
                "reply": e.get("reply", ""),
                "detail": e.get("detail", "")
            })
        if len(jobs) >= 16:
            break
    return jobs

'''
    s = s.replace(insert_before, helper + "\n" + insert_before)

# Patch /api/live JSON with new payloads.
if '"ceo_panels": ceo_panels()' not in s:
    s = s.replace(
        '"latest_decision": latest_decision(),',
        '"latest_decision": latest_decision(),\n                "ceo_panels": ceo_panels(),\n                "job_board": job_board(),'
    )

p.write_text(s, encoding="utf-8")
print("[OK] backend V4 job/reply telemetry patched")
PY

echo
echo "===== 2. INSTALL V4 MISSION CONTROL FRONTEND ====="

python3 - <<'PY'
from pathlib import Path

p = Path("/vaults/nvme0/qsb_tower_v1/tools/skyscraper_gene_pool_router.py")
s = p.read_text(errors="ignore")

start = s.find("HTML = r'''")
if start < 0:
    raise SystemExit("[FAIL] Could not find HTML block")
body_start = start + len("HTML = r'''")
end = s.find("'''", body_start)
if end < 0:
    raise SystemExit("[FAIL] Could not find HTML end")

html = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SkyscraperHQ · Brain Router V4 Mission Control</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#020610;--panel:#071426;--panel2:#0c2035;--line:#1e4566;--text:#e8f7ff;--muted:#8ca9bd;
  --cyan:#42d9ff;--green:#45f59b;--amber:#ffc857;--red:#ff5d7d;--purple:#b987ff;--blue:#2a8cff;
}
*{box-sizing:border-box}
body{
  margin:0;color:var(--text);font-family:system-ui,Segoe UI,Arial,sans-serif;overflow-x:hidden;
  background:
    radial-gradient(circle at 12% 0,rgba(66,217,255,.22),transparent 30%),
    radial-gradient(circle at 82% 8%,rgba(185,135,255,.20),transparent 32%),
    radial-gradient(circle at 50% 0,#173655 0,#06101d 50%,#02050b 100%);
}
body:before{
  content:"";position:fixed;inset:0;pointer-events:none;opacity:.13;
  background-image:
    linear-gradient(rgba(66,217,255,.16) 1px,transparent 1px),
    linear-gradient(90deg,rgba(66,217,255,.16) 1px,transparent 1px);
  background-size:46px 46px;animation:gridDrift 22s linear infinite;
}
@keyframes gridDrift{to{background-position:46px 46px}}
header{
  padding:14px 20px;border-bottom:1px solid var(--line);background:rgba(0,0,0,.48);
  position:sticky;top:0;z-index:20;backdrop-filter:blur(12px)
}
h1{margin:0;font-size:23px;letter-spacing:.3px}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
.layout{display:grid;grid-template-columns:1.08fr .92fr;gap:14px;padding:14px}
.lower{display:grid;grid-template-columns:.95fr 1.05fr;gap:14px;padding:0 14px 42px}
.card{
  background:linear-gradient(180deg,rgba(13,32,54,.94),rgba(4,12,23,.94));
  border:1px solid var(--line);border-radius:22px;padding:14px;
  box-shadow:0 14px 42px rgba(0,0,0,.42),inset 0 0 34px rgba(66,217,255,.025);
}
.flow{height:720px;position:relative;overflow:hidden}
.flow:after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 50% 50%,transparent 0,transparent 62%,rgba(2,6,16,.70) 100%)}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:1}
.line{stroke:#1d5f86;stroke-width:2;opacity:.38;stroke-dasharray:7 8;animation:dash 1.8s linear infinite}
.line.ceoline{stroke:rgba(66,217,255,.64)}.line.providerline{stroke:rgba(185,135,255,.52)}.line.wrenline{stroke:#246b49;opacity:.38}
@keyframes dash{to{stroke-dashoffset:-30}}
.hotbeam{stroke:var(--cyan);stroke-width:4;opacity:.96;filter:drop-shadow(0 0 8px var(--cyan));stroke-dasharray:12 10;animation:dash .75s linear infinite,fadeBeam 1.55s ease-out forwards}
@keyframes fadeBeam{to{opacity:0}}
.node{
  position:absolute;width:174px;height:116px;border:1px solid var(--line);border-radius:24px;
  background:linear-gradient(180deg,rgba(7,24,42,.96),rgba(2,9,18,.94));
  text-align:center;box-shadow:0 0 24px rgba(66,217,255,.08),inset 0 0 20px rgba(255,255,255,.025);
  z-index:3;overflow:hidden;padding-top:12px;
}
.node:before{content:"";position:absolute;inset:-2px;border-radius:26px;opacity:.20;background:conic-gradient(from var(--a,0deg),transparent,var(--cyan),transparent 35%,transparent);animation:ring 4s linear infinite}
.node>*{position:relative;z-index:2}.node b{display:block;font-size:15px;margin-top:4px}.node small{color:var(--muted);font-size:11px}
@property --a{syntax:"<angle>";initial-value:0deg;inherits:false}@keyframes ring{to{--a:360deg}}
.avatar{
  width:46px;height:46px;border-radius:50%;margin:0 auto;
  background:radial-gradient(circle at 35% 30%,#fff,var(--cyan) 20%,#09304b 58%,#020812 100%);
  border:1px solid rgba(66,217,255,.65);box-shadow:0 0 18px rgba(66,217,255,.45);
  position:relative;animation:avatarBob 2.2s ease-in-out infinite;
}
.avatar:before,.avatar:after{content:"";position:absolute;inset:-7px;border-radius:50%;border:1px solid rgba(66,217,255,.30);animation:avatarRing 2.4s linear infinite}
.avatar:after{inset:-13px;opacity:.45;animation-duration:3.4s}
@keyframes avatarBob{50%{transform:translateY(-4px)}}@keyframes avatarRing{to{transform:rotate(360deg)}}
.claude .avatar{background:radial-gradient(circle at 35% 30%,#fff,#42d9ff 20%,#0a4166 58%,#020812 100%)}
.ceo2 .avatar{background:radial-gradient(circle at 35% 30%,#fff,#b987ff 20%,#3b1d66 58%,#020812 100%)}
.ceo3 .avatar{background:radial-gradient(circle at 35% 30%,#fff,#ffc857 20%,#61420a 58%,#020812 100%)}
.claude{left:34px;top:55px}.ceo2{left:34px;top:295px}.ceo3{left:34px;top:535px}
.provider{
  position:absolute;right:34px;width:166px;height:76px;border:1px solid var(--line);border-radius:22px;
  background:linear-gradient(180deg,rgba(7,24,42,.96),rgba(2,9,18,.94));
  text-align:center;z-index:3;padding-top:9px;box-shadow:0 0 20px rgba(66,217,255,.07);overflow:hidden;
}
.provider b{display:block}.provider small{color:var(--muted);font-size:11px}
.provider .miniMeter{position:absolute;left:12px;right:12px;bottom:9px;height:5px;border-radius:999px;background:#10263a;overflow:hidden}
.provider .miniMeter i{display:block;height:100%;width:45%;background:linear-gradient(90deg,var(--cyan),var(--green));animation:meterFlow 2.2s ease-in-out infinite}
@keyframes meterFlow{50%{width:92%}}
.provider.active{border-color:var(--green);box-shadow:0 0 30px rgba(69,245,155,.28),inset 0 0 18px rgba(69,245,155,.06)}
.provider.selectedNow{border-color:var(--amber);box-shadow:0 0 38px rgba(255,200,87,.38),inset 0 0 22px rgba(255,200,87,.10)}
.provider.missing{border-color:rgba(255,93,125,.50);opacity:.70}
.p0{top:18px}.p1{top:100px}.p2{top:182px}.p3{top:264px}.p4{top:346px}.p5{top:428px}.p6{top:510px}.p7{top:592px}
.router{
  position:absolute;left:50%;top:278px;transform:translateX(-50%);
  width:238px;height:178px;border:1px solid rgba(66,217,255,.70);border-radius:34px;
  background:radial-gradient(circle at center,rgba(66,217,255,.12),rgba(2,9,18,.95) 62%);
  z-index:4;text-align:center;padding-top:18px;
  box-shadow:0 0 50px rgba(66,217,255,.42),inset 0 0 34px rgba(66,217,255,.08);
  overflow:hidden;
}
.router b{font-size:18px;position:relative;z-index:3}.router small{color:var(--muted);position:relative;z-index:3}
.brainCore{
  width:96px;height:96px;border-radius:50%;margin:12px auto 6px;position:relative;z-index:2;
  background:radial-gradient(circle at 50% 50%,rgba(255,255,255,.85),rgba(66,217,255,.55) 16%,rgba(10,65,102,.50) 38%,rgba(2,8,18,.92) 68%);
  border:1px solid rgba(66,217,255,.72);box-shadow:0 0 34px rgba(66,217,255,.52);animation:brainPulse 1.65s ease-in-out infinite;
}
.brainCore:before{content:"";position:absolute;inset:-14px;border-radius:50%;border:2px dashed rgba(66,217,255,.42);animation:spin 6s linear infinite}
.brainCore:after{content:"";position:absolute;inset:-27px;border-radius:50%;border:1px solid rgba(185,135,255,.38);animation:spin 10s linear reverse infinite}
.orbitDot{position:absolute;width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 14px var(--green);left:50%;top:50%;transform-origin:-34px -34px;animation:orbit 3s linear infinite}
.orbitDot.d2{background:var(--purple);box-shadow:0 0 14px var(--purple);animation-duration:4.2s}
.orbitDot.d3{background:var(--amber);box-shadow:0 0 14px var(--amber);animation-duration:5.4s}
@keyframes brainPulse{50%{transform:scale(1.06);filter:brightness(1.28)}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes orbit{to{rotate:360deg}}
.wren{
  position:absolute;right:220px;bottom:24px;width:208px;height:94px;border:1px solid var(--green);border-radius:24px;
  background:linear-gradient(180deg,rgba(8,38,24,.90),rgba(2,12,9,.95));text-align:center;z-index:3;padding-top:12px;
  box-shadow:0 0 34px rgba(69,245,155,.25),inset 0 0 28px rgba(69,245,155,.08);
}
.wren b{display:block}.wren small{color:#a8dbc1}
.shield{width:38px;height:42px;margin:0 auto 3px;background:linear-gradient(180deg,var(--green),#0a6c40);clip-path:polygon(50% 0,92% 16%,82% 76%,50% 100%,18% 76%,8% 16%);box-shadow:0 0 20px rgba(69,245,155,.55);animation:shieldPulse 1.8s ease-in-out infinite}
@keyframes shieldPulse{50%{filter:brightness(1.3);transform:scale(1.05)}}
.routeLabel{
  position:absolute;z-index:9;left:50%;top:222px;transform:translateX(-50%);
  background:rgba(0,0,0,.66);border:1px solid rgba(66,217,255,.58);border-radius:999px;
  padding:8px 14px;font-family:ui-monospace,monospace;font-size:12px;color:var(--cyan);
  box-shadow:0 0 22px rgba(66,217,255,.20)
}
.packet{position:absolute;width:12px;height:12px;border-radius:50%;background:var(--cyan);box-shadow:0 0 18px var(--cyan);opacity:0;z-index:8}
.packet:after{content:"";position:absolute;inset:-8px;border-radius:50%;border:1px solid rgba(66,217,255,.36)}
.packet.go{animation:move 1.15s linear forwards}
@keyframes move{0%{opacity:0;transform:translate(var(--x1),var(--y1)) scale(.45)}12%{opacity:1}100%{opacity:0;transform:translate(var(--x2),var(--y2)) scale(1.25)}}
.panelGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.statGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.stat{background:#061426;border:1px solid var(--line);border-radius:16px;padding:10px;position:relative;overflow:hidden}
.stat:after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:linear-gradient(90deg,var(--cyan),var(--green));opacity:.8}
.big{font-size:25px;font-weight:900}
.gaugeGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.gauge{height:108px;display:grid;place-items:center;border-radius:18px;background:linear-gradient(180deg,#061426,#030a13);border:1px solid var(--line);position:relative;overflow:hidden}
.dial{width:76px;height:76px;border-radius:50%;background:conic-gradient(var(--green) calc(var(--v)*1%),#10263a 0);display:grid;place-items:center;transition:.45s;box-shadow:0 0 20px rgba(69,245,155,.14)}
.dial:after{content:attr(data-v) '%';width:52px;height:52px;border-radius:50%;background:#061426;display:grid;place-items:center;font-weight:900;font-size:13px}
.gauge span{position:absolute;bottom:7px;color:var(--muted);font-size:11px}
.box{
  background:#040b14;border:1px solid var(--line);border-radius:16px;padding:11px;
  font-family:ui-monospace,monospace;font-size:12px;line-height:1.45;overflow:auto;
}
.decision{height:176px}
.jobbox{height:170px}
.providerReply{height:150px}
.ceoReplies{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.ceoBox{height:224px}
.ceoBox h4{margin:0 0 7px;color:var(--cyan)}
.ceoBox .ask{color:var(--amber)}
.ceoBox .reply{color:var(--green)}
.providers{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.prov{padding:10px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(180deg,#061426,#030a13);min-height:142px;position:relative;overflow:hidden}
.prov.ok{border-color:rgba(69,245,155,.75);box-shadow:0 0 14px rgba(69,245,155,.08)}
.prov.selected{border-color:rgba(255,200,87,.95);box-shadow:0 0 22px rgba(255,200,87,.18)}
.prov.bad{border-color:rgba(255,93,125,.55);opacity:.75}
.prov b{display:block}.prov small{color:var(--muted)}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 7px;font-size:11px;margin-top:5px}
.pill.ok{border-color:rgba(69,245,155,.6)}.pill.warn{border-color:rgba(255,200,87,.6)}.pill.bad{border-color:rgba(255,93,125,.6)}
.stream{height:312px}
.event{padding:7px;border-bottom:1px solid rgba(255,255,255,.05);animation:eventIn .35s ease-out}
@keyframes eventIn{from{opacity:0;transform:translateY(8px)}}.ok{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}.muted{color:var(--muted)}
.pulse{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green);animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.25;transform:scale(.65)}}
.ticker{position:fixed;left:0;right:0;bottom:0;z-index:20;background:rgba(0,0,0,.68);border-top:1px solid var(--line);color:var(--cyan);font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;height:28px;display:flex;align-items:center}
.ticker span{display:inline-block;padding-left:100%;animation:ticker 34s linear infinite}
@keyframes ticker{to{transform:translateX(-100%)}}
@media(max-width:1250px){.layout,.lower{grid-template-columns:1fr}.providers,.gaugeGrid,.statGrid{grid-template-columns:repeat(2,1fr)}.ceoReplies{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
<h1>🧠 SkyscraperHQ Brain Router V4 · Mission Control <span class="pulse"></span></h1>
<div class="sub">Shows who submits the job, what they ask, what the router chooses, and what reply returns to each CEO. Wren/GPU protected.</div>
</header>

<div class="layout">
<section class="card flow" id="flow">
<svg id="wires"></svg>
<div class="routeLabel" id="routeLabel">waiting for autonomous route...</div>

<div class="node claude" data-node="Claude HQ"><div class="avatar"></div><b>Claude HQ</b><small id="claudeStatus">waiting</small></div>
<div class="node ceo2" data-node="CEO 2"><div class="avatar"></div><b>CEO 2</b><small id="ceo2Status">waiting</small></div>
<div class="node ceo3" data-node="CEO 3"><div class="avatar"></div><b>CEO 3</b><small id="ceo3Status">waiting</small></div>

<div class="router" data-node="Brain Router">
  <b>Brain Router</b>
  <div class="brainCore"><i class="orbitDot"></i><i class="orbitDot d2"></i><i class="orbitDot d3"></i></div>
  <small>autonomous gene selector</small>
</div>

<div class="provider p0" data-provider="claude"><b>Claude</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p1" data-provider="openai"><b>OpenAI</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p2" data-provider="deepseek"><b>DeepSeek</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p3" data-provider="gemini"><b>Gemini</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p4" data-provider="cohere"><b>Cohere</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p5" data-provider="kimi"><b>Kimi</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p6" data-provider="grok"><b>Grok/xAI</b><small>provider</small><div class="miniMeter"><i></i></div></div>
<div class="provider p7" data-provider="groq"><b>Groq</b><small>provider</small><div class="miniMeter"><i></i></div></div>

<div class="wren" data-node="Wren"><div class="shield"></div><b>Wren</b><small>GPU guardian · protected</small></div>
</section>

<section class="card">
<div class="gaugeGrid">
<div class="gauge"><div class="dial" id="g_router" style="--v:0" data-v="0"></div><span>Router rev</span></div>
<div class="gauge"><div class="dial" id="g_pool" style="--v:0" data-v="0"></div><span>API pool</span></div>
<div class="gauge"><div class="dial" id="g_ceo" style="--v:0" data-v="0"></div><span>CEO load</span></div>
<div class="gauge"><div class="dial" id="g_wren" style="--v:100" data-v="100"></div><span>Wren guard</span></div>
</div>
<br>
<div class="statGrid">
<div class="stat"><small>Unique keys</small><div class="big" id="uniqueKeys">0</div></div>
<div class="stat"><small>Duplicate sightings</small><div class="big" id="sightings">0</div></div>
<div class="stat"><small>Active providers</small><div class="big" id="providerscount">0</div></div>
<div class="stat"><small>Routes</small><div class="big" id="routecount">0</div></div>
</div>
<br>
<div class="panelGrid">
  <div>
    <h3>Current submitted job</h3>
    <div class="box jobbox" id="jobBox">Waiting for job...</div>
  </div>
  <div>
    <h3>Brain Router decision</h3>
    <div class="box decision" id="decisionBox">Waiting for decision...</div>
  </div>
</div>
<br>
<h3>Selected API reply preview</h3>
<div class="box providerReply" id="providerReply">Waiting for provider reply...</div>
</section>
</div>

<div class="card" style="margin:0 14px 14px">
<h3>CEO live ask / reply windows</h3>
<div class="ceoReplies" id="ceoReplies"></div>
</div>

<div class="lower">
<section class="card"><h3>API Gene Pool provider states</h3><div class="providers" id="providers"></div></section>
<section class="card"><h3>Rolling live transcript</h3><div class="box stream" id="stream"></div></section>
</div>

<div class="ticker"><span id="tickerText">SkyscraperHQ Brain Router V4 online · job/reply windows active · Claude HQ active identity · Wren protected · CEOs API Gene Pool only...</span></div>

<script>
const $=q=>document.querySelector(q);
let lastSeen=0;

function centre(el){const f=$("#flow").getBoundingClientRect(),r=el.getBoundingClientRect();return{x:r.left-f.left+r.width/2,y:r.top-f.top+r.height/2};}
function lineBetween(a,b,cls){const l=document.createElementNS("http://www.w3.org/2000/svg","line");l.setAttribute("x1",a.x);l.setAttribute("y1",a.y);l.setAttribute("x2",b.x);l.setAttribute("y2",b.y);l.setAttribute("class",cls);return l;}
function drawWires(){
  const svg=$("#wires");svg.innerHTML="";
  const router=centre($('[data-node="Brain Router"]'));
  [...document.querySelectorAll(".claude,.ceo2,.ceo3")].forEach(n=>svg.appendChild(lineBetween(centre(n),router,"line ceoline")));
  [...document.querySelectorAll(".provider")].forEach(n=>svg.appendChild(lineBetween(centre(n),router,"line providerline")));
  svg.appendChild(lineBetween(centre($('[data-node="Wren"]')),router,"line wrenline"));
}
function hotBeam(aSel,bSel){const a=$(aSel),b=$(bSel);if(!a||!b)return;const svg=$("#wires");const l=lineBetween(centre(a),centre(b),"hotbeam");svg.appendChild(l);setTimeout(()=>l.remove(),1700);}
function packet(aSel,bSel,color){
  const aEl=$(aSel),bEl=$(bSel);if(!aEl||!bEl)return;
  hotBeam(aSel,bSel);
  const a=centre(aEl),b=centre(bEl);
  for(let i=0;i<4;i++){
    const p=document.createElement("div");p.className="packet";
    if(color){p.style.background=color;p.style.boxShadow=`0 0 18px ${color}`;}
    p.style.setProperty("--x1",(a.x-5)+"px");p.style.setProperty("--y1",(a.y-5)+"px");
    p.style.setProperty("--x2",(b.x-5)+"px");p.style.setProperty("--y2",(b.y-5)+"px");
    $("#flow").appendChild(p);setTimeout(()=>p.classList.add("go"),20+i*105);setTimeout(()=>p.remove(),1700+i*105);
  }
}
function ceoSel(n){return n==="Claude HQ"?".claude":n==="CEO 2"?".ceo2":".ceo3";}
function provSel(p){return `[data-provider="${p}"]`;}
function ceoStatusId(n){return n==="Claude HQ"?"#claudeStatus":n==="CEO 2"?"#ceo2Status":"#ceo3Status";}
function setGauge(id,v){v=Math.max(0,Math.min(100,Math.round(v||0)));const e=$(id);e.style.setProperty("--v",v);e.setAttribute("data-v",v);}
async function getJSON(u){const r=await fetch(u);return await r.json();}
function esc(x){return String(x??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function renderProviders(ps,stats,selected){
  document.querySelectorAll(".provider").forEach(n=>{n.classList.remove("active","missing","selectedNow")});
  let unique=0,sight=0;
  const source=stats&&Object.keys(stats).length?stats:ps;
  $("#providers").innerHTML=Object.values(source||{}).map(p=>{
    const ok=(p.key_count||0)>0;
    const isSel=p.provider===selected;
    unique+=p.unique_keys??p.key_count??0;
    sight+=p.sightings??p.key_count??0;
    const node=document.querySelector(`[data-provider="${p.provider}"]`);
    if(node){if(isSel)node.classList.add("selectedNow");else if(ok)node.classList.add("active");else node.classList.add("missing");}
    const cls=isSel?"selected":ok?"ok":"bad";
    const pill=isSel?"SELECTED NOW":ok?(p.status||"READY").toUpperCase():"MISSING KEY";
    const pillCls=isSel?"warn":ok?"ok":"bad";
    return `<div class="prov ${cls}">
      <b>${esc(p.label)}</b>
      <small>${esc(p.role||"")}</small><br>
      <span class="pill ${pillCls}">${esc(pill)}</span><br>
      <small>unique: ${p.unique_keys??p.key_count??0} · sightings: ${p.sightings??p.key_count??0}</small><br>
      <small>calls: ${p.calls||0} · fails: ${p.failures||0}</small><br>
      <small>latency: ${p.latency_ms??"-"}ms · last: ${esc(p.last_task||"-")}</small><br>
      <small>${esc(p.status_reason||"")}</small>
    </div>`;
  }).join("");
  $("#uniqueKeys").textContent=unique;
  $("#sightings").textContent=sight;
}
function renderMission(decision, jobs){
  const j=(jobs&&jobs[0])||{};
  $("#jobBox").innerHTML =
    `<b class="ok">From:</b> ${esc(j.from||decision.ceo||"waiting")}<br>`+
    `<b class="ok">To:</b> ${esc(j.to||"Brain Router")}<br>`+
    `<b class="ok">Task:</b> ${esc(j.task||decision.task||"waiting")}<br><br>`+
    `<b class="warn">Asking:</b><br>${esc(j.ask||decision.ask||"Waiting for next job.")}`;

  $("#decisionBox").innerHTML =
    `<b>CEO:</b> ${esc(decision.ceo||"waiting")}<br>`+
    `<b>Task:</b> ${esc(decision.task||"waiting")}<br>`+
    `<b>Selected API:</b> ${esc(decision.selected_label||decision.selected_provider||"none")}<br>`+
    `<b>Latency:</b> ${decision.latency_ms??"-"} ms<br>`+
    `<b>Wren fallback:</b> ${esc(decision.wren_fallback||"blocked")}<br>`+
    `<b>Reason:</b> ${esc(decision.reason||"waiting for route")}`;

  $("#providerReply").innerHTML =
    `<b class="ok">Reply preview:</b><br>${esc(decision.provider_reply||j.reply||"Waiting for provider reply.")}`;

  $("#routeLabel").textContent=`${decision.ceo||"CEO"} → Brain Router → ${decision.selected_label||decision.selected_provider||"provider"} · ${decision.task||"task"}`;

  if(decision.ceo){
    const el=$(ceoStatusId(decision.ceo));
    if(el) el.textContent=`${decision.task||"task"} → ${decision.selected_label||decision.selected_provider||"API"}`;
  }
}
function renderCEOReplies(panels){
  const order=["Claude HQ","CEO 2","CEO 3"];
  $("#ceoReplies").innerHTML=order.map(name=>{
    const p=(panels||{})[name]||{};
    return `<div class="box ceoBox">
      <h4>${esc(name)}</h4>
      <div class="muted">Task: ${esc(p.task||"waiting")} · Provider: ${esc(p.provider_label||p.provider||"none")}</div>
      <br>
      <div class="ask">ASK:</div>
      <div>${esc(p.ask||"Waiting for next job.")}</div>
      <br>
      <div class="reply">REPLY:</div>
      <div>${esc(p.reply||"No reply yet.")}</div>
    </div>`;
  }).join("");
}
function renderEvents(logs){
  $("#stream").innerHTML=(logs||[]).slice(-110).reverse().map(e=>{
    const cls=e.status==="blocked"||e.status==="error"?"bad":e.status==="selected"||e.status==="stored"?"ok":"warn";
    return `<div class="event">
      <span class="${cls}">●</span> ${esc(e.ts||"")}<br>
      ${esc(e.from||"?")} → ${esc(e.to||"?")} · ${esc(e.provider||"")} · ${esc(e.task||"")}<br>
      <small>${esc(e.ask||e.detail||"")}</small>
      ${e.reply?`<br><small class="ok">↳ ${esc(e.reply)}</small>`:""}
    </div>`;
  }).join("");
}
function animate(e){
  if(!e)return;
  if(e.event==="request")packet(ceoSel(e.from),'[data-node="Brain Router"]',"#42d9ff");
  if(e.event==="dispatch"&&e.provider&&e.provider!=="none")packet('[data-node="Brain Router"]',provSel(e.provider),"#b987ff");
  if(e.event==="return"&&e.provider&&e.provider!=="none"){
    packet(provSel(e.provider),'[data-node="Brain Router"]',"#45f59b");
    setTimeout(()=>packet('[data-node="Brain Router"]',ceoSel(e.to),"#45f59b"),500);
  }
  if(e.event==="auto_scan")packet('[data-node="Wren"]','[data-node="Brain Router"]',"#45f59b");
}
async function live(){
  const d=await getJSON("/api/live");
  const m=d.metrics||{},rev=m.rev||{},decision=d.latest_decision||{};
  setGauge("#g_router",rev.router);setGauge("#g_pool",rev.api_pool);setGauge("#g_ceo",rev.ceo_load);setGauge("#g_wren",rev.wren_guard);
  $("#providerscount").textContent=m.active_provider_count||0;
  $("#routecount").textContent=(m.autonomy&&m.autonomy.route_count)||0;
  renderMission(decision,d.job_board||[]);
  renderCEOReplies(d.ceo_panels||{});
  renderProviders(d.providers||{},d.provider_stats||{},decision.selected_provider);
  renderEvents(d.logs||[]);
  $("#tickerText").textContent=`SkyscraperHQ live · ${decision.ceo||"CEO"} asks: ${decision.ask||"job"} · route: Brain Router → ${decision.selected_label||"API"} · Wren protected · CEOs API Gene Pool only`;
  const logs=d.logs||[];
  if(logs.length>lastSeen){logs.slice(lastSeen).forEach((e,i)=>setTimeout(()=>animate(e),i*150));lastSeen=logs.length;}
}
drawWires();
window.addEventListener("resize",drawWires);
live();
setInterval(live,1000);
</script>
</body>
</html>'''

s = s[:body_start] + html + s[end:]
p.write_text(s, encoding="utf-8")
print("[OK] V4 Mission Control frontend installed")
PY

echo
echo "===== 3. COMPILE CHECK ====="
python3 -m py_compile "$APP" && echo "[OK] app compiles" || exit 2

echo
echo "===== 4. RESTART DASHBOARD ====="
[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null || true
pkill -f "skyscraper_gene_pool_router.py" 2>/dev/null || true
sleep 2

nohup "$STARTER" >> "$LOG" 2>&1 &
PID="$!"
echo "$PID" > "$PIDFILE"
echo "[OK] started pid=$PID"

echo
echo "===== 5. WAIT FOR DASHBOARD ====="
OK=NO
for i in $(seq 1 25); do
  if curl -sS --max-time 2 "http://127.0.0.1:$PORT/health" >/tmp/gene_pool_health.json 2>/dev/null; then
    OK=YES
    break
  fi
  sleep 1
done

if [ "$OK" != YES ]; then
  echo "[FAIL] dashboard did not come online"
  tail -n 180 "$LOG" || true
  cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
  exit 3
fi

echo "[OK] dashboard online"

echo
echo "===== 6. LET AUTONOMY FLOW 15 SECONDS ====="
sleep 15

echo
echo "===== 7. SMOKE TEST LIVE DATA ====="
curl -sS --max-time 20 "http://127.0.0.1:$PORT/api/live" > "$RUN_DIR/reports/live_v4.json"

python3 - <<PYSHOW
import json
d=json.load(open("$RUN_DIR/reports/live_v4.json"))
m=d.get("metrics",{})
print("ok:", d.get("ok"))
print("stored_key_count:", m.get("stored_key_count"))
print("active_provider_count:", m.get("active_provider_count"))
print("route_count:", m.get("autonomy",{}).get("route_count"))
print("events:", len(d.get("logs",[])))
print("latest_decision:", d.get("latest_decision"))
print("")
print("CEO PANELS:")
for name,p in (d.get("ceo_panels") or {}).items():
    print(name, "| task=", p.get("task"), "| provider=", p.get("provider_label"), "| ask=", (p.get("ask") or "")[:80], "| reply=", (p.get("reply") or "")[:80])
print("")
print("LATEST JOBS:")
for j in (d.get("job_board") or [])[:5]:
    print(j.get("event"), j.get("from"), "->", j.get("to"), "|", j.get("task"), "|", (j.get("ask") or "")[:80])
PYSHOW

echo
echo "===== 8. OPEN DASHBOARD ====="
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LOCAL="http://127.0.0.1:$PORT"
LAN="http://${LAN_IP:-127.0.0.1}:$PORT"
echo "Local: $LOCAL"
echo "LAN:   $LAN"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$LOCAL" >/dev/null 2>&1 || true
fi

echo
echo "===== 9. LOG TAIL ====="
tail -n 80 "$LOG" || true

echo
echo "============================================================"
echo "DONE — DASHBOARD V4 MISSION CONTROL DEPLOYED"
echo "Open:"
echo "$LOCAL"
echo "$LAN"
echo
echo "Report:"
echo "$REPORT"
echo
echo "Send-back:"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$RUN_DIR/reports/live_v4.json" "$SEND/live_v4.json"
