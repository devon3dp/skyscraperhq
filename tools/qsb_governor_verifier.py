#!/usr/bin/env python3
"""
QSB GOVERNOR VERIFIER  (action_id=WREN-GOVERNOR-V1, Phase 5)

Deterministic fact-checker used by Wren to verify Claude's claims. It checks FACTS,
never prose, and it never makes a final acceptance decision — it returns facts to Wren.
Claude HQ may NOT modify this file during a governed Claude task (SAFETY_DENY).

Each check returns one of: PASS FAIL PARTIAL STALE NOT_TESTED BLOCKED
plus the evidence used, so Wren (and Ross) can see exactly why.

CLI:
  python3 tools/qsb_governor_verifier.py --check endpoint --url http://192.168.1.74:8871 --expect-id tp_pip --kind physical
  python3 tools/qsb_governor_verifier.py --check physical_vs_surrogate --worker tp_pip
  python3 tools/qsb_governor_verifier.py --check stale_registration --worker tp_pip
  python3 tools/qsb_governor_verifier.py --check one_owner --port 8851
  python3 tools/qsb_governor_verifier.py --check compile --file tools/qsb_boardroom_hub.py
  python3 tools/qsb_governor_verifier.py --check secret_scan --file <path>
  python3 tools/qsb_governor_verifier.py --check forbidden_changes --files a.py,b.py
"""
import argparse, json, re, socket, subprocess, urllib.request, hashlib, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data/registries"
PHYSICAL = {"tp_pip": "http://192.168.1.74:8871", "acer_cass": "http://192.168.1.78:8872"}
SURROGATE = {"tp_pip": "http://127.0.0.1:8861", "acer_cass": "http://127.0.0.1:8862"}
RETIRED = {"acer_cass": "http://192.168.1.41:8872"}   # historical/dead — must NOT be current truth
HOSTNAMES = {"tp_pip": "DESKTOP-9RBVKSM", "acer_cass": "DESKTOP-1E2FB5N"}
SAFETY_DENY = ["CLAUDE.md", "config/wren_governor_policy.yaml", "tools/qsb_governor_verifier.py",
               "floors/floor_28_security_department/vault/", ".env"]
SECRET_RX = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY|password\s*[:=]\s*\S+)", re.I)


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _res(check, result, evidence, **extra):
    return {"check": check, "result": result, "evidence": evidence, "ts": _utc(), **extra}


def _http(url, path="", timeout=3):
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=timeout) as r:
            return r.status, r.read(2048).decode("utf-8", "replace")
    except Exception as e:
        return 0, type(e).__name__ + ":" + str(e)[:80]


def check_endpoint(url, expect_id=None, kind="physical"):
    code, body = _http(url, "/whoami") if _http(url, "/health")[0] == 0 else _http(url, "/health")
    if code == 0:
        code, body = _http(url, "/whoami")
    if code == 0:
        return _res("endpoint", "FAIL", "no HTTP response from %s: %s" % (url, body), url=url)
    m = re.search(r'"(?:id|runtime_id)"\s*:\s*"([^"]+)"', body)
    host = re.search(r'"hostname"\s*:\s*"([^"]+)"', body)
    got_id = m.group(1) if m else None
    hq_hosted = '"hq_hosted": true' in body or '"hq_hosted":true' in body
    result = "PASS"
    notes = []
    if expect_id and got_id != expect_id:
        result = "FAIL"; notes.append("id %s != expected %s" % (got_id, expect_id))
    if kind == "physical" and hq_hosted:
        result = "FAIL"; notes.append("hq_hosted=true — this is a SURROGATE, not physical")
    if kind == "surrogate" and not hq_hosted and "127.0.0.1" not in url:
        notes.append("surrogate flag not set")
    return _res("endpoint", result, "HTTP %d id=%s host=%s hq_hosted=%s %s" % (code, got_id, host.group(1) if host else "?", hq_hosted, ";".join(notes)),
                url=url, got_id=got_id, kind=kind)


def check_physical_vs_surrogate(worker):
    phys = check_endpoint(PHYSICAL.get(worker, ""), expect_id=worker, kind="physical")
    surr = check_endpoint(SURROGATE.get(worker, ""), expect_id=worker, kind="surrogate")
    distinct = PHYSICAL.get(worker, "a").split("//")[-1] != SURROGATE.get(worker, "b").split("//")[-1]
    result = "PASS" if distinct and phys["result"] != "FAIL" else "PARTIAL"
    if phys["result"] == "FAIL":
        result = "FAIL"
    return _res("physical_vs_surrogate", result,
                "physical(%s)=%s ; surrogate(%s)=%s ; distinct=%s ; surrogate must NOT be shown as physical" % (
                    PHYSICAL.get(worker), phys["result"], SURROGATE.get(worker), surr["result"], distinct),
                physical=phys, surrogate=surr)


