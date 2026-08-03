#!/usr/bin/env python3
"""
qsb_council15_tools.py — the COUNCIL-OF-15 TOOL DISPATCH (2026-07-18, Ross: "use the council
of 15 ... lots of others as tools for the ceos and wren to use, hermes as well").

The council is the 4 CEOs (Wren, Pip, Asa, Bill) PLUS a roster of TOOLS they wield. This module
lets an owner CEO pick the RIGHT tool for a task and actually USE it to produce a genuine
deliverable — instead of the bare qwen2.5:7b that generated text the honest verifier always
rejected. Tools are loaded from data/registries/wren_local_workforce_registry.json (the real
roster) so this stays in sync with what Wren already has.

select_tool(title, desc) -> tool spec   (keyword routing over the real roster)
use_tool(tool, spec, context, target_file) -> {ok, output, tool, model, artifact_path, ...}

No gates flipped. Producing a deliverable != applying it — application still goes through the
council's independent verification + Ross gate.
"""
import os, sys, json, time, subprocess, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
REG = os.path.join(ROOT, "data", "registries", "wren_local_workforce_registry.json")
OLLAMA = "http://127.0.0.1:11434/api/generate"

# 2026-07-29 STRONG-CODER path config (BUILD PIECE 1 of 3). Routes kind=coder / code BUILD
# tasks through a STRONG cloud coder (OpenAI, e.g. gpt-4o-mini/gpt-4o) via the AUTHORIZED
# consult path (tools/qsb_consult_external.py) — which enforces the $1/day advisory cap, the
# per-call cap, and writes a provider_call audit row + spend ledger entry for every call.
# The weak local iquest-40B coder stays as an HONEST fallback when OpenAI is unavailable
# (no key / 401 / over-cap / unknown model). No gates flipped, no fake output.
STRONG_CODER_CONFIG = os.path.join(ROOT, "data", "registries", "qsb_council15_strong_coder_config.json")


def _load_strong_coder_config() -> dict:
    """Load the strong-coder config; safe defaults if missing/unreadable."""
    defaults = {"enabled": True, "provider": "openai", "model": "gpt-4o-mini",
                "fallback_model": "gpt-4o", "max_output_tokens": 4096,
                "reason_tag": "council_strong_coder_build"}
    try:
        d = json.load(open(STRONG_CODER_CONFIG))
        if isinstance(d, dict):
            defaults.update({k: d[k] for k in defaults if k in d})
    except Exception:
        pass
    return defaults

# 2026-07-19 Ross "wren can use the claude specialist": the caged Claude (Max subscription /
# account mode) is a council-of-15 tool too — the most capable, used SPARINGLY for COMPLEX builds
# iQuest 40B can't finish on CPU. Invoked with the paid key UNSET so it uses the free Max
# subscription (paid API is dead). Routine code still goes to iQuest to preserve Max quota.
_COMPLEX_WORDS = ("3d", "holographic", "hologram", "webgl", "three.js", "threejs", "tour",
                  "dashboard", "animation", "game", "engine", "shader", "cockpit", "visualization")

# Keyword routing → which council-of-15 tool the owner should USE.
_CODE_WORDS = ("code", "build", "implement", "fix", "add ", "wire", "endpoint", "page",
               "dashboard", "3d", "tour", "html", "javascript", " js", "css", "pipeline",
               "api", "script", "bug", "patch", "render", "function", "class ")
_GOV_WORDS = ("govern", "rule", "risk", "audit", "review", "second opinion", "policy",
              "compliance", "cost", "sanity")
_RESEARCH_WORDS = ("research", "investigate", "find out", "compare", "options", "curriculum")


def _load_roster():
    try:
        d = json.load(open(REG))
        return d.get("workers", []) if isinstance(d, dict) else []
    except Exception:
        return []


