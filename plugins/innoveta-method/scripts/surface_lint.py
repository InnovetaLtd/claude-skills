"""Mechanical layout lint for registered web screens: the surface review's SR14-SR17 rules.

    python surface_lint.py --app <repo root> --all
    python surface_lint.py --app <repo root> --changed-since origin/master
    python surface_lint.py --app <repo root> --all --write-baseline
    python surface_lint.py --app <repo root> --all --channel chromium --json lint.json

What it does, in order:

1. Reads the app's `surface-review.toml` (at `--app`) and the screen registry it names.
2. Picks screens: every one (`--all`), or the ones a change since a git ref touches. A changed
   file that is a screen's own template selects that screen; a changed SHARED file (a `shared`
   glob that is not any screen's own template, and not some other page template) selects ALL
   screens, because a stylesheet or a base template moves every page at once (SR16).
3. Builds a throwaway world: a fresh temp data dir, the app's `prepare` command, one `seed` run
   per screen x setup (each prints `{"url": "/path"}`), and the app's `serve` command on a free
   port. The server is always killed at the end, children included.
4. Loads every URL at phone (375x812) and desk (1280x900), light and dark, and checks six rules:
       overflow  the page scrolls sideways
       wrap      a button label renders on more than one line
       tap       a tap target under 44 px tall (phone only)
       console   a console error, an uncaught page error, or an HTTP error status
       contrast  text under 4.5:1 (3:1 for large text) against its effective background
       fold      the screen's `answer` element is missing, hidden, or starts below the fold
5. Compares the failures with the app's baseline (SR17, shrink-only). A failure not in the
   baseline fails the run; so does a baseline entry, for a screen linted in this run, that no
   longer fails ("fixed: remove it", so the baseline can only shrink). `--write-baseline`
   records the current failures for the linted screens and keeps every other screen's entries.

Each failure has a STABLE key, `screen|setup|width|theme|rule|text`, which never carries a
pixel value or a database id: the measured value is printed beside it, not baked into it.

Everything app-specific comes from the toml; nothing here knows which app it is linting.
Needs Python 3.11+ (tomllib), the standard library and the `playwright` package. On Windows it drives the installed
Edge (`--channel msedge`, the default there); on Linux CI use `--channel chromium`, Playwright's
bundled browser (`playwright install chromium`).

The app's `[lint]` table (placeholders `{python}` `{data_dir}` `{port}` `{screen}` `{setup}`
are substituted in every string; nothing else in braces is touched):

    prepare = [...]          # command run once, in the app root, on the fresh data dir
    seed    = [...]          # command run per screen x setup; its stdout's last JSON line has "url"
    serve   = [...]          # command that serves the app on {port} until killed
    env     = {...}          # extra environment for all three (templated too)
    drop_env = [...]         # environment keys removed first (e.g. a production DB host)
    theme_init = "..."       # JS run before any page script; {theme} is light | dark
    button_selector = "..."  # what counts as a button for the `wrap` rule
    tap_selector = "..."     # what counts as a tap target for the `tap` rule
"""
import argparse
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

# The four page variants every URL is loaded in. Widths are named in failure keys, never measured.
WIDTHS = {'phone': (375, 812), 'desk': (1280, 900)}
THEMES = ('light', 'dark')
RULES = ('overflow', 'wrap', 'tap', 'console', 'contrast', 'fold')

# Ports the lint never serves on: the usual dev-server range, ports that are reserved on some
# Windows machines, and the range sibling dev sessions use. Anything already listening is skipped too.
AVOID_PORTS = set(range(8000, 8011)) | {8033, 8034, 8080} | set(range(8041, 8062))
PORT_RANGE = (8100, 8999)

KEY_TEXT_MAX = 40          # a key's identifying text is trimmed to this many characters
MIN_TAP_PX = 44            # SR14: tap targets at phone width
SETTLE_MS = 300            # after `load`: let late layout (fonts, scripts that reflow) settle


# ---------------------------------------------------------------------------------------------
# Configuration and screen selection
# ---------------------------------------------------------------------------------------------

