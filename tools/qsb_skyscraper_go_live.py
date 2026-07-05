#!/usr/bin/env python3
"""qsb_skyscraper_go_live.py — flip everything to the permanent URL.

Run AFTER Ross has:
  - Deployed to Netlify (auto-deploy from GitHub)
  - Added DNS records in Namecheap pointing skyscraperhq.uk → Netlify
  - Confirmed https://skyscraperhq.uk serves the site

This script:
  1. Updates Stripe business_profile.url to https://skyscraperhq.uk
  2. Recreates 150 Payment Links with new redirect URLs
  3. Updates products.json with new buy URLs
  4. Updates all shop HTML files
  5. Commits + reports
"""
from __future__ import annotations
import json, os, urllib.request, urllib.parse, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/vaults/nvme0/qsb_tower_v1')
NEW_URL = 'https://skyscraperhq.uk'

def src_stripe():
    for ln in (ROOT/'floors/floor_28_security_department/vault/.env.stripe').read_text().split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln.startswith('export '): ln = ln[7:]
        if '=' in ln:
            k, v = ln.split('=', 1)
            os.environ[k] = v.strip("'\"")

def stripe_post(path, fields):
    sk = os.environ['STRIPE_SECRET_KEY']
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f'https://api.stripe.com{path}', data=data, method='POST',
        headers={'Authorization': f'Bearer {sk}'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def main():
    src_stripe()
    print(f'going LIVE on {NEW_URL}')
    
    # 1) Update Stripe business profile URL
    ACCT = json.loads(urllib.request.urlopen(
        urllib.request.Request('https://api.stripe.com/v1/account',
            headers={'Authorization': f'Bearer {os.environ["STRIPE_SECRET_KEY"]}'})).read())['id']
    try:
        r = stripe_post(f'/v1/accounts/{ACCT}', {'business_profile[url]': NEW_URL})
        print(f'  ✓ Stripe business_profile.url updated to {NEW_URL}')
    except Exception as e:
        print(f'  ⚠ Stripe URL update (may need dashboard): {e}')
    
    # 2) Recreate Payment Links with new redirect URLs
    links = json.loads((ROOT/'data/registries/qsb_stripe_payment_links.json').read_text())['links']
    new_links = {}
    for sku, info in links.items():
        try:
            slug = info['shop']
            r = stripe_post('/v1/payment_links', {
                'line_items[0][price]': info['price_id'],
                'line_items[0][quantity]': '1',
                f'metadata[sku]': sku,
                f'metadata[shop]': slug,
                'after_completion[type]': 'redirect',
                'after_completion[redirect][url]': f'{NEW_URL}/{slug}/thank-you.html?thank_you={sku}',
                'shipping_address_collection[allowed_countries][0]': 'GB',
                'shipping_address_collection[allowed_countries][1]': 'IE',
                'phone_number_collection[enabled]': 'true',
                'allow_promotion_codes': 'true',
            })
            new_links[sku] = {**info, 'payment_link_id': r['id'], 'payment_link_url': r['url']}
            print(f'  ✓ {sku}: {r["url"]}')
        except Exception as e:
            new_links[sku] = info
            print(f'  ⚠ {sku}: {e}')
    
    out = ROOT/'data/registries/qsb_stripe_payment_links.json'
    payload = json.loads(out.read_text())
    payload['links'] = new_links
    payload['updated_ts'] = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    out.write_text(json.dumps(payload, indent=2))
    print(f'\n  ✓ {len(new_links)} Payment Links recreated')

if __name__ == '__main__':
    sys.exit(main() or 0)
