"""Schema constants for Tower Operations V1: zones, departments, manager types."""

# Zones the tower is divided into (used for zone managers).
ZONES = {
    "infrastructure_zone": {"name": "Infrastructure Zone",     "floor_range": (1, 22)},
    "intelligence_zone":   {"name": "Intelligence Zone",       "floor_range": (23, 27)},
    "governance_zone":     {"name": "Governance Zone",         "floor_range": (28, 36)},
    "operations_zone":     {"name": "Operations Zone",         "floor_range": (37, 40)},
    "trading_zone":        {"name": "Trading Zone",            "floor_range": (41, 45)},
    "executive_zone":      {"name": "Executive Zone",          "floor_range": (46, 53)},
    "penthouse_zone":      {"name": "Penthouse Kernel Zone",   "floor_range": (55, 55)},
}

# Authoritative department-by-floor map (matches data/registries/floors.json).
FLOOR_TO_DEPARTMENT = {
    1:  ("Operations Department",          "operations"),
    2:  ("Memory Department",              "memory"),
    3:  ("Research Department",            "research_facility"),
    4:  ("Knowledge Department",           "knowledge"),
    5:  ("Coding Department",              "coding"),
    6:  ("Engineering Department",         "engineering"),
    7:  ("Architecture Department",        "architecture"),
    8:  ("Testing Department",             "testing"),
    9:  ("Quality Assurance Department",   "quality_assurance"),
    10: ("Trading Simulation Department",  "trading_simulation"),
    11: ("Market Intelligence Department", "market_intelligence"),
    12: ("Risk Analysis Department",       "risk_analysis"),
    13: ("Vision Department",              "vision"),
    14: ("Media Department",               "media"),
    15: ("Speech and Audio Department",    "speech_audio"),
    16: ("Document Processing Department", "document_processing"),
    17: ("Graphics and Design Department", "graphics_design"),
    18: ("Automation Department",          "automation"),
    19: ("Workflow Management Department", "workflow_management"),
    20: ("API Services Department",        "api_services"),
    21: ("Adapter Systems Department",     "adapter_systems"),
    22: ("Integration Services Department","integration_services"),
    23: ("AIR LLM Operations Department",  "airllm_advisory"),
    24: ("Model Routing Department",       "model_routing"),
    25: ("Agent Coordination Department",  "agent_coordination"),
    26: ("Model Evaluation Department",    "model_evaluation"),
    27: ("Local Model Operations Department","local_model_operations"),
    28: ("Security Department",            "security"),
    29: ("Guardian Department",            "guardian"),
    30: ("Permissions Department",         "permissions_risk"),
    31: ("Audit Department",               "audit_ledger"),
    32: ("Compliance Department",          "compliance"),
    33: ("Diagnostics Department",         "maintenance"),
    34: ("Monitoring Department",          "monitoring"),
    35: ("Infrastructure Services Department", "it_networking"),
    36: ("Expansion Planning Department",  "expansion"),
    37: ("Simulation Labs",                "strategy_simulation"),
    38: ("Worker Recruitment Agency",      "recruitment_agency"),  # UI rename
    39: ("Development Labs",               "development"),
    40: ("Prototype Systems",              "prototype"),
    41: ("OANDA Trading Floor",            "trading_fx"),
    42: ("Binance Trading Floor",          "trading_crypto"),
    43: ("Stock Exchange Trading Floor",   "trading_equities"),
    44: ("Future Systems / Vacant",        "vacant"),
    45: ("Future Systems / Vacant",        "vacant"),
    46: ("Executive Support Department",   "executive_support"),
    47: ("Executive Operations Department","executive_operations"),
    48: ("Strategic Planning Department",  "strategic_planning"),
    49: ("Resource Management Department", "resource_management"),
    50: ("Building Governance Department", "building_governance"),
    51: ("Executive Council Department",   "executive_council"),
    52: ("Infrastructure Command Department","infrastructure_command"),
    53: ("Tower Command Department",       "tower_command"),
    55: ("Penthouse — QSB Kernel",         "penthouse_kernel"),
}

# Inverse map for quickly finding which floor hosts a department.
DEPARTMENT_FLOORS = {
    "recruitment_agency":  38,
    "maintenance":         33,
    "security":            28,
    "it_networking":       35,
    "research_facility":   3,
    "media":               14,
    "speech_audio":        15,
    "permissions_risk":    30,
    "audit_ledger":        31,
    "strategy_simulation": 37,
    "trading_fx":          41,
    "trading_crypto":      42,
    "trading_equities":    43,
    "airllm_advisory":     23,
    "tower_command":       53,
    "penthouse_kernel":    55,
}


def zone_for_floor(n):
    for zid, z in ZONES.items():
        lo, hi = z["floor_range"]
        if lo <= n <= hi:
            return zid, z["name"]
    return "infrastructure_zone", "Infrastructure Zone"


MGR_TYPES = ("floor_manager", "zone_manager", "tower_manager")
