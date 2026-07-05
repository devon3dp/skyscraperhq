"""
QSB Skyscraper Full Occupancy + Commerce Wing + 1000-Worker Expansion
Phase: QSB_FULL_SKYSCRAPER_OCCUPANCY_COMMERCE_WORKFORCE_EXPANSION_V1

One module that emits the full set of registries described in the
phase brief. Idempotent — safe to re-run. No real-money writes, no
listing publication, no live API calls. All commerce is documented in
"safe mode" with manual_approval_required=true.

Build targets are selectable via main() argv so each script wrapper
can call its specific slice without duplicating logic.
"""

from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
import json
import sys

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

PHASE = "QSB_FULL_SKYSCRAPER_OCCUPANCY_COMMERCE_WORKFORCE_EXPANSION_V1"
EQSB_EVENTS = LOGS / "eqsb_kernel_events.jsonl"
EQSB_HISTORY = LOGS / "eqsb_phase_history.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safety():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "real_money_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
        "worker_execution_enabled": False,
        "autonomous_dispatch_enabled": False,
        "live_payments_enabled": False,
        "live_listings_publishing_enabled": False,
        "external_api_calls_enabled": False,
        "secrets_in_logs": False,
        "manual_approval_required_for_commerce": True,
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


def _stable_idx(seed, modulo):
    if modulo <= 0:
        return 0
    return int.from_bytes(
        blake2b(str(seed).encode("utf-8"), digest_size=4).digest(),
        "big"
    ) % modulo


# ── Floor catalog (commerce + training + rest layers added on top) ───
# Each entry: floor, primary (existing dept), secondary (new role from
# this phase), purpose, profit/kernel/safety contribution flags,
# manager role, team_size, rooms.


FLOOR_PLAN = [
    # Lower commerce / order fulfilment block
    {"floor": 1,  "primary": "Operations",          "secondary": "Order Fulfilment Hub",
     "purpose": "physical/digital order fulfilment dispatch", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Order Intake", "Dispatch Desk", "Fulfilment Ledger",
       "Quality Check", "Returns Desk"], "team_size": 35},
    {"floor": 2,  "primary": "Memory",              "secondary": "Customer Memory Vault",
     "purpose": "customer history + repeat-purchase memory",  "profit": True,
     "kernel": True,  "safety": True, "rest": False, "rooms": [
       "Customer Profiles Vault", "Purchase History Archive",
       "Loyalty Ledger", "Memory Retention Desk"], "team_size": 18},
    {"floor": 3,  "primary": "Research",            "secondary": "Product Research Lab",
     "purpose": "commerce + product research", "profit": True,
     "kernel": True, "safety": False, "rest": False, "rooms": [
       "Trend Watch Desk", "Competitor Research Desk",
       "Pricing Research Desk", "Niche Discovery Desk",
       "Demand Signal Wall"], "team_size": 30},
    {"floor": 4,  "primary": "Knowledge",           "secondary": "Knowledge Library + Classroom Wing",
     "purpose": "training resources + classroom content", "profit": False,
     "kernel": True, "safety": False, "rest": False, "rooms": [
       "Curriculum Library", "Teacher Office", "Study Carrels",
       "Certification Records"], "team_size": 20},
    {"floor": 5,  "primary": "Coding",              "secondary": "Code Observatory + Dev Squad",
     "purpose": "claude-change tracking + repo health", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Code Review Desk", "Phase History Wall",
       "Refactor Queue", "Test Runner Bench"], "team_size": 15},
    {"floor": 6,  "primary": "Engineering",         "secondary": "Etsy Shop Floor",
     "purpose": "digital products listing pipeline (manual approval)", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Etsy Shop Manager Office", "Product Research Desk",
       "Digital Product Studio", "Listing Writer Desk",
       "SEO / Tags Desk", "Pricing Desk", "Image Preview Wall",
       "Customer Message Desk", "Order Monitor", "Revenue Ledger",
       "Compliance Review Desk"], "team_size": 32},
    {"floor": 7,  "primary": "Architecture",        "secondary": "Shopify Storefront Floor",
     "purpose": "direct storefront design + theme work", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Theme Studio", "Cart Logic Desk", "Storefront Audit",
       "Webhook Listener Desk", "Compliance Review"], "team_size": 22},
    {"floor": 8,  "primary": "Training Academy",    "secondary": "Trading + Commerce Classrooms",
     "purpose": "curriculum + cohort teaching", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Trading Classroom", "Commerce Classroom",
       "Etsy Classroom", "Print-on-Demand Classroom",
       "3D Printing Classroom", "SEO / Listing Classroom",
       "Prompt Engineering Lab", "Teacher Lounge",
       "Certification Board"], "team_size": 48},
    {"floor": 9,  "primary": "Quality Assurance",   "secondary": "Design Quality Review + Mistake Lab",
     "purpose": "design QA + lessons-from-mistakes review", "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Design Quality Review Room", "Mistake Review Room",
       "Lessons Room", "QA Sign-off Desk"], "team_size": 22},
    {"floor": 10, "primary": "Trading Simulation",  "secondary": "Strategy Lab + Sandbox Coupling",
     "purpose": "extend Floor 38 sandbox with strategy scenarios", "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Scenario Lab", "Counter-Strategy Bench",
       "Walk-Forward Test Pit", "Simulation Result Wall"], "team_size": 25},
    {"floor": 11, "primary": "Market Intelligence", "secondary": "Demand + Competitor Watch",
     "purpose": "cross-platform demand watching", "profit": True,
     "kernel": False, "safety": False, "rest": False, "rooms": [
       "Demand Watch Desk", "Competitor Watch Desk",
       "Trend Signal Wall", "Pricing Intel Desk"], "team_size": 24},
    {"floor": 12, "primary": "Risk Analysis",       "secondary": "Commerce + Trading Risk Bench",
     "purpose": "unified risk view across trading + commerce", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Trading Risk Bench", "Commerce Risk Bench",
       "Risk Threshold Desk", "Kill-Switch Console"], "team_size": 20},
    {"floor": 13, "primary": "Vision",              "secondary": "Product Image Studio + Mockup Wall",
     "purpose": "mockup + product image previews", "profit": True,
     "kernel": False, "safety": False, "rest": False, "rooms": [
       "Mockup Studio", "Image Preview Wall",
       "Product Photography Set", "Asset Library"], "team_size": 18},
    {"floor": 14, "primary": "Media",               "secondary": "Print-on-Demand Floor",
     "purpose": "POD product design + Printful/Printify drafts", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Design Intake", "Product Mockup Desk",
       "Printful/Printify Integration Desk", "Quality Check",
       "Fulfilment Monitor", "Order Ledger"], "team_size": 28},
    {"floor": 15, "primary": "Speech & Audio",      "secondary": "Voice Commerce Studio",
     "purpose": "audio narration + customer voice replies (draft only)", "profit": False,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Voice Narrator Desk", "Customer Voice Drafts",
       "Audio QA"], "team_size": 12},
    {"floor": 16, "primary": "Document Processing", "secondary": "Listing Writer + SEO Lab",
     "purpose": "listing copy + SEO + tags", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Listing Writer Desk", "SEO Lab", "Keyword Vault",
       "Tag Optimizer", "Compliance Review"], "team_size": 22},
    {"floor": 17, "primary": "Graphics & Design",   "secondary": "Product Design Studio + Prompt-to-Product",
     "purpose": "design asset generation + prompt iteration", "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Design Studio", "Prompt Engineering Lab",
       "Asset Vault", "Style Guide Wall",
       "Design Quality Review"], "team_size": 30},
    {"floor": 18, "primary": "Automation",          "secondary": "Marketing + Promotion Floor",
     "purpose": "campaign drafts + scheduled posts (manual approval)", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Campaign Draft Desk", "Schedule Board",
       "Newsletter Studio", "Promotion Compliance"], "team_size": 22},
    {"floor": 19, "primary": "Workflow Management", "secondary": "Customer Service Floor",
     "purpose": "customer messaging drafts + ticket triage", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Ticket Triage", "Message Draft Desk",
       "Refund Negotiation Desk", "Escalation Bench",
       "Customer Sentiment Wall"], "team_size": 28},
    {"floor": 20, "primary": "API Services",        "secondary": "Platform Integration Bench",
     "purpose": "API watchers + integration health (test/sandbox only)", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Etsy API Sandbox", "Shopify API Sandbox",
       "Printful API Sandbox", "Webhook Sandbox",
       "Integration Health Wall"], "team_size": 20},
    {"floor": 21, "primary": "Adapter Systems",     "secondary": "Format / Schema Translation",
     "purpose": "data format translation between commerce + kernel", "profit": False,
     "kernel": True, "safety": False, "rest": False, "rooms": [
       "Schema Bench", "Format Translator",
       "Validation Desk"], "team_size": 12},
    {"floor": 22, "primary": "Integration Services","secondary": "Lifts Department Operations",
     "purpose": "lift + sealed-packet routing", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Lift Dispatch", "Packet Router Bench",
       "Lift Maintenance"], "team_size": 14},
    {"floor": 23, "primary": "AIR LLM Operations",  "secondary": "AirLLM Chamber",
     "purpose": "local model advisory only", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Model Chamber", "Prompt Buffer", "Advisory Out"],
     "team_size": 10},
    {"floor": 24, "primary": "Model Routing",       "secondary": "Lane Governance",
     "purpose": "route prompts between local lanes", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Routing Console", "Lane Governance"], "team_size": 10},
    {"floor": 25, "primary": "Agent Coordination",  "secondary": "OpenClaw Coordination Office",
     "purpose": "openclaw read-only supervision dispatch", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Inspection Dispatch", "Ticket Coordination",
       "Finding Archive"], "team_size": 12},
    {"floor": 26, "primary": "Model Evaluation",    "secondary": "Commerce Accounting Floor",
     "purpose": "commerce PnL + tax-ready ledger", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Commerce PnL Desk", "Sales Ledger",
       "Tax-Ready Export", "Refund Accounting",
       "Platform Fee Tracker"], "team_size": 22},
    {"floor": 27, "primary": "Local Model Ops",     "secondary": "Local Model Drafting Bench",
     "purpose": "local-only LLM draft surfaces", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Drafting Bench", "Local Model Console"], "team_size": 8},
    {"floor": 28, "primary": "Security",            "secondary": "Security Operations Center",
     "purpose": "security observability + secret vault audit", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "SecOps Console", "Vault Audit", "Access Log Wall",
       "Incident Bench"], "team_size": 18},
    {"floor": 29, "primary": "Guardian",            "secondary": "Guardian Watch",
     "purpose": "guardian state + lock map watch", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Lock Map Console", "Guardian Watch",
       "Drift Alarm"], "team_size": 12},
    {"floor": 30, "primary": "Permissions",         "secondary": "Permissions / Risk Department",
     "purpose": "13-lock execution permissions", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Permissions Desk", "Risk Review",
       "Lock Audit", "Approval Workflow Bench"], "team_size": 18},
    {"floor": 31, "primary": "Audit",               "secondary": "Audit / Ledger Department",
     "purpose": "ledger fan-in + audit reports", "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Ledger Dispatch", "Audit Trail Wall",
       "Compliance Bench", "Sealed-Packet Receiver"], "team_size": 20},
    {"floor": 32, "primary": "Compliance",          "secondary": "Platform Compliance Office",
     "purpose": "platform terms + compliance checklists", "profit": False,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Etsy Compliance Desk", "Shopify Compliance Desk",
       "Print Platforms Compliance Desk",
       "Terms Tracking Wall", "Compliance Audit"],
     "team_size": 16},
    {"floor": 33, "primary": "Diagnostics",         "secondary": "Refund / Dispute Desk + Diagnostics",
     "purpose": "refund handling + system diagnostics", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Refund Intake", "Dispute Negotiation",
       "Diagnostics Console", "Service Health Wall"], "team_size": 16},
    {"floor": 34, "primary": "Monitoring",          "secondary": "Storefront Analytics Room",
     "purpose": "cross-store analytics + telemetry", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Storefront Analytics", "Conversion Funnel Wall",
       "Telemetry Console", "Alert Bench"], "team_size": 18},
    {"floor": 35, "primary": "Infrastructure Svcs", "secondary": "Hardware Systems Floor",
     "purpose": "CPU/GPU/RAM/disk observatory", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Hardware Observatory", "Resource Console",
       "Service Monitor Bench"], "team_size": 14},
    {"floor": 36, "primary": "Expansion Planning",  "secondary": "Workforce Expansion Planning",
     "purpose": "workforce expansion + onboarding plans", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Expansion Desk", "Onboarding Track",
       "Department Growth Plan"], "team_size": 18},
    {"floor": 37, "primary": "Simulation Labs",     "secondary": "Strategy Labs",
     "purpose": "strategy scenarios + backtesting", "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Strategy Scenario Lab", "Backtest Bench",
       "Walk-Forward Lab"], "team_size": 22},
    {"floor": 38, "primary": "Sandbox Operations",  "secondary": "Sandbox Ops Coupling",
     "purpose": "sandbox lift packets + market sim",   "profit": True,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Sandbox Console", "Lift Packet Dispatch",
       "Sandbox Audit"], "team_size": 16},
    {"floor": 39, "primary": "Development Labs",    "secondary": "Worker Recreation Floor",
     "purpose": "recreation + recovery after shifts", "profit": False,
     "kernel": False, "safety": False, "rest": True, "rooms": [
       "Break Room", "Game Room", "Morale Board",
       "Coffee Bar", "Wellness Monitor"], "team_size": 20},
    {"floor": 40, "primary": "Prototype Systems",   "secondary": "Worker Rest / Dormitory Floor",
     "purpose": "sleep pods + standby for off-shift workers", "profit": False,
     "kernel": False, "safety": True, "rest": True, "rooms": [
       "Sleep Pods", "Standby Lounge",
       "Quiet Recovery Room", "Shift Change Desk"], "team_size": 25},
    {"floor": 41, "primary": "OANDA Trading Floor", "secondary": "OANDA Practice Trading",
     "purpose": "FX paper/practice trading",          "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "OANDA — already populated by qsb_floor41_oanda module"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 42, "primary": "Binance Trading",     "secondary": "Binance Testnet Preview",
     "purpose": "crypto testnet preview only",      "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Binance — already populated by qsb_floor42_binance module"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 43, "primary": "Stock Exchange",      "secondary": "Stocks Paper Preview",
     "purpose": "equities paper preview only",      "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "Stocks — already populated by qsb_floor43_stocks module"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 44, "primary": "Accounts Department", "secondary": "Trading + Commerce Accounting",
     "purpose": "PnL ledger for trading + commerce", "profit": True,
     "kernel": False, "safety": True, "rest": False, "rooms": [
       "PnL Ledger", "Trade Accounting Desk",
       "Loss Review", "Reward Accounting",
       "Commerce Revenue Desk"], "team_size": 24},
    {"floor": 45, "primary": "Recruitment Agency",  "secondary": "Worker Recruitment",
     "purpose": "candidate intake + assignment",  "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Recruitment — already populated"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 46, "primary": "Executive Support",   "secondary": "Executive Liaison + Concierge",
     "purpose": "executive support + colonel concierge",  "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Colonel Concierge", "Executive Briefing Room",
       "VIP Reception"], "team_size": 16},
    {"floor": 47, "primary": "Executive Operations","secondary": "Executive Ops Department",
     "purpose": "executive operations + governance", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Executive Ops — already populated"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 48, "primary": "Strategic Planning",  "secondary": "Strategic Plan Office",
     "purpose": "long-term planning + roadmap", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Plan Desk", "Roadmap Wall", "Quarterly Review"],
     "team_size": 14},
    {"floor": 49, "primary": "Resource Management", "secondary": "Resource Mgmt Department",
     "purpose": "resource allocation",              "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Resource Mgmt — already populated"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 50, "primary": "Building Governance", "secondary": "Building Governance Council",
     "purpose": "building rules + governance", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Governance Council", "Rule Book Library"],
     "team_size": 12},
    {"floor": 51, "primary": "Executive Council",   "secondary": "Executive Council Office",
     "purpose": "executive council convenings", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Council Chamber"], "team_size": 10},
    {"floor": 52, "primary": "Infrastructure Cmd",  "secondary": "Infrastructure Command",
     "purpose": "infrastructure command",           "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Infrastructure — already populated"],
     "team_size": 0, "preserve_existing": True},
    {"floor": 53, "primary": "Tower Command",       "secondary": "Tower Command Department",
     "purpose": "tower command + colonel observation", "profit": False,
     "kernel": True, "safety": True, "rest": False, "rooms": [
       "Tower Command — already populated"],
     "team_size": 0, "preserve_existing": True},
]


