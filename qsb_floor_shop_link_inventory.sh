#!/usr/bin/env bash
set -u

QSB="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/QSB_CONTROL_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_floor_shop_link_inventory"
REPORT="$RUN_DIR/reports/floor_shop_link_inventory_report.txt"
CSV="$RUN_DIR/reports/floor_shop_link_inventory.csv"
BAD="$RUN_DIR/reports/bad_or_missing_shop_links.txt"
IPAD_LINKS="$RUN_DIR/reports/ipad_links_found.txt"

mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/reports" "$RUN_DIR/json" "$RUN_DIR/logs" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "QSB FLOOR / SHOP / WEBSITE LINK INVENTORY"
echo "Generated: $(date -Is)"
echo "QSB root: $QSB"
echo "Run folder: $RUN_DIR"
echo "Report: $REPORT"
echo "CSV: $CSV"
echo "============================================================"
echo
echo "Purpose:"
echo " - scan every skyscraper floor and registry"
echo " - find shop/business/service names"
echo " - find website/shop URLs"
echo " - compare them against iPad dashboard links"
echo " - detect 123-reg / parked / dead links"
echo " - do not patch yet"
echo

cd "$QSB" || exit 1

python3 - "$QSB" "$CSV" "$BAD" "$IPAD_LINKS" <<'PY'
import re, csv, sys, json, subprocess, html
from pathlib import Path
from urllib.parse import urlparse

qsb = Path(sys.argv[1])
csv_path = Path(sys.argv[2])
bad_path = Path(sys.argv[3])
ipad_links_path = Path(sys.argv[4])

skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache", "models", "ollama"}
text_exts = {".py",".html",".js",".json",".jsonl",".md",".txt",".yaml",".yml",".toml",".sh",".env",".css"}

url_re = re.compile(r"""https?://[^\s'"<>),;]+""", re.I)

# Names Ross explicitly mentioned, plus broad shop/service terms.
name_patterns = [
    "Lumen AI",
    "Lumen",
    "Green Lane Cannabis Seed Company",
    "Green Lane",
    "Cannabis Seed",
    "Jim's Shop",
    "Jims Shop",
    "Jim Shop",
    "shop",
    "web shop",
    "webshop",
    "store",
    "storefront",
    "website",
    "domain",
    "123-reg",
    "123reg",
    "seed",
    "seeds",
    "company",
]

def is_text_file(p):
    if p.suffix.lower() in text_exts:
        return True
    n = p.name.lower()
    return any(x in n for x in ["floor","shop","store","website","domain","link","dash","config","registry","business"])

def floor_from_path(p):
    parts = list(p.parts)
    for part in parts:
        m = re.search(r"(floor[_\- ]?\d+[^/]*)", part, re.I)
        if m:
            return m.group(1)
    return ""

def safe_read(p):
    try:
        if p.stat().st_size > 8_000_000:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def title_from_body(body):
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if not m:
        return ""
    return html.unescape(re.sub(r"\s+"," ",m.group(1)).strip())[:160]