def _produce_on_worker_box(prompt: str, timeout_s: int = 150) -> dict:
    """2026-07-29 councilbottleneck fix. PRODUCE a research/general artifact on a LIVE worker BOX
    (Acer/ThinkPad cockpit :9120/api/chat), NOT the contended main-box Ollama. Cockpit addresses are
    resolved live from presence.json so IP churn can't break it. Tries the fast box (Acer/.41, GPU
    llama3.2 ~20s) then the slow one (ThinkPad/.91, CPU llama3.2 ~8-60s) with generous timeouts.
    Returns {ok, output, chars, model, produced_by, elapsed_s}. ok=False when no box answers — the
    caller then falls back to the main box, and a genuinely-empty reply stays a FAILED attempt
    (never fabricated)."""
    try:
        from qsb_task_council_run import _resolve_peer
    except Exception:
        return {"ok": False, "error": "peer resolver unavailable"}
    # fast box first, then the slow CPU box. per-box timeout is bounded but generous for CPU.
    for cid, per_to in (("acer_cass", min(timeout_s, 90)), ("tp_pip", min(timeout_s, 120))):
        url = _resolve_peer(cid)  # http://<ip>:9120/api/chat
        if not url:
            continue
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=json.dumps({"prompt": prompt}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=per_to) as r:
                j = json.loads(r.read() or b"{}")
            out = (j.get("reply") or j.get("response") or j.get("text") or "").strip()
            if out:
                return {"ok": True, "output": out, "chars": len(out),
                        "model": f"{cid}:cockpit", "produced_by": cid,
                        "elapsed_s": round(time.time() - t0, 1)}
        except Exception:
            continue
    return {"ok": False, "error": "no worker box produced a reply"}


def _ollama_generate_alive(model: str = None, timeout_s: float = 6.0, keep_alive: str = None) -> bool:
    """FIX P1 (councilfix): FAST health probe of the Ollama /api/generate path before we route a
    coder task to iQuest-40B. The 40B model at 127.0.0.1:11434 is frequently DEAD (connection
    refused) or hangs for hours producing 0 chars on CPU (CLAUDE.md: it 'can't finish on CPU').
    A tiny 1-token generate proves the endpoint actually answers; if it doesn't, callers fall back
    to the Claude specialist instead of looping 0-char attempts for hours.

    keep_alive (2026-07-29 hermes-dark fix): when supplied (e.g. "25m"), a SUCCESSFUL probe pins
    the model resident in VRAM for that window. This is the honest fix for hermes going dark: on a
    16GB GPU shared with qwen2.5:14b (~12GB), a cold hermes3:8b load loses the eviction race and
    times out. Once it answers with keep_alive set it stays warm, so the next liveness tick's probe
    returns immediately and the hermes station stays LIT. Still honest — a probe that never answers
    still returns False and the station stays dark; nothing is fabricated."""
    try:
        body = {"model": model or "iquest-coder-v1:40b-instruct", "prompt": "ok",
                "stream": False, "options": {"num_predict": 1, "num_ctx": 256}}
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            j = json.loads(r.read().decode())
        # a real answer has a 'response' key (even if empty) and no fatal error
        return ("response" in j) and not j.get("error")
    except Exception:
        return False


def _strip_code_fences(code: str) -> str:
    """Remove a leading ```lang line and trailing ``` if the model wrapped output."""
    code = (code or "").strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[-1] if "\n" in code else ""
        if code.rstrip().endswith("```"):
            code = code.rstrip()[:-3].rstrip()
    return code.strip()


