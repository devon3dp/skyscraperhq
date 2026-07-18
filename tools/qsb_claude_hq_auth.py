#!/usr/bin/env python3
"""
QSB CLAUDE HQ AUTH CORE  (action_id=CLAUDE-HQ-DASHBOARD-HARDENING-V1, Phase 3)

HTTP-agnostic authentication core for the :8858 Claude HQ dashboard. Provides:
scrypt password hashing, account storage, server-side sessions (opaque token, only
its SHA-256 stored), per-session CSRF token, role model, login rate limiting, and an
append-only audit log. NO plaintext passwords. NO secrets in logs/reports.

Storage (ross-only): runtime/claude_hq_auth/{auth.sqlite3 (0600), audit.jsonl (0600)}, dir 0700.
"""
import os, json, sqlite3, hashlib, hmac, secrets, time, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
AUTH_DIR = ROOT / "runtime/claude_hq_auth"
DB_PATH = AUTH_DIR / "auth.sqlite3"
AUDIT_PATH = AUTH_DIR / "audit.jsonl"

ROLES = {"ROSS", "WREN", "PHYSICAL_WORKER", "VIEW_ONLY"}
# central route/action permission matrix (Phase 3F)
ROLE_ACTIONS = {
    "ROSS": {"draft", "send-to-wren", "approve", "start-approved-job", "launch",
             "freeze", "stop", "reject", "request-evidence", "prepare-review", "prepare-ross-review", "read"},
    "WREN": {"send-to-wren", "review", "freeze", "reject", "request-evidence", "prepare-review", "prepare-ross-review", "read"},
    "PHYSICAL_WORKER": {"draft", "read"},
    "VIEW_ONLY": {"read"},
}
# actions no role may ever perform (no Claude self-accept, no Wren final-accept)
FORBIDDEN_ACTIONS = {"accept", "final-accept", "self-approve", "self-verify", "self-close", "manage-accounts", "change-role"}

# scrypt parameters
SCRYPT_N, SCRYPT_R, SCRYPT_P, DKLEN = 2 ** 14, 8, 1, 32
MIN_PW_LEN = 14
COMMON_BAD = {"password", "password123", "changeme", "letmein", "admin", "administrator",
              "qwerty", "12345678", "11111111", "ross", "claude", "skyscraper", "default",
              "passw0rd", "welcome", "iloveyou", "00000000", "abc12345", "qsbtower"}
SESSION_ABSOLUTE = 8 * 3600     # 8 hours
SESSION_IDLE = 30 * 60          # 30 minutes
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 10 * 60          # 10 minutes
CONTROL_MAX_PER_MIN = 60

_login_fails = {}               # source_ip -> [timestamps]
_control_hits = {}              # token_hash -> [timestamps]


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dir():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(AUTH_DIR, 0o700)
    except Exception:
        pass


