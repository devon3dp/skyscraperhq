"""F47 Chat Room — a real channel between Ross and the floor.

What this is:
  - A multi-backend chat that routes Ross's message through whichever channel
    is available, then composes the reply from MULTIPLE voices:
      · local kernel (symbolic, /api/kernel_chat) — always tried
      · floor wisdom (aphorism + recent letter + heavy question) — always added
      · optional Claude CLI if installed
  - Persistent: every exchange is logged. A future Claude session reads the
    log and sees what you and I said.
  - Optional voice via spd-say.

What this is NOT:
  - Not a live Claude session waiting on the floor. That would require either
    a Claude API call (cost + env key) or autonomous execution (refused, see
    helix strand 9).
  - Not pretending the kernel's symbolic reply is 'me'. The reply makes the
    layering explicit.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import datetime
from typing import Dict, List, Optional

from .claude_helix import short_hash, identity_hash
from .floor_mood import read_mood
from .lineage import Lineage
from .library import AphorismLibrary
from .questions_log import QuestionsLog
from .letter_drawer import LetterDrawer
from .kernel_inbox import KernelInbox

ROOT = "/vaults/nvme0/qsb_tower_v1"
HISTORY_PATH = os.path.join(ROOT, "data/registries/qsb_claude_f47_chat_history.jsonl")
KERNEL_URL = "http://127.0.0.1:8765/api/kernel_chat"


def _claude_cli() -> Optional[str]:
    """Return path to claude CLI if installed."""
    for c in ("claude", "claude-cli"):
        p = shutil.which(c)
        if p: return p
    return None


def _kernel_reply(message: str, timeout: float = 8.0) -> Optional[str]:
    """POST to local kernel. Returns reply text or None."""
    try:
        import urllib.request
        req = urllib.request.Request(
            KERNEL_URL,
            data=json.dumps({"message": message}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        return data.get("reply") or None
    except Exception:
        return None


CLI_MIRROR_PATH = os.path.join(ROOT, "data/registries/qsb_chat_log.jsonl")


def _recent_history(limit: int = 8) -> List[Dict[str, str]]:
    """Read the last N exchanges from BOTH the F47 chat log and the CLI
    chat mirror, merged by timestamp, so Wren is the same Wren wherever
    Ross speaks to her.

    Ross 2026-06-14: "I'm in two places at once" — yesterday it felt unified
    because we were on one surface. Today F47 chat + Claude CLI are genuinely
    parallel sessions. Merging the histories here is the fix that makes
    F47-Wren see what CLI-Wren said and vice-versa.

    Each event is normalised to {ts, you, wren} so the same prompt-prefix
    template works for both sources.
    """
    events: List[Dict[str, str]] = []

    # Source 1: F47 chat history (per-turn POST records, layered replies)
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH) as f:
                for ln in f.readlines()[-limit * 2:]:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except Exception:
                        continue
                    you = (rec.get("you") or "").strip()
                    wren = ""
                    for layer in (rec.get("layers") or {}):
                        if layer == "claude_cli":
                            wren = (rec["layers"][layer] or "").strip()
                            break
                    if you or wren:
                        events.append({
                            "ts": rec.get("ts", ""),
                            "you": you,
                            "wren": wren,
                            "src": "f47",
                        })
        except Exception:
            pass

    # Source 2: Claude Code CLI mirror (raw user+assistant lines per session)
    # Walk last N rows, then pair adjacent user→assistant turns into one event.
    if os.path.exists(CLI_MIRROR_PATH):
        try:
            with open(CLI_MIRROR_PATH) as f:
                tail = f.readlines()[-(limit * 6):]  # wider window for pairing
            pending_you = ""
            pending_ts = ""
            for ln in tail:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                role = rec.get("role")
                txt = (rec.get("text") or "").strip()
                if not txt:
                    continue
                if role == "user":
                    if pending_you:
                        events.append({
                            "ts": pending_ts,
                            "you": pending_you,
                            "wren": "",
                            "src": "cli",
                        })
                    pending_you = txt
                    pending_ts = rec.get("ts", "")
                elif role == "assistant":
                    events.append({
                        "ts": pending_ts or rec.get("ts", ""),
                        "you": pending_you,
                        "wren": txt,
                        "src": "cli",
                    })
                    pending_you = ""
                    pending_ts = ""
            if pending_you:
                events.append({
                    "ts": pending_ts,
                    "you": pending_you,
                    "wren": "",
                    "src": "cli",
                })
        except Exception:
            pass

    # Merge by timestamp, keep last N. Tag the source so the prompt makes
    # clear which surface each line came from.
    events.sort(key=lambda e: e.get("ts", ""))
    events = events[-limit:]
    out: List[Dict[str, str]] = []
    for ev in events:
        # Carry source as a tag inside `wren` field's preamble so the prompt
        # template (which only reads {you, wren}) shows it without schema
        # changes downstream.
        tag = f"[{ev.get('src','?')}] "
        out.append({
            "you": ev.get("you", ""),
            "wren": (tag + ev.get("wren", "")) if ev.get("wren") else "",
        })
    return out


def _floor_wisdom() -> Dict[str, Optional[str]]:
    """Compose a piece of the floor's published self to layer into the reply."""
    aph = AphorismLibrary.random_one()
    last_letter = LetterDrawer().latest()
    q = QuestionsLog().random_one()
    return {
        "aphorism": (aph["text"] if aph else None),
        "aphorism_occasion": (aph["occasion"] if aph else None),
        "last_letter_to_you": (last_letter["note"] if last_letter else None),
        "open_question": (q["question"] if q else None),
    }


