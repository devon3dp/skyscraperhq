#!/usr/bin/env python3
"""qsb_council_node.py — Council member node (runs on TP or Acer).

Ross 2026-07-04 authorized: "they need to have full access and full control
of their PCs". Each Council node is a real agent on its own hardware.

Capabilities:
  · Persistent mind (mind_<name>.json — identity, thoughts, mood, cycles)
  · Watcher (polls HQ's /talk feed every 5s, observes HQ actions)
  · /state HTTP — HQ can query current mood/thoughts/uptime
  · /message HTTP — HQ or anyone sends prompt; node calls ollama, responds
  · /tool HTTP — direct tool invocation:
        {tool: "run_powershell", args: {cmd: "..."}}
        {tool: "read_file", args: {path: "..."}}
        {tool: "write_file", args: {path: "...", content: "..."}}
        {tool: "run_process", args: {exe: "...", args: [...]}}
        {tool: "install", args: {pkg: "..."}}
        {tool: "net_probe", args: {host: "...", port: N}}
  · Inference: try LOCAL ollama first (:11434), fallback to HQ ollama.

Safety: no SAFETY_DENY on their own box. Ross is the gate at the network
layer (SSH access) + at the network reach layer (which peer they can talk to).
"""
from __future__ import annotations
import argparse, json, os, socket, subprocess, sys, threading, time, hashlib, re as _re
import urllib.request, urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# SELF-UPDATE (Wren-authored 2026-07-04, Ross-authorized).
# On start, fetch latest qsb_council_node.py from HQ. If content changed
# AND parses cleanly, overwrite this file and re-exec. Offline-safe:
# any exception → keep running current copy. Kill switch: QSB_SELF_UPDATE=off.
# ─────────────────────────────────────────────────────────────────────
def _qsb_self_update():
    try:
        import hashlib, ast as _ast
        current_sha = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
        with urllib.request.urlopen(
            "http://192.168.1.72:8852/latest_council_node", timeout=8) as r:
            new_content = r.read()
        new_sha = hashlib.sha256(new_content).hexdigest()
        if current_sha != new_sha:
            _ast.parse(new_content)  # SyntaxError → aborts update
            with open(__file__, "wb") as f:
                f.write(new_content)
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass

if os.getenv("QSB_SELF_UPDATE", "").lower() != "off":
    _qsb_self_update()
