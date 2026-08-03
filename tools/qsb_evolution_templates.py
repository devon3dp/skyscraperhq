#!/usr/bin/env python3
"""qsb_evolution_templates.py — GOVERNED evolution task-intake templates (Phase 8).

SkyscraperHQ evolution work (floor health, floor fit-out, online shop) must enter
the REPAIRED Task Council (qsb_council_tasks.py) through the SAME governance every
other task obeys — never around it. This module builds and validates the INTAKE for
three evolution categories and hands the result to the existing reducer. It does NOT
create live tasks itself, and it adds NO new completion path.

Design contract (all enforced by ROUTING THROUGH qsb_council_tasks, never bypassing):
  · intake-completeness gate  -> _intake_assess (affected_component+evidence+DoD)
  · deterministic dedup       -> _dedup_key / _find_open_dup
  · active-board cap (<=20)    -> create() overflow -> reserve
  · per-CEO cap (<=3) / global WIP -> claim/assign downstream (GATE17/GATE18)
  · two physical CEOs + independent verifier -> assignment + peer_signoff
  · completion proof gate      -> done() needs non-builder verifier + fresh proof

Category-specific rules ADDED ON TOP of governance (never in place of it):
  A. floor_health  — a REAL evidence-gathering function classifies a floor
                     functional/partial/narrative-only/dormant from live signals.
  B. floor_fitout  — intake must define OPERATIONAL capability (backend + live data
                     + service registration + dashboard + transport + persistence +
                     acceptance tests + maintenance owner + independent verification).
                     A visual shell alone is REJECTED as incomplete.
  C. online_shop   — full commerce field set + a HARD Ross-approval gate: a shop task
                     may not reach public launch / payment activation / account
                     creation without an explicit Ross authorization.

This module is READ-ONLY against the live board: generation + validation are dry-run.
Proof of governance routing is done on a COPY of the reducer (temp LOG/SNAPSHOT).
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
FLOORS_DIR = ROOT / "floors"
TEMPLATE_DIR = ROOT / "data/registries/evolution_templates"
CENSUS = Path("/home/ross/Desktop/QSB_CONTROL_RUNS/"
              "20260731T104232Z_SKYSCRAPERHQ_EVOLUTION_TRUTH_CENSUS/"
              "02_FLOORS_1-170_CENSUS.md")

CATEGORIES = ("floor_health", "floor_fitout", "online_shop")

# Words that, if the shop scope touches them, force the Ross-approval hard gate.
_LAUNCH_TRIGGERS = ("public launch", "go live", "go-live", "payment activation",
                    "activate payment", "account creation", "create account",
                    "real transaction", "real money", "publish domain", "production",
                    "charge customer", "live payment", "checkout live")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ─────────────────────────── template loading ───────────────────────────
def load_template(category: str) -> dict:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; expected one of {CATEGORIES}")
    p = TEMPLATE_DIR / f"{category}.template.json"
    return json.loads(p.read_text())


def all_templates() -> dict:
    return {c: load_template(c) for c in CATEGORIES}


# ─────────────────────── floor identity resolution ──────────────────────
def _canonical_floor_dirs(floor_number: int) -> list[Path]:
    """Every on-disk floor_* directory whose leading number == floor_number.
    More than one => duplicate/anomaly (real signal for dedup + fit-out check)."""
    out = []
    if not FLOORS_DIR.is_dir():
        return out
    for d in sorted(FLOORS_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r'floor_(\d{1,3})(?:_|$)', d.name)
        if m and int(m.group(1)) == floor_number:
            out.append(d)
    return out


def resolve_floor(selector) -> dict:
    """Selector = int floor number OR a name/substring. Returns identity info."""
    num = None
    if isinstance(selector, int):
        num = selector
    else:
        s = str(selector).strip()
        m = re.match(r'^(?:floor[_ ]?)?(\d{1,3})$', s, re.I)
        if m:
            num = int(m.group(1))
        else:
            # name substring search
            for d in sorted(FLOORS_DIR.iterdir()):
                if d.is_dir() and s.lower() in d.name.lower():
                    mm = re.match(r'floor_(\d{1,3})', d.name)
                    if mm:
                        num = int(mm.group(1))
                        break
    if num is None:
        return {"resolved": False, "selector": selector,
                "error": "could not resolve selector to a floor number"}
    dirs = _canonical_floor_dirs(num)
    card = {}
    if dirs:
        cp = dirs[0] / "floor_card.json"
        if cp.exists():
            try:
                card = json.loads(cp.read_text())
            except Exception:
                card = {}
    name = (card.get("floor_name") or (dirs[0].name if dirs else f"floor_{num}"))
    return {"resolved": True, "floor_number": num, "floor_name": name,
            "dirs": [str(d) for d in dirs],
            "duplicate_dirs": len(dirs) > 1,
            "card_present": bool(card), "card": card}


# ─────────────────────── REAL floor evidence gather ─────────────────────
def _systemd_units() -> list[str]:
    try:
        out = subprocess.run(["systemctl", "list-units", "qsb-*", "--all",
                              "--no-legend", "--plain", "--no-pager"],
                             capture_output=True, text=True, timeout=15).stdout
        return [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []


def _unit_state(unit: str) -> dict:
    st = {"unit": unit}
    try:
        r = subprocess.run(["systemctl", "show", unit, "--no-pager",
                            "-p", "ActiveState,SubState,UnitFileState"],
                           capture_output=True, text=True, timeout=10).stdout
        for ln in r.splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                st[k] = v
    except Exception:
        pass
    return st


def _floor_name_tokens(floor_number: int, floor_name: str, dirname: str) -> set:
    toks = set()
    for src in (floor_name or "", dirname or ""):
        src = re.sub(r'floor[_ ]?\d+', ' ', src.lower())
        for t in re.findall(r'[a-z]{4,}', src):
            if t not in ("floor", "department", "operations", "services", "office"):
                toks.add(t)
    return toks


def _map_services(floor_number: int, floor_name: str, dirname: str,
                  units: list[str]) -> dict:
    """Map floor -> systemd unit(s), separating STRONG bindings (unit name literally
    carries floorNN / fNN — an unambiguous floor->service link) from WEAK bindings
    (a fuzzy floor-name token appears in the unit name). A WEAK-only match is NOT
    proof the service belongs to this floor, so it must never alone promote a floor
    to 'functional' (that is what falsely flagged narrative floor 0 as live)."""
    toks = _floor_name_tokens(floor_number, floor_name, dirname)
    strong, weak = [], []
    for u in units:
        lu = u.lower()
        if re.search(rf'floor[-_]?{floor_number}\b', lu) or re.search(rf'\bf{floor_number}\b', lu):
            strong.append(u); continue
        for t in toks:
            if t in lu:
                weak.append(u); break
    return {"strong": sorted(set(strong)), "weak": sorted(set(weak)),
            "all": sorted(set(strong) | set(weak))}


def _curl_local(url: str) -> dict:
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "--max-time", "4", url],
                           capture_output=True, text=True, timeout=8)
        code = (r.stdout or "").strip()
        return {"url": url, "http_code": code, "ok": code.startswith("2")}
    except Exception as e:
        return {"url": url, "http_code": None, "ok": False, "error": str(e)[:80]}


def _freshness(evidence_paths: list) -> list[dict]:
    out = []
    now = time.time()
    for rel in (evidence_paths or [])[:8]:
        p = ROOT / rel
        if p.exists():
            age_h = round((now - p.stat().st_mtime) / 3600.0, 2)
            out.append({"path": rel, "exists": True, "age_hours": age_h,
                        "fresh": age_h < 24})
        else:
            out.append({"path": rel, "exists": False})
    return out


def _backing_code(floor_number: int, toks: set) -> list[str]:
    """src/tower(_ops) modules referencing this floor number or a name token."""
    hits = []
    for base in ("src/tower", "src/tower_ops"):
        d = ROOT / base
        if not d.is_dir():
            continue
        for f in d.rglob("*.py"):
            ln = f.name.lower()
            if re.search(rf'floor[_]?{floor_number}\b', ln):
                hits.append(str(f.relative_to(ROOT)))
    return sorted(set(hits))


_CENSUS_CACHE = {}


def _census_sets() -> dict:
    """Reuse the existing floor census (do NOT re-census) as an honesty ANCHOR:
    the set of floor numbers the census already verified LIVE / PRESENT. Live signals
    still drive classification; the census corroborates a weak service match and
    guards against promoting a floor the census judged narrative."""
    if _CENSUS_CACHE:
        return _CENSUS_CACHE
    live, present = set(), set()
    try:
        txt = CENSUS.read_text()
        # VERIFIED LIVE table rows: | 24 | Gene Pool | ...
        in_live = in_present = False
        for ln in txt.splitlines():
            if ln.startswith("## VERIFIED LIVE"):
                in_live, in_present = True, False; continue
            if ln.startswith("## VERIFIED PRESENT"):
                in_live, in_present = False, True; continue
            if ln.startswith("## NARRATIVE") or ln.startswith("## VACANT"):
                in_live = in_present = False; continue
            if in_live:
                m = re.match(r'\|\s*(\d{1,3})\s*\|', ln)
                if m:
                    live.add(int(m.group(1)))
            if in_present:
                for n in re.findall(r'\bF(\d{1,3})\b', ln):
                    present.add(int(n))
    except Exception:
        pass
    _CENSUS_CACHE.update({"live": live, "present": present})
    return _CENSUS_CACHE


def gather_floor_evidence(selector) -> dict:
    """REAL, live signals for one floor. No trust of card self-report."""
    ident = resolve_floor(selector)
    ev = {"gathered_at": utc(), "selector": selector, "identity": ident}
    if not ident.get("resolved"):
        ev["error"] = ident.get("error")
        return ev
    num = ident["floor_number"]
    name = ident["floor_name"]
    dirname = Path(ident["dirs"][0]).name if ident["dirs"] else ""
    card = ident.get("card", {})

    # (1) canonical identity
    ev["canonical_identity"] = {
        "floor_number": num, "floor_name": name,
        "on_disk": bool(ident["dirs"]), "duplicate_dirs": ident["duplicate_dirs"],
        "card_present": ident["card_present"],
        "card_skeleton": card.get("skeleton"),
        "card_advisory_only": card.get("advisory_only"),
    }

    # census anchor (reuse — do NOT re-census)
    cen = _census_sets()
    ev["census"] = {"verified_live": num in cen.get("live", set()),
                    "verified_present": num in cen.get("present", set())}

    # (2) service status + (6) startup persistence
    units = _systemd_units()
    toks = _floor_name_tokens(num, name, dirname)
    mp = _map_services(num, name, dirname, units)
    mapped = mp["all"]
    svc = [_unit_state(u) for u in mapped]
    strong_active = any(s.get("ActiveState") == "active"
                        for s in svc if s["unit"] in mp["strong"])
    weak_active = any(s.get("ActiveState") == "active"
                      for s in svc if s["unit"] in mp["weak"])
    ev["service_status"] = {
        "mapped_units": mapped,
        "strong_units": mp["strong"], "weak_units": mp["weak"],
        "states": svc,
        "any_active": any(s.get("ActiveState") == "active" for s in svc),
        "strong_active": strong_active, "weak_active": weak_active,
    }
    ev["startup_persistence"] = {
        "any_enabled": any(s.get("UnitFileState") in ("enabled", "enabled-runtime")
                           for s in svc),
        "unit_file_states": {s["unit"]: s.get("UnitFileState") for s in svc},
    }

    # (3) endpoint health (localhost only, read-only)
    endpoints = card.get("endpoints") or []
    port = None
    for u in svc:
        pass
    checks = []
    # try explicit ports mentioned in card live_signals / endpoints
    ports = set(re.findall(r':(\d{4,5})\b', json.dumps(card)))
    for p in sorted(ports)[:4]:
        checks.append(_curl_local(f"http://127.0.0.1:{p}/"))
    ev["endpoint_health"] = {"declared_endpoints": endpoints,
                             "probed_ports": sorted(ports),
                             "checks": checks,
                             "any_2xx": any(c.get("ok") for c in checks)}

    # (4) data freshness
    ev["data_freshness"] = {"evidence_paths": _freshness(card.get("evidence_paths"))}

    # (5) dependency status (backing code)
    code = _backing_code(num, toks)
    ev["dependency_status"] = {"backing_code_modules": code,
                               "has_backing_code": bool(code)}

    # (7) logs
    log_lines = []
    if mapped:
        try:
            r = subprocess.run(["journalctl", "-u", mapped[0], "-n", "3",
                                "--no-pager", "-o", "cat"],
                               capture_output=True, text=True, timeout=10)
            log_lines = [l for l in (r.stdout or "").splitlines() if l.strip()][-3:]
        except Exception:
            pass
    ev["logs"] = {"unit": mapped[0] if mapped else None, "tail": log_lines}
    return ev


def classify_floor(ev: dict) -> dict:
    """Honest classification from REAL evidence. A WEAK (fuzzy name-token) service
    match never alone makes a floor 'functional' — that requires a STRONG floor-bound
    service, a 2xx on a floor-DECLARED port, or census corroboration of the weak match.
      functional     : strong-bound active service OR declared-port 2xx OR
                       (census-verified-live AND a weak service is active now).
      dormant        : a strong-bound service exists but is not active (real, now down).
      partial        : backing code / census-present, but nothing actively serving.
      narrative-only : no floor-bound service, no code, not census-backed — shell only
                       (a weak service name-match is noted but not treated as this floor)."""
    if not ev.get("identity", {}).get("resolved"):
        return {"classification": "unknown", "why": ev.get("error", "unresolved")}
    svc = ev.get("service_status", {})
    strong_active = svc.get("strong_active")
    weak_active = svc.get("weak_active")
    strong_units = svc.get("strong_units") or []
    weak_units = svc.get("weak_units") or []
    has_code = ev.get("dependency_status", {}).get("has_backing_code")
    ep2xx = ev.get("endpoint_health", {}).get("any_2xx")
    fresh_list = [f for f in ev.get("data_freshness", {}).get("evidence_paths", [])
                  if f.get("exists")]
    any_fresh = any(f.get("fresh") for f in fresh_list)
    cen_live = ev.get("census", {}).get("verified_live")
    cen_present = ev.get("census", {}).get("verified_present")

    if strong_active or ep2xx or (cen_live and weak_active):
        cls = "functional"
        bind = ("/".join(strong_units) if strong_active else
                (f"declared-port 2xx" if ep2xx else
                 f"census-live + active {'/'.join(weak_units)}"))
        why = (f"functional binding: {bind}"
               + (", fresh data" if any_fresh else
                  (", data stale" if fresh_list else "")))
    elif strong_units and not strong_active:
        cls = "dormant"
        why = f"floor-bound service exists but not active: {'/'.join(strong_units)}"
    elif has_code or cen_present:
        cls = "partial"
        why = ("backing code / census-present but nothing actively serving"
               + (", data fresh" if any_fresh else ""))
    else:
        cls = "narrative-only"
        why = "no floor-bound service, no backing code, not census-backed — card/render shell only"
        if ev["canonical_identity"].get("card_skeleton") or ev["canonical_identity"].get("card_advisory_only"):
            why += " (card advertises skeleton/advisory)"
        if weak_active:
            why += (f"; NOTE a running service name-matches ({'/'.join(weak_units)}) "
                    "but is NOT floor-bound — not counted as this floor's")
    return {"classification": cls, "why": why,
            "signals": {"strong_service_active": bool(strong_active),
                        "weak_service_active": bool(weak_active),
                        "endpoint_2xx": bool(ep2xx),
                        "backing_code": bool(has_code),
                        "census_verified_live": bool(cen_live),
                        "census_verified_present": bool(cen_present),
                        "fresh_data": bool(any_fresh)}}


# ─────────────────────── intake completeness embed ──────────────────────
def _embed_gate_markers(affected: str, evidence: str, dod: str) -> str:
    """Assemble a description block that SATISFIES the reducer's intake gate
    (_intake_assess needs affected_component + evidence + definition_of_done).
    We do not weaken the gate; we author intakes that legitimately carry all three."""
    return (f"Affected: {affected}\n"
            f"Evidence (observed): {evidence}\n"
            f"Definition of done (acceptance) — done when: {dod}")


# ─────────────────────── category intake validation ─────────────────────
def _nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return len(v.strip()) >= 3
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def validate_intake(category: str, fields: dict) -> dict:
    """Category-specific completeness. Returns {ok, missing[], reasons[], gates[]}.
    This is IN ADDITION TO the reducer's own intake gate — it never replaces it."""
    tpl = load_template(category)
    missing, reasons, gates = [], [], []
    for f in tpl.get("required_fields", []):
        if not _nonempty(fields.get(f)):
            missing.append(f)

    if category == "floor_fitout":
        cap = fields.get("operational_capability") or {}
        if not isinstance(cap, dict):
            reasons.append("operational_capability must be an object of subfields")
            missing.append("operational_capability")
        else:
            for sub in tpl["operational_capability_subfields"]:
                if not _nonempty(cap.get(sub)):
                    missing.append(f"operational_capability.{sub}")
            # A visual-shell-only intake is exactly one that lacks backend+live_data+service.
            shell_only = (not _nonempty(cap.get("backend"))
                          or not _nonempty(cap.get("live_data"))
                          or not _nonempty(cap.get("service_registration")))
            if shell_only:
                reasons.append("VISUAL-SHELL-ONLY REJECTED: a fit-out needs backend + "
                               "live_data + service_registration, not just a 3D shell.")

    if category == "online_shop":
        gate = _shop_launch_gate(fields)
        gates.append(gate)
        if gate["launch_scope"] and not gate["approved"]:
            reasons.append("HARD GATE: shop scope touches public launch / payment "
                           "activation / account creation without Ross approval — "
                           "refused. Build/test-env only until Ross authorizes.")

    ok = (len(missing) == 0
          and not any(g.get("launch_scope") and not g.get("approved") for g in gates))
    return {"ok": ok, "category": category, "missing": missing,
            "reasons": reasons, "gates": gates}


