from .database import connect, now
from .registry import Registry

# V1.5 — sealed-packet and zone-permission enforcement.
# This module enforces routing/movement policy. It NEVER toggles an execution gate.

_ZONE_MAP = {  # floor_id -> zone label used by lift_permissions.json
    # ZONE A: ground + low floors 1-15
    "ground":   "ZONE A",
    "floor_01": "ZONE A", "floor_02": "ZONE A", "floor_03": "ZONE A",
    "floor_04": "ZONE A", "floor_05": "ZONE A", "floor_06": "ZONE A",
    "floor_07": "ZONE A", "floor_08": "ZONE A", "floor_09": "ZONE A",
    "floor_10": "ZONE A", "floor_11": "ZONE A", "floor_12": "ZONE A",
    "floor_13": "ZONE A", "floor_14": "ZONE A", "floor_15": "ZONE A",
    # ZONE B: mid floors 16-30
    "floor_16": "ZONE B", "floor_17": "ZONE B", "floor_18": "ZONE B",
    "floor_19": "ZONE B", "floor_20": "ZONE B", "floor_21": "ZONE B",
    "floor_22": "ZONE B", "floor_23": "ZONE B", "floor_24": "ZONE B",
    "floor_25": "ZONE B", "floor_26": "ZONE B", "floor_27": "ZONE B",
    "floor_28": "ZONE B", "floor_29": "ZONE B", "floor_30": "ZONE B",
    # ZONE C: high floors 31-45
    "floor_31": "ZONE C", "floor_32": "ZONE C", "floor_33": "ZONE C",
    "floor_34": "ZONE C", "floor_35": "ZONE C", "floor_36": "ZONE C",
    "floor_37": "ZONE C", "floor_38": "ZONE C", "floor_39": "ZONE C",
    "floor_40": "ZONE C", "floor_41": "ZONE C", "floor_42": "ZONE C",
    "floor_43": "ZONE C", "floor_44": "ZONE C", "floor_45": "ZONE C",
    # ZONE D: executive floors 46-53 + penthouse
    "floor_46": "ZONE D", "floor_47": "ZONE D", "floor_48": "ZONE D",
    "floor_49": "ZONE D", "floor_50": "ZONE D", "floor_51": "ZONE D",
    "floor_52": "ZONE D", "floor_53": "ZONE D",
    "penthouse": "penthouse", "roof": "ZONE D",
}


