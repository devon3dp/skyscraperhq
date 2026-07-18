#!/usr/bin/env python3
import json, pathlib, urllib.request, datetime, time, os, traceback

TOWER = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
BASE = TOWER / "data/night_council"
RUN = BASE / ("v1_team_overnight_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
RUN.mkdir(parents=True, exist_ok=True)
(RUN / "cycles").mkdir(exist_ok=True)

(BASE / "latest_run_path.txt").write_text(str(RUN), encoding="utf-8")

LEDGER = RUN / "team_overnight_ledger.jsonl"
SUMMARY = RUN / "team_latest_summary.txt"
NOTES = RUN / "team_runner.log"

MODEL = os.environ.get("QSB_V1_TEAM_MODEL", "qwen2.5:14b")
SLEEP = int(os.environ.get("QSB_V1_TEAM_SLEEP", "900"))
CYCLES = int(os.environ.get("QSB_V1_TEAM_CYCLES", "48"))

ENDPOINTS = {
    "brain_router": "http://127.0.0.1:8853/health.json",
    "task_council": "http://127.0.0.1:8854/health.json",
    "asa": "http://127.0.0.1:9122/heartbeat.json",
    "tp_pip": "http://192.168.1.91:9110/heartbeat.json",
    "ollama": "http://127.0.0.1:11434/api/tags",
    "boardroom": "http://127.0.0.1:8852/",
}

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def note(msg):
    with NOTES.open("a", encoding="utf-8") as f:
        f.write(f"[{now()}] {msg}\n")

def get_url(url, timeout=8, limit=1500):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QSB-V1-Night-Team"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit).decode("utf-8", errors="replace")
            return {"ok": True, "status": getattr(r, "status", None), "sample": body[:900]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

def post_json(url, payload, timeout=180, limit=12000):
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json","User-Agent":"QSB-V1-Night-Team"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit).decode("utf-8", errors="replace")
            return {"ok": True, "status": getattr(r, "status", None), "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}

def answer_from(resp):
    if not resp.get("ok"):
        return "NOT_OK: " + resp.get("error", "")
    body = resp.get("body", "")
    try:
        j = json.loads(body)
        return j.get("answer") or j.get("response") or j.get("result") or body[:4000]
    except Exception:
        return body[:4000]

def cycle(n):
    cdir = RUN / "cycles" / f"cycle_{n:03d}"
    cdir.mkdir(parents=True, exist_ok=True)

    endpoints = {k: get_url(v) for k,v in ENDPOINTS.items()}
    (cdir / "endpoints.json").write_text(json.dumps(endpoints, indent=2), encoding="utf-8")

    packet = {
        "cycle": n,
        "timestamp": now(),
        "active_root": str(TOWER),
        "mode": "V1 overnight read-only team study",
        "endpoints": endpoints,
        "truth": {
            "model_weight_learning": False,
            "destructive_actions": False,
            "trading_changes": False,
            "memory_overwrite": False
        }
    }

    prompt = f"""
HQ-Claude V1 overnight green-light cycle.

Active root is /vaults/nvme0/qsb_tower_v1.
Do not use /vaults/nvme0/qsb_skyscraper as the live service root.
Study only the endpoint packet and produce a short night status.

Required headings:
1. HQ STATUS
2. BRAIN ROUTER STATUS
3. TASK COUNCIL STATUS
4. WREN / ASA / TP-PIP STATUS
5. SAFE MORNING ACTION
6. PROOF LABELS

Truth rules:
- No model-weight training claim.
- No destructive actions.
- No trading changes.
- If proof is endpoint proof, say ENDPOINT PROOF.
- If inferred, say INFERRED.

Packet:
{json.dumps(packet, indent=2)[:9000]}
"""

    hq = post_json("http://127.0.0.1:8853/chat", {
        "message": prompt,
        "model": MODEL,
        "task_gate": "read_only"
    }, timeout=240)

    if not hq.get("ok"):
        fallback = post_json("http://127.0.0.1:11434/api/generate", {
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=240)
        hq = {"ok": fallback.get("ok"), "provider_path": "local_ollama_fallback", "body": fallback.get("body",""), "error": fallback.get("error","")}

    asa = post_json("http://127.0.0.1:9122/task", {
        "task_id": f"v1_asa_night_cycle_{n:03d}",
        "instruction": "Asa V1 night clerk: summarise endpoint state and record proof labels. Read-only. No destructive action.",
        "task_gate": "read_only",
        "model": MODEL
    }, timeout=180)

    tp = post_json("http://192.168.1.91:9110/task", {
        "task_id": f"v1_tp_night_cycle_{n:03d}",
        "instruction": "TP-Pip V1 night pulse: report heartbeat/proof/dashboard state if task endpoint exists. Read-only.",
        "task_gate": "read_only",
        "model": MODEL
    }, timeout=30)

    row = {
        "timestamp": now(),
        "cycle": n,
        "active_root": str(TOWER),
        "model": MODEL,
        "endpoints_ok": {k:v.get("ok") for k,v in endpoints.items()},
        "hq_ok": bool(hq.get("ok")),
        "asa_task_ok": bool(asa.get("ok")),
        "tp_task_ok": bool(tp.get("ok")),
        "claude_api_used": False,
        "destructive_actions": False,
        "trading_changes": False,
        "hq_preview": answer_from(hq)[:1600],
        "asa_preview": answer_from(asa)[:900],
        "tp_preview": answer_from(tp)[:600],
        "cycle_dir": str(cdir)
    }

    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    human = []
    human.append("QSB V1 TEAM OVERNIGHT LATEST SUMMARY")
    human.append(f"timestamp: {now()}")
    human.append(f"active_root: {TOWER}")
    human.append(f"cycle: {n}/{CYCLES}")
    human.append(f"model: {MODEL}")
    human.append("mode: READ_ONLY_V1_TEAM_STUDY")
    human.append("model_weight_learning: false")
    human.append("destructive_actions: false")
    human.append("trading_changes: false")
    human.append("")
    human.append("ENDPOINTS:")
    for k,v in endpoints.items():
        human.append(f"  {k}: {'UP' if v.get('ok') else 'DOWN'}")
    human.append("")
    human.append("HQ:")
    human.append(row["hq_preview"])
    human.append("")
    human.append("ASA:")
    human.append(row["asa_preview"])
    human.append("")
    human.append("TP:")
    human.append(row["tp_preview"])
    SUMMARY.write_text("\n".join(human), encoding="utf-8")

    (cdir / "cycle_summary.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row

note("V1 overnight team worker started")
for i in range(1, CYCLES + 1):
    try:
        note(f"cycle {i} start")
        cycle(i)
        note(f"cycle {i} complete")
    except Exception:
        note("cycle failed:\n" + traceback.format_exc())
    if i < CYCLES:
        time.sleep(SLEEP)
note("V1 overnight team worker finished")