def load_config(app):
    """The app's surface-review.toml plus its registry's screens, as plain dicts."""
    cfg_path = app / 'surface-review.toml'
    if not cfg_path.exists():
        sys.exit(f'No surface-review.toml in {app}.')
    with open(cfg_path, 'rb') as f:
        cfg = tomllib.load(f)
    with open(app / cfg['registry'], 'rb') as f:
        screens = tomllib.load(f).get('screen', [])
    for s in screens:
        s.setdefault('templates', [])
        s.setdefault('setups', [])
        s.setdefault('answer_by_setup', {})
    return cfg, screens


def glob_to_regex(pattern):
    """A path glob as a regex: `**/` spans any number of folders, `*` and `?` stay inside one."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith('**/', i):
            out.append('(?:.*/)?')
            i += 3
        elif pattern.startswith('**', i):
            out.append('.*')
            i += 2
        elif pattern[i] == '*':
            out.append('[^/]*')
            i += 1
        elif pattern[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(''.join(out) + r'\Z')


def matches_any(path, globs):
    return any(glob_to_regex(g).match(path) for g in globs)


def git_lines(app, *args):
    out = subprocess.run(['git', '-C', str(app), *args], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f'git {" ".join(args)} failed: {out.stderr.strip()}')
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def changed_files(app, ref):
    """Files changed on this branch since `ref`, plus anything uncommitted or untracked."""
    files = set(git_lines(app, 'diff', '--name-only', f'{ref}...HEAD'))
    files |= set(git_lines(app, 'diff', '--name-only', 'HEAD'))
    files |= set(git_lines(app, 'ls-files', '--others', '--exclude-standard'))
    return sorted(f.replace('\\', '/') for f in files)


def is_other_page(app, cfg, path):
    """True when `path` is a PAGE template (it matches `page_templates` and contains `page_marker`).
    An unregistered page changes only itself, so it is not shared. A deleted file reads as shared."""
    if not matches_any(path, cfg.get('page_templates', [])) or not cfg.get('page_marker'):
        return False
    try:
        return cfg['page_marker'] in (app / path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False


def select_screens(app, cfg, screens, ref):
    """(screens to lint, a line explaining why) for a change since `ref` (SR16)."""
    own = {t: s['slug'] for s in screens for t in s['templates']}
    picked, shared_hits, unregistered = set(), [], []
    for path in changed_files(app, ref):
        if path in own:
            picked.add(own[path])
        elif matches_any(path, cfg.get('shared', [])):
            if is_other_page(app, cfg, path):
                unregistered.append(path)
            else:
                shared_hits.append(path)
    if unregistered:
        print(f'note: changed page templates no screen registers (not linted): {", ".join(unregistered)}')
    if shared_hits:
        return screens, f'shared file(s) changed ({", ".join(shared_hits[:5])}'\
                        f'{", ..." if len(shared_hits) > 5 else ""}): every registered screen'
    return [s for s in screens if s['slug'] in picked], 'screens whose own templates changed'


# ---------------------------------------------------------------------------------------------
# The throwaway world: data dir, seeded URLs, a dev server on a free port
# ---------------------------------------------------------------------------------------------

def fill(value, **subs):
    """Substitute only the known `{name}` placeholders; leave every other brace alone (JS, JSON)."""
    for name, sub in subs.items():
        value = value.replace('{' + name + '}', str(sub))
    return value


def lint_env(cfg, subs):
    env = {k: v for k, v in os.environ.items() if k not in set(cfg['lint'].get('drop_env', []))}
    env.update({k: fill(v, **subs) for k, v in cfg['lint'].get('env', {}).items()})
    env['PYTHONUNBUFFERED'] = '1'
    return env


def run_command(template, app, env, subs, what):
    """Run a templated command in the app root; exit with its output on failure, else return stdout."""
    cmd = [fill(part, **subs) for part in template]
    out = subprocess.run(cmd, cwd=app, env=env, capture_output=True, text=True,
                         encoding='utf-8', errors='replace')
    if out.returncode != 0:
        sys.exit(f'{what} failed ({" ".join(cmd)}):\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}')
    return out.stdout


def seeded_url(stdout, what):
    """The `url` from the last JSON object line a seed command printed."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)['url']
            except (ValueError, KeyError):
                pass
    sys.exit(f'{what} printed no {{"url": ...}} line:\n{stdout[-1000:]}')


