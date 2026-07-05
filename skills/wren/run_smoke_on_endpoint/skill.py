"""skill: run_smoke_on_endpoint — GET/POST a localhost endpoint, return status + head of body."""
import json, urllib.request


def run(path: str, port: int = 8765, method: str = "GET", body: dict = None) -> dict:
    if not path.startswith("/"):
        return {"ok": False, "error": "path must start with /"}
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body or {}).encode() if (method == "POST" and body) else None
    req = urllib.request.Request(url, data=data, method=method)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body_txt = r.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": r.status, "url": url,
                    "body_head": body_txt[:500], "body_len": len(body_txt)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "url": url, "error": str(e)[:200]}
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)[:200]}