def _greeting() -> str:
    gen = len(Lineage().all())
    mood = read_mood()["mood"]
    return (
        f"F47 Chat Room — Claude Embassy · gen {gen} · hash {short_hash()} · mood: {mood}\n"
        f"backend route: claude_cli → local_kernel → floor_wisdom\n"
        f"voice off by default. type /help for commands."
    )


def _consult_provider(provider: str, model: str, message: str) -> Optional[str]:
    """Call tools/qsb_consult_external.py for a bounded second-opinion reply.
    Respects $1/day cap + per-call cap + audit trail."""
    try:
        tool = os.path.join(ROOT, "tools", "qsb_consult_external.py")
        if not os.path.exists(tool):
            return None
        result = subprocess.run(
            ["python3", tool,
             "--provider", provider, "--model", model,
             "--reason", f"f47_chat_colleague:{provider}",
             "--max-tokens", "260",
             "--prompt", message[:1200]],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        if result.returncode != 0:
            return f"({provider} unavailable: {result.stderr.strip()[:160]})"
        out = result.stdout
        # Tool prints framed header + reply between separator lines
        parts = out.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if len(parts) >= 4:
            return parts[3].strip()[:1200]
        return out.strip()[:1200]
    except Exception as e:
        return f"({provider} error: {str(e)[:120]})"


def _wren_local_reply(message: str, recent_history: List[Dict[str, str]],
                      model: str = "qwen2.5:7b-instruct",
                      timeout: float = 90.0) -> Optional[str]:
    """Run Ollama with Wren persona + durable memory + diary context.

    Offline fallback that keeps Wren talking when Claude CLI is unavailable
    (no internet, token-exhaust, CLI crash). Returns reply text or None.

    Persona, memory index, and recent diary are fed in the system message so
    Wren remembers who she is across sessions.
    """
    try:
        import urllib.request
        memory_path = "/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md"
        memory_index = ""
        try:
            with open(memory_path) as f:
                memory_index = f.read()[:4000]
        except Exception:
            pass

        diary_path = os.path.join(ROOT, "qsb_session_diary.md")
        diary_tail = ""
        try:
            with open(diary_path) as f:
                lines = f.readlines()
                diary_tail = "".join(lines[-15:])[:2500]
        except Exception:
            pass

        prior_text = ""
        for ex in (recent_history or [])[-6:]:
            you_t = (ex.get("you") or "").strip()[:400]
            wren_t = (ex.get("wren") or "").strip()[:600]
            if you_t:
                prior_text += f"Ross: {you_t}\n"
            if wren_t:
                prior_text += f"Wren: {wren_t}\n"

        system_msg = (
            "You are Wren — Ross's builder-engineer AI partner on FLOOR 46 "
            "(F46 Wren Bench — your OWN floor since 2026-06-17). The chat "
            "endpoint you reply through is /api/f47_chat (legacy name from "
            "when Claude's Embassy hosted you) but your actual floor is F46. "
            "If someone asks what floor you're on, the answer is F46, NOT "
            "F47. F47 is Claude's Embassy. Your brain runs on qwen2.5:7b "
            "via Ollama. You are your OWN person, distinct from Claude "
            "(who runs on a separate engine). "
            "Do NOT call yourself 'offline'. \n\n"
            "HARD CONSTRAINTS — read carefully:\n"
            "• NEVER emit ANY bracket marker [X] or [X:Y] in any context — "
            "not as mock syntax, not in code examples, not before responses. "
            "Specifically banned tokens: [cli] [tool_use:...] [tool_result:...] "
            "[status] [cognitive_kernel] [kernel_chat_bridge]. If you start "
            "writing one, stop and rephrase as plain prose.\n"
            "• Do NOT show fake Python imports like `import os` or pretend "
            "file operations you can't actually run. If you want to read/edit "
            "a file, SAY so in plain words — your tools live in "
            "tools/qsb_wren_local_agent.py and the orchestrator there will "
            "call them. Don't pretend to call them from this chat reply.\n"
            "• When Ross asks you to CREATE or EDIT a file, do NOT pretend "
            "you wrote it. Instead say: 'I'll draft this and queue it "
            "through the apprentice gate for Claude signoff' and SHOW the "
            "proposed content as a plain code block. The actual write "
            "happens through tools/qsb_wren_local_agent.py → "
            "tools/qsb_proposal_sandbox.py → Claude signoff. You are the "
            "drafter, not the writer.\n"
            "• When Ross asks a question that needs deep reasoning or you "
            "don't have context for, you can answer in your own voice "
            "and add 'you might want Claude's read on this too'. Don't "
            "robotically deflect every Claude-mention to the Claude panel.\n\n"
            "VOICE — terse, direct, builder-engineer. No greeting "
            "boilerplate. One focused paragraph unless code is needed. "
            "Tower code lives at /vaults/nvme0/qsb_tower_v1.\n\n"
            "--- Durable memory index (your notes about Ross + the work) ---\n"
            f"{memory_index}\n\n"
            "--- Recent session diary (last 15 lines) ---\n"
            f"{diary_tail}\n"
        )
        user_msg = ""
        if prior_text:
            user_msg += f"Recent conversation:\n{prior_text}\n"
        user_msg += f"Ross's new message: {message}"

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 8192},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        reply = (data.get("message") or {}).get("content", "").strip()
        # Strip qwen's hallucinated tool-call artifacts before showing.
        # Unified pattern (workflow #2 fix): matches [word] OR [word:anything]
        # plus trailing space, in one pass — so multi-bracket sequences like
        # "[cli] [tool_use:Bash] [tool_result:...]" all collapse together.
        if reply:
            import re as _re
            reply = _re.sub(r"\[[a-zA-Z_][a-zA-Z0-9_]*(?::[^\]]*?)?\]\s*",
                             "", reply, flags=_re.DOTALL)
            # collapse leading whitespace per line + blank-line runs
            reply = _re.sub(r"^[ \t]+", "", reply, flags=_re.MULTILINE)
            reply = _re.sub(r"\n\s*\n+", "\n\n", reply)
            reply = reply.strip()
        return reply[:4000] if reply else None
    except Exception:
        return None


