import sqlite3
from datetime import datetime, UTC
from .paths import DB
from .registry import Registry
def now(): return datetime.now(UTC).isoformat()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS floor_state (floor_id TEXT PRIMARY KEY,status TEXT,health INTEGER,occupancy INTEGER,updated_ts TEXT);
CREATE TABLE IF NOT EXISTS lift_state (lift_id TEXT PRIMARY KEY,status TEXT,current_position TEXT,traffic_count INTEGER,updated_ts TEXT);
CREATE TABLE IF NOT EXISTS packets (id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,source TEXT,target TEXT,lift_id TEXT,priority INTEGER,receipt TEXT,status TEXT);
'''
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB)
def init_db():
    conn=connect(); conn.executescript(SCHEMA); reg=Registry()
    for f in reg.floors():
        conn.execute('INSERT OR IGNORE INTO floor_state VALUES (?,?,?,?,?)',(f['id'],f['status'],100,0 if f['vacant'] else len(f['workers']),now()))
    for l in reg.lifts():
        conn.execute('INSERT OR IGNORE INTO lift_state VALUES (?,?,?,?,?)',(l['id'],l['status'],'ground',0,now()))
    conn.commit(); conn.close()
if __name__ == '__main__':
    init_db(); print('SQLite initialized')
