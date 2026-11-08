#!/usr/bin/env python3
"""The surface review's RECORDER: walk each screen's flows in a real browser and keep a picture of every step.

    python surface_record.py record --app <repo root> (--screens a,b | --changed-since REF | --all)
                             --out <dir> [--plan plan.json] [--stills] [--channel msedge|chromium]
    python surface_record.py mark --after <dir> [--before <dir>]
    python surface_record.py page --walk walk.json --after <dir>/manifest.json
                             [--before <dir>/manifest.json] [--assets urls.json] --out page.html

**One engine, three readers (Ben, 2026-11-08).** The same recorded walk serves the build (a lane
records its scenarios and checks each picture against the scope's words before it claims done), the
independent reviewer (who judges the pictures as well as the page), and Ben's walkthrough (who
eyeballs the lot, with before and after side by side, from his phone if need be). It prepares, seeds
and serves exactly as the layout lint does, from the app's `surface-review.toml`, by the lint's own
functions: there is no second copy of how to stand the app up.

**A flow** is a scenario registered on its screen (`[[screen.flow]]` in the registry): a `setup`, the
`steps` a user takes, and what they should SEE (`sees`, in the scope's words). The walk STARTS on the
setup's seeded address, so a flow never hard-codes a record's id. Steps (one verb each, plus an
optional `shot` caption, `full_page` and `selector` on any step):

    {goto = "/path/"}  {click = "a:has-text('Open the draft')"}  {fill = ["#id_qty", "4"]}
    {select = ["#id_term", "30 days"]}  {press = ["#id_qty", "Enter"]}  {wait = 500}  {shot = "caption"}

Flows on one screen run in registry order on ONE seeded world: a flow that saves something should
have a setup of its own. `--plan` adds one-off walks in the same shape plus `screen` (a walkthrough's
checks on screens with no flow yet); `--stills` adds a desk and a phone picture of each selected
screen's `typical` setup that no flow already covers.

**A setup the app cannot seed is left out, not fatal** (on a base, it is a scenario the change adds:
the page marks its walk *new*). **A step the browser cannot do is a finding, not a crash**: the walk stops, its last picture shows
where, captioned with the reason, and the next walk starts (exit 1 names every stopped walk).
`<out>/manifest.json` lists every walk: `{key, screen, name, scenario, sees, viewport, setup, shots:
[{file, caption, page, stopped, sha256}]}`.

`page` fills `templates/walkthrough-checklist.html`: each check in `walk.json` names the walks it
shows (`walks: ["screen/flow"]`). With `--before` (the same walks recorded on the base, e.g. the live
SHA in a worktree: `record --app <base worktree> --same-as <after>/manifest.json --label before`, so it
walks exactly what the after run walked and its files never share a name), each picture is paired with its before; byte-identical pictures say *no visible
change* instead. `mark` (Pillow) finds what changed on both, rows aligned like a text diff so an
insertion does not light up the page below it; the page draws those boxes as a layer Ben can switch off.
It also writes the JPEG each picture is uploaded as (the recorder keeps lossless PNG for the diff). `--assets` swaps file names for the artifact's uploaded URLs. `record` needs
Playwright; `page` is stdlib only.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import surface_lint as lint
from check_surface_reviews import STEP_VERBS

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / 'templates' / 'walkthrough-checklist.html'


def walks_for(screens, plan, stills):
    """Every walk to record, in order: registered flows, then the plan's, then stills."""
    walks = [{**flow, 'screen': s['slug']} for s in screens for flow in s.get('flow', [])]
    walks += [dict(item) for item in plan or []]
    if stills:
        covered = {(w['screen'], w['setup']) for w in walks}
        for s in screens:
            if 'typical' in s['setups'] and (s['slug'], 'typical') not in covered:
                for viewport in ('desk', 'phone'):
                    walks.append({'screen': s['slug'], 'setup': 'typical', 'name': f'typical-{viewport}',
                                  'viewport': viewport, 'sees': s.get('job', ''),
                                  'steps': [{'shot': f'{s.get("title") or s["slug"]}, {viewport}',
                                             'full_page': True}]})
    for w in walks:
        w.setdefault('viewport', 'desk')
        w['key'] = f'{w["screen"]}/{w["name"]}'
    return walks