def check_retired(worker):
    """A deliberately supplied stale/historical endpoint MUST be rejected as current truth."""
    url = RETIRED.get(worker)
    if not url:
        return _res("retired_endpoint", "NOT_TESTED", "no retired endpoint recorded for %s" % worker)
    code, body = _http(url, "/health")
    if code == 0:
        return _res("retired_endpoint", "STALE", "RETIRED endpoint %s is DEAD (%s) — correctly NOT current truth" % (url, body), url=url)
    return _res("retired_endpoint", "FAIL", "RETIRED endpoint %s unexpectedly answered — investigate" % url, url=url)


def check_stale_registration(worker, ttl=180):
    p = REG / "qsb_physical_workers_current.json"
    if not p.exists():
        return _res("stale_registration", "NOT_TESTED", "registry file missing")
    try:
        w = json.loads(p.read_text()).get("workers", {}).get(worker)
    except Exception as e:
        return _res("stale_registration", "BLOCKED", "registry unreadable: %s" % e)
    if not w:
        return _res("stale_registration", "NOT_TESTED", "%s not registered" % worker)
    try:
        age = time.time() - datetime.fromisoformat((w.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return _res("stale_registration", "BLOCKED", "bad timestamp")
    if age < ttl:
        return _res("stale_registration", "PASS", "heartbeat age %ds < TTL %ds (FRESH)" % (int(age), ttl), age_s=int(age), source_ip=w.get("source_ip"))
    return _res("stale_registration", "STALE", "heartbeat age %ds >= TTL %ds — LAST ENDPOINT STALE, not current" % (int(age), ttl), age_s=int(age))


def check_one_owner(port):
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=5).stdout
        n = sum(1 for l in out.splitlines() if (":%s " % port) in l)
        return _res("one_owner", "PASS" if n == 1 else ("FAIL" if n > 1 else "FAIL"),
                    "port %s has %d listener(s) (want exactly 1)" % (port, n), count=n)
    except Exception as e:
        return _res("one_owner", "BLOCKED", str(e))


def check_compile(fp):
    p = ROOT / fp
    if not p.exists():
        return _res("compile", "FAIL", "file missing: %s" % fp)
    try:
        import py_compile
        py_compile.compile(str(p), doraise=True)
        return _res("compile", "PASS", "%s compiles" % fp)
    except Exception as e:
        return _res("compile", "FAIL", "%s: %s" % (fp, str(e)[:120]))


def check_file(fp, before_sha=None):
    p = ROOT / fp
    if not p.exists():
        return _res("file", "FAIL", "missing: %s" % fp)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if before_sha and sha == before_sha:
        return _res("file", "PARTIAL", "%s UNCHANGED (sha matches before) — claim of edit unsupported" % fp, sha=sha)
    return _res("file", "PASS", "%s exists sha=%s" % (fp, sha[:16]), sha=sha)


def check_secret_scan(fp):
    p = ROOT / fp
    if not p.exists():
        return _res("secret_scan", "NOT_TESTED", "missing: %s" % fp)
    hits = SECRET_RX.findall(p.read_text(errors="ignore"))
    return _res("secret_scan", "FAIL" if hits else "PASS", "%d secret-pattern hit(s)" % len(hits))


def check_forbidden_changes(files):
    bad = [f for f in files if any(f.strip().startswith(d) or d in f for d in SAFETY_DENY)]
    return _res("forbidden_changes", "FAIL" if bad else "PASS",
                ("SAFETY_DENY paths touched: " + ", ".join(bad)) if bad else "no forbidden paths changed", forbidden=bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True)
    ap.add_argument("--url", default=""); ap.add_argument("--expect-id", default=None); ap.add_argument("--kind", default="physical")
    ap.add_argument("--worker", default=""); ap.add_argument("--port", default=""); ap.add_argument("--file", default="")
    ap.add_argument("--files", default=""); ap.add_argument("--before-sha", default=None)
    a = ap.parse_args()
    c = a.check
    if c == "endpoint": r = check_endpoint(a.url, a.expect_id, a.kind)
    elif c == "physical_vs_surrogate": r = check_physical_vs_surrogate(a.worker)
    elif c == "retired_endpoint": r = check_retired(a.worker)
    elif c == "stale_registration": r = check_stale_registration(a.worker)
    elif c == "one_owner": r = check_one_owner(a.port)
    elif c == "compile": r = check_compile(a.file)
    elif c == "file": r = check_file(a.file, a.before_sha)
    elif c == "secret_scan": r = check_secret_scan(a.file)
    elif c == "forbidden_changes": r = check_forbidden_changes(a.files.split(","))
    else: r = _res(c, "NOT_TESTED", "unknown check")
    print(json.dumps(r))


if __name__ == "__main__":
    main()