def port_is_free(port):
    """Free = nothing answers a connect on it, and we can bind it ourselves."""
    with socket.socket() as s:
        s.settimeout(0.2)
        if s.connect_ex(('127.0.0.1', port)) == 0:
            return False
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def pick_port(preferred=None):
    if preferred:
        if not port_is_free(preferred):
            sys.exit(f'--port {preferred} is in use.')
        return preferred
    candidates = [p for p in range(*PORT_RANGE) if p not in AVOID_PORTS]
    random.shuffle(candidates)       # two lints at once rarely collide on the first try
    for port in candidates[:200]:
        if port_is_free(port):
            return port
    sys.exit('No free port found in %d-%d.' % PORT_RANGE)


class Server:
    """The app's `serve` command in its own process group, killed with all its children on exit
    (a Windows venv python.exe is a launcher that starts the real interpreter as a child)."""

    def __init__(self, cmd, app, env, port, log_path):
        self.cmd, self.app, self.env, self.port, self.log_path = cmd, app, env, port, log_path
        self.proc = None
        self.base = f'http://127.0.0.1:{port}'

    def __enter__(self):
        self.log = open(self.log_path, 'w', encoding='utf-8')
        kwargs = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                  else {'start_new_session': True})
        self.proc = subprocess.Popen(self.cmd, cwd=self.app, env=self.env, stdout=self.log,
                                     stderr=subprocess.STDOUT, **kwargs)
        deadline = time.time() + 90
        while time.time() < deadline:
            if self.proc.poll() is not None:
                break
            if self._answers():
                return self
            time.sleep(0.5)
        self.__exit__()
        sys.exit(f'The dev server did not come up on {self.base}; its log:\n'
                 + Path(self.log_path).read_text(encoding='utf-8', errors='replace')[-2000:])

    def _answers(self):
        """Any HTTP response at all (a 404 or a 401 included) means the server is up."""
        try:
            with urllib.request.urlopen(self.base + '/', timeout=3):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            return False

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(self.proc.pid)],
                               capture_output=True)
            else:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()


# ---------------------------------------------------------------------------------------------
# The in-page measurements: one evaluate per page load
# ---------------------------------------------------------------------------------------------

# Returns {overflow, wrap, tap, contrast} measurements for the page as loaded at the top.
# Kept as one function so a maintainer reads every rule's definition in one place.
MEASURE_JS = r"""
({buttonSelector, tapSelector, checkTap, minTap}) => {
  const vw = window.innerWidth;
  const text = el => (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '')
      .replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const describe = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (typeof el.className === 'string' && el.className.trim()
        ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  const out = {overflow: null, wrap: [], tap: [], contrast: []};

  // overflow: the document is wider than the viewport. Name the widest offender to help the fix.
  const sw = document.documentElement.scrollWidth;
  if (sw > vw) {
    let worst = null, right = vw;
    for (const el of document.body.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.right > right + 0.5 && r.width > 0) { right = r.right; worst = el; }
    }
    out.overflow = {scrollWidth: sw, viewport: vw, widest: worst ? describe(worst) : ''};
  }

  // wrap: count the lines a button's label occupies. Rects of the label's text fragments are
  // grouped into lines by vertical overlap, so an icon sitting a few px higher on the SAME line
  // does not count as a second line.
  for (const el of document.querySelectorAll(buttonSelector)) {
    if (!visible(el) || !el.firstChild) continue;
    const range = document.createRange();
    range.selectNodeContents(el);
    const rects = [...range.getClientRects()].filter(r => r.width > 0.5 && r.height > 0.5)
        .sort((a, b) => a.top - b.top);
    let lines = 0, bottom = -Infinity;
    for (const r of rects) {
      if (r.top >= bottom - 1) { lines++; bottom = r.bottom; }
      else bottom = Math.max(bottom, r.bottom);
    }
    if (lines > 1) out.wrap.push({text: text(el), lines});
  }

  // tap: a visible tap target under the minimum height (phone only).
  if (checkTap) {
    for (const el of document.querySelectorAll(tapSelector)) {
      if (!visible(el)) continue;
      const h = el.getBoundingClientRect().height;
      if (h < minTap) out.tap.push({text: text(el) || describe(el), height: Math.round(h * 10) / 10});
    }
  }

  // contrast. Colours are normalised through a 1x1 canvas, so any CSS colour syntax the browser
  // computes (rgb, color(srgb ...), oklch ...) comes back as plain RGBA.
  const ctx = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
  const cache = new Map();
  const rgba = css => {
    if (cache.has(css)) return cache.get(css);
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000'; ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    const v = {r, g, b, a: a / 255};
    cache.set(css, v);
    return v;
  };
  const over = (top, under) => ({   // `top` composited over an opaque `under`
    r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lum = c => {
    const ch = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
  };
  // The page's canvas when no element paints a background: white, or the UA's dark canvas.
  const rootScheme = getComputedStyle(document.documentElement).colorScheme || '';
  const canvas = rootScheme.includes('dark') && matchMedia('(prefers-color-scheme: dark)').matches
      ? {r: 18, g: 18, b: 18, a: 1} : {r: 255, g: 255, b: 255, a: 1};
  // The effective background: walk ancestors collecting translucent layers down to the first
  // opaque one, then composite them. A background IMAGE (a gradient, a picture) on the way makes
  // the answer unknowable from styles alone, so that element is skipped (null), not guessed.
  const background = el => {
    const layers = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      const c = rgba(cs.backgroundColor);
      if (c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let bg = canvas;
    for (let i = layers.length - 1; i >= 0; i--) bg = layers[i].a >= 1 ? layers[i] : over(layers[i], bg);
    return bg;
  };
  // Visually hidden text (the sr-only pattern, off-screen text) is for screen readers, not eyes.
  const visuallyHidden = (el, r) => {
    if (r.width <= 1 || r.height <= 1 || r.right <= 0 || r.bottom <= 0) return true;
    const cs = getComputedStyle(el);
    return (cs.clip && cs.clip.startsWith('rect(0')) || cs.clipPath === 'inset(50%)';
  };
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION'].includes(el.tagName)) continue;
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('')
        .replace(/\s+/g, ' ').trim();
    if (!own || !visible(el)) continue;
    if (el.closest(':disabled, [aria-disabled="true"]')) continue;   // WCAG exempts disabled controls
    const r = el.getBoundingClientRect();
    if (visuallyHidden(el, r)) continue;
    const bg = background(el);
    if (!bg) continue;
    const cs = getComputedStyle(el);
    const fg = over(rgba(cs.color), bg);
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
    const ratio = (hi + 0.05) / (lo + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const floor = large ? 3 : 4.5;
    if (ratio < floor - 0.005) {
      out.contrast.push({text: own, ratio: Math.round(ratio * 100) / 100, floor,
                         where: describe(el), fg: cs.color});
    }
  }
  return out;
}
"""

