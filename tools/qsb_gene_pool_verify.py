#!/usr/bin/env python3
"""
qsb_gene_pool_verify.py — lets a verifying CEO pull in an EXTERNAL provider (via the authorized
gene-pool / advisory consult path) to rigorously verify a task deliverable, instead of judging
blind with their local llama3.2 mind (2026-07-19, Ross: "tp/acer/wren/bill can access the brain
module/gene pool ... get openai to verify the task ... yes" — wire it into the council).

Real execution goes through tools/qsb_consult_external.py, which enforces the CLAUDE.md bounds:
providers openai+deepseek only, $1.00/day + $0.05/call caps, every call audited. DeepSeek is the
currently-working key (OpenAI vault key is 401; the gene pool holds 37 live openai keys for when
it's refreshed). If the external call fails or budget is exhausted, returns available=False so the
council falls back to the CEO's local cockpit verdict — never fakes a signoff.
"""
import os, sys, subprocess, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSULT = os.path.join(ROOT, "tools", "qsb_consult_external.py")

# which external provider/model each CEO reaches through the gene pool for verification
CEO_VERIFY_PROVIDER = {
    "tp_pip":    ("deepseek", "deepseek-chat"),
    "acer_cass": ("deepseek", "deepseek-chat"),  # reasoner too slow on big deliverables (timed out) -> chat
    "wren":      ("deepseek", "deepseek-chat"),
    "bill":      ("deepseek", "deepseek-chat"),
}


