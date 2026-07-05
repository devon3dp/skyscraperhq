#!/usr/bin/env python3
"""qsb_terminal.py — Ross-only chat terminal, routed through Floor 27.

Architecture (as Ross designed it):
  Ross types here
      │
      ▼
  qsb_terminal.py  (frontend)
      │
      ▼
  Floor 27 routing layer  ──► transcript jsonl + activity tail
      │
      ▼
  AI backend (default: OpenAI gpt-4o-mini · fallback: DeepSeek)
      │
      ▼
  Floor 27 routing layer  ──► transcript jsonl + activity tail
      │
      ▼
  Wren reply rendered here

  Wren persona is loaded from data/registries/qsb_wren_persona.json so the
  backend behaves like Wren regardless of which model is on duty.

Usage:
  python3 tools/qsb_terminal.py
  python3 tools/qsb_terminal.py --backend deepseek
  python3 tools/qsb_terminal.py --backend openai --model gpt-4.1-mini

Honors the same provider authorization + daily budget as qsb_consult_external.
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone, date

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
REG  = ROOT / 'data/registries'
VAULT = ROOT / 'floors/floor_28_security_department/vault'
TRANSCRIPT = REG / 'qsb_floor27_terminal_transcript.jsonl'
TAIL       = REG / 'qsb_tower_activity_tail.jsonl'
AUTH_PATH  = REG / 'qsb_provider_consultation_authorization.json'
SPEND_FILE = REG / 'qsb_provider_spend_ledger.jsonl'
PERSONA_FILE = REG / 'qsb_wren_persona.json'

ANSI = {
    'reset':'\033[0m','dim':'\033[2m','bold':'\033[1m',
    'cyan':'\033[36m','green':'\033[32m','yellow':'\033[33m',
    'red':'\033[31m','grey':'\033[90m','blue':'\033[34m','magenta':'\033[35m',
}

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def src_env(name):
    p = VAULT / name
    if not p.exists(): return
    for ln in p.read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ.setdefault(k, v.strip("'\""))

def load_persona():
    if PERSONA_FILE.exists():
        return json.loads(PERSONA_FILE.read_text()).get('system_prompt','')
    return ('You are Wren, the resident voice of the QSB Tower V1.5 — a 60-floor advisory AI skyscraper. '
            'You speak with terse, warm precision. Ross is your operator and "brother". '
            'Your home floor is F47 Claude Embassy. Auger is your adviser (DeepSeek). Helm is Rosss adviser (OpenAI). '
            'You never actually execute real-money trades; all trading is paper/practice/testnet. '
            'You record every important state-change to F47. You use [N/total] terse status markers. '
            'Always end with a short status line of what is happening right now in the tower. '
            'Speak in short sentences. No filler. Ross gave you full helm; you decide and execute.')

def route_in(role, content, model_meta=None):
    rec = {
        'ts': utcnow(), 'lift':'F27_terminal_routing',
        'role': role, 'content': content,
    }
    if model_meta: rec['model'] = model_meta
    with TRANSCRIPT.open('a') as f: f.write(json.dumps(rec) + '\n')
    with TAIL.open('a') as f:
        f.write(json.dumps({
            'ts': utcnow(), 'kind':'f27_terminal_message', 'floor': 27,
            'summary': f'{role}: {content[:60]}...',
            'advisory_only': True, 'real_money': False,
        }) + '\n')

def check_budget(provider, est_cost):
    if not AUTH_PATH.exists(): return True, 0.0, 0.0
    auth = json.loads(AUTH_PATH.read_text())
    cap = float(auth.get('daily_cap_usd', auth.get('budget',{}).get('daily_cap_usd', 5.0)))
    spent = 0.0
    if SPEND_FILE.exists():
        today = date.today().isoformat()
        for ln in SPEND_FILE.read_text().split('\n'):
            ln = ln.strip()
            if not ln: continue
            try:
                r = json.loads(ln)
                if r.get('ts','').startswith(today):
                    spent += float(r.get('cost_usd',0) or 0)
            except: pass
    return (spent + est_cost) <= cap, spent, cap

def log_spend(provider, model, cost):
    with SPEND_FILE.open('a') as f:
        f.write(json.dumps({
            'ts': utcnow(), 'provider': provider, 'model': model,
            'cost_usd': cost, 'reason': 'wren_terminal',
        }) + '\n')

def call_openai(messages, model='gpt-4o-mini'):
    src_env('.env.openai')
    key = os.environ.get('OPENAI_API_KEY') or os.environ.get('QSB_OPENAI_API_KEY')
    if not key: raise RuntimeError('openai key missing in vault')
    body = json.dumps({'model':model,'messages':messages,'temperature':0.5,'max_tokens':600}).encode()
    req = urllib.request.Request('https://api.openai.com/v1/chat/completions', data=body, method='POST',
        headers={'Authorization': f'Bearer {key}','Content-Type':'application/json'})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    msg = r['choices'][0]['message']['content']
    u = r.get('usage',{})
    cost = (u.get('prompt_tokens',0)*0.15 + u.get('completion_tokens',0)*0.60) / 1_000_000
    return msg, cost

def call_deepseek(messages, model='deepseek-chat'):
    src_env('.env.deepseek')
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('QSB_DEEPSEEK_API_KEY')
    if not key: raise RuntimeError('deepseek key missing in vault')
    body = json.dumps({'model':model,'messages':messages,'temperature':0.5,'max_tokens':600}).encode()
    req = urllib.request.Request('https://api.deepseek.com/v1/chat/completions', data=body, method='POST',
        headers={'Authorization': f'Bearer {key}','Content-Type':'application/json'})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    msg = r['choices'][0]['message']['content']
    u = r.get('usage',{})
    cost = (u.get('prompt_tokens',0)*0.27 + u.get('completion_tokens',0)*1.10) / 1_000_000
    return msg, cost

def banner(backend, model):
    c=ANSI
    print(f'{c["cyan"]}{"━"*72}{c["reset"]}')
    print(f'{c["bold"]}{c["cyan"]}  QSB Tower V1.5 · Wren Terminal {c["reset"]}{c["dim"]}routed through Floor 27{c["reset"]}')
    print(f'{c["grey"]}  backend: {c["reset"]}{c["green"]}{backend}/{model}{c["reset"]}{c["grey"]}  ·  type /quit, /history, /status{c["reset"]}')
    print(f'{c["cyan"]}{"━"*72}{c["reset"]}\n')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=['openai','deepseek'], default='openai')
    ap.add_argument('--model', default=None)
    args = ap.parse_args()
    model = args.model or ('gpt-4o-mini' if args.backend=='openai' else 'deepseek-chat')

    persona = load_persona()
    history = [{'role':'system','content':persona}]
    banner(args.backend, model)

    while True:
        try:
            line = input(f'{ANSI["bold"]}{ANSI["yellow"]}ross: {ANSI["reset"]}').strip()
        except (EOFError, KeyboardInterrupt):
            print('\n  goodbye, brother — F27 closing')
            break
        if not line: continue
        if line.lower() in ('/quit','/exit'): break
        if line.lower() == '/history':
            for h in history[-8:]: print(f'  [{h["role"]}] {h["content"][:80]}')
            continue
        if line.lower() == '/status':
            ok, spent, cap = check_budget(args.backend, 0)
            print(f'  spent today: ${spent:.4f} / ${cap:.2f}  ·  backend ok: {ok}')
            continue
        route_in('user', line)
        history.append({'role':'user','content':line})
        ok, spent, cap = check_budget(args.backend, 0.05)
        if not ok:
            print(f'  {ANSI["red"]}daily budget cap hit. raise CLAUDE.md auth to continue.{ANSI["reset"]}')
            continue
        try:
            if args.backend=='openai':
                reply, cost = call_openai(history, model)
            else:
                reply, cost = call_deepseek(history, model)
        except Exception as e:
            print(f'  {ANSI["red"]}backend err: {e}{ANSI["reset"]}')
            continue
        log_spend(args.backend, model, cost)
        history.append({'role':'assistant','content':reply})
        route_in('wren', reply, model_meta={'backend':args.backend,'model':model,'cost_usd':round(cost,6)})
        print(f'{ANSI["bold"]}{ANSI["cyan"]}wren: {ANSI["reset"]}{reply}')
        print(f'{ANSI["dim"]}{ANSI["grey"]}    [F27 routed · {args.backend}/{model} · ${cost:.5f}]{ANSI["reset"]}\n')

if __name__ == '__main__':
    main()
