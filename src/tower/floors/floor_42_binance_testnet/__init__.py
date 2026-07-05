"""Floor 42 — Binance Testnet (scaffold ready for credentials).

The scaffold:
  · enumerates supported symbols + per-symbol guardrails
  · loads credentials from env vars only (NEVER from chat)
  · refuses every order call until the operator has registered with
    Binance testnet AND set the env vars locally
  · once credentials are present, the adapter places orders on the
    Binance Spot Testnet ONLY (https://testnet.binance.vision)
  · production (real money) is hard-locked behind a separate gate
    flip in a separate session

Workers can place/close testnet orders ONLY when:
  · they're certified for the instrument (extends our cert ledger)
  · operator manual-confirms each order
  · symbol is on the whitelist
  · quantity within per-order cap
  · no more than max_open_trades open at once
  · spread sanity check passes
  · daily loss not exceeded
  · kill switch off

The placement function lives in `placement.py`; it raises
`BinanceTestnetNotConfigured` until credentials are set.
"""

from .state import (
    FLAGS, GUARDS, floor_state_snapshot, persist_floor_state, tick,
    creds_present,
)
from .placement import (
    BinanceTestnetNotConfigured,
    BinanceTestnetClient,
    preflight,
    place_for_worker,
    close_for_worker,
)

__all__ = [
    "FLAGS", "GUARDS", "floor_state_snapshot", "persist_floor_state",
    "tick", "creds_present",
    "BinanceTestnetNotConfigured", "BinanceTestnetClient",
    "preflight", "place_for_worker", "close_for_worker",
]
