"""peer_belief_fusion.py — pure math for cross-worker belief teaching.

Per Ross 2026-06-21 mandate: workers teach each other. A peer's belief is
fused into own belief, weighted by peer's reputation (from trader chat board
win_rate) × peer's own regime_confidence.

Authorship:
  Hermes-8b drafted the function signature + weight formula
  Claude integrated — fixed the divide-by-(1-(1-weight)) math bug + preserved
                       own n_trades after fusion.

DO NOT FUSE: n_trades (each worker counts its own), stream_evidence (each
watches its own ticks), regime (each computes from its own ticks).
"""
from __future__ import annotations


def fuse_peer_belief(own: dict, peer: dict, peer_reputation: float) -> dict:
    """Return a NEW belief that mixes own with peer-derived strategy beliefs.

    peer_reputation: 0..1 — typically the peer's win_rate from trader_chat_board.
    Weight = peer_reputation * peer.regime.regime_confidence. Bounded to ≤ 0.5
    so own belief always anchors at least half (never overwhelmed by one peer).
    """
    peer_rc = peer.get("regime", {}).get("regime_confidence", 0.0)
    weight = min(0.5, max(0.0, peer_reputation * peer_rc))
    if weight == 0.0:
        return own  # no influence

    own_wr = own["strategy_fitness"].get("win_rate", 0.0)
    peer_wr = peer.get("strategy_fitness", {}).get("win_rate", 0.0)
    own_exp = own["strategy_fitness"].get("expectancy", 0.0)
    peer_exp = peer.get("strategy_fitness", {}).get("expectancy", 0.0)

    fused = {
        "regime": dict(own["regime"]),
        "strategy_fitness": {
            "win_rate": (1 - weight) * own_wr + weight * peer_wr,
            "expectancy": (1 - weight) * own_exp + weight * peer_exp,
            "n_trades": own["strategy_fitness"]["n_trades"],  # never fused
        },
        "stream_evidence": dict(own["stream_evidence"]),
    }
    return fused


def peer_reputation_from_chat_board(rows: list[dict], worker_id: str,
                                      min_trades: int = 10) -> float:
    """Compute a 0..1 reputation from trader_chat_board rows for one worker.
    Returns 0 if fewer than min_trades total to avoid early-game noise."""
    relevant = [r for r in rows if r.get("worker_id") == worker_id]
    if not relevant:
        return 0.0
    last = relevant[-1]
    n = last.get("wins", 0) + last.get("losses", 0)
    if n < min_trades:
        return 0.0
    wr = last.get("win_rate", 0.0)
    # Confidence-discounted reputation: rep = wr * (1 - 1/sqrt(n)) caps growth
    import math
    return max(0.0, min(1.0, wr * (1.0 - 1.0 / math.sqrt(n))))