def _shop_launch_gate(fields: dict) -> dict:
    """Detect whether the shop intake scope crosses into launch/payment/account, and
    whether an explicit Ross approval is present."""
    scope_text = " ".join(str(fields.get(k, "")) for k in
                          ("scope", "business_purpose", "payment_architecture",
                           "phase", "milestone", "deploy", "launch")).lower()
    launch_scope = any(t in scope_text for t in _LAUNCH_TRIGGERS)
    ra = fields.get("ross_approval")
    approved = bool(_nonempty(ra) and str(ra).strip().lower() not in
                    ("false", "no", "pending", "none"))
    return {"gate": "ross_launch_approval", "launch_scope": launch_scope,
            "approved": approved,
            "note": ("launch-scoped intake requires ross_approval token"
                     if launch_scope else "build/test-env scope — Ross gate dormant")}


# ─────────────────────── build council intake ───────────────────────────
def build_council_intake(category: str, fields: dict) -> dict:
    """Turn validated fields into a {title, description, tags} council intake that
    passes the reducer's intake-completeness gate. REFUSES (raises) when the
    category validation fails — so an incomplete or launch-scoped-unapproved intake
    can NEVER be minted into a council task."""
    v = validate_intake(category, fields)
    if not v["ok"]:
        return {"ok": False, "refused": True, "category": category,
                "missing": v["missing"], "reasons": v["reasons"], "gates": v["gates"]}
    tpl = load_template(category)

    if category == "floor_health":
        fn = fields.get("floor_number", "?")
        name = fields.get("floor_name", fields.get("floor_selector", "?"))
        cls = fields.get("classification", "unassessed")
        title = tpl["intake_builder"]["title_fmt"].format(
            floor_name=name, floor_number=fn, classification=cls)
        affected = f"floor_{fn} ({name}); floors/ registry + mapped service/registries"
        evidence = fields.get("reason_for_assessment") or fields.get("evidence_summary") \
            or f"live signal scan classified floor {fn} as {cls}"
        dod = ("real evidence gathered for all seven signal classes, an honest "
               "classification recorded, and any remediation verified by an "
               "independent non-builder verifier via the proof gate")

    elif category == "floor_fitout":
        fn = fields.get("canonical_floor_selection", {}).get("floor_number", "?") \
            if isinstance(fields.get("canonical_floor_selection"), dict) \
            else fields.get("floor_number", "?")
        name = fields.get("floor_name", "?")
        title = tpl["intake_builder"]["title_fmt"].format(
            floor_name=name, floor_number=fn)
        cap = fields["operational_capability"]
        affected = f"floor_{fn} ({name}); backend={cap.get('backend')}; " \
                   f"service={cap.get('service_registration')}"
        evidence = f"real_need: {fields.get('real_need')}; existing-floor inspection: " \
                   f"{fields.get('existing_floor_inspection')}"
        dod = ("floor OPERATIONAL — backend runs, live_data written, service registered "
               "& startup-persistent, dashboard reflects real data, transport link, "
               "state persists across restart, acceptance tests pass, maintenance owner "
               f"named ({cap.get('maintenance_owner')}), independent verifier confirms "
               "via proof gate. Visual shell alone does NOT satisfy done.")

    else:  # online_shop
        prod = fields.get("product", "?")
        bp = str(fields.get("business_purpose", ""))[:48]
        title = tpl["intake_builder"]["title_fmt"].format(
            product=prod, business_purpose_short=bp)
        affected = f"commerce floor / storefront; product={prod}; " \
                   f"hosting={fields.get('hosting')}; payment={fields.get('payment_architecture')}"
        evidence = f"business_purpose: {fields.get('business_purpose')}; owner: " \
                   f"{fields.get('owner')}; test_env: {fields.get('test_env')}"
        dod = ("BUILD/TEST-ENV done: catalogue, inventory, pricing, TEST-MODE payment, "
               "privacy/terms/refund/support docs, security+hosting+analytics plan, "
               "acceptance tests pass, independent verifier confirms via proof gate. "
               "PUBLIC LAUNCH / PAYMENT ACTIVATION / ACCOUNT CREATION remain a SEPARATE "
               "Ross-approved step, NOT part of build done.")

    description = _embed_gate_markers(affected, evidence, dod)
    return {"ok": True, "category": category, "title": title,
            "description": description, "tags": tpl["intake_builder"]["tags"],
            "validation": v}


