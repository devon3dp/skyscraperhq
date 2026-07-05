#!/usr/bin/env python3
"""qsb_leak_audit.py — scan public-facing files for skyscraper internal references.

Usage:
  python3 tools/qsb_leak_audit.py web/shops/
  python3 tools/qsb_leak_audit.py path/to/any/folder
  python3 tools/qsb_leak_audit.py --string "some text to check"

Exit 0 = clean. Exit 1 = leaks found (BLOCKS publish).
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

# Tokens that must NEVER appear in public-facing content
FORBIDDEN = [
    r'\bskyscraper\b',  # internal name (we'll review master landing separately)
    r'\bqsb\b',
    r'\bqsb_?tower\b',
    r'\bfloor_\d+\b',
    r'(?<!%)\bF\d{1,3}\b(?![A-Fa-f0-9])',  # F47, F60 etc — but not URL-encoded %F0 or hex bytes
    r'\bwren\b',
    r'\bauger\b',
    r'\bhelm\b(?! (chair|of))',  # exclude generic "helm of X"
    r'lumin.{0,3}internal',
    r'\boanda\b',
    r'\bbinance\b',
    r'\balpaca\b',
    r'sk_(test|live)_\w+',  # Stripe secret keys
    r'pk_(test|live)_\w+',  # Stripe publishable keys
    r'whsec_\w+',
    r'\bopenai_api_key\b|\bdeepseek_api_key\b',
    r'sealed[ _-]packet',
    r'\bsentinel\b',
    r'\bhelix\b',
    r'\blineage\b',
    r'classroom_gated|classroom-gated',
    r'\bopenclaw\b',
    r'\bkernel\b',
    r'\bpenthouse\b',
    r'ross[ ]?knechtel',
    r'/vaults/',
    r'\.env\.[a-z]+',
    r'\badvisory_only\b',
    r'ledger_clerk',
    r'\bscribe\b',
    r'\binternal_only\b',
    r'\bf47\b',
    r'\bf44\b',
    r'qsb_floor\d+',
    r'real_money_(live_)?trading',
]
PATTERNS = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN]

# Allowlist: master landing legitimately uses "Skyscraper" as the consumer brand name
# Skyscraper is the consumer brand; allow in any web/shops/ public file
ALLOWLIST = {
    # The public brand name is OK everywhere
    # Ross's email is the authorized public customer-support contact (Ross 2026-06-11 helm decision)
    '__GLOBAL_PUBLIC__': [r'\bSkyscraper\b', r'knechtelross@gmail\.com'],
}

def scan_text(text, file_label='string'):
    hits = []
    allowed = ALLOWLIST.get(file_label, []) + ALLOWLIST.get('__GLOBAL_PUBLIC__', [])
    for pat, raw in zip(PATTERNS, FORBIDDEN):
        if any(re.search(ap, raw, re.IGNORECASE) for ap in allowed):
            continue
        for m in pat.finditer(text):
            # Check against allowlist for this file
            matched_text = m.group(0)
            if any(re.match(ap, matched_text, re.IGNORECASE) for ap in allowed):
                continue
            line_no = text.count('\n', 0, m.start()) + 1
            col = m.start() - text.rfind('\n', 0, m.start())
            hits.append({'pattern': raw, 'match': matched_text, 'line': line_no, 'col': col})
    return hits

def scan_path(path):
    p = Path(path)
    results = {}
    files_to_scan = []
    if p.is_file():
        files_to_scan = [p]
    elif p.is_dir():
        for f in p.rglob('*'):
            if f.is_file() and f.suffix in ('.html','.htm','.css','.js','.json','.md','.txt','.svg'):
                files_to_scan.append(f)
    for f in files_to_scan:
        try:
            t = f.read_text(errors='ignore')
        except Exception:
            continue
        rel = str(f.relative_to(Path.cwd())) if f.is_absolute() else str(f)
        hits = scan_text(t, rel)
        if hits:
            results[rel] = hits
    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', nargs='?', help='file or folder to scan')
    ap.add_argument('--string', help='scan a literal string instead of a path')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    if a.string:
        hits = scan_text(a.string)
        if a.json:
            print(json.dumps(hits, indent=2))
        else:
            if hits:
                print(f'BLOCKED — {len(hits)} leaks:')
                for h in hits: print(f"  match='{h['match']}' pattern={h['pattern']}")
                return 1
            print('clean')
        return 0 if not hits else 1
    if not a.target:
        ap.error('provide a path or --string')
    results = scan_path(a.target)
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        if results:
            print(f'BLOCKED — leaks found in {len(results)} file(s):')
            for f, hits in results.items():
                print(f'  {f}:')
                for h in hits[:5]:
                    print(f"    L{h['line']}:{h['col']}  '{h['match']}'  (pattern {h['pattern']})")
                if len(hits) > 5:
                    print(f'    ...+{len(hits)-5} more')
        else:
            print(f'clean — scanned {a.target}')
    return 1 if results else 0

if __name__ == '__main__':
    sys.exit(main())