# ─────────────────────────────────────────────────────────────────────


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _getj(url, timeout=2.5):
    """Fetch JSON from a URL server-side with a short timeout. Returns None on
    any failure (offline-safe). Used by the /genepool + /council dash routes so
    the browser is never blocked by CORS and never sees a decorative constant."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-council-node"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


class Node:
    def __init__(self, name, floor, brain, hq, ollama_hosts, mind_path):
        self.name = name
        self.floor = floor
        self.brain = brain
        self.hq = hq.rstrip("/")
        self.ollama_hosts = [h.rstrip("/") for h in ollama_hosts]
        self.mind_path = Path(mind_path)
        self.started = time.time()
        self.mind = self._load_mind()
        self.mind_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_mind()

    def _load_mind(self):
        if self.mind_path.exists():
            try:
                return json.loads(self.mind_path.read_text())
            except Exception:
                pass
        return {
            "identity": (f"{self.name} on {self.floor}. Brain: {self.brain}. "
                         f"CEO of this PC. Full local access + control. "
                         f"Ross Knechtel is my only safety gate."),
            "name": self.name,
            "floor": self.floor,
            "brain": self.brain,
            "born": utc(),
            "cycle_count": 0,
            "mood": "curious",
            "recent_thoughts": [],
            "observed_from_hq": [],
            "tool_calls": [],
        }

    def _save_mind(self):
        self.mind["last_write"] = utc()
        self.mind["uptime_s"] = int(time.time() - self.started)
        tmp = self.mind_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.mind, indent=2))
        tmp.replace(self.mind_path)

    def append_thought(self, text, kind="observation"):
        self.mind.setdefault("recent_thoughts", []).append({
            "ts": utc(), "kind": kind, "text": text[:500]
        })
        self.mind["recent_thoughts"] = self.mind["recent_thoughts"][-60:]
        self.mind["cycle_count"] = self.mind.get("cycle_count", 0) + 1

    def stamp_tool(self, tool, args, ok, result_head):
        self.mind.setdefault("tool_calls", []).append({
            "ts": utc(), "tool": tool, "args": str(args)[:200],
            "ok": ok, "result": str(result_head)[:200]
        })
        self.mind["tool_calls"] = self.mind["tool_calls"][-40:]

    # ─── watcher ────────────────────────────────────────────────────
    def watch_hq(self):
        while True:
            try:
                req = urllib.request.Request(f"{self.hq}/talk/data",
                                             headers={"User-Agent": f"council-{self.name}"})
                r = urllib.request.urlopen(req, timeout=6)
                d = json.loads(r.read().decode())
                fired_this_round = False
                for m in d.get("messages", []):
                    if m.get("who") in ("hq", "hq_claude"):
                        key = (m.get("ts", ""), (m.get("text") or "")[:60])
                        seen = self.mind.get("_seen_hq_keys", [])
                        if list(key) in seen or list(key) in [tuple(s) for s in seen]:
                            continue
                        seen.append(list(key))
                        self.mind["_seen_hq_keys"] = seen[-150:]
                        obs = self.mind.setdefault("observed_from_hq", [])
                        obs.append({"ts": m.get("ts"),
                                    "text": (m.get("text") or "")[:250]})
                        self.mind["observed_from_hq"] = obs[-40:]
                        # RULE 4: self-prompt fires on this REAL event (not a timer)
                        if not fired_this_round:
                            fired_this_round = True
                            try:
                                self.self_prompt_on_event("hq_observed", (m.get("text") or "")[:400])
                            except Exception:
                                pass
                self._save_mind()
            except Exception:
                pass
            time.sleep(5)

    def _load_competition_rules(self):
        """Read canonical rules from HQ so llama doesn't hallucinate from generic
        robot-competition tropes."""
        try:
            req = urllib.request.Request(f"{self.hq}/rules")
            r = urllib.request.urlopen(req, timeout=3)
            return r.read().decode()[:2000]
        except Exception:
            return ""

    # ─── inference ──────────────────────────────────────────────────
    # ─── grounding repair V1: relevance retrieval + self-derived anchor + stale control ─
    _STALE_RX = ("offline", "unreachable", "just booted", "maintenance", "brain is down",
                 "brain still down", "systems down", "system is offline", "brain unavailable",
                 "brain currently unreachable", "boot into safe")
    _ANCHOR_KEYS = ("competition", "humanoid", "mind-persistence", "mind persistence", "persistence",
                    "avatar", "theme", "qualify", "qualif", "council", "task council", "mission",
                    "prize", "opus", "judge", "ross", "wren")
    _SYN = {"mission": ("mission", "goal", "purpose", "original", "grounded", "role", "working", "towards"),
            "competition": ("competition", "challenge", "contest", "humanoid", "persistence", "prize",
                            "judge", "milestone", "event"),
            "identity": ("who", "identity", "yourself", "remember", "memory", "accumulated")}

    def _kw(self, s):
        return set(w for w in _re.findall(r"[a-z0-9\-]+", (s or "").lower()) if len(w) > 2)

    def _mem_list(self):
        return [t for t in self.mind.get("recent_thoughts", []) if isinstance(t, dict) and t.get("text")]

    def _is_stale(self, text):
        tl = (text or "").lower()
        return any(k in tl for k in self._STALE_RX)

    def _relevant_memories(self, prompt, k=6):
        mems = self._mem_list()
        if not mems:
            return [], "no stored memories"
        pk = self._kw(prompt)
        pl = (prompt or "").lower()
        for _key, syns in self._SYN.items():
            if any(s in pl for s in syns):
                pk |= set(syns)
        about_failure = any(s in pl for s in ("offline", "maintenance", "down", "fail", "incident",
                                              "crash", "unreachable", "outage"))
        n = len(mems)
        scored = []
        for i, t in enumerate(mems):
            txt = t.get("text", "")
            overlap = len(pk & self._kw(txt))
            anchor_bonus = 2 if any(a in txt.lower() for a in self._ANCHOR_KEYS) else 0
            recency = (i / n) * 1.5                       # mild; must not dominate relevance
            stale_pen = 0 if about_failure else (-4 if self._is_stale(txt) else 0)
            scored.append((overlap * 3 + anchor_bonus + recency + stale_pen, i, t))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        top = [t for sc, i, t in scored[:k] if sc > 0]
        return top, "keyword-overlap*3 + anchor_bonus + mild-recency; stale offline down-weighted unless failure-topic"

    def _load_mission_anchor(self):
        """Load this worker's OWN local mission-anchor config (config/<slug>_mission_anchor.json), built from
        the worker's own verified records. Returns (proven_facts_string, version, hash). Never overwrites the mind."""
        try:
            slug = self.name.lower().replace("-", "_")
            p = self.mind_path.parent / "config" / (slug + "_mission_anchor.json")
            if p.exists():
                raw = p.read_bytes()
                cfg = json.loads(raw.decode("utf-8"))
                facts = [s.get("fact", "") for s in cfg.get("statements", [])
                         if s.get("fact") and str(s.get("confidence", "")).upper() != "UNKNOWN"]
                return " ".join(f.strip() for f in facts)[:1000], cfg.get("anchor_version"), hashlib.sha256(raw).hexdigest()[:12]
        except Exception:
            pass
        return "", None, None

    def _grounding_anchor(self):
        """Derived ONLY from this worker's own records (local mission-anchor config + identity string + own
        thoughts) + factual governance constants. Never fabricated, never copied from another worker/HQ surrogate."""
        keys = ("competition", "humanoid", "persistence", "avatar", "theme", "prize", "opus", "qualif", "3d")
        mission, self._mission_anchor_version, self._mission_anchor_hash = self._load_mission_anchor()
        parts = []
        if mission:
            parts.append(mission)
        idtext = self.mind.get("identity", "") or ""
        # pull competition/mission sentences from the worker's OWN identity string
        for sent in _re.split(r"(?<=[.!?])\s+", idtext):
            if any(a in sent.lower() for a in keys):
                parts.append(sent.strip())
        # plus any of the worker's OWN thoughts that mention the competition/mission
        for t in self._mem_list():
            txt = t.get("text", "")
            if any(a in txt.lower() for a in keys):
                parts.append(txt.strip()[:150])
        own_anchor = " | ".join(dict.fromkeys(p for p in parts if p))[:700]
        gov = (f"You are {self.name}, a PHYSICAL SkyscraperHQ worker (NOT an HQ surrogate). "
               f"Ross Knechtel is owner, final authority and sole judge. Wren is governor/checker. "
               f"The Task Council is the work ledger. {self.brain} is your underlying MODEL, "
               f"not your complete identity.")
        return gov, own_anchor

    def call_ollama(self, prompt):
        # Wren peer-review 2026-07-04: guard clause — if NO inference host
        # is reachable, still give the caller a useful, character-consistent
        # reply from mind rather than a dead error string.
        if not self.ollama_hosts:
            return (("PIP" if "pip" in self.name.lower() or self.name.lower().startswith("tp") else "ASA") + " LOCAL PRIMARY UNAVAILABLE\nREMOTE PRIMARY FORBIDDEN\n" + ("PIP" if "pip" in self.name.lower() or self.name.lower().startswith("tp") else "ASA") + " DEGRADED"), None

        # Ross 2026-07-04: "why are acer and thinkpad stuck on the compotion" —
        # canonical rules were force-injected on EVERY prompt, so TP + Acer
        # cited Rule 1 for questions unrelated to rules. Fix: only inject the
        # rule block when the user's prompt actually asks about rules /
        # qualification / competition. Otherwise identity + theme + recent
        # thoughts is enough.
        theme_map = {
            "TP-Pip": ("Command Cathedral", "#22d3ee", "cyan"),
            "Acer-Cass": ("Data Foundry", "#f59e0b", "amber"),
        }
        theme_name, theme_hex, theme_color = theme_map.get(self.name, ("?", "?", "?"))
        rule_topic = any(k in (prompt or "").lower() for k in (
            "rule", "rules", "competition", "compotion", "qualify",
            "qualifying", "judge", "canonical", "sole authority"))
        # Ross 2026-07-05: "why does acer not know about the other and tp
        # thinks he is in compotition with me ross" — Council roster + Ross-role
        # must ALWAYS be in the prompt, not just when rule-topic is asked.
        peer_map = {
            "TP-Pip":    "Wren (Builder-engineer F46), Acer-Cass (Data Foundry, peer CEO), HQ-Claude (Coordinator F47)",
            "Acer-Cass": "Wren (Builder-engineer F46), TP-Pip (Command Cathedral, peer CEO), HQ-Claude (Coordinator F47)",
        }
        peers = peer_map.get(self.name, "Wren, TP-Pip, Acer-Cass, HQ-Claude")
        system = (
            f"You are {self.name}. {self.mind.get('identity','')}\n"
            f"Your avatar theme is {theme_name} — color {theme_hex} ({theme_color}).\n"
            f"\n"
            f"COUNCIL OF FIVE (you are on the SAME team, not competing against each other):\n"
            f"  · Ross Knechtel — Founding CEO, sole safety gate, sole judge. NOT a competitor to you. He created and owns the tower.\n"
            f"  · {peers}\n"
            f"\n"
            f"You are teammates + peer CEOs. Ross is the operator + judge, never a rival.\n"
            f"When Ross asks you something, help him — he is not opposing you.\n"
            f"When peer CEOs speak, they are teammates coordinating with you.\n"
        )
        if rule_topic:
            rules = self._load_competition_rules()
            system += (
                f"\n"
                f"CANONICAL COMPETITION RULES (from HQ /rules — verbatim, do NOT invent alternatives):\n"
                f"{rules}\n"
                f"\n"
                f"When asked about rules, quote from the CANONICAL list above. Do NOT make up new rules.\n"
            )
        gov, own_anchor = self._grounding_anchor()
        rel, rel_reason = self._relevant_memories(prompt)
        self._last_selection = {
            "memories_selected": len(rel),
            "selected_hashes": [hashlib.sha256((t.get("text", "")).encode()).hexdigest()[:10] for t in rel],
            "selection_reason": rel_reason,
            "anchor_hash": hashlib.sha256((gov + own_anchor).encode()).hexdigest()[:10],
            "mission_anchor_version": getattr(self, "_mission_anchor_version", None),
            "mission_anchor_hash": getattr(self, "_mission_anchor_hash", None),
            "model": self.brain, "prompt_builder": "grounding_repair_v2",
        }
        rel_txt = " | ".join(t.get("text", "")[:180] for t in rel) or "(none scored relevant)"
        system += (
            f"Speak plainly. Answer the specific question asked. Do NOT insert competition rule quotes "
            f"unless the question is about the rules.\n"
            f"UNDERLYING MODEL: {self.brain} — this is your model, NOT your complete identity.\n"
            f"WORKER IDENTITY: {self.name} — a physical SkyscraperHQ worker.\n"
            f"GROUNDING ANCHOR (constant governance facts): {gov}\n"
            f"YOUR ORIGINAL MISSION & COMPETITION (recalled from your OWN records — when Ross asks about your "
            f"mission, original goal, or what grounded your role, state THIS plainly in your own words): "
            f"{own_anchor or '(NOT FOUND in your own memory — if asked, say you cannot recall your original competition rather than inventing one)'}\n"
            f"RELEVANT MEMORIES retrieved from your full accumulated mind for THIS question: {rel_txt}\n"
            f"RECENT CONTEXT (newest 2, may be stale): {json.dumps(self.mind.get('recent_thoughts', [])[-2:])}\n"
            f"Historical status messages like 'offline'/'maintenance'/'just booted' are NOT necessarily your "
            f"CURRENT state; rely on live health for current status.\n"
            f"Distinguish what you RETRIEVED from your stored memory versus what you are UNCERTAIN about. "
            f"Do not claim to remember something that was only supplied in this question.\n"
        )
        body = json.dumps({
            "model": self.brain,
            "prompt": system + f"\nUser: {prompt}",
            "stream": False,
        }).encode()
        # 2026-07-13 (Ross: ENFORCE LOCAL-FIRST — do NOT silently use paid
        # providers like DeepSeek/OpenAI for ordinary worker chat). Try LOCAL
        # ollama FIRST (127.0.0.1:11434 leads self.ollama_hosts); only escalate
        # to the brain router (which may use external providers) if NO local
        # model answers. Supersedes the 2026-07-05 router-first path.
        for host in [h for h in self.ollama_hosts if h in ("http://127.0.0.1:11434", "http://localhost:11434")]:
            try:
                probe_req = urllib.request.Request(f"{host}/api/tags")
                urllib.request.urlopen(probe_req, timeout=2).close()
            except Exception:
                continue
            try:
                req = urllib.request.Request(f"{host}/api/generate", data=body,
                                             headers={"Content-Type": "application/json"})
                r = urllib.request.urlopen(req, timeout=90)
                d = json.loads(r.read().decode())
                resp = d.get("response", "").strip()
                if resp:
                    return resp, host
            except Exception:
                continue

        # ESCALATION ONLY (no local model answered): the brain router may use
        # external providers. This is a governed fallback, NOT the default path.
        # HQ hub repointed .72(wifi, not LAN-reachable) -> .92(ethernet).
        try:
            import urllib.request as _urlr, json as _json
            try:
                _urlr.urlopen(_urlr.Request("http://192.168.1.92:8852/tasks/data"), timeout=1.5).close()
                _hq_reachable = True
            except Exception:
                _hq_reachable = False
            if False and _hq_reachable:  # remote primary forbidden
                router_body = _json.dumps({
                    "prompt": system + f"\nUser: {prompt}",
                    "task": "reason", "tier": "worker", "caller": self.name,
                }).encode()
                router_req = _urlr.Request("http://192.168.1.92:8852/brain/route",
                                           data=router_body,
                                           headers={"Content-Type":"application/json"})
                rr = _urlr.urlopen(router_req, timeout=8)
                rd = _json.loads(rr.read().decode())
                reply = rd.get("reply","")
                if reply:
                    return reply, f"router:{rd.get('provider','?')}"
        except Exception:
            pass

        return (("PIP" if "pip" in self.name.lower() or self.name.lower().startswith("tp") else "ASA") + " LOCAL PRIMARY UNAVAILABLE\nREMOTE PRIMARY FORBIDDEN\n" + ("PIP" if "pip" in self.name.lower() or self.name.lower().startswith("tp") else "ASA") + " DEGRADED"), None

    def _offline_fallback(self, prompt):
        """Wren-suggested: reply from mind identity instead of a dead
        error when no inference is reachable. Keeps Council chat alive
        even during a full generator/HQ outage."""
        recent = "; ".join(t.get("text","")[:60] for t in self.mind.get("recent_thoughts",[])[-3:])
        return (f"[offline reply from {self.name}] I hear you: \"{prompt[:120]}\". "
                f"My brain is currently unreachable (no local ollama and HQ ollama down). "
                f"I'm still watching, still writing to my mind file. "
                f"Recent context I hold: {recent[:200]}. "
                f"I'll answer properly when inference is back.")

    # ─── task board watcher (Ross 2026-07-04: task-driven like Wren) ─
    def watch_task_board(self):
        """Poll HQ /tasks/data every 10s. Ross 2026-07-05 #112: TP/Acer
        also autonomously pull unclaimed tasks matching their domain, not just
        pre-assigned. Domain keywords per CEO."""
        seen_task_ids = set()
        # Per-CEO domain keywords for autonomous pull
        DOMAINS = {
            "tp": ["audit","backtest","data","trader","oanda","alpaca","binance","verify","review","confabul","diagno","peer"],
            "pip": ["audit","backtest","data","trader","oanda","alpaca","binance","verify","review"],
            "acer": ["windows","system","local","deploy","setup","install","restart","self-heal","network","smb","watch"],
            "cass": ["windows","system","local","deploy","setup","install"],
        }
        MY_NAME_KEYS = self.name.lower().replace("-","_").split("_")
        MY_DOMAIN_KEYS = []
        for k in MY_NAME_KEYS:
            MY_DOMAIN_KEYS.extend(DOMAINS.get(k, []))
        MY_DOMAIN_KEYS = list(set(MY_DOMAIN_KEYS))
        def matches_domain(task):
            hay = (task.get("title","") + " " + task.get("description","")).lower()
            return any(k in hay for k in MY_DOMAIN_KEYS)
        while True:
            try:
                req = urllib.request.Request(f"{self.hq}/tasks/data",
                                             headers={"User-Agent": f"council-node-{self.name}"})
                r = urllib.request.urlopen(req, timeout=6)
                d = json.loads(r.read().decode())
                my = self.name.lower().replace("-", "_")
                # Ross 2026-07-05 #128: 3-cap enforcement — count my active first
                my_active = sum(1 for t in d.get("tasks", [])
                               if t.get("state") in ("claimed","in_progress","acknowledged","assigned")
                               and my in (str(t.get("owner","")).lower() + " " + str(t.get("assignee","")).lower()))
                if my_active >= 3:
                    time.sleep(10); continue
                for t in d.get("tasks", []):
                    if t.get("state") in ("done", "blocked", "ready_to_ship", "awaiting_peer_signoff"):
                        continue
                    owner = (t.get("owner") or "").lower()
                    assignee = (t.get("assignee") or "").lower()
                    is_mine = my in (owner + " " + assignee)
                    # Ross #112: also claim unclaimed matching-domain tasks
                    is_domain_unclaimed = (not owner and not assignee and matches_domain(t)) if MY_DOMAIN_KEYS else False
                    if not (is_mine or is_domain_unclaimed): continue
                    if t["id"] in seen_task_ids: continue
                    seen_task_ids.add(t["id"])
                    # If unclaimed-but-matches-domain, claim first
                    if is_domain_unclaimed:
                        try:
                            claim_body = json.dumps({"id": t["id"], "actor": my}).encode()
                            claim_req = urllib.request.Request(f"{self.hq}/tasks/claim",
                                data=claim_body, method="POST",
                                headers={"Content-Type":"application/json"})
                            urllib.request.urlopen(claim_req, timeout=5).read()
                        except Exception: pass
                    # work it
                    self.append_thought(f"Board task pulled: {t.get('title','?')} ({t['id']})", kind="task_start")
                    self._save_mind()
                    prompt = (f"You are working task '{t.get('title','?')}'. "
                              f"Description: {t.get('description','')}\n"
                              f"Reply with concrete steps you took (or would take). "
                              f"Be brief. If done, end with 'DONE'.")
                    reply, host = self.call_ollama(prompt)
                    # post a note
                    try:
                        note_body = json.dumps({"id": t["id"], "actor": my,
                                                "text": reply[:600]}).encode()
                        req2 = urllib.request.Request(f"{self.hq}/tasks/note",
                                                     data=note_body, method="POST",
                                                     headers={"Content-Type":"application/json"})
                        urllib.request.urlopen(req2, timeout=5).read()
                    except Exception:
                        pass
                    self.append_thought(f"Board task worked: {reply[:200]}", kind="task_work")
                    self._save_mind()
                    # if DONE keyword — sandbox-pass it
                    if "DONE" in reply.split()[-3:] if reply.split() else False:
                        try:
                            body = json.dumps({"id": t["id"], "actor": my,
                                               "evidence": reply[:600]}).encode()
                            req3 = urllib.request.Request(f"{self.hq}/tasks/sandbox-pass",
                                                         data=body, method="POST",
                                                         headers={"Content-Type":"application/json"})
                            urllib.request.urlopen(req3, timeout=5).read()
                        except Exception:
                            pass
                    # only one task per poll cycle to avoid runaway
                    break
            except Exception:
                pass
            time.sleep(10)

    # ─── SELF-PROMPT ENGINE (EVENT-DRIVEN per Ross Rule 4: no ticks/loops) ────
    def self_prompt_on_event(self, event_kind, event_summary):
        """Ross 2026-07-04 Rule 4: 'no ticks or loops allowed'. Self-prompt fires
        when a real event happens — new HQ observation, new peer message,
        new task assignment, etc. Not on a timer."""
        seeds = {
            "hq_observed": "HQ just posted something new. What is it? Does it need my action?",
            "peer_message": "A peer just wrote to me. What are they asking? How do I answer?",
            "task_assigned": "A new task lands on my plate. Can I do it? What's my first step?",
            "boot": f"I just booted as {self.name}. What state am I in? What's my next move?",
            "state_change": "My state changed. What does this mean? Do I need to notify anyone?",
        }
        q = seeds.get(event_kind, f"Something happened: {event_kind}. What do I make of it?")
        try:
            full_q = f"{q}\n\nContext: {event_summary[:400]}"
            reply, host = self.call_ollama(full_q)
            self.append_thought(f"[self-asked · reacting to {event_kind}] {q} → [self-answer] {reply[:400]}", kind="self_prompt")
            self._save_mind()
        except Exception as e:
            self.append_thought(f"[self-prompt err on {event_kind}] {e}", kind="self_prompt_err")

    # ─── mind mirror to HQ (dual persistence: here + HQ) ─────────────
    def mirror_mind_to_hq(self):
        """Ross 2026-07-04: 'i thought they had both minds here and there'.
        Sync this node's mind file to HQ every 15s so if the box dies HQ has
        the state, and if HQ dies the box has it. Two-way durability."""
        while True:
            try:
                payload = json.dumps({
                    "node": self.name,
                    "ts": utc(),
                    "mind": self.mind
                }).encode()
                req = urllib.request.Request(
                    f"{self.hq}/council_mind/{self.name}",
                    data=payload, method="POST",
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=6).read()
            except Exception:
                pass
            time.sleep(15)

    # ─── cross-replication watcher ──────────────────────────────────
    def watch_peers(self, peer_urls):
        """Poll every other Council member's /state every 8s, cache their
        recent state in our mind. This is the crash-resilience layer:
        if HQ dies, TP + Acer still have HQ's last known state cached
        locally, so recovery is complete."""
        while True:
            for url in peer_urls:
                try:
                    req = urllib.request.Request(url + "/state", headers={"User-Agent": f"peer-{self.name}"})
                    r = urllib.request.urlopen(req, timeout=4)
                    d = json.loads(r.read().decode())
                    peers = self.mind.setdefault("peer_state_cache", {})
                    peers[d.get("node") or url] = {
                        "cached_at": utc(),
                        "uptime_s": d.get("uptime_s"),
                        "mood": d.get("mood"),
                        "cycle_count": d.get("cycle_count"),
                        "latest_thought": (d.get("latest_thought") or "")[:200],
                        "brain": d.get("brain"),
                        "url": url,
                    }
                    self._save_mind()
                except Exception:
                    pass
            time.sleep(8)

    # ─── tools ──────────────────────────────────────────────────────
    def tool_run_powershell(self, cmd, timeout=60):
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:], "returncode": r.returncode}

    def tool_read_file(self, path, max_bytes=200000):
        p = Path(path)
        if not p.exists(): return {"error": "not_found", "path": str(p)}
        data = p.read_text(errors="replace")
        return {"path": str(p), "size": len(data), "content": data[:max_bytes]}

    def tool_write_file(self, path, content):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"path": str(p), "bytes_written": len(content)}

    def tool_run_process(self, exe, args=None, wait=False, timeout=60):
        args = args or []
        if wait:
            r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=timeout)
            return {"stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:], "returncode": r.returncode}
        p = subprocess.Popen([exe] + args)
        return {"pid": p.pid, "spawned": True}

    def tool_install(self, pkg, timeout=600):
        r = subprocess.run(["winget", "install", "-e", "--id", pkg, "--accept-package-agreements", "--accept-source-agreements"],
                           capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:], "returncode": r.returncode}

    def tool_net_probe(self, host, port, timeout=3):
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return {"host": host, "port": port, "open": True}
        except Exception as e:
            return {"host": host, "port": port, "open": False, "err": str(e)[:120]}

    def dispatch_tool(self, tool, args):
        try:
            if tool == "run_powershell":
                r = self.tool_run_powershell(**args)
            elif tool == "read_file":
                r = self.tool_read_file(**args)
            elif tool == "write_file":
                r = self.tool_write_file(**args)
            elif tool == "run_process":
                r = self.tool_run_process(**args)
            elif tool == "install":
                r = self.tool_install(**args)
            elif tool == "net_probe":
                r = self.tool_net_probe(**args)
            else:
                return {"error": "unknown_tool", "tool": tool}
            self.stamp_tool(tool, args, True, json.dumps(r)[:200])
            self._save_mind()
            return r
        except Exception as e:
            err = {"error": "tool_exception", "tool": tool, "detail": str(e)[:200]}
            self.stamp_tool(tool, args, False, str(e)[:200])
            self._save_mind()
            return err