# ─────────── floor-health task generation from LIVE evidence ─────────────
def generate_floor_health_task(selector, reason_for_assessment: str = "") -> dict:
    """Gather REAL evidence for a floor, classify honestly, and build the council
    intake — WITHOUT admitting it to the live board (dry-run). Returns everything a
    council would need to admit it through normal governance."""
    ev = gather_floor_evidence(selector)
    cls = classify_floor(ev)
    fields = {
        "floor_selector": selector,
        "floor_number": ev.get("identity", {}).get("floor_number"),
        "floor_name": ev.get("identity", {}).get("floor_name"),
        "classification": cls.get("classification"),
        "reason_for_assessment": reason_for_assessment
            or f"scheduled health scan: classified {cls.get('classification')} — {cls.get('why')}",
        "evidence_summary": cls.get("why"),
    }
    intake = build_council_intake("floor_health", fields)
    return {"selector": selector, "evidence": ev, "classification": cls,
            "intake": intake, "admitted": False,
            "note": "DRY-RUN — intake built from live evidence, NOT created on live board."}


# ─────────── governance routing proof on a COPY of the reducer ───────────
def route_dry_run(intake: dict, tmpdir: str = None) -> dict:
    """Prove the built intake obeys the EXISTING governance without touching the live
    board: import qsb_council_tasks, point its LOG/SNAPSHOT at a temp copy, and run
    create()/done() there. Returns the reducer's real verdicts.

    This exercises the SAME code the live council uses — it is not a re-implementation.
    """
    if not intake.get("ok"):
        return {"routed": False, "reason": "intake refused by template validation",
                "detail": intake}
    import tempfile, importlib
    sys.path.insert(0, str(ROOT / "tools"))
    import qsb_council_tasks as C
    importlib.reload(C)
    td = Path(tmpdir or tempfile.mkdtemp(prefix="phase8_council_copy_"))
    orig_log, orig_snap = C.LOG, C.SNAPSHOT
    C.LOG = td / "copy_tasks.jsonl"
    C.SNAPSHOT = td / "copy_snapshot.json"
    try:
        # 1) create through the real reducer (dedup + intake gate + cap all run here)
        res = C.create(intake["title"], intake["description"],
                       actor="evolution_template_dryrun", tags=intake["tags"])
        # 2) prove the proof gate: done() with no verifier/proof must be REFUSED
        proof = None
        tid = res.get("task_id")
        if tid and res.get("state") in ("open", "reserved"):
            proof = C.done(tid, actor="evolution_template_dryrun",
                           summary="attempt to close with no verifier/proof")
        # 3) prove intake-gate directly on the text
        complete, missing = C._intake_assess(intake["title"], intake["description"],
                                              intake["tags"])
        return {"routed": True, "copy_dir": str(td),
                "create_result": res,
                "intake_gate_complete": complete, "intake_gate_missing": missing,
                "proof_gate_done_attempt": proof,
                "proof_gate_refused": bool(proof and not proof.get("ok")),
                "live_board_touched": False}
    finally:
        C.LOG, C.SNAPSHOT = orig_log, orig_snap


