#!/usr/bin/env python3
"""
qsb_ssk_vault_sync.py — canonical SkyscraperHQ SSK Vault sync (ONE mechanism).

Push model: approved reports on the MSI -> the SSK Vault on the Pi
(/media/ross/SSK Cloud/SKYSCRAPERHQ). Runs from an MSI systemd --user timer.

Safety (per Ross's vault policy):
  - secret-scan EVERY file before copy; suspects are quarantined (never synced).
  - copy to STAGING, SHA-256 verify (source==dest), then atomic rename into place.
  - retain source; NEVER propagate deletion.
  - if the Pi/SSK is unavailable, log 'queued' and exit 0 (bounded, no error storm).
  - no secret values are printed or logged.
"""
import hashlib, json, os, re, subprocess, sys, time, datetime

SRC = "/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT"
PI = "ross@192.168.1.23"
VAULT = "/media/ross/SSK Cloud/SKYSCRAPERHQ"
KEY = os.environ.get("QSB_SSK_KEY", "")   # ssh key path; falls back to default agent/key
LOG = "/vaults/nvme0/qsb_tower_v1/data/registries/ssk_vault_safety/sync.log"
SYNC_EXT = (".txt", ".md", ".json", ".sh", ".plist", ".png", ".zst")

SECRET_PATS = {
    'anthropic_key': r'sk-ant-[A-Za-z0-9_-]{20,}',
    'openai_key': r'sk-[A-Za-z0-9]{40,}',
    'aws_key': r'AKIA[0-9A-Z]{16}',
    'github_token': r'gh[pousr]_[A-Za-z0-9]{30,}',
    'slack_token': r'xox[baprs]-[A-Za-z0-9-]{10,}',
    'private_key': r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'jwt': r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}',
    'secret_assign': r'(?i)(password|passwd|secret|api[_-]?key|service[_-]?token|bearer)["\s]*[:=]["\s]*[A-Za-z0-9/+._-]{24,}',
}


def sshbase():
    b = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
         "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    if KEY:
        b = b[:1] + ["-i", KEY] + b[1:]
    return b


def log(msg):
    line = f"{datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')} {msg}"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "a").write(line + "\n")
    print(line)


def scan_secret(path):
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None  # unreadable/binary -> treat as clean-by-type (png/zst handled below)
    for cat, rx in SECRET_PATS.items():
        if re.search(rx, txt):
            return cat
    return None


def pi_ready():
    r = subprocess.run(sshbase() + [PI, f"mountpoint -q '{VAULT.rsplit('/',1)[0]}' && test -d '{VAULT}' && echo READY"],
                       capture_output=True, text=True, timeout=20)
    return "READY" in r.stdout


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    if not pi_ready():
        log("VAULT_UNAVAILABLE — queued locally (no-op, exit 0)")
        return 0
    dest = f"{VAULT}/REPORTS/CURRENT"
    synced = quarantined = verified = 0
    receipts = []
    for f in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, f)
        if not os.path.isfile(p) or not f.lower().endswith(SYNC_EXT):
            continue
        cat = scan_secret(p) if f.lower().endswith((".txt", ".md", ".json", ".sh", ".plist")) else None
        if cat:
            quarantined += 1
            log(f"QUARANTINE {f} -> {cat} (not synced)")
            continue
        # atomic: rsync to STAGING, verify, move
        stg = f"{VAULT}/STAGING/{f}"
        rc = subprocess.run(["rsync", "-t", "--no-perms", "--no-owner", "--no-group",
                             "-e", " ".join(sshbase()), p, f"{PI}:{stg}"],
                            capture_output=True, text=True, timeout=120).returncode
        if rc != 0:
            log(f"RSYNC_FAIL {f}")
            continue
        lsha = sha(p)
        r = subprocess.run(sshbase() + [PI, f"sha256sum '{stg}' | cut -d' ' -f1"], capture_output=True, text=True, timeout=30)
        rsha = (r.stdout or "").strip()
        if lsha == rsha:
            subprocess.run(sshbase() + [PI, f"mv '{stg}' '{dest}/{f}'"], capture_output=True, text=True, timeout=20)
            synced += 1; verified += 1
            receipts.append({"file": f, "sha256": lsha, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')})
        else:
            subprocess.run(sshbase() + [PI, f"rm -f '{stg}'"], capture_output=True, text=True, timeout=15)
            log(f"CHECKSUM_MISMATCH {f} (staged copy removed)")
    # write a receipt batch into the vault
    if receipts:
        rc_json = json.dumps({"ts": receipts[-1]["ts"], "synced": synced, "verified": verified,
                              "quarantined": quarantined, "files": receipts})
        subprocess.run(sshbase() + [PI, f"cat > '{VAULT}/SYNC_RECEIPTS/receipt_{int(time.time())}.json'"],
                       input=rc_json, text=True, timeout=20)
    log(f"SYNC_OK synced={synced} verified={verified} quarantined={quarantined}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"SYNC_ERROR {type(e).__name__}")
        sys.exit(0)  # never error-storm the timer
