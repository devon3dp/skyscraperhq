"""
QSB Floor 41/42/43 Inter-Floor Sealed-Packet Bus
Phase: QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1

Architectural rules (CLAUDE.md):
  - Departments do NOT communicate directly.
  - Inter-floor communication travels through lifts.
  - Lifts carry sealed packets.

Reads cross_market_bus_latest.json + each floor's latest interior /
strategy registry and emits sealed packets routed through the
Memory Lift (which serves floor_02, floor_04, floor_16, floor_31).
Floors 41/42/43 dispatch packets to floor_31 (Audit/Ledger) via the
Service Lift; floor_31 fan-outs back.

Produces:
  - qsb_floor_intercom_packets_latest.json   (live packet stream)
  - qsb_floor_intercom_state.json            (per-floor send/recv stats)
  - mirrors recent packets into qsb_live_packets_latest.json

Safety:
  - packets carry advisory labels only — never an order
  - execution_allowed=false stamped on every packet
  - real_money_live_trading_enabled=false
"""

from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

PHASE = "QSB_FLOOR_41_42_43_INTERCOM_AND_FLOOR_43_VISIBLE_V1"

# Lift routing — each floor pair uses a specific lift per CLAUDE.md
# architecture. 41/42/43 all use the Service Lift for trading-floor
# correlation packets; results return via the Memory Lift to the
# Audit floor (31).
LIFT_ROUTES = {
    ("floor_41", "floor_42"): "service_lift",
    ("floor_41", "floor_43"): "service_lift",
    ("floor_42", "floor_41"): "service_lift",
    ("floor_42", "floor_43"): "service_lift",
    ("floor_43", "floor_41"): "service_lift",
    ("floor_43", "floor_42"): "service_lift",
    ("floor_41", "floor_31"): "memory_lift",
    ("floor_42", "floor_31"): "memory_lift",
    ("floor_43", "floor_31"): "memory_lift",
    ("floor_31", "floor_41"): "memory_lift",
    ("floor_31", "floor_42"): "memory_lift",
    ("floor_31", "floor_43"): "memory_lift",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _packet_id(src, dst, kind, seq):
    h = blake2b(f"{src}{dst}{kind}{seq}".encode("utf-8"),
                 digest_size=4).digest()
    return "pkt_intercom_" + h.hex()


def _seal_packet(src, dst, kind, body, seq):
    """Build a sealed packet. body is advisory only — never an order."""
    lift = LIFT_ROUTES.get((src, dst), "service_lift")
    pkt = {
        "packet_id": _packet_id(src, dst, kind, seq),
        "kind": kind,
        "from_floor": src,
        "to_floor": dst,
        "lift": lift,
        "sealed": True,
        "body": body,
        "advisory_only": True,
        "execution_allowed": False,
        "real_money_live_trading_enabled": False,
        "ts": _now(),
        "source_registry": body.get("source") if isinstance(body, dict) else None,
    }
    return pkt


def build_packets():
    bus = _load("cross_market_bus_latest.json", {})
    f41_state = _load("qsb_floor41_oanda_state.json", {})
    f41_pnl = _load("qsb_floor41_oanda_pnl.json", {})
    f41_prices = _load("qsb_floor41_oanda_prices_latest.json", {})
    f42 = _load("qsb_floor42_binance_interior.json", {})
    f43 = _load("qsb_floor43_stocks_interior.json", {})
    f43_strategy = _load("stock_paper_strategy_latest.json", {})
    f43_status = _load("stock_floor_status.json", {})

    packets = []
    seq = 0

    # ── Floor 41 → 42 (FX context for crypto correlation) ─────────────
    seq += 1
    packets.append(_seal_packet(
        "floor_41", "floor_42", "fx_market_brief",
        {
            "summary": "OANDA practice FX brief for Binance correlation review.",
            "prices": [{"instrument": p["instrument"], "bid": p.get("bid"),
                        "ask": p.get("ask"),
                        "spread_pips": p.get("spread_pips")}
                       for p in (f41_prices.get("prices") or [])[:5]],
            "realized_pnl": f41_pnl.get("realized_pnl_total"),
            "unrealized_pnl": f41_pnl.get("unrealized_pnl_total"),
            "source": "qsb_floor41_oanda_prices_latest.json + qsb_floor41_oanda_pnl.json",
        }, seq))

    # ── Floor 41 → 43 (FX context for equity-sector cross check) ──────
    seq += 1
    packets.append(_seal_packet(
        "floor_41", "floor_43", "fx_market_brief",
        {
            "summary": "OANDA FX brief shared with Stocks for USD strength cross-check.",
            "usd_pairs": [p for p in (f41_prices.get("prices") or [])
                          if "USD" in (p.get("instrument") or "")][:4],
            "source": "qsb_floor41_oanda_prices_latest.json",
        }, seq))

    # ── Floor 42 → 41 (Binance status for trading-floor coupling) ─────
    seq += 1
    packets.append(_seal_packet(
        "floor_42", "floor_41", "crypto_status_brief",
        {
            "summary": "Binance testnet floor status for OANDA risk awareness.",
            "mode": (f42.get("policy") or {}).get("mode"),
            "rooms": len(f42.get("rooms") or []),
            "workers": len(f42.get("workers") or []),
            "source": "qsb_floor42_binance_interior.json",
        }, seq))

    # ── Floor 43 → 41 (equities brief for FX dollar correlation) ──────
    seq += 1
    packets.append(_seal_packet(
        "floor_43", "floor_41", "equities_brief",
        {
            "summary": "Stocks paper floor brief — sector breadth and provider state.",
            "provider": f43_status.get("provider"),
            "environment": f43_status.get("environment"),
            "market_status": f43_strategy.get("market_status"),
            "default_symbols": f43_strategy.get("default_symbols"),
            "source": "stock_floor_status.json + stock_paper_strategy_latest.json",
        }, seq))

    # ── Floor 43 → 42 (equities brief for crypto coupling) ────────────
    seq += 1
    packets.append(_seal_packet(
        "floor_43", "floor_42", "equities_brief",
        {
            "summary": "Stocks paper floor brief shared with Binance for "
                       "equity-crypto correlation review.",
            "market_status": f43_strategy.get("market_status"),
            "default_symbols": f43_strategy.get("default_symbols"),
            "source": "stock_paper_strategy_latest.json",
        }, seq))

    # ── Floors 41/42/43 → 31 (audit ledger fan-in) ────────────────────
    for src in ("floor_41", "floor_42", "floor_43"):
        seq += 1
        packets.append(_seal_packet(
            src, "floor_31", "audit_fan_in",
            {
                "summary": "Audit fan-in: floor sent intercom packets this tick.",
                "intercom_packets_sent": sum(1 for p in packets
                                              if p["from_floor"] == src),
                "source": "qsb_floor_intercom_bus.py",
            }, seq))

    # ── Floor 31 → 41/42/43 (cross-market labels) ─────────────────────
    labels = (bus.get("cross_market_labels") or [])[:6]
    for dst in ("floor_41", "floor_42", "floor_43"):
        seq += 1
        packets.append(_seal_packet(
            "floor_31", dst, "cross_market_labels",
            {
                "summary": "Cross-market advisory labels from Audit/Ledger.",
                "labels": labels,
                "label_reasons": (bus.get("label_reasons") or [])[:4],
                "source": "cross_market_bus_latest.json",
            }, seq))

    payload = {
        "ok": True,
        "kind": "qsb_floor_intercom_packets_latest",
        "phase": PHASE,
        "generated_ts": _now(),
        "packet_count": len(packets),
        "packets": packets,
        "lift_routes": {f"{k[0]}->{k[1]}": v for k, v in LIFT_ROUTES.items()},
        "architecture_rule": "Departments do not communicate directly. All packets travel through lifts.",
    }
    payload.update(_safety())
    _write(REG / "qsb_floor_intercom_packets_latest.json", payload)
    return packets


def build_state(packets):
    per_floor = {}
    for p in packets:
        s = p["from_floor"]
        d = p["to_floor"]
        per_floor.setdefault(s, {"sent": 0, "received": 0,
                                  "kinds_sent": {}, "lift_use": {}})
        per_floor[s]["sent"] += 1
        per_floor[s]["kinds_sent"][p["kind"]] = per_floor[s]["kinds_sent"].get(p["kind"], 0) + 1
        per_floor[s]["lift_use"][p["lift"]] = per_floor[s]["lift_use"].get(p["lift"], 0) + 1
        per_floor.setdefault(d, {"sent": 0, "received": 0,
                                  "kinds_sent": {}, "lift_use": {}})
        per_floor[d]["received"] += 1

    payload = {
        "ok": True,
        "kind": "qsb_floor_intercom_state",
        "phase": PHASE,
        "generated_ts": _now(),
        "per_floor": per_floor,
        "total_packets": len(packets),
        "lifts_used": sorted(set(p["lift"] for p in packets)),
        "kinds": sorted(set(p["kind"] for p in packets)),
        "rule": "Direct floor-to-floor communication is FORBIDDEN. Every packet here was routed via a lift.",
    }
    payload.update(_safety())
    _write(REG / "qsb_floor_intercom_state.json", payload)
    return payload


def mirror_into_live_packets(packets):
    live = _load("qsb_live_packets_latest.json",
                 {"packets": [], "packet_count": 0})
    pk = live.get("packets") or []
    pk.extend(packets)
    pk = pk[-200:]
    live.update({
        "ok": True,
        "kind": "qsb_live_packets_latest",
        "generated_ts": _now(),
        "packet_count": len(pk),
        "packets": pk,
    })
    _write(REG / "qsb_live_packets_latest.json", live)


def build_all():
    packets = build_packets()
    state = build_state(packets)
    mirror_into_live_packets(packets)
    return {
        "ok": True,
        "phase": PHASE,
        "generated_ts": _now(),
        "packet_count": len(packets),
        "per_floor": state.get("per_floor"),
        **_safety(),
    }


def main():
    payload = build_all()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
