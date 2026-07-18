#!/usr/bin/env bash
set -u

RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_check_all_vault_claude_keys"
REPORT="$RUN_DIR/reports/all_vault_claude_keys_report.txt"

mkdir -p "$RUN_DIR/reports" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ — CHECK ALL VAULT CLAUDE API KEYS"
echo "Generated: $(date -Is)"
echo "Run folder: $RUN_DIR"
echo "Report: $REPORT"
echo "============================================================"
echo
echo "SAFETY:"
echo " - This will NOT print full API keys."
echo " - It prints masked key + SHA256 fingerprint only."
echo " - It tests keys with Anthropic read/model check and a tiny 1-token chat check."
echo " - No trading. No orders. No writes to providers."
echo

python3 - <<'PY'
import os, re, json, time, hashlib, subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOTS = [
    Path("/vaults/nvme0/qsb_tower_v1"),
    Path("/vaults/nvme0/qsb_skyscraper"),
    Path("/vaults/ai"),
    Path.home(),
]

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".cache", "cache", "models", "model", "ollama", "huggingface",
    "datasets", "downloads"
}

NAME_HINTS = [
    "env", "key", "token", "secret", "vault", "claude",
    "anthropic", "credential", "credentials", "config"
]

KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")

def mask(k):
    if len(k) <= 26:
        return k[:6] + "..." + k[-4:]
    return k[:14] + "..." + k[-8:]

def fp(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]

def safe_err(text):
    if not text:
        return ""
    text = KEY_RE.sub(lambda m: mask(m.group(0)), text)
    text = text.replace("\n", " ")
    return text[:500]

def http_json(url, headers, body=None, timeout=20):
    data = None
    method = "GET"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        method = "POST"
        headers = dict(headers)
        headers["content-type"] = "application/json"

    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw}
            return r.status, parsed, raw
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return e.code, parsed, raw
    except URLError as e:
        return 0, {"error": str(e)}, str(e)
    except Exception as e:
        return 0, {"error": str(e)}, str(e)

def classify(status, raw):
    s = (raw or "").lower()

    if status == 200:
        return "OK"

    if status == 401:
        return "INVALID_KEY"

    if "invalid x-api-key" in s or "invalid api key" in s or "authentication_error" in s:
        return "INVALID_KEY"

    if "credit" in s or "balance" in s or "billing" in s or "quota" in s:
        return "LOW_CREDIT_OR_BILLING"

    if status == 429 or "rate" in s:
        return "RATE_LIMITED"

    if status == 403 or "permission" in s or "forbidden" in s:
        return "FORBIDDEN_OR_NO_PERMISSION"

    if status == 0:
        return "NETWORK_OR_CURL_ERROR"

    return f"HTTP_{status}"

def choose_model(models_json):
    ids = []
    try:
        data = models_json.get("data", [])
        for m in data:
            mid = m.get("id")
            if mid:
                ids.append(mid)
    except Exception:
        pass

    preferred = [
        "claude-3-5-haiku-latest",
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-latest",
        "claude-sonnet-4-5",
        "claude-opus-4-1",
    ]

    for p in preferred:
        if p in ids:
            return p

    for mid in ids:
        if "haiku" in mid.lower():
            return mid

    for mid in ids:
        if "sonnet" in mid.lower():
            return mid

    return ids[0] if ids else "claude-3-5-haiku-latest"

found = {}

def add_key(key, source):
    found.setdefault(key, {
        "masked": mask(key),
        "fingerprint": fp(key),
        "sources": set(),
        "process_sources": set(),
    })
    found[key]["sources"].add(source)
    if source.startswith("process_env:"):
        found[key]["process_sources"].add(source)

print("===== 1. SCANNING RUNNING PROCESS ENVIRONMENTS =====")
ps = subprocess.run(
    ["ps", "-eo", "pid,ppid,comm,args"],
    capture_output=True,
    text=True
).stdout

candidate_pids = []
for line in ps.splitlines():
    low = line.lower()
    if any(x in low for x in [
        "qsb_boardroom_hub.py",
        "qsb_brain_router.py",
        "qsb_hq_claude_dash.py",
        "claude",
        "anthropic"
    ]):
        print(line[:300])
        parts = line.split(None, 3)
        if parts and parts[0].isdigit():
            candidate_pids.append(parts[0])

for pid in sorted(set(candidate_pids)):
    envp = Path(f"/proc/{pid}/environ")
    try:
        raw = envp.read_bytes().replace(b"\x00", b"\n").decode("utf-8", "ignore")
    except Exception as e:
        print(f"pid={pid} env read failed: {e}")
        continue

    hits = KEY_RE.findall(raw)
    if hits:
        for k in hits:
            add_key(k, f"process_env:pid={pid}")
        print(f"pid={pid} contains {len(set(hits))} Claude key(s)")
    else:
        print(f"pid={pid} no visible sk-ant key in env")

print()
print("===== 2. SCANNING VAULT / CONFIG FILES =====")