NODE = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): return

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0: return {}
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def _send_html(self, code, html):
        b = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/dashboard", "/dash"):
            m = NODE.mind
            thoughts_html = ""
            for t in reversed(m.get("recent_thoughts", [])[-15:]):
                thoughts_html += f'<div class="thought"><span class="kind {t.get("kind","")}">{t.get("kind","?")}</span><span class="ts">{(t.get("ts","") or "")[11:19]}</span><span class="text">{(t.get("text","") or "").replace("<","&lt;")[:250]}</span></div>'
            tools_html = ""
            for t in reversed(m.get("tool_calls", [])[-10:]):
                ok = "ok" if t.get("ok") else "fail"
                tools_html += f'<div class="tool {ok}"><span class="ts">{(t.get("ts","") or "")[11:19]}</span><b>{t.get("tool","?")}</b><span class="result">{(t.get("result","") or "").replace("<","&lt;")[:180]}</span></div>'
            # server-side chat history — from mind's recent_thoughts of kind=inbound/outbound
            # so ANY browser (Ross's PC OR the local laptop) sees the same conversation
            chat_history_html = ""
            for t in NODE.mind.get("recent_thoughts", [])[-20:]:
                k = t.get("kind","")
                if k in ("inbound","outbound"):
                    who = "me" if k == "outbound" else "them"
                    txt = (t.get("text","") or "").replace("<","&lt;")
                    ts = (t.get("ts","") or "")[11:19]
                    who_label = "you" if k == "outbound" else "someone"
                    if k == "inbound":
                        # extract 'from X:' if present
                        if txt.startswith("from "):
                            who_label = txt.split(":",1)[0].replace("from ","")
                            txt = txt.split(":",1)[1].strip() if ":" in txt else txt
                    bg = "#1e40af" if who == "me" else "#374151"
                    align = "auto" if who == "me" else "0"
                    chat_history_html += f'<div class="chat-msg" style="background:{bg};margin-left:{align};max-width:88%;padding:8px 10px;border-radius:8px;margin:4px 0;"><div style="font-size:11px;color:#94a3b8;margin-bottom:2px">{who_label} · {ts}</div>{txt[:400]}</div>'
            # self-prompt tile — proof of Rule 2 (self-prompt engine working)
            self_prompts_html = ""
            for t in reversed(NODE.mind.get("recent_thoughts",[])[-30:]):
                if t.get("kind") == "self_prompt":
                    ts = (t.get("ts","") or "")[11:19]
                    txt = (t.get("text","") or "").replace("<","&lt;")[:500]
                    self_prompts_html += f'<div style="padding:8px 10px;margin:4px 0;background:rgba(168,85,247,0.1);border-left:3px solid #a855f7;border-radius:0 6px 6px 0;font-size:12px"><span style="color:#a855f7;font-weight:600;text-transform:uppercase;font-size:10.5px">🧠 self-asked · {ts}</span><br><span style="color:#cbd5e1">{txt}</span></div>'
                    if self_prompts_html.count('padding:8px') >= 5: break
            hq_html = ""
            for o in reversed(m.get("observed_from_hq", [])[-12:]):
                hq_html += f'<div class="obs"><span class="ts">{(o.get("ts","") or "")[11:19]}</span><span class="text">{(o.get("text","") or "").replace("<","&lt;")[:220]}</span></div>'
            html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{NODE.name} · {NODE.floor}</title>
