#!/usr/bin/env python3
"""The surface review's RECORDER: walk each screen's flows in a real browser and keep a picture of every step.

    python surface_record.py record --app <repo root> (--screens a,b | --changed-since REF | --all)
                             --out <dir> [--plan plan.json] [--stills] [--channel msedge|chromium]
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
change* instead. `--assets` swaps file names for the artifact's uploaded URLs. `record` needs
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
                name = f'{label + "-" if label else ""}w{i:03d}-{len(shots) + 1}.jpg'
                opts = {'path': str(out / name), 'type': 'jpeg', 'quality': 80}
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
                pair = dict(shot, url=assets.get(shot['file']))
                if key in before_walks:
                    old = then[n] if n < len(then) else None
                    pair['same'] = bool(old) and old['sha256'] == shot['sha256']
                    pair['before_url'] = assets.get(old['file']) if old and not pair['same'] else None
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
    load = lambda path: json.loads(path.read_text(encoding='utf-8')) if path else None
    opts.out.write_text(build_page(load(opts.walk), load(opts.after), load(opts.before), load(opts.assets)),
                        encoding='utf-8')
    print(f'wrote {opts.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
