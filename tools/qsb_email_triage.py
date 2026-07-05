#!/usr/bin/env python3
"""qsb_email_triage.py — classify + suggest action for inbound emails.

Input: pipe an email body to stdin OR pass --json with a list of emails.
Output: classification + suggested action + draft reply.

Classes:
  - order_confirmation         (we sent this — log, no reply)
  - customer_enquiry           (draft response, escalate if complex)
  - return_request             (draft return flow steps)
  - shipping_complaint         (escalate to F108)
  - payment_dispute            (escalate immediately + F44 alert)
  - spam_or_marketing          (label + ignore)
  - newsletter_subscribe       (add to list + welcome)
  - unknown                    (escalate to F108)
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
LOG = ROOT / 'data/registries/qsb_email_triage_log.jsonl'

CLASSIFIERS = [
    ('payment_dispute',     [r'chargeback', r'unauthor[is]z', r'fraud', r'dispute', r'didn[\'’]?t (order|authoris)', r'refund.*?(transaction|charge)']),
    ('return_request',      [r'\breturn\b', r'send back', r'refund.*?item', r'not as described', r'wrong item', r'damaged']),
    ('shipping_complaint',  [r'where[\'’]?s my order', r'not arrived', r'delivery.*?(late|missing|delay)', r'tracking', r'lost in post']),
    ('customer_enquiry',    [r'\bquestion\b', r'how do I', r'can you tell me', r'wondering', r'before I (buy|order)']),
    ('newsletter_subscribe',[r'subscribe', r'sign up.*?newsletter', r'add me to']),
    ('order_confirmation',  [r'thank you for your purchase', r'order confirmation', r'order #\d+', r'has been received']),
    ('spam_or_marketing',   [r'increase your.*?(traffic|sales|revenue)', r'guaranteed.*?(rankings|seo)', r'special offer.*?for you', r'work from home', r'unsubscribe me from your', r'why am i receiving']),
]

REPLY_TEMPLATES = {
    'customer_enquiry': "Thank you for reaching out. We've received your enquiry and a member of our team will reply within one working day. — Customer Care",
    'return_request': "Thank you for your message. To start a return: reply with your order number and item, and we'll send return instructions. Returns are accepted within 14 days of receipt (UK Consumer Contracts Regulations). — Customer Care",
    'shipping_complaint': "We're sorry to hear about the delay. Standard UK delivery is 7-14 working days. Please reply with your order number and we'll check status with the supplier immediately. — Customer Care",
    'newsletter_subscribe': "Welcome — you're on the list. Your first issue arrives next week. To unsubscribe at any time, reply STOP. — The Editor",
    'payment_dispute': "We've received your message and have alerted our finance team. You will hear back within one working day. We take all payment concerns seriously. — Finance",
}

def utcnow():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def classify(text):
    text_lc = text.lower()
    for label, patterns in CLASSIFIERS:
        for p in patterns:
            if re.search(p, text_lc, re.IGNORECASE):
                return label
    return 'unknown'

def triage(email):
    body = email.get('body','') if isinstance(email, dict) else str(email)
    cls = classify(body)
    reply = REPLY_TEMPLATES.get(cls, "Thank you for your message. We'll be in touch within one working day. — Customer Care")
    suggested_action = {
        'payment_dispute':   'auto_acknowledge + escalate_to_F44 + F108 critical',
        'shipping_complaint':'auto_reply + escalate_to_F108',
        'return_request':    'auto_reply with template + label thread',
        'customer_enquiry':  'auto_acknowledge + queue to F108 for human review',
        'newsletter_subscribe':'auto_welcome + add to subscriber list',
        'order_confirmation':'log only (we sent this)',
        'spam_or_marketing': 'label and ignore',
        'unknown':           'escalate_to_F108',
    }[cls]
    return {'class': cls, 'suggested_action': suggested_action, 'reply_draft': reply}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true', help='read a list of emails from stdin as JSON')
    a = ap.parse_args()
    if a.json:
        emails = json.loads(sys.stdin.read())
        out = []
        for e in emails:
            r = triage(e)
            with LOG.open('a') as f:
                f.write(json.dumps({'ts':utcnow(),'email_id':e.get('id'),**r})+'\n')
            out.append({'id':e.get('id'),**r})
        print(json.dumps(out, indent=2))
    else:
        text = sys.stdin.read()
        r = triage(text)
        with LOG.open('a') as f:
            f.write(json.dumps({'ts':utcnow(), **r})+'\n')
        print(json.dumps(r, indent=2))

if __name__ == '__main__':
    main()