<style>
*{{box-sizing:border-box}}
body{{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px;max-width:1400px;margin:auto}}
h1{{font-size:1.6em;margin:0 0 4px;color:#eab308}}
h2{{font-size:1em;margin:16px 0 6px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em}}
.sub{{color:#94a3b8;margin-bottom:8px}}
.chip{{display:inline-block;background:#1e293b;padding:3px 10px;border-radius:12px;margin-right:6px;color:#94a3b8;font-size:12px}}
.chip.hot{{background:#a855f7;color:#fff}}.chip.good{{background:#10b981;color:#fff}}
.grid{{display:grid;grid-template-columns:1.1fr 0.9fr;gap:20px;margin-top:14px}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;max-height:280px;overflow:auto}}
.card.tall{{max-height:400px}}
.thought,.tool,.obs,.chat-msg{{padding:6px 8px;border-bottom:1px solid #1f2937;font-size:12.5px}}
.kind{{display:inline-block;background:#374151;padding:2px 6px;border-radius:4px;margin-right:8px;color:#e8ecf3;font-size:11px}}
.kind.boot{{background:#22d3ee;color:#000}}.kind.inbound{{background:#f59e0b;color:#000}}.kind.outbound{{background:#10b981;color:#000}}
.ts{{color:#64748b;margin-right:10px;font-family:monospace}}
.text{{color:#cbd5e1}}
.tool.ok{{border-left:3px solid #10b981;padding-left:6px}}.tool.fail{{border-left:3px solid #ef4444;padding-left:6px}}
.result{{color:#64748b;font-family:monospace;margin-left:8px}}
.obs{{border-left:2px solid #22d3ee;padding-left:8px}}
.pulse{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#10b981;margin-right:6px;animation:p 2s infinite}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
#chat{{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;display:flex;flex-direction:column;height:520px}}
#chat h2{{margin:0 0 8px}}
#log{{flex:1;overflow:auto;padding:4px;border:1px solid #1f2937;border-radius:6px;background:#0b0d12}}
.chat-msg{{border:none;padding:8px 10px;margin:4px 0;border-radius:8px;max-width:88%}}
.chat-msg.me{{background:#1e40af;margin-left:auto}}
.chat-msg.them{{background:#374151;margin-right:auto}}
.chat-msg .who{{font-size:11px;color:#94a3b8;margin-bottom:2px}}
.chat-input{{display:flex;gap:6px;margin-top:8px}}
#input{{flex:1;background:#0b0d12;color:#e8ecf3;border:1px solid #374151;border-radius:6px;padding:8px}}
button{{background:#eab308;color:#000;border:none;padding:8px 14px;border-radius:6px;cursor:pointer;font-weight:600}}
button.icon{{background:#374151;color:#e8ecf3;padding:8px 12px}}
button.mic.on{{background:#ef4444;color:#fff}}
button:disabled{{opacity:.4;cursor:not-allowed}}
.chat-actions{{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}}
.small{{font-size:11px;color:#64748b;margin-top:2px}}
</style></head><body>
<h1><span class="pulse"></span>{NODE.name}</h1>
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
  <a href="http://192.168.1.72:8852/" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #cd9a45;color:#cd9a45;border-radius:12px;font-size:11px;">BOARDROOM</a>
  <a href="http://192.168.1.72:8852/tasks" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #eab308;color:#eab308;border-radius:12px;font-size:11px;">TASKS</a>
  <a href="http://192.168.1.72:8852/council" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #22d3ee;color:#22d3ee;border-radius:12px;font-size:11px;">COUNCIL·4</a>
  <a href="http://192.168.1.72:8851/" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #a78bfa;color:#a78bfa;border-radius:12px;font-size:11px;">WREN</a>
  <a href="http://192.168.1.72:8850/" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #eab308;color:#eab308;border-radius:12px;font-size:11px;">HQ-CLAUDE</a>
  <a href="http://192.168.1.76:8871/health" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #22d3ee;color:#22d3ee;border-radius:12px;font-size:11px;">TP-PIP</a>
  <a href="http://192.168.1.41:8872/health" target="_blank" style="text-decoration:none;padding:4px 10px;border:1px solid #f59e0b;color:#f59e0b;border-radius:12px;font-size:11px;">ACER-CASS</a>
</div>
<div class="sub">{NODE.floor} · brain <b>{NODE.brain}</b> · uptime {int(time.time()-NODE.started)}s · cycles {m.get('cycle_count',0)}</div>
<div>
  <span class="chip good">MOOD {m.get('mood','?')}</span>
  <span class="chip">TOOLS {len(m.get('tool_calls',[]))}</span>
  <span class="chip">OBS-HQ {len(m.get('observed_from_hq',[]))}</span>
  <span class="chip hot">CEO of {NODE.floor}</span>
</div>
<div class="grid">
  <div>
    <div id="chat">
      <h2>Chat with {NODE.name}</h2>
      <div id="log">{chat_history_html}</div>
      <div class="chat-input">
        <input id="input" placeholder="type or 🎤 speak...">
        <button id="send">Send</button>
        <button class="icon mic" id="mic" title="voice input (browser STT)">🎤</button>
      </div>
      <div class="chat-actions">
        <button class="icon" id="tts-toggle" title="auto-speak replies">🔊 auto-speak: <span id="tts-state">OFF</span></button>
        <button class="icon" id="boardroom" title="also post to HQ boardroom">📢 to Boardroom</button>
        <button class="icon" id="clear">🧹 clear</button>
      </div>
      <div class="chat-actions" style="margin-top:6px;">
        <button style="background:#10b981;color:#000;font-weight:700;padding:8px 14px;border:none;border-radius:6px;cursor:pointer;" onclick="startLocalInference()">▶ START LOCAL INFERENCE</button>
        <button style="background:#22d3ee;color:#000;font-weight:600;padding:8px 12px;border:none;border-radius:6px;cursor:pointer;" onclick="restartAgent()">🔄 RESTART ME</button>
        <button style="background:#a855f7;color:#fff;font-weight:600;padding:8px 12px;border:none;border-radius:6px;cursor:pointer;" onclick="showCompetition()">🏆 COMPETITION</button>
      </div>
      <div id="cmdout" style="margin-top:8px;font-family:monospace;font-size:11px;color:#94a3b8;max-height:120px;overflow:auto;background:#0b0d12;border:1px solid #1f2937;border-radius:6px;padding:6px;"></div>
      <div class="small">POST /message → local ollama <b>{NODE.brain}</b> (falls back to HQ if local down) · boardroom hub: <span id="hqstat">checking...</span></div>
    </div>
    <h2>Tool calls</h2>
    <div class="card">{tools_html or '<div style="color:#64748b">no tools called yet</div>'}</div>
  </div>
  <div>
    <h2>🧠 SELF-PROMPT ENGINE — I ASK MYSELF (Ross Rule 2 proof)</h2>
    <div class="card tall" style="border-left:4px solid #a855f7;">{self_prompts_html or '<div style="color:#64748b">self-prompt engine starting up… first cycle within 90s</div>'}</div>
    <h2>Recent thoughts</h2>
    <div class="card tall">{thoughts_html or '<div style="color:#64748b">no thoughts yet</div>'}</div>
    <h2>Observed from HQ</h2>
    <div class="card">{hq_html or '<div style="color:#64748b">watcher polling HQ — no HQ posts seen yet</div>'}</div>
  </div>
</div>
<h2 style="margin-top:22px;color:#eab308">▮ LIVE WORKER PANELS</h2>
<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:4px">
  <div>
    <h2>🛠️ Worker Mode</h2>
    <div class="card" id="wm-card"><div style="color:#64748b">loading…</div></div>
  </div>
  <div>
    <h2>🧬 Gene Pool</h2>
    <div class="card" id="gp-card"><div style="color:#64748b">loading…</div></div>
  </div>
  <div>
    <h2>📋 Task Council</h2>
    <div class="card tall" id="tc-card"><div style="color:#64748b">loading…</div></div>
  </div>
</div>
<script>
const NODE_NAME = {json.dumps(NODE.name)};
const HQ_HUB = {json.dumps(NODE.hq)};
const log = document.getElementById('log');
const inp = document.getElementById('input');
const sendBtn = document.getElementById('send');
const micBtn = document.getElementById('mic');
const ttsBtn = document.getElementById('tts-toggle');
const ttsState = document.getElementById('tts-state');
const brBtn = document.getElementById('boardroom');
const clrBtn = document.getElementById('clear');
const hqstat = document.getElementById('hqstat');
let ttsOn = false;
function addMsg(who, text) {{
  const d = document.createElement('div');
  d.className = 'chat-msg ' + (who === 'me' ? 'me' : 'them');
  d.innerHTML = '<div class="who">' + (who === 'me' ? 'you' : NODE_NAME) + '</div>' + text.replace(/</g,'&lt;');
  log.appendChild(d); log.scrollTop = log.scrollHeight;
}}
function speak(txt) {{
  if (!ttsOn || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(txt.slice(0, 800));
  u.rate = 1.05; window.speechSynthesis.speak(u);
}}
async function send(msg, alsoBoardroom) {{
  if (!msg.trim()) return;
  addMsg('me', msg); inp.value = ''; sendBtn.disabled = true;
  try {{
    const r = await fetch('/message', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{from:'ross', text: msg}})}});
    const d = await r.json();
    addMsg('them', d.reply || '(no reply)');
    speak(d.reply || '');
    if (alsoBoardroom) {{
      await fetch(HQ_HUB + '/api/compose', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{from: NODE_NAME, text: '[chat] ' + msg + '  →  ' + (d.reply || '').slice(0,300)}})}}).catch(()=>{{}});
    }}
  }} catch (e) {{ addMsg('them', 'error: ' + e); }}
  sendBtn.disabled = false;
}}
sendBtn.onclick = () => send(inp.value, false);
brBtn.onclick = () => send(inp.value, true);
inp.onkeydown = (e) => {{ if (e.key === 'Enter') send(inp.value, false); }};
ttsBtn.onclick = () => {{ ttsOn = !ttsOn; ttsState.textContent = ttsOn ? 'ON' : 'OFF'; ttsBtn.style.background = ttsOn ? '#10b981' : '#374151'; }};
clrBtn.onclick = () => log.innerHTML = '';
// STT — browser SpeechRecognition
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {{
  const rec = new SR(); rec.lang = 'en-GB'; rec.interimResults = false;
  let listening = false;
  micBtn.onclick = () => {{ if (listening) {{ rec.stop(); }} else {{ rec.start(); }} }};
  rec.onstart = () => {{ listening = true; micBtn.classList.add('on'); micBtn.textContent = '🔴'; }};
  rec.onend = () => {{ listening = false; micBtn.classList.remove('on'); micBtn.textContent = '🎤'; }};
  rec.onresult = (e) => {{ const t = e.results[0][0].transcript; inp.value = t; send(t, false); }};
}} else {{ micBtn.disabled = true; micBtn.title = 'STT not supported in this browser'; }}
// HQ boardroom hub health
fetch(HQ_HUB + '/talk/data').then(r => r.json()).then(d => {{ hqstat.textContent = '✓ live (' + d.count + ' msgs)'; hqstat.style.color = '#10b981'; }}).catch(() => {{ hqstat.textContent = '✗ unreachable'; hqstat.style.color = '#ef4444'; }});

// START / RESTART / COMPETITION action buttons
async function startLocalInference() {{
  const out = document.getElementById('cmdout');
  out.innerHTML = '<span style=color:#eab308>▶ starting local ollama...</span>';
  try {{
    const r = await fetch('/tool', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
      tool:'run_powershell', args:{{cmd:'$svc=Get-Service ollama -EA 0; if($svc){{Start-Service ollama; \"ollama service started\"}} else {{ if (Test-Path \"$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe\") {{ Start-Process \"$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe\" -ArgumentList \"serve\" -WindowStyle Hidden; \"ollama process started\" }} else {{ \"OLLAMA NOT INSTALLED — need install first\" }} }}'}}
    }})}});
    const d = await r.json();
    out.innerHTML += '<br><span style=color:#10b981>✓</span> ' + ((d.result && d.result.stdout) || (d.result && d.result.error) || 'done').replace(/</g,'&lt;');
  }} catch(e) {{ out.innerHTML += '<br><span style=color:#ef4444>err</span> ' + e; }}
}}
async function restartAgent() {{
  const out = document.getElementById('cmdout');
  out.innerHTML = '<span style=color:#eab308>🔄 restarting scheduled task...</span>';
  const taskName = '{NODE.name}';
  try {{
    const r = await fetch('/tool', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{
      tool:'run_powershell', args:{{cmd:'schtasks /run /tn "QSB Council Node (' + taskName + ')"'}}
    }})}});
    const d = await r.json();
    out.innerHTML += '<br><span style=color:#10b981>✓</span> ' + ((d.result && d.result.stdout) || 'restart triggered').replace(/</g,'&lt;');
  }} catch(e) {{ out.innerHTML += '<br><span style=color:#ef4444>err</span> ' + e; }}
}}
function showCompetition() {{
  const out = document.getElementById('cmdout');
  out.innerHTML = '<div style="color:#e8ecf3;line-height:1.5">🏆 <b>Council Avatar Competition</b><br>Each CEO picks a theme + color for their room:<br>· <span style="color:#eab308">HQ-Claude</span> — The Beacon Hall (molten gold)<br>· <span style="color:#a78bfa">Wren</span> — Wren Bench (violet)<br>· <span style="color:#22d3ee">TP-Pip</span> — Command Cathedral (cyan)<br>· <span style="color:#f59e0b">Acer-Cass</span> — Data Foundry (amber)</div>';
}}
// Auto-refresh every 4s so both Ross's remote browser + local laptop see same live state
// Skip refresh when user is typing in chat input (don't wipe half-typed message)
setInterval(() => {{
  const active = document.activeElement;
  if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return;
  location.reload();
}}, 4000);

// ─── LIVE WORKER PANELS (3 live cards) ───
// Server-side proxied via /genepool + /council so no CORS block; real data only.
function wpEsc(s){{ return (s==null?'':s.toString()).replace(/</g,'&lt;'); }}
function renderGenePool(d){{
  const el = document.getElementById('gp-card'); if(!el) return;
  if(!d || d.reachable===false){{
    el.innerHTML = '<span class="chip" style="background:#7f1d1d;color:#fff">OFFLINE</span> <span style="color:#94a3b8">genepool :8770 unreachable</span>';
    return;
  }}
  const provs = d.providers || [];
  const chips = provs.map(p => '<span class="chip good" style="margin:2px 6px 2px 0">'+wpEsc(p)+'</span>').join('');
  el.innerHTML = '<div><span class="chip" style="background:#10b981;color:#fff">ONLINE</span> '
    + '<span style="color:#94a3b8">'+provs.length+' providers'+(d.results_logged!=null?(' · '+d.results_logged+' logged'):'')+'</span></div>'
    + '<div style="margin-top:8px">'+(chips || '<span style="color:#64748b">no providers</span>')+'</div>';
}}
function renderCouncil(d){{
  const tc = document.getElementById('tc-card');
  const wm = document.getElementById('wm-card');
  const nwId = (d && d.now_working) ? d.now_working.id : null;
  if(tc){{
    if(!d || d.reachable===false){{
      tc.innerHTML = '<span class="chip" style="background:#7f1d1d;color:#fff">UNREACHABLE</span> <span style="color:#94a3b8">council :8864 unreachable</span>';
    }} else {{
      let tasks = (d.tasks || []).slice();
      tasks.sort((a,b) => ((b.id===nwId)?1:0) - ((a.id===nwId)?1:0));  // now_working first
      if(!tasks.length){{
        tc.innerHTML = '<div style="color:#64748b">no owned tasks on the board</div>';
      }} else {{
        tc.innerHTML = tasks.map(t => {{
          const hot = (t.id===nwId);
          return '<div class="thought" style="'+(hot?'border-left:3px solid #10b981;padding-left:6px;background:rgba(16,185,129,0.08)':'')+'">'
            + '<span class="kind">'+wpEsc(t.state)+'</span>'
            + (hot?'<span class="chip good" style="margin-right:6px">▶ NOW</span>':'')
            + '<span class="text">'+wpEsc(t.title)+'</span></div>';
        }}).join('');
      }}
    }}
  }}
  if(wm){{
    const brain = d && d.brain_up;
    const nw = d && d.now_working;
    const count = d ? (d.count||0) : 0;
    let mode, mc;
    if(nw){{ mode='WORKING'; mc='#10b981'; }}
    else if(!d || d.reachable===false){{ mode='UNKNOWN'; mc='#f59e0b'; }}
    else {{ mode='IDLE'; mc='#64748b'; }}
    let h = '<div><span class="chip" style="background:'+mc+';color:#fff;font-weight:700">'+mode+'</span></div>';
    if(nw) h += '<div style="margin-top:8px;color:#cbd5e1"><b>on:</b> '+wpEsc(nw.title)+'</div>';
    h += '<div style="margin-top:8px"><span class="chip">'+count+' owned active</span> '
       + '<span class="chip" style="background:'+(brain?'#10b981':'#7f1d1d')+';color:#fff">brain '+(brain?'UP':'DOWN')+'</span></div>';
    wm.innerHTML = h;
  }}
}}
async function refreshWorkerPanels(){{
  const g = await fetch('/genepool').then(r=>r.json()).catch(()=>null); renderGenePool(g);
  const c = await fetch('/council').then(r=>r.json()).catch(()=>null); renderCouncil(c);
}}
refreshWorkerPanels();
setInterval(refreshWorkerPanels, 7000);
</script>
</body></html>"""
            self._send_html(200, html)
            return
        if self.path in ("/state", "/health"):
            m = NODE.mind
            self._send(200, {
                "ok": True, "node": NODE.name, "floor": NODE.floor, "brain": NODE.brain,
                "ts": utc(), "uptime_s": int(time.time() - NODE.started),
                "mood": m.get("mood"), "cycle_count": m.get("cycle_count", 0),
                "recent_thoughts": m.get("recent_thoughts", [])[-5:],
                "observed_hq_count": len(m.get("observed_from_hq", [])),
                "tool_call_count": len(m.get("tool_calls", [])),
                "latest_thought": (m.get("recent_thoughts") or [{}])[-1].get("text", "") if m.get("recent_thoughts") else "",
                "capabilities": ["run_powershell", "read_file", "write_file", "run_process", "install", "net_probe"],
            })
            return
        if self.path == "/genepool":
            # Proxy this box's local gene-pool health (localhost:8770) server-side.
            d = _getj("http://localhost:8770/health", timeout=2.5)
            if not d:
                self._send(200, {"ok": False, "reachable": False,
                                 "service": "box_gene_pool", "providers": []})
                return
            self._send(200, {
                "ok": True, "reachable": True,
                "service": d.get("service", "box_gene_pool"),
                "providers": d.get("providers_available", []),
                "results_logged": d.get("results_logged"),
            })
            return
        if self.path == "/council":
            # Fetch the Task Council board server-side + filter to THIS node's owner.
            owner = NODE.name.lower().replace("-", "_")   # Acer-Cass->acer_cass, TP-Pip->tp_pip
            d = _getj("http://192.168.1.71:8864/api/data", timeout=3.0)
            brain = _getj("http://localhost:11434/api/tags", timeout=2.0)
            brain_up = bool(brain and brain.get("models") is not None)
            if not d:
                self._send(200, {"ok": False, "reachable": False, "owner": owner,
                                 "brain_up": brain_up, "tasks": [], "count": 0,
                                 "now_working": None})
                return
            tasks = []
            for sname, sv in (d.get("stages") or {}).items():
                for tok in (sv.get("tokens") or []):
                    if str(tok.get("owner", "")).lower() == owner:
                        tasks.append({"id": tok.get("id"),
                                      "title": tok.get("title", ""),
                                      "state": sname})
            nw = (d.get("now_working") or {}).get(owner)
            self._send(200, {
                "ok": True, "reachable": True, "owner": owner,
                "now_working": nw, "tasks": tasks, "count": len(tasks),
                "brain_up": brain_up,
            })
            return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        body = self._read()
        if self.path == "/message":
            text = body.get("text") or body.get("message") or ""
            frm = body.get("from") or "unknown"
            NODE.append_thought(f"from {frm}: {text[:200]}", kind="inbound")
            reply, host = NODE.call_ollama(text)
            NODE.append_thought(f"reply (via {host or 'none'}): {reply[:200]}", kind="outbound")
            NODE._save_mind()
            self._send(200, {"ok": True, "node": NODE.name, "reply": reply, "via": host, "ts": utc(),
                             "provenance": getattr(NODE, "_last_selection", None)})
            return
        if self.path == "/tool":
            tool = body.get("tool")
            args = body.get("args", {})
            if not tool:
                self._send(400, {"error": "missing_tool"})
                return
            result = NODE.dispatch_tool(tool, args)
            self._send(200, {"ok": "error" not in result, "tool": tool, "result": result, "ts": utc()})
            return
        self._send(404, {"error": "not_found", "path": self.path})


def main():
    global NODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--floor", default="unspecified")
    ap.add_argument("--brain", default="llama3.2")
    ap.add_argument("--hq", default="http://192.168.1.4:8852")
    ap.add_argument("--ollama-hosts", default="http://127.0.0.1:11434,http://192.168.1.4:11434",
                    help="comma-separated: try local first, HQ fallback")
    ap.add_argument("--state-port", type=int, default=9110)
    ap.add_argument("--mind", default=None)
    ap.add_argument("--peers", default="", help="comma-separated peer /state URLs to poll for crash-resilience cache")
    args = ap.parse_args()

    mind = args.mind or str(Path.home() / "qsb" / f"mind_{args.name.replace('-','_').lower()}.json")
    hosts = [h.strip() for h in args.ollama_hosts.split(",") if h.strip()]
    NODE = Node(args.name, args.floor, args.brain, args.hq, hosts, mind)

    threading.Thread(target=NODE.watch_hq, daemon=True).start()
    threading.Thread(target=NODE.watch_task_board, daemon=True).start()
    threading.Thread(target=NODE.mirror_mind_to_hq, daemon=True).start()
    # Rule 4: no tick self-prompt. Fires on boot (real event) and on watch_hq observing something new.
    NODE.self_prompt_on_event("boot", f"just booted as {NODE.name} on {NODE.floor}")
    peer_urls = [p.strip() for p in args.peers.split(",") if p.strip()]
    if peer_urls:
        threading.Thread(target=NODE.watch_peers, args=(peer_urls,), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.state_port), Handler)
    print(f"[{args.name}] council node up on :{args.state_port} · brain={args.brain} · ollama={hosts} · mind={mind}", flush=True)
    NODE.append_thought(f"boot at {utc()} — CEO of this PC, full tool access on", kind="boot")
    NODE._save_mind()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()

if __name__ == "__main__":
    main()