# Roles per secondary department type
ROLE_TEMPLATES = {
    "Etsy Shop Floor": [
        ("etsy_floor_manager", "Etsy Floor Manager",      1),
        ("etsy_dept_manager",  "Etsy Department Manager", 1),
        ("etsy_product_seer",  "Product Research Seer",   3),
        ("etsy_listing_writer","Listing Writer",          4),
        ("etsy_seo_clerk",     "SEO Clerk",                3),
        ("etsy_image_designer","Digital Image Designer",   4),
        ("etsy_mockup_creator","Mockup Creator",           3),
        ("etsy_pricing_analyst","Pricing Analyst",         2),
        ("etsy_customer_clerk","Customer Service Clerk",  3),
        ("etsy_order_watcher", "Order Watcher",            2),
        ("etsy_revenue_acct",  "Revenue Accountant",       2),
        ("etsy_compliance",    "Compliance Watcher",       2),
        ("etsy_openclaw_insp", "OpenClaw Etsy Inspector",  1),
        ("etsy_trainee",       "Etsy Trainee",             1),
    ],
    "Shopify Storefront Floor": [
        ("shop_floor_manager",  "Shopify Floor Manager",      1),
        ("shop_theme_designer", "Theme Designer",             3),
        ("shop_cart_engineer",  "Cart Logic Engineer",        3),
        ("shop_storefront_aud", "Storefront Auditor",         2),
        ("shop_webhook_clerk",  "Webhook Listener Clerk",     2),
        ("shop_compliance",     "Shopify Compliance Watcher", 2),
        ("shop_openclaw_insp",  "OpenClaw Shopify Inspector", 1),
        ("shop_trainee",        "Shopify Trainee",            8),
    ],
    "Trading + Commerce Classrooms": [
        ("class_teacher_lead",  "Lead Teacher",                2),
        ("class_trading_teacher","Trading Teacher",            4),
        ("class_commerce_teacher","Commerce Teacher",           4),
        ("class_etsy_teacher",  "Etsy Teacher",                3),
        ("class_pod_teacher",   "POD Teacher",                 3),
        ("class_3dprint_teacher","3D Printing Teacher",        3),
        ("class_seo_teacher",   "SEO/Listing Teacher",         3),
        ("class_prompt_teacher","Prompt Engineering Teacher", 3),
        ("class_mentor",        "Worker Mentor",               4),
        ("class_certifier",     "Certification Officer",       2),
        ("class_student",       "Cohort Student",              17),
    ],
    "Print-on-Demand Floor": [
        ("pod_floor_manager",   "POD Floor Manager",           1),
        ("pod_design_intake",   "Design Intake Clerk",         2),
        ("pod_mockup_creator",  "Mockup Creator",              4),
        ("pod_printful_clerk",  "Printful Integration Clerk",  2),
        ("pod_printify_clerk",  "Printify Integration Clerk",  2),
        ("pod_qc",              "POD Quality Check",           3),
        ("pod_fulfilment_mon",  "Fulfilment Monitor",          3),
        ("pod_ledger_clerk",    "POD Order Ledger Clerk",      2),
        ("pod_openclaw_insp",   "OpenClaw POD Inspector",      1),
        ("pod_trainee",         "POD Trainee",                 8),
    ],
    "Order Fulfilment Hub": [
        ("ful_floor_manager",   "Fulfilment Floor Manager",   1),
        ("ful_intake_clerk",    "Order Intake Clerk",          5),
        ("ful_dispatch_clerk",  "Dispatch Clerk",              5),
        ("ful_ledger_clerk",    "Fulfilment Ledger Clerk",     3),
        ("ful_qc",              "Quality Check Worker",        4),
        ("ful_returns_clerk",   "Returns Desk Clerk",          3),
        ("ful_openclaw_insp",   "OpenClaw Fulfilment Insp.",   1),
        ("ful_trainee",         "Fulfilment Trainee",          13),
    ],
    "Customer Service Floor": [
        ("cs_floor_manager",    "Customer Service Manager",   1),
        ("cs_ticket_triager",   "Ticket Triager",              4),
        ("cs_message_drafter",  "Customer Message Drafter",    5),
        ("cs_refund_clerk",     "Refund Negotiation Clerk",    3),
        ("cs_escalation",       "Escalation Officer",          2),
        ("cs_sentiment_seer",   "Customer Sentiment Seer",     2),
        ("cs_openclaw_insp",    "OpenClaw CS Inspector",       1),
        ("cs_trainee",          "Customer Service Trainee",    10),
    ],
    "Product Research Lab": [
        ("pr_lab_manager",      "Product Research Lab Mgr",    1),
        ("pr_trend_watcher",    "Trend Watcher",               4),
        ("pr_competitor_seer",  "Competitor Seer",             4),
        ("pr_pricing_analyst",  "Pricing Analyst",             3),
        ("pr_niche_seer",       "Niche Discovery Seer",        3),
        ("pr_demand_seer",      "Demand Signal Seer",          3),
        ("pr_openclaw_insp",    "OpenClaw Research Inspector", 1),
        ("pr_trainee",          "Product Research Trainee",    11),
    ],
    "Listing Writer + SEO Lab": [
        ("ls_lab_manager",      "Listing Lab Manager",         1),
        ("ls_writer",           "Listing Writer",              5),
        ("ls_seo_clerk",        "SEO Clerk",                   4),
        ("ls_keyword_clerk",    "Keyword Optimizer",           3),
        ("ls_tag_optimizer",    "Tag Optimizer",               3),
        ("ls_compliance",       "Listing Compliance",          2),
        ("ls_openclaw_insp",    "OpenClaw Listing Inspector",  1),
        ("ls_trainee",          "Listing Trainee",             3),
    ],
    "Product Design Studio + Prompt-to-Product": [
        ("ds_studio_manager",   "Design Studio Manager",       1),
        ("ds_designer",         "Product Designer",            6),
        ("ds_prompt_engineer",  "Prompt Engineer",             5),
        ("ds_asset_curator",    "Asset Vault Curator",         2),
        ("ds_style_keeper",     "Style Guide Keeper",          2),
        ("ds_qa",               "Design Quality Reviewer",     4),
        ("ds_openclaw_insp",    "OpenClaw Design Inspector",   1),
        ("ds_trainee",          "Design Trainee",              9),
    ],
    "Worker Rest / Dormitory Floor": [
        ("rest_floor_manager",  "Rest Floor Manager",          1),
        ("rest_pod_attendant",  "Sleep Pod Attendant",         4),
        ("rest_standby_host",   "Standby Lounge Host",         3),
        ("rest_quiet_warden",   "Quiet Recovery Warden",       2),
        ("rest_shift_clerk",    "Shift Change Desk Clerk",     3),
        ("rest_resting_worker", "Resting Worker (rotation)",   12),
    ],
    "Worker Recreation Floor": [
        ("rec_floor_manager",   "Recreation Manager",          1),
        ("rec_break_host",      "Break Room Host",             3),
        ("rec_morale_keeper",   "Morale Board Keeper",         2),
        ("rec_wellness_mon",    "Wellness Monitor",            2),
        ("rec_recovering",      "Recovering Worker",           12),
    ],
}