class LiftNetwork:
    def __init__(self):
        self.reg = Registry()

    # ----- registration introspection ----- #

    def _serves(self, lift, stop):
        return stop in lift.get("serves", [])

    def _serves_route(self, lift, source, target):
        return self._serves(lift, source) and self._serves(lift, target)

    def _permissions_for(self, lift_id):
        from pathlib import Path
        import json
        p = Path("/vaults/nvme0/qsb_tower_v1/data/registries/lift_permissions.json")
        if not p.exists():
            return None
        try:
            for row in json.loads(p.read_text()):
                if row.get("lift") == lift_id:
                    return row
        except Exception:
            return None
        return None

    def _zone_of(self, floor_id):
        return _ZONE_MAP.get(floor_id, "unknown")

    def _gate_state(self):
        from pathlib import Path
        import json
        p = Path("/vaults/nvme0/qsb_tower_v1/penthouse/security_precheck/security_precheck.json")
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}

    # ----- enforcement ----- #

    def permission_check(self, source, target, lift_id, *,
                          sealed_packet=False, packet_type=None, worker=None):
        """Return a structured allow/block decision."""
        perm = self._permissions_for(lift_id) or {}
        sec_gate = (self._gate_state().get("security_gate") or "not_enforcing_yet")
        src_zone = self._zone_of(source)
        tgt_zone = self._zone_of(target)
        allowed_zones = perm.get("allowed_zones") or []
        allowed_packet_types = perm.get("allowed_packet_types") or []
        sealed_required = bool(perm.get("sealed_packets_required"))
        reasons = []

        # 1. sealed-packet enforcement
        if sealed_required and not sealed_packet:
            reasons.append("sealed_packet_required")

        # 2. packet-type allow-list (only if the lift declares one)
        if allowed_packet_types and packet_type and packet_type not in allowed_packet_types:
            reasons.append("packet_type_not_allowed")

        # 3. zone permission ("all" is the wildcard; non-standard tokens like
        # "selected_memory_archive_floors" are treated as lift-specific allow-lists
        # that this layer doesn't model — they pass.)
        STANDARD_ZONES = {"ZONE A", "ZONE B", "ZONE C", "ZONE D", "penthouse"}
        if (allowed_zones and "all" not in allowed_zones
            and all(z in STANDARD_ZONES for z in allowed_zones)):
            if src_zone not in allowed_zones or tgt_zone not in allowed_zones:
                if not (src_zone == "penthouse" or tgt_zone == "penthouse"):
                    reasons.append("zone_not_allowed")

        # 4. worker access-level guard (only if the floor is in their denied list)
        if worker:
            denied = (worker.get("denied_floors") or [])
            if source in denied or target in denied:
                reasons.append("worker_access_denied")

        # 5. security gate must be enforcing for routing
        if not sec_gate.startswith("enforcing"):
            reasons.append("security_gate_not_enforcing_yet")

        return {
            "lift_id": lift_id,
            "source_floor": source, "target_floor": target,
            "source_zone": src_zone, "target_zone": tgt_zone,
            "sealed_required": sealed_required,
            "sealed_supplied": bool(sealed_packet),
            "packet_type": packet_type,
            "security_gate": sec_gate,
            "allowed": (len(reasons) == 0),
            "blocked": (len(reasons) > 0),
            "reasons": reasons,
        }

    def permission_audit(self):
        """Audit every lift against every floor pair (sampled) — for the dashboard."""
        lifts = self.reg.lifts()
        rows = []
        for lift in lifts:
            perm = self._permissions_for(lift.get("id"))
            rows.append({
                "lift_id": lift.get("id"),
                "name": lift.get("name"),
                "type": lift.get("type"),
                "status": lift.get("status"),
                "serves": lift.get("serves") or [],
                "sealed_packets_required": (perm or {}).get("sealed_packets_required", False),
                "allowed_zones":            (perm or {}).get("allowed_zones") or [],
                "allowed_packet_types":     (perm or {}).get("allowed_packet_types") or [],
            })
        return {
            "lift_count": len(rows),
            "lifts": rows,
            "security_gate": (self._gate_state().get("security_gate") or "not_enforcing_yet"),
        }

    # ----- routing ----- #

    def choose(self, source, target, preferred="main"):
        lifts = self.reg.lifts()

        if preferred and preferred != "none":
            for lift in lifts:
                if lift.get("id") == preferred and self._serves_route(lift, source, target):
                    return lift

        if preferred and preferred != "none":
            for lift in lifts:
                if lift.get("type") == preferred and self._serves_route(lift, source, target):
                    return lift

        for lift in lifts:
            if self._serves_route(lift, source, target):
                return lift

        for lift in lifts:
            if lift.get("id") == "emergency_stairwell":
                return lift

        raise RuntimeError(f"No lift route available from {source} to {target}")

    def request_route(self, source, target, *,
                       preferred="main", priority=5,
                       sealed_packet=False, packet_type=None, worker=None):
        """V1.5 — enforced route request. Returns blocked decision if any check fails."""
        try:
            lift = self.choose(source, target, preferred)
        except RuntimeError as e:
            return {"ok": False, "blocked": True, "reason": str(e),
                     "source_floor": source, "target_floor": target}
        decision = self.permission_check(source, target, lift["id"],
                                          sealed_packet=sealed_packet,
                                          packet_type=packet_type,
                                          worker=worker)
        if decision["blocked"]:
            return {"ok": False, "blocked": True,
                     "reason": ",".join(decision["reasons"]),
                     "lift_id": lift["id"], "source_floor": source,
                     "target_floor": target, "decision": decision,
                     "execution_allowed": False}
        return {"ok": True, "blocked": False,
                 "lift_id": lift["id"], "lift_type": lift.get("type"),
                 "source_floor": source, "target_floor": target,
                 "decision": decision, "execution_allowed": False}

    def send(self, source, target, preferred="main", priority=5,
              *, sealed_packet=True, packet_type=None, worker=None):
        """Backwards-compatible send. New keyword args default to sealed=True
        so existing callers (which were already supposed to be sending sealed
        packets per CLAUDE.md) keep working without surprise blocks."""
        # V1.5 — enforcement happens here too.
        decision = None
        try:
            lift = self.choose(source, target, preferred)
        except RuntimeError as e:
            return {"ok": False, "blocked": True, "reason": str(e),
                     "source_floor": source, "target_floor": target}
        decision = self.permission_check(source, target, lift["id"],
                                          sealed_packet=sealed_packet,
                                          packet_type=packet_type,
                                          worker=worker)
        if decision["blocked"]:
            return {"ok": False, "blocked": True,
                     "reason": ",".join(decision["reasons"]),
                     "lift_id": lift["id"],
                     "source_floor": source, "target_floor": target,
                     "decision": decision}

        conn = connect()
        conn.execute(
            """
            INSERT INTO packets(ts, source, target, lift_id, priority, receipt, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now(), source, target, lift["id"], int(priority), "delivered", "delivered")
        )
        conn.execute(
            """
            UPDATE lift_state
            SET current_position=?, traffic_count=traffic_count+1, updated_ts=?
            WHERE lift_id=?
            """,
            (target, now(), lift["id"])
        )
        conn.commit()
        conn.close()

        return {
            "lift": lift["id"],
            "lift_type": lift.get("type"),
            "source": source,
            "target": target,
            "receipt": "delivered",
            "status": "delivered",
            "decision": decision,
        }

    def states(self):
        conn = connect()
        rows = conn.execute("SELECT * FROM lift_state ORDER BY lift_id").fetchall()
        desc = conn.execute("SELECT * FROM lift_state LIMIT 1").description
        cols = [x[0] for x in desc] if desc else []
        conn.close()
        return [dict(zip(cols, row)) for row in rows]

    def packets(self):
        conn = connect()
        rows = conn.execute("SELECT * FROM packets ORDER BY id DESC LIMIT 20").fetchall()
        desc = conn.execute("SELECT * FROM packets LIMIT 1").description
        cols = [x[0] for x in desc] if desc else []
        conn.close()
        return [dict(zip(cols, row)) for row in rows]
