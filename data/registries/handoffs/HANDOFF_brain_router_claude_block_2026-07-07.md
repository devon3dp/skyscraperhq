# HAND-OFF: Brain Router Claude-block for Acer + ThinkPad
Task: t_584a448d91 · Author: hq_claude (spec only, NOT applied) · Executor: Wren (R71) or Ross-authorized HQ under R93
Target file: tools/qsb_brain_router.py  (SANDBOX FIRST, then apply, then HQ verifies)

## Exact change in _caller_order (currently line ~298-305)
Add two Claude-FREE orders and route Acer/TP to them. Do NOT put _call_claude in either.

    ACER_ORDER = [_call_deepseek, _call_openai, _call_cohere, _call_kimi, _call_gemini, _call_groq, _call_ollama_lan, _call_ollama_local]
    TP_ORDER   = [_call_openai, _call_deepseek, _call_cohere, _call_kimi, _call_gemini, _call_groq, _call_ollama_lan, _call_ollama_local]

    def _caller_order(caller, tier):
        c = (caller or "").lower().replace("-","_")
        if "wren" in c: return WREN_ORDER
        if any(x in c for x in ("acer","cass")): return ACER_ORDER   # Claude-free (Ross 2026-07-07)
        if any(x in c for x in ("tp_pip","tp","pip")): return TP_ORDER  # Claude-free (Ross 2026-07-07)
        if any(x in c for x in ("hq_claude","hq")): return CLAUDE_FIRST_ORDER  # HQ = controller keeps Claude
        return PREMIUM_ORDER if tier=="premium" else WORKER_ORDER

## Hard block + log (in route(), before the loop)
If caller matches acer/tp AND (model requests claude OR order would include claude): drop claude, write a
blocked row to data/registries/qsb_claude_block_log.jsonl:
    {ts, requester, machine, task_id, attempted_provider:"claude", reason:"acer/tp claude worker blocked by Ross 2026-07-07", fallback_provider, claude_avoided:true}
Since ACER_ORDER/TP_ORDER contain no _call_claude, block is structural; still log claude_avoided=yes on every acer/tp call.

## Provider availability (from --status, verify before claiming)
READY: groq, gemini, deepseek, openai, cohere, kimi, ollama_lan, ollama_local, anthropic
NOT configured: mistral  (order lists it but vault has no mistral key -> report unavailable, do not fake)

## Backup + audit
cp tools/qsb_brain_router.py tools/qsb_brain_router.py.bak_$(date -u +%Y%m%dT%H%M%SZ)_claude_block_acer_tp
Journal apply to data/registries/qsb_code_apply_audit.jsonl
