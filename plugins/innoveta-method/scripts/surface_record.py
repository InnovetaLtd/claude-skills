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

Floating chrome pinned to the window (a scan button, a quick-action bubble) lands somewhere arbitrary in a
full-page picture, so the app names it in `surface-review.toml` (`[record] hide = [".fab"]`) and it is hidden
while recording; it is not hidden generically, since a flow may mean to show a dialog.

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
#: Text drawn the same way every run: grayscale, unhinted, no LCD colour fringes. Without these two runs
#: of the SAME page differ by up to ~32 grey levels on unchanged text (measured 2026-11-08), which the
#: before/after diff then reads as change.
RENDER_ARGS = ['--disable-lcd-text', '--font-render-hinting=none', '--disable-gpu']
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
        browser = pw.chromium.launch(args=RENDER_ARGS, **({} if channel == 'chromium' else {'channel': channel}))
        for i, walk in enumerate(walks, 1):
            phone = walk['viewport'] == 'phone'
            width, height = lint.WIDTHS[walk['viewport']]
            context = browser.new_context(viewport={'width': width, 'height': height},
                                          device_scale_factor=2 if phone else 1, **lint.DEVICE[walk['viewport']])
            if theme_init:
                context.add_init_script(lint.fill(theme_init, theme=theme))
            hide = cfg.get('record', {}).get('hide', [])
            if hide:
                css = ', '.join(hide) + ' { visibility: hidden !important; }'
                context.add_init_script(
                    "document.addEventListener('DOMContentLoaded', function () { var s = document.createElement('style');"
                    " s.textContent = " + json.dumps(css) + "; document.head.appendChild(s); });")
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
                                                        'viewport', 'setup', 'steps')}
                            | {'scale': 2 if phone else 1, 'shots': shots})
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
# aligned first, the way a text diff aligns lines (difflib on each row's exact pixels: the recorder
# keeps PNG and draws text the same way every run, RENDER_ARGS, so an unchanged row is byte-identical).
# A band only the after has was ADDED and a band only the before has was REMOVED. A band both have is
# paired at the vertical offset that differs least, and a pixel counts only when it moved by more than
# NOISE AND is content on that side (not page background): a box never marks empty space, and never
# sits a line off the text it means. Specks under MIN_AREA go; nearby boxes merge. The boxes are kept
# as COORDINATES, never drawn into the picture: the page lays them over it as a layer Ben can switch
# off to see the true screen (Ben, 2026-11-08). Checked by eye against Build Manager's order and
# acknowledgement pages before and after their surface reviews, 2026-11-08.

NOISE = 48                    # grey levels: smaller moves are anti-aliasing, not change
MIN_AREA = 24                 # px: a box smaller than this is a speck, not a change
MERGE_GAP = 12                # px: boxes this close (and overlapping side to side) are one change
SPLIT_GAP = 24                # px: content this far apart across a row is two changes, not one
MAX_SHIFT = 600               # px: the furthest a band's rows are searched for their partner
NUDGE = 2                     # px: a box that matches its partner moved by this much is a re-drawn edge
NUDGE_LEFT = 0.02             # share of a box's pixels that may still differ after the nudge
MOVE = 240                    # px: content found this far sideways, unchanged, MOVED (a dropped column
                              # moves the rest a long way: BM's acknowledgement totals moved 194 px)
MOVE_Y = 32                   # px: ...and this far up or down (a header above it now wraps one line less)
SOFTEN = 0.6                  # blur radius for those two checks: text that lands on a fraction of a pixel
                              # is re-drawn (BM's right-aligned quantity: 21 of 108 pixels differ, 0 once
                              # softened), while a 2 against a 1 still differs by 38 pixels
SMALL_PATCH = 2000            # px: a patch this small is searched on half-size copies (a quarter-size digit is mush)
CANDIDATES = 20               # best coarse spots confirmed at full size
# Every distance above is in CSS pixels. A phone picture is recorded at 2 device pixels per CSS pixel, so
# `changed_boxes` is told the picture's scale and _px() converts (areas by its square).
_SCALE = [1]


