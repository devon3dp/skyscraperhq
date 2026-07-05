#!/usr/bin/env python3
"""qsb_netlify_deploy.py — bake live data into static HTML and deploy to Netlify.

Ross 2026-06-12: token in vault. Deploy /shops, /studio, /garden, /lumen as
fully static sites (data inlined so they don't need the local dashboard API).

Steps per surface:
  1. Read the live JSON from the local dashboard
  2. Read the template HTML
  3. Replace the fetch() call with an inline data constant
  4. Write to a temp build dir
  5. Zip the dir
  6. POST to /api/v1/sites/{id}/deploys

Sites get created via API if they don't exist yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.netlify"
STATIC = ROOT / "src/dashboard/static"
DASH = "http://127.0.0.1:8765"
NETLIFY_API = "https://api.netlify.com/api/v1"


def load_token():
    if not VAULT.exists():
        print("[deploy] vault missing:", VAULT)
        sys.exit(1)
    for line in VAULT.read_text().splitlines():
        if line.startswith("NETLIFY_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip()
    print("[deploy] NETLIFY_AUTH_TOKEN missing from vault")
    sys.exit(1)


def api(method, path, token, body=None, raw_body=None, headers=None):
    url = NETLIFY_API + path
    h = {"Authorization": f"Bearer {token}"}
    if body is not None:
        raw_body = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    if headers: h.update(headers)
    req = urllib.request.Request(url, data=raw_body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ct = resp.headers.get("Content-Type", "")
            data = resp.read()
            if "json" in ct:
                return json.loads(data.decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"[deploy] HTTP {e.code} {method} {url}\n{msg[:400]}")
        raise


def fetch_local_json(path):
    req = urllib.request.Request(DASH + path)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def bake_shops_html():
    """Build the shops index as static — embed all 20 shops + their detail."""
    idx = fetch_local_json("/api/shops")
    details = {}
    for s in idx["shops"]:
        try:
            details[s["floor"]] = fetch_local_json(f"/api/shop/{s['floor']}")
        except Exception as e:
            print(f"[deploy]   skip {s['floor']}: {e}")
    src = (STATIC / "shops.html").read_text(encoding="utf-8")
    # Replace the two fetch calls with inline data lookups
    inline = "const __SHOPS_INDEX__ = " + json.dumps(idx) + ";\n"
    inline += "const __SHOP_DETAILS__ = " + json.dumps(details) + ";\n"
    src = src.replace(
        "const r = await fetch('/api/shops'); const idx = await r.json();",
        inline + "const idx = __SHOPS_INDEX__;",
    )
    src = src.replace(
        "const dr = await fetch('/api/shop/' + tag); const d = await dr.json();",
        "const d = __SHOP_DETAILS__[tag] || { ok: false };",
    )
    return src


def bake_one_shop_html(template_path, floor_tag):
    """Build studio.html / garden.html with the single-shop data inlined."""
    detail = fetch_local_json(f"/api/shop/{floor_tag}")
    src = (STATIC / template_path).read_text(encoding="utf-8")
    inline = "const __SHOP__ = " + json.dumps(detail) + ";\n"
    src = src.replace(
        f"const r = await fetch('/api/shop/{floor_tag}'); const d = await r.json();",
        inline + "const d = __SHOP__;",
    )
    return src


def write_build(build_dir: Path, files: dict):
    build_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        p = build_dir / name
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)


def zip_build(build_dir: Path) -> Path:
    zip_path = build_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in build_dir.rglob("*"):
            if fp.is_file():
                zf.write(fp, fp.relative_to(build_dir).as_posix())
    return zip_path


def ensure_site(token, name):
    """Find or create a Netlify site with the given name. Returns the site dict."""
    sites = api("GET", "/sites", token)
    for s in sites:
        if s["name"] == name:
            return s
    # Create
    print(f"[deploy] creating site '{name}'…")
    return api("POST", "/sites", token, body={"name": name})


def deploy_zip(token, site_id, zip_path: Path):
    raw = zip_path.read_bytes()
    res = api("POST", f"/sites/{site_id}/deploys",
              token,
              raw_body=raw,
              headers={"Content-Type": "application/zip"})
    return res


def build_and_deploy(surface, html_files, token):
    """surface: short name like 'qsb-shops'. html_files: dict name->str."""
    print(f"\n=== {surface} ===")
    tmp = Path(tempfile.mkdtemp(prefix=f"netdeploy-{surface}-"))
    try:
        write_build(tmp, html_files)
        zip_path = zip_build(tmp)
        site = ensure_site(token, surface)
        print(f"  site_id={site['id']} url={site.get('ssl_url') or site.get('url')}")
        dep = deploy_zip(token, site["id"], zip_path)
        # Wait briefly for ready
        for _ in range(20):
            time.sleep(2)
            cur = api("GET", f"/deploys/{dep['id']}", token)
            if cur.get("state") in ("ready", "error"):
                dep = cur
                break
        print(f"  state={dep.get('state')}  deploy_url={dep.get('deploy_ssl_url') or dep.get('deploy_url')}")
        return {"surface": surface, "site": site["name"],
                 "url": site.get("ssl_url") or site.get("url"),
                 "deploy_url": dep.get("deploy_ssl_url") or dep.get("deploy_url"),
                 "state": dep.get("state")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="single surface: shops|studio|garden")
    args = ap.parse_args()
    token = load_token()
    targets = {"shops":  ("qsb-tower-shops",  {"index.html": bake_shops_html()}),
                "studio": ("qsb-tower-studio", {"index.html": bake_one_shop_html("studio.html", "F58")}),
                "garden": ("qsb-tower-garden", {"index.html": bake_one_shop_html("garden.html", "F149")}),
              }
    results = []
    for k, (site_name, files) in targets.items():
        if args.only and args.only != k: continue
        try:
            r = build_and_deploy(site_name, files, token)
            results.append(r)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"surface": site_name, "error": str(e)[:200]})
    print("\n=== SUMMARY ===")
    for r in results:
        if r.get("error"):
            print(f"  {r['surface']}: ERROR — {r['error']}")
        else:
            print(f"  {r['surface']:24s}  state={r.get('state'):6s}  {r.get('url')}")
    return results


if __name__ == "__main__":
    main()
