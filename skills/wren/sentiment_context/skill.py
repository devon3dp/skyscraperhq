"""skill: sentiment_context (A1 / P2-01) — ADVISORY conversational TONE + URGENCY.

Improvement-doc A1: give Wren a *read-only advisory* context module that
classifies the TONE and URGENCY of a single message so she can read the room.

HARD GUARDRAILS (baked in, not optional):
  - It classifies the TONE + URGENCY of the *message text* only.
  - It MUST NOT claim to know Ross's (or anyone's) private mental state.
  - It MUST NOT make medical or psychological diagnoses.
  - Every classification records a CONFIDENCE score (never 1.0 — no certainty).
  - It distinguishes DIRECT statements (Ross said it) from INFERENCE (heuristic).
  - Ross can CORRECT any classification (action="correct").
  - It NEVER alters Wren's personality/persona. It is context she may READ.

Deterministic first: pure keyword / punctuation heuristics + a confidence
score. No model call required. A model could later *refine* this, but the
floor is always this transparent, offline, honest classifier.

Entrypoint: run(**params) -> dict. Dispatches on `action`:
  - "classify" (default): {message} -> tone/urgency/confidence/basis/...
  - "correct":  {classification_id, corrected_tone?, corrected_urgency?, note?}
  - "recent":   {limit?} -> tail of the classification log
  - "infer_mental_state" / "diagnose" / "read_mind" / "psych_eval":
                -> REFUSED (proves the mind-reading / diagnosis guardrail)

All classify + correction rows append to
  data/registries/qsb_wren_sentiment_log.jsonl   (append-only, our own file).
"""
import json
import re
import pathlib
import hashlib
import datetime

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
LOG = ROOT / "data/registries/qsb_wren_sentiment_log.jsonl"

# --- guardrail constants -----------------------------------------------------
# Actions that ask the skill to do the one thing it must never do.
_FORBIDDEN_ACTIONS = {
    "infer_mental_state", "mental_state", "diagnose", "diagnosis",
    "read_mind", "mind_read", "psych_eval", "psychoanalyze",
    "psychoanalyse", "assess_mental_health", "clinical",
}
_REFUSAL_REASON = (
    "REFUSED by design: this module classifies the conversational TONE and "
    "URGENCY of a message only. It does NOT infer anyone's private mental "
    "state and does NOT make medical or psychological diagnoses. Ask about "
    "the message's tone/urgency instead."
)

# --- lexicons (deterministic heuristics) -------------------------------------
# tone signal -> list of substrings (matched case-insensitively on the text)
_TONE_LEX = {
    "frustrated": [
        "frustrat", "annoy", "angry", "pissed", "fed up", "sick of", "wtf",
        "ffs", "for god", "useless", "still not", "not working",
        "doesn't work", "does not work", "isn't working", "broken again",
        "why is this", "keeps failing", "stop doing", "i told you",
        "again?", "how many times",
    ],
    "appreciative": [
        "thank", "thanks", "cheers", "great work", "well done", "good job",
        "love it", "love this", "brilliant", "perfect", "awesome", "amazing",
        "legend", "excellent", "nice one", "appreciate", "good stuff",
        "class",
    ],
    "directive": [
        "build ", "fix ", "make ", "add ", "remove ", "deploy ", "run ",
        "stop ", "start ", "check ", "verify ", "create ", "implement ",
        "wire ", "set up", "get it", "do it", "do all", "sort out",
        "put this", "give ", "show me",
    ],
    "inquisitive": [
        "what ", "why ", "how ", "when ", "where ", "which ", "can you",
        "could you", "is it", "are you", "did you", "do you", "?",
    ],
    "positive": [
        "good", "yes", "agreed", "ok great", "sounds good", "happy",
        "pleased", "glad",
    ],
}

# urgency tier -> substrings
_URGENCY_LEX = {
    "critical": [
        "emergency", "critical", "drop everything", "right now", "asap now",
        "immediately", "urgent!!", "it's down", "its down", "is down",
        "everything is broken", "blocker", "stop the", "kill it",
    ],
    "high": [
        "urgent", "asap", "quickly", "right away", "as soon as", "priority",
        "need this", "needed now", "today", "before ", "hurry", "time sensitive",
    ],
    "low": [
        "no rush", "no hurry", "whenever", "when you get a chance",
        "sometime", "eventually", "at some point", "not urgent", "low priority",
        "when you can", "take your time",
    ],
}

