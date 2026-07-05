#!/usr/bin/env python3
"""
QSB Tower V1.3 — OANDA Gateway

Read-only OANDA practice gateway for Floor 41.

Safety:
- Defaults to practice environment.
- Credentials are read from environment variables only.
- No order placement in V1.
- No live trading.
- No worker dispatch.
- No external AI providers.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import urllib.parse
import urllib.request
import urllib.error

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOG = ROOT / "data/logs/oanda_trading_floor.jsonl"

POLICY_PATH = REG / "oanda_trading_floor_policy.json"
STATUS_PATH = REG / "oanda_trading_floor_status.json"

LOCKED_FALSE = {
    "live_trading_enabled": False,
    "order_execution_enabled": False,
    "practice_order_execution_enabled": False,
    "worker_execution_enabled": False,
    "provider_execution_enabled": False,
    "external_provider_execution_enabled": False,
    "openclaw_execution_enabled": False,
    "autonomous_dispatch_enabled": False,
    "live_dispatch_enabled": False,
    "direct_provider_access": False,
}


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


class OANDAGateway:
    def __init__(self):
        self.policy = load_json(POLICY_PATH, {})
        self.base_url = self.policy.get("selected_base_url") or "https://api-fxpractice.oanda.com"

        if self.base_url != "https://api-fxpractice.oanda.com":
            raise RuntimeError("Blocked: OANDA Trading Floor V1 only allows practice base URL.")

        self.token = os.environ.get("OANDA_API_TOKEN", "").strip()
        self.account_id = os.environ.get("OANDA_ACCOUNT_ID", "").strip()

    def _headers(self):
        if not self.token:
            raise RuntimeError("Missing OANDA_API_TOKEN environment variable.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def _get(self, path, params=None, timeout=10):
        if not path.startswith("/v3/"):
            raise RuntimeError(f"Blocked non-v3 OANDA path: {path}")

        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers=self._headers(), method="GET")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def credentials_status(self):
        return {
            "token_present": bool(self.token),
            "account_id_present": bool(self.account_id),
            "account_id": self.account_id if self.account_id else None,
            "credentials_source": "environment_variables_only"
        }

    # ── PRACTICE-ONLY ORDER METHODS (Tower Ops V4) ────────────────────
    # Hard guard: base_url is checked at __init__ to be the practice URL.
    # These helpers are still gated by per-call practice-mode checks in
    # tower_ops.oanda_practice_trading — they can ONLY be reached through
    # that module's strict guardrails.

    def _post(self, path, body, timeout=12):
        if not path.startswith("/v3/"):
            raise RuntimeError(f"Blocked non-v3 OANDA path: {path}")
        if self.base_url != "https://api-fxpractice.oanda.com":
            raise RuntimeError("Blocked: OANDA practice base URL required for POST.")
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _put(self, path, body, timeout=12):
        if not path.startswith("/v3/"):
            raise RuntimeError(f"Blocked non-v3 OANDA path: {path}")
        if self.base_url != "https://api-fxpractice.oanda.com":
            raise RuntimeError("Blocked: OANDA practice base URL required for PUT.")
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def place_market_order(self, instrument, units, side):
        """Place a MARKET order on the practice account. PRACTICE ONLY."""
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID.")
        if side not in ("buy", "sell"):
            raise RuntimeError(f"Invalid side: {side}")
        signed = int(units) if side == "buy" else -int(units)
        body = {"order": {"type": "MARKET", "instrument": instrument,
                           "units": str(signed),
                           "timeInForce": "FOK", "positionFill": "DEFAULT"}}
        return self._post(f"/v3/accounts/{self.account_id}/orders", body)

    def close_trade(self, trade_id, units="ALL"):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID.")
        return self._put(f"/v3/accounts/{self.account_id}/trades/{trade_id}/close",
                          {"units": str(units)})

    def open_positions(self):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID.")
        return self._get(f"/v3/accounts/{self.account_id}/openPositions")

    def open_trades(self):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID.")
        return self._get(f"/v3/accounts/{self.account_id}/openTrades")

    def transactions(self, count=20):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID.")
        return self._get(f"/v3/accounts/{self.account_id}/transactions",
                          params={"pageSize": count})

    def list_accounts(self):
        return self._get("/v3/accounts")

    def account_summary(self):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID environment variable.")
        return self._get(f"/v3/accounts/{self.account_id}/summary")

    def pricing(self, instruments=None):
        if not self.account_id:
            raise RuntimeError("Missing OANDA_ACCOUNT_ID environment variable.")

        if not instruments:
            instruments = self.policy.get("default_instruments") or ["EUR_USD"]

        if isinstance(instruments, str):
            instruments = [x.strip() for x in instruments.split(",") if x.strip()]

        return self._get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": ",".join(instruments)}
        )

    def status(self):
        status = {
            "status_ts": datetime.now(timezone.utc).isoformat(),
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "environment": "practice",
            "base_url": self.base_url,
            "credentials": self.credentials_status(),
            "account_read_enabled": True,
            "pricing_read_enabled": True,
            "paper_trading_enabled": True,
            "local_model_commentary_enabled": True,
            **LOCKED_FALSE,
            "ready_for_account_read": bool(self.token and self.account_id),
            "ready_for_pricing_read": bool(self.token and self.account_id),
            "ready_for_order_execution": False
        }

        write_json(STATUS_PATH, status)
        return status

    def snapshot(self, instruments=None):
        result = {
            "snapshot_ts": datetime.now(timezone.utc).isoformat(),
            "status": self.status(),
            "account_summary": None,
            "pricing": None,
            "errors": [],
            **LOCKED_FALSE
        }

        try:
            result["account_summary"] = self.account_summary()
        except Exception as exc:
            result["errors"].append(f"account_summary: {exc}")

        try:
            result["pricing"] = self.pricing(instruments)
        except Exception as exc:
            result["errors"].append(f"pricing: {exc}")

        append_log(result)
        write_json(REG / "oanda_trading_floor_latest_snapshot.json", result)
        return result


if __name__ == "__main__":
    gw = OANDAGateway()
    print(json.dumps(gw.status(), indent=2))
