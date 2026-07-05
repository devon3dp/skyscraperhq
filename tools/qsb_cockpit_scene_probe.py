#!/usr/bin/env python3
"""qsb_cockpit_scene_probe.py — headless browser probe of the cockpit 3D scene.

Loads http://127.0.0.1:8765/cockpit, captures console messages, waits 6 seconds,
then dumps window.QSB_SCENE.diag — what Babylon actually saw.

Saves a screenshot to /tmp/skyscraper/cockpit_probe.png so we can see what
Ross is seeing.
"""
from __future__ import annotations
import json, pathlib
from playwright.sync_api import sync_playwright

OUT = pathlib.Path("/tmp/skyscraper")
OUT.mkdir(exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="/opt/google/chrome/chrome", args=["--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 950})
        page = ctx.new_page()
        console = []
        errors = []
        page.on("console", lambda m: console.append({"type": m.type, "text": m.text[:300]}))
        page.on("pageerror", lambda e: errors.append(str(e)[:400]))

        page.goto("http://127.0.0.1:8765/cockpit", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(6000)

        # Pull the scene diag
        diag = page.evaluate("""() => {
            const out = {};
            if (window.QSB_SCENE) {
                out.diag = window.QSB_SCENE.diag || {};
                out.ready = !!window.QSB_SCENE.ready;
                out.has_engine = !!window.QSB_SCENE.engine;
                out.has_scene = !!window.QSB_SCENE.scene;
                out.floorMeshes_count = Object.keys(window.QSB_SCENE.floorMeshes || {}).length;
            }
            const c = document.getElementById('qsbCanvas');
            if (c) {
                out.canvas_clientW = c.clientWidth;
                out.canvas_clientH = c.clientHeight;
                out.canvas_W = c.width;
                out.canvas_H = c.height;
                out.canvas_opacity = getComputedStyle(c).opacity;
            }
            const sb = document.querySelector('.stage-body');
            if (sb) {
                out.stage_classes = sb.className;
                out.stage_W = sb.clientWidth;
                out.stage_H = sb.clientHeight;
            }
            out.BABYLON_present = typeof BABYLON !== 'undefined';
            return out;
        }""")

        page.screenshot(path=str(OUT / "cockpit_probe.png"), full_page=False)
        browser.close()

    report = {
        "diag": diag,
        "console_messages": console[-30:],
        "page_errors": errors,
        "screenshot": str(OUT / "cockpit_probe.png"),
    }
    print(json.dumps(report, indent=2, default=str))

if __name__ == "__main__":
    main()
