"""multilingual_check — Wren translates / responds in another language using her OWN
local model (qwen2.5:14b via Ollama), with an HONEST confidence tier and a fallback note.

Design constraints (Ross A4, 2026-07-30):
  - Uses Wren's EXISTING local model only. Installs nothing. No external providers.
  - Fully offline: talks to localhost Ollama (127.0.0.1:11434). Zero network, zero cost.
  - Never claims a translation is authoritative when the model is out of its depth.

Confidence tiers are grounded in a real measured assessment run 2026-07-30
(see skills/wren/multilingual_check/ASSESSMENT_2026-07-30.md for quoted outputs):
  HIGH   — measured excellent or documented-strong for qwen2.5: fr/es/de/ru/zh/ja/en
           (+ it/pt/ko from qwen2.5's documented coverage, not separately probed).
  MEDIUM — documented-supported but showed drift / needs a second look
           (Arabic leaked a foreign token + swapped 'packet'->'bag' in the probe).
  LOW    — MEASURED FAILURE or unknown: hi/cy/sw/zu produced garbled or nonsense
           output. Anything unlisted defaults to LOW -> fallback recommended.

Given text + a target language, the skill calls the model, then applies
out-of-depth heuristics (meta-rambling, script leakage) and downgrades confidence
+ raises needs_review with a concrete fallback recommendation when they trip.

Read-only w.r.t. the repo: this skill reads and writes NO project files and does
NOT touch Wren's mind/persona. Its only side effect is one local model inference.
"""

import json
import re
import time
import urllib.request

MODEL = "qwen2.5:14b"
ENDPOINT = "http://127.0.0.1:11434/api/chat"

# --- language capability tiers (from the 2026-07-30 measured assessment) --------
_HIGH = {
    "english", "en", "french", "fr", "spanish", "es", "german", "de",
    "russian", "ru", "chinese", "mandarin", "zh", "japanese", "ja",
    # documented-strong for qwen2.5, not separately probed in the assessment:
    "italian", "it", "portuguese", "pt", "korean", "ko",
}
_MEDIUM = {
    "arabic", "ar", "hebrew", "he", "dutch", "nl", "polish", "pl",
    "turkish", "tr", "vietnamese", "vi", "thai", "th", "indonesian", "id",
}
_LOW = {  # MEASURED FAILURE in the assessment
    "hindi", "hi", "welsh", "cy", "swahili", "sw", "zulu", "zu",
}
# non-Latin-script targets — used by the script-leak heuristic
_NON_LATIN = {
    "chinese", "mandarin", "zh", "japanese", "ja", "korean", "ko",
    "russian", "ru", "arabic", "ar", "hebrew", "he", "hindi", "hi",
    "thai", "th",
}

_TIER_RANK = {"high": 3, "medium": 2, "low": 1}
_RANK_TIER = {3: "high", 2: "medium", 1: "low"}


def _norm(lang: str) -> str:
    return (lang or "").strip().lower()


def _base_tier(target: str) -> str:
    t = _norm(target)
    if t in _HIGH:
        return "high"
    if t in _MEDIUM:
        return "medium"
    if t in _LOW:
        return "low"
    return "low"  # unknown/untested -> conservative


def _call_model(prompt: str, timeout: float, retries: int) -> dict:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode()
    last = None
    for _ in range(max(1, retries)):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=body, headers={"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            return {
                "ok": True,
                "content": d["message"]["content"].strip(),
                "wall_s": round(time.time() - t0, 1),
                "eval_count": d.get("eval_count"),
                "eval_duration": d.get("eval_duration"),
            }
        except Exception as e:  # noqa: BLE001 — wedge/cold-load resilience
            last = e
            time.sleep(6)
    return {"ok": False, "error": str(last)}


