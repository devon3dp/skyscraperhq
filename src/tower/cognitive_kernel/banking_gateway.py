"""BankingGateway — SCAFFOLD for future real-money providers.

This module is the DESIGN DOC for the future real-money phase. It does
not call any API, store any credential, or initiate any transfer. It
exists so that when Ross is ready to add real bank accounts in a
SEPARATE Claude session, that session has a precise specification of:

  · which providers are supported
  · which environment variables each provider expects
  · which OAuth scopes / API permissions are required
  · which kill-switch endpoints must exist before payouts are enabled
  · which audit-log records must be written per transaction
  · which reconciliation cadence the provider expects

Hard guarantees (every payload):
  · payments_enabled                       = False
  · external_api_calls_enabled             = False
  · provider_credentials_present           = False
  · real_money_withdrawal_enabled          = False
  · real_money_deposit_enabled             = False
  · kernel_initiates_money_transfer        = False

The gateway never sees a credential. If a future phase wires real
providers, it does NOT write the credentials into this registry —
they live in environment / secret store / OS keychain only.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

from . import write_registry, append_log, now, SAFETY


@dataclass
class ProviderSpec:
    name: str
    kind: str                          # 'bank' | 'payment_processor' | 'card_processor'
    homepage: str
    onboarding_requirements: List[str]
    env_vars_required: List[str]        # names only, never values
    api_permissions_required: List[str]
    deposit_supported: bool
    withdrawal_supported: bool
    reconciliation_cadence: str         # 'daily' / 'realtime' / 'monthly_statement'
    kill_switch_method: str             # human-readable description
    estimated_lead_time: str
    notes: str = ""


# All gates default-LOCKED. The real-money phase flips these per provider
# AFTER credentials are independently verified out-of-band.
PROVIDERS: List[ProviderSpec] = [
    ProviderSpec(
        name="Halifax",
        kind="bank",
        homepage="https://www.halifax.co.uk",
        onboarding_requirements=[
            "Personal or business account already open with Halifax.",
            "Open Banking enrolment via Halifax Mobile Banking app.",
            "Consent token obtained via UK Open Banking flow.",
            "Account number + sort code captured ONCE during setup.",
        ],
        env_vars_required=[
            "QSB_HALIFAX_OPEN_BANKING_CLIENT_ID",
            "QSB_HALIFAX_OPEN_BANKING_CLIENT_SECRET",
            "QSB_HALIFAX_OPEN_BANKING_CONSENT_TOKEN",
            "QSB_HALIFAX_ACCOUNT_REF",      # masked tail only on the registry
        ],
        api_permissions_required=[
            "ReadAccountsBasic",
            "ReadBalances",
            "ReadTransactionsBasic",
            "ReadTransactionsDetail",
            "ReadDirectDebits",
            "(Payments scope ONLY if outbound transfers are required — "
            "do NOT enable for read-only reconciliation.)",
        ],
        deposit_supported=True,
        withdrawal_supported=True,
        reconciliation_cadence="daily",
        kill_switch_method=("Revoke Open Banking consent in Halifax app + "
                              "delete the consent token env var. Both must "
                              "succeed in < 30 seconds."),
        estimated_lead_time="3-5 business days for Open Banking enrolment",
        notes=("UK Open Banking is the only sanctioned path for "
                "programmatic Halifax access. Screen-scraping is "
                "forbidden by Halifax T&Cs."),
    ),
    ProviderSpec(
        name="Square",
        kind="payment_processor",
        homepage="https://squareup.com",
        onboarding_requirements=[
            "Square account opened + verified.",
            "Square Developer application created (https://developer.squareup.com).",
            "OAuth app created OR personal Access Token issued (sandbox first).",
            "Webhook endpoint registered for payment notifications.",
        ],
        env_vars_required=[
            "QSB_SQUARE_APPLICATION_ID",
            "QSB_SQUARE_ACCESS_TOKEN",         # sandbox token to start
            "QSB_SQUARE_LOCATION_ID",
            "QSB_SQUARE_WEBHOOK_SIGNATURE_KEY",
            "QSB_SQUARE_ENV",                   # 'sandbox' | 'production'
        ],
        api_permissions_required=[
            "PAYMENTS_READ",
            "PAYMENTS_WRITE (only if listing publishing flips on)",
            "ORDERS_READ",
            "MERCHANT_PROFILE_READ",
            "BANK_ACCOUNTS_READ",
        ],
        deposit_supported=True,         # customer charges become deposits
        withdrawal_supported=False,     # withdrawals go to linked bank, not via Square API
        reconciliation_cadence="realtime",
        kill_switch_method=("Disable the OAuth token in Square dashboard. "
                              "Confirm withdrawal in Webhook log within 30 seconds."),
        estimated_lead_time="1-2 business days for sandbox; longer for production",
        notes=("Square is the recommended path for COMMERCE-floor payments "
                "(Etsy alternative; integrate Square Online Store for the "
                "Floor 46 catalog). Start in sandbox. Production gate is "
                "FLIPPED ONLY by operator out-of-band."),
    ),
]


PROVIDER_GATES_TEMPLATE = {
    "payments_enabled":                  False,
    "external_api_calls_enabled":        False,
    "provider_credentials_present":      False,
    "real_money_withdrawal_enabled":     False,
    "real_money_deposit_enabled":        False,
    "kernel_initiates_money_transfer":   False,
    "sandbox_mode_only":                 True,
    "kill_switch_verified":              False,
    "reconciliation_path_verified":      False,
    "double_entry_ledger_present":       False,
}


def snapshot() -> Dict[str, Any]:
    return {
        "ok": True,
        "kind": "cognitive_banking_gateway_scaffold",
        "generated_ts": now(),
        "policy": (
            "SCAFFOLD ONLY. No credentials stored. No API calls made. "
            "No money moved. Real-money wiring is a SEPARATE Claude "
            "session with operator-supplied credentials, after which "
            "specific gates may be flipped per provider."
        ),
        "safety_envelope": dict(SAFETY),
        "global_gates": dict(PROVIDER_GATES_TEMPLATE),
        "provider_count": len(PROVIDERS),
        "providers": [asdict(p) for p in PROVIDERS],
        "future_phase_checklist": [
            "1. Open a fresh Claude session with: 'wire real-money phase'",
            "2. That session reads cognitive_banking_gateway_scaffold.json.",
            "3. Operator exports the env_vars_required for the chosen provider "
            "INTO THE SHELL of the session (never into a registry / chat).",
            "4. That session builds the provider adapter (one file per provider). "
            "Adapter respects sandbox_mode_only=True initially.",
            "5. Operator runs reconciliation against the provider's statement; "
            "confirms 1:1 match.",
            "6. Operator flips reconciliation_path_verified=True only after "
            "successful match.",
            "7. Operator flips kill_switch_verified=True only after firing the "
            "kill switch and confirming new payouts are blocked < 30s.",
            "8. Operator flips real_money_deposit_enabled=True (deposits first; "
            "withdrawals later).",
            "9. The Kernel may then OBSERVE balances + propose payouts; "
            "kernel_initiates_money_transfer stays False forever — every "
            "withdrawal requires an operator-typed code from a separate "
            "channel (phone, hardware key).",
        ],
        "what_kernel_will_NEVER_do": [
            "store, log, or emit credentials of any kind",
            "initiate a money transfer on its own",
            "approve a withdrawal proposal — those need an out-of-band code",
            "trust a registry that was edited by hand without a fresh "
            "reconciliation",
        ],
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_banking_gateway_scaffold.json", snap)
    append_log("banking_gateway.jsonl", {
        "event": "scaffold_snapshot",
        "provider_count": snap["provider_count"],
        "gates_all_locked": all(not v for k, v in snap["global_gates"].items()
                                  if not k.endswith("_only")),
    })
    return snap
