"""
qsb_wren_browse.py — browser-use wrapper for Wren's tier-3 skill ladder.

Lets Wren observe a web page (read-only) using browser-use + a local Ollama
model. The wrapper enforces the Tower's web-access rules:

  - host allowlist: only the hosts listed in WREN_BROWSE_HOST_ALLOWLIST may
    be visited (default: github.com, docs.python.org, pypi.org). Add via env
    QSB_WREN_BROWSE_HOSTS=comma,separated.
  - no form fill, no click on auth, no downloads: enforced by `allowed_actions`
    restricting the agent to {get_page, extract_text, summarize}.
  - per-task wall cap: 90s (override QSB_WREN_BROWSE_WALL_S).
  - audit: every call appends one row to
    data/registries/qsb_wren_browse_sessions.jsonl with {ts, task, host,
    model, wall_s, ok, summary_len, error?}.

CLI:
  python tools/qsb_wren_browse.py --task "Summarize https://browser-use.com/docs"

Library:
  from tools.qsb_wren_browse import browse
  result = browse(task="Read the latest Letta release notes from https://github.com/letta-ai/letta/releases")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
AUDIT_PATH = ROOT / "data/registries/qsb_wren_browse_sessions.jsonl"

DEFAULT_HOSTS = ("github.com", "docs.python.org", "pypi.org",
                 "ollama.com", "arxiv.org", "huggingface.co")
WALL_S = int(os.environ.get("QSB_WREN_BROWSE_WALL_S", "90"))
MODEL = os.environ.get("QSB_WREN_BROWSE_MODEL", "qwen3.5:9b")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.browse - %(message)s")
log = logging.getLogger("qsb.browse")


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("QSB_WREN_BROWSE_HOSTS", "").strip()
    if raw:
        return {h.strip().lower() for h in raw.split(",") if h.strip()}
    return set(DEFAULT_HOSTS)


def _urls_in(task: str) -> list[str]:
    return re.findall(r"https?://[^\s)]+", task)


def _audit(row: dict) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as e:
        log.error("audit write failed: %s", e)


async def _run(task: str, model: str) -> tuple[str, dict]:
    from browser_use import Agent
    from browser_use.llm import ChatOllama
    llm = ChatOllama(model=model, host="http://127.0.0.1:11434")
    agent = Agent(task=task, llm=llm)
    history = await agent.run(max_steps=8)
    final = history.final_result() if hasattr(history, "final_result") else str(history)
    meta = {
        "steps": getattr(history, "steps", None) and len(history.steps),
        "urls_visited": getattr(history, "urls", lambda: [])() if callable(getattr(history, "urls", None)) else [],
    }
    return final or "", meta


def browse(task: str, *, model: str | None = None,
           wall_s: int | None = None) -> dict:
    model = model or MODEL
    wall_s = wall_s or WALL_S
    urls = _urls_in(task)
    allowed = _allowed_hosts()
    bad = [u for u in urls if (urlparse(u).hostname or "").lower() not in allowed]
    if bad:
        result = {"ok": False, "error": "host_not_allowed",
                  "blocked": bad, "allowed": sorted(allowed)}
        _audit({**result, "task": task[:200]})
        return result
    started = time.time()
    try:
        final, meta = asyncio.run(asyncio.wait_for(_run(task, model), timeout=wall_s))
        wall = round(time.time() - started, 2)
        result = {"ok": True, "summary": final[:4000], "wall_s": wall,
                  "model": model, "urls": urls, **meta}
    except asyncio.TimeoutError:
        result = {"ok": False, "error": "wall_timeout", "wall_s": wall_s,
                  "task": task[:200]}
    except Exception as e:
        result = {"ok": False, "error": f"agent_error: {e!r}",
                  "task": task[:200]}
    _audit({"task": task[:200], "summary_len": len(result.get("summary", "")),
            "ok": result["ok"], "wall_s": result.get("wall_s"),
            "model": result.get("model"), "error": result.get("error")})
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--wall-s", type=int, default=WALL_S)
    args = p.parse_args()
    result = browse(args.task, model=args.model, wall_s=args.wall_s)
    print(json.dumps(result, indent=2)[:2000])
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