def _connect():
    _ensure_dir()
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    _ensure_dir()
    con = _connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts(
          username TEXT PRIMARY KEY, role TEXT NOT NULL, algo TEXT NOT NULL,
          salt BLOB NOT NULL, hash BLOB NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
          created TEXT NOT NULL, last_login TEXT, fail_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL,
          csrf TEXT NOT NULL, created REAL NOT NULL, last_seen REAL NOT NULL);
        """)
    con.commit(); con.close()
    for p in (DB_PATH, AUDIT_PATH):
        try:
            if not p.exists() and p == AUDIT_PATH:
                p.write_text("")
            os.chmod(p, 0o600)
        except Exception:
            pass


def audit(event, actor=None, role=None, source=None, route=None, result=None, reason=None, ref=None):
    """Append-only audit. NEVER records passwords/tokens/cookies/CSRF/API keys/sudo secrets."""
    _ensure_dir()
    row = {"ts": utc(), "event": event, "actor": actor, "role": role, "source": source,
           "route": route, "result": result, "reason": reason, "ref": ref}
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(row) + "\n")
    try:
        os.chmod(AUDIT_PATH, 0o600)
    except Exception:
        pass


def _hash_pw(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN)


def validate_password_strength(password):
    if len(password) < MIN_PW_LEN:
        return False, "password must be at least %d characters" % MIN_PW_LEN
    if password.lower() in COMMON_BAD:
        return False, "password is a common/default value"
    if re.fullmatch(r"(.)\1+", password):
        return False, "password is a single repeated character"
    return True, ""


def create_account(username, role, password, db=None):
    role = role.upper()
    if role not in ROLES:
        raise ValueError("unknown role %r" % role)
    ok, why = validate_password_strength(password)
    if not ok:
        raise ValueError(why)
    salt = secrets.token_bytes(16)
    h = _hash_pw(password, salt)
    con = db or _connect()
    con.execute("INSERT OR REPLACE INTO accounts(username,role,algo,salt,hash,enabled,created,last_login,fail_count)"
                " VALUES(?,?,?,?,?,1,?,NULL,0)",
                (username, role, "scrypt:n=%d,r=%d,p=%d" % (SCRYPT_N, SCRYPT_R, SCRYPT_P), salt, h, utc()))
    con.commit()
    if db is None:
        con.close()
    try:
        os.chmod(DB_PATH, 0o600)
    except Exception:
        pass
    audit("account_created", actor=username, role=role, result="ok")


def _rate_login_ok(source):
    now = time.time()
    _login_fails.setdefault(source, [])
    _login_fails[source] = [t for t in _login_fails[source] if now - t < LOGIN_WINDOW]
    return len(_login_fails[source]) < LOGIN_MAX_FAILS


def verify_login(username, password, source, db=None):
    """Returns (ok, token, csrf, role). Generic failure; never reveals if username exists."""
    if not _rate_login_ok(source):
        audit("login_locked", actor=username, source=source, result="denied", reason="rate_limit")
        return False, None, None, None
    con = db or _connect()
    row = con.execute("SELECT role,salt,hash,enabled FROM accounts WHERE username=?", (username,)).fetchone()
    ok = False; role = None
    if row and row[3] == 1:
        role = row[0]
        calc = _hash_pw(password, row[1])
        ok = hmac.compare_digest(calc, row[2])
    if not ok:
        _login_fails.setdefault(source, []).append(time.time())
        audit("login_fail", actor=username, source=source, result="denied", reason="bad_credentials")
        if db is None:
            con.close()
        return False, None, None, None
    # success: clear failures, rotate a fresh session token
    _login_fails[source] = []
    token = secrets.token_urlsafe(32)
    th = hashlib.sha256(token.encode()).hexdigest()
    csrf = secrets.token_urlsafe(24)
    now = time.time()
    con.execute("DELETE FROM sessions WHERE username=?", (username,))   # single active session per user (rotate)
    con.execute("INSERT INTO sessions(token_hash,username,role,csrf,created,last_seen) VALUES(?,?,?,?,?,?)",
                (th, username, role, csrf, now, now))
    con.execute("UPDATE accounts SET last_login=?, fail_count=0 WHERE username=?", (utc(), username))
    con.commit()
    if db is None:
        con.close()
    audit("login_success", actor=username, role=role, source=source, result="ok")
    return True, token, csrf, role


def get_session(token, db=None):
    """Validate a raw session token; enforce absolute + idle expiry; refresh last_seen. Returns dict or None."""
    if not token:
        return None
    th = hashlib.sha256(token.encode()).hexdigest()
    con = db or _connect()
    row = con.execute("SELECT username,role,csrf,created,last_seen FROM sessions WHERE token_hash=?", (th,)).fetchone()
    if not row:
        if db is None:
            con.close()
        return None
    username, role, csrf, created, last_seen = row
    now = time.time()
    if now - created > SESSION_ABSOLUTE or now - last_seen > SESSION_IDLE:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (th,)); con.commit()
        if db is None:
            con.close()
        audit("session_expired", actor=username, role=role, result="denied", reason="expired")
        return None
    # account still enabled?
    acc = con.execute("SELECT enabled FROM accounts WHERE username=?", (username,)).fetchone()
    if not acc or acc[0] != 1:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (th,)); con.commit()
        if db is None:
            con.close()
        return None
    con.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, th)); con.commit()
    if db is None:
        con.close()
    return {"username": username, "role": role, "csrf": csrf}


def logout(token, db=None):
    if not token:
        return
    th = hashlib.sha256(token.encode()).hexdigest()
    con = db or _connect()
    row = con.execute("SELECT username FROM sessions WHERE token_hash=?", (th,)).fetchone()
    con.execute("DELETE FROM sessions WHERE token_hash=?", (th,)); con.commit()
    if db is None:
        con.close()
    if row:
        audit("logout", actor=row[0], result="ok")


def check_csrf(session_csrf, presented):
    return bool(session_csrf) and bool(presented) and hmac.compare_digest(str(session_csrf), str(presented))


def control_rate_ok(token):
    th = hashlib.sha256(token.encode()).hexdigest() if token else "anon"
    now = time.time()
    _control_hits.setdefault(th, [])
    _control_hits[th] = [t for t in _control_hits[th] if now - t < 60]
    if len(_control_hits[th]) >= CONTROL_MAX_PER_MIN:
        return False
    _control_hits[th].append(now)
    return True


def role_can(role, action):
    if role not in ROLES:
        return False
    if action in FORBIDDEN_ACTIONS:
        return False
    return action in ROLE_ACTIONS.get(role, set())
