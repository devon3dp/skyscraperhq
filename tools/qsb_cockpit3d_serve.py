"""
qsb_cockpit3d_serve.py — Floor 49 Tower Studio's 3D browser cockpit.

A single-page Three.js skyscraper with 169 floor slabs, each colored by
the live status of that floor. Hover any slab to see name + worker count
+ last tick.

  GET /                    -> static/cockpit3d.html
  GET /api/floor_states    -> {totals: {...}, floors: [{floor, name, status, workers, last_tick}, ...]}

Status per floor is derived from registry files:
  - F25, F31, F38 ticker logs (recent rows -> "working")
  - canonical roster -> "paper_only" if no recent tick
  - if loop process for that floor is alive -> "idle" (waiting for next tick)
  - if a row mentions "fail" or "error" in last hour -> "blocked"

Read-only. Bound to loopback :8853.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DASHBOARD_BASE = os.environ.get("QSB_DASHBOARD_BASE", "http://127.0.0.1:8765")

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATIC_DIR = ROOT / "tools/cockpit3d_static"
FLOORS_DIR = ROOT / "floors"
REGISTRIES = ROOT / "data/registries"
CANONICAL = REGISTRIES / "qsb_canonical_workers.json"
ACTIVITY_TAIL = REGISTRIES / "qsb_tower_activity_tail.jsonl"

HOST = "127.0.0.1"
PORT = int(os.environ.get("QSB_COCKPIT3D_PORT", "8853"))

TICK_LOG_BY_FLOOR = {
    25: REGISTRIES / "qsb_f25_tick_log.jsonl",
    31: REGISTRIES / "qsb_f31_tick_log.jsonl",
    38: REGISTRIES / "qsb_f38_tick_log.jsonl",
}

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s qsb.cockpit3d - %(message)s")
log = logging.getLogger("qsb.cockpit3d")


def _floor_num_from_name(name: str) -> int | None:
    for part in name.split("_"):
        try:
            return int(part)
        except ValueError:
            pass
    return None


def _list_floors() -> dict[int, str]:
    floors: dict[int, str] = {}
    if not FLOORS_DIR.exists():
        return floors
    for entry in FLOORS_DIR.iterdir():
        if not entry.is_dir():
            continue
        n = _floor_num_from_name(entry.name)
        if n is None:
            continue
        pretty = " ".join(w.capitalize() for w in entry.name.split("_")[2:]) or entry.name
        floors[n] = pretty
    return floors


def _recent_jsonl(path: Path, window_s: int) -> list[dict]:
    if not path.exists():
        return []
    cutoff = time.time() - window_s
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            f.seek(max(0, path.stat().st_size - 200_000))
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                ts = r.get("ts", "")
                try:
                    t = calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
                except ValueError:
                    continue
                if t >= cutoff:
                    out.append(r)
    except OSError:
        return out
    return out


def _live_procs_count() -> int:
    try:
        r = subprocess.run(["pgrep", "-af", "python.*qsb"], text=True,
                            capture_output=True, timeout=2)
        return sum(1 for ln in r.stdout.splitlines()
                    if "qsb" in ln and "grep" not in ln)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return -1


def _proc_alive(pat: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", pat], text=True,
                            capture_output=True, timeout=2)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _floor_status_map() -> dict[int, dict]:
    """Per-floor: {status, workers, last_tick}."""
    out: dict[int, dict] = {}
    # F25 / F31 / F38 — read their tick logs (last hour = working)
    for fn, path in TICK_LOG_BY_FLOOR.items():
        rows = _recent_jsonl(path, 3600)
        recent = len(rows)
        last_ts = rows[-1]["ts"] if rows else None
        alive = _proc_alive(f"qsb_f{fn:02d}_")
        any_err = any("fail" in str(r).lower() or "error" in str(r).lower()
                       for r in rows)
        status = "blocked" if any_err else ("working" if recent > 0 else
                                             ("idle" if alive else "paper_only"))
        out[fn] = {"status": status, "workers": 0, "last_tick": last_ts,
                    "recent_rows": recent}
    # F47 — workshop bench — read F47 records (last hour)
    f47_path = REGISTRIES / "qsb_f47_team_records.jsonl"
    f47_recent = _recent_jsonl(f47_path, 3600)
    out[47] = {"status": "working" if f47_recent else "idle",
                "workers": 0,
                "last_tick": f47_recent[-1]["ts"] if f47_recent else None}
    # F0 reception — heartbeat alive
    out[0] = {"status": "idle" if _proc_alive("qsb_telegram_receptionist") else "blocked",
              "workers": 0,
              "last_tick": None}
    # F41 OANDA — alive if module imports recently
    return out


def _floor_worker_counts() -> dict[int, int]:
    """Map floor number -> registered worker count using roster JSONs."""
    counts: dict[int, int] = {}
    for fp in REGISTRIES.glob("qsb_f*_roster.json"):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
            n = None
            for ch in fp.stem.replace("qsb_f", "").replace("_roster", ""):
                if ch.isdigit():
                    n = (n or 0) * 10 + int(ch)
                else:
                    break
            workers = d.get("workers") or []
            if n is not None and workers:
                counts[n] = counts.get(n, 0) + len(workers)
        except (OSError, ValueError):
            continue
    return counts


def _fetch_dashboard(path: str, timeout: float = 2.0) -> dict | None:
    """Proxy to the existing dashboard server endpoints at :8765."""
    try:
        req = urllib.request.Request(f"{DASHBOARD_BASE}{path}",
                                       headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None


def state_payload() -> dict:
    """SINGLE SOURCE OF TRUTH = the existing dashboard at :8765.

    Tries dashboard endpoints first; falls back to local tick-log derivation
    only when the dashboard is unreachable.
    """
    floors = _list_floors()
    procs = _live_procs_count()

    # ── Primary: pull from existing /api/* surfaces ────────────────
    audit = _fetch_dashboard("/api/audit/status") or {}
    worker_sources = _fetch_dashboard("/api/debug/worker_count_sources") or {}
    by_floor = _fetch_dashboard("/api/workers/by_floor") or {}
    team_live = _fetch_dashboard("/api/team/live") or {}

    workers_registered = (
        worker_sources.get("preferred_count_for_ui")
        or worker_sources.get("canonical_count")
        or 0
    )

    # Read worker counts per floor from /api/workers/by_floor if present.
    by_floor_data = (by_floor.get("by_floor") or by_floor.get("floors")
                      or by_floor.get("directory") or {})
    worker_counts: dict[int, int] = {}
    if isinstance(by_floor_data, dict):
        for k, v in by_floor_data.items():
            try:
                fn = int(str(k).lstrip("Ff").lstrip("0") or "0")
            except ValueError:
                continue
            if isinstance(v, list):
                worker_counts[fn] = len(v)
            elif isinstance(v, int):
                worker_counts[fn] = v
    # Fallback: derive from local roster JSONs
    if not worker_counts:
        worker_counts = _floor_worker_counts()

    # Per-floor status: keep local derivation (the dashboard doesn't surface
    # a per-floor ticking-status; this is value cockpit3d genuinely adds).
    status = _floor_status_map()

    # Most-recent activity ts from team_live (proxied) or fallback to local
    last_ts = None
    events = team_live.get("events_tail") or []
    if events:
        last_ts = events[-1].get("ts")
    if not last_ts and ACTIVITY_TAIL.exists():
        try:
            with ACTIVITY_TAIL.open("rb") as f:
                f.seek(max(0, ACTIVITY_TAIL.stat().st_size - 2048))
                lines = f.read().decode("utf-8", "ignore").splitlines()
                for ln in reversed(lines):
                    if ln.strip():
                        try:
                            last_ts = json.loads(ln).get("ts")
                            break
                        except ValueError:
                            pass
        except OSError:
            pass

    out_floors = []
    for fn in sorted(floors):
        s = status.get(fn) or {"status": "paper_only", "workers": 0, "last_tick": None}
        out_floors.append({
            "floor": fn,
            "name": floors[fn],
            "status": s["status"],
            "workers": worker_counts.get(fn, s.get("workers", 0)),
            "last_tick": s.get("last_tick"),
        })

    return {
        "totals": {
            "floors_registered": len(floors),
            "workers_registered": workers_registered,
            "live_procs": procs,
            "last_activity_ts": last_ts,
            "audit_overall_score": audit.get("overall_score"),
            "audit_critical_count": audit.get("critical_count"),
            "source": ("dashboard:" + DASHBOARD_BASE
                        if (audit or worker_sources) else "local_fallback"),
        },
        "floors": out_floors,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        log.info("%s - %s", self.address_string(), fmt % a)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/cockpit3d.html"):
            return self._static("cockpit3d.html", "text/html; charset=utf-8")
        if self.path == "/api/floor_states":
            return self._json(state_payload())
        if self.path == "/api/health":
            return self._json({"ok": True, "service": "qsb_cockpit3d"})
        return self._json({"ok": False, "error": "not_found"}, status=404)

    def _static(self, name: str, mime: str) -> None:
        p = STATIC_DIR / name
        if not p.exists():
            return self._json({"ok": False, "error": f"missing {name}"}, status=404)
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("serving cockpit3d on http://%s:%d/", HOST, PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
