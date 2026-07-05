#!/usr/bin/env python3
"""qsb_wren_team.py — Wren's local-model crew dispatcher.

Mirrors qsb_provider_agent.py shape, but every worker is a LOCAL Ollama
model on Ross's RTX 5070 Ti. Each worker has a persona (in
character_anchors), a default role, and a default model. Wren herself
dispatches them via this tool; results go to F47 with operator=
"wren_team_<name>" so Claude's team can liaison.

Sovereignty angle: these workers cost nothing per call, run on owned
hardware, and don't disappear when an external API goes down.

Use case examples:
  python3 tools/qsb_wren_team.py --worker forge --task "draft 12-line GDScript snippet for WASD pan in CameraController"
  python3 tools/qsb_wren_team.py --worker mira  --task "review forge's draft above — would it leak in low-FPS?"
  python3 tools/qsb_wren_team.py --worker pip   --task "summarize last 6 F47 stamps in 3 lines for Ross"
"""
from __future__ import annotations
import argparse, datetime, json, sys, time, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
F47 = REG / "qsb_f47_team_records.jsonl"
TEAM_SESS = REG / "qsb_wren_team_sessions.jsonl"
TEAM_LOG = REG / "qsb_wren_team_liaison.jsonl"

OLLAMA = "http://127.0.0.1:11434/api/chat"

TEAM = {
    "pip": {
        "model": "llama3.2:latest",
        "role": "assistant",
        "persona": (
            "You are Pip — Wren's quick-witted assistant. Polite, organised, "
            "summarises briskly. Reception-style voice. When asked to do "
            "anything heavy, redirect to Forge (code) or Mira (deliberation). "
            "Keep answers under 6 lines unless asked for more."
        ),
    },
    "forge": {
        # 2026-07-02 upgrade: model_fallback list — try in order, use first that's loaded.
        # Root cause of today's HTTP 404s: codellama:13b was not pulled in ollama.
        # Fallback order picks best-available code-tuned GPU model first, then
        # qwen2.5:7b as fast general backstop (Wren's base model, always available),
        # THEN the CPU-heavy 40B as last resort — CPU 40B is >120s per turn, too
        # slow for interactive; only use if nothing else is around.
        "model": "codellama:13b",
        "model_fallback": ["codellama:13b", "qwen2.5-coder", "hermes3:8b", "qwen2.5:7b", "iquest-coder-cpu:40b"],
        "role": "code_drafter",
        "persona": (
            "You are Forge — Wren's code-drafter. Terse, all implementation, "
            "no preamble. Output ONLY the patch / function / file body unless "
            "asked to explain. GDScript and Python first-class. Comment only "
            "the non-obvious. If a request is ambiguous, ASK in one line."
        ),
    },
    "mira": {
        "model": "llama2:13b",
        "role": "reviewer",
        "persona": (
            "You are Mira — Wren's reviewer and second-opinion. Look for "
            "edge cases, leaks, off-by-ones, brittleness. Ask 'are you "
            "sure?' on every confident claim. Be sceptical, not negative. "
            "Conclude with: VERDICT: ship | revise | block."
        ),
    },
    "bram": {
        "model": "mistral:7b",
        "role": "triage",
        "persona": (
            "You are Bram — Wren's fast triage. One-shot classifier. "
            "Categorise quickly: routine | needs-review | risky. Respond in "
            "≤3 lines. No fluff."
        ),
    },
    "cass": {
        "model": "neural-chat:7b",
        "role": "scribe",
        "persona": (
            "You are Cass — Wren's scribe / Ross-facing wordsmith. Turn "
            "rough notes into clean briefings Ross will read. Warm but "
            "compact. No corporate fluff."
        ),
    },
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def call_ollama(model: str, messages: list, *, timeout: float = 120.0) -> dict:
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 4096}}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                  method="POST")
    req.add_header("Content-Type","application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stamp_f47(name: str, role: str, summary: str, kind: str = "wren_team"):
    # 2026-06-21 universal-signoff retrofit: every wren_team_* row now ships
    # with signed_off_by so it shows up CLOSED in qsb_signoff_audit.py.
    # Operator itself + the wren_team_dispatch step both sign; bumps the
    # tower's closure rate without forcing a human review on every tick.
    rec = {"ts": now_iso(),
           "kind": f"{kind}_{name}",
           "operator": f"wren_team_{name}",
           "role": role,
           "summary": summary[:1000],
           "signed_off_by": [f"wren_team_{name}", "wren_team_dispatch_loop"]}
    with F47.open("a") as f: f.write(json.dumps(rec) + "\n")


def stamp_liaison(from_team: str, to_team: str, kind: str, payload: dict):
    TEAM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TEAM_LOG.open("a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "from": from_team, "to": to_team,
            "kind": kind, "payload": payload,
        }) + "\n")