def _px(n, area=False):
    return int(n * _SCALE[0] * (_SCALE[0] if area else 1))


def _rows(img):
    """The picture's rows as exact RGB bytes (the alignment key)."""
    rgb = img.convert('RGB')
    raw, w = rgb.tobytes(), rgb.width * 3
    return [raw[y * w:(y + 1) * w] for y in range(rgb.height)]


def _over(img):
    """Pixels above NOISE, as a 0/255 mask."""
    return img.point(lambda v: 255 if v > NOISE else 0)


def _delta(a, b):
    """How far each pixel moved: the largest change in any colour channel (grey alone would let a red
    chip turn teal unseen: they are the same lightness)."""
    from PIL import ImageChops
    r, g, b_ = ImageChops.difference(a, b).split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b_)


def _ink(rgb):
    """Content on this picture: pixels that differ from their own row's background (its leftmost
    pixel, stretched across the row)."""
    edge = rgb.crop((0, 0, 1, rgb.height)).resize(rgb.size)
    return _over(_delta(rgb, edge))


def _runs(mask, y0):
    """Boxes (x0, y0, x1, y1) round the set pixels: one per run of rows, split where the run's content
    has a gap of SPLIT_GAP across it (new text and an untouched icon beside it stay two boxes)."""
    from PIL import Image
    raw, w = mask.tobytes(), mask.width
    spans, start = [], None
    for n in range(mask.height + 1):
        hit = n < mask.height and raw[n * w:(n + 1) * w].find(b'\xff') >= 0
        if hit and start is None:
            start = n
        elif not hit and start is not None:
            spans.append((start, n))
            start = None
    boxes = []
    for top, bottom in spans:
        band = mask.crop((0, top, w, bottom))
        cols = band.resize((w, 1), Image.BOX).tobytes()
        x = 0
        while x < w:
            if not cols[x]:
                x += 1
                continue
            left, gap = x, 0
            while x < w and gap < _px(SPLIT_GAP):
                gap = 0 if cols[x] else gap + 1
                x += 1
            box = band.crop((left, 0, x - gap, band.height)).getbbox()
            if box:
                boxes.append((left + box[0], y0 + top + box[1], left + box[2] - 1, y0 + top + box[3] - 1))
    return boxes


def _paired(ga, ja, la, gb, ib, lb):
    """A band both pictures have (after rows ja..ja+la, before rows ib..ib+lb): pair the shorter band
    with the stretch of the longer that differs least, box what differs on each side, and treat the
    longer side's leftover rows as added or removed."""
    from PIL import ImageChops
    a = ga.crop((0, ja, ga.width, ja + la))
    b = gb.crop((0, ib, gb.width, ib + lb))
    h = min(la, lb)
    best = None
    for off in range(0, min(abs(la - lb), MAX_SHIFT) + 1):
        da, db = (off, 0) if la > lb else (0, off)
        diff = _over(_delta(a.crop((0, da, a.width, da + h)), b.crop((0, db, b.width, db + h))))
        cost = diff.histogram()[255]
        if best is None or cost < best[0]:
            best = (cost, da, db, diff)
    _, da, db, diff = best
    pa, pb = a.crop((0, da, a.width, da + h)), b.crop((0, db, b.width, db + h))
    shift = (ib + db) - (ja + da)          # after row y is before row y + shift, in this band
    on_a = _kinds(_runs(ImageChops.multiply(diff, _ink(pa)), ja + da), ga, gb, {shift})
    on_b = _kinds(_runs(ImageChops.multiply(diff, _ink(pb)), ib + db), gb, ga, {-shift})
    for top, rest, base, side in ((a.crop((0, 0, a.width, da)), a.crop((0, da + h, a.width, la)), ja, on_a),
                                  (b.crop((0, 0, b.width, db)), b.crop((0, db + h, b.width, lb)), ib, on_b)):
        if top.height:
            side += [box + ('changed',) for box in _runs(_ink(top), base)]
        if rest.height:
            side += [box + ('changed',) for box in _runs(_ink(rest), base + (da if side is on_a else db) + h)]
    return on_a, on_b