def gen_workers_for_floor(floor_plan):
    """Return list of worker dicts for one floor entry."""
    if floor_plan.get("preserve_existing"):
        return []
    secondary = floor_plan.get("secondary")
    floor = floor_plan.get("floor")
    rooms = floor_plan.get("rooms") or []
    if not rooms:
        return []
    template = ROLE_TEMPLATES.get(secondary)
    workers = []
    counter = 1
    # If no specific template, use a generic Manager + 1 Overseer + N Specialists + Trainees
    if not template:
        size = floor_plan.get("team_size", 12)
        template = [
            ("dept_floor_manager", "Floor Manager",        1),
            ("dept_manager",       "Department Manager",   1),
            ("dept_overseer",      "Department Overseer",  1),
            ("dept_watcher",       "Department Watcher",   2),
            ("dept_seer",          "Department Seer",      2),
            ("dept_specialist",    "Specialist",           max(0, size - 12)),
            ("dept_clerk",         "Clerk",                2),
            ("dept_openclaw_insp", "OpenClaw Inspector",   1),
            ("dept_trainee",       "Trainee",              max(0, size - 12)),
        ]
    for role_key, role_label, count in template:
        for i in range(count):
            wid = "wrk_v2_f{:02d}_{}_{:03d}".format(floor, role_key, counter)
            room = rooms[_stable_idx(wid, len(rooms))]
            station_idx = (_stable_idx(wid + role_key, 24)) + 1
            name = "{} {}".format(role_label, counter)
            manager_role = role_key
            # Manager linkage: managers under floor manager; everyone
            # else under their dept manager or floor manager
            if "floor_manager" in role_key:
                manager_id = "FLOOR_OWNER"
            elif "dept_manager" in role_key or "_manager" in role_key:
                manager_id = "FLOOR_MANAGER"
            else:
                manager_id = "DEPT_MANAGER"
            cls = _classify(role_label)
            workers.append({
                "worker_id": wid,
                "display_name": name,
                "class": cls,
                "department": secondary,
                "floor": floor,
                "team": _team_for(secondary),
                "role": role_label,
                "role_key": role_key,
                "manager": manager_id,
                "room": room,
                "station": "{} · station #{:02d}".format(room, station_idx),
                "current_task": _initial_task(role_label),
                "state": "idle_at_station" if "trainee" in role_key
                          else ("resting" if "rest" in role_key or "recovering" in role_label.lower()
                                else "active"),
                "profit_mission_link": _profit_link(floor_plan),
                "training_status": "trainee" if "trainee" in role_key else "trained",
                "created_ts": _now(),
            })
            counter += 1
    return workers


def _classify(role_label):
    r = role_label.lower()
    if "trainee" in r or "student" in r: return "trainee"
    if "teacher" in r or "instructor" in r: return "teacher"
    if "manager" in r: return "manager"
    if "watcher" in r: return "watcher"
    if "seer" in r: return "seer"
    if "overseer" in r: return "overseer"
    if "analyst" in r: return "analyst"
    if "clerk" in r: return "clerk"
    if "scout" in r: return "scout"
    if "strategist" in r: return "strategist"
    if "auditor" in r: return "auditor"
    if "designer" in r: return "designer"
    if "engineer" in r: return "engineer"
    if "operator" in r: return "operator"
    if "openclaw" in r and "inspector" in r: return "openclaw_inspector"
    if "recovering" in r or "resting" in r: return "resting_worker"
    return "specialist"


def _team_for(secondary):
    secondary_l = (secondary or "").lower()
    if "etsy" in secondary_l: return "etsy_team"
    if "shopify" in secondary_l: return "shopify_team"
    if "print-on-demand" in secondary_l or "pod" in secondary_l: return "pod_team"
    if "3d printing" in secondary_l: return "3d_printing_team"
    if "classroom" in secondary_l: return "teaching_team"
    if "research" in secondary_l: return "research_team"
    if "design" in secondary_l: return "design_team"
    if "fulfilment" in secondary_l: return "fulfilment_team"
    if "customer service" in secondary_l: return "customer_service_team"
    if "rest" in secondary_l or "recreation" in secondary_l: return "rest_team"
    if "audit" in secondary_l: return "audit_team"
    if "compliance" in secondary_l: return "compliance_team"
    if "openclaw" in secondary_l: return "openclaw_team"
    return "department_team"


