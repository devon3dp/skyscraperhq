#!/usr/bin/env python3
"""qsb_consult_external.py — bounded external provider consultation.

ONE tool, TWO providers (openai + deepseek), HARD CAPS.

Reads its authorization from:
  data/registries/qsb_provider_consultation_authorization.json

Reads keys from:
  floors/floor_28_security_department/vault/.env.openai
  floors/floor_28_security_department/vault/.env.deepseek

Stamps every call to:
  data/registries/qsb_tower_activity_tail.jsonl  (event_kind: provider_call)
  data/registries/qsb_provider_spend_ledger.jsonl  (cost log, append-only)

Hard refuses if:
  · authorization registry missing or "advisory_only" not stamped
  · today's spend (UTC day) would exceed daily_budget_usd
  · single call's estimated cost would exceed per_call_cap_usd
  · provider not in providers_authorized

Usage:
    python3 tools/qsb_consult_external.py \
        --provider openai \
        --model gpt-4o-mini \
        --prompt "review this strategy proposal: ..."

    python3 tools/qsb_consult_external.py --status
"""

from __future__ import annotations
import argparse, datetime, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
AUTH_PATH = REG / "qsb_provider_consultation_authorization.json"
SPEND_LEDGER = REG / "qsb_provider_spend_ledger.jsonl"
VAULT = ROOT / "floors/floor_28_security_department/vault"
ACTIVITY_TAIL = REG / "qsb_tower_activity_tail.jsonl"
AUGER_CONTEXT = REG / "qsb_auger_recent_context.md"   # 24h-rolling consult memory
AUGER_CONTEXT_MAX_CHARS = 200                          # per-row summary cap
AUGER_CONTEXT_PROMPT_LAST_N = 10                       # rows prepended to prompt

# Pricing — input / output cost per 1M tokens, USD.
# Pinned values for budget enforcement (refresh manually as needed).
PRICING = {
    "openai": {
        "gpt-4o-mini":    {"input": 0.15, "output": 0.60},
        "gpt-4o":         {"input": 2.50, "output": 10.00},
        "gpt-4.1":        {"input": 2.00, "output": 8.00},
        "gpt-4.1-mini":   {"input": 0.40, "output": 1.60},
        "gpt-3.5-turbo":  {"input": 0.50, "output": 1.50},
        "o1-mini":        {"input": 3.00, "output": 12.00},
    },
    "deepseek": {
        "deepseek-chat":      {"input": 0.27, "output": 1.10},
        "deepseek-reasoner":  {"input": 0.55, "output": 2.19},
    },
}

