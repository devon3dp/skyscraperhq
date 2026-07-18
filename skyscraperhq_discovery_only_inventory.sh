#!/usr/bin/env bash
set -u

PROJECT="/vaults/nvme0/qsb_tower_v1"
RUN_ROOT="/home/ross/Desktop/SKYSCRAPERHQ_RUNS"
SEND="$RUN_ROOT/00_SEND_THIS_TO_CHATGPT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$RUN_ROOT/${STAMP}_discovery_only_inventory"

mkdir -p "$RUN_DIR/reports" "$RUN_DIR/json" "$RUN_DIR/scripts" "$SEND"
rm -f "$RUN_ROOT/LATEST"
ln -s "$RUN_DIR" "$RUN_ROOT/LATEST"

REPORT="$RUN_DIR/reports/LATEST_REPORT.txt"
CSV="$RUN_DIR/reports/discovered_links.csv"
FLOORS="$RUN_DIR/reports/discovered_floors.txt"
BROKEN="$RUN_DIR/reports/broken_or_missing_connections.txt"

exec > >(tee "$REPORT") 2>&1

echo "============================================================"
echo "SKYSCRAPERHQ DISCOVERY-ONLY INVENTORY"
echo "Generated: $(date -Is)"
echo "Project: $PROJECT"
echo "Run folder: $RUN_DIR"
echo "============================================================"
echo
echo "Rules:"
echo " - discovery only"
echo " - no guessed shop names"
echo " - no guessed websites"
echo " - no patches"
echo " - no dashboard replacement"
echo " - report only what exists in files or live routes"
echo

cd "$PROJECT" || exit 1

python3 - "$PROJECT" "$CSV" "$FLOORS" "$BROKEN" <<'PY'
import re, csv, sys, json, subprocess, html
from pathlib import Path
from urllib.parse import urlparse

root = Path(sys.argv[1])
csv_path = Path(sys.argv[2])
floors_path = Path(sys.argv[3])
broken_path = Path(sys.argv[4])

skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache", "models", "ollama"}
text_exts = {".py",".html",".js",".json",".jsonl",".md",".txt",".yaml",".yml",".toml",".sh",".env",".css"}

url_re = re.compile(r"""https?://[^\s'"<>),;]+""", re.I)
route_re = re.compile(r"""['"](/[^'"\s<>]+)['"]""")
title_re = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
json_name_re = re.compile(r'''"(name|title|label|display_name|site|website|url|domain|shop|store)"\s*:\s*"([^"]{1,200})"''', re.I)
heading_re = re.compile(r"^\s{0,3}#{1,4}\s+(.{2,160})\s*$", re.M)

def safe_read(p):
    try:
        if p.stat().st_size > 8_000_000:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def is_text(p):
    return p.suffix.lower() in text_exts or any(x in p.name.lower() for x in ["floor","department","dashboard","registry","site","link","domain","shop","store"])

def floor_from_path(p):
    for part in p.parts:
        m = re.search(r"(floor[_\- ]?\d+[^/]*)", part, re.I)
        if m:
            return m.group(1)
    return ""

def title_from_html(txt):
    m = title_re.search(txt)
    if not m:
        return ""
    return html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())[:160]

def curl_test(url):
    low = url.lower()
    if any(x in low for x in ["127.0.0.1", "localhost", "0.0.0.0", "192.168.", "10.0.", "172.16.", "172.17.", "172.18."]):
        return {"status":"LOCAL_OR_LAN_NOT_PUBLIC", "code":"", "final":"", "title":""}

    tmp = "/tmp/skyscraperhq_discovery_url.html"
    fmt = "CODE:%{http_code}\nFINAL:%{url_effective}\nTIME:%{time_total}\n"
    try:
        r = subprocess.run(
            ["curl","-L","-sS","--max-time","15","-A","Mozilla/5.0","-o",tmp,"-w",fmt,url],
            capture_output=True, text=True, timeout=20
        )
    except subprocess.TimeoutExpired:
        return {"status":"BAD_TIMEOUT", "code":"000", "final":"", "title":""}

    out = (r.stdout or "") + "\n" + (r.stderr or "")
    cm = re.search(r"CODE:(\d+)", out)
    fm = re.search(r"FINAL:(.*)", out)
    code = cm.group(1) if cm else "000"
    final = fm.group(1).strip() if fm else ""

    body = Path(tmp).read_text(encoding="utf-8", errors="ignore") if Path(tmp).exists() else ""
    title = title_from_html(body)
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
for p in root.rglob("*"):
    try:
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        if is_text(p):
            files.append(p)
    except Exception:
        pass

