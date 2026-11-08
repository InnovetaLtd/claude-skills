"""Watch mode for the walkthrough skill: record each check as step pictures, then build the checklist page.

    python walkthrough_watch.py record plan.json --out <dir> [--channel msedge|chromium]
    python walkthrough_watch.py page walk.json --out page.html [--manifest <dir>/manifest.json] [--assets urls.json]

**Why (Ben, 2026-11-07).** A walkthrough started from a phone over Remote Control cannot reach the
walkthrough server on localhost. So Claude walks each check itself in a real browser, takes a picture at
every step that matters, and the checklist artifact shows them in order. Ben watches and gives feedback in
chat. A step the browser cannot complete is itself a finding: the picture of where it stopped goes in the
card, captioned with the reason, and recording moves on to the next check.

`record` reads a plan (what Claude decided to do on each check):

    {"base_url": "http://127.0.0.1:8051", "viewport": "desktop",
     "theme_init": "try { localStorage.setItem('egb-theme', 'light') } catch (e) {}",
     "checks": [{"n": 3, "viewport": "phone", "steps": [
         {"goto": "/purchasing/po/12/"},
         {"shot": "The order before the amend"},
         {"click": "text=Edit"}, {"fill": ["#id_qty", "4"]}, {"select": ["#id_term", "30 days"]},
         {"press": ["#id_qty", "Enter"]}, {"wait": 500},
         {"shot": "Saved: one revision, the quantity now 4", "full_page": true, "selector": "main"}]}]}

and writes `<out>/c03-1.jpg …` plus `<out>/manifest.json` (`{"checks": [{"n", "shots": [{"file", "caption",
"page", "stopped"}]}]}`). Sign-in is the server's job (the app's dev-user setting), never the browser's.

`page` fills `templates/walkthrough-checklist.html` from `walk.json` (title, date, range, mode, server,
finding0, checks: n · title · ids · shapes · where · see · desk_only), takes each check's shots from the
manifest, and swaps every picture's file name for its uploaded URL from `--assets` (`{"c03-1.jpg": url}`).
Stdlib only; `record` also needs Playwright (`pip install playwright`, and `playwright install chromium`
where Edge is not installed).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / 'templates' / 'walkthrough-checklist.html'
VIEWPORTS = {'desktop': {'width': 1280, 'height': 860}, 'phone': {'width': 375, 'height': 812}}


def record(plan, out, channel):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('record needs Playwright: pip install playwright (and `playwright install chromium` without Edge)')
    out.mkdir(parents=True, exist_ok=True)
    base = plan['base_url'].rstrip('/')
    manifest = {'checks': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
        for check in plan['checks']:
            n = check['n']
            size = check.get('viewport') or plan.get('viewport') or 'desktop'
            phone = size == 'phone'
            context = browser.new_context(viewport=VIEWPORTS[size], is_mobile=phone, has_touch=phone,
                                          device_scale_factor=2 if phone else 1)
            if plan.get('theme_init'):
                context.add_init_script(plan['theme_init'])
            page = context.new_page()
            page.set_default_timeout(check.get('timeout_ms') or 10000)
            shots = []

            def shoot(caption, step, stopped=False):
                name = f'c{n:02d}-{len(shots) + 1}.jpg'
                target = page.locator(step['selector']).first if step.get('selector') else page
                opts = {'path': str(out / name), 'type': 'jpeg', 'quality': 80}
                if not step.get('selector'):
                    opts['full_page'] = bool(step.get('full_page'))
                target.screenshot(**opts)
                shots.append({'file': name, 'caption': caption, 'page': page.url, 'stopped': stopped})

            for i, step in enumerate(check['steps'], 1):
                try:
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
                    if 'shot' in step:
                        shoot(step['shot'], step)
                except Exception as exc:  # the browser could not do it: that IS the finding
                    reason = str(exc).splitlines()[0][:200]
                    shoot(f'Stopped at step {i} ({_describe(step)}): {reason}', {}, stopped=True)
                    break
            manifest['checks'].append({'n': n, 'shots': shots})
            context.close()
        browser.close()
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    stopped = [c['n'] for c in manifest['checks'] if any(s['stopped'] for s in c['shots'])]
    print(f'recorded {sum(len(c["shots"]) for c in manifest["checks"])} pictures for '
          f'{len(manifest["checks"])} checks into {out}' + (f'; STOPPED on checks {stopped}' if stopped else ''))


def _describe(step):
    for verb in ('goto', 'click', 'fill', 'select', 'press', 'wait'):
        if verb in step:
            value = step[verb]
            return f'{verb} {value[0] if isinstance(value, list) else value}'
    return 'shot'


def build_page(walk, out, manifest=None, assets=None):
    shots = {c['n']: c['shots'] for c in (manifest or {}).get('checks', [])}
    for check in walk['checks']:
        if check['n'] in shots:
            check['shots'] = shots[check['n']]
        for shot in check.get('shots', []):
            shot['url'] = (assets or {}).get(shot['file']) or shot.get('url')
    payload = json.dumps(walk, ensure_ascii=False).replace('</', '<\\/')
    title = walk.get('title') or 'Walkthrough'
    html = TEMPLATE.read_text(encoding='utf-8')
    html = html.replace('__WALK_TITLE__', title.replace('&', '&amp;').replace('<', '&lt;'), 1)
    html = html.replace('__WALK_DATA__', payload, 1)
    out.write_text(html, encoding='utf-8')
    missing = [s['file'] for c in walk['checks'] for s in c.get('shots', []) if not s.get('url')]
    print(f'wrote {out}' + (f'; {len(missing)} pictures not uploaded yet' if missing else ''))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('record')
    r.add_argument('plan', type=Path)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--channel', default='msedge' if sys.platform == 'win32' else None)
    p = sub.add_parser('page')
    p.add_argument('walk', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--assets', type=Path)
    args = ap.parse_args(argv)
    load = lambda path: json.loads(path.read_text(encoding='utf-8')) if path else None
    if args.cmd == 'record':
        record(load(args.plan), args.out, args.channel)
    else:
        build_page(load(args.walk), args.out, load(args.manifest), load(args.assets))


if __name__ == '__main__':
    main()