# Endpoints
PROVIDER_ENDPOINT = {
    "openai":   "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}


# ── helpers ────────────────────────────────────────────────────────────

def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def now_ts() -> str:
    return now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")


def today_utc_str() -> str:
    return now_utc().strftime("%Y-%m-%d")


def load_auth() -> dict:
    if not AUTH_PATH.exists():
        raise SystemExit(
            "REFUSE: authorization registry missing. "
            "Run only if CLAUDE.md provider-consultation section is present."
        )
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    if not auth.get("ok") or not auth.get("advisory_only"):
        raise SystemExit("REFUSE: authorization registry not stamped advisory_only")
    return auth


def load_keys() -> dict:
    """Load provider env vars from Floor 28 vault."""
    keys = {}
    for envfile in VAULT.glob(".env.*"):
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if line.startswith("export "): line = line[7:]
            if "=" not in line: continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and v:
                keys[k] = v
    return keys


def today_spend_usd() -> float:
    """Sum cost_usd of all calls in qsb_provider_spend_ledger.jsonl for today."""
    if not SPEND_LEDGER.exists():
        return 0.0
    today = today_utc_str()
    total = 0.0
    for line in SPEND_LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if (row.get("ts", "")[:10]) == today:
            total += float(row.get("cost_usd", 0) or 0)
    return round(total, 6)


def estimate_cost(provider: str, model: str, prompt_chars: int,
                    max_output_tokens: int) -> float:
    """Conservative pre-call cost estimate. Assumes 1 token ~= 4 chars input,
    full max_output_tokens output. Used for per-call gate; actual cost recorded
    after the call from the API's usage block."""
    price = PRICING.get(provider, {}).get(model)
    if not price:
        return 999.0   # unknown model → refuse to send
    in_tokens = max(1, prompt_chars // 4)
    out_tokens = max(1, max_output_tokens)
    return (in_tokens * price["input"] / 1_000_000) + (out_tokens * price["output"] / 1_000_000)


def actual_cost(provider: str, model: str, usage: dict) -> float:
    price = PRICING.get(provider, {}).get(model)
    if not price:
        return 0.0
    in_tokens = int(usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or 0)
    return round(
        (in_tokens * price["input"] / 1_000_000) +
        (out_tokens * price["output"] / 1_000_000),
        6,
    )


def append_activity(event_kind: str, summary: str, payload: dict) -> None:
    """Append to qsb_tower_activity_tail.jsonl directly (avoids the tower
    module's MAX_EVENTS rotation race if it's huge)."""
    ACTIVITY_TAIL.parent.mkdir(parents=True, exist_ok=True)
    ev = {
        "ts": now_ts(),
        "event_kind": event_kind,
        "summary": summary,
        "payload": payload,
    }
    with ACTIVITY_TAIL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


def append_spend(row: dict) -> None:
    SPEND_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with SPEND_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── 24h-rolling Auger context (short-term memory across consults) ────

def _auger_parse_ts(line: str) -> datetime.datetime | None:
    """Lines look like: '<iso-ts> · <reason> · <takeaway>'. Return ts or None."""
    head = line.split(" · ", 1)[0].strip()
    if not head:
        return None
    try:
        # tolerate trailing 'Z'
        return datetime.datetime.fromisoformat(head.replace("Z", "+00:00"))
    except Exception:
        return None


def auger_load_recent(last_n: int = AUGER_CONTEXT_PROMPT_LAST_N) -> list[str]:
    """Return up to last_n surviving (≤24h-old) rows, newest last."""
    if not AUGER_CONTEXT.exists():
        return []
    cutoff = now_utc() - datetime.timedelta(hours=24)
    kept: list[str] = []
    for line in AUGER_CONTEXT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ts = _auger_parse_ts(line)
        if ts is None or ts < cutoff:
            continue
        kept.append(line)
    return kept[-last_n:]


def auger_append_and_purge(reason: str, takeaway: str) -> None:
    """Append one row; purge anything older than 24h on the same pass."""
    # sanitize: single line, ≤200 chars total summary
    summary = (takeaway or "").replace("\n", " ").replace("\r", " ").strip()
    reason_clean = (reason or "advisory_consultation").replace("·", "-").strip()
    if len(summary) > AUGER_CONTEXT_MAX_CHARS:
        summary = summary[:AUGER_CONTEXT_MAX_CHARS - 1].rstrip() + "…"
    new_row = f"{now_ts()} · {reason_clean} · {summary}"

    cutoff = now_utc() - datetime.timedelta(hours=24)
    kept: list[str] = []
    if AUGER_CONTEXT.exists():
        for line in AUGER_CONTEXT.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            ts = _auger_parse_ts(stripped)
            if ts is None or ts < cutoff:
                continue
            kept.append(stripped)
    kept.append(new_row)

    AUGER_CONTEXT.parent.mkdir(parents=True, exist_ok=True)
    header = "# qsb_auger_recent_context — 24h-rolling consult memory (auto-managed)\n"
    AUGER_CONTEXT.write_text(header + "\n".join(kept) + "\n", encoding="utf-8")


def auger_prepend_block(prompt: str) -> str:
    """Prepend a '## Recent Auger context' block (last 10 ≤24h rows) to prompt."""
    rows = auger_load_recent()
    if not rows:
        return prompt
    block = ["## Recent Auger context",
             "(last consults, ≤24h, newest last — short-term memory)",
             ""]
    block.extend(f"- {r}" for r in rows)
    block.append("")
    block.append("## Current request")
    block.append("")
    return "\n".join(block) + prompt


# ── providers ─────────────────────────────────────────────────────────

def call_chat(provider: str, model: str, prompt: str,
               max_output_tokens: int, keys: dict) -> dict:
    """One synchronous chat completion. Returns dict with text, usage, raw."""
    url = PROVIDER_ENDPOINT[provider]
    if provider == "openai":
        key = keys.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("REFUSE: OPENAI_API_KEY not in vault")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        org = keys.get("OPENAI_ORG_ID")
        if org:
            headers["OpenAI-Organization"] = org
    elif provider == "deepseek":
        key = keys.get("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("REFUSE: DEEPSEEK_API_KEY not in vault")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    else:
        raise SystemExit(f"REFUSE: provider {provider!r} not authorized")

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(max_output_tokens),
        "stream": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    choices = out.get("choices") or []
    text = choices[0].get("message", {}).get("content", "") if choices else ""
    usage = out.get("usage") or {}
    return {"text": text, "usage": usage}


# ── main ──────────────────────────────────────────────────────────────

def cmd_status(auth: dict) -> None:
    spent = today_spend_usd()
    cap = auth["hard_caps_usd"]["daily_budget_usd"]
    print(f"  authorization:     {AUTH_PATH.name}  ({auth.get('scope')})")
    print(f"  providers:         {auth['providers_authorized']}")
    print(f"  daily cap:         ${cap:.2f}")
    print(f"  per-call cap:      ${auth['hard_caps_usd']['per_call_cap_usd']:.2f}")
    print(f"  spent today (UTC): ${spent:.4f}")
    print(f"  remaining today:   ${max(0, cap - spent):.4f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--provider", choices=["openai", "deepseek"])
    ap.add_argument("--model", help="e.g. gpt-4o-mini, deepseek-chat")
    ap.add_argument("--prompt", help="prompt to send")
    ap.add_argument("--max-tokens", type=int, default=400,
                    help="max output tokens (default 400)")
    ap.add_argument("--reason", default="advisory_consultation",
                    help="why this call (logged)")
    ap.add_argument("--status", action="store_true",
                    help="show spend + remaining budget and exit")
    args = ap.parse_args()

    auth = load_auth()
    if args.status:
        cmd_status(auth)
        sys.exit(0)
    if not (args.provider and args.model and args.prompt):
        ap.print_help()
        sys.exit(1)

    # Gate: provider authorized?
    if args.provider not in auth["providers_authorized"]:
        raise SystemExit(f"REFUSE: provider {args.provider!r} not in authorization")
    # Gate: model known?
    if args.model not in PRICING.get(args.provider, {}):
        raise SystemExit(
            f"REFUSE: model {args.model!r} not in pinned pricing table — "
            f"add it to PRICING in this file if you want to use it"
        )

    # Prepend the 24h-rolling Auger context (short-term memory across consults).
    # Built BEFORE cost-gating so caps reflect what's actually sent.
    effective_prompt = auger_prepend_block(args.prompt)
    # 2026-06-26 — also prepend team_memory inject for THIS provider so the
    # stateless API call sees its own continuity (per Ross "all team players
    # must remember"). Keep header tight (200 words) to stay within cost caps.
    try:
        import subprocess as _sp
        _r = _sp.run(["python3", "tools/qsb_team_memory.py", args.provider, "inject_provider_header"],
                      capture_output=True, text=True, timeout=8, cwd="/vaults/nvme0/qsb_tower_v1")
        if _r.returncode == 0 and _r.stdout.strip():
            # 2026-06-26 fix: 1500-char cap truncated the LATE SESSION block where
            # today's facts live. Raised to 5000; cost-gate below catches overruns.
            effective_prompt = _r.stdout.strip()[:5000] + "\n\n---\n\n" + effective_prompt
    except Exception:
        pass

    # Cost-gate the call BEFORE sending.
    est = estimate_cost(args.provider, args.model, len(effective_prompt), args.max_tokens)
    per_call_cap = float(auth["hard_caps_usd"]["per_call_cap_usd"])
    daily_cap = float(auth["hard_caps_usd"]["daily_budget_usd"])
    spent = today_spend_usd()

    if est > per_call_cap:
        raise SystemExit(
            f"REFUSE: estimated call cost ${est:.4f} > per-call cap ${per_call_cap:.4f}"
        )
    if spent + est > daily_cap:
        raise SystemExit(
            f"REFUSE: daily cap would be exceeded (today ${spent:.4f} + est ${est:.4f} > ${daily_cap:.4f})"
        )

    keys = load_keys()
    try:
        result = call_chat(args.provider, args.model, effective_prompt,
                            args.max_tokens, keys)
    except Exception as exc:
        # Log the failed attempt too
        append_activity("provider_call", f"FAILED {args.provider}/{args.model}",
                        {"provider": args.provider, "model": args.model,
                         "ok": False, "error": str(exc)[:200],
                         "reason": args.reason})
        raise SystemExit(f"call failed: {exc}")

    actual = actual_cost(args.provider, args.model, result["usage"])
    spent_after = spent + actual

    # Audit + spend ledger
    audit = {
        "ts": now_ts(),
        "provider": args.provider,
        "model": args.model,
        "reason": args.reason,
        "prompt_chars": len(args.prompt),
        "prompt_tokens": result["usage"].get("prompt_tokens"),
        "completion_tokens": result["usage"].get("completion_tokens"),
        "cost_usd": actual,
        "spent_today_after_usd": round(spent_after, 6),
        "daily_cap_usd": daily_cap,
    }
    append_spend(audit)
    append_activity("provider_call",
                     f"{args.provider}/{args.model} cost=${actual:.4f} reason={args.reason}",
                     audit)

    # 24h-rolling Auger context: one-paragraph takeaway from the response.
    # Best-effort; never block on failure.
    try:
        takeaway = (result.get("text") or "").strip().replace("\n", " ")
        auger_append_and_purge(args.reason, takeaway)
    except Exception as _e:
        pass

    # Print result
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  consult · {args.provider}/{args.model}  cost ${actual:.4f}")
    print(f"  spent today: ${spent_after:.4f}  /  cap ${daily_cap:.4f}  "
          f"(remaining ${max(0, daily_cap - spent_after):.4f})")
    print(f"  reason: {args.reason}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(result["text"])
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