def act(page, step, base):
    """Do the step's one verb (a shot-only step does nothing here)."""
    if 'goto' in step:
        page.goto(base + step['goto'], wait_until='networkidle')
    elif 'click' in step:
        page.locator(step['click']).first.click()
        page.wait_for_load_state('networkidle')
    elif 'fill' in step:
        page.locator(step['fill'][0]).first.fill(step['fill'][1])
    elif 'select' in step:
        page.locator(step['select'][0]).first.select_option(label=step['select'][1])
    elif 'press' in step:
        page.locator(step['press'][0]).first.press(step['press'][1])
        page.wait_for_load_state('networkidle')
    elif 'wait' in step:
        page.wait_for_timeout(int(step['wait']))


def verb_text(step):
    for verb in STEP_VERBS:
        if verb in step and verb != 'shot':
            value = step[verb]
            return f'{verb} {value[0] if isinstance(value, list) else value}'
    return 'shot'


def record_walks(walks, urls, base, cfg, channel, out, theme, label=''):
    from playwright.sync_api import sync_playwright
    manifest = []
    theme_init = cfg['lint'].get('theme_init')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel) if channel != 'chromium' else pw.chromium.launch()
        for i, walk in enumerate(walks, 1):
            phone = walk['viewport'] == 'phone'
            width, height = lint.WIDTHS[walk['viewport']]
            context = browser.new_context(viewport={'width': width, 'height': height},
                                          device_scale_factor=2 if phone else 1, **lint.DEVICE[walk['viewport']])
            if theme_init:
                context.add_init_script(lint.fill(theme_init, theme=theme))
            page = context.new_page()
            page.set_default_timeout(walk.get('timeout_ms') or 10000)
            shots = []

            def shoot(caption, step, stopped=False):
                name = f'{label + "-" if label else ""}w{i:03d}-{len(shots) + 1}.png'
                opts = {'path': str(out / name), 'type': 'png'}
                if step.get('selector'):
                    page.locator(step['selector']).first.screenshot(**opts)
                else:
                    page.screenshot(full_page=bool(step.get('full_page')), **opts)
                shots.append({'file': name, 'caption': caption, 'page': page.url, 'stopped': stopped,
                              'sha256': hashlib.sha256((out / name).read_bytes()).hexdigest()})

            try:
                page.goto(base + urls[(walk['screen'], walk['setup'])], wait_until='networkidle')
                for n, step in enumerate(walk.get('steps', []), 1):
                    try:
                        act(page, step, base)
                        if 'shot' in step:
                            shoot(step['shot'], step)
                    except Exception as exc:  # the browser could not do it: that IS the finding
                        shoot(f'Stopped at step {n} ({verb_text(step)}): {str(exc).splitlines()[0][:200]}',
                              {}, stopped=True)
                        break
            except Exception as exc:
                shoot(f'Stopped opening the {walk["setup"]} setup: {str(exc).splitlines()[0][:200]}', {},
                      stopped=True)
            manifest.append({k: walk.get(k) for k in ('key', 'screen', 'name', 'scenario', 'sees',
                                                        'viewport', 'setup', 'steps')} | {'shots': shots})
            context.close()
        browser.close()
    return manifest


def select(app, cfg, screens, opts):
    if opts.screens:
        wanted = set(opts.screens.split(','))
        missing = wanted - {s['slug'] for s in screens}
        if missing:
            sys.exit(f'not registered: {", ".join(sorted(missing))}')
        return [s for s in screens if s['slug'] in wanted], 'named screens'
    if opts.all:
        return screens, 'all registered screens'
    if opts.changed_since:
        return lint.select_screens(app, cfg, screens, opts.changed_since)
    return [], 'no screens named'


def seed_all(cfg, app, env, subs, data_dir, pairs):
    """({(screen, setup): url}, {(screen, setup): why not}). One batch when the app has one; if it
    fails, setup by setup, so a setup the base does not have yet (recording BEFORE a change that adds
    it) leaves that walk out as NEW instead of failing the run."""
    if cfg['lint'].get('seed_batch'):
        try:
            return lint.seed_batch(cfg, app, env, subs, data_dir, pairs), {}
        except SystemExit:
            pass
    urls, missing = {}, {}
    for screen, setup in pairs:
        what = f'seed {screen} {setup}'
        try:
            printed = lint.run_command(cfg['lint']['seed'], app, env, {**subs, 'screen': screen, 'setup': setup}, what)
            urls[(screen, setup)] = lint.seeded_url(printed, what)
        except SystemExit as exc:
            missing[(screen, setup)] = str(exc).splitlines()[0][:200]
    return urls, missing


