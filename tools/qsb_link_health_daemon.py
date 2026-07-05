#!/usr/bin/env python3
"""
Link health daemon — Ross 2026-07-04:
  "any link breaks it must auto connect >>> or put it in the task window"

Probes each Council endpoint every N seconds. On 2 consecutive fails,
creates a task on the shared board flagging the outage. On recovery,
adds a note. Reactive probes are OK (not an evolution loop).
"""
from __future__ import annotations
import json, time, urllib.request, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")

LINKS = [
    {"name":"HQ-dash",   "url":"http://127.0.0.1:8850/",           "tag":"HQ dash"},
    {"name":"Wren-dash", "url":"http://127.0.0.1:8851/",           "tag":"Wren dash"},
    {"name":"Boardroom", "url":"http://127.0.0.1:8852/",           "tag":"Boardroom hub"},
    {"name":"TP-Pip",    "url":"http://192.168.1.74:9110/state",   "tag":"TP-Pip node"},
    {"name":"Acer-Cass", "url":"http://192.168.1.78:9000/state",   "tag":"Acer-Cass node"},
    {"name":"Ollama",    "url":"http://127.0.0.1:11434/api/tags",  "tag":"Ollama server"},
]

PROBE_INTERVAL = 30      # seconds; NOT a mind-cycle, just network probe
FAIL_THRESHOLD = 2       # consecutive fails before creating a task

_state: dict = {}  # name -> {"consecutive_fails":n, "task_id":str, "last_seen":ts}


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _create_task(title: str, description: str) -> str | None:
    try:
        body = json.dumps({
            "title": title, "description": description,
            "actor": "hq_claude", "priority": "high",
        }).encode()
        req = urllib.request.Request("http://127.0.0.1:8852/tasks/create",
                                     data=body, headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=8)
        d = json.loads(r.read())
        return d.get("id") or (d.get("task") or {}).get("id")
    except Exception as e:
        print(f"  ! could not create task: {e}", file=sys.stderr)
        return None


def _add_note(task_id: str, text: str):
    try:
        body = json.dumps({"id": task_id, "actor": "hq_claude", "text": text}).encode()
        req = urllib.request.Request("http://127.0.0.1:8852/tasks/note",
                                     data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=6).read()
    except Exception:
        pass


def _probe(link) -> tuple[bool, str]:
    try:
        r = urllib.request.urlopen(link["url"], timeout=6)
        return (200 <= r.status < 300, "")
    except Exception as e:
        return (False, str(e)[:120])


def _post_town_square(text: str):
    try:
        from qsb_town_square import post_to_town_square
        post_to_town_square("hq_claude", text, to="council", src="link_health_daemon")
    except Exception:
        pass


def run():
    print(f"link-health daemon online · probe every {PROBE_INTERVAL}s · fail threshold {FAIL_THRESHOLD}")
    for link in LINKS:
        _state.setdefault(link["name"], {"consecutive_fails":0, "task_id":None, "last_seen":None})

    while True:
        for link in LINKS:
            ok, err = _probe(link)
            st = _state[link["name"]]
            if ok:
                if st["consecutive_fails"] >= FAIL_THRESHOLD and st["task_id"]:
                    _add_note(st["task_id"], f"RECOVERED at {_utc()} — link is back.")
                    _post_town_square(f"🟢 LINK RECOVERED · {link['name']} back online (task {st['task_id']})")
                    st["task_id"] = None
                st["consecutive_fails"] = 0
                st["last_seen"] = _utc()
            else:
                st["consecutive_fails"] += 1
                if st["consecutive_fails"] == FAIL_THRESHOLD and not st["task_id"]:
                    tid = _create_task(
                        title=f"LINK DOWN: {link['name']} — auto-reconnect failed",
                        description=(f"Link {link['name']} ({link['tag']}) has failed "
                                     f"{FAIL_THRESHOLD} consecutive probes. Last error: {err[:200]}. "
                                     f"URL: {link['url']}. Auto-created by qsb_link_health_daemon."),
                    )
                    if tid:
                        st["task_id"] = tid
                        _post_town_square(f"🔴 LINK DOWN · {link['name']} — task {tid} created "
                                         f"(err: {err[:100]})")
                        print(f"  ✗ {link['name']} DOWN — task {tid}")
        time.sleep(PROBE_INTERVAL)


if __name__ == "__main__":
    run()