def _out_of_depth(text_in: str, out: str, target: str) -> list:
    """Return a list of triggered out-of-depth signals (empty == clean)."""
    signals = []
    low = out.lower()
    # 1. meta-rambling: the model second-guesses itself / adds notes despite
    #    being told to reply with only the translation.
    if re.search(r"\bnote:|\(note|however,|correct translation|adjusted version|"
                 r"strictly (following|adhering)|but sticking", low):
        signals.append("meta_rambling")
    # 2. runaway length: a short line should translate to a short line.
    if len(out) > max(120, 3 * len(text_in)) and len(text_in) < 200:
        signals.append("runaway_length")
    # 3. script leak: a non-Latin target that comes back mostly ASCII letters
    #    (the assessment saw Latin fragments bleed into Hindi/Welsh output).
    if _norm(target) in _NON_LATIN:
        letters = [c for c in out if c.isalpha()]
        if letters:
            ascii_ratio = sum(c.isascii() for c in letters) / len(letters)
            if ascii_ratio > 0.35:
                signals.append("script_leak")
    return signals


def run(text: str = "", target_language: str = "", mode: str = "translate",
        timeout: float = 300.0, retries: int = 3) -> dict:
    """Translate or respond in target_language using Wren's local qwen2.5:14b.

    Args:
      text: the source text (to translate) or the request (mode="respond").
      target_language: language name or ISO code, e.g. "French" / "fr".
      mode: "translate" (default) or "respond" (answer the text in that language).
      timeout/retries: wedge-aware; the local model can cold-load or be mid-restart.

    Returns a dict with an HONEST confidence and, when warranted, a fallback note.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "text required"}
    if not target_language or not target_language.strip():
        return {"ok": False, "error": "target_language required"}

    target = target_language.strip()
    base = _base_tier(target)

    if mode == "respond":
        prompt = (f"Respond to the following in {target}, naturally and concisely. "
                  f"Reply ONLY in {target}.\n\n{text.strip()}")
    else:
        prompt = (f"Translate the following text into {target}. "
                  f"Reply with ONLY the translation, no notes or commentary.\n\n{text.strip()}")

    r = _call_model(prompt, timeout=timeout, retries=retries)
    if not r["ok"]:
        return {
            "ok": False,
            "target_language": target,
            "offline": True,
            "cost_usd": 0.0,
            "error": f"local model unreachable: {r['error']}",
            "fallback": ("qwen2.5:14b did not answer (may be mid wedge-heal / cold "
                         "load). Retry with a larger timeout, or escalate to a human."),
        }

    output = r["content"]
    signals = _out_of_depth(text, output, target)

    # confidence starts at the language tier, then is downgraded per signal.
    rank = _TIER_RANK[base]
    if signals:
        rank = max(1, rank - len(signals))
    confidence = _RANK_TIER[rank]

    needs_review = confidence == "low" or bool(signals)
    fallback = None
    if needs_review:
        reasons = []
        if base == "low":
            reasons.append(f"'{target}' is in the LOW tier "
                           "(measured failure or untested for qwen2.5:14b)")
        if signals:
            reasons.append("model showed out-of-depth signals: " + ", ".join(signals))
        fallback = (
            f"DO NOT ship this as authoritative — {'; '.join(reasons)}. "
            "Route to the gene pool for a second opinion "
            "(tools/qsb_wren_local_agent.py -> wren_consult_gene_pool), or escalate "
            "to a human translator. For LOW-tier languages consider recommending a "
            "dedicated local MT model (e.g. an NLLB-200 / M2M-100 build) to Ross — "
            "but install nothing without his go."
        )

    tok_s = None
    if r.get("eval_count") and r.get("eval_duration"):
        tok_s = round(r["eval_count"] / (r["eval_duration"] / 1e9), 1)

    return {
        "ok": True,
        "mode": mode,
        "target_language": target,
        "language_tier": base,
        "confidence": confidence,
        "output": output,
        "needs_review": needs_review,
        "fallback": fallback,
        "out_of_depth_signals": signals,
        "model": MODEL,
        "offline": True,
        "cost_usd": 0.0,
        "wall_s": r["wall_s"],
        "tok_s": tok_s,
        "note": ("Wren's own local model — offline, no external provider, no cost. "
                 "Confidence tiers from the 2026-07-30 measured assessment."),
    }


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    tgt = args[0] if args else "French"
    txt = " ".join(args[1:]) if len(args) > 1 else "The tower is quiet tonight."
    print(json.dumps(run(txt, tgt), ensure_ascii=False, indent=2))