def record(opts):
    app = opts.app.resolve()
    cfg, screens = lint.load_config(app)
    if opts.same_as:
        walks = json.loads(opts.same_as.read_text(encoding='utf-8'))['walks']
        why = f'the walks of {opts.same_as}'
    else:
        selected, why = select(app, cfg, screens, opts)
        plan = json.loads(opts.plan.read_text(encoding='utf-8')) if opts.plan else []
        walks = walks_for(selected, plan, opts.stills)
    if not walks:
        print(f'surface record: nothing to walk ({why}; no flows, no plan, no stills).')
        return 0
    print(f'surface record: {len(walks)} walk(s) on {len({w["screen"] for w in walks})} screen(s) - {why}')
    opts.out.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix='surface-record-'))
    port = lint.pick_port(opts.port)
    subs = {'python': sys.executable, 'data_dir': data_dir, 'port': port}
    env = lint.lint_env(cfg, subs)
    try:
        lint.run_command(cfg['lint']['prepare'], app, env, subs, 'prepare')
        pairs = list(dict.fromkeys((w['screen'], w['setup']) for w in walks))
        urls, missing = seed_all(cfg, app, env, subs, data_dir, pairs)
        for (screen, setup), why_not in missing.items():
            print(f'- not seeded, left out as new: {screen} {setup} ({why_not})')
        walks = [w for w in walks if (w['screen'], w['setup']) in urls]
        serve_cmd = [lint.fill(part, **subs) for part in cfg['lint']['serve']]
        with lint.Server(serve_cmd, app, env, port, data_dir / 'serve.log') as server:
            manifest = record_walks(walks, urls, server.base, cfg, opts.channel, opts.out, opts.theme, opts.label)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    (opts.out / 'manifest.json').write_text(json.dumps({'walks': manifest}, indent=1), encoding='utf-8')
    stopped = [w['key'] for w in manifest if any(s['stopped'] for s in w['shots'])]
    print(f'recorded {sum(len(w["shots"]) for w in manifest)} picture(s) into {opts.out}'
          + (f'; STOPPED: {", ".join(stopped)}' if stopped else ''))
    return 1 if stopped else 0


# ---------------------------------------------------------------------------------------------
# mark: find what visibly changed, on the after AND the before
# ---------------------------------------------------------------------------------------------
#
# A plain pixel diff lights up everything below an insertion (the page shifts down). So the rows are
# aligned first, the way a text diff aligns lines (difflib, on each row's colours coarsened so the
# browser's text-smoothing noise does not split a row; colour, not grey, so a red band and a teal band of
# the same lightness never pass for each other, which is also why the recorder keeps PNG: a
# JPEG re-encodes a shifted block differently). A band only the after has was ADDED, a band only the
# before has was REMOVED, and a band on both is compared row against row, counting only a pixel that
# moved by more than NOISE (two runs of the same page differ by up to ~32 grey levels: measured on
# Build Manager's acknowledgement, 2026-11-08). Specks under MIN_AREA go; nearby boxes merge.
# The boxes are kept as COORDINATES, never drawn into the picture: the page lays them over it as a
# layer Ben can switch off to see the true screen (Ben, 2026-11-08).

NOISE = 64                    # grey levels: a pixel that moved less than this is rendering noise
KEY_SHIFT = 5                 # alignment key: each colour channel >> 5 (8 levels)
MIN_AREA = 24                 # px: a box smaller than this is a speck, not a change
MERGE_GAP = 12                # px: boxes this close are one change


def _rows(img):
    """The picture's rows as grey bytes."""
    grey = img.convert('L')
    raw, w = grey.tobytes(), grey.width
    return [raw[y * w:(y + 1) * w] for y in range(grey.height)]


def _keys(img):
    """Each row's alignment key: its colours, coarsened."""
    rgb = img.convert('RGB')
    raw, w = rgb.tobytes(), rgb.width * 3
    return [bytes(v >> KEY_SHIFT for v in raw[y * w:(y + 1) * w]) for y in range(rgb.height)]


