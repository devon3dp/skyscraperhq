"""
qsb_wren_describe_form.py — Wren's tier-3b skill: visit a page, describe
every form field as JSON, take a screenshot. Read-only. No submit, no fill.

Builds training corpus for the Wren team and lets Wren plan a future signup
without touching anything. Output looks like:

  {
    "url": "https://signup.oracle.com/...",
    "fields": [
      {"selector": "#email", "label": "Email", "type": "email",
       "required": true, "placeholder": "you@example.com"},
      {"selector": "#first_name", "label": "First name", "type": "text",
       "required": true},
      ...
    ],
    "buttons": [
      {"selector": "button[type=submit]", "text": "Create account",
       "disabled": false},
    ],
    "screenshot": "data/registries/wren_form_specs/oracle_signup_2026-06-15T12-30-00Z.png"
  }

CLI:
  python tools/qsb_wren_describe_form.py --url https://github.com/login

Library:
  from tools.qsb_wren_describe_form import describe_form
  spec = describe_form("https://github.com/login")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
AUDIT = ROOT / "data/registries/qsb_wren_form_specs.jsonl"
SCREENSHOT_DIR = ROOT / "data/registries/wren_form_specs"

DEFAULT_HOSTS = ("github.com", "docs.python.org", "pypi.org",
                 "ollama.com", "huggingface.co",
                 "console.hetzner.cloud", "signup.hetzner.com",
                 "cloud.oracle.com", "signup.oracle.com",
                 "tailscale.com", "console.cloud.google.com")
WALL_S = int(os.environ.get("QSB_DESCRIBE_FORM_WALL_S", "60"))

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.describe_form - %(message)s")
log = logging.getLogger("qsb.describe_form")


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("QSB_DESCRIBE_FORM_HOSTS", "").strip()
    if raw:
        return {h.strip().lower() for h in raw.split(",") if h.strip()}
    return set(DEFAULT_HOSTS)


def _now_iso_filesafe() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())


def _audit(row: dict) -> None:
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as e:
        log.error("audit write failed: %s", e)


async def _describe(url: str, screenshot_path: Path) -> dict:
    """Use Playwright directly — no LLM in the loop for this skill."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                        " (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.0)
            fields = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    "input, select, textarea"
                )).map(el => {
                    const id = el.id ? "#" + el.id : "";
                    const name = el.name ? `[name="${el.name}"]` : "";
                    const tag = el.tagName.toLowerCase();
                    const sel = id || (tag + name);
                    let label = "";
                    if (el.id) {
                        const lab = document.querySelector(
                            `label[for="${el.id}"]`);
                        if (lab) label = (lab.innerText || "").trim();
                    }
                    if (!label && el.placeholder) label = el.placeholder;
                    if (!label) label = el.getAttribute("aria-label") || "";
                    return {
                        selector: sel,
                        tag,
                        type: el.type || tag,
                        name: el.name || "",
                        label: label.slice(0, 120),
                        placeholder: el.placeholder || "",
                        required: !!el.required,
                        disabled: !!el.disabled,
                        value_preview: (el.value || "").slice(0, 24),
                    };
                });
            """)
            buttons = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    "button, [role='button'], input[type='submit']"
                )).slice(0, 30).map(el => ({
                    selector: el.id ? "#" + el.id : el.tagName.toLowerCase()
                               + (el.getAttribute('type') ? `[type="${el.getAttribute('type')}"]` : ""),
                    text: (el.innerText || el.value || "").slice(0, 80),
                    disabled: !!el.disabled,
                }));
            """)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=False)
            return {
                "url": url,
                "title": (await page.title())[:140],
                "fields": fields,
                "buttons": buttons,
                "screenshot": str(screenshot_path.relative_to(ROOT)),
            }
        finally:
            await ctx.close()
            await browser.close()


def describe_form(url: str) -> dict:
    host = (urlparse(url).hostname or "").lower()
    if host not in _allowed_hosts():
        result = {"ok": False, "error": "host_not_allowed",
                  "host": host, "allowed": sorted(_allowed_hosts())}
        _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "url": url, **result})
        return result
    screenshot = SCREENSHOT_DIR / f"{host}_{_now_iso_filesafe()}.png"
    t0 = time.time()
    try:
        spec = asyncio.run(asyncio.wait_for(
            _describe(url, screenshot), timeout=WALL_S))
        spec["ok"] = True
        spec["wall_s"] = round(time.time() - t0, 2)
    except asyncio.TimeoutError:
        spec = {"ok": False, "error": "wall_timeout",
                "url": url, "wall_s": WALL_S}
    except Exception as e:
        spec = {"ok": False, "error": f"playwright_error: {e!r}", "url": url}
    _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             **spec,
             "fields_count": len(spec.get("fields", [])),
             "buttons_count": len(spec.get("buttons", []))})
    return spec


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    args = p.parse_args()
    result = describe_form(args.url)
    out = {"ok": result.get("ok"), "url": result.get("url"),
           "title": result.get("title"),
           "fields_count": len(result.get("fields", [])),
           "buttons_count": len(result.get("buttons", [])),
           "screenshot": result.get("screenshot"),
           "wall_s": result.get("wall_s"),
           "error": result.get("error")}
    print(json.dumps(out, indent=2))
    if result.get("ok") and result.get("fields"):
        print("\nFields (first 10):")
        for f in result["fields"][:10]:
            print(f"  {f.get('selector'):30s} type={f.get('type'):10s}"
                  f" label={f.get('label')[:50]!r}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