# ───────────────────────────────── CLI ──────────────────────────────────
def _p(x):
    print(json.dumps(x, indent=2, default=str))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Governed evolution task-intake templates")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list").set_defaults(cmd="list")

    g = sub.add_parser("floor-health")
    g.add_argument("selector")
    g.add_argument("--reason", default="")

    e = sub.add_parser("evidence")
    e.add_argument("selector")

    v = sub.add_parser("validate")
    v.add_argument("category", choices=CATEGORIES)
    v.add_argument("--fields", required=True, help="JSON fields")

    b = sub.add_parser("build")
    b.add_argument("category", choices=CATEGORIES)
    b.add_argument("--fields", required=True, help="JSON fields")
    b.add_argument("--route", action="store_true", help="dry-run route through reducer copy")

    args = ap.parse_args(argv)
    if args.cmd == "list":
        _p({c: {"title": t["title"], "required_fields": t["required_fields"],
                "hard_gates": [g.get("gate") for g in t.get("hard_gates", [])]}
            for c, t in all_templates().items()})
    elif args.cmd == "evidence":
        ev = gather_floor_evidence(args.selector)
        _p({"evidence": ev, "classification": classify_floor(ev)})
    elif args.cmd == "floor-health":
        _p(generate_floor_health_task(args.selector, args.reason))
    elif args.cmd == "validate":
        _p(validate_intake(args.category, json.loads(args.fields)))
    elif args.cmd == "build":
        intake = build_council_intake(args.category, json.loads(args.fields))
        out = {"intake": intake}
        if args.route:
            out["route"] = route_dry_run(intake)
        _p(out)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