floor_blocks = []
rows = []
seen = set()

for p in sorted(files):
    rel = str(p.relative_to(root))
    txt = safe_read(p)
    if not txt:
        continue

    floor = floor_from_path(p)

    if floor:
        names = []
        title = title_from_html(txt)
        if title:
            names.append("html_title=" + title)
        for h in heading_re.findall(txt):
            names.append("heading=" + h.strip())
        for k,v in json_name_re.findall(txt):
            if k.lower() in {"name","title","label","display_name"}:
                names.append(f"{k}={v}")
        urls = url_re.findall(txt)
        floor_blocks.append((floor, rel, names[:20], urls[:20]))

    for m in url_re.finditer(txt):
        url = m.group(0).rstrip("\\").rstrip("/")
        line = txt[:m.start()].count("\n") + 1
        context = re.sub(r"\s+", " ", txt[max(0,m.start()-250):min(len(txt),m.end()+250)]).strip()[:500]
        key = (url, rel, line)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "kind":"url",
            "floor":floor,
            "name":"",
            "url":url,
            "route":"",
            "source":rel,
            "line":line,
            "context":context
        })

    for m in route_re.finditer(txt):
        route = m.group(1)
        if len(route) > 180:
            continue
        line = txt[:m.start()].count("\n") + 1
        context = re.sub(r"\s+", " ", txt[max(0,m.start()-180):min(len(txt),m.end()+180)]).strip()[:400]
        key = ("ROUTE", route, rel, line)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "kind":"route",
            "floor":floor,
            "name":"",
            "url":"",
            "route":route,
            "source":rel,
            "line":line,
            "context":context
        })

    title = title_from_html(txt)
    if title:
        rows.append({
            "kind":"html_title",
            "floor":floor,
            "name":title,
            "url":"",
            "route":"",
            "source":rel,
            "line":"",
            "context":"HTML title found"
        })

    for k,v in json_name_re.findall(txt):
        rows.append({
            "kind":"named_field",
            "floor":floor,
            "name":f"{k}={v}",
            "url":v if v.startswith("http") else "",
            "route":"",
            "source":rel,
            "line":"",
            "context":"Named field found exactly as written"
        })

# Test unique URLs.
status = {}
for r in rows:
    u = r["url"]
    if u and u not in status:
        status[u] = curl_test(u)

# Current iPad links.
hub = root / "tools/qsb_boardroom_hub.py"
hub_txt = safe_read(hub)
ipad_urls = set(u.rstrip("/") for u in url_re.findall(hub_txt))
ipad_routes = set(route_re.findall(hub_txt))

with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["kind","floor","name_exactly_found","url","route","status","http_code","final_url","page_title","in_ipad_dashboard","source_file","line","evidence_context"])
    for r in rows:
        u = r["url"]
        st = status.get(u, {"status":"","code":"","final":"","title":""})
        in_ipad = "NO"
        if u and u.rstrip("/") in ipad_urls:
            in_ipad = "YES_URL"
        if r["route"] and r["route"] in ipad_routes:
            in_ipad = "YES_ROUTE"
        w.writerow([
            r["kind"], r["floor"], r["name"], u, r["route"],
            st["status"], st["code"], st["final"], st["title"],
            in_ipad, r["source"], r["line"], r["context"]
        ])

