"""draft_floor_card — produce a clean floor_card.json template for Wren."""


def run(floor_number=None, floor_name="", department="",
        archetype="generic", tour_blurb=""):
    if floor_number is None or not floor_name:
        return {"ok": False, "error": "floor_number + floor_name required"}
    try:
        n = int(floor_number)
    except Exception:
        return {"ok": False, "error": "floor_number must be integer"}
    card = {
        "floor_id": f"floor_{n:02d}",
        "floor_number": n,
        "floor_name": floor_name,
        "department": department,
        "zone": "ZONE TBD",
        "archetype": archetype,
        "staff_lead": "TBD",
        "tour_blurb": tour_blurb or f"{floor_name} — a floor in the QSB Tower.",
        "visitor_open": False,
        "advisory_only": True,
        "execution_mode": "PREVIEW_ONLY",
        "live_signals": {},
        "gate_posture": {
            "advisory_only": True,
            "execution_allowed": False,
            "live_payments_enabled": False,
        },
    }
    return {
        "ok": True,
        "draft_path": f"floors/floor_{n:02d}_<slug>/floor_card.json",
        "card": card,
        "next_step": "push the card through wren_propose_patch so Claude signs off",
    }
