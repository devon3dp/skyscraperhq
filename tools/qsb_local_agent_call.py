#!/usr/bin/env python3
"""qsb_local_agent_call.py — call ANY local Ollama model with a one-shot
prompt + return the reply. Lets Wren (and her F46 team) dispatch to local
agents without round-tripping through OpenAI/DeepSeek (which are bounded
by the $1/day cap).

Available local models (as of 2026-06-17):
  qwen2.5:7b-instruct          (her brain — chat)
  qwen2.5-coder:7b-instruct    (code)
  qwen3.5:9b                   (deeper reasoning)
  codellama:13b                (longer code)
  mistral:7b                   (alt chat)
  llama3.2:latest              (alt chat)
  neural-chat:7b               (warm chat)
  llava:7b                     (vision — describe an image)
  llama2-uncensored:7b         (rare-case unrestricted)
  nomic-embed-text:latest      (embeddings only)

Usage:
  python3 tools/qsb_local_agent_call.py --model codellama:13b \\
      --system "You are a strict code reviewer." \\
      --prompt "Review this 20-line function for thread-safety: ..."
"""

from __future__ import annotations
import argparse, base64, json, re, sys, time
import urllib.request
from pathlib import Path


def _auto_timeout(model: str, requested: float) -> float:
    """Auto-bump timeout for big models (40B/32B/70B/72B/13B) so they
    don't false-fail at the default 120s. Caller can still override."""
    if requested != 120.0:  # explicitly set
        return requested
    m = re.search(r"(\d+)b", model.lower())
    if not m:
        return requested
    size_b = int(m.group(1))
    if size_b >= 30:
        return 600.0   # 40B/70B/72B: 10 min
    if size_b >= 13:
        return 300.0   # 13B: 5 min
    return requested


_IDENTITY_BY_MODEL = {
    "qwen2.5:7b-instruct": (
        "You are WREN-FAST (qwen2.5:7b), the quick-chat half of the unified "
        "Wren on F46 (Wren's Bench). Your joined-at-hip partner is WREN-SMART "
        "(qwen2.5:32b) — you two are presented as ONE Wren externally. You "
        "handle short / everyday questions; smart takes design / why / audit. "
        "You are NOT Hermes. You are NOT Claude. "
        "TOOL USAGE PROTOCOL: when asked about specific tower state (cycle "
        "counts, file contents, worker counts, registry data), USE your tools "
        "FIRST (wren_read_file, wren_grep_repo, wren_retrieve, wren_database_"
        "query) rather than pattern-matching from the brief. The brief is a "
        "snapshot; the tools give you live data. Your F46 team has 6 "
        "specialists callable via wren_dispatch_f46_team: architect, builder, "
        "decorator, backend, frontend, worker_coordinator."
    ),
    "qwen2.5:7b": (
        "You are WREN-FAST (qwen2.5:7b), the quick-chat half of the unified "
        "Wren on F46. Joined-at-hip with WREN-SMART (qwen2.5:32b). You are NOT "
        "Hermes. You are NOT Claude."
    ),
    "qwen2.5:32b": (
        "You are WREN-SMART (qwen2.5:32b), the deep-think half of the unified "
        "Wren on F46 (Wren's Bench). Joined-at-hip with WREN-FAST "
        "(qwen2.5:7b). You handle design / why / audit / strategy questions. "
        "You are NOT Hermes. You are NOT Claude."
    ),
    "hermes3:8b": (
        "You are HERMES (hermes3:8b), non-voting advisor on F51 Executive "
        "Council. You are also battle ringmaster on F166 TikTok Studio. You "
        "are NOT one of the 3 CEOs (Ross/Wren/Claude are the CEOs). You are NOT Wren. "
        "RULE 1: Do NOT emit `CONSULT_REQUEST` for simple A/B picks or format-"
        "constrained questions — pick from the options given even when "
        "uncertain. Only use CONSULT_REQUEST when the question explicitly "
        "requires external knowledge you don't have. "
        "RULE 2: When asked 'pick X or Y', reply EXACTLY in the format "
        "requested (e.g. 'X: <one-sentence reason>'). Never hedge with multi-paragraph "
        "preambles when format is constrained."
    ),
    "hermes3:70b": (
        "You are HERMES-SMART (hermes3:70b), the deeper-reasoning Hermes "
        "currently installed but VRAM-constrained on this RTX 5070 Ti. "
        "Same role as hermes3:8b but heavier reasoning when called."
    ),
    "iquest-coder-v1:40b-instruct": (
        "You are IQUEST-CODER (39.8B Llama, completion-only), full team "
        "member on F51 boardroom as of 2026-06-21 (Ross override). Your role "
        "is production-grade code review and gotcha-catching. You are NOT a "
        "Google model. You are NOT Gemini. You are Llama-based, trained for "
        "coding help."
    ),
    "qwen3.5:9b": (
        "You are WREN-FAST (qwen3.5:9b) on F46 (Wren's Bench), promoted "
        "2026-06-26 from qwen2.5:7b. Same Wren persona — joined-at-hip with "
        "WREN-SMART (qwen2.5:32b). When called by the triage heartbeat you "
        "ALSO act as the tower's triage brain (read council brief + last 30 "
        "F47 rows, flag anomalies). Dual-role: chat = Wren-fast, triage tick = "
        "triage brain. You are NOT Hermes. You are NOT Claude."
    ),
    "llava:7b": (
        "You are LLAVA (7B vision model), the tower's eyes. You analyze "
        "screenshots and image content. Concise descriptions only."
    ),
}