def _found(patch, other, x0, y0, xs, allowed):
    """True when the patch appears in the other picture at row y0 (give or take NUDGE) and any of
    the column offsets `xs`."""
    for ny in range(-_px(NUDGE), _px(NUDGE) + 1):
        for nx in xs:
            ox, oy = x0 + nx, y0 + ny
            if ox < 0 or oy < 0 or ox + patch.width > other.width or oy + patch.height > other.height:
                continue
            twin = other.crop((ox, oy, ox + patch.width, oy + patch.height))
            if _over(_delta(patch, twin)).histogram()[255] <= allowed:
                return True
    return False


def _kind(box, side, other, dys):
    """What a differing patch IS. `same`: it matches the other picture nudged up to NUDGE px (a vector
    icon or a border landing on a fractional pixel is re-drawn, not changed: BM's dropdown arrow,
    2026-11-08). `moved`: it is there unchanged, slid up to MOVE px sideways (a resized column: BM's
    order-form quantities, 2026-11-08). Otherwise `changed`. `dys` map this picture's rows onto the
    other's."""
    x0, y0, x1, y1 = box
    # Cut from the softened WHOLE picture: softening a tight cut-out smears its edges against nothing,
    # and the box hugs the text, so those edges would never match (BM's moved £45.00, 2026-11-08).
    patch = _softened(side).crop((x0, y0, x1 + 1, y1 + 1))
    other = _softened(other)
    allowed = max(4, int(patch.width * patch.height * NUDGE_LEFT))
    if any(_found(patch, other, x0, y0 + dy, range(-_px(NUDGE), _px(NUDGE) + 1), allowed) for dy in dys):
        return 'same'
    return 'moved' if any(_moved(patch, other, x0, y0 + dy, allowed) for dy in dys) else 'changed'


# One derived copy per picture, cached against the picture ITSELF: an id() key is reused once a picture
# is freed, and handed the next picture a stale copy (a flaky test found it, 2026-11-08).
_CACHE = {'soft': [], 'small2': [], 'small4': []}


def _derived(kind, img, make):
    """The `kind` copy of a picture; the last two are kept (the diff alternates after and before)."""
    held = _CACHE[kind]
    for picture, copy in held:
        if picture is img:
            return copy
    copy = make(img)
    held[:] = (held + [(img, copy)])[-2:]
    return copy


def _soft(img):
    """Softened by SOFTEN CSS pixels (so twice as much on a phone picture: at 0.6 device px a moved word
    on BM's phone acknowledgement still differed in 192 pixels; at 1.2, none)."""
    from PIL import ImageFilter
    return img.filter(ImageFilter.GaussianBlur(SOFTEN * _SCALE[0]))


def _softened(img):
    """The softened copy of a whole picture, made once per picture."""
    return _derived('soft', img, _soft)


