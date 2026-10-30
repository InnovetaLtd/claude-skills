#!/usr/bin/env python3
"""The surface-review GATE: refuse to land a screen change nobody reviewed.

    python check_surface_reviews.py --app <repo root> [--base <git ref>]
    python check_surface_reviews.py --app <repo root> --fingerprint <slug>      # for a new record entry
    python check_surface_reviews.py --app <repo root> --init-unregistered       # bootstrap, once per app

Part of the Innoveta surface review (standards/surface-review.md; the scope and Ben's rulings SR1-SR19
live in Build Manager's docs/surface-review-suite-2026-10-29.md). The app's `surface-review.toml` names
its registry, records, the unregistered list and the lint baseline. Stdlib only (Python 3.11+).

It is STATELESS on purpose: every check reads the tree as it stands, so it runs the same in a merge
queue, in CI on push, or by hand. A review is tied to the screen's templates by a FINGERPRINT (a hash
of their text, line endings normalised), so "this template changed after its last review" needs no
diff and no base. Only the shrink-only rules need `--base` (the ref being landed onto); without it
they are skipped and the output says so.

It fails (exit 1) when:
  1. a registry entry is malformed (missing goal lines, a template that does not exist, no
     `empty`/`typical` setup);
  2. a page template is neither registered nor on the unregistered list (SR5: "register this screen");
  3. an unregistered page template CHANGED (SR18: register on touch), or its list entry is stale;
  4. a registered screen has no record, or its record's latest entry does not match the templates'
     current fingerprint (the screen changed after its last review);
  5. a record breaks the finding rules: every finding rated major/moderate/minor and ended
     fixed/waived/ben; a waiver only on a minor finding, with a reason (SR9, SR12, SR12a);
  6. with --base: the unregistered list or the lint baseline GREW (SR17, SR18: shrink-only).
An `n/a` entry (a change that needed no review, with its reason) passes, and is listed in the output
so it stays visible (SR3)."""
import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

SEVERITIES = ('major', 'moderate', 'minor')
OUTCOMES = ('fixed', 'waived', 'ben')
GOAL_KEYS = ('who', 'job', 'questions', 'done', 'answer')
REQUIRED_SETUPS = ('empty', 'typical')


def load_config(app):
    path = app / 'surface-review.toml'
    if not path.exists():
        raise SystemExit(f'No surface-review.toml in {app}: run /surface-review-init first.')
    return tomllib.loads(path.read_text(encoding='utf-8'))


def text(path):
    """A file's text with line endings normalised: a Windows checkout and a Linux CI checkout must
    fingerprint the same bytes."""
    return path.read_bytes().decode('utf-8').replace('\r\n', '\n')


def fingerprint(app, templates):
    digest = hashlib.sha256()
    for rel in sorted(templates):
        digest.update(rel.encode('utf-8') + b'\0' + text(app / rel).encode('utf-8') + b'\0')
    return digest.hexdigest()[:16]


def glob_all(app, patterns):
    """Repo-relative POSIX paths matching any pattern (`**` recursive)."""
    found = set()
    for pattern in patterns:
        for path in app.glob(pattern):
            if path.is_file():
                found.add(path.relative_to(app).as_posix())
    return found


def page_templates(app, config):
    marker = config.get('page_marker', '{% extends')
    return {rel for rel in glob_all(app, config['page_templates']) if marker in text(app / rel)}


def read_record(path):
    """A record is markdown with a TOML block between `+++` lines at the top."""
    raw = text(path)
    if not raw.startswith('+++\n'):
        raise ValueError('it does not open with a +++ TOML block')
    end = raw.find('\n+++', 4)
    if end < 0:
        raise ValueError('its +++ TOML block is not closed')
    return tomllib.loads(raw[4:end])


def read_unregistered(path):
    entries = {}
    if path.exists():
        for line in text(path).splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                rel, _, digest = line.partition(' ')
                entries[rel] = digest.strip()
    return entries


def at_base(app, base, rel):
    """The file's text at `base`, or None where it did not exist there."""
    result = subprocess.run(['git', 'show', f'{base}:{rel}'], cwd=app, capture_output=True)
    return result.stdout.decode('utf-8').replace('\r\n', '\n') if result.returncode == 0 else None


def check_registry(app, screens):
    problems = []
    seen = set()
    for i, screen in enumerate(screens):
        slug = screen.get('slug') or f'entry {i + 1}'
        if slug in seen:
            problems.append(f'{slug}: registered twice.')
        seen.add(slug)
        for key in ('slug', 'templates', 'setups', *GOAL_KEYS):
            if not screen.get(key):
                problems.append(f'{slug}: the registry entry has no `{key}` (standard §1: write the goal first).')
        for rel in screen.get('templates', []):
            if not (app / rel).is_file():
                problems.append(f'{slug}: template {rel} does not exist.')
        missing = [s for s in REQUIRED_SETUPS if s not in screen.get('setups', [])]
        if missing:
            problems.append(f'{slug}: needs the setups {", ".join(missing)} (SR13).')
    return problems


def check_pages(app, config, screens, unregistered):
    problems = []
    registered = {rel for s in screens for rel in s.get('templates', [])}
    pages = page_templates(app, config)
    for rel in sorted(pages - registered - set(unregistered)):
        problems.append(f'{rel} is a new screen: register it in {config["registry"]} with its goal, '
                        f'seed its setups, and review it (SR5).')
    for rel, digest in sorted(unregistered.items()):
        if rel in registered:
            problems.append(f'{rel} is registered now: remove it from {config["unregistered"]}.')
        elif rel not in pages:
            problems.append(f'{rel} is no longer a page template: remove it from {config["unregistered"]}.')
        elif fingerprint(app, [rel]) != digest:
            problems.append(f'{rel} changed but is not registered: register it on this touch, with its '
                            f'goal and a review (SR18), and remove it from {config["unregistered"]}.')
    return problems


