#!/usr/bin/env python3
"""The review REPORT: where do findings leak through the method, and what should be promoted?

    python review_report.py --app <repo root> [--since 2026-11-01] [--json out.json]

**Why (Ben, 2026-11-08):** *"a key concept is capturing the results of these reviews so it can fine
tune the performance and improve over time."* Every finding in every screen's record says where it was
found (`origin`: lint, review, self-walk, walkthrough) and, once Ben has seen it, which layer SHOULD
have caught it (`caught_by`: scope, canon, review, lint, test, taste). This reads them all and prints:

1. **The leak:** walkthrough findings per walkthrough date, split taste / not taste. The number to
   watch is NOT-TASTE findings per walkthrough: each one is something an earlier layer should have
   caught. It should fall.
2. **Where they leak:** walkthrough findings counted by `caught_by`.
3. **Promote:** a friction-checklist `row` or a named `component` that turns up on two or more screens
   in walkthrough or review findings. A repeat is promoted into the layer that should have caught it:
   a component or rule in the app's catalogue, a checklist line, a lint rule, or a ratchet test.
4. **Waiting on Ben:** `ben` findings, and walkthrough findings still `open`.

Stdlib only; reads the same records the gate checks (`check_surface_reviews.read_record`)."""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import check_surface_reviews as gate


def findings(app):
    """Every finding in every record, flattened with its screen, entry kind and date."""
    config = gate.load_config(app)
    rows = []
    for path in sorted((app / config['records']).glob('*.md')):
        if path.name.startswith('_'):
            continue
        try:
            record = gate.read_record(path)
        except Exception:
            continue
        for entry in record.get('entry', []):
            kind = entry.get('kind')
            for f in entry.get('finding', []):
                rows.append({**f, 'screen': path.stem, 'kind': kind, 'date': str(entry.get('date', '')),
                             'origin': f.get('origin', 'walkthrough' if kind == 'walkthrough' else 'review')})
    return rows


def report(rows, since=''):
    rows = [r for r in rows if not since or r['date'] >= since]
    walk = [r for r in rows if r['origin'] == 'walkthrough']
    by_date = defaultdict(Counter)
    for r in walk:
        by_date[r['date']]['taste' if r.get('caught_by') == 'taste' else 'not taste'] += 1
    repeats = defaultdict(set)
    for r in rows:
        if r['origin'] in ('walkthrough', 'review', 'self-walk'):
            if r.get('row'):
                repeats[f'checklist row {r["row"]}'].add(r['screen'])
            if r.get('component'):
                repeats[f'component {r["component"]}'].add(r['screen'])
    return {
        'leak': {d: dict(c) for d, c in sorted(by_date.items())},
        'caught_by': dict(Counter(r.get('caught_by', 'unsaid') for r in walk).most_common()),
        'origins': dict(Counter(r['origin'] for r in rows).most_common()),
        'promote': {k: sorted(v) for k, v in sorted(repeats.items()) if len(v) >= 2},
        'waiting': [f'{r["screen"]} {r.get("id", "?")}: {r.get("what", "")}'.strip()
                    for r in rows if r.get('outcome') == 'ben' or (r['origin'] == 'walkthrough'
                                                                    and r.get('outcome') == 'open')],
    }


def print_report(result):
    print('Review report')
    print('\n1. The leak: walkthrough findings per walkthrough (not taste = an earlier layer missed it)')
    for date, counts in result['leak'].items() or []:
        print(f'   {date or "undated"}: {counts.get("not taste", 0)} not taste, {counts.get("taste", 0)} taste')
    if not result['leak']:
        print('   none recorded yet')
    print('\n2. Where they leak (should have been caught by)')
    for layer, n in result['caught_by'].items():
        print(f'   {layer}: {n}')
    print('\n3. Promote (seen on two or more screens)')
    for what, screens in result['promote'].items():
        print(f'   {what}: {", ".join(screens)}')
    if not result['promote']:
        print('   nothing repeats yet')
    print(f'\n4. Waiting on Ben: {len(result["waiting"])}')
    for line in result['waiting']:
        print(f'   {line}')
    print(f'\nAll findings by origin: {", ".join(f"{k} {v}" for k, v in result["origins"].items()) or "none"}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--app', required=True, type=Path)
    ap.add_argument('--since', default='', help='only entries dated on or after this (YYYY-MM-DD)')
    ap.add_argument('--json', type=Path, help='also write the result here')
    opts = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    result = report(findings(opts.app.resolve()), opts.since)
    print_report(result)
    if opts.json:
        opts.json.write_text(json.dumps(result, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
