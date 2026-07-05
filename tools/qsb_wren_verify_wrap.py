#!/usr/bin/env python3
"""qsb_wren_verify_wrap.py — HQ verifies Wren's test claims after the fact.

Ross 2026-07-05: Wren confabulated the RSI v3 test result (reported 66.13,
actual output 0.0). Same confabulation as TP+Acer, just harder to catch
because Wren is usually reliable. This wrap makes confabulation impossible
to hide: after Wren finishes a task, we re-run the script she claims to have
tested and compare her reported number to the actual number.

Design (kept simple, no prompt edits):
  · read Wren's last reply from her chain output / mind file
  · extract:  reported_path  (file she said she wrote)
              reported_output (number she claimed the file prints)
  · re-run the file with `python3 <path>`
  · diff actual output vs reported
  · outcomes:
      MATCH        → log VERIFIED_CORRECT to lessons, town-square OK
      MISMATCH     → log CONFABULATED to lessons, town-square ALERT to Ross
      NO_TEST_DONE → no output claimed, skip (not a confabulation)
      SYNTAX_ERROR → file broken, log BROKEN_CODE

The wrap is a POST-CHECK layer. It does NOT edit Wren's base prompt.
It does NOT interrupt her chain. It just verifies + reports + adds
concrete lessons using her ACTUAL failure patterns as training data.

USAGE
  python3 tools/qsb_wren_verify_wrap.py --reply-file <path>
  python3 tools/qsb_wren_verify_wrap.py --reply-text "..."
  python3 tools/qsb_wren_verify_wrap.py --tail-mind    # verify last mind entry

Return code: 0=match, 1=mismatch, 2=no-test, 3=error
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"
SANDBOX = ROOT / "data/wren_sandbox"

sys.path.insert(0, str(ROOT / "tools"))


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


# ---------- extract Wren's claims from her reply text ----------

_PATH_HINTS = [
    r"(?:V\d+_?FILE|FILE|PATH|WROTE|SAVED)[:=\s]+([^\s\n]+\.py)",
    r"(data/wren_sandbox/[^\s\n]+\.py)",
    r"(rsi_demo(?:_v\d+)?\.py)",
]
_OUTPUT_HINTS = [
    r"(?:RSI_OUTPUT|OUTPUT|RESULT|PRINTS?)[:=\s]+(-?[\d]+\.?\d*)",
    r"(?:CORRECT|answer)[:=\s]+(?:yes|true)[,\s]+(-?\d+\.?\d*)",
]


def extract_claims(reply_text: str) -> dict:
    """Pull out (path, reported_output, correct_flag) from Wren's reply."""
    path = None
    for pat in _PATH_HINTS:
        m = re.search(pat, reply_text, re.IGNORECASE)
        if m:
            path = m.group(1).strip()
            break
    # resolve to absolute
    if path and not path.startswith("/"):
        cand = SANDBOX / path.split("/")[-1]
        if cand.exists():
            path = str(cand)
        else:
            cand2 = ROOT / path
            if cand2.exists():
                path = str(cand2)
    output = None
    for pat in _OUTPUT_HINTS:
        m = re.search(pat, reply_text, re.IGNORECASE)
        if m:
            try:
                output = float(m.group(1))
                break
            except ValueError:
                continue
    correct = None
    cm = re.search(r"CORRECT[:=\s]+(yes|no|true|false)", reply_text, re.IGNORECASE)
    if cm:
        correct = cm.group(1).lower() in ("yes","true")
    return {"path": path, "reported_output": output, "reported_correct": correct}


# ---------- run the file + capture actual output ----------

def run_script(path: str, timeout: int = 15) -> dict:
    """Run python3 <path>, return {ok, stdout, stderr, exit_code}."""
    if not Path(path).exists():
        return {"ok": False, "stdout":"", "stderr":f"NOT_FOUND: {path}",
                "exit_code": -1}
    try:
        r = subprocess.run(["python3", path],
                           capture_output=True, text=True,
                           timeout=timeout,
                           cwd=str(Path(path).parent))
        return {"ok": r.returncode == 0,
                "stdout": r.stdout.strip(),
                "stderr": r.stderr.strip(),
                "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout":"", "stderr":"TIMEOUT", "exit_code": -2}
    except Exception as e:
        return {"ok": False, "stdout":"", "stderr":str(e)[:400],
                "exit_code": -3}


def _first_number(s: str) -> float | None:
    m = re.search(r"-?\d+\.?\d*(?:[eE][+-]?\d+)?", s)
    if not m: return None
    try: return float(m.group(0))
    except ValueError: return None


# ---------- verdict ----------

