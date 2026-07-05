"""Floor 46 — Commerce Wing (Etsy preview-only).

This floor scaffolds a digital storefront workflow WITHOUT publishing,
charging, or contacting Etsy in any way. Everything is:

  · sandbox catalog
  · listing drafts (never sent to a marketplace)
  · pricing analytics
  · advisory proposals to the operator

Hard locks (every payload reasserts):
  · live_listings_publishing_enabled = False
  · payments_enabled                 = False
  · external_api_calls_enabled       = False
  · openclaw_real_tool_execution_enabled = False

To enable real publishing later, the operator must explicitly flip
FLAGS["live_listings_publishing_enabled"] AND wire a publisher worker;
neither happens automatically.
"""

from .catalog import (
    SANDBOX_PRODUCTS,
    SandboxProduct,
    catalog_snapshot,
    persist_catalog,
)
from .pricing import (
    PricingAdvisor,
    pricing_advisor,
)
from .state import (
    FLAGS,
    floor_state_snapshot,
    persist_floor_state,
    tick,
)

__all__ = [
    "SANDBOX_PRODUCTS", "SandboxProduct",
    "catalog_snapshot", "persist_catalog",
    "PricingAdvisor", "pricing_advisor",
    "FLAGS", "floor_state_snapshot", "persist_floor_state", "tick",
]