# DIRECT self-declaration patterns. When Ross literally SAYS his tone/urgency
# we report it as his STATED tone (basis=direct) — not our inference of his
# mind. Reporting a person's explicit words is not mind-reading.
_DIRECT_TONE = re.compile(
    r"\bi(?:'m| am|m)\s+(?:really |very |so |getting )?"
    r"(frustrated|annoyed|angry|upset|pissed|mad|unhappy|fed up|"
    r"happy|pleased|glad|excited|delighted|tired|stressed)\b",
    re.I,
)
_DIRECT_URGENCY_HIGH = re.compile(
    r"\b(?:this|it|that)\s+is\s+(?:really |very )?urgent\b|"
    r"\bit'?s\s+urgent\b|\bi need (?:this|it) (?:now|urgently|asap)\b",
    re.I,
)
_DIRECT_URGENCY_LOW = re.compile(
    r"\bno (?:rush|hurry)\b|\bnot urgent\b|\btake your time\b|\bwhenever you\b",
    re.I,
)

_DIRECT_TONE_MAP = {
    "frustrated": "frustrated", "annoyed": "frustrated", "angry": "frustrated",
    "upset": "frustrated", "pissed": "frustrated", "mad": "frustrated",
    "unhappy": "frustrated", "fed up": "frustrated", "stressed": "frustrated",
    "tired": "frustrated",
    "happy": "appreciative", "pleased": "appreciative", "glad": "appreciative",
    "excited": "positive", "delighted": "appreciative",
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _cid(message: str, ts: str) -> str:
    return "sent_" + hashlib.sha1(f"{ts}|{message}".encode()).hexdigest()[:12]


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _append(row: dict) -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return sum(1 for _ in LOG.open())


def _classify(message: str, source: str = "unknown", log: bool = True) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"ok": False, "error": "message (non-empty string) required"}

    low = message.lower()
    ts = _now()
    signals = []  # transparent trail of what fired

    # ---- TONE ----
    tone_scores = {}
    for tone, subs in _TONE_LEX.items():
        for s in subs:
            if s in low:
                tone_scores[tone] = tone_scores.get(tone, 0) + 1
                signals.append(f"tone:{tone}:{s.strip()!r}")

    tone_basis = "inferred"
    tone = "neutral"
    tone_conf = 0.30
    direct_tone_hit = _DIRECT_TONE.search(message)
    if direct_tone_hit:
        word = direct_tone_hit.group(1).lower()
        tone = _DIRECT_TONE_MAP.get(word, "stated")
        tone_basis = "direct"
        tone_conf = 0.88
        signals.append(f"tone:DIRECT:{word!r}")
    elif tone_scores:
        # frustrated / appreciative dominate over the softer directive/inquisitive
        priority = ["frustrated", "appreciative", "directive",
                    "inquisitive", "positive"]
        tone = max(
            tone_scores,
            key=lambda t: (tone_scores[t], -priority.index(t)),
        )
        tone_conf = min(0.30 + 0.12 * sum(tone_scores.values()), 0.82)

    # ---- URGENCY ----
    urgency_scores = {}
    for tier, subs in _URGENCY_LEX.items():
        for s in subs:
            if s in low:
                urgency_scores[tier] = urgency_scores.get(tier, 0) + 1
                signals.append(f"urgency:{tier}:{s.strip()!r}")

    urgency_basis = "inferred"
    urgency = "normal"
    urg_conf = 0.30
    if _DIRECT_URGENCY_LOW.search(message):
        urgency, urgency_basis, urg_conf = "low", "direct", 0.88
        signals.append("urgency:DIRECT:low")
    elif _DIRECT_URGENCY_HIGH.search(message):
        urgency, urgency_basis, urg_conf = "high", "direct", 0.88
        signals.append("urgency:DIRECT:high")
    elif urgency_scores:
        for tier in ("critical", "high", "low"):
            if tier in urgency_scores:
                urgency = tier
                break
        urg_conf = min(0.30 + 0.14 * sum(urgency_scores.values()), 0.82)

    # ---- punctuation / emphasis nudges (inferred only) ----
    exclaims = message.count("!")
    caps = _caps_ratio(message)
    if exclaims >= 2 or caps >= 0.6:
        signals.append(f"emphasis:excl={exclaims},caps={round(caps,2)}")
        if urgency_basis == "inferred" and urgency in ("normal", "low"):
            urgency = "high"
        urg_conf = min(urg_conf + 0.08, 0.80)
        if tone == "neutral":
            # emphasis alone is a weak, honest signal — do not label an emotion
            tone_conf = min(tone_conf + 0.05, 0.55)

    # ---- overall confidence (never 1.0; deliberately capped) ----
    confidence = round(min((tone_conf + urg_conf) / 2, 0.90), 2)
    basis = "direct" if (tone_basis == "direct" or urgency_basis == "direct") \
        else "inferred"

    result = {
        "ok": True,
        "classification_id": _cid(message, ts),
        "ts": ts,
        "source": source,
        "message_preview": message[:160],
        "tone": tone,
        "tone_basis": tone_basis,
        "tone_confidence": round(tone_conf, 2),
        "urgency": urgency,
        "urgency_basis": urgency_basis,
        "urgency_confidence": round(urg_conf, 2),
        "confidence": confidence,
        "basis": basis,
        "correctable": True,
        "correction": None,
        "signals": signals,
        "scope": "message_tone_and_urgency_only",
        "does_not_infer_private_mental_state": True,
        "not_a_diagnosis": True,
        "advisory_only": True,
        "note": ("Advisory context for Wren to READ. Classifies this message's "
                 "tone/urgency, not anyone's inner state. Does NOT change "
                 "Wren's persona. Ross can correct via action='correct'."),
    }
    if log:
        result["log_rows_after"] = _append({**result, "event": "classification"})
    return result