files_seen = 0
files_with_keys = 0

for root in ROOTS:
    if not root.exists():
        continue

    for p in root.rglob("*"):
        try:
            if not p.is_file():
                continue

            if any(part in SKIP_DIRS for part in p.parts):
                continue

            name_low = p.name.lower()
            path_low = str(p).lower()

            if not any(h in name_low or h in path_low for h in NAME_HINTS):
                continue

            if p.stat().st_size > 2_000_000:
                continue

            files_seen += 1
            txt = p.read_text(encoding="utf-8", errors="ignore")
            hits = KEY_RE.findall(txt)

            if hits:
                files_with_keys += 1
                for k in hits:
                    add_key(k, str(p))

        except Exception:
            continue

print(f"Files scanned: {files_seen}")
print(f"Files containing Claude keys: {files_with_keys}")
print(f"Unique Claude keys found: {len(found)}")

print()
print("===== 3. TESTING EACH CLAUDE KEY =====")

if not found:
    print("NO CLAUDE sk-ant KEYS FOUND.")
else:
    rows = []

    for idx, key in enumerate(sorted(found.keys(), key=lambda k: fp(k)), 1):
        info = found[key]
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }

        print()
        print("------------------------------------------------------------")
        print(f"KEY #{idx}")
        print(f"masked:      {info['masked']}")
        print(f"fingerprint: {info['fingerprint']}")

        if info["process_sources"]:
            print("loaded_now:  YES")
            for s in sorted(info["process_sources"]):
                print(f"  active source: {s}")
        else:
            print("loaded_now:  NO")

        print(f"file/process sources: {len(info['sources'])}")
        for s in sorted(info["sources"])[:12]:
            print(f"  source: {s}")
        if len(info["sources"]) > 12:
            print(f"  ... plus {len(info['sources']) - 12} more")

        status, parsed, raw = http_json(
            "https://api.anthropic.com/v1/models",
            headers=headers,
            timeout=20
        )
        model_status = classify(status, raw)
        print(f"models_check: HTTP {status} => {model_status}")

        model_used = ""
        chat_status = "NOT_RUN"

        if status == 200:
            model_used = choose_model(parsed)
            print(f"test_model:   {model_used}")

            body = {
                "model": model_used,
                "max_tokens": 1,
                "messages": [
                    {"role": "user", "content": "ping"}
                ]
            }

            c_status, c_parsed, c_raw = http_json(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                body=body,
                timeout=30
            )
            chat_status = classify(c_status, c_raw)
            print(f"chat_check:  HTTP {c_status} => {chat_status}")

            if c_status != 200:
                print(f"chat_error:  {safe_err(c_raw)}")
        else:
            print(f"models_error: {safe_err(raw)}")

        rows.append({
            "idx": idx,
            "masked": info["masked"],
            "fingerprint": info["fingerprint"],
            "loaded_now": bool(info["process_sources"]),
            "models_check": model_status,
            "chat_check": chat_status,
            "model_used": model_used,
            "sources": sorted(info["sources"]),
        })

        time.sleep(0.4)

    print()
    print("============================================================")
    print("SUMMARY")
    print("============================================================")

    active = [r for r in rows if r["loaded_now"]]
    usable = [r for r in rows if r["chat_check"] == "OK"]
    low_credit = [r for r in rows if "LOW_CREDIT" in r["chat_check"] or "LOW_CREDIT" in r["models_check"]]
    invalid = [r for r in rows if "INVALID" in r["chat_check"] or "INVALID" in r["models_check"]]

    print(f"Unique Claude keys found: {len(rows)}")
    print(f"Loaded by running process now: {len(active)}")
    print(f"Chat usable now: {len(usable)}")
    print(f"Low credit / billing blocked: {len(low_credit)}")
    print(f"Invalid keys: {len(invalid)}")

    print()
    print("TABLE:")
    print("IDX | LOADED_NOW | MODELS_CHECK | CHAT_CHECK | FINGERPRINT | MASKED")
    for r in rows:
        print(
            f"{r['idx']:>3} | "
            f"{'YES' if r['loaded_now'] else 'NO ':>10} | "
            f"{r['models_check']:<23} | "
            f"{r['chat_check']:<23} | "
            f"{r['fingerprint']} | "
            f"{r['masked']}"
        )

    print()
    print("WHAT THIS MEANS:")
    print(" - LOADED_NOW=YES means that key is inside a currently running SkyscraperHQ/Claude process environment.")
    print(" - CHAT_CHECK=OK means the key works for a real Claude message.")
    print(" - LOW_CREDIT_OR_BILLING means the key is real but cannot currently pay/run.")
    print(" - INVALID_KEY means do not use that key.")
    print(" - If the wrong key is LOADED_NOW=YES, restart the service after changing the vault/env key.")
PY

echo
echo "============================================================"
echo "DONE"
echo "Report copied to:"
echo "$REPORT"
echo "$SEND/LATEST_REPORT.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