def is_ignored_console(text):
    """Console noise that is not the page's own failure. Each line says why it is ignored:
    - a missing favicon: the browser asks for /favicon.ico whether or not the page links one;
    - service-worker registration/update noise: the worker is an offline cache, not the page, and
      its install races a page that is closed right after measuring."""
    t = text.lower()
    return 'favicon' in t or ('serviceworker' in t.replace(' ', '') and 'register' in t)


def stable_text(text):
    """A key's identifying text: whitespace collapsed, `|` (the key separator) replaced, trimmed."""
    text = re.sub(r'\s+', ' ', text or '').replace('|', '/').strip()
    return text[:KEY_TEXT_MAX].rstrip()


def console_text(text, base):
    """Console text made run-independent: the server origin (its port varies) and numbers (ids,
    line:column positions) are folded, so the same error keys the same way every run."""
    text = text.replace(base, '')
    return re.sub(r'\d+', '#', text)


# ---------------------------------------------------------------------------------------------
# Loading pages
# ---------------------------------------------------------------------------------------------

def lint_page(context, base, url, screen, setup, width_name, theme, answer, button_sel, tap_sel):
    """Load one URL in one variant; return [(key, measured value)]."""
    prefix = f'{screen}|{setup}|{width_name}|{theme}'
    found = []

    def fail(rule, text, measured):
        found.append((f'{prefix}|{rule}|{stable_text(text)}', measured))

    page = context.new_page()
    errors = []

    def on_console(m):
        # Chromium's "Failed to load resource" console line carries no URL; the `response` hook
        # below reports the same failure WITH its path, so this copy is dropped.
        if m.type == 'error' and not m.text.startswith('Failed to load resource'):
            errors.append(m.text)

    def on_response(r):
        if r.status >= 400 and r.url != base + url:     # the page's own status is checked below
            errors.append(f'HTTP {r.status} {r.url}')

    page.on('console', on_console)
    page.on('pageerror', lambda e: errors.append(f'uncaught: {e}'))
    page.on('response', on_response)
    page.on('requestfailed', lambda r: errors.append(f'request failed {r.url}'))
    try:
        response = page.goto(base + url, wait_until='load', timeout=60000)
        page.wait_for_timeout(SETTLE_MS)
        if response is None or response.status >= 400:
            status = response.status if response else 'no response'
            fail('console', f'HTTP {status}', f'{url} answered {status}')

        width, height = WIDTHS[width_name]
        m = page.evaluate(MEASURE_JS, {'buttonSelector': button_sel, 'tapSelector': tap_sel,
                                       'checkTap': width_name == 'phone', 'minTap': MIN_TAP_PX})
        if m['overflow']:
            o = m['overflow']
            fail('overflow', 'page', f'scrollWidth {o["scrollWidth"]} > {o["viewport"]}'
                                     f' (widest: {o["widest"]})')
        for w in m['wrap']:
            fail('wrap', w['text'], f'{w["lines"]} lines')
        for t in m['tap']:
            fail('tap', t['text'], f'{t["height"]} px tall')
        for c in m['contrast']:
            fail('contrast', c['text'], f'{c["ratio"]}:1 < {c["floor"]}:1 ({c["where"]}, {c["fg"]})')

        # fold: the answer's first visible match must start above the fold.
        box = None
        for el in page.locator(answer).all():
            if el.is_visible():
                box = el.bounding_box()
                break
        if box is None:
            fail('fold', answer, 'no visible match')
        elif box['y'] >= height:
            fail('fold', answer, f'starts at {round(box["y"])} px, fold at {height} px')

        # console: read last, so errors raised while measuring are caught too.
        for msg in errors:
            if not is_ignored_console(msg):
                fail('console', console_text(msg, base), msg[:200])
    except Exception as exc:        # a page that cannot even be measured is a failure, not a crash
        fail('console', f'lint could not load page: {type(exc).__name__}', str(exc)[:200])
    finally:
        page.close()

    # Dedupe within the page: the first measurement of a key is the one reported.
    seen, unique = set(), []
    for key, measured in found:
        if key not in seen:
            seen.add(key)
            unique.append((key, measured))
    return unique