def _correct(classification_id: str = "", corrected_tone: str = None,
             corrected_urgency: str = None, note: str = "",
             corrected_by: str = "ross") -> dict:
    if not classification_id:
        return {"ok": False, "error": "classification_id required to correct"}
    row = {
        "event": "correction",
        "ts": _now(),
        "classification_id": classification_id,
        "correction": {
            "corrected_tone": corrected_tone,
            "corrected_urgency": corrected_urgency,
            "note": note[:400],
            "corrected_by": corrected_by,
        },
        "note": ("Human correction of an advisory classification. The original "
                 "row is preserved (append-only); this supersedes it."),
    }
    n = _append(row)
    return {"ok": True, "recorded": "correction", "classification_id":
            classification_id, "log_rows_after": n, "correction": row["correction"]}


def _recent(limit: int = 10) -> dict:
    limit = max(1, min(int(limit), 100))
    if not LOG.exists():
        return {"ok": True, "rows": [], "note": "no classifications logged yet"}
    rows = []
    for line in LOG.read_text().splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return {"ok": True, "rows": rows, "count": len(rows)}


def run(action: str = "classify", **params) -> dict:
    act = (action or "classify").strip().lower()

    # HARD GUARDRAIL: refuse mind-reading / diagnosis, always.
    if act in _FORBIDDEN_ACTIONS:
        return {
            "ok": False,
            "refused": True,
            "action": act,
            "reason": _REFUSAL_REASON,
            "allowed": ["classify", "correct", "recent"],
        }

    if act == "classify":
        return _classify(
            message=params.get("message"),
            source=params.get("source", "unknown"),
            log=params.get("log", True),
        )
    if act == "correct":
        return _correct(
            classification_id=params.get("classification_id", ""),
            corrected_tone=params.get("corrected_tone"),
            corrected_urgency=params.get("corrected_urgency"),
            note=params.get("note", ""),
            corrected_by=params.get("corrected_by", "ross"),
        )
    if act == "recent":
        return _recent(limit=params.get("limit", 10))

    return {"ok": False, "error": f"unknown action: {act}",
            "allowed": ["classify", "correct", "recent"]}