def check_finding(slug, finding):
    problems = []
    ident = f'{slug} finding {finding.get("id", "?")}'
    severity, outcome = finding.get('severity'), finding.get('outcome')
    if severity not in SEVERITIES:
        problems.append(f'{ident}: severity must be one of {", ".join(SEVERITIES)} (SR9).')
    if outcome not in OUTCOMES:
        problems.append(f'{ident}: has no outcome; end it as {", ".join(OUTCOMES)} (SR12).')
    if outcome == 'waived' and severity != 'minor':
        problems.append(f'{ident}: only a minor finding may be waived; fix it or make it Ben\'s call (SR12a).')
    if outcome in ('waived', 'ben') and not finding.get('reason'):
        problems.append(f'{ident}: a {outcome} finding needs its reason.')
    return problems


def check_records(app, config, screens):
    problems, notes = [], []
    records = app / config['records']
    for screen in screens:
        slug = screen.get('slug')
        if not slug or not screen.get('templates'):
            continue
        path = records / f'{slug}.md'
        if not path.exists():
            problems.append(f'{slug}: no review record at {path.relative_to(app).as_posix()}.')
            continue
        try:
            record = read_record(path)
        except (ValueError, tomllib.TOMLDecodeError) as e:
            problems.append(f'{slug}: its record cannot be read: {e}.')
            continue
        entries = record.get('entry', [])
        if not any(e.get('kind') == 'review' for e in entries):
            problems.append(f'{slug}: its record holds no review; a screen registers with one.')
            continue
        latest = entries[-1]
        current = fingerprint(app, screen['templates'])
        if latest.get('fingerprint') != current:
            problems.append(f'{slug}: changed since its last review (fingerprint {current}, record has '
                            f'{latest.get("fingerprint")}). Review it, or add an n/a entry with the reason.')
        if latest.get('kind') == 'na':
            if not latest.get('reason'):
                problems.append(f'{slug}: an n/a entry needs its reason.')
            else:
                notes.append(f'{slug}: n/a - {latest["reason"]}')
        elif latest.get('kind') != 'review':
            problems.append(f'{slug}: an entry\'s kind must be review or na.')
        for entry in entries:
            for finding in entry.get('finding', []):
                problems.extend(check_finding(slug, finding))
    return problems, notes


def check_shrink_only(app, config, base, unregistered):
    problems = []
    before = at_base(app, base, config['unregistered'])
    if before is not None:
        old = {line.split(' ')[0] for line in before.splitlines() if line.strip() and not line.startswith('#')}
        for rel in sorted(set(unregistered) - old):
            problems.append(f'{rel} was added to {config["unregistered"]}: that list only shrinks; '
                            f'register the screen instead (SR18).')
    lint_path = app / config['lint_baseline']
    before = at_base(app, base, config['lint_baseline'])
    if before is not None and lint_path.exists():
        grown = sorted(set(json.loads(text(lint_path))) - set(json.loads(before)))
        for key in grown:
            problems.append(f'lint baseline grew: {key}. Fix the failure; the baseline only shrinks (SR17).')
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--app', default='.', help='the app repo root (holds surface-review.toml)')
    parser.add_argument('--base', help='the ref being landed onto; enables the shrink-only checks')
    parser.add_argument('--fingerprint', metavar='SLUG', help='print a registered screen\'s fingerprint')
    parser.add_argument('--init-unregistered', action='store_true',
                        help='write every unregistered page template to the list (bootstrap only)')
    args = parser.parse_args(argv)
    app = Path(args.app).resolve()
    config = load_config(app)
    screens = tomllib.loads(text(app / config['registry'])).get('screen', [])

    if args.fingerprint:
        match = [s for s in screens if s.get('slug') == args.fingerprint]
        if not match:
            raise SystemExit(f'{args.fingerprint} is not registered.')
        print(fingerprint(app, match[0]['templates']))
        return 0
    unregistered_path = app / config['unregistered']
    if args.init_unregistered:
        if unregistered_path.exists():
            raise SystemExit(f'{unregistered_path} exists: it may only shrink, never be rebuilt.')
        registered = {rel for s in screens for rel in s.get('templates', [])}
        lines = [f'{rel} {fingerprint(app, [rel])}' for rel in sorted(page_templates(app, config) - registered)]
        unregistered_path.parent.mkdir(parents=True, exist_ok=True)
        unregistered_path.write_text(
            '# Page templates not yet in the screen registry, with their fingerprint. SHRINK-ONLY:\n'
            '# a screen leaves this list when a change first touches it (register it then).\n'
            + '\n'.join(lines) + '\n', encoding='utf-8')
        print(f'{len(lines)} unregistered page templates written to {unregistered_path}.')
        return 0

    unregistered = read_unregistered(unregistered_path)
    problems = check_registry(app, screens)
    problems += check_pages(app, config, screens, unregistered)
    record_problems, notes = check_records(app, config, screens)
    problems += record_problems
    if args.base:
        problems += check_shrink_only(app, config, args.base, unregistered)
    for note in notes:
        print(f'  {note}')
    if problems:
        print(f'Surface review gate: {len(problems)} problem(s).')
        for problem in problems:
            print(f'  - {problem}')
        print('The method: the surface-review skill in innoveta-method.')
        return 1
    shrink = '' if args.base else ' (shrink-only checks skipped: no --base)'
    print(f'Surface review gate OK: {len(screens)} registered screen(s), {len(unregistered)} still '
          f'unregistered{shrink}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