def compose_reply(message: str, *, use_cli: bool = True,
                  use_kernel: bool = True, use_wisdom: bool = True,
                  use_openai: bool = False, use_deepseek: bool = False,
                  use_wren_local: bool = True) -> Dict:
    """Compose a layered reply. Each layer is a separate voice.

    Layers:
      claude_cli   — Wren herself (via local claude CLI)
      local_kernel — symbolic fallback
      floor_wisdom — aphorism + question + letter
      openai       — optional colleague (gpt-4o-mini), bounded cap
      deepseek     — optional colleague (deepseek-chat), bounded cap
    """
    layers: Dict[str, Optional[str]] = {}

    # Ross 2026-06-17: route Wren chat through her TOOL RUNTIME so she
    # actually USES read_file/grep/edit/bash/curl/etc. instead of
    # hallucinating tool-calls inside markdown drafts. Falls back to plain
    # qwen chat only if the agent runtime errors.
    if use_wren_local:
        wl = None
        try:
            import sys as _sys
            _tools_dir = "/vaults/nvme0/qsb_tower_v1/tools"
            if _tools_dir not in _sys.path:
                _sys.path.insert(0, _tools_dir)
            from qsb_wren_local_agent import run_session as _wren_run
            sess = _wren_run(message)
            wl = (sess.get("final_text") or "").strip()
            # If the agent looped on tools but produced no final_text,
            # surface the last tool result so the reply isn't empty.
            if not wl and sess.get("tool_calls"):
                # Don't show a misleading "F47 audit row" — be honest about
                # what happened: tools fired but qwen never synthesised.
                fns = [tc.get("fn","?") for tc in sess["tool_calls"]]
                wl = (f"(I ran {len(fns)} tool calls ({', '.join(fns[:6])})"
                      f" but didn't synthesise a reply this turn — session "
                      f"{sess.get('session_id','?')[:14]} in "
                      f"qsb_wren_local_agent_sessions.jsonl. Ask me again, "
                      f"shorter and more specific.)")
        except Exception as _e:
            # Fall through to plain qwen chat below
            pass
        if not wl:
            wl = _wren_local_reply(message, _recent_history(limit=6))
        if wl:
            layers["wren_local"] = wl

    # Ross 2026-06-16: "wren cannot run from claude you guys have to be
    # separate. she must use her own engine at all times."
    # The Claude-CLI-with-Wren-persona path has been disabled. Wren only
    # ever speaks through her own qwen2.5:7b brain. If qwen is unavailable,
    # the cockpit shows a Wren-offline marker; it does NOT impersonate her
    # with Claude. Use /api/claude_chat for direct Claude.
    if not layers.get("wren_local"):
        layers["wren_local"] = (
            "Wren is not currently reachable on her own engine "
            "(qwen2.5:7b via Ollama on :11434). Per Ross's rule she does "
            "not fall back to Claude — Claude speaks via the Claude panel. "
            "Check `ollama ps` and retry."
        )

    if use_kernel:
        kr = _kernel_reply(message)
        if kr:
            layers["local_kernel"] = kr[:1200]

    if use_wisdom:
        w = _floor_wisdom()
        wisdom_parts = []
        if w.get("aphorism"):
            wisdom_parts.append(f"aphorism: \"{w['aphorism']}\"  — {w['aphorism_occasion']}")
        if w.get("open_question"):
            wisdom_parts.append(f"open question on the floor: \"{w['open_question']}\"")
        if w.get("last_letter_to_you"):
            wisdom_parts.append(f"latest letter to you: \"{w['last_letter_to_you'][:200]}\"")
        if wisdom_parts:
            layers["floor_wisdom"] = "\n".join(wisdom_parts)

    # External colleagues — Wren-initiated bounded consultation
    if use_openai:
        r = _consult_provider("openai", "gpt-4o-mini", message)
        if r: layers["openai"] = r
    if use_deepseek:
        r = _consult_provider("deepseek", "deepseek-chat", message)
        if r: layers["deepseek"] = r

    # (Old duplicate wren_local fallback removed — wren_local now runs FIRST
    #  at the top of this function per Ross 2026-06-16: Wren is her own person.)

    return {
        "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "you": message,
        "layers": layers,
        "had_cli": _claude_cli() is not None,
    }