def _initial_task(role_label):
    r = role_label.lower()
    if "trainee" in r: return "attend onboarding session"
    if "teacher" in r: return "prepare today's lesson"
    if "manager" in r: return "review floor health"
    if "watcher" in r: return "watch signals"
    if "seer" in r: return "interpret data"
    if "writer" in r: return "draft listing copy"
    if "designer" in r: return "prepare design asset"
    if "clerk" in r: return "process queue"
    if "monitor" in r: return "monitor health board"
    if "openclaw" in r: return "inspect floor (read-only)"
    if "recovering" in r or "resting" in r: return "rest"
    return "shift duties"


def _profit_link(plan):
    if plan.get("profit"): return "direct"
    if plan.get("kernel"): return "kernel_evolution"
    if plan.get("safety"): return "safety_support"
    if plan.get("rest"):   return "workforce_recovery"
    return "support"


# ── Audit ──────────────────────────────────────────────────────────


def build_audit():
    floors_reg = _load("floors.json", [])
    rooms_reg = _load("qsb_worker_room_assignments.json", {})
    by_floor_room = rooms_reg.get("by_floor_room") or {}
    existing_workers_by_floor = {}
    # Pull canonical worker counts from existing telemetry if available
    try:
        from tower.qsb_dashboard_live_telemetry import build_live_telemetry
        live = build_live_telemetry()
        for w in (live.get("workers") or []):
            f = w.get("floor") or w.get("home_floor")
            if isinstance(f, int):
                existing_workers_by_floor[f] = existing_workers_by_floor.get(f, 0) + 1
    except Exception:
        pass

    audit = []
    weak = 0
    populated = 0
    for plan in FLOOR_PLAN:
        f = plan["floor"]
        floor_row = next((r for r in floors_reg
                          if isinstance(r, dict) and r.get("number") == f), None)
        canonical_existing = existing_workers_by_floor.get(f, 0)
        new_workers = 0 if plan.get("preserve_existing") else \
            sum(c for _, _, c in (ROLE_TEMPLATES.get(plan.get("secondary"))
                                    or [("x", "x", plan.get("team_size") or 0)]))
        status = "complete" if canonical_existing >= 30 else \
            ("partial" if canonical_existing >= 5 else "weak")
        if status == "weak":
            weak += 1
        else:
            populated += 1
        audit.append({
            "floor_number": f,
            "floor_id": (floor_row or {}).get("id") or "floor_{:02d}".format(f),
            "floor_name": plan["primary"],
            "secondary_department": plan["secondary"],
            "department": plan["primary"],
            "purpose": plan["purpose"],
            "manifest_exists": True,
            "dashboard_visible": True,
            "interior_exists": f in (41, 42, 43, 55) or plan.get("rooms"),
            "manager_exists": True,
            "worker_count_before": canonical_existing,
            "worker_count_new": new_workers,
            "rooms": plan["rooms"],
            "live_data_sources": ["qsb_worker_room_assignments.json",
                                   "qsb_worker_station_assignments.json"],
            "status": status,
            "profit_contribution": plan.get("profit"),
            "kernel_evolution_contribution": plan.get("kernel"),
            "safety_contribution": plan.get("safety"),
            "rest_contribution": plan.get("rest"),
            "recommended_action": "expand" if status == "weak" else "maintain",
        })

    payload = {
        "ok": True,
        "kind": "qsb_full_floor_audit",
        "phase": PHASE,
        "generated_ts": _now(),
        "total_floors": len(audit),
        "weak_floors_count": weak,
        "populated_floors_count": populated,
        "floors": audit,
    }
    payload.update(_safety())
    _write(REG / "qsb_full_floor_audit.json", payload)

    # Markdown log
    md = ["# QSB Full Floor Audit",
           "Phase: %s" % PHASE,
           "Generated: %s" % _now(),
           "",
           "| Floor | Department | Secondary | Status | Workers (before/new) | Purpose |",
           "|-------|-----------|-----------|--------|---------------------|---------|"]
    for a in audit:
        md.append("| F{f} | {p} | {s} | {st} | {wb}/{wn} | {pur} |".format(
            f=a["floor_number"], p=a["floor_name"], s=a["secondary_department"],
            st=a["status"], wb=a["worker_count_before"], wn=a["worker_count_new"],
            pur=a["purpose"]))
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "qsb_full_floor_audit.md").write_text("\n".join(md), encoding="utf-8")
    return payload


# ── Workforce expansion 1000 ──────────────────────────────────────


def build_workforce_1000():
    all_workers = []
    for plan in FLOOR_PLAN:
        workers = gen_workers_for_floor(plan)
        all_workers.extend(workers)
    # Cap at 1000 for the exact phase target — pick deterministically
    # by floor order so distribution stays consistent.
    if len(all_workers) > 1000:
        all_workers = all_workers[:1000]
    # If under, top up with extra rest/standby workers on Floor 40
    while len(all_workers) < 1000:
        idx = len(all_workers) + 1
        wid = "wrk_v2_f40_rest_resting_worker_{:03d}".format(100 + idx)
        all_workers.append({
            "worker_id": wid, "display_name": "Standby Worker %d" % idx,
            "class": "resting_worker",
            "department": "Worker Rest / Dormitory Floor", "floor": 40,
            "team": "rest_team", "role": "Standby Worker",
            "role_key": "rest_resting_worker",
            "manager": "FLOOR_MANAGER",
            "room": "Standby Lounge",
            "station": "Standby Lounge · station #%02d" % ((idx % 24) + 1),
            "current_task": "rest", "state": "resting",
            "profit_mission_link": "workforce_recovery",
            "training_status": "trained",
            "created_ts": _now(),
        })

    payload = {
        "ok": True,
        "kind": "qsb_new_1000_workers_employed",
        "phase": PHASE,
        "generated_ts": _now(),
        "new_worker_count": len(all_workers),
        "workers": all_workers,
        "by_department": _group_count(all_workers, "department"),
        "by_floor":      _group_count(all_workers, "floor"),
        "by_class":      _group_count(all_workers, "class"),
        "by_team":       _group_count(all_workers, "team"),
    }
    payload.update(_safety())
    _write(REG / "qsb_new_1000_workers_employed.json", payload)

    # Team assignments + floor assignments + room + station + chain
    floor_map = {}
    team_map = {}
    room_map = _load("qsb_worker_room_assignments.json",
                     {"by_floor_room": {}}).get("by_floor_room") or {}
    if not isinstance(room_map, dict):
        room_map = {}
    station_map = _load("qsb_worker_station_assignments.json",
                        {"stations": {}}).get("stations") or {}
    if not isinstance(station_map, dict):
        station_map = {}
    chain = []

    floor_key_lookup = {p["floor"]: "floor_%02d_%s" % (
        p["floor"],
        p["secondary"].lower().replace(" / ", "_").replace(" ", "_").replace("+", "and").replace("-", "_")
    ) for p in FLOOR_PLAN}

    for w in all_workers:
        floor_map.setdefault(str(w["floor"]), []).append(w["worker_id"])
        team_map.setdefault(w["team"], []).append(w["worker_id"])
        fkey = floor_key_lookup.get(w["floor"], "floor_%02d" % w["floor"])
        rooms_for_floor = room_map.setdefault(fkey, {})
        if not isinstance(rooms_for_floor, dict):
            rooms_for_floor = {}
            room_map[fkey] = rooms_for_floor
        rooms_for_floor.setdefault(w["room"], []).append(w["worker_id"])
        station_map[w["worker_id"]] = {
            "floor": fkey, "room": w["room"], "station": w["station"],
            "role": w["role"], "stable": True,
            "source": "qsb_skyscraper_occupancy.py",
        }
        chain.append({
            "worker_id": w["worker_id"], "role": w["role"],
            "manager_role_key": w["manager"], "team": w["team"],
            "floor": w["floor"],
        })

    _write(REG / "qsb_worker_team_assignments.json",
           dict({"ok": True, "kind": "qsb_worker_team_assignments",
                  "generated_ts": _now(), "by_team": team_map,
                  "team_count": len(team_map)},
                 **_safety()))
    _write(REG / "qsb_worker_floor_assignments.json",
           dict({"ok": True, "kind": "qsb_worker_floor_assignments",
                  "generated_ts": _now(), "by_floor": floor_map,
                  "floor_count": len(floor_map)},
                 **_safety()))
    rooms_payload = _load("qsb_worker_room_assignments.json", {})
    rooms_payload.update({
        "ok": True, "kind": "qsb_worker_room_assignments",
        "generated_ts": _now(), "by_floor_room": room_map,
        "v2_expansion_appended": True,
    })
    rooms_payload.update(_safety())
    _write(REG / "qsb_worker_room_assignments.json", rooms_payload)
    stations_payload = _load("qsb_worker_station_assignments.json", {})
    stations_payload.update({
        "ok": True, "kind": "qsb_worker_station_assignments",
        "generated_ts": _now(), "station_count": len(station_map),
        "stations": station_map, "v2_expansion_appended": True,
    })
    stations_payload.update(_safety())
    _write(REG / "qsb_worker_station_assignments.json", stations_payload)
    _write(REG / "qsb_worker_chain_of_command.json",
           dict({"ok": True, "kind": "qsb_worker_chain_of_command",
                  "generated_ts": _now(), "chain": chain,
                  "chain_count": len(chain)},
                 **_safety()))
    return payload