with floors_path.open("w", encoding="utf-8") as f:
    f.write("SECTION 1 — DISCOVERED FLOORS AND WHAT THEY CONTAIN\n\n")
    if not floor_blocks:
        f.write("No floor folders found.\n")
    for floor, rel, names, urls in floor_blocks:
        f.write("="*80 + "\n")
        f.write(f"floor: {floor}\n")
        f.write(f"source_file: {rel}\n")
        if names:
            f.write("names/titles/headings exactly found:\n")
            for n in names:
                f.write(f" - {n}\n")
        if urls:
            f.write("urls found:\n")
            for u in urls:
                f.write(f" - {u}\n")
        f.write("\n")

with broken_path.open("w", encoding="utf-8") as f:
    f.write("SECTION 3 — BROKEN OR MISSING CONNECTIONS\n\n")
    count = 0
    for r in rows:
        u = r["url"]
        if not u:
            continue
        st = status.get(u, {})
        s = st.get("status","")
        bad = s.startswith("BAD") or s.startswith("WARN")
        missing_ipad = r["kind"] == "url" and r["floor"] and u.rstrip("/") not in ipad_urls
        if bad or missing_ipad:
            count += 1
            f.write("-"*80 + "\n")
            f.write(f"kind: {r['kind']}\n")
            f.write(f"floor: {r['floor'] or 'not tied to floor path'}\n")
            f.write(f"url: {u}\n")
            f.write(f"status: {s}\n")
            f.write(f"http_code: {st.get('code','')}\n")
            f.write(f"final_url: {st.get('final','')}\n")
            f.write(f"title: {st.get('title','')}\n")
            f.write(f"in_iPad_dashboard: {'YES' if u.rstrip('/') in ipad_urls else 'NO'}\n")
            f.write(f"source: {r['source']}:{r['line']}\n")
            f.write(f"evidence: {r['context']}\n\n")
    if count == 0:
        f.write("No broken public URL evidence found in this discovery pass.\n")
    f.write("\nNO PATCHES APPLIED. DISCOVERY ONLY.\n")

print("discovered_rows:", len(rows))
print("csv:", csv_path)
print("floors:", floors_path)
print("broken:", broken_path)
PY

echo
echo "===== SECTION 1 — DISCOVERED FLOORS PREVIEW ====="
sed -n '1,220p' "$FLOORS"

echo
echo "===== SECTION 2 — DISCOVERED WEB/DASHBOARD/SHOP LINKS PREVIEW ====="
head -80 "$CSV"

echo
echo "===== SECTION 3 — BROKEN OR MISSING CONNECTIONS PREVIEW ====="
sed -n '1,220p' "$BROKEN"

echo
echo "NO PATCHES APPLIED. DISCOVERY ONLY."
echo
echo "============================================================"
echo "DONE"
echo "Send these files back:"
echo "$SEND/LATEST_REPORT.txt"
echo "$SEND/discovered_links.csv"
echo "$SEND/discovered_floors.txt"
echo "$SEND/broken_or_missing_connections.txt"
echo "============================================================"

cp -a "$REPORT" "$SEND/LATEST_REPORT.txt"
cp -a "$CSV" "$SEND/discovered_links.csv"
cp -a "$FLOORS" "$SEND/discovered_floors.txt"
cp -a "$BROKEN" "$SEND/broken_or_missing_connections.txt"
cp -a "$REPORT" "$RUN_ROOT/00_LATEST_REPORT.txt"

cat > "$SEND/README_SEND_THIS.txt" <<TXT
Send these back to ChatGPT:

$SEND/LATEST_REPORT.txt
$SEND/discovered_links.csv
$SEND/discovered_floors.txt
$SEND/broken_or_missing_connections.txt

NO PATCHES APPLIED. DISCOVERY ONLY.
TXT

xdg-open "$SEND" >/dev/null 2>&1 &