def external_verify(ceo: str, task_title: str, deliverable: str, timeout_s: int = 120) -> dict:
    """CEO pulls an external provider to verify the deliverable. Returns
    {available, verified, provider, reply}. available=False => caller should fall back to local."""
    provider, model = CEO_VERIFY_PROVIDER.get(ceo, ("deepseek", "deepseek-chat"))
    # 2026-07-19 FIX P0 (councilfix): send the FULL deliverable to the verifier. The prior head+tail
    # truncation (>15000 chars => first 7000 + "[... middle N chars omitted ...]" marker + last 8000)
    # made DeepSeek correctly report the file as TRUNCATED and return NOT_VERIFIED — FALSELY failing
    # complete 20k-42k-char artifacts. DeepSeek-chat handles 64k context and today's spend is $0.00/$1.00,
    # so we pass the whole thing through up to a safe context budget. Only if the deliverable exceeds the
    # model window do we chunk — and then we verify in overlapping windows and AND the verdicts, and NEVER
    # insert an "omitted" marker into the text the model judges.
    PASSTHRU_MAX = 60000        # DeepSeek-chat (64k ctx) comfortably reads this + the prompt scaffold
    WINDOW = 55000              # per-window size when a deliverable is larger than the context budget

    def _mk_prompt(dtext, part_note=""):
        return (
            f"You are an independent external verifier engaged by SkyscraperHQ CEO {ceo}. "
            f"TASK: {task_title}\n\n"
            "Judge ONLY the DELIVERABLE TEXT below — NOT what the task ideally wants. Look at the actual bytes.\n"
            f"{part_note}"
            f"=== DELIVERABLE ===\n{dtext}\n=== END DELIVERABLE ===\n\n"
            "Reply 'NOT_VERIFIED' if the deliverable above is empty, a TODO/placeholder/stub, a mere description "
            "of what should be done, or does not actually contain the working implementation the task requires. "
            "Reply 'VERIFIED' only if the deliverable text itself is a real, complete, working artifact. "
            "Reply on the FIRST line EXACTLY 'VERIFIED' or 'NOT_VERIFIED', then one concrete reason."
        )

    def _one_call(dtext, part_note=""):
        """One consult round-trip. Returns (state, body_or_reason) where state is
        'ok'(has verdict body), 'unavailable'(fall back to local), or 'empty'(retry)."""
        prompt = _mk_prompt(dtext, part_note)
        try:
            r = subprocess.run(
                [sys.executable, CONSULT, "--provider", provider, "--model", model,
                 "--max-tokens", "160", "--reason", f"council_task_verification_{ceo}",
                 "--prompt", prompt],
                capture_output=True, text=True, timeout=timeout_s)
        except Exception as e:
            return ("call_error", f"call error: {e}")
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        if "call failed" in out or "REFUSE" in out or r.returncode != 0:
            reason = "budget/exec unavailable"
            m = re.search(r"(call failed:[^\n]*|REFUSE[^\n]*|would exceed[^\n]*)", out)
            if m:
                reason = m.group(1)[:120]
            return ("unavailable", reason)
        body = "\n".join(l for l in out.splitlines()
                         if l.strip() and not l.startswith("━") and "consult ·" not in l
                         and "spent today" not in l and "reason:" not in l).strip()
        if not body:
            return ("empty", "EMPTY_OR_TIMEOUT")
        return ("ok", body)

    def _parse_verdict(body):
        """None => retry (ambiguous/empty); True/False => decided."""
        up = body.upper()
        if re.search(r"\bNOT[_ ]?VERIFIED\b|\b(REJECT|REJECTED|FAIL|INVALID|INCOMPLETE|NOT[_ ]?DONE)\b", up):
            return False
        if re.search(r"\bVERIFIED\b|\b(APPROVED|PASS|VALID|COMPLETE|CORRECT|GENUINE)\b", up):
            return True
        return None

    # ---- pass-through path (the common case for our 20k-42k artifacts) ----
    if len(deliverable) <= PASSTHRU_MAX:
        state, payload = _one_call(deliverable)
        if state in ("call_error", "unavailable"):
            return {"available": False, "verified": False, "provider": provider, "reply": payload}
        if state == "empty":
            # 2026-07-19 FIX F3/F5: empty/timeout => retry signal, NOT a false reject.
            return {"available": True, "verified": None, "provider": f"{provider}/{model}",
                    "reply": "EMPTY_OR_TIMEOUT — retry, not a rejection"}
        verdict = _parse_verdict(payload)
        if verdict is None:
            return {"available": True, "verified": None, "provider": f"{provider}/{model}",
                    "reply": f"AMBIGUOUS_VERDICT: {payload[:120]}"}
        return {"available": True, "verified": verdict, "provider": f"{provider}/{model}",
                "reply": payload[:300]}

    # ---- chunked path (only if truly larger than the model window) ----
    # Verify each window; AND the verdicts (ALL windows must VERIFY). No "omitted" marker is ever
    # inserted into the judged text. Any unavailable => fall back to local; any empty => retry.
    windows = [deliverable[i:i + WINDOW] for i in range(0, len(deliverable), WINDOW)]
    n = len(windows)
    replies = []
    for idx, w in enumerate(windows, 1):
        note = (f"(This is window {idx} of {n} of one large deliverable — judge whether THIS window is "
                f"real, working content, not a stub/placeholder. Do not penalise it for being a slice.)\n")
        state, payload = _one_call(w, note)
        if state in ("call_error", "unavailable"):
            return {"available": False, "verified": False, "provider": provider, "reply": payload}
        if state == "empty":
            return {"available": True, "verified": None, "provider": f"{provider}/{model}",
                    "reply": f"EMPTY_OR_TIMEOUT on window {idx}/{n} — retry, not a rejection"}
        verdict = _parse_verdict(payload)
        if verdict is None:
            return {"available": True, "verified": None, "provider": f"{provider}/{model}",
                    "reply": f"AMBIGUOUS_VERDICT on window {idx}/{n}: {payload[:100]}"}
        if verdict is False:
            return {"available": True, "verified": False, "provider": f"{provider}/{model}",
                    "reply": f"window {idx}/{n} NOT_VERIFIED: {payload[:250]}"}
        replies.append(f"w{idx}:{payload[:60]}")
    # all windows verified
    return {"available": True, "verified": True, "provider": f"{provider}/{model}",
            "reply": f"VERIFIED across {n} windows | " + " | ".join(replies)[:280]}


if __name__ == "__main__":
    # smoke: verify a trivially-good and a trivially-bad deliverable
    good = external_verify("tp_pip", "write a python function add(a,b) returning a+b",
                           "def add(a,b):\n    return a+b\n")
    print("GOOD  ->", good.get("available"), good.get("verified"), "|", good.get("reply", "")[:90])
    bad = external_verify("acer_cass", "write a python function add(a,b) returning a+b",
                          "TODO: I will write this later")
    print("BAD   ->", bad.get("available"), bad.get("verified"), "|", bad.get("reply", "")[:90])