def test_url(url):
    # Skip local service links for public shop status, but still record.
    low = url.lower()
    if any(x in low for x in ["127.0.0.1","localhost","0.0.0.0","192.168.","10.0.","172.16.","172.17.","172.18."]):
        return {"status":"LOCAL_OR_LAN", "code":"", "final":"", "title":""}

    tmp = "/tmp/qsb_floor_shop_url_body.html"
    fmt = "CODE:%{http_code}\nFINAL:%{url_effective}\nTIME:%{time_total}\n"
    try:
        r = subprocess.run(
            ["curl","-L","-sS","--max-time","15","-A","Mozilla/5.0","-o",tmp,"-w",fmt,url],
            capture_output=True, text=True, timeout=20
        )
    except subprocess.TimeoutExpired:
        return {"status":"BAD_TIMEOUT", "code":"000", "final":"", "title":""}

    out = (r.stdout or "") + "\n" + (r.stderr or "")
    code_m = re.search(r"CODE:(\d+)", out)
    final_m = re.search(r"FINAL:(.*)", out)
    code = code_m.group(1) if code_m else "000"
    final = final_m.group(1).strip() if final_m else ""

    try:
        body = Path(tmp).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        body = ""

    title = title_from_body(body)
    blob = " ".join([url, final, title, body[:4000]]).lower()

    if "123-reg" in blob or "123reg" in blob or "123 reg" in blob:
        status = "BAD_123REG_OR_PARKED"
    elif "domain parked" in blob or ("parking" in blob and "domain" in blob):
        status = "BAD_PARKED_DOMAIN"
    elif code == "000":
        status = "BAD_NO_RESPONSE"
    else:
        try:
            c = int(code)
        except Exception:
            c = 0
        if 200 <= c < 300:
            status = "OK_PUBLIC"
        elif 300 <= c < 400:
            status = "WARN_REDIRECT"
        elif 400 <= c < 500:
            status = "BAD_CLIENT_ERROR"
        elif 500 <= c < 600:
            status = "BAD_SERVER_ERROR"
        else:
            status = "WARN_UNKNOWN"

    return {"status":status, "code":code, "final":final, "title":title}

files = []
for p in qsb.rglob("*"):
    try:
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        if not is_text_file(p):
            continue
        files.append(p)
    except Exception:
        pass

# Extract iPad links from Boardroom hub.
ipad_links = []
hub = qsb / "tools/qsb_boardroom_hub.py"
hub_txt = safe_read(hub)
for u in url_re.findall(hub_txt):
    if u not in ipad_links:
        ipad_links.append(u.rstrip("/"))

# Also capture relative routes from the hub.
for route in re.findall(r"""['"](/[^'"]+)['"]""", hub_txt):
    if route not in ipad_links and not route.startswith("//"):
        ipad_links.append(route)

ipad_links_path.write_text("\n".join(ipad_links) + "\n", encoding="utf-8")

rows = []
seen = set()

for p in files:
    txt = safe_read(p)
    if not txt:
        continue

    rel = str(p.relative_to(qsb))
    floor = floor_from_path(p)

    # URL rows.
    for m in url_re.finditer(txt):
        url = m.group(0).rstrip("\\").rstrip("/")
        line = txt[:m.start()].count("\n") + 1
        low = url.lower()

        # Keep public, shop, 123-reg, and named-site URLs. Ignore pure API endpoints unless near shop terms.
        start = max(0, m.start()-400)
        end = min(len(txt), m.end()+400)
        context = re.sub(r"\s+", " ", txt[start:end]).strip()[:500]
        ctx_low = context.lower()

        shopish = any(x.lower() in ctx_low or x.lower() in low for x in name_patterns)
        public = not any(x in low for x in ["127.0.0.1","localhost","192.168.","api.anthropic.com","api.openai.com","testnet.binance","api-fxpractice.oanda","ollama"])

        if not public and not shopish:
            continue

        key = (url, rel, line)
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "floor": floor,
            "name_hit": "",
            "url": url,
            "source_file": rel,
            "line": line,
            "context": context,
        })

    # Name rows without URL.
    lines = txt.splitlines()
    for i, line_text in enumerate(lines, 1):
        low = line_text.lower()
        hits = [n for n in name_patterns if n.lower() in low]
        if not hits:
            continue

        # Nearby URL if present.
        window = "\n".join(lines[max(0,i-4):min(len(lines),i+5)])
        urls = url_re.findall(window)
        url = urls[0].rstrip("/").rstrip("\\") if urls else ""

        context = re.sub(r"\s+", " ", window).strip()[:500]
        key = ("NAME", ",".join(hits), rel, i, url)
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "floor": floor,
            "name_hit": ",".join(hits),
            "url": url,
            "source_file": rel,
            "line": i,
            "context": context,
        })

# Test unique URLs.
url_status = {}
for r in rows:
    u = r["url"]
    if not u:
        continue
    if u not in url_status:
        print("Testing:", u)
        url_status[u] = test_url(u)