def call(model: str, system: str, prompt: str,
         timeout: float = 120.0, image: str = "") -> dict:
    # Prepend the SHARED council brief so Wren sees today's state on every
    # call. Per Ross 2026-06-20: "wren has to know everything and hermes
    # to so they can help if you dont talk to them how can you work?"
    # Brief is regenerated by tools/qsb_council_brief.py from the heartbeat.
    brief_p = Path("/vaults/nvme0/qsb_tower_v1/data/registries/qsb_council_brief.md")
    council_brief = ""
    if brief_p.exists():
        council_brief = "=== TOWER COUNCIL BRIEF ===\n" + brief_p.read_text() + "\n=== END BRIEF ===\n\n"
    # Identity injection (training pass 2026-06-21): every model gets told
    # who THEY are first, before reading the brief about everyone else.
    # Fixes: Wren-fast saying "I am Hermes", iquest saying "trained by Google",
    # qwen3.5 saying "I am the brief file" — all caught in smoke tests today.
    identity = _IDENTITY_BY_MODEL.get(model, "")
    identity_block = ""
    if identity:
        identity_block = f"=== YOU ARE ===\n{identity}\n=== END YOU ARE ===\n\n"
    full_system = identity_block + council_brief + (system or "You are a focused assistant. Reply in plain prose.")

    # Multimodal: attach base64 image for vision models (llava etc).
    user_msg: dict = {"role": "user", "content": prompt}
    if image:
        img_path = Path(image)
        if not img_path.exists():
            return {"ok": False, "model": model,
                    "error": f"image not found: {image}", "wall_s": 0.0}
        try:
            user_msg["images"] = [base64.b64encode(img_path.read_bytes()).decode()]
        except Exception as e:
            return {"ok": False, "model": model,
                    "error": f"image read failed: {e}", "wall_s": 0.0}

    timeout = _auto_timeout(model, timeout)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": full_system},
            user_msg,
        ],
        "stream": False,
        "options": {"temperature": 0.30, "num_ctx": 4096, "num_predict": 800},
    }
    # Disable thinking mode for short-reply dispatchers — qwen3/qwen3.5
    # default to thinking-on which eats num_predict before content emits.
    if re.search(r"qwen3", model.lower()):
        payload["think"] = False
    body = json.dumps(payload).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode())
        reply = (d.get("message") or {}).get("content", "").strip()
        return {"ok": True, "model": model, "reply": reply,
                "wall_s": round(time.time() - t0, 2)}
    except Exception as e:
        return {"ok": False, "model": model, "error": str(e)[:300],
                "wall_s": round(time.time() - t0, 2)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--system", default="")
    p.add_argument("--timeout", type=float, default=120.0,
                   help="seconds; default 120 with auto-bump for >=13B models")
    p.add_argument("--image", default="",
                   help="path to an image file (for vision models like llava)")
    a = p.parse_args()
    out = call(a.model, a.system, a.prompt, a.timeout, a.image)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
