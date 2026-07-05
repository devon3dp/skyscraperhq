from pathlib import Path
import textwrap

ROOT = Path("/vaults/nvme0/qsb_tower_v1")

def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

print("Repairing Lift Network V1.2...")

write("src/tower/lifts.py", r'''
from .database import connect, now
from .registry import Registry

class LiftNetwork:
    def __init__(self):
        self.reg = Registry()

    def _serves(self, lift, stop):
        return stop in lift.get("serves", [])

    def _serves_route(self, lift, source, target):
        return self._serves(lift, source) and self._serves(lift, target)

    def choose(self, source, target, preferred="main"):
        lifts = self.reg.lifts()

        # Preferred may be a lift ID, such as "model_lift" or "service_lift".
        if preferred and preferred != "none":
            for lift in lifts:
                if lift.get("id") == preferred and self._serves_route(lift, source, target):
                    return lift

        # Preferred may also be a lift type, such as "main", "model", or "service".
        if preferred and preferred != "none":
            for lift in lifts:
                if lift.get("type") == preferred and self._serves_route(lift, source, target):
                    return lift

        # Fallback to any lift that serves both source and target.
        for lift in lifts:
            if self._serves_route(lift, source, target):
                return lift

        # Final safe fallback.
        for lift in lifts:
            if lift.get("id") == "emergency_stairwell":
                return lift

        raise RuntimeError(f"No lift route available from {source} to {target}")

    def send(self, source, target, preferred="main", priority=5):
        lift = self.choose(source, target, preferred)
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
            "status": "delivered"
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
''')

write("tests/test_lift_network_v12.py", """
import sys
from pathlib import Path

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
sys.path.insert(0, str(ROOT / 'src'))

from tower.lifts import LiftNetwork

lift = LiftNetwork()

a = lift.send('floor_24', 'floor_27', 'model_lift', 5)
assert a['lift'] == 'model_lift', a

b = lift.send('floor_05', 'floor_24', 'service_lift', 5)
assert b['lift'] == 'service_lift', b

c = lift.send('ground', 'floor_01', 'main', 5)
assert c['lift'] in ['main_low_rise', 'service_lift', 'emergency_stairwell'], c

print('LIFT NETWORK V1.2 VALIDATION PASSED')
print('Model lift route:', a)
print('Service lift route:', b)
print('Main route:', c)
""")

print("Lift Network V1.2 repair written.")