def verify(reply_text: str) -> dict:
    claims = extract_claims(reply_text)
    result = {"ts": _utc(), "claims": claims, "actual": None,
              "verdict": None, "detail": ""}

    if not claims["path"]:
        result["verdict"] = "NO_FILE_CLAIMED"
        result["detail"] = "Wren didn't mention a specific .py file"
        return result

    if claims["reported_output"] is None:
        result["verdict"] = "NO_OUTPUT_CLAIMED"
        result["detail"] = f"Path {claims['path']} mentioned, but no numeric result"
        return result

    run = run_script(claims["path"])
    result["actual"] = run

    if not run["ok"]:
        result["verdict"] = "BROKEN_CODE"
        result["detail"] = f"exit={run['exit_code']} stderr={run['stderr'][:200]}"
        return result

    actual_num = _first_number(run["stdout"])
    if actual_num is None:
        result["verdict"] = "NO_ACTUAL_OUTPUT"
        result["detail"] = f"script printed non-numeric: {run['stdout'][:200]}"
        return result

    reported = claims["reported_output"]
    delta = abs(actual_num - reported)
    tol = max(0.01, abs(reported) * 0.001)  # 0.1% relative

    if delta <= tol:
        result["verdict"] = "VERIFIED_CORRECT"
        result["detail"] = f"actual={actual_num} matches reported={reported}"
    else:
        result["verdict"] = "CONFABULATED"
        result["detail"] = (f"REPORTED {reported} · ACTUAL {actual_num} · "
                            f"delta {delta:.4f} > tol {tol:.4f}")
    return result


# ---------- write audit + lessons + notify ----------

def stamp(verdict: dict, source: str = "wren_reply") -> None:
    aud = REG / "qsb_wren_verify_audit.jsonl"
    aud.parent.mkdir(parents=True, exist_ok=True)
    with aud.open("a") as f:
        f.write(json.dumps({"source": source, **verdict}) + "\n")


def learn_from(verdict: dict) -> None:
    """Append a concrete lesson using this actual event as training data."""
    try:
        from qsb_ceo_distiller import append_lessons
    except Exception:
        return
    v = verdict["verdict"]
    d = verdict.get("detail","")
    if v == "CONFABULATED":
        append_lessons("wren", [
            f"You reported a test result you did not actually run. Detail: {d}",
            "Before reporting a number as CORRECT, read wren_bash's stdout verbatim.",
            "If wren_bash returned no output or an error, report EMPTY_OUTPUT — do not invent a plausible number.",
        ])
    elif v == "VERIFIED_CORRECT":
        append_lessons("wren", [
            f"Good work — your reported {d} was verified by independent re-run.",
        ])
    elif v == "BROKEN_CODE":
        append_lessons("wren", [
            f"You shipped code that fails when re-run: {d}. Test locally before reporting success.",
        ])


def notify(verdict: dict) -> None:
    v = verdict["verdict"]
    if v not in ("CONFABULATED","BROKEN_CODE"):
        return
    try:
        from qsb_town_square import post_to_town_square
    except Exception:
        return
    icon = "⚠️" if v == "BROKEN_CODE" else "🚨"
    msg = (f"{icon} verify-wrap · Wren {v} · {verdict.get('detail','')[:300]}")
    post_to_town_square("hq_claude", msg, to="ross", src="verify_wrap")


# ---------- CLI ----------

def _load_last_wren_mind_reply() -> str:
    p = REG / "qsb_wren_mind.json"
    if not p.exists(): return ""
    try:
        m = json.loads(p.read_text())
        thoughts = m.get("recent_thoughts", [])
        if not thoughts: return ""
        return thoughts[-1].get("text","")
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reply-file", help="path to a text file with Wren's reply")
    ap.add_argument("--reply-text", help="Wren's reply as a string")
    ap.add_argument("--tail-mind", action="store_true",
                    help="use last thought from qsb_wren_mind.json")
    ap.add_argument("--quiet", action="store_true", help="suppress human log")
    a = ap.parse_args()

    if a.reply_file:
        text = Path(a.reply_file).read_text()
    elif a.reply_text:
        text = a.reply_text
    elif a.tail_mind:
        text = _load_last_wren_mind_reply()
        if not text:
            print("  (no thought in mind file)")
            return 2
    else:
        text = sys.stdin.read()

    v = verify(text)
    stamp(v)
    learn_from(v)
    notify(v)

    if not a.quiet:
        print(json.dumps(v, indent=2, default=str))

    verdict_code = {"VERIFIED_CORRECT": 0,
                    "CONFABULATED": 1,
                    "BROKEN_CODE": 1,
                    "NO_OUTPUT_CLAIMED": 2,
                    "NO_FILE_CLAIMED": 2,
                    "NO_ACTUAL_OUTPUT": 3}.get(v["verdict"], 3)
    return verdict_code


if __name__ == "__main__":
    sys.exit(main())