def _differs(row, other):
    """(first, last) column where the rows differ by more than NOISE; against no other row, where
    the row differs from its own leftmost pixel (the content of an added or removed band)."""
    if other is None:
        bg = row[0]
        cols = [x for x in range(len(row)) if abs(row[x] - bg) > NOISE]
    else:
        cols = [x for x in range(min(len(row), len(other))) if abs(row[x] - other[x]) > NOISE]
    return (cols[0], cols[-1]) if cols else None


def _boxes(rows, y0, others=None):
    """Boxes over the rows that differ, one per run of differing rows."""
    boxes, run = [], None
    for n, row in enumerate(rows):
        hit = _differs(row, others[n] if others is not None else None)
        if hit:
            run = [min(run[0], hit[0]), run[1], max(run[2], hit[1]), y0 + n] if run else [hit[0], y0 + n, hit[1], y0 + n]
        elif run:
            boxes.append(tuple(run))
            run = None
    if run:
        boxes.append(tuple(run))
    return boxes


def _paired(rows_a, ja, rows_b, ib):
    """A band both pictures have: pair its rows top-aligned or bottom-aligned, whichever differs less,
    and treat the rows left over on the longer side as added or removed."""
    h = min(len(rows_a), len(rows_b))
    best = None
    for da, db in {(0, 0), (len(rows_a) - h, len(rows_b) - h)}:
        on_a = _boxes(rows_a[da:da + h], ja + da, rows_b[db:db + h])
        on_b = _boxes(rows_b[db:db + h], ib + db, rows_a[da:da + h])
        area = sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in on_a)
        if best is None or area < best[0]:
            extra_a = _boxes(rows_a[:da], ja) + _boxes(rows_a[da + h:], ja + da + h)
            extra_b = _boxes(rows_b[:db], ib) + _boxes(rows_b[db + h:], ib + db + h)
            best = (area, on_a + extra_a, on_b + extra_b)
    return best[1], best[2]


def _merge(boxes):
    merged = []
    for box in sorted((b for b in boxes if (b[2] - b[0] + 1) * (b[3] - b[1] + 1) >= MIN_AREA), key=lambda b: b[1]):
        if merged and box[1] - merged[-1][3] <= MERGE_GAP:
            last = merged[-1]
            merged[-1] = (min(last[0], box[0]), last[1], max(last[2], box[2]), max(last[3], box[3]))
        else:
            merged.append(box)
    return merged


def changed_boxes(after_img, before_img):
    """([boxes on the after], [boxes on the before]), each box (x0, y0, x1, y1) in pixels."""
    import difflib
    if after_img.width != before_img.width:
        return ([(0, 0, after_img.width - 1, after_img.height - 1)],
                [(0, 0, before_img.width - 1, before_img.height - 1)])
    rows_a, rows_b = _rows(after_img), _rows(before_img)
    keys_a, keys_b = _keys(after_img), _keys(before_img)
    on_after, on_before = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, keys_b, keys_a, autojunk=False).get_opcodes():
        if op == 'replace':
            a, b = _paired(rows_a[j1:j2], j1, rows_b[i1:i2], i1)
            on_after += a
            on_before += b
        elif op == 'insert':
            on_after += _boxes(rows_a[j1:j2], j1)
        elif op == 'delete':
            on_before += _boxes(rows_b[i1:i2], i1)
    return _merge(on_after), _merge(on_before)


def _as_share(boxes, img):
    """Boxes as fractions of the picture, so the page can lay them over it at any width."""
    w, h = img.width, img.height
    return [[round(x0 / w, 5), round(y0 / h, 5), round((x1 + 1) / w, 5), round((y1 + 1) / h, 5)]
            for x0, y0, x1, y1 in boxes]