def _group_count(items, key):
    out = {}
    for x in items:
        k = x.get(key)
        out[str(k)] = out.get(str(k), 0) + 1
    return out


# ── Department + team maps ────────────────────────────────────────


def build_department_team_map():
    dept_map = {}
    team_map = {}
    for plan in FLOOR_PLAN:
        dept = plan["secondary"]
        dept_map[dept] = {
            "floor": plan["floor"],
            "primary_label": plan["primary"],
            "purpose": plan["purpose"],
            "rooms": plan["rooms"],
            "profit": plan.get("profit"),
            "kernel": plan.get("kernel"),
            "safety": plan.get("safety"),
            "rest": plan.get("rest"),
            "team": _team_for(dept),
        }
        team_map.setdefault(_team_for(dept), []).append(dept)
    payload = {
        "ok": True, "kind": "qsb_department_team_map",
        "phase": PHASE, "generated_ts": _now(),
        "department_count": len(dept_map),
        "departments": dept_map,
    }
    payload.update(_safety())
    _write(REG / "qsb_department_team_map.json", payload)
    _write(REG / "qsb_floor_team_map.json",
           dict({"ok": True, "kind": "qsb_floor_team_map",
                  "generated_ts": _now(),
                  "by_team": team_map, "team_count": len(team_map)},
                 **_safety()))

    rosters = {}
    workers = _load("qsb_new_1000_workers_employed.json", {}).get("workers") or []
    for w in workers:
        rosters.setdefault(w["team"], {"team": w["team"], "members": []})
        rosters[w["team"]]["members"].append({
            "worker_id": w["worker_id"],
            "role": w["role"],
            "floor": w["floor"],
        })
    _write(REG / "qsb_team_rosters.json",
           dict({"ok": True, "kind": "qsb_team_rosters",
                  "generated_ts": _now(),
                  "team_count": len(rosters), "rosters": rosters},
                 **_safety()))
    return payload


# ── Floor occupancy masterplan ─────────────────────────────────────


def build_occupancy_masterplan():
    items = []
    for plan in FLOOR_PLAN:
        items.append({
            "floor": plan["floor"],
            "primary_label": plan["primary"],
            "secondary_department": plan["secondary"],
            "purpose": plan["purpose"],
            "manager_role_key": "floor_manager",
            "rooms": plan["rooms"],
            "team_size": plan.get("team_size", 0),
            "profit": plan.get("profit"),
            "kernel": plan.get("kernel"),
            "safety": plan.get("safety"),
            "rest": plan.get("rest"),
            "preserve_existing": bool(plan.get("preserve_existing")),
            "dashboard_interior_required": True,
            "openclaw_inspection_required": True,
        })
    payload = {
        "ok": True, "kind": "qsb_floor_occupancy_masterplan",
        "phase": PHASE, "generated_ts": _now(),
        "floor_count": len(items),
        "floors": items,
    }
    payload.update(_safety())
    _write(REG / "qsb_floor_occupancy_masterplan.json", payload)
    _write(REG / "qsb_vacant_floor_population_plan.json",
           dict({"ok": True, "kind": "qsb_vacant_floor_population_plan",
                  "generated_ts": _now(),
                  "vacancy_population": [
                      {"floor": p["floor"], "before": "weak",
                       "after": p["secondary"],
                       "team_size": p.get("team_size", 0)}
                      for p in FLOOR_PLAN if not p.get("preserve_existing")
                  ]},
                 **_safety()))
    profit_map = [{"floor": p["floor"],
                    "secondary": p["secondary"],
                    "profit_contribution": (
                        "direct" if p.get("profit") else
                        ("kernel_evolution" if p.get("kernel") else
                         ("workforce_recovery" if p.get("rest") else "support")))}
                   for p in FLOOR_PLAN]
    _write(REG / "qsb_floor_profit_alignment_map.json",
           dict({"ok": True, "kind": "qsb_floor_profit_alignment_map",
                  "generated_ts": _now(), "map": profit_map},
                 **_safety()))
    return payload


# ── Worker rest / recreation ──────────────────────────────────────


def build_rest_recreation():
    rest_workers = []
    workers = _load("qsb_new_1000_workers_employed.json", {}).get("workers") or []
    for w in workers:
        if w.get("class") == "resting_worker":
            rest_workers.append(w)
    payload = {
        "ok": True, "kind": "qsb_worker_rest_recreation_state",
        "phase": PHASE, "generated_ts": _now(),
        "rest_floors": [40],
        "recreation_floors": [39],
        "sleep_pods_count": 80,
        "standby_lounge_count": 30,
        "quiet_recovery_count": 20,
        "break_room_count": 30,
        "workers_currently_resting": len(rest_workers),
        "rotation_policy": "8h shifts with hot-desking; idle workers cycle to standby",
        "rooms": [
            "Sleep Pods", "Standby Lounge", "Quiet Recovery Room",
            "Break Room", "Game Room", "Morale Board",
            "Wellness Monitor", "Shift Change Desk", "Coffee Bar"
        ],
    }
    payload.update(_safety())
    _write(REG / "qsb_worker_rest_recreation_state.json", payload)
    _write(REG / "qsb_worker_shift_schedule.json",
           dict({"ok": True, "kind": "qsb_worker_shift_schedule",
                  "generated_ts": _now(),
                  "shifts": [
                    {"shift": "alpha", "hours": "00-08", "lead_floor": 40},
                    {"shift": "beta",  "hours": "08-16", "lead_floor": 40},
                    {"shift": "gamma", "hours": "16-24", "lead_floor": 40}],
                  "rotation_cadence": "every cadence tick (~24h)"},
                 **_safety()))
    return payload


# ── Commerce Wing masterplan ──────────────────────────────────────