# Write CSV.
with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["floor","name_hit","url","status","http_code","final_url","title","in_ipad_links","source_file","line","context"])
    for r in rows:
        u = r["url"]
        st = url_status.get(u, {"status":"NO_URL_FOUND_NEAR_NAME","code":"","final":"","title":""})
        in_ipad = "YES" if (u and any(u.rstrip("/") == x.rstrip("/") for x in ipad_links)) else "NO"
        w.writerow([
            r["floor"], r["name_hit"], u,
            st["status"], st["code"], st["final"], st["title"],
            in_ipad, r["source_file"], r["line"], r["context"]
        ])

# Bad/missing summary.
with bad_path.open("w", encoding="utf-8") as f:
    f.write("BAD OR MISSING SHOP / WEBSITE LINKS\n\n")
    for r in rows:
        u = r["url"]
        st = url_status.get(u, {"status":"NO_URL_FOUND_NEAR_NAME","code":"","final":"","title":""})
        bad = (
            not u or
            st["status"].startswith("BAD") or
            st["status"] == "NO_URL_FOUND_NEAR_NAME" or
            (u and not any(u.rstrip("/") == x.rstrip("/") for x in ipad_links) and (r["name_hit"] or r["floor"]))
        )
        if bad:
            f.write("------------------------------------------------------------\n")
            f.write(f"floor: {r['floor']}\n")
            f.write(f"name_hit: {r['name_hit']}\n")
            f.write(f"url: {u or 'NO URL FOUND NEAR NAME'}\n")
            f.write(f"status: {st['status']}\n")
            f.write(f"http_code: {st['code']}\n")
            f.write(f"final_url: {st['final']}\n")
            f.write(f"title: {st['title']}\n")
            f.write(f"in_ipad_links: {'YES' if (u and any(u.rstrip('/') == x.rstrip('/') for x in ipad_links)) else 'NO'}\n")
            f.write(f"source: {r['source_file']}:{r['line']}\n")
            f.write(f"context: {r['context']}\n\n")

print()
print("rows:", len(rows))
print("csv:", csv_path)
print("bad_summary:", bad_path)
print("ipad_links:", ipad_links_path)
PY

echo
echo "===== QUICK SUMMARY ====="
echo
echo "CSV rows:"
wc -l "$CSV" || true

echo
echo "Bad/missing count:"
grep -c '^------------------------------------------------------------' "$BAD" 2>/dev/null || true

echo
echo "Names Ross mentioned:"
grep -iE "Lumen|Green Lane|Jim" "$CSV" || true

echo
echo "123-reg / parked:"
grep -iE "123reg|123-reg|PARKED" "$CSV" || true

echo
echo "Missing from iPad:"
awk -F',' 'NR>1 && $8=="NO" {print $1 " | " $2 " | " $3 " | " $9 ":" $10}' "$CSV" 2>/dev/null | head -120 || true

echo
echo "===== BAD OR MISSING SUMMARY PREVIEW ====="
sed -n '1,220p' "$BAD" 2>/dev/null || true

echo
echo "============================================================"
echo "DONE"
echo "Run folder:"
echo "$RUN_DIR"
echo
echo "Send these files back:"
echo "$SEND/LATEST_REPORT.txt"
echo "$SEND/floor_shop_link_inventory.csv"
echo "$SEND/bad_or_missing_shop_links.txt"
echo "============================================================"

cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"
cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$CSV" "$SEND/floor_shop_link_inventory.csv"
cp -a "$BAD" "$SEND/bad_or_missing_shop_links.txt"
cp -a "$IPAD_LINKS" "$SEND/ipad_links_found.txt"

cat > "$SEND/README_SEND_THIS.txt" <<TXT
Send these files back to ChatGPT:

1. $SEND/LATEST_REPORT.txt
2. $SEND/floor_shop_link_inventory.csv
3. $SEND/bad_or_missing_shop_links.txt

This run scanned floors and registries for:
- Lumen AI
- Green Lane Cannabis Seed Company
- Jim's Shop
- shop/store/web/domain links
- 123-reg/parked domains
- links missing from the iPad dashboard

Original run:
$RUN_DIR
TXT

xdg-open "$SEND" >/dev/null 2>&1 &
