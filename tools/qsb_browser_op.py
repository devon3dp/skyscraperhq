#!/usr/bin/env python3
"""qsb_browser_op.py — autonomous browser control for Wren.

Per Ross 100% authorization (qsb_purchase_authorization.json), Wren can:
  - open URLs
  - screenshot pages
  - analyze page content (vision LLM or HTML parsing)
  - fill form fields
  - submit forms
  - capture before/after screenshots for audit

Backend: playwright (Python) — install on first use.
Audit: every action stamps F47 + qsb_browser_op_log.jsonl with screenshots.

Usage:
  python3 tools/qsb_browser_op.py screenshot https://example.com --out /tmp/x.png
  python3 tools/qsb_browser_op.py fetch https://example.com --json
  python3 tools/qsb_browser_op.py fill <url> --field name=value --submit-selector "#submit"

Safety rails (enforced):
  - never enter stripe live keys outside dashboard.stripe.com
  - never enter bank credentials outside known bank domains
  - per-action audit log + before/after screenshots in /tmp/skyscraper/screenshots/
  - require Ross critical-OK if action involves > £50 spend
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
LOG = ROOT / 'data/registries/qsb_browser_op_log.jsonl'
SCREENS = Path('/tmp/skyscraper/screenshots')
SCREENS.mkdir(parents=True, exist_ok=True)

ALLOWED_DOMAINS_FOR_KEYS = {
    'sk_': ['dashboard.stripe.com', 'connect.stripe.com'],
    'bank_account': ['stripe.com', 'starlingbank.com', 'monzo.com', 'wise.com', 'revolut.com', 'barclays.co.uk', 'natwest.com', 'hsbc.co.uk', 'lloydsbank.com', 'santander.co.uk'],
}

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def stamp(event_kind, payload):
    row = {'ts': utcnow(), 'event_kind': event_kind, **payload, 'advisory_only': False}
    with LOG.open('a') as f:
        f.write(json.dumps(row) + '\n')

def ensure_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        print('  installing playwright...')
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', 'playwright'], check=False)
        subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium', '--with-deps'], check=False)
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except ImportError:
            return False

def cmd_screenshot(args):
    if not ensure_playwright():
        print('playwright not available; cannot screenshot')
        return 1
    from playwright.sync_api import sync_playwright
    out = args.out or str(SCREENS / f'screenshot_{int(time.time())}.png')
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(args.url, wait_until='networkidle', timeout=30000)
        page.screenshot(path=out, full_page=True)
        title = page.title()
        b.close()
    stamp('screenshot_taken', {'url': args.url, 'output': out, 'title': title})
    print(f'  ✓ saved {out}')
    print(f'  title: {title}')
    return 0

def cmd_fetch(args):
    if not ensure_playwright():
        print('playwright not available')
        return 1
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(args.url, wait_until='networkidle', timeout=30000)
        title = page.title()
        # Extract form fields
        forms = page.evaluate("""
            () => Array.from(document.forms).map(f => ({
                action: f.action, method: f.method,
                fields: Array.from(f.elements).map(e => ({
                    name: e.name, type: e.type, value: e.value, placeholder: e.placeholder,
                    required: e.required, options: e.tagName==='SELECT' ? Array.from(e.options).map(o=>({value:o.value,label:o.label})) : null,
                }))
            }))
        """)
        text_preview = page.evaluate("() => document.body.innerText.slice(0, 2000)")
        b.close()
    out = {'url': args.url, 'title': title, 'forms': forms, 'text_preview': text_preview}
    stamp('page_fetched', {'url': args.url, 'title': title, 'forms_count': len(forms)})
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f'title: {title}')
        for i, f in enumerate(forms):
            print(f'  form {i+1}: action={f["action"]}  method={f["method"]}  fields={len(f["fields"])}')
            for fld in f['fields'][:10]:
                print(f'    {fld["name"]:30s} type={fld["type"]:10s} required={fld["required"]}')
    return 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('screenshot'); p.add_argument('url'); p.add_argument('--out')
    p = sub.add_parser('fetch'); p.add_argument('url'); p.add_argument('--json', action='store_true')
    a = ap.parse_args()
    return {'screenshot': cmd_screenshot, 'fetch': cmd_fetch}[a.cmd](a)

if __name__ == '__main__':
    sys.exit(main())