def build_commerce_wing():
    platforms = [
        {"platform": "Etsy",
         "api_availability": "Etsy Open API v3 (requires OAuth2, app review for write scope)",
         "authentication": "OAuth2 with keystring + shared secret",
         "allowed_automation": "draft listing JSON locally; publishing requires user click",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "via Etsy Shop API",
         "fees_risks_to_check_manually": "Etsy listing fee, transaction fee, payment processing fee, advertising fee",
         "terms_compliance_risk": "must follow Seller Policy + Intellectual Property Policy",
         "required_credentials": ["ETSY_API_KEY", "ETSY_SHARED_SECRET",
                                    "ETSY_SHOP_ID", "ETSY_OAUTH_TOKEN"],
         "safe_test_or_manual_mode": "store drafts locally; render listing JSON; never POST without user approval",
         "recommended_floor": 6, "recommended_team": "etsy_team",
         "build_now_or_later": "now (draft-only)"},
        {"platform": "Shopify",
         "api_availability": "Shopify Admin API + Storefront API",
         "authentication": "API key + access token (private app) OR OAuth (public app)",
         "allowed_automation": "draft products + themes locally; no writes until approved",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "via Shopify fulfilment endpoints",
         "fees_risks_to_check_manually": "Shopify plan fees, transaction fees if not using Shopify Payments",
         "terms_compliance_risk": "Shopify ToS + acceptable use policy",
         "required_credentials": ["SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_API_TOKEN"],
         "safe_test_or_manual_mode": "development store + draft product JSON",
         "recommended_floor": 7, "recommended_team": "shopify_team",
         "build_now_or_later": "later (after Etsy proves the pipeline)"},
        {"platform": "Printful",
         "api_availability": "Printful API v2",
         "authentication": "Bearer token",
         "allowed_automation": "draft products + mockups",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Printful fulfils + ships directly",
         "fees_risks_to_check_manually": "Printful product cost + shipping cost + Printful markup",
         "terms_compliance_risk": "Printful Acceptable Use + IP policies",
         "required_credentials": ["PRINTFUL_API_TOKEN"],
         "safe_test_or_manual_mode": "mockup generation API has no commitment; orders require manual approval",
         "recommended_floor": 14, "recommended_team": "pod_team",
         "build_now_or_later": "now (mockup-only)"},
        {"platform": "Printify",
         "api_availability": "Printify API v1",
         "authentication": "Personal Access Token (Bearer)",
         "allowed_automation": "draft products + mockups",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Printify fulfils + ships directly",
         "fees_risks_to_check_manually": "Printify product cost + shipping cost",
         "terms_compliance_risk": "Printify ToS + IP policies",
         "required_credentials": ["PRINTIFY_API_TOKEN"],
         "safe_test_or_manual_mode": "API supports unsubmitted drafts; orders require manual approval",
         "recommended_floor": 14, "recommended_team": "pod_team",
         "build_now_or_later": "later (after Printful proves pipeline)"},
        {"platform": "Gumroad",
         "api_availability": "Gumroad API v2",
         "authentication": "OAuth access token",
         "allowed_automation": "draft products + price changes (with approval)",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Gumroad delivers digital downloads",
         "fees_risks_to_check_manually": "Gumroad transaction fee",
         "terms_compliance_risk": "Gumroad ToS",
         "required_credentials": ["GUMROAD_ACCESS_TOKEN"],
         "safe_test_or_manual_mode": "draft products; publishing needs human approval",
         "recommended_floor": 6, "recommended_team": "etsy_team",
         "build_now_or_later": "later"},
        {"platform": "Payhip",
         "api_availability": "Payhip API",
         "authentication": "API key",
         "allowed_automation": "draft listings",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Digital downloads",
         "fees_risks_to_check_manually": "Payhip processing fee",
         "terms_compliance_risk": "Payhip ToS",
         "required_credentials": ["PAYHIP_API_KEY"],
         "safe_test_or_manual_mode": "draft only",
         "recommended_floor": 6, "recommended_team": "etsy_team",
         "build_now_or_later": "later"},
        {"platform": "Ko-fi",
         "api_availability": "Webhook receive only (no full REST)",
         "authentication": "Webhook secret",
         "allowed_automation": "receive notifications for incoming support",
         "listing_api_support": False, "order_api_support": False,
         "fulfilment_support": "Manual / digital download",
         "fees_risks_to_check_manually": "Ko-fi Gold fee (membership tier)",
         "terms_compliance_risk": "Ko-fi creator guidelines",
         "required_credentials": ["KOFI_WEBHOOK_SECRET"],
         "safe_test_or_manual_mode": "webhook listener only",
         "recommended_floor": 6, "recommended_team": "etsy_team",
         "build_now_or_later": "later"},
        {"platform": "eBay",
         "api_availability": "eBay Trading + Browse API",
         "authentication": "OAuth2 + Developer App ID",
         "allowed_automation": "research only; listing API restricted",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Seller fulfils",
         "fees_risks_to_check_manually": "eBay insertion fees + final value fee",
         "terms_compliance_risk": "eBay seller policies are strict",
         "required_credentials": ["EBAY_APP_ID", "EBAY_CERT_ID", "EBAY_OAUTH"],
         "safe_test_or_manual_mode": "sandbox environment available",
         "recommended_floor": 11, "recommended_team": "research_team",
         "build_now_or_later": "research only — do not build"},
        {"platform": "Amazon Handmade / Merch",
         "api_availability": "Selling Partner API (SP-API) — gated approval",
         "authentication": "SP-API LWA + IAM role",
         "allowed_automation": "tightly gated",
         "listing_api_support": True, "order_api_support": True,
         "fulfilment_support": "Amazon FBA optional",
         "fees_risks_to_check_manually": "Amazon referral fees + FBA fees",
         "terms_compliance_risk": "very high — strict policy enforcement",
         "required_credentials": ["AMZ_LWA_CLIENT_ID", "AMZ_LWA_CLIENT_SECRET",
                                    "AMZ_REFRESH_TOKEN", "AMZ_AWS_ACCESS_KEY",
                                    "AMZ_AWS_SECRET_KEY"],
         "safe_test_or_manual_mode": "research only — do not build",
         "recommended_floor": 11, "recommended_team": "research_team",
         "build_now_or_later": "research only"},
        {"platform": "Local Direct Storefront",
         "api_availability": "n/a — local Flask/FastAPI page",
         "authentication": "n/a",
         "allowed_automation": "full local control",
         "listing_api_support": True, "order_api_support": False,
         "fulfilment_support": "manual",
         "fees_risks_to_check_manually": "n/a (no platform)",
         "terms_compliance_risk": "low (no platform terms)",
         "required_credentials": [],
         "safe_test_or_manual_mode": "local-only catalog page",
         "recommended_floor": 7, "recommended_team": "shopify_team",
         "build_now_or_later": "now (preview catalog only)"},
    ]

    payload = {
        "ok": True,
        "kind": "qsb_commerce_platform_research",
        "phase": PHASE,
        "generated_ts": _now(),
        "platform_count": len(platforms),
        "platforms": platforms,
    }
    payload.update(_safety())
    _write(REG / "qsb_commerce_platform_research.json", payload)

    # Masterplan
    masterplan = {
        "ok": True, "kind": "qsb_commerce_wing_masterplan",
        "phase": PHASE, "generated_ts": _now(),
        "wing_name": "Commerce Wing",
        "departments": [
            {"floor": 6,  "name": "Etsy Shop Floor"},
            {"floor": 7,  "name": "Shopify Storefront Floor"},
            {"floor": 13, "name": "Product Image Studio + Mockup Wall"},
            {"floor": 14, "name": "Print-on-Demand Floor"},
            {"floor": 15, "name": "Voice Commerce Studio"},
            {"floor": 16, "name": "Listing Writer + SEO Lab"},
            {"floor": 17, "name": "Product Design Studio + Prompt-to-Product"},
            {"floor": 18, "name": "Marketing + Promotion Floor"},
            {"floor": 19, "name": "Customer Service Floor"},
            {"floor": 1,  "name": "Order Fulfilment Hub"},
            {"floor": 26, "name": "Commerce Accounting Floor"},
            {"floor": 32, "name": "Platform Compliance Office"},
            {"floor": 33, "name": "Refund / Dispute Desk"},
            {"floor": 34, "name": "Storefront Analytics Room"},
        ],
        "manual_approval_gate": "no listing publishes / no payment / no spending without explicit user click",
        "live_payments_enabled": False,
        "live_listings_publishing_enabled": False,
    }
    masterplan.update(_safety())
    _write(REG / "qsb_commerce_wing_masterplan.json", masterplan)

    _write(REG / "qsb_commerce_department_map.json",
           dict({"ok": True, "kind": "qsb_commerce_department_map",
                  "generated_ts": _now(),
                  "departments": masterplan["departments"],
                  "wing": "Commerce Wing"},
                 **_safety()))

    profit_alignment = {
        "ok": True, "kind": "qsb_commerce_profit_alignment",
        "phase": PHASE, "generated_ts": _now(),
        "wing_profit_potential": "Etsy digital products + POD physical goods + Shopify direct storefront — all gated behind manual approval.",
        "first_revenue_milestones": [
            "Etsy listing draft pipeline + one approved test listing",
            "POD mockup pipeline + one approved test product",
            "Shopify development store ready for catalog import",
        ],
        "estimated_setup_effort": {
            "etsy_first_draft":    "2-4 weeks human time + Claude assist",
            "pod_first_draft":     "2-4 weeks human time",
            "shopify_dev_store":   "1-2 weeks human time",
        },
    }
    profit_alignment.update(_safety())
    _write(REG / "qsb_commerce_profit_alignment.json", profit_alignment)
    return masterplan


# ── Etsy floor manifest ───────────────────────────────────────────


def build_etsy_floor():
    plan = next(p for p in FLOOR_PLAN if p["floor"] == 6)
    workers = [w for w in (_load("qsb_new_1000_workers_employed.json", {}).get("workers") or [])
               if w.get("floor") == 6]
    manifest = {
        "ok": True, "kind": "qsb_etsy_floor_manifest",
        "phase": PHASE, "generated_ts": _now(),
        "floor": 6, "department": plan["secondary"],
        "purpose": plan["purpose"],
        "rooms": plan["rooms"],
        "worker_count": len(workers),
        "workers": workers,
        "safe_mode": True,
        "draft_only": True,
        "manual_approval_required": True,
        "publishing_enabled": False,
        "customer_messaging_automation_enabled": False,
        "account_actions_enabled": False,
        "credentials_source": "environment_variables_only_at_runtime",
        "secrets_in_logs": False,
    }
    manifest.update(_safety())
    _write(REG / "qsb_etsy_floor_manifest.json", manifest)
    _write(REG / "qsb_etsy_product_pipeline.json",
           dict({"ok": True, "kind": "qsb_etsy_product_pipeline",
                  "generated_ts": _now(),
                  "stages": ["niche_research", "design_brief",
                              "asset_generation", "mockup",
                              "listing_draft", "compliance_review",
                              "manual_approval_gate",
                              "publish_to_etsy_(blocked_until_unlock)",
                              "monitor_orders", "review_pnl"]},
                 **_safety()))
    _write(REG / "qsb_etsy_listing_drafts.json",
           dict({"ok": True, "kind": "qsb_etsy_listing_drafts",
                  "generated_ts": _now(),
                  "drafts": [], "draft_count": 0,
                  "note": "drafts created by Etsy floor workers will be appended here; nothing publishes without explicit user unlock"},
                 **_safety()))
    _write(REG / "qsb_etsy_compliance_checklist.json",
           dict({"ok": True, "kind": "qsb_etsy_compliance_checklist",
                  "generated_ts": _now(),
                  "items": [
                    "no_copyright_infringement", "no_trademark_infringement",
                    "honest_product_description", "honest_shipping_times",
                    "compliant_tags_and_keywords", "shop_policies_complete",
                    "tax_settings_complete", "no_misleading_imagery",
                    "compliant_with_etsy_seller_policy"]},
                 **_safety()))
    _write(REG / "qsb_etsy_worker_team.json",
           dict({"ok": True, "kind": "qsb_etsy_worker_team",
                  "generated_ts": _now(),
                  "team": "etsy_team",
                  "members": [{"worker_id": w["worker_id"],
                                "role": w["role"]} for w in workers]},
                 **_safety()))
    return manifest


# ── POD + 3D printing floors ──────────────────────────────────────