def _strong_coder_build(spec: str, context: str = "", target_file: str = "",
                        cfg: dict = None) -> dict:
    """STRONG-CODER path: build the code deliverable via OpenAI through the AUTHORIZED
    consult path (tools/qsb_consult_external.py). Reuses that module's library functions so
    ALL cost-gating ($1/day advisory cap, per-call cap) and audit (provider_call event +
    spend ledger row) happen in the single authorized place.

    Returns {ok, output, tool, model, cost_usd, elapsed_s, chars} on success, or
    {ok: False, error, unavailable: True, ...} when OpenAI is unavailable (no key / 401 /
    over-cap / unknown model) so the caller can fall back to the local coder HONESTLY.
    """
    cfg = cfg or _load_strong_coder_config()
    t0 = time.time()
    provider = cfg.get("provider", "openai")
    model = cfg.get("model", "gpt-4o-mini")
    max_tokens = int(cfg.get("max_output_tokens", 4096))
    reason = cfg.get("reason_tag", "council_strong_coder_build")

    try:
        import qsb_consult_external as cx
    except Exception as e:
        return {"ok": False, "unavailable": True,
                "error": f"consult path unimportable: {str(e)[:120]}",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}

    # Authorization + caps must be live, else fall back honestly (never bypass).
    try:
        auth = cx.load_auth()
    except SystemExit as e:
        return {"ok": False, "unavailable": True, "error": f"consult unauthorized: {str(e)[:120]}",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}
    if provider not in auth.get("providers_authorized", []):
        return {"ok": False, "unavailable": True, "error": f"provider {provider} not authorized",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}
    if model not in cx.PRICING.get(provider, {}):
        return {"ok": False, "unavailable": True,
                "error": f"model {model} not in consult PRICING table",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}

    # 2026-07-29 FIX: for EDITING an existing file, do a SURGICAL ANCHORED INSERTION instead of a
    # full rewrite. Rewriting a whole module from a prompt drops/breaks existing code (that's how a
    # generated tour-guide module 404'd the root route). In edit mode we ask for a precise
    # {anchor, insert} and splice it into the UNTOUCHED original, so regression is structurally
    # impossible. Full-file build is kept for NEW files (no existing content to preserve).
    _tf = None
    current = ""
    if target_file:
        try:
            p = target_file if os.path.isabs(target_file) else os.path.join(ROOT, target_file)
            if os.path.isfile(p):
                _tf = p
                current = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            current = ""
    edit_mode = bool(current)

    if edit_mode:
        prompt = (
            "You are a STRONG senior coder editing an EXISTING file for the SkyscraperHQ council. "
            "Make the SMALLEST surgical change that satisfies the task. DO NOT rewrite the file — "
            "only ADD new lines; never remove or alter existing lines.\n\n"
            "Output EXACTLY this plain-text format (NO json, NO markdown fences), nothing else:\n"
            "ANCHOR: <one EXACT existing line copied verbatim from the file, that appears EXACTLY "
            "ONCE, after which your new code goes. CHOOSE CAREFULLY: pick the LAST line of a complete "
            "statement/block at the SAME nesting level where your new code should live, so your "
            "insertion becomes a SIBLING, not nested inside it. E.g. to add a new route handler, "
            "anchor on the closing `return ...` line of the PREVIOUS route handler, not on its `if:` line.>\n"
            "INSERT:\n"
            "<your new code block, indented to the SAME column as the anchor line (sibling level), "
            "as many lines as needed>\n"
            "END_INSERT\n"
            "SUMMARY: <one short sentence>\n\n"
            "The ANCHOR line must be copied character-for-character (same indentation) from the file "
            "below and be unique. If you cannot do it as a pure insertion, output exactly: CANNOT: <reason>\n\n"
            "TASK: " + spec + "\n\nTARGET FILE: " + (target_file or "") +
            "\n\n--- CURRENT FILE (pick the anchor from here; do not rewrite) ---\n" + current[:48000]
        )
    else:
        kind_word = "the FULL new file content"
        prompt = (
            "You are a STRONG senior coder used by the SkyscraperHQ council as a tool. "
            "Produce ONLY " + kind_word + " for the task below. "
            "Output MUST be complete, syntactically valid, runnable code — NOT a description, "
            "NOT a 'proposed enhancement', NOT a diff, NOT TODO stubs, NOT partial. "
            "No prose, no explanation, no markdown fences.\n\n"
            "After the code, on a final line, emit exactly:  #SUMMARY: <one short sentence of what changed>\n\n"
            "TASK: " + spec
        )
        if context:
            prompt += "\n\n--- CONTEXT ---\n" + context[:16000]

    # Cost-gate BEFORE sending, mirroring the CLI's checks exactly.
    caps = auth["hard_caps_usd"]
    per_call_cap = float(caps["per_call_cap_usd"])
    daily_cap = float(caps["daily_budget_usd"])
    spent = cx.today_spend_usd()
    est = cx.estimate_cost(provider, model, len(prompt), max_tokens)
    if est > per_call_cap:
        return {"ok": False, "unavailable": True,
                "error": f"est ${est:.4f} > per-call cap ${per_call_cap:.4f}",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}
    if spent + est > daily_cap:
        return {"ok": False, "unavailable": True,
                "error": f"daily cap would exceed (today ${spent:.4f} + est ${est:.4f} > ${daily_cap:.4f})",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}

    # Real call via the authorized channel.
    keys = cx.load_keys()
    try:
        result = cx.call_chat(provider, model, prompt, max_tokens, keys)
    except SystemExit as e:  # e.g. key missing in vault
        cx.append_activity("provider_call", f"FAILED {provider}/{model} (council strong coder)",
                           {"provider": provider, "model": model, "ok": False,
                            "error": str(e)[:200], "reason": reason})
        return {"ok": False, "unavailable": True, "error": f"consult refused: {str(e)[:140]}",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:  # network / 401 / HTTP error
        cx.append_activity("provider_call", f"FAILED {provider}/{model} (council strong coder)",
                           {"provider": provider, "model": model, "ok": False,
                            "error": str(e)[:200], "reason": reason})
        return {"ok": False, "unavailable": True, "error": f"openai call failed: {str(e)[:140]}",
                "model": f"{provider}::{model}", "elapsed_s": round(time.time() - t0, 1)}

    # Record real cost + audit rows (same shape the CLI writes).
    actual = cx.actual_cost(provider, model, result.get("usage") or {})
    audit = {"ts": cx.now_ts(), "provider": provider, "model": model, "reason": reason,
             "prompt_chars": len(prompt),
             "prompt_tokens": (result.get("usage") or {}).get("prompt_tokens"),
             "completion_tokens": (result.get("usage") or {}).get("completion_tokens"),
             "cost_usd": actual, "spent_today_after_usd": round(spent + actual, 6),
             "daily_cap_usd": daily_cap}
    cx.append_spend(audit)
    cx.append_activity("provider_call",
                       f"{provider}/{model} cost=${actual:.4f} reason={reason}", audit)

    raw = (result.get("text") or "").strip()

    if edit_mode:
        # Parse the marker-delimited edit (robust for multi-line code — no JSON escaping needed)
        # and splice into the UNTOUCHED original.
        import re as _re2
        body = _strip_code_fences(raw)
        if _re2.match(r"\s*CANNOT\s*:", body):
            return {"ok": False, "output": "", "error": f"coder declined: {body.strip()[:100]}",
                    "tool": f"Strong Coder ({provider} {model})", "model": f"{provider}::{model}",
                    "cost_usd": actual, "elapsed_s": round(time.time() - t0, 1), "chars": 0}
        am = _re2.search(r"^ANCHOR:[ \t]*(.+)$", body, _re2.MULTILINE)
        im = _re2.search(r"^INSERT:[ \t]*\n(.*?)\n[ \t]*END_INSERT", body, _re2.DOTALL | _re2.MULTILINE)
        sm = _re2.search(r"^SUMMARY:[ \t]*(.+)$", body, _re2.MULTILINE)
        if not am or not im:
            return {"ok": False, "output": "",
                    "error": f"edit markers not found (anchor={bool(am)} insert={bool(im)})",
                    "tool": f"Strong Coder ({provider} {model})", "model": f"{provider}::{model}",
                    "cost_usd": actual, "elapsed_s": round(time.time() - t0, 1), "chars": 0}
        anchor = am.group(1).rstrip("\r\n")
        insert = im.group(1)
        summary = sm.group(1).strip() if sm else ""
        # anchor must exist EXACTLY ONCE, verbatim
        if not anchor or current.count(anchor) != 1:
            cnt = current.count(anchor) if anchor else 0
            return {"ok": False, "output": "",
                    "error": f"anchor not unique in file (found {cnt}x): {anchor[:60]!r}",
                    "tool": f"Strong Coder ({provider} {model})", "model": f"{provider}::{model}",
                    "cost_usd": actual, "elapsed_s": round(time.time() - t0, 1), "chars": 0}
        idx = current.index(anchor) + len(anchor)
        # insert right after the anchor line (preserve a newline boundary)
        sep = "" if insert.startswith("\n") else "\n"
        new_code = current[:idx] + sep + insert + ("" if insert.endswith("\n") else "\n") + current[idx:]
        # SAFETY: the result must strictly CONTAIN the whole original (only additions, no removals).
        preserved = all(line in new_code for line in current.splitlines() if line.strip())
        if not preserved:
            return {"ok": False, "output": "",
                    "error": "splice would drop original lines — refused (no regression allowed)",
                    "tool": f"Strong Coder ({provider} {model})", "model": f"{provider}::{model}",
                    "cost_usd": actual, "elapsed_s": round(time.time() - t0, 1), "chars": 0}
        return {"ok": True, "output": new_code, "summary": summary, "edit_mode": "anchored_insert",
                "tool": f"Strong Coder ({provider} {model})", "model": f"{provider}::{model}",
                "cost_usd": actual, "elapsed_s": round(time.time() - t0, 1), "chars": len(new_code)}

    # NEW-file path: full content.
    summary = ""
    if "#SUMMARY:" in raw:
        head, _, tail = raw.rpartition("#SUMMARY:")
        summary = tail.strip().splitlines()[0].strip() if tail.strip() else ""
        raw = head.rstrip()
    code = _strip_code_fences(raw)
    ok = bool(code) and "CANNOT" not in code[:40].upper()
    return {"ok": ok, "output": code, "summary": summary,
            "tool": f"Strong Coder ({provider} {model})",
            "model": f"{provider}::{model}", "cost_usd": actual,
            "elapsed_s": round(time.time() - t0, 1), "chars": len(code),
            "error": (None if ok else "strong coder returned empty/refusal")}


def select_tool(title: str, desc: str = "") -> dict:
    """Pick the council-of-15 tool best suited to the task. Returns a tool spec dict."""
    t = f"{title} {desc}".lower()
    roster = _load_roster()

    def find(pred, fallback):
        for w in roster:
            if pred(w):
                return w
        return fallback

    # 2026-07-29 STRONG-CODER routing (BUILD PIECE 1 of 3): when the strong-coder path is enabled,
    # code / complex-build tasks route to kind=coder — which uses the STRONG cloud coder (OpenAI via
    # the authorized consult path) with the weak local iquest coder as fallback. This replaces the
    # weak Pi Gene Pool coder that produced mediocre code and looped on NOT_VERIFIED forever.
    _sc_cfg = _load_strong_coder_config()
    _strong_on = _sc_cfg.get("enabled", True)
    if any(w in t for w in _COMPLEX_WORDS):
        if _strong_on:
            return {"kind": "coder", "tool": f"Strong Coder ({_sc_cfg.get('provider')} {_sc_cfg.get('model')})",
                    "model": "iquest-coder-v1:40b-instruct", "task_class": "coding"}
        # 2026-07-22 Ross (a): complex build -> the Pi GENE POOL (governed non-Claude model), NOT the
        # Claude cage (which drained tokens). Claude stays a manual-only specialist.
        return {"kind": "gene_pool", "tool": "Gene Pool (Pi, non-Claude)", "model": "gene-pool", "task_class": "coding"}
    if any(w in t for w in _CODE_WORDS):
        if _strong_on:
            return {"kind": "coder", "tool": f"Strong Coder ({_sc_cfg.get('provider')} {_sc_cfg.get('model')})",
                    "model": "iquest-coder-v1:40b-instruct", "task_class": "coding"}
        # 2026-07-22 Ross: code -> cloud GENE POOL (keeps local ollama free for Wren the governor;
        # iQuest-40B local was saturating ollama and knocking her offline). Non-Claude, free-only.
        return {"kind": "gene_pool", "tool": "Gene Pool (Pi, non-Claude coder)", "model": "gene-pool",
                "task_class": "coding"}
    if any(w in t for w in _GOV_WORDS):
        # 2026-07-22 Ross: governance/review -> cloud GENE POOL (Hermes-70B local starved Wren).
        return {"kind": "gene_pool", "tool": "Gene Pool (Pi, non-Claude reasoning)", "model": "gene-pool",
                "task_class": "reasoning"}
    # default: a general local worker (research / short deliverable)
    w = find(lambda w: "research" in (w.get("role", "").lower()),
             {"display_name": "qwen worker", "model": "qwen2.5:14b", "worker_type": "research"})
    return {"kind": "general", "tool": w.get("display_name", "qwen worker"), "model": w.get("model", "qwen2.5:14b")}


def use_tool(tool: dict, spec: str, context: str = "", target_file: str = "",
             timeout_s: int = 620) -> dict:
    """The owner CEO USES the selected tool to produce a real deliverable."""
    kind = tool.get("kind")
    model = tool.get("model")
    if kind == "gene_pool":
        # 2026-07-22 Ross (a): council produces the deliverable via the Pi GENE POOL (governed
        # non-Claude model) instead of the caged Claude specialist. No Claude token drain.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from qsb_wren_consult_gene_pool import consult_gene_pool
        t0 = time.time()
        prompt = ("Produce ONLY the complete code deliverable (no prose, no markdown fences) — a runnable "
                  "artifact, not a description or stub.\n\nTASK: " + spec)
        r = consult_gene_pool(prompt, task_class=tool.get("task_class", "coding"),
                              redacted_context=(context or "")[:8000], timeout=150)
        if not r.get("available") or not r.get("ok"):
            return {"ok": False, "error": "gene pool unavailable: " + str(r.get("reason") or r.get("error"))[:140],
                    "tool": tool.get("tool"), "model": "gene-pool", "elapsed_s": round(time.time() - t0, 1)}
        code = (r.get("answer") or "").strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
            if code.rstrip().endswith("```"):
                code = code.rstrip()[:-3].rstrip()
        return {"ok": bool(code), "output": code, "tool": tool.get("tool"),
                "model": f"{r.get('hosting_provider')}::{r.get('model')}",
                "elapsed_s": round(time.time() - t0, 1), "chars": len(code)}
    if kind == "specialist":
        # caged Claude Max via CLI, paid key UNSET (Max subscription, free — never the dead paid API)
        prompt = ("Produce ONLY the code deliverable (no prose, no markdown fences). It must be a "
                  "complete, runnable artifact, not a description or stub.\n\nTASK: " + spec)
        if context:
            prompt += f"\n\n--- CURRENT FILE / CONTEXT (produce the full updated version) ---\n{context[:12000]}"
        env = dict(os.environ); env.pop("ANTHROPIC_API_KEY", None)
        t0 = time.time()
        try:
            r = subprocess.run(["claude", "--print", prompt], capture_output=True, text=True,
                               timeout=timeout_s, env=env)
            code = (r.stdout or "").strip()
            if code.startswith("```"):
                code = code.split("\n", 1)[-1]
                if code.rstrip().endswith("```"):
                    code = code.rstrip()[:-3].rstrip()
            # 2026-07-21 fix (council watcher): an Anthropic session/usage-limit or refusal string was
            # being SAVED as the deliverable and shipped to verifiers (dozens of "the deliverable is a
            # session-limit error message" rejects). Guard: if the CLI errored, or the output looks like
            # an error/limit/refusal notice (not code), mark ok=False so the runner recycles instead of
            # verifying garbage.
            _low = code[:400].lower()
            _err_sig = ("session limit", "usage limit", "rate limit", "quota", "overloaded",
                        "please try again", "try again later", "i cannot", "i can't", "cannot assist",
                        "unable to", "429", "too many requests", "context left", "reset at", "credit balance")
            looks_error = (r.returncode != 0) or (not code) or ("CANNOT" in code[:40].upper()) \
                or (len(code) < 40 and any(s in _low for s in _err_sig)) \
                or (any(s in _low for s in _err_sig) and len(code) < 600 and "\n" not in code.strip()[:200])
            return {"ok": not looks_error, "output": code,
                    "tool": tool.get("tool"), "model": "claude-account(Max)",
                    "error": ("producer returned error/limit notice, not code" if looks_error and code else None),
                    "elapsed_s": round(time.time() - t0, 1), "chars": len(code)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "tool": tool.get("tool"), "model": model,
                    "elapsed_s": round(time.time() - t0, 1)}
    if kind in ("coder", "strong_coder"):
        # 2026-07-29 STRONG-CODER path (BUILD PIECE 1 of 3): for a code BUILD, route through a
        # STRONG cloud coder (OpenAI) via the AUTHORIZED consult path first — it returns real,
        # complete, working code (not the weak local model's prose "proposed enhancement" that
        # verifiers reject forever). The local iquest-40B coder stays as an HONEST fallback when
        # OpenAI is unavailable (no key / 401 / over-cap). No fake output either way.
        cfg = _load_strong_coder_config()
        if cfg.get("enabled", True):
            sc = _strong_coder_build(spec, context=context, target_file=target_file, cfg=cfg)
            if sc.get("ok"):
                return sc
            # OpenAI unavailable → fall back to local coder, logging honestly.
            fb_reason = sc.get("error", "openai unavailable")
        else:
            fb_reason = "strong coder disabled by config"
        # local iquest 40B fallback — produces full runnable code (weaker, but honest)
        from qsb_coder_tool import write_code
        r = write_code(spec, context=context, target_file=target_file, timeout_s=timeout_s, model=model)
        r["tool"] = tool.get("tool")
        r["output"] = r.get("code", "")
        r["fallback_from_strong_coder"] = fb_reason
        return r
    # reasoning / general → PRODUCE on a live worker BOX first (2026-07-29 councilbottleneck fix).
    # The old path went straight to the main-box Ollama with the roster model (qwen2.5:14b). That box
    # runs OLLAMA_MAX_LOADED_MODELS=1 with Wren's qwen2.5:14b pinned Forever, so ANY generate here —
    # even a small llama3.2 — loses the VRAM/slot race and TIMES OUT (proven: 60-120s -> 0 chars ->
    # recycle). That WAS the "Research Worker produced 0 chars" loop. Fix: route research/general
    # production to the restored Acer(.41) / ThinkPad(.91) cockpits (their own local Ollama), resolved
    # live from presence.json, with the contended main box only as a LAST resort. This also makes the
    # worker boxes genuinely PRODUCE task artifacts (Ross: "get acer and thinkpad working on tasks").
    prompt = spec if not context else f"{spec}\n\n--- CONTEXT ---\n{context[:8000]}"
    box = _produce_on_worker_box(prompt, timeout_s=timeout_s)
    if box.get("ok") and (box.get("output") or "").strip():
        box["tool"] = tool.get("tool")
        return box
    # last resort: the contended main-box Ollama (kept honest — a timeout returns ok=False, not fake)
    body = {"model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 700, "num_ctx": 4096}}
    # keep_alive (2026-07-29 hermes-dark fix): a caller may ask the model to stay resident after
    # answering (tool["keep_alive"]="25m"), so a light 8B specialist like hermes3:8b that just won
    # the VRAM race stays warm through the map's 900s age-gate window instead of being evicted by
    # qwen and going dark next tick. Honest: only affects residency, never the truthfulness of the reply.
    _ka = tool.get("keep_alive")
    if _ka is not None:
        body["keep_alive"] = _ka
    t0 = time.time()
    try:
        req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            j = json.loads(r.read().decode())
        out = (j.get("response") or "").strip()
        return {"ok": bool(out), "output": out, "tool": tool.get("tool"), "model": model,
                "elapsed_s": round(time.time() - t0, 1), "chars": len(out)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "tool": tool.get("tool"), "model": model,
                "elapsed_s": round(time.time() - t0, 1)}


if __name__ == "__main__":
    # quick self-check of routing (no model calls)
    for ttl in ["add a 3D tour to the tour guide page", "audit the governance rules for risk",
                "research trader strategy options"]:
        print(f"  {ttl!r:55} -> {select_tool(ttl)}")
