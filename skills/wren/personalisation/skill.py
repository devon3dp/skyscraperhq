"""personalisation — Wren's A3 personalisation engine (read-mostly, guardrailed).

WHAT IT IS
  Given a work CONTEXT, this returns which EXPLICIT, CITED Ross preferences apply
  and — crucially — WHY: the exact source Ross stated the preference, plus which
  tokens in the context matched. It lets Wren act in line with what Ross has
  actually asked for, without ever silently inventing or "learning" preferences.

HARD GUARDRAILS (doc A3)
  1. EXPLICIT + VERIFIED ONLY. Every applied preference comes from
     data/registries/qsb_wren_ross_preferences.json, where each entry cites a
     real Ross message/directive. There is NO code path that infers a new
     preference from behaviour. Sensitive assumptions are never learned.
  2. INSPECTABLE. action='inspect' returns every stored preference + its source.
  3. CORRECTABLE. action='correct' (Ross only, with a cited source) appends a
     correction; the original is preserved (history kept), never silently wiped.
  4. RECORDS WHY. Each applied preference carries why{ source, matched_tokens }.
  5. HONEST 'unset'. If nothing matches the context, the skill says so plainly —
     it does NOT guess.
  6. PRESERVES ROSS'S AUTHORITY. Corrections require corrected_by='ross' AND a
     source citation; anything else is refused. Ross overrides everything.

  This skill NEVER touches Wren's mind/persona and NEVER edits registries that
  other agents (Codex) write — it reads/writes only Wren's own preference store
  and its own correction audit log.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "data/registries/qsb_wren_ross_preferences.json"
CORR_LOG = ROOT / "data/registries/qsb_wren_ross_preferences_corrections.jsonl"

# Preferences here are the ONLY source of truth. No learning, no inference.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_store():
    try:
        return json.loads(STORE.read_text())
    except FileNotFoundError:
        return {"error": f"store missing: {STORE}"}
    except Exception as e:
        return {"error": f"store unreadable: {e}"}


def _active_prefs(store):
    """Preferences that are not retired (retired ones stay inspectable but do not apply)."""
    out = []
    for p in store.get("preferences", []):
        if p.get("retired"):
            continue
        out.append(p)
    return out


def _tokens(text):
    return set(_TOKEN_RE.findall((text or "").lower()))


def _apply(store, context):
    ctx_tokens = _tokens(context)
    matched = []
    for p in _active_prefs(store):
        keys = set(k.lower() for k in (p.get("applies_to") or []))
        hits = sorted(ctx_tokens & keys)
        if hits:
            matched.append({
                "id": p.get("id"),
                "preference": p.get("preference"),
                "confidence": p.get("confidence"),
                "correctable": p.get("correctable", True),
                "why": {
                    "source": p.get("source"),
                    "matched_tokens": hits,
                    "reason": (f"context mentions {hits} which this preference "
                               f"({p.get('id')}) governs; Ross stated it at: "
                               f"{p.get('source')}"),
                },
            })
    if matched:
        return {
            "ok": True,
            "action": "apply",
            "context": context,
            "applied": matched,
            "applied_count": len(matched),
            "honesty": "every applied preference cites a real Ross source (R01); nothing inferred.",
        }
    # Honest unset — no guessing.
    return {
        "ok": True,
        "action": "apply",
        "context": context,
        "applied": [],
        "applied_count": 0,
        "unset": True,
        "message": ("No explicit Ross preference covers this context. Personalisation "
                    "returns 'unset' rather than guessing — ask Ross or proceed on the "
                    "documented rules."),
        "honesty": "unknown => unset, never fabricated.",
    }


def _inspect(store):
    prefs = []
    for p in store.get("preferences", []):
        prefs.append({
            "id": p.get("id"),
            "preference": p.get("preference"),
            "source": p.get("source"),
            "date": p.get("date"),
            "confidence": p.get("confidence"),
            "correctable": p.get("correctable", True),
            "retired": bool(p.get("retired")),
            "corrections": p.get("corrections", []),
            "applies_to": p.get("applies_to", []),
        })
    return {
        "ok": True,
        "action": "inspect",
        "store_path": str(STORE.relative_to(ROOT)),
        "guardrails": store.get("guardrails", {}),
        "preference_count": len(prefs),
        "preferences": prefs,
        "note": "Full store shown. Every entry is a cited Ross directive; correct any of them with action='correct'.",
    }


def _correct(store, pref_id, new_preference, source, corrected_by, retire):
    # Ross authority + citation are mandatory (guardrail 6).
    if (corrected_by or "").strip().lower() != "ross":
        return {"ok": False, "action": "correct", "error":
                "REFUSED: only Ross may correct a preference (corrected_by must be 'ross'). "
                "This preserves Ross's authority over his own preferences."}
    if not (source or "").strip():
        return {"ok": False, "action": "correct", "error":
                "REFUSED: a correction needs a cited source (where Ross said it). "
                "Preferences are explicit-and-cited only; no uncited changes."}
    if not retire and not (new_preference or "").strip():
        return {"ok": False, "action": "correct", "error":
                "REFUSED: provide new_preference text, or set retire=true."}

    prefs = store.get("preferences", [])
    target = next((p for p in prefs if p.get("id") == pref_id), None)
    if target is None:
        return {"ok": False, "action": "correct", "error":
                f"no preference with id '{pref_id}'. Use action='inspect' to list ids."}
    if not target.get("correctable", True):
        return {"ok": False, "action": "correct", "error":
                f"preference '{pref_id}' is flagged not-correctable."}

    ts = _now()
    correction = {
        "ts": ts,
        "corrected_by": "ross",
        "source": source.strip(),
        "old_preference": target.get("preference"),
        "retire": bool(retire),
    }
    if retire:
        target["retired"] = True
        correction["new_preference"] = None
    else:
        correction["new_preference"] = new_preference.strip()
        target["preference"] = new_preference.strip()
    target.setdefault("corrections", []).append(correction)

    # Persist store (Wren's OWN file) + append an audit row. History preserved.
    STORE.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n")
    CORR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CORR_LOG.open("a") as f:
        f.write(json.dumps({"preference_id": pref_id, **correction}) + "\n")

    return {
        "ok": True,
        "action": "correct",
        "preference_id": pref_id,
        "retired": bool(retire),
        "correction": correction,
        "note": "Correction appended and audited; original text kept in corrections[] history.",
    }


def run(action: str = "apply", context: str = "", id: str = "",
        new_preference: str = "", source: str = "", corrected_by: str = "",
        retire: bool = False) -> dict:
    store = _load_store()
    if store.get("error"):
        return {"ok": False, "error": store["error"]}

    action = (action or "apply").strip().lower()
    if action == "inspect":
        return _inspect(store)
    if action == "correct":
        return _correct(store, id, new_preference, source, corrected_by, retire)
    if action == "apply":
        if not (context or "").strip():
            return {"ok": False, "error": "action='apply' needs a context string."}
        return _apply(store, context)
    return {"ok": False, "error": f"unknown action '{action}' (apply|inspect|correct)."}


if __name__ == "__main__":
    import sys
    ctx = " ".join(sys.argv[1:]) or "about to place a trader order on the broker"
    print(json.dumps(run("apply", ctx), indent=2, ensure_ascii=False))