def build_pod_3d():
    pod_plan = next(p for p in FLOOR_PLAN if p["floor"] == 14)
    pod_workers = [w for w in (_load("qsb_new_1000_workers_employed.json", {}).get("workers") or [])
                   if w.get("floor") == 14]
    pod = {
        "ok": True, "kind": "qsb_print_on_demand_floor",
        "phase": PHASE, "generated_ts": _now(),
        "floor": 14, "department": pod_plan["secondary"],
        "purpose": pod_plan["purpose"],
        "rooms": pod_plan["rooms"],
        "worker_count": len(pod_workers),
        "workers": pod_workers,
        "safe_mode": True, "draft_only": True,
        "manual_approval_required": True,
        "platforms_supported": ["printful", "printify"],
        "no_real_orders_without_unlock": True,
    }
    pod.update(_safety())
    _write(REG / "qsb_print_on_demand_floor.json", pod)

    # 3D Printing — define a floor entry on a still-weak slot;
    # Floor 33 has Refund desk; Floor 34 has analytics. Use Floor 39's
    # recreation overlap? Better: dedicate a NEW logical sub-floor on
    # Floor 17 (Design Studio) since the design pipeline includes 3D.
    three_d = {
        "ok": True, "kind": "qsb_3d_printing_floor",
        "phase": PHASE, "generated_ts": _now(),
        "floor": 17,
        "secondary_role": "3D Printing Product Pipeline (co-located on Design Studio floor)",
        "rooms": ["Product Concept Lab", "CAD / Model Desk",
                   "STL Review Desk", "Material/Cost Desk",
                   "Print Queue", "Quality Control",
                   "Marketplace Listing Desk"],
        "safe_mode": True, "draft_only": True,
        "manual_approval_required": True,
        "platforms_supported": ["local_3d_printer_queue_only",
                                  "future_etsy_or_marketplace_listing"],
        "no_real_orders_without_unlock": True,
    }
    three_d.update(_safety())
    _write(REG / "qsb_3d_printing_floor.json", three_d)

    _write(REG / "qsb_product_design_pipeline.json",
           dict({"ok": True, "kind": "qsb_product_design_pipeline",
                  "generated_ts": _now(),
                  "stages": ["concept", "design_brief",
                              "cad_or_image", "review",
                              "cost_calculation",
                              "manual_approval_gate",
                              "list_or_print"]},
                 **_safety()))
    return pod


# ── Online shop opportunity map ───────────────────────────────────


def build_shop_opportunity_map():
    opps = [
        {"product_type": "Etsy digital downloads (printables, planners)",
         "platform": "Etsy", "setup_difficulty": "medium",
         "api_availability": True, "fulfilment_complexity": "low (auto digital)",
         "expected_worker_teams": ["etsy_team", "design_team", "research_team"],
         "compliance_risks": "IP, listing accuracy",
         "credential_needs": "Etsy OAuth", "human_approval_needed": True,
         "recommended_next_step": "draft 5 candidate niches; user picks one",
         "profit_potential": "moderate"},
        {"product_type": "Print-on-demand T-shirts/mugs/posters",
         "platform": "Printful via Etsy/Shopify", "setup_difficulty": "medium",
         "api_availability": True, "fulfilment_complexity": "low (POD partner ships)",
         "expected_worker_teams": ["pod_team", "design_team", "compliance_team"],
         "compliance_risks": "IP, trademark, copyright",
         "credential_needs": "Printful API + Etsy/Shopify",
         "human_approval_needed": True,
         "recommended_next_step": "build mockup pipeline; user reviews 10 designs",
         "profit_potential": "moderate-high"},
        {"product_type": "Shopify direct storefront (digital + physical)",
         "platform": "Shopify", "setup_difficulty": "medium-high",
         "api_availability": True, "fulfilment_complexity": "varies",
         "expected_worker_teams": ["shopify_team", "design_team", "customer_service_team"],
         "compliance_risks": "Shopify ToS, data protection",
         "credential_needs": "Shopify admin token",
         "human_approval_needed": True,
         "recommended_next_step": "Shopify development store import + theme",
         "profit_potential": "high (long-term)"},
        {"product_type": "Gumroad/Payhip digital downloads",
         "platform": "Gumroad/Payhip", "setup_difficulty": "low",
         "api_availability": True, "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "platform ToS",
         "credential_needs": "Gumroad/Payhip OAuth",
         "human_approval_needed": True,
         "recommended_next_step": "draft 3 products",
         "profit_potential": "moderate"},
        {"product_type": "Ko-fi memberships/tips",
         "platform": "Ko-fi", "setup_difficulty": "low",
         "api_availability": False,
         "fulfilment_complexity": "low (manual or download)",
         "expected_worker_teams": ["etsy_team"],
         "compliance_risks": "Ko-fi guidelines",
         "credential_needs": "Ko-fi webhook secret",
         "human_approval_needed": True,
         "recommended_next_step": "page draft only",
         "profit_potential": "low-moderate"},
        {"product_type": "eBay research (later)",
         "platform": "eBay", "setup_difficulty": "high",
         "api_availability": True,
         "fulfilment_complexity": "high (seller ships)",
         "expected_worker_teams": ["research_team"],
         "compliance_risks": "strict seller policies",
         "credential_needs": "eBay OAuth",
         "human_approval_needed": True,
         "recommended_next_step": "research only",
         "profit_potential": "varies"},
        {"product_type": "Amazon Handmade/Merch research (later)",
         "platform": "Amazon", "setup_difficulty": "very high",
         "api_availability": True,
         "fulfilment_complexity": "high (FBA)",
         "expected_worker_teams": ["research_team"],
         "compliance_risks": "very strict policy enforcement",
         "credential_needs": "Amazon SP-API",
         "human_approval_needed": True,
         "recommended_next_step": "research only",
         "profit_potential": "varies"},
        {"product_type": "Local direct storefront (catalog page)",
         "platform": "local", "setup_difficulty": "low",
         "api_availability": False,
         "fulfilment_complexity": "manual",
         "expected_worker_teams": ["shopify_team", "design_team"],
         "compliance_risks": "low (no platform)",
         "credential_needs": "none",
         "human_approval_needed": True,
         "recommended_next_step": "build catalog preview page",
         "profit_potential": "low (until traffic)"},
        {"product_type": "Newsletter + product bundles",
         "platform": "Ghost/Substack/email",
         "setup_difficulty": "medium",
         "api_availability": True,
         "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "spam/marketing law (CAN-SPAM, GDPR)",
         "credential_needs": "email-platform API",
         "human_approval_needed": True,
         "recommended_next_step": "newsletter draft + free lead magnet",
         "profit_potential": "moderate"},
        {"product_type": "AI prompt pack store",
         "platform": "Etsy/Gumroad",
         "setup_difficulty": "low",
         "api_availability": True,
         "fulfilment_complexity": "low (digital)",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "AI content disclosure",
         "credential_needs": "Etsy/Gumroad",
         "human_approval_needed": True,
         "recommended_next_step": "curate 30 high-quality prompts",
         "profit_potential": "moderate"},
        {"product_type": "Printable planner/template store",
         "platform": "Etsy",
         "setup_difficulty": "low",
         "api_availability": True,
         "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "IP",
         "credential_needs": "Etsy",
         "human_approval_needed": True,
         "recommended_next_step": "design 10 planners",
         "profit_potential": "moderate"},
        {"product_type": "Digital art pack store",
         "platform": "Etsy/Gumroad",
         "setup_difficulty": "low",
         "api_availability": True,
         "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "IP, AI disclosure",
         "credential_needs": "Etsy/Gumroad",
         "human_approval_needed": True,
         "recommended_next_step": "curate 50 art packs",
         "profit_potential": "moderate"},
        {"product_type": "3D printable STL store",
         "platform": "Etsy/Cults3D/Thangs",
         "setup_difficulty": "medium",
         "api_availability": "partial",
         "fulfilment_complexity": "low (digital)",
         "expected_worker_teams": ["pod_team", "design_team"],
         "compliance_risks": "IP",
         "credential_needs": "varies",
         "human_approval_needed": True,
         "recommended_next_step": "draft 10 STL designs",
         "profit_potential": "moderate"},
        {"product_type": "Trading journal / template store",
         "platform": "Etsy/Gumroad",
         "setup_difficulty": "low",
         "api_availability": True,
         "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "research_team"],
         "compliance_risks": "compliance disclaimers (not financial advice)",
         "credential_needs": "Etsy/Gumroad",
         "human_approval_needed": True,
         "recommended_next_step": "draft 5 templates (Excel/PDF/Notion)",
         "profit_potential": "moderate"},
        {"product_type": "QSB-themed digital dashboard templates",
         "platform": "Etsy/Gumroad",
         "setup_difficulty": "low",
         "api_availability": True,
         "fulfilment_complexity": "low",
         "expected_worker_teams": ["etsy_team", "design_team"],
         "compliance_risks": "low",
         "credential_needs": "Etsy/Gumroad",
         "human_approval_needed": True,
         "recommended_next_step": "package the next3d cockpit as a template",
         "profit_potential": "low-moderate (niche)"},
    ]
    payload = {
        "ok": True, "kind": "qsb_online_shop_opportunity_map",
        "phase": PHASE, "generated_ts": _now(),
        "opportunity_count": len(opps),
        "opportunities": opps,
        "warning": "All profit potentials are estimates. Real revenue depends on quality, marketing, niche choice, and execution.",
        "no_guaranteed_profit": True,
        "use_only_test_pipeline_until_approved": True,
    }
    payload.update(_safety())
    _write(REG / "qsb_online_shop_opportunity_map.json", payload)
    return payload


# ── Classrooms + research facilities ──────────────────────────────


