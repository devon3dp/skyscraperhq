#!/usr/bin/env python3
"""
QSB CLAUDE HQ AUTH INIT  (action_id=CLAUDE-HQ-DASHBOARD-HARDENING-V1, Phase 3B)

Interactive account initialiser for the :8858 Claude HQ dashboard. Ross runs this
LOCALLY to set his own password — Claude never selects or sees it.

Usage (interactive, password via getpass ONLY):
  python3 tools/qsb_claude_hq_auth_init.py --username ross --role ROSS

It REFUSES any non-interactive password argument. It never echoes the password and
never places it in process arguments.
"""
import argparse, getpass, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qsb_claude_hq_auth as auth


def main():
    ap = argparse.ArgumentParser(description="Initialise a Claude HQ dashboard account (interactive).")
    ap.add_argument("--username", required=True)
    ap.add_argument("--role", required=True, choices=sorted(auth.ROLES))
    # Trap any attempt to pass a password non-interactively:
    ap.add_argument("--password", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.password is not None:
        print("REFUSED: passwords must be entered interactively (getpass), never as an argument.")
        sys.exit(2)
    if not sys.stdin.isatty():
        print("REFUSED: this initialiser must be run interactively in a terminal (no piped password).")
        sys.exit(2)

    auth.init_db()
    print("Claude HQ auth init — user=%s role=%s" % (a.username, a.role))
    print("Password rules: >= %d chars, not a common/default value. It will NOT be echoed." % auth.MIN_PW_LEN)
    pw1 = getpass.getpass("New password: ")
    ok, why = auth.validate_password_strength(pw1)
    if not ok:
        print("REJECTED:", why); sys.exit(3)
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("REJECTED: passwords do not match."); sys.exit(3)
    auth.create_account(a.username, a.role, pw1)
    del pw1, pw2
    print("OK: account '%s' (role %s) created/updated." % (a.username, a.role))
    print("DB: %s (0600)  ·  audit: %s (0600)  ·  dir 0700" % (auth.DB_PATH, auth.AUDIT_PATH))


if __name__ == "__main__":
    main()