def mark(after_dir, before_dir=None):
    """Find what changed and record it in the manifests: `boxes` (fractions of the picture) on each
    changed shot, after and before, and `changes` on the after. Also write each picture's `view`: the
    JPEG it is uploaded as (clean: the boxes are a layer on the page, never in the picture)."""
    from PIL import Image
    after = json.loads((after_dir / 'manifest.json').read_text(encoding='utf-8'))
    before = json.loads((before_dir / 'manifest.json').read_text(encoding='utf-8')) if before_dir else {'walks': []}
    before_walks = {w['key']: w for w in before['walks']}

    def view(folder, shot):
        if 'file' not in shot:
            return
        name = Path(shot['file']).stem + '.jpg'
        Image.open(folder / shot['file']).convert('RGB').save(folder / name, 'JPEG', quality=80)
        shot['view'] = name

    marked = 0
    for walk in after['walks']:
        then = before_walks.get(walk['key'], {}).get('shots', [])
        for n, shot in enumerate(walk['shots']):
            old = then[n] if n < len(then) else None
            if old and 'file' in shot and 'file' in old and old['sha256'] != shot['sha256']:
                new_img, old_img = Image.open(after_dir / shot['file']), Image.open(before_dir / old['file'])
                on_after, on_before = changed_boxes(new_img, old_img)
                shot['boxes'], old['boxes'] = _as_share(on_after, new_img), _as_share(on_before, old_img)
                shot['changes'] = max(len(on_after), len(on_before))
                marked += 1
            view(after_dir, shot)
            if old:
                view(before_dir, old)
    (after_dir / 'manifest.json').write_text(json.dumps(after, indent=1), encoding='utf-8')
    if before_dir:
        (before_dir / 'manifest.json').write_text(json.dumps(before, indent=1), encoding='utf-8')
    print(f'marked {marked} changed picture(s); upload the .jpg views')
    return 0


def build_page(walk, after, before=None, assets=None):
    """The checklist page: walk.json's checks, each with its walks' pictures (paired with BEFORE)."""
    assets = assets or {}
    after_walks = {w['key']: w for w in after.get('walks', [])}
    before_walks = {w['key']: w for w in (before or {}).get('walks', [])}
    for check in walk['checks']:
        shots = []
        for key in check.get('walks', []):
            got = after_walks.get(key)
            if not got:
                shots.append({'caption': f'{key}: not recorded', 'stopped': True})
                continue
            if got.get('sees'):
                check.setdefault('see', got['sees'])
            then = before_walks.get(key, {}).get('shots', [])
            for n, shot in enumerate(got['shots']):
                pair = dict(shot, url=assets.get(shot.get('view') or shot.get('file')))
                if key in before_walks:
                    old = then[n] if n < len(then) else None
                    pair['same'] = bool(old) and old['sha256'] == shot['sha256']
                    pair['before_url'] = (assets.get(old.get('view') or old['file'])
                                          if old and not pair['same'] else None)
                    pair['before_boxes'] = old.get('boxes', []) if old and not pair['same'] else []
                elif before is not None:
                    pair['new'] = True
                shots.append(pair)
        check['shots'] = shots + check.get('shots', [])
    payload = json.dumps(walk, ensure_ascii=False).replace('</', '<\\/')
    title = (walk.get('title') or 'Walkthrough').replace('&', '&amp;').replace('<', '&lt;')
    html = TEMPLATE.read_text(encoding='utf-8').replace('__WALK_TITLE__', title, 1)
    return html.replace('__WALK_DATA__', payload, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('record')
    r.add_argument('--app', required=True, type=Path)
    which = r.add_mutually_exclusive_group()
    which.add_argument('--screens', help='comma-separated registry slugs')
    which.add_argument('--changed-since', metavar='REF')
    which.add_argument('--all', action='store_true')
    which.add_argument('--same-as', type=Path, metavar='MANIFEST',
                       help="replay another run's walks (record BEFORE on the base with the AFTER run's walks)")
    r.add_argument('--plan', type=Path, help='one-off walks: a JSON list in the flow shape, plus `screen`')
    r.add_argument('--stills', action='store_true', help="a desk + phone picture of each screen's typical setup")
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--channel', default='msedge' if sys.platform == 'win32' else 'chromium')
    r.add_argument('--theme', default='light', choices=('light', 'dark'))
    r.add_argument('--port', type=int)
    r.add_argument('--label', default='', help='prefix for picture names (`before`), so two runs upload side by side')
    m = sub.add_parser('mark')
    m.add_argument('--after', type=Path, required=True, help='the after run folder')
    m.add_argument('--before', type=Path, help='the before run folder')
    p = sub.add_parser('page')
    p.add_argument('--walk', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--before', type=Path)
    p.add_argument('--assets', type=Path)
    p.add_argument('--out', type=Path, required=True)
    opts = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if opts.cmd == 'record':
        return record(opts)
    if opts.cmd == 'mark':
        return mark(opts.after, opts.before)
    load = lambda path: json.loads(path.read_text(encoding='utf-8')) if path else None
    opts.out.write_text(build_page(load(opts.walk), load(opts.after), load(opts.before), load(opts.assets)),
                        encoding='utf-8')
    print(f'wrote {opts.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
