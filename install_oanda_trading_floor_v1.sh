#!/usr/bin/env bash
set -euo pipefail

cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "======================================================"
echo "  QSB Tower V1.3 — Install Floor 41 OANDA Trading Floor"
echo "======================================================"
echo "Mode: practice/read-only/simulation first"
echo "Workers/providers/OpenClaw/autonomous dispatch remain disabled."
echo "Live trading remains disabled."

mkdir -p \
  floors/floor_41_oanda_trading_floor \
  data/registries \
  data/logs \
  data/backups \
  scripts \
  tests \
  src/tower

echo
echo "=== BACKUP FLOOR REGISTRIES ==="
for f in data/registries/floors.json data/registries/vacant_floor_registry.json data/registries/building.json; do
  [ -f "$f" ] && cp -f "$f" "data/backups/$(basename "$f").backup_before_oanda_floor_${TS}" || true
done

echo
echo "=== WRITE FLOOR 41 MANIFEST ==="
cat > floors/floor_41_oanda_trading_floor/floor_manifest.json <<'JSON'
{
  "floor_id": "floor_41",
  "number": 41,
  "department": "OANDA Trading Floor",
  "version": "1.0",
  "zone": "ZONE C",
  "status": "staged",
  "role": "Local-only trading research, OANDA practice data intake, risk simulation, and kernel-supervised market commentary.",
  "oanda_enabled": true,
  "oanda_environment": "practice",
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "paper_trading_enabled": true,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "local_model_commentary_enabled": true,
  "kernel_required": true,
  "kernel_activation_required": "active_local_only",
  "allowed_operations": [
    "read OANDA practice account metadata",
    "read OANDA practice pricing",
    "simulate signals",
    "log market observations",
    "produce local-only model commentary"
  ],
  "forbidden_operations": [
    "live order placement",
    "practice order placement until explicitly enabled",
    "external provider routing",
    "OpenClaw execution",
    "autonomous worker dispatch",
    "credential hardcoding"
  ]
}
JSON

echo
echo "=== WRITE OANDA TRADING POLICY ==="
cat > data/registries/oanda_trading_floor_policy.json <<'JSON'
{
  "policy": "oanda_trading_floor_v1",
  "version": "1.0",
  "floor": "floor_41",
  "department": "OANDA Trading Floor",
  "environment": "practice",
  "base_url_practice": "https://api-fxpractice.oanda.com",
  "base_url_live": "https://api-fxtrade.oanda.com",
  "selected_base_url": "https://api-fxpractice.oanda.com",
  "credentials_source": "environment_variables_only",
  "required_env": [
    "OANDA_API_TOKEN",
    "OANDA_ACCOUNT_ID"
  ],
  "default_instruments": [
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "XAU_USD"
  ],
  "account_read_enabled": true,
  "pricing_read_enabled": true,
  "paper_trading_enabled": true,
  "local_model_commentary_enabled": true,
  "live_trading_enabled": false,
  "order_execution_enabled": false,
  "practice_order_execution_enabled": false,
  "worker_execution_enabled": false,
  "provider_execution_enabled": false,
  "external_provider_execution_enabled": false,
  "openclaw_execution_enabled": false,
  "autonomous_dispatch_enabled": false,
  "live_dispatch_enabled": false,
  "direct_provider_access": false,
  "risk_mode": "observe_and_simulate_only",
  "notes": "Floor 41 may read OANDA practice account/pricing data and generate local-only commentary. It must not place live or practice orders until a later explicit activation phase."
}
JSON

echo
echo "=== CREATE OANDA GATEWAY ==="
cat > src/tower/oanda_gateway.py <<'PY'
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
PY

