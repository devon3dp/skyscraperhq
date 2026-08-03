"""governor_act — Wren's PROACTIVE control loop (R01 honest, gate-respecting).

Governor upgrade (2026-07-30). Her old loop was survey -> observe -> book. This is
survey -> DECIDE -> DELEGATE -> FOLLOW-UP. In one call it:

  1. READS the real command deck (per-CEO load, global WIP, backlog, blocked, stale).
  2. FOLLOWS UP her own open delegations (surfaces which handoffs are still waiting
     / in-flight / done) so nothing she delegated is forgotten.
  3. DECIDES what a governor should actually do given the real state:
       · if the council is SATURATED at the WIP ceiling -> it does NOT pile on new
         work. It earmarks the highest-value work to the least-loaded worker as
         PENDING (via delegate_task, which the cap keeps honest) and reports the
         finish-first / unblock / reap recommendation. Nothing is forced.
       · if there is FREE WIP capacity -> it DELEGATES real work into the free
         slot(s): first any unowned OPEN backlog task (highest priority), else a
         fresh governor_scan finding turned into a new task — assigning it to the
         least-loaded online worker with a verifier and a relay ping.
  4. Every action goes through delegate_task, so every gate (per-CEO cap, global
     WIP ceiling) is respected and every handoff is logged. It flips no gate and
     forces nothing onto a jammed board.

max_actions bounds how many delegations it will make this tick (default 1, so the
loop stays deliberate). dry_run=True plans without delegating.
"""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / "skills/wren"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_skill(name):
    p = SKILLS / name / "skill.py"
    spec = importlib.util.spec_from_file_location(f"wren_skill_{name}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(max_actions: int = 1, dry_run: bool = False, notify: bool = True):
    deck_mod = _load_skill("command_deck")
    scan_mod = _load_skill("governor_scan")
    deleg_mod = _load_skill("delegate_task")

    deck = deck_mod.run()
    gwip = deck["global_wip"]
    backlog = deck["backlog"]
    saturated = gwip["saturated"]
    free = gwip["free_slots"]

    # follow-up: which of Wren's own delegations are still not done?
    outcomes = deck.get("delegation_outcomes", {})
    outstanding = [r for r in outcomes.get("records", [])
                   if r.get("outcome") in ("waiting", "in_flight")]

    plan = []
    # candidate work, highest value first: unowned OPEN backlog by priority
    candidates = list(backlog.get("top_unowned_by_priority", []))
    # if the backlog is empty, fall back to a fresh governor_scan finding
    scan = scan_mod.run()
    fresh_findings = [f for f in scan.get("findings", []) if not f.get("already_on_board")]

    n_slots = max_actions if saturated else min(max_actions, max(free, 1))
    actions = []
    used = 0

    # 1) assign existing unowned backlog tasks (drives completion, no new sprawl)
    for c in candidates:
        if used >= n_slots:
            break
        plan.append({"kind": "assign_backlog", "task_id": c["id"],
                     "priority": c["priority"], "title": c["title"]})
        if not dry_run:
            res = deleg_mod.run(task_id=c["id"], reason="governor_act: driving down the open backlog",
                                notify=notify)
            actions.append(res)
        used += 1

    # 2) if no backlog candidates but fresh findings exist, create+delegate one
    if used < n_slots and not candidates and fresh_findings:
        f = fresh_findings[0]
        plan.append({"kind": "new_from_finding", "finding": f.get("kind"),
                     "title": f.get("suggested_task_title")})
        if not dry_run:
            res = deleg_mod.run(title=f.get("suggested_task_title"),
                                description=f.get("detail", ""),
                                priority=f.get("priority", "normal"),
                                reason=f"governor_act: acting on {f.get('kind')} finding",
                                notify=notify)
            actions.append(res)
        used += 1

    if saturated:
        decision = ("SATURATED — did not start new in-flight work. "
                    f"{'Earmarked pending delegation(s); ' if actions else ''}"
                    f"finish/verify the {gwip['in_flight']} in-flight, unblock "
                    f"{len(deck.get('blocked', []))}, reap {len(deck.get('stale_claims', []))} stale.")
    elif plan:
        verb = "would delegate" if dry_run else "delegated"
        decision = f"Capacity available ({free} free) — {verb} {len(plan)} real task(s) into free slot(s)."
    else:
        decision = "Capacity available but nothing worth delegating (backlog + fresh findings empty). Holding."

    return {
        "ok": True,
        "generated_ts": _now(),
        "mode": "dry_run" if dry_run else "live",
        "deck_briefing": deck["briefing"],
        "decision": decision,
        "recommendation": deck["recommendation"],
        "followup_outstanding_delegations": outstanding,
        "plan": plan,
        "actions_taken": [
            {"task_id": a.get("task_id"), "assignee": a.get("assignee"),
             "verifier": a.get("verifier"), "status": a.get("status"),
             "wip_gate": a.get("wip_gate"), "notified": (a.get("notify") or {}).get("sent")}
            for a in actions
        ],
        "honesty": "decisions read live state; every delegation went through delegate_task (cap-checked, logged). No gate flipped, nothing forced onto a jammed board (R01).",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-actions", type=int, default=1)
    ap.add_argument("--live", action="store_true", help="actually delegate (default is dry_run)")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(max_actions=a.max_actions, dry_run=not a.live,
                         notify=not a.no_notify), indent=2, default=str))
