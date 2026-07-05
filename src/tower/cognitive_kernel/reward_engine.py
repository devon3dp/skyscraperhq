"""RewardEngine — Friend & Child grant flow with dual-signature gate.

Flow:
  1. observe_and_propose() — scan worker_pnl rollup against thresholds;
     for each eligible worker, create a PendingGrant + write a
     human-readable report at data/reports/grant_proposals/<grant_id>.md.
  2. Claude reviews; calls endorse(grant_id) to add Claude signature.
  3. Ross reviews; calls authorize(grant_id) to add Ross signature.
  4. execute_authorized() — for every grant with BOTH signatures,
     apply: family_tree.add_friend_edge / add_child_edge; for children,
     also seed worker_genetics with inherited gene.

Thresholds (from Kernel's defended numbers):
  FRIEND:  25 closed trades, win_rate >= 0.58, realized_pnl > 0,
           no recent suspension.
  CHILD:   75 closed trades, win_rate >= 0.60, realized_pnl >= $500,
           current children < 3, no recent loss streak (last 10),
           population headroom available, gene diversity OK.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import time

from . import ROOT, write_registry, append_log, now, SAFETY
from .worker_pnl import worker_pnl
from .worker_certification import worker_certification
from .worker_genetics import worker_genetics
from .family_tree import family_tree, MAX_CHILDREN_PER_PARENT
from .population import has_headroom_for_grant, population_snapshot
from .long_term_memory import long_term_memory


REPORTS_DIR = ROOT / "data/reports/grant_proposals"

FRIEND_MIN_TRADES = 25
FRIEND_MIN_WIN_RATE = 0.58
CHILD_MIN_TRADES = 75
CHILD_MIN_WIN_RATE = 0.60
CHILD_MIN_REALIZED_PNL = 500.0
CHILD_NO_LOSS_STREAK_WINDOW = 10


@dataclass
class PendingGrant:
    grant_id: str
    kind: str                # 'friend' | 'child'
    candidate_worker_id: str
    rationale: str
    proposed_ts: float
    target_worker_id: Optional[str] = None   # for friend grants: the high-earner peer
    inherited_gene: Optional[Dict[str, Any]] = None   # for child grants
    signatures: Dict[str, bool] = field(default_factory=dict)  # 'claude', 'ross'
    status: str = "open"     # open | endorsed | authorized | executed | declined | superseded
    notes: List[str] = field(default_factory=list)
    report_path: Optional[str] = None
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)


class RewardEngine:
    def __init__(self):
        self._grants: Dict[str, PendingGrant] = {}
        self._counter = 0

    # ── eligibility ───────────────────────────────────────────────
    def _friend_eligible(self, row: Dict[str, Any]) -> bool:
        return (row["closed_trade_count"] >= FRIEND_MIN_TRADES
                and (row["win_rate"] or 0) >= FRIEND_MIN_WIN_RATE
                and row["realized_pnl"] > 0
                and row["consecutive_losses_current"] < 3)

    def _child_eligible(self, row: Dict[str, Any], parent_id: str) -> bool:
        if family_tree().is_at_child_cap(parent_id):
            return False
        if not has_headroom_for_grant(1):
            return False
        if (row["closed_trade_count"] < CHILD_MIN_TRADES
            or (row["win_rate"] or 0) < CHILD_MIN_WIN_RATE
            or row["realized_pnl"] < CHILD_MIN_REALIZED_PNL):
            return False
        if row["consecutive_losses_current"] >= 3:
            return False
        # Gene diversity guard
        warn, _fam = worker_genetics().is_monoculture_warning()
        if warn:
            return False
        return True

    def _pick_friend_for(self, candidate_id: str,
                          top_earners: List[Dict[str, Any]]) -> Optional[str]:
        # Friend = top-decile earner that isn't the candidate themselves
        for row in top_earners:
            wid = row["worker_id"]
            if wid != candidate_id and wid != "unassigned":
                return wid
        return None

    # ── observe + propose ────────────────────────────────────────
    def observe_and_propose(self) -> List[PendingGrant]:
        pnl = worker_pnl()
        pnl.refresh()
        snap = pnl.snapshot()
        top = pnl.top_earners(20)
        proposed: List[PendingGrant] = []

        for row in snap.get("rows_sample") or []:
            wid = row["worker_id"]
            if wid == "unassigned":
                continue

            # ── FRIEND ──────────────────────────────────────────
            if self._friend_eligible(row):
                # Skip if this worker already has friends — keep it simple v1
                if family_tree().friends_of(wid):
                    pass
                else:
                    friend_id = self._pick_friend_for(wid, top)
                    if friend_id:
                        g = self._propose(
                            kind="friend",
                            candidate_worker_id=wid,
                            target_worker_id=friend_id,
                            rationale=(
                                f"{wid} has {row['closed_trade_count']} closed trades, "
                                f"win_rate {row['win_rate']:.2%}, "
                                f"realized PnL ${row['realized_pnl']:.2f} "
                                f"on practice. Friend candidate is "
                                f"top-decile earner {friend_id}."
                            ),
                            metrics_snapshot=row,
                        )
                        proposed.append(g)

            # ── CHILD ───────────────────────────────────────────
            if self._child_eligible(row, parent_id=wid):
                best = pnl.best_pair_for(wid)
                inherited_gene = None
                if best:
                    (instrument, style), pair_pnl = best
                    from .worker_genetics import family_of
                    inherited_gene = {
                        "instrument": instrument,
                        "style": style,
                        "family": family_of(instrument),
                        "from_parent_pair_pnl": round(pair_pnl, 2),
                    }
                g = self._propose(
                    kind="child",
                    candidate_worker_id=wid,
                    inherited_gene=inherited_gene,
                    rationale=(
                        f"{wid} has {row['closed_trade_count']} closed trades, "
                        f"win_rate {row['win_rate']:.2%}, "
                        f"realized PnL ${row['realized_pnl']:.2f}. "
                        f"Current children: {family_tree().children_count(wid)}/"
                        f"{MAX_CHILDREN_PER_PARENT}. "
                        f"Inherited gene: "
                        f"{inherited_gene['instrument']}/{inherited_gene['style']} "
                        f"(family={inherited_gene['family']})."
                        if inherited_gene else
                        f"{wid} eligible for child grant; no clear gene yet."
                    ),
                    metrics_snapshot=row,
                )
                proposed.append(g)

        append_log("reward_engine.jsonl", {
            "event": "observe_and_propose",
            "proposed_count": len(proposed),
        })
        return proposed

    def _propose(self, kind: str, candidate_worker_id: str, rationale: str,
                  target_worker_id: Optional[str] = None,
                  inherited_gene: Optional[Dict[str, Any]] = None,
                  metrics_snapshot: Optional[Dict[str, Any]] = None) -> PendingGrant:
        self._counter += 1
        grant_id = f"grant_{kind}_{int(time.time())}_{self._counter}"
        g = PendingGrant(
            grant_id=grant_id, kind=kind,
            candidate_worker_id=candidate_worker_id,
            target_worker_id=target_worker_id,
            rationale=rationale,
            inherited_gene=inherited_gene,
            proposed_ts=time.time(),
            metrics_snapshot=metrics_snapshot or {},
        )
        report_path = self._write_report(g)
        g.report_path = str(report_path)
        self._grants[grant_id] = g
        append_log("reward_engine.jsonl", {
            "event": "proposed",
            "grant_id": grant_id, "kind": kind,
            "candidate": candidate_worker_id,
            "target": target_worker_id,
        })
        return g

    # ── report writer ────────────────────────────────────────────
    def _write_report(self, g: PendingGrant) -> Path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"{g.grant_id}.md"
        m = g.metrics_snapshot or {}
        if g.kind == "friend":
            body = self._friend_report(g, m)
        else:
            body = self._child_report(g, m)
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _friend_report(g: PendingGrant, m: Dict[str, Any]) -> str:
        return (
            f"# Grant Proposal — FRIEND\n\n"
            f"**grant_id:** `{g.grant_id}`  \n"
            f"**filed:** {now()}  \n"
            f"**status:** open (awaiting Claude endorse + Ross authorize)\n\n"
            f"## Candidate\n"
            f"- worker_id: `{g.candidate_worker_id}`\n"
            f"- closed practice trades: **{m.get('closed_trade_count')}**\n"
            f"- win_rate: **{m.get('win_rate')}**\n"
            f"- realized_pnl (practice): **${m.get('realized_pnl', 0):.2f}**\n"
            f"- best single trade: **${m.get('best_trade_pnl', 0):.2f}**\n"
            f"- worst single trade: **${m.get('worst_trade_pnl', 0):.2f}**\n"
            f"- avg hold seconds: **{m.get('avg_hold_seconds', 0):.1f}**\n\n"
            f"## Proposed Friend\n"
            f"- worker_id: `{g.target_worker_id}` (top-decile earner)\n\n"
            f"## Rationale\n"
            f"{g.rationale}\n\n"
            f"## Effect on grant\n"
            f"- adds `friend({g.candidate_worker_id}, {g.target_worker_id})` to family_tree\n"
            f"- both workers' next-trade Attention scores gain a small bonus\n"
            f"- no population change\n\n"
            f"## Safety\n"
            f"- execution_allowed: **False**\n"
            f"- autonomous_dispatch_enabled: **False**\n"
            f"- live_trading_enabled: **False**\n\n"
            f"## How to act\n"
            f"```\n"
            f"# Claude endorse:  python3 tools/qsb_grant.py endorse {g.grant_id}\n"
            f"# Ross authorize:  python3 tools/qsb_grant.py authorize {g.grant_id}\n"
            f"# After both:      python3 tools/qsb_grant.py execute {g.grant_id}\n"
            f"```\n"
        )

    @staticmethod
    def _child_report(g: PendingGrant, m: Dict[str, Any]) -> str:
        gene = g.inherited_gene or {}
        return (
            f"# Grant Proposal — CHILD (digital child)\n\n"
            f"**grant_id:** `{g.grant_id}`  \n"
            f"**filed:** {now()}  \n"
            f"**status:** open (awaiting Claude endorse + Ross authorize)\n\n"
            f"## Parent\n"
            f"- worker_id: `{g.candidate_worker_id}`\n"
            f"- closed practice trades: **{m.get('closed_trade_count')}**\n"
            f"- win_rate: **{m.get('win_rate')}**\n"
            f"- realized_pnl (practice): **${m.get('realized_pnl', 0):.2f}**\n"
            f"- current children: **{family_tree().children_count(g.candidate_worker_id)}"
            f"/{MAX_CHILDREN_PER_PARENT}**\n\n"
            f"## Inherited Gene\n"
            f"- instrument: **{gene.get('instrument', '(unrevealed)')}**\n"
            f"- style: **{gene.get('style', '(unrevealed)')}**\n"
            f"- family: **{gene.get('family', '(unrevealed)')}**\n"
            f"- parent's PnL on this pair: **${gene.get('from_parent_pair_pnl', 0):.2f}**\n\n"
            f"## Population Status\n"
            f"- current effective: **{population_snapshot()['effective_population']}**\n"
            f"- cap: **{population_snapshot()['cap']}**\n"
            f"- headroom: **{population_snapshot()['headroom']}**\n\n"
            f"## Rationale\n"
            f"{g.rationale}\n\n"
            f"## Effect on grant\n"
            f"- adds `parent_of({g.candidate_worker_id}, <new_child_id>)` to family_tree\n"
            f"- new child worker is created in a SEPARATE Claude phase that writes\n"
            f"  the workforce registry — this grant only stamps the lineage edge\n"
            f"- child starts in classroom with inherited gene's instrument as their\n"
            f"  first study target; confidence_seed = 0.55\n"
            f"- effective population goes up by 1\n\n"
            f"## Safety\n"
            f"- execution_allowed: **False** (Kernel never spawns workers itself)\n"
            f"- autonomous_dispatch_enabled: **False**\n"
            f"- live_trading_enabled: **False**\n\n"
            f"## How to act\n"
            f"```\n"
            f"# Claude endorse:  python3 tools/qsb_grant.py endorse {g.grant_id}\n"
            f"# Ross authorize:  python3 tools/qsb_grant.py authorize {g.grant_id}\n"
            f"# After both:      python3 tools/qsb_grant.py execute {g.grant_id}\n"
            f"```\n"
        )

    # ── signatures ───────────────────────────────────────────────
    def endorse(self, grant_id: str, note: str = "") -> bool:
        g = self._grants.get(grant_id)
        if g is None or g.status not in ("open", "endorsed", "authorized"):
            return False
        g.signatures["claude"] = True
        g.status = "authorized" if g.signatures.get("ross") else "endorsed"
        if note: g.notes.append(f"endorse: {note}")
        append_log("reward_engine.jsonl",
                   {"event": "endorsed", "grant_id": grant_id})
        return True

    def authorize(self, grant_id: str, note: str = "") -> bool:
        g = self._grants.get(grant_id)
        if g is None or g.status not in ("open", "endorsed", "authorized"):
            return False
        g.signatures["ross"] = True
        g.status = "authorized" if g.signatures.get("claude") else "open"
        if note: g.notes.append(f"authorize: {note}")
        append_log("reward_engine.jsonl",
                   {"event": "authorized", "grant_id": grant_id})
        return True

    def decline(self, grant_id: str, note: str = "") -> bool:
        g = self._grants.get(grant_id)
        if g is None: return False
        g.status = "declined"
        if note: g.notes.append(f"decline: {note}")
        append_log("reward_engine.jsonl",
                   {"event": "declined", "grant_id": grant_id, "note": note})
        return True

    # ── execute ──────────────────────────────────────────────────
    def execute_authorized(self) -> List[str]:
        executed: List[str] = []
        for grant_id, g in list(self._grants.items()):
            if g.status != "authorized": continue
            if not (g.signatures.get("claude") and g.signatures.get("ross")):
                continue
            ok = self._execute_one(g)
            if ok:
                g.status = "executed"
                executed.append(grant_id)
        return executed

    def _execute_one(self, g: PendingGrant) -> bool:
        ft = family_tree()
        if g.kind == "friend":
            if not g.target_worker_id: return False
            edge = ft.add_friend_edge(
                a=g.candidate_worker_id, b=g.target_worker_id,
                grant_id=g.grant_id,
                note=f"reward grant {g.grant_id}",
            )
            ok = edge is not None
            long_term_memory().record_episode(
                kind="reward_grant_executed",
                summary=f"FRIEND grant executed: {g.candidate_worker_id} ↔ {g.target_worker_id}",
                tags=["reward", "friend"],
                payload={"grant_id": g.grant_id},
            )
            return ok
        elif g.kind == "child":
            if not has_headroom_for_grant(1):
                g.notes.append("execute_refused: population cap reached")
                return False
            # Create a deterministic placeholder child id; the separate
            # Claude phase that writes the workforce registry will
            # promote this to a real worker entity.
            child_id = (f"child_of_{g.candidate_worker_id}_"
                         f"{int(time.time())}_{g.grant_id[-6:]}")
            edge = ft.add_child_edge(
                parent_id=g.candidate_worker_id,
                child_id=child_id,
                grant_id=g.grant_id,
                inherited_gene=g.inherited_gene,
                note=f"reward grant {g.grant_id}",
            )
            if edge is None:
                g.notes.append("execute_refused: family_tree refused (cap or duplicate)")
                return False
            # Seed genetics for the new child
            genome = worker_genetics().get_or_create(
                child_id, parent_id=g.candidate_worker_id)
            long_term_memory().record_episode(
                kind="reward_grant_executed",
                summary=f"CHILD grant executed: parent {g.candidate_worker_id} → child {child_id}",
                tags=["reward", "child"],
                payload={"grant_id": g.grant_id,
                         "child_id": child_id,
                         "inherited_gene": g.inherited_gene},
            )
            return True
        return False

    # ── snapshot ─────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        rows = []
        for g in self._grants.values():
            by_status[g.status] = by_status.get(g.status, 0) + 1
            rows.append({
                "grant_id": g.grant_id, "kind": g.kind,
                "candidate_worker_id": g.candidate_worker_id,
                "target_worker_id": g.target_worker_id,
                "status": g.status,
                "signatures": dict(g.signatures),
                "report_path": g.report_path,
                "proposed_ts": g.proposed_ts,
                "rationale": g.rationale,
                "inherited_gene": g.inherited_gene,
            })
        return {
            "ok": True,
            "kind": "cognitive_reward_engine_state",
            "generated_ts": now(),
            "policy": ("Dual-signature flow. Kernel proposes; Claude "
                        "endorses; Ross authorizes; execute applies the "
                        "lineage edge. No execution without both signatures."),
            "safety_envelope": dict(SAFETY),
            "thresholds": {
                "friend_min_trades": FRIEND_MIN_TRADES,
                "friend_min_win_rate": FRIEND_MIN_WIN_RATE,
                "child_min_trades": CHILD_MIN_TRADES,
                "child_min_win_rate": CHILD_MIN_WIN_RATE,
                "child_min_realized_pnl": CHILD_MIN_REALIZED_PNL,
                "max_children_per_parent": MAX_CHILDREN_PER_PARENT,
            },
            "grant_count": len(self._grants),
            "by_status": by_status,
            "grants": rows,
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_reward_engine_state.json", snap)
        return snap

    def get(self, grant_id: str) -> Optional[PendingGrant]:
        return self._grants.get(grant_id)

    def all_grants(self) -> List[PendingGrant]:
        return list(self._grants.values())

    def load_from_snapshot(self) -> int:
        """Rehydrate _grants from the persisted registry."""
        from . import COG_REG, load
        d = load(COG_REG / "cognitive_reward_engine_state.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("grants") or []:
            grant_id = r.get("grant_id")
            if not grant_id or grant_id in self._grants:
                continue
            g = PendingGrant(
                grant_id=grant_id,
                kind=r.get("kind", "?"),
                candidate_worker_id=r.get("candidate_worker_id", "?"),
                rationale=r.get("rationale", ""),
                proposed_ts=float(r.get("proposed_ts", time.time())),
                target_worker_id=r.get("target_worker_id"),
                inherited_gene=r.get("inherited_gene"),
                signatures=dict(r.get("signatures") or {}),
                status=r.get("status", "open"),
                report_path=r.get("report_path"),
                metrics_snapshot={},
            )
            self._grants[grant_id] = g
            count += 1
        return count


_RE: Optional[RewardEngine] = None


def reward_engine() -> RewardEngine:
    global _RE
    if _RE is None:
        _RE = RewardEngine()
    return _RE