echo
echo "=== CREATE OANDA TRADING FLOOR MODULE ==="
cat > src/tower/oanda_trading_floor.py <<'PY'
#!/usr/bin/env python3
"""
QSB Tower V1.3 — Floor 41 OANDA Trading Floor

V1 capabilities:
- OANDA practice status.
- Account/pricing snapshot if credentials exist.
- Local-only commentary through the existing kernel chat/local model layer.
- Paper/simulation only.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

from tower.oanda_gateway import OANDAGateway

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return fallback


class OANDATradingFloor:
    def __init__(self):
        self.gateway = OANDAGateway()

    def dashboard(self):
        status = self.gateway.status()
        latest = load_json(REG / "oanda_trading_floor_latest_snapshot.json", {})

        return {
            "floor": "floor_41",
            "department": "OANDA Trading Floor",
            "status": "healthy" if status.get("ready_for_account_read") else "waiting_for_credentials",
            "mode": "practice_read_only_simulation",
            "environment": "practice",
            "local_model_commentary_enabled": True,
            "account_ready": status.get("ready_for_account_read"),
            "pricing_ready": status.get("ready_for_pricing_read"),
            "paper_trading_enabled": True,
            "live_trading_enabled": False,
            "order_execution_enabled": False,
            "practice_order_execution_enabled": False,
            "worker_execution_enabled": False,
            "provider_execution_enabled": False,
            "openclaw_execution_enabled": False,
            "autonomous_dispatch_enabled": False,
            "latest_snapshot_ts": latest.get("snapshot_ts"),
            "latest_errors": latest.get("errors", []),
            "updated_ts": datetime.now(timezone.utc).isoformat()
        }

    def snapshot(self, instruments=None):
        return self.gateway.snapshot(instruments)


def dashboard():
    return OANDATradingFloor().dashboard()


if __name__ == "__main__":
    print(json.dumps(dashboard(), indent=2))
PY

echo
echo "=== UPDATE FLOOR 41 IN FLOORS REGISTRY IF PRESENT ==="
python3 - <<'PY'
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
p = ROOT / "data/registries/floors.json"

if not p.exists():
    print("floors.json not found; skipping registry update")
    raise SystemExit(0)

data = json.loads(p.read_text())

changed = False
if isinstance(data, list):
    for floor in data:
        if isinstance(floor, dict) and floor.get("number") == 41:
            floor.update({
                "id": "floor_41",
                "number": 41,
                "department": "OANDA Trading Floor",
                "zone": "ZONE C",
                "status": "occupied",
                "vacant": False,
                "active": True,
                "description": "OANDA practice trading research, pricing intake, local model commentary, and paper simulation.",
                "worker_execution_enabled": False,
                "provider_execution_enabled": False,
                "openclaw_execution_enabled": False,
                "autonomous_dispatch_enabled": False,
                "live_trading_enabled": False,
                "order_execution_enabled": False,
                "updated_ts": datetime.now(timezone.utc).isoformat()
            })
            changed = True

if changed:
    p.write_text(json.dumps(data, indent=2))
    print("Updated Floor 41 in floors.json to OANDA Trading Floor.")
else:
    print("Floor 41 record not found or registry format unexpected; skipped.")
PY

echo
echo "=== CREATE STATUS/SNAPSHOT SCRIPTS ==="
cat > scripts/oanda_trading_floor_status.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

echo "======================================================"
echo "  QSB Tower V1.3 — Floor 41 OANDA Trading Floor Status"
echo "======================================================"
python3 - <<'PY'
from tower.oanda_trading_floor import OANDATradingFloor
import json
print(json.dumps(OANDATradingFloor().dashboard(), indent=2))
PY
echo "======================================================"
SH2
chmod +x scripts/oanda_trading_floor_status.sh

cat > scripts/oanda_trading_floor_snapshot.sh <<'SH2'
#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

INSTRUMENTS="${1:-EUR_USD,GBP_USD,USD_JPY,XAU_USD}"

python3 - <<PY
from tower.oanda_trading_floor import OANDATradingFloor
import json
print(json.dumps(OANDATradingFloor().snapshot("$INSTRUMENTS"), indent=2))
PY
SH2
chmod +x scripts/oanda_trading_floor_snapshot.sh

echo
echo "=== CREATE TEST ==="
cat > tests/test_oanda_trading_floor_v1.py <<'PY'
import sys
import py_compile
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "src"))

for rel in [
    "src/tower/oanda_gateway.py",
    "src/tower/oanda_trading_floor.py",
]:
    py_compile.compile(str(ROOT / rel), doraise=True)

from tower.oanda_trading_floor import OANDATradingFloor

d = OANDATradingFloor().dashboard()

assert d["floor"] == "floor_41"
assert d["department"] == "OANDA Trading Floor"
assert d["environment"] == "practice"
assert d["paper_trading_enabled"] is True
assert d["live_trading_enabled"] is False
assert d["order_execution_enabled"] is False
assert d["practice_order_execution_enabled"] is False
assert d["worker_execution_enabled"] is False
assert d["provider_execution_enabled"] is False
assert d["openclaw_execution_enabled"] is False
assert d["autonomous_dispatch_enabled"] is False

print("OANDA TRADING FLOOR V1 TEST PASSED")
print("  Status:", d["status"])
print("  Account ready:", d["account_ready"])
print("  Pricing ready:", d["pricing_ready"])
print("  Live trading:", d["live_trading_enabled"])
print("  Order execution:", d["order_execution_enabled"])
PY

echo
echo "=== RUN TESTS ==="
python3 -m py_compile src/tower/oanda_gateway.py
python3 -m py_compile src/tower/oanda_trading_floor.py
python3 tests/test_oanda_trading_floor_v1.py

echo
echo "=== STATUS ==="
./scripts/oanda_trading_floor_status.sh

echo
echo "======================================================"
echo "  FLOOR 41 OANDA TRADING FLOOR V1 INSTALLED"
echo "======================================================"
echo "Next:"
echo "  export OANDA_API_TOKEN='your_practice_token'"
echo "  export OANDA_ACCOUNT_ID='your_practice_account_id'"
echo "  ./scripts/oanda_trading_floor_snapshot.sh EUR_USD,GBP_USD,USD_JPY"
echo
echo "Live trading and order execution remain disabled."
echo "======================================================"