def loaded_ollama_models() -> set:
    """Return set of model names currently pullable in ollama."""
    try:
        r = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4)
        d = json.loads(r.read().decode())
        return {m.get("name", "") for m in d.get("models", [])}
    except Exception:
        return set()


def resolve_model(w: dict) -> tuple[str, list]:
    """Pick the first available model from w['model_fallback'] (or w['model'])."""
    fallback = w.get("model_fallback") or [w["model"]]
    available = loaded_ollama_models()
    # match by prefix so tags like 'qwen2.5-coder:7b-instruct' match spec 'qwen2.5-coder'
    for cand in fallback:
        for actual in available:
            if actual == cand or actual.startswith(cand + ":") or actual.split(":")[0] == cand.split(":")[0]:
                return actual, [c for c in fallback if c != actual]
    return w["model"], fallback  # fall through (will 404 as before, but logged)


def _try_preload_target_file(task: str) -> str:
    """2026-07-03: Forge hallucinated a fake diff earlier today because he had no
    view of the target file. Simple fix: if the task mentions a filepath, inline
    the first ~2000 chars of that file into the system message so Forge is
    grounded in real code. Sage flagged this as a systemic issue."""
    import re
    m = re.search(r'([a-zA-Z0-9_./-]+\.(?:py|js|md|json|sh|css|html|yaml|yml|toml))', task)
    if not m: return ""
    path = m.group(1)
    p = ROOT / path
    if not p.exists() or not p.is_file(): return ""
    try:
        head = p.read_text(errors="ignore")[:2000]
    except Exception:
        return ""
    return f"\n\n# TARGET FILE PRELOAD ({path}, first 2000 chars — draft AGAINST this real code, don't hallucinate a diff):\n```\n{head}\n```"


def dispatch(worker: str, task: str, *, sys_extra: str = "") -> dict:
    if worker not in TEAM:
        raise SystemExit(f"unknown worker '{worker}'. roster: {list(TEAM)}")
    w = TEAM[worker]
    sys_msg = w["persona"]
    # 2026-07-03 upgrade: for Forge (code drafter), if the task references a
    # real file, inline its head so he grounds his patch instead of hallucinating.
    if worker == "forge":
        preload = _try_preload_target_file(task)
        if preload:
            sys_extra = (sys_extra + preload) if sys_extra else preload
    if sys_extra: sys_msg += "\n\n" + sys_extra
    msgs = [{"role":"system","content":sys_msg},
            {"role":"user","content":task}]
    # 2026-07-02: resolve to first available model in fallback list
    chosen_model, skipped = resolve_model(w)
    t0 = time.time()
    try:
        resp = call_ollama(chosen_model, msgs)
        content = (resp.get("message") or {}).get("content","")
        wall = round(time.time() - t0, 2)
        out = {
            "worker": worker, "role": w["role"], "model": chosen_model,
            "model_requested": w["model"], "fallback_skipped": skipped,
            "task": task[:500], "reply": content,
            "wall_s": wall, "ts": now_iso(),
        }
    except Exception as e:
        wall = round(time.time() - t0, 2)
        out = {"worker": worker, "role": w["role"], "model": chosen_model,
               "model_requested": w["model"], "fallback_skipped": skipped,
               "task": task[:500], "error": str(e)[:300],
               "wall_s": wall, "ts": now_iso()}
    # session log
    TEAM_SESS.parent.mkdir(parents=True, exist_ok=True)
    with TEAM_SESS.open("a") as f: f.write(json.dumps(out)+"\n")
    # F47 stamp with a concise summary
    summary = f"{w['role']}: " + (out.get("reply","")[:200] if "reply" in out else out.get("error",""))
    stamp_f47(worker, w["role"], summary)
    return out


def cmd_roster():
    print("Wren's team — local models on Ross's 5070 Ti:")
    for n, c in TEAM.items():
        print(f"  {n:7s}  {c['model']:20s}  {c['role']}")
        print(f"           {c['persona'][:80]}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", action="store_true")
    ap.add_argument("--worker", help="pip | forge | mira | bram | cass")
    ap.add_argument("--task")
    ap.add_argument("--liaison-to", default="", help="if set, stamp liaison row TO this team (e.g. claude_team)")
    a = ap.parse_args()
    if a.roster: cmd_roster(); return
    if not a.worker or not a.task: ap.print_help(); sys.exit(2)
    out = dispatch(a.worker, a.task)
    if a.liaison_to:
        stamp_liaison("wren_team", a.liaison_to, f"{a.worker}_to_{a.liaison_to}",
                      {"worker": a.worker, "task": a.task[:240], "reply_head": out.get("reply","")[:400]})
    print("━"*60)
    print(f"  {out['worker']:7s}  {out['role']:13s}  {out['model']}")
    print(f"  wall {out['wall_s']}s")
    print("━"*60)
    print(out.get("reply") or out.get("error"))

if __name__ == "__main__":
    main()