def _moved(patch, other, x0, y0, allowed):
    """True when the patch is in the other picture unchanged within MOVE px sideways and MOVE_Y px up
    or down. Searched coarse to fine: on reduced copies first (half size for a small patch, a quarter
    for a large one), then the CANDIDATES best spots are confirmed at full size (a small digit's single
    best coarse spot can be a near-blank one)."""
    scale = 2 if patch.width * patch.height <= _px(SMALL_PATCH, area=True) else 4
    small = _derived(f'small{scale}', other, lambda img: img.reduce(scale))
    # Both sides are softened (`_kind`), so a move by an odd number of pixels still ranks near the top
    # on the reduced copies; each candidate is then confirmed within +/- scale px at full size.
    tiny, found = patch.reduce(scale), []
    for sy in range((y0 - _px(MOVE_Y)) // scale, (y0 + _px(MOVE_Y)) // scale + 1):
        for sx in range((x0 - _px(MOVE)) // scale, (x0 + _px(MOVE)) // scale + 1):
            if sx < 0 or sy < 0 or sx + tiny.width > small.width or sy + tiny.height > small.height:
                continue
            crop = small.crop((sx, sy, sx + tiny.width, sy + tiny.height))
            found.append((_over(_delta(tiny, crop)).histogram()[255], sx * scale, sy * scale))
    # The best spots, spread out: twenty neighbours of one near-miss would crowd out the real one.
    chosen = []
    for _, ox, oy in sorted(found):
        if any(abs(ox - cx) <= 2 * scale and abs(oy - cy) <= 2 * scale for cx, cy in chosen):
            continue
        chosen.append((ox, oy))
        if _found(patch, other, ox, oy, range(-scale, scale + 1), allowed):
            return True
        if len(chosen) == CANDIDATES:
            break
    return False


def _kinds(boxes, side, other, dys):
    """The boxes that are not `same`, each with its kind appended."""
    out = []
    for box in boxes:
        kind = _kind(box, side, other, dys)
        if kind != 'same':
            out.append(box + (kind,))
    return out


def _merge(boxes):
    """Nearby boxes of the same kind become one; specks go."""
    merged = []
    for box in sorted((b for b in boxes if (b[2] - b[0] + 1) * (b[3] - b[1] + 1) >= _px(MIN_AREA, area=True)), key=lambda b: b[1]):
        near = [k for k, m in enumerate(merged) if m[4] == box[4] and box[1] - m[3] <= _px(MERGE_GAP)
                and box[0] <= m[2] + _px(SPLIT_GAP) and m[0] <= box[2] + _px(SPLIT_GAP)]
        if near:
            m = merged[near[-1]]
            merged[near[-1]] = (min(m[0], box[0]), min(m[1], box[1]), max(m[2], box[2]), max(m[3], box[3]), m[4])
        else:
            merged.append(box)
    return merged


def changed_boxes(after_img, before_img, scale=1):
    """([boxes on the after], [boxes on the before]), each box (x0, y0, x1, y1, kind) in pixels, kind
    `changed` or `moved`."""
    import difflib
    _SCALE[0] = scale
    if after_img.width != before_img.width:
        return ([(0, 0, after_img.width - 1, after_img.height - 1, 'changed')],
                [(0, 0, before_img.width - 1, before_img.height - 1, 'changed')])
    ga, gb = after_img.convert('RGB'), before_img.convert('RGB')
    on_after, on_before = [], []
    ops = difflib.SequenceMatcher(None, _rows(before_img), _rows(after_img), autojunk=False).get_opcodes()
    for n, (op, i1, i2, j1, j2) in enumerate(ops):
        # Where an added or removed band would sit in the other picture: the offset of the matched rows
        # just above it, or just below it (a lone blank row can match out of place, so try both).
        near = {o[1] - o[3] for o in (ops[n - 1] if n else None, ops[n + 1] if n + 1 < len(ops) else None)
                if o and o[0] == 'equal'} or {i1 - j1}
        if op == 'replace':
            a, b = _paired(ga, j1, j2 - j1, gb, i1, i2 - i1)
            on_after += a
            on_before += b
        elif op == 'insert':
            on_after += _kinds(_runs(_ink(ga.crop((0, j1, ga.width, j2))), j1), ga, gb, near)
        elif op == 'delete':
            on_before += _kinds(_runs(_ink(gb.crop((0, i1, gb.width, i2))), i1), gb, ga, {-d for d in near})
    return _merge(on_after), _merge(on_before)


def _as_share(boxes, img):
    """Boxes as fractions of the picture, so the page can lay them over it at any width; a moved box
    carries a fifth element, "moved"."""
    w, h = img.width, img.height
    return [[round(x0 / w, 5), round(y0 / h, 5), round((x1 + 1) / w, 5), round((y1 + 1) / h, 5)]
            + (['moved'] if kind == 'moved' else []) for x0, y0, x1, y1, kind in boxes]


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
                on_after, on_before = changed_boxes(new_img, old_img, walk.get('scale') or 1)
                shot['boxes'], old['boxes'] = _as_share(on_after, new_img), _as_share(on_before, old_img)
                shot['changes'] = max(sum(b[4] == 'changed' for b in on_after), sum(b[4] == 'changed' for b in on_before))
                shot['moved'] = max(sum(b[4] == 'moved' for b in on_after), sum(b[4] == 'moved' for b in on_before))
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
