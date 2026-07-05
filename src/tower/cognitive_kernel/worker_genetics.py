"""WorkerGenetics — Each worker has a 'winning gene'.

A worker's gene = (instrument, style). Style = scalp | trend | mean_revert.
The gene is the worker's best-PnL pairing observed across their practice
trades. A child inherits the parent's gene.

Gene assignment rule:
  · If a worker has < N closed practice trades, gene is "unrevealed".
  · Once they cross N trades, compute PnL by (instrument, style) and
    pick the highest-PnL pair as the gene.
  · Genes can EVOLVE: if a worker's gene-pair stops being their best,
    we record the prior gene + the new gene in their gene_history.

Inheritance rule:
  · Child gene = parent's CURRENT gene at grant time.
  · Child confidence_seed = 0.55 (less than parent's, > naive).
  · Child gene_lineage = parent.gene_lineage + [parent.id].

Gene diversity guard (used by reward_engine):
  · Count children granted in last 30 days by gene family.
  · If any single gene family > 60%, refuse new child grants until
    operator approves the monoculture warning or extends gene families.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
import time

from . import write_registry, append_log, now, load


GENE_REVEAL_THRESHOLD_TRADES = 25
DIVERSITY_WINDOW_DAYS = 30
DIVERSITY_MAX_SHARE = 0.60


GENE_STYLES = ("scalp", "trend", "mean_revert")
GENE_INSTRUMENT_FAMILIES = {
    "fx_majors":   ("EUR_USD", "USD_JPY", "GBP_USD", "USD_CHF"),
    "fx_crosses":  ("EUR_GBP", "EUR_JPY", "GBP_JPY", "AUD_NZD"),
    "fx_minors":   ("AUD_USD", "USD_CAD", "NZD_USD"),
    "metals":      ("XAU_USD", "XAG_USD"),
}


def family_of(instrument: str) -> str:
    for fam, members in GENE_INSTRUMENT_FAMILIES.items():
        if instrument in members:
            return fam
    return "other"


@dataclass
class Gene:
    instrument: str
    style: str
    revealed_ts: float
    confidence: float = 0.55
    family: str = "other"


@dataclass
class WorkerGenome:
    worker_id: str
    current_gene: Optional[Gene] = None
    gene_history: List[Gene] = field(default_factory=list)
    parent_id: Optional[str] = None
    gene_lineage: List[str] = field(default_factory=list)   # ancestor ids


class WorkerGenetics:
    def __init__(self):
        self._genomes: Dict[str, WorkerGenome] = {}

    def get_or_create(self, worker_id: str,
                      parent_id: Optional[str] = None) -> WorkerGenome:
        g = self._genomes.get(worker_id)
        if g is None:
            g = WorkerGenome(worker_id=worker_id, parent_id=parent_id)
            if parent_id and parent_id in self._genomes:
                parent = self._genomes[parent_id]
                g.gene_lineage = list(parent.gene_lineage) + [parent_id]
                # Inherit parent's current gene with reduced confidence
                if parent.current_gene:
                    inherited = Gene(
                        instrument=parent.current_gene.instrument,
                        style=parent.current_gene.style,
                        revealed_ts=time.time(),
                        confidence=0.55,
                        family=parent.current_gene.family,
                    )
                    g.current_gene = inherited
                    g.gene_history.append(inherited)
                    append_log("worker_genetics.jsonl", {
                        "event": "inherit_gene",
                        "worker_id": worker_id,
                        "parent_id": parent_id,
                        "instrument": inherited.instrument,
                        "style": inherited.style,
                    })
            self._genomes[worker_id] = g
        return g

    def reveal_or_update(self, worker_id: str,
                          pnl_by_pair: Dict[Tuple[str, str], float],
                          total_trades: int) -> Optional[Gene]:
        """Given per-(instrument, style) PnL totals and trade count,
        either reveal the worker's gene for the first time, or update
        if a different pair is now best."""
        if total_trades < GENE_REVEAL_THRESHOLD_TRADES:
            return None
        if not pnl_by_pair:
            return None
        best_pair, best_pnl = max(pnl_by_pair.items(), key=lambda kv: kv[1])
        if best_pnl <= 0:
            return None    # no profitable pair yet
        instrument, style = best_pair
        g = self.get_or_create(worker_id)
        if g.current_gene and (g.current_gene.instrument == instrument
                                and g.current_gene.style == style):
            # Same gene; lift confidence slightly with sustained performance
            g.current_gene.confidence = min(0.95,
                                            g.current_gene.confidence + 0.02)
            return g.current_gene
        # New or shifted gene
        new_gene = Gene(
            instrument=instrument, style=style,
            revealed_ts=time.time(),
            confidence=0.65 if g.current_gene is None else 0.60,
            family=family_of(instrument),
        )
        g.current_gene = new_gene
        g.gene_history.append(new_gene)
        append_log("worker_genetics.jsonl", {
            "event": "reveal_or_shift",
            "worker_id": worker_id,
            "instrument": instrument,
            "style": style,
            "pnl_at_reveal": round(best_pnl, 2),
        })
        return new_gene

    def diversity_share_by_family(self,
                                    window_seconds: float = DIVERSITY_WINDOW_DAYS * 86400.0
                                  ) -> Dict[str, float]:
        cutoff = time.time() - window_seconds
        family_counts: Dict[str, int] = {}
        total = 0
        for g in self._genomes.values():
            if not g.current_gene: continue
            if g.current_gene.revealed_ts < cutoff: continue
            family_counts[g.current_gene.family] = \
                family_counts.get(g.current_gene.family, 0) + 1
            total += 1
        if total == 0:
            return {}
        return {f: round(c / total, 3) for f, c in family_counts.items()}

    def is_monoculture_warning(self) -> Tuple[bool, Optional[str]]:
        shares = self.diversity_share_by_family()
        for fam, share in shares.items():
            if share > DIVERSITY_MAX_SHARE:
                return True, fam
        return False, None

    def snapshot(self) -> Dict[str, Any]:
        rows = []
        for g in self._genomes.values():
            d = {
                "worker_id": g.worker_id,
                "parent_id": g.parent_id,
                "gene_lineage": g.gene_lineage,
                "current_gene": asdict(g.current_gene) if g.current_gene else None,
                "gene_history_count": len(g.gene_history),
            }
            rows.append(d)
        warn, fam = self.is_monoculture_warning()
        return {
            "ok": True,
            "kind": "cognitive_worker_genetics",
            "generated_ts": now(),
            "worker_genome_count": len(rows),
            "diversity_share_by_family": self.diversity_share_by_family(),
            "monoculture_warning": warn,
            "monoculture_family": fam,
            "thresholds": {
                "gene_reveal_threshold_trades": GENE_REVEAL_THRESHOLD_TRADES,
                "diversity_window_days": DIVERSITY_WINDOW_DAYS,
                "diversity_max_share": DIVERSITY_MAX_SHARE,
            },
            "genomes_sample": rows[:50],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_worker_genetics.json", snap)
        return snap


_GENETICS: Optional[WorkerGenetics] = None


def worker_genetics() -> WorkerGenetics:
    global _GENETICS
    if _GENETICS is None:
        _GENETICS = WorkerGenetics()
    return _GENETICS