def lint_urls(targets, base, cfg, channel):
    """Load every (screen, setup, url, answer) in all four variants; {key: measured}."""
    from playwright.sync_api import sync_playwright
    lint_cfg = cfg['lint']
    failures, loaded = {}, 0
    with sync_playwright() as pw:
        launch = {'headless': True}
        if channel != 'chromium':
            launch['channel'] = channel
        browser = pw.chromium.launch(**launch)
        try:
            for width_name, (w, h) in WIDTHS.items():
                for theme in THEMES:
                    context = browser.new_context(viewport={'width': w, 'height': h},
                                                  color_scheme=theme)
                    if lint_cfg.get('theme_init'):
                        context.add_init_script(fill(lint_cfg['theme_init'], theme=theme))
                    for screen, setup, url, answer in targets:
                        for key, measured in lint_page(
                                context, base, url, screen, setup, width_name, theme, answer,
                                lint_cfg.get('button_selector', 'button'),
                                lint_cfg.get('tap_selector', 'button')):
                            failures.setdefault(key, measured)
                        loaded += 1
                    context.close()
        finally:
            browser.close()
    return failures, loaded


# ---------------------------------------------------------------------------------------------
# Baseline + report
# ---------------------------------------------------------------------------------------------

def report(title, keys, failures):
    if not keys:
        return
    print(f'\n{title}')
    by_screen = defaultdict(list)
    for k in sorted(keys):
        by_screen[k.split('|', 1)[0]].append(k)
    for screen, ks in by_screen.items():
        print(f'  {screen}')
        for k in ks:
            measured = failures.get(k)
            print(f'    {k}' + (f'    [{measured}]' if measured else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--app', required=True, type=Path, help='the app repo root (holds surface-review.toml)')
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument('--all', action='store_true', help='lint every registered screen')
    which.add_argument('--changed-since', metavar='REF', help='lint the screens changed since a git ref')
    parser.add_argument('--write-baseline', action='store_true',
                        help='record the current failures for the linted screens and exit 0')
    parser.add_argument('--channel', default='msedge' if os.name == 'nt' else 'chromium',
                        help="browser: msedge (installed Edge), chrome, or chromium (Playwright's own)")
    parser.add_argument('--port', type=int, help='serve on this port (default: a free one)')
    parser.add_argument('--json', type=Path, help='also write the result as JSON here')
    parser.add_argument('--keep', action='store_true', help='keep the temp data dir (for debugging)')
    opts = parser.parse_args()

    if hasattr(sys.stdout, 'reconfigure'):   # labels can be any Unicode; a Windows console is not
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    started = time.time()
    app = opts.app.resolve()
    cfg, screens = load_config(app)

    if opts.all:
        selected, why = screens, 'all registered screens'
    else:
        selected, why = select_screens(app, cfg, screens, opts.changed_since)
    if not selected:
        print(f'surface lint: no registered screen is touched since {opts.changed_since}; nothing to lint.')
        return 0
    print(f'surface lint: {len(selected)} screen(s) - {why}')

    data_dir = Path(tempfile.mkdtemp(prefix='surface-lint-'))
    port = pick_port(opts.port)
    subs = {'python': sys.executable, 'data_dir': data_dir, 'port': port}
    env = lint_env(cfg, subs)
    try:
        t0 = time.time()
        run_command(cfg['lint']['prepare'], app, env, subs, 'prepare')
        targets = []
        for s in selected:
            for setup in s['setups']:
                out = run_command(cfg['lint']['seed'], app, env, {**subs, 'screen': s['slug'], 'setup': setup},
                                  f'seed {s["slug"]} {setup}')
                answer = s['answer_by_setup'].get(setup, s.get('answer', 'body'))
                targets.append((s['slug'], setup, seeded_url(out, f'seed {s["slug"]} {setup}'), answer))
        t_seed = time.time() - t0
        print(f'- prepared and seeded {len(targets)} screen setup(s) in {t_seed:.0f}s; serving on {port}')

        serve_cmd = [fill(part, **subs) for part in cfg['lint']['serve']]
        t0 = time.time()
        with Server(serve_cmd, app, env, port, data_dir / 'serve.log') as server:
            failures, loaded = lint_urls(targets, server.base, cfg, opts.channel)
        t_pages = time.time() - t0
    finally:
        if opts.keep:
            print(f'- data dir kept: {data_dir}')
        else:
            shutil.rmtree(data_dir, ignore_errors=True)

    # SR17: the shrink-only baseline.
    baseline_path = app / cfg['lint_baseline']
    baseline = set(json.loads(baseline_path.read_text(encoding='utf-8'))) if baseline_path.exists() else set()
    linted = {s['slug'] for s in selected}
    current = set(failures)
    new = current - baseline
    cleared = {k for k in baseline if k.split('|', 1)[0] in linted and k not in current}
    baselined = current & baseline

    per_rule = defaultdict(int)
    for k in current:
        per_rule[k.split('|')[4]] += 1
    print(f'- loaded {loaded} page(s) in {t_pages:.0f}s ({len(targets)} setups x {len(WIDTHS) * len(THEMES)} variants)')
    print(f'- failures: {len(current)} ('
          + ', '.join(f'{r} {per_rule[r]}' for r in RULES if per_rule[r]) + ')'
          if current else '- failures: none')

    if opts.json:
        opts.json.write_text(json.dumps({
            'screens': sorted(linted), 'pages': loaded, 'failures': failures,
            'new': sorted(new), 'baselined': sorted(baselined), 'cleared': sorted(cleared),
        }, indent=2), encoding='utf-8')

    if opts.write_baseline:
        kept = {k for k in baseline if k.split('|', 1)[0] not in linted}
        written = sorted(kept | current)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(written, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'- baseline written: {baseline_path} ({len(written)} keys; '
              f'{len(current)} from this run, {len(kept)} kept for screens not linted)')
        print(f'surface lint: done in {time.time() - started:.0f}s')
        return 0

    report('NEW failures (not in the baseline) - fix them:', new, failures)
    report('FIXED - remove these from the baseline (it only shrinks):', cleared, failures)
    print(f'\nsurface lint: {len(linted)} screen(s), {len(targets)} setup(s), {loaded} page(s); '
          f'new {len(new)}, baselined {len(baselined)}, cleared {len(cleared)}; '
          f'{time.time() - started:.0f}s')
    return 1 if new or cleared else 0


if __name__ == '__main__':
    sys.exit(main())
