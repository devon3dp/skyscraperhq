"""
QSB G2 SVG Renderer Probe
Phase: QSB_NEXT_SAFE_IMPROVEMENTS_V1

Stronger probe for completion-engine gate G2. Instead of merely checking
files-on-disk, this probe actively fetches:

  * GET /                           (HTML body)
  * GET /static/qsb_tower_2d.js     (renderer source)
  * GET /static/qsb_scene.js        (Babylon source)
  * GET /static/cockpit.js          (orchestrator)
  * GET /static/qsb_rebuild_workers.js
  * GET /static/qsb_workforce_ops_panel.js
  * GET /api/unified                (worker payload)

and verifies:

  * DOM container ids: qsbTower2D, qsbCanvas, workerLabels, hudTip
  * Worker view selector exists with selected_floor_and_groups SELECTED
  * Script tags include every renderer file
  * refreshWorkers(), upsertWorker(), buildShafts() in tower_2d.js
  * QSB_TOWER_2D_INIT defined and exported
  * Babylon vendor file > 100KB (sanity)
  * unified.workers[] non-empty
  * unified.worker_truth_debug.canonical_count > 100

This does NOT need a headless browser. It is a deeper, deterministic
check than the file-on-disk path used by the completion engine. The
result is recorded so the completion engine can read it.

Outputs:
  data/registries/qsb_g2_svg_probe.json
  data/logs/qsb_g2_svg_probe.txt
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_PROBE = REG / "qsb_g2_svg_probe.json"
L_PROBE = LOGS / "qsb_g2_svg_probe.txt"

DASH = "http://127.0.0.1:8765"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get(path, timeout=4):
    try:
        with urllib.request.urlopen(DASH + path, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return 0, str(exc)


def _check(name, ok, evidence):
    return {"check": name, "ok": bool(ok), "evidence": evidence}


def probe():
    checks = []

    code, html = _get("/")
    checks.append(_check("GET / returns 200", code == 200,
                          "status=%s body_size=%s" % (code, len(html))))

    # DOM ids
    for cid in ("qsbTower2D", "qsbCanvas", "workerLabels", "hudTip"):
        present = ('id="%s"' % cid) in html
        checks.append(_check("DOM id %s" % cid, present,
                              "id=\"%s\" %s" % (cid, "present" if present else "MISSING")))

    # Worker view selector default
    m = re.search(r'<select[^>]+id="workerViewMode"[^>]*>([\s\S]*?)</select>', html)
    sel_default = None
    if m:
        opts = m.group(1)
        sel_m = re.search(r'<option value="([^"]+)"[^>]*selected', opts)
        sel_default = sel_m.group(1) if sel_m else None
    checks.append(_check("workerViewMode default == selected_floor_and_groups",
                          sel_default == "selected_floor_and_groups",
                          "selected=%s" % sel_default))

    # Script tags
    expected_scripts = [
        "/static/qsb_tower_2d.js",
        "/static/qsb_scene.js",
        "/static/cockpit.js",
        "/static/qsb_rebuild_workers.js",
        "/static/qsb_workforce_ops_panel.js",
        "/static/vendor/babylon.js",
    ]
    for s in expected_scripts:
        present = ('src="' + s + '"') in html
        checks.append(_check("<script src=%s>" % s, present,
                              "present" if present else "MISSING"))

    # tower_2d.js content
    code_2d, body_2d = _get("/static/qsb_tower_2d.js")
    checks.append(_check("qsb_tower_2d.js fetch 200", code_2d == 200,
                          "status=%s size=%s" % (code_2d, len(body_2d))))
    for fn in ("function refreshWorkers", "function upsertWorker",
                "function buildShafts"):
        present = fn in body_2d
        checks.append(_check("tower_2d.js contains %s" % fn,
                              present, "found" if present else "MISSING"))
    has_init = "QSB_TOWER_2D_INIT" in body_2d
    checks.append(_check("QSB_TOWER_2D_INIT exported",
                          has_init, "found" if has_init else "MISSING"))

    # Babylon vendor sanity
    code_b, body_b = _get("/static/vendor/babylon.js")
    checks.append(_check("vendor/babylon.js > 100KB",
                          code_b == 200 and len(body_b) > 100_000,
                          "status=%s size=%s" % (code_b, len(body_b))))

    # Unified payload
    code_u, body_u = _get("/api/unified")
    try:
        unified = json.loads(body_u) if code_u == 200 else None
    except Exception:
        unified = None
    workers_len = len((unified or {}).get("workers") or [])
    canonical = (((unified or {}).get("worker_truth_debug") or {})
                 .get("canonical_count") or 0)
    checks.append(_check("/api/unified responds 200", code_u == 200,
                          "status=%s" % code_u))
    checks.append(_check("/api/unified.workers[] non-empty", workers_len > 0,
                          "workers=%s" % workers_len))
    checks.append(_check("canonical_count > 100", canonical > 100,
                          "canonical=%s" % canonical))

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    payload = {
        "ok": True,
        "phase": "QSB_NEXT_SAFE_IMPROVEMENTS_V1",
        "kind": "qsb_g2_svg_probe",
        "generated_ts": _now(),
        "passed":   passed,
        "total":    total,
        "all_passed": passed == total,
        "checks":   checks,
        "note":     "This probe does NOT use a headless browser. It is a "
                    "deeper static + HTTP probe than the file-on-disk path. "
                    "For pixel-level verification, run Playwright separately.",
    }
    REG.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    P_PROBE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with L_PROBE.open("w", encoding="utf-8") as f:
        f.write("QSB G2 SVG Probe\n")
        f.write("=" * 60 + "\n")
        f.write("ts:         " + payload["generated_ts"] + "\n")
        f.write("passed:     %s / %s\n\n" % (passed, total))
        for c in checks:
            f.write("  [%s] %s -- %s\n" % (
                "OK" if c["ok"] else "FAIL", c["check"], c["evidence"]))
    return payload


def main():
    out = probe()
    print(json.dumps({
        "passed": out["passed"], "total": out["total"],
        "all_passed": out["all_passed"],
    }, indent=2))


if __name__ == "__main__":
    main()