def build_classrooms():
    classroom_plan = next(p for p in FLOOR_PLAN if p["floor"] == 8)
    workers = [w for w in (_load("qsb_new_1000_workers_employed.json", {}).get("workers") or [])
               if w.get("floor") == 8]
    payload = {
        "ok": True, "kind": "qsb_classroom_map",
        "phase": PHASE, "generated_ts": _now(),
        "primary_floor": 8,
        "classrooms": classroom_plan["rooms"],
        "teacher_count": sum(1 for w in workers if "teacher" in w.get("role", "").lower()),
        "student_count": sum(1 for w in workers if "student" in w.get("role", "").lower()),
    }
    payload.update(_safety())
    _write(REG / "qsb_classroom_map.json", payload)
    curriculum = {
        "ok": True, "kind": "qsb_teaching_curriculum",
        "phase": PHASE, "generated_ts": _now(),
        "topics": [
            "paper/testnet trading rules",
            "risk discipline + 5-pip spread cap",
            "entry/exit reasons mandatory",
            "PnL review + lessons from losing trades",
            "digital product design",
            "Etsy listing basics + IP compliance",
            "Shopify storefront basics + theme work",
            "Print-on-Demand workflow + mockups",
            "3D printing product workflow",
            "Customer service drafting + tone",
            "SEO + listing optimization",
            "Pricing research + competitor watch",
            "Compliance + platform rules",
            "Product testing + quality checks",
            "Worker performance + certification",
        ],
        "cohort_size_recommended": 17,
        "certification_required_before_active_duty": True,
    }
    curriculum.update(_safety())
    _write(REG / "qsb_teaching_curriculum.json", curriculum)
    research = {
        "ok": True, "kind": "qsb_research_strategy_facilities",
        "phase": PHASE, "generated_ts": _now(),
        "facilities": [
            {"floor": 3,  "name": "Product Research Lab"},
            {"floor": 10, "name": "Strategy Lab + Sandbox Coupling"},
            {"floor": 11, "name": "Demand + Competitor Watch"},
            {"floor": 37, "name": "Strategy Labs"},
            {"floor": 17, "name": "Prompt Engineering Lab (in Design Studio)"},
        ],
    }
    research.update(_safety())
    _write(REG / "qsb_research_strategy_facilities.json", research)
    return payload


# ── Floor occupancy dashboard state + interior completion ─────────


def build_dashboard_state():
    workers = _load("qsb_new_1000_workers_employed.json", {}).get("workers") or []
    state = {
        "ok": True, "kind": "qsb_floor_occupancy_dashboard_state",
        "phase": PHASE, "generated_ts": _now(),
        "floor_total": len(FLOOR_PLAN),
        "floors_with_secondary_department": sum(1 for p in FLOOR_PLAN
                                                  if not p.get("preserve_existing")),
        "floors_preserved": sum(1 for p in FLOOR_PLAN if p.get("preserve_existing")),
        "new_workers_employed": len(workers),
        "by_floor_summary": [
            {"floor": p["floor"], "department": p["secondary"],
              "rooms": len(p["rooms"]),
              "team_size": p.get("team_size", 0),
              "preserve_existing": bool(p.get("preserve_existing"))}
            for p in FLOOR_PLAN
        ],
    }
    state.update(_safety())
    _write(REG / "qsb_floor_occupancy_dashboard_state.json", state)
    _write(REG / "qsb_department_directory.json",
           dict({"ok": True, "kind": "qsb_department_directory",
                  "generated_ts": _now(),
                  "departments": [
                    {"floor": p["floor"], "primary": p["primary"],
                     "secondary": p["secondary"], "purpose": p["purpose"]}
                    for p in FLOOR_PLAN]},
                 **_safety()))
    _write(REG / "qsb_floor_interior_completion_state.json",
           dict({"ok": True, "kind": "qsb_floor_interior_completion_state",
                  "generated_ts": _now(),
                  "floors_with_dedicated_dashboard_panel": [41, 42, 43, 55],
                  "floors_with_generic_inspector": [
                      p["floor"] for p in FLOOR_PLAN
                      if p["floor"] not in (41, 42, 43, 55)],
                  "follow_up_floors_for_dedicated_panels": [6, 14, 17],
                  "note": "Floors 41/42/43/55 have dedicated next3d interiors. Other floors fall back to the generic inspector that lists rooms + workers."},
                 **_safety()))
    return state


# ── OpenClaw full floor inspection ────────────────────────────────


def build_openclaw_inspection():
    findings = []
    tickets = []
    workers = _load("qsb_new_1000_workers_employed.json", {}).get("workers") or []
    workers_per_floor = {}
    for w in workers:
        workers_per_floor[w["floor"]] = workers_per_floor.get(w["floor"], 0) + 1

    for plan in FLOOR_PLAN:
        f = plan["floor"]
        wc = workers_per_floor.get(f, 0)
        sev = "OK"
        issue = None
        # Vacant after expansion?
        if not plan.get("preserve_existing") and wc < 5:
            sev = "WARN"
            issue = "floor under-populated (new workers=%d)" % wc
        # Has profit/kernel/safety/rest alignment?
        if not any([plan.get("profit"), plan.get("kernel"),
                    plan.get("safety"), plan.get("rest")]):
            sev = "WARN"
            issue = "floor has no profit/kernel/safety/rest alignment"
        # Commerce floors must have manual approval gate
        is_commerce = plan["secondary"] in {
            "Etsy Shop Floor", "Shopify Storefront Floor",
            "Print-on-Demand Floor", "Marketing + Promotion Floor"}
        if is_commerce:
            findings.append({
                "floor": f, "severity": "OK",
                "kind": "commerce_safe_mode",
                "detail": "draft_only=true; manual_approval_required=true; live_payments_enabled=false"
            })
        finding = {"floor": f, "secondary": plan["secondary"],
                    "severity": sev,
                    "kind": "floor_health",
                    "worker_count_new": wc,
                    "manager_present": True,
                    "team_present": wc > 0,
                    "rooms_count": len(plan["rooms"]),
                    "profit_aligned": bool(plan.get("profit")),
                    "kernel_aligned": bool(plan.get("kernel")),
                    "safety_aligned": bool(plan.get("safety")),
                    "rest_aligned": bool(plan.get("rest")),
                    "issue": issue}
        findings.append(finding)
        if sev != "OK":
            tickets.append({
                "id": "oc_full_f{:02d}".format(f),
                "floor": f,
                "severity": sev,
                "issue": issue or "see finding"
            })

    payload = {
        "ok": True, "kind": "qsb_openclaw_full_floor_inspection",
        "phase": PHASE, "generated_ts": _now(),
        "finding_count": len(findings),
        "ticket_count": len(tickets),
        "findings": findings,
        "tickets": tickets,
        "supervisor_state": "active_local_only",
        "real_tool_execution_enabled": False,
    }
    payload.update(_safety())
    _write(REG / "qsb_openclaw_full_floor_inspection.json", payload)
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / "qsb_openclaw_full_floor_inspection.jsonl"
    rec = {"ts": _now(), "phase": PHASE,
           "event": "openclaw_full_floor_inspection",
           "summary": {"findings": len(findings), "tickets": len(tickets)}}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return payload


# ── EQSB record ───────────────────────────────────────────────────


def _eqsb_record(event, payload):
    rec = {"ts": _now(), "phase": PHASE, "event": event, "payload": payload}
    EQSB_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EQSB_EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    with EQSB_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# ── Orchestrator ──────────────────────────────────────────────────


def build_all():
    audit = build_audit()
    workforce = build_workforce_1000()
    depts = build_department_team_map()
    occ = build_occupancy_masterplan()
    rest = build_rest_recreation()
    commerce = build_commerce_wing()
    etsy = build_etsy_floor()
    pod = build_pod_3d()
    opps = build_shop_opportunity_map()
    classrooms = build_classrooms()
    dash = build_dashboard_state()
    oc = build_openclaw_inspection()
    summary = {
        "ok": True, "phase": PHASE, "generated_ts": _now(),
        "floors_audited": audit.get("total_floors"),
        "weak_floors": audit.get("weak_floors_count"),
        "new_workers_employed": workforce.get("new_worker_count"),
        "departments_in_map": depts.get("department_count"),
        "commerce_wing_departments": len(commerce.get("departments", [])),
        "shop_opportunities_mapped": opps.get("opportunity_count"),
        "openclaw_findings": oc.get("finding_count"),
        "openclaw_tickets": oc.get("ticket_count"),
    }
    summary.update(_safety())
    _eqsb_record("skyscraper_occupancy_v1_complete", summary)
    return summary


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target == "all":
        out = build_all()
    elif target == "audit":           out = build_audit()
    elif target == "workforce_1000":  out = build_workforce_1000()
    elif target == "department_team": out = build_department_team_map()
    elif target == "occupancy":       out = build_occupancy_masterplan()
    elif target == "rest_recreation": out = build_rest_recreation()
    elif target == "commerce_wing":   out = build_commerce_wing()
    elif target == "etsy":            out = build_etsy_floor()
    elif target == "pod_3d":          out = build_pod_3d()
    elif target == "shop_opps":       out = build_shop_opportunity_map()
    elif target == "classrooms":      out = build_classrooms()
    elif target == "dashboard_state": out = build_dashboard_state()
    elif target == "openclaw_inspection": out = build_openclaw_inspection()
    else:
        print(json.dumps({"ok": False, "error": "unknown_target",
                          "target": target}, indent=2))
        return
    print(json.dumps({"ok": True, "target": target,
                       "summary_keys": list(out.keys()) if isinstance(out, dict) else None},
                       indent=2))


if __name__ == "__main__":
    main()
