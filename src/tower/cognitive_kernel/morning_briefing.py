"""MorningBriefing — One-screen tower summary for the operator.

A tight digest that pulls from every layer and produces a screen of
text the operator can read in 30 seconds and understand:
  · what changed since the last briefing
  · who's earning, who's struggling
  · what proposals are awaiting Ross
  · what the Kernel is uncertain about
  · what gates are still locked (always)
  · one "headline" line capturing the most important fact

Persisted to cognitive_morning_briefing.json so the chat (and any future
email/Slack hook) can read it.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import time

from . import write_registry, append_log, now, load, COG_REG, SAFETY


@dataclass
class Briefing:
    headline: str
    bullets: List[str] = field(default_factory=list)
    pending_actions_for_ross: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)


class MorningBriefing:

    def _read(self, name: str) -> Dict[str, Any]:
        d = load(COG_REG / name)
        return d if isinstance(d, dict) else {}

    def compose(self) -> Briefing:
        bk = self._read("cognitive_bank_state.json")
        cmp_ = self._read("cognitive_compensation_state.json")
        pnl = self._read("cognitive_worker_pnl_rollup.json")
        ft = self._read("cognitive_family_tree.json")
        cert = self._read("cognitive_worker_certification.json")
        gate = self._read("cognitive_trading_authority_gate.json")
        reward = self._read("cognitive_reward_engine_state.json")
        audit = self._read("cognitive_self_audit.json")
        sm = self._read("cognitive_self_model.json")
        prof = self._read("cognitive_profit_snapshot.json")
        ap = self._read("cognitive_action_proposals.json")
        spend = self._read("cognitive_bank_spend_state.json")
        spawn = self._read("cognitive_worker_spawn_state.json")
        attr = self._read("cognitive_oanda_attribution_audit.json")

        bullets: List[str] = []
        pending: List[str] = []
        risks: List[str] = []

        # ── Money / PnL ───────────────────────────────────────────
        total_pnl = pnl.get("total_realized_pnl_practice") or 0
        wc = pnl.get("worker_count") or 0
        top = (pnl.get("top_earners") or [])
        top_str = ", ".join(
            f"{r.get('worker_id')} (${r.get('realized_pnl', 0):.0f})"
            for r in top[:3]) or "(none yet)"
        bullets.append(f"Practice PnL: ${total_pnl:.2f} across {wc} worker(s). "
                       f"Top earners: {top_str}.")

        # ── Bank ──────────────────────────────────────────────────
        supply = bk.get("outstanding_supply") or 0
        cap = bk.get("total_supply_cap") or 1
        util = bk.get("utilisation") or 0
        bullets.append(f"Bank: {supply:.0f} QBC outstanding "
                       f"({util*100:.2f}% of {cap} cap). "
                       f"Top concentration: {bk.get('top10_pct_concentration')}.")

        # ── Workforce / certs / lineage ───────────────────────────
        cert_counts = cert.get("by_status") or {}
        bullets.append(f"Certifications: {cert_counts}. "
                       f"Authority gate: certified={gate.get('certified_workers_count')}, "
                       f"suspended={gate.get('suspended_workers_count')}.")
        friend_n = ft.get("friend_edge_count") or 0
        child_n = ft.get("child_edge_count") or 0
        bullets.append(f"Family tree: {friend_n} friend edge(s), "
                       f"{child_n} child edge(s). "
                       f"Population: {self._read('cognitive_population_status.json').get('effective_population')} "
                       f"/ {self._read('cognitive_population_status.json').get('cap')}.")

        # ── Profit ───────────────────────────────────────────────
        if prof:
            top_line = prof.get("topline") or {}
            bullets.append(f"Commerce projection: revenue "
                           f"${top_line.get('projected_monthly_revenue_commerce', 0):.0f}/mo, "
                           f"profit ${top_line.get('projected_monthly_profit_commerce', 0):.0f}/mo. "
                           f"Warnings: {top_line.get('warnings') or '(none)'}.")

        # ── Pending actions for Ross ─────────────────────────────
        # Grants
        grants_open = [r for r in (reward.get("grants") or [])
                        if r.get("status") in ("open", "endorsed")]
        if grants_open:
            pending.append(f"{len(grants_open)} pending grant(s) in qsb_grant.py")
            for r in grants_open[:3]:
                pending.append(f"  · {r.get('grant_id')}  [{r.get('kind')}]  "
                               f"candidate={r.get('candidate_worker_id')}")
        # Spend
        spend_open = (spend.get("by_status") or {}).get("open", 0)
        if spend_open:
            pending.append(f"{spend_open} pending spend request(s) in qsb_spend.py")
        # Spawn
        spawn_pending = [pb for pb in (spawn.get("pending_births") or [])
                          if pb.get("spawn_status") == "pending_birth"]
        if spawn_pending:
            pending.append(f"{len(spawn_pending)} pending child birth(s) in qsb_spawn.py")
        # Free image approvals
        cat_approvals = self._read("cognitive_free_image_approvals.json")
        not_promoted = [a for a in (cat_approvals.get("approvals") or [])
                         if not a.get("promoted")]
        if not_promoted:
            pending.append(f"{len(not_promoted)} free-image draft(s) approved "
                            f"but not yet promoted to Floor 46 catalog "
                            "(orchestrator handles next tick)")

        # ── Risks ─────────────────────────────────────────────────
        # Audit findings
        af = audit.get("findings") or []
        reds = [f for f in af if f.get("severity") == "RED"]
        ambers = [f for f in af if f.get("severity") == "AMBER"]
        if reds:
            for f in reds[:3]:
                risks.append(f"AUDIT-RED: {f.get('code')} — {f.get('description')}")
        if ambers:
            for f in ambers[:3]:
                risks.append(f"AUDIT-AMBER: {f.get('code')} — {f.get('description')}")
        # OANDA attribution coverage
        if attr.get("ledger_present") and attr.get("total_rows", 0) > 0:
            cov = attr.get("attribution_coverage") or 1.0
            if cov < 0.9:
                risks.append(f"OANDA ledger attribution coverage {cov:.0%} — "
                              f"{attr.get('unassigned_rows')} unassigned rows")
        # Bank utilisation
        if util > 0.5:
            risks.append(f"Bank utilisation {util:.0%} — watch for tighten threshold (80%)")

        # ── Headline ─────────────────────────────────────────────
        if reds:
            headline = (f"⚠ {len(reds)} RED audit finding(s) need attention. "
                        f"PnL ${total_pnl:.0f}, Bank {supply:.0f} QBC, "
                        f"{friend_n} friend edges, {child_n} child edges.")
        elif grants_open:
            headline = (f"📜 {len(grants_open)} pending grant(s) awaiting "
                         f"dual signature. PnL ${total_pnl:.0f} practice; "
                         f"Bank {supply:.0f} QBC.")
        else:
            headline = (f"Tower steady. PnL ${total_pnl:.0f}, "
                        f"Bank {supply:.0f} QBC, "
                        f"{friend_n} friend edges, {child_n} child edges, "
                        f"{cert_counts.get('certified', 0)} certified.")

        append_log("morning_briefing.jsonl", {
            "event": "compose",
            "headline": headline,
            "bullet_count": len(bullets),
            "pending_count": len(pending),
            "risk_count": len(risks),
        })

        return Briefing(headline=headline,
                         bullets=bullets,
                         pending_actions_for_ross=pending,
                         risks=risks)

    def snapshot(self) -> Dict[str, Any]:
        b = self.compose()
        return {
            "ok": True,
            "kind": "cognitive_morning_briefing",
            "generated_ts": now(),
            "policy": ("One-screen tower digest. Read-only. "
                        "Advisory. Kernel never DOES."),
            "safety_envelope": dict(SAFETY),
            "headline": b.headline,
            "bullets": b.bullets,
            "pending_actions_for_ross": b.pending_actions_for_ross,
            "risks": b.risks,
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_morning_briefing.json", snap)
        return snap


_BR: Optional[MorningBriefing] = None


def morning_briefing() -> MorningBriefing:
    global _BR
    if _BR is None:
        _BR = MorningBriefing()
    return _BR