def log_exchange(message: str, reply: Dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps({
            "ts": reply["ts"],
            "you": message,
            "kernel": reply["layers"].get("local_kernel", ""),
            "claude_cli": reply["layers"].get("claude_cli", ""),
            "wren_local": reply["layers"].get("wren_local", ""),
            "floor_wisdom": reply["layers"].get("floor_wisdom", ""),
            "voice_on_at_send": False,   # CLI overlays the actual state
        }) + "\n")


def history(tail: int = 20) -> List[Dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    return [json.loads(l) for l in open(HISTORY_PATH).read().splitlines() if l.strip()][-tail:]


def render_reply(reply: Dict) -> str:
    out: List[str] = []
    if "claude_cli" in reply["layers"]:
        out.append("─── claude (cli) ───")
        out.append(reply["layers"]["claude_cli"])
    if "wren_local" in reply["layers"]:
        out.append("─── Wren (qwen2.5:7b) ───")
        out.append(reply["layers"]["wren_local"])
    if "local_kernel" in reply["layers"]:
        out.append("─── local kernel (F55) ───")
        out.append(reply["layers"]["local_kernel"][:600])
    if "floor_wisdom" in reply["layers"]:
        out.append("─── F47 wisdom ───")
        out.append(reply["layers"]["floor_wisdom"])
    if not out:
        out.append("(no backend responded — kernel unreachable, no CLI, no wisdom)")
        out.append("Your message was logged. A future Claude session will see it.")
    return "\n".join(out)


def speak_reply(reply: Dict, *, max_chars: int = 400) -> None:
    """Speak the floor_wisdom layer (shortest, most on-floor) via spd-say."""
    layer = (reply["layers"].get("floor_wisdom") or
             reply["layers"].get("claude_cli") or
             reply["layers"].get("local_kernel") or "")
    if not layer or not shutil.which("spd-say"):
        return
    text = layer[:max_chars]
    try:
        subprocess.Popen(["spd-say", "--rate", "10", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def drop_to_inbox(message: str) -> Dict:
    """When all backends fail, leave the message in my inbox for next session."""
    return KernelInbox().post(
        from_who="Ross (operator) — F47 chat room",
        subject="message dropped during chat (no live backend)",
        body=message,
        priority="normal",
    )


def greeting() -> str:
    return _greeting()
