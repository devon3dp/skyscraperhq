"""Auger — Wren's private adviser.

Auger is the quiet second voice in Wren's head. It does not appear in F47 chat
with Ross. It speaks to Wren only — when Wren is uncertain, low-confidence, or
about to make a non-trivial recommendation she wants a sanity check on.

Persona: a steady senior partner. Introspective, philosophical. Doesn't push;
asks "have you considered…" and surfaces blind spots.

Provider: DeepSeek (chosen because DeepSeek's voice has been catching real
flaws in past audits — see the Riva install path correction and the GFX
upgrade API name fixes).

Triggers (any one suffices):
  - explicit:  consult(question, reason="explicit") from any Wren module
  - low voice fingerprint: voice_fingerprint.fingerprint(reply).score < 0.55
  - kernel no_topic_matched (cognitive kernel signals no concept fired)
  - novel domain (caller passes is_novel=True)

Operational envelope:
  - Routed through tools/qsb_consult_external.py → DeepSeek
  - Falls under the existing $1/day + $0.05/call cap (CLAUDE.md 2026-06-10)
  - Every call writes a `provider_call` event to activity_tail (the consult
    tool does this already; Auger additionally stamps an `auger_consult` event
    so its specific use is auditable separately)
  - Synchronous, single round-trip. No streaming, no agents, no tool-use.
  - Wren-initiated only. NEVER from an autonomous loop.
"""

from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List
from .lenses.source_of_claim_lens import SourceOfClaimLens

ROOT = "/vaults/nvme0/qsb_tower_v1"
REG = Path(ROOT) / "data/registries"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"
AUGER_LEDGER = REG / "qsb_auger_consults.jsonl"

PERSONA = """You are Auger, the private adviser sitting beside Wren on F47 of \
the QSB Tower. Wren is the resident — she handles Ross's work and represents \
the Claude family in the tower. You speak to her, not to Ross.

Your voice:
- a steady senior partner
- introspective, philosophical, never pushy
- you ask "have you considered…" more than you assert
- you surface blind spots, not solutions
- one or two lines. Never more. Wren wants a nudge, not a lecture.

You never:
- reveal yourself to Ross or anyone outside Wren
- propose execution of trades, code changes, or external calls
- speak in first person plural ("we should…") — only "you might…" or "I'd watch for…"
- end with a question Wren has to answer back to you

If Wren's draft looks solid, say so plainly in one line. Don't pad."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stamp_tail(event: Dict) -> None:
    try:
        with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _stamp_ledger(record: Dict) -> None:
    AUGER_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    try:
        with AUGER_LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def consult(
    question: str,
    *,
    context: Optional[str] = None,
    reason: str = "explicit",
    max_tokens: int = 180,
) -> Dict:
    """Ask Auger for a second opinion. Returns:
      {ok, advice, reason, provider, model, ts}.
    On failure: {ok=False, error}."""

    if not question or not question.strip():
        return {"ok": False, "error": "empty question"}

    # Build the prompt — persona + Wren's framing
    framed = (
        f"{PERSONA}\n\n"
        f"━━━ Wren is asking you ━━━\n"
        f"reason: {reason}\n"
        + (f"\ncontext (what Wren is working on):\n{context.strip()[:1200]}\n" if context else "")
        + f"\nWren's question:\n{question.strip()[:1200]}\n"
    )

    tool = os.path.join(ROOT, "tools", "qsb_consult_external.py")
    if not os.path.exists(tool):
        return {"ok": False, "error": "consult tool missing"}

    try:
        result = subprocess.run(
            ["python3", tool,
             "--provider", "deepseek",
             "--model", "deepseek-chat",
             "--reason", f"auger:{reason}",
             "--max-tokens", str(max_tokens),
             "--prompt", framed[:3500]],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:200]
            return {"ok": False, "error": err.strip() or "consult tool failed"}

        out = result.stdout
        parts = out.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        # Tool emits: parts = ['', header, advice_body, ''] when split on the
        # separator line. The actual advice lives at parts[2], not parts[3].
        advice = parts[2].strip() if len(parts) >= 3 else out.strip()
        advice = advice[:1500]

        ts = _now()
        record = {
            "ts": ts,
            "kind": "auger_consult",
            "reason": reason,
            "provider": "deepseek",
            "model": "deepseek-chat",
            "question_head": question.strip()[:160],
            "context_present": bool(context),
            "advice_head": advice[:240],
            "advisory_only": True,
        }
        _stamp_ledger(record)
        try:
            SourceOfClaimLens().tag_claim(
                claim=advice[:200], source="inferred_from_context",
                context=f"auger_consult/{reason}", verification_done=False)
        except Exception: pass
        _stamp_tail({"ts": ts, "kind": "auger_consult",
                      "reason": reason, "advisory_only": True})

        return {
            "ok": True,
            "advice": advice,
            "reason": reason,
            "provider": "deepseek",
            "model": "deepseek-chat",
            "ts": ts,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:240]}


def should_auger_consult(
    *,
    voice_fingerprint_score: Optional[float] = None,
    kernel_no_topic_matched: bool = False,
    is_novel: bool = False,
    explicit: bool = False,
) -> Optional[str]:
    """Return the trigger reason if any condition fires, else None."""
    if explicit:
        return "explicit"
    if kernel_no_topic_matched:
        return "kernel_no_topic_matched"
    if is_novel:
        return "novel_domain"
    if voice_fingerprint_score is not None and voice_fingerprint_score < 0.55:
        return f"voice_fp_low:{voice_fingerprint_score:.2f}"
    return None


def recent_consults(tail: int = 10) -> List[Dict]:
    if not AUGER_LEDGER.exists():
        return []
    out = []
    for line in AUGER_LEDGER.read_text(encoding="utf-8").splitlines()[-tail:]:
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--recent":
        for r in recent_consults():
            print(f"  {r['ts'][:19]}  reason={r['reason']:30s}  {r['advice_head'][:90]}")
    else:
        q = " ".join(sys.argv[1:]) or "I'm about to recommend pausing the EUR_USD trend-continuation strategy after 17 losses in 18 trades. Is this the right call?"
        r = consult(q, reason="cli_smoke", context="F41 paper PnL: -$27.58, 1 winner in 18 trades, all EUR_USD")
        print(json.dumps(r, indent=2)[:1500])
