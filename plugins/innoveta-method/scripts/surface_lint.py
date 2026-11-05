"""Mechanical layout lint for registered web screens: the surface review's SR14-SR17 rules.

    python surface_lint.py --app <repo root> --all
    python surface_lint.py --app <repo root> --changed-since origin/master
    python surface_lint.py --app <repo root> --all --write-baseline
    python surface_lint.py --app <repo root> --all --channel chromium --json lint.json

What it does, in order:

1. Reads the app's `surface-review.toml` (at `--app`) and the screen registry it names.
2. Picks screens: every one (`--all`), or the ones a change since a git ref touches. A changed
   file that is a screen's own template selects that screen; a changed SHARED file selects the
   screens it can reach (the template graph, <script src>, the changed CSS selectors and custom
   properties), and ALL screens whenever it cannot be pinned down (see "Precise selection"
   below; `[select] mode = "shared-all"` restores "any shared file lints every screen"). Each
   selected screen is printed with why; `--select-only` stops there (SR16).
3. Builds a throwaway world: a fresh temp data dir, the app's `prepare` command, then every
   screen x setup seeded in order into that one world: in ONE process when the app has
   `seed_batch`, else one `seed` run each (each prints `{"url": "/path"}`). Then the app's
   `serve` command on a free port; the server is always killed at the end, children included.
4. Loads every URL at phone (375x812) and desk (1280x900), light and dark, each in a fresh browser
   context, waits for it to SETTLE (no request in flight, fonts ready, two animation frames; a
   page not settled within `settle_timeout_ms` fails the whole run), and checks six rules:
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
are substituted in every string, `{batch_file}` in seed_batch; nothing else in braces is touched):

    prepare = [...]          # command run once, in the app root, on the fresh data dir
    seed    = [...]          # command run per screen x setup; its stdout's last JSON line has "url"
    seed_batch = [...]       # optional: one command seeding every setup in {batch_file} (see seed_batch)
    parallel = 1             # browsers loading pages at once; above 1 the world digest must stay unchanged
    world_digest = "sqlite"  # how pages are proven to write nothing: "sqlite" | [command] | "off"
    settle_timeout_ms = 15000
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
# The phone is a TOUCH device, not a narrow desk window: apps size their targets under
# `(hover:none), (pointer:coarse)`, which only a touch context matches. Without it the tap rule
# measured desk-sized buttons at 375 px and reported targets a real phone draws at 44 px.
DEVICE = {'phone': {'has_touch': True, 'is_mobile': True}, 'desk': {}}
THEMES = ('light', 'dark')
RULES = ('overflow', 'wrap', 'tap', 'console', 'contrast', 'fold')

# Ports the lint never serves on: the usual dev-server range, ports that are reserved on some
# Windows machines, and the range sibling dev sessions use. Anything already listening is skipped too.
AVOID_PORTS = set(range(8000, 8011)) | {8033, 8034, 8080} | set(range(8041, 8062))
PORT_RANGE = (8100, 8999)

KEY_TEXT_MAX = 40          # a key's identifying text is trimmed to this many characters
MIN_TAP_PX = 44            # SR14: tap targets at phone width
SETTLE_TIMEOUT_MS = 15000  # a page not settled by then FAILS THE RUN (see `settle`)


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
    """(screens to lint, a line explaining why) for a change since `ref` (SR16).

    `[select] mode = "precise"` (the default) traces each changed shared file to the screens it can
    reach (see `precise_selection`); `mode = "shared-all"` keeps the old rule: any shared file
    lints every screen."""
    if cfg.get('select', {}).get('mode', 'precise') == 'precise':
        return precise_selection(app, cfg, screens, ref)
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
# Precise selection: trace each changed shared file to the screens it can reach
# ---------------------------------------------------------------------------------------------
#
# A changed SHARED file selects only the screens that can show it, worked out statically:
#   template    the screens whose template graph reaches it. Edges are every quoted template name
#               a template mentions ({% extends %}, {% include %}, {% with x="..." %}, an import).
#   script      the screens whose templates (base and includes too) name it in a src, or name a
#               script that names it.
#   stylesheet  the rules that changed between the merge base and now; each changed selector's
#               required classes/ids (outside :not()/:is()/:has()...) must appear in a screen's
#               templates or the scripts it loads. A changed custom property on a root-ish rule
#               selects the screens using the rules that read it.
# It FALLS BACK TO EVERY SCREEN, and says why, whenever it cannot attribute a change: a deleted
# file; a template or script no page reaches, or one named in app code (a view may render it); an
# element / universal / :root selector; a token app code builds or names (it may set it on any
# page); a custom property read by more than `css_var_fanout_max` rules; an @import, @font-face,
# @keyframes, @layer order or other at-rule it cannot attribute; or a stylesheet it cannot parse.
# `[select] mode = "shared-all"` turns all of this off (any shared file lints every screen).

TEMPLATE_EXTS = ('.html', '.htm', '.txt', '.xml', '.jinja', '.jinja2', '.j2')
SCRIPT_EXTS = ('.js', '.mjs')
DEFAULT_CODE_GLOBS = ['**/*.py']
DEFAULT_CODE_EXCLUDE = ['**/test_*.py', '**/*_test.py', '**/tests.py', '**/tests/**', '**/migrations/**']
CSS_VAR_FANOUT_MAX = 12
#: At-rule blocks whose rules still match only what their own selectors say (they only narrow).
CSS_NARROWING_AT = ('@media', '@supports', '@container', '@layer')
QUOTED_TEMPLATE = re.compile(r'''["']([^"'\s{}%]+\.(?:html?|txt|xml|jinja2?|j2))["']''')
FUNCTIONAL_PSEUDO = re.compile(r'::?[a-zA-Z-]+\(')


class Unattributable(Exception):
    """A change the selector cannot pin to some screens: lint every screen, for this reason."""


class Finder:
    """A literal searched with str.find, its neighbours then checked: `before` / `after` say which
    characters may sit either side ('' = the text's edge or a line break is also fine). Much
    faster than a regex that opens with a lookbehind over hundreds of KB of templates."""

    def __init__(self, needle, before_ok, after_ok):
        self.needle, self.before_ok, self.after_ok = needle, before_ok, after_ok

    def search(self, text):
        i = text.find(self.needle)
        while i >= 0:
            j = i + len(self.needle)
            if self.before_ok(text[i - 1] if i else '\n') and self.after_ok(text[j] if j < len(text) else '\n'):
                return True
            i = text.find(self.needle, i + 1)
        return False


def _not_word(c):
    return not (c.isalnum() or c in '_-')


def word_re(token):
    """`token` as a whole CSS-ish word: not preceded or followed by a word character or `-`."""
    return Finder(token, _not_word, _not_word)


def file_ref_re(name):
    """A reference to a served file `name` (`/static/x.js`, `{% static 'x.js' %}`, `'./x.js'`)."""
    return Finder(name, lambda c: c in '/\'"`\n', lambda c: c in '\'"`?#\n')


def prefix_re(prefix, follow):
    """`prefix` at a word start, followed by one of the regex alternatives in `follow`."""
    return _PrefixFinder(prefix, re.compile(follow))


class _PrefixFinder(Finder):
    def __init__(self, prefix, rx):
        super().__init__(prefix, _not_word, lambda c: True)
        self.rx = rx

    def search(self, text):
        i = text.find(self.needle)
        while i >= 0:
            if _not_word(text[i - 1] if i else '\n') and self.rx.match(text, i + len(self.needle)):
                return True
            i = text.find(self.needle, i + 1)
        return False


def code_strings(path):
    """The string literals in a Python file, docstrings left out (they explain, they render
    nothing); f-string parts included. A file that does not parse is returned whole."""
    import ast
    import warnings
    text = path.read_text(encoding='utf-8', errors='replace')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')        # an app's own invalid-escape warnings
            tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return text
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    return '\n'.join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)


class Estate:
    """Every template, script and code string in the app, read once, plus the template graph."""

    def __init__(self, app, cfg):
        sel = cfg.get('select', {})
        self.app = app
        files = set(git_lines(app, 'ls-files')) | set(git_lines(app, 'ls-files', '--others', '--exclude-standard'))
        files = sorted(f.replace('\\', '/') for f in files if (app / f).is_file())
        tpl_globs = sel.get('templates', cfg.get('page_templates', []))
        self.roots = sel.get('template_roots')
        self.templates = {f: self._read(f) for f in files
                          if f.endswith(TEMPLATE_EXTS) and matches_any(f, tpl_globs)}
        self.by_name = defaultdict(set)
        for f in self.templates:
            self.by_name[self.template_name(f)].add(f)
        self.edges = {f: {p for n in QUOTED_TEMPLATE.findall(text) for p in self.by_name.get(n, ())}
                      for f, text in self.templates.items()}
        self.scripts = {f: self._read(f) for f in files if f.endswith(SCRIPT_EXTS)
                        and not matches_any(f, sel.get('script_exclude', []))}
        code_globs = sel.get('code', DEFAULT_CODE_GLOBS)
        code_exclude = sel.get('code_exclude', DEFAULT_CODE_EXCLUDE)
        self.code = {f: code_strings(app / f) for f in files
                     if matches_any(f, code_globs) and not matches_any(f, code_exclude)}
        self.var_fanout_max = sel.get('css_var_fanout_max', CSS_VAR_FANOUT_MAX)
        self._closures = {}

    def _read(self, f):
        return (self.app / f).read_text(encoding='utf-8', errors='replace')

    def template_name(self, path):
        """The name a template is loaded by: its path below a configured root, else below the
        last `templates/` folder (Django's and Jinja's convention)."""
        for root in self.roots or []:
            root = root.rstrip('/') + '/'
            if path.startswith(root):
                return path[len(root):]
        i = ('/' + path).rfind('/templates/')
        return ('/' + path)[i + len('/templates/'):] if i >= 0 else path

    def closure(self, paths):
        key = tuple(sorted(paths))
        if key not in self._closures:
            seen, todo = set(), [p for p in paths if p in self.templates]
            while todo:
                p = todo.pop()
                if p not in seen:
                    seen.add(p)
                    todo.extend(self.edges.get(p, ()))
            self._closures[key] = seen
        return self._closures[key]

    def code_hits(self, pattern):
        return sorted(f for f, text in self.code.items() if pattern.search(text))

    def loaders(self, name):
        """(templates, scripts) that load the served file `name`, through other scripts too."""
        rx = file_ref_re(name)
        scripts, todo = set(), [name]
        while todo:
            n = todo.pop()
            r = file_ref_re(n)
            for f, text in self.scripts.items():
                if f not in scripts and r.search(text):
                    scripts.add(f)
                    todo.append(served_name(f))
        names = [rx] + [file_ref_re(served_name(f)) for f in scripts]
        tpls = {f for f, text in self.templates.items() if any(r.search(text) for r in names)}
        return tpls, scripts

    def scripts_of(self, closure):
        """The scripts a set of templates loads (directly, or through another script)."""
        out = set()
        for f in self.scripts:
            tpls, _ = self._script_loaders(f)
            if tpls & closure:
                out.add(f)
        return out

    def _script_loaders(self, f):
        cache = self.__dict__.setdefault('_sl', {})
        if f not in cache:
            cache[f] = self.loaders(served_name(f))
        return cache[f]


def served_name(path):
    """The name a static file is served and referenced by: its path below `static/`."""
    i = ('/' + path).rfind('/static/')
    return ('/' + path)[i + len('/static/'):] if i >= 0 else path.rsplit('/', 1)[-1]


# --- stylesheets ------------------------------------------------------------------------------

def css_strip_comments(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in '"\'':
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            if j < 0:
                raise Unattributable('an unclosed comment')
            out.append(' ')
            i = j + 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def css_items(text):
    """A stylesheet as a flat list of (context, kind, head, body): `context` the enclosing
    narrowing at-rules, `kind` rule | opaque (an at-rule block) | statement. Raises
    Unattributable when it does not parse."""
    text = css_strip_comments(text)
    items, n = [], len(text)
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()

    def scan(i, stops):
        """Index of the first char in `stops` at depth 0 (outside strings and brackets)."""
        depth = 0
        while i < n:
            c = text[i]
            if c in '"\'':
                j = i + 1
                while j < n and text[j] != c:
                    j += 2 if text[j] == '\\' else 1
                i = j + 1
                continue
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            elif depth == 0 and c in stops:
                return i
            i += 1
        return n

    def block_end(i):
        """`i` is just past a `{`; the index of its matching `}`."""
        depth = 1
        while i < n:
            j = scan(i, '{}')
            if j >= n:
                raise Unattributable('an unbalanced brace')
            depth += 1 if text[j] == '{' else -1
            if depth == 0:
                return j
            i = j + 1
        raise Unattributable('an unbalanced brace')

    def parse(i, end, context):
        while i < end:
            j = scan(i, '{};')
            j = min(j, end)
            head = norm(text[i:j])
            if j >= end:
                if head:
                    raise Unattributable(f'trailing text "{head[:40]}"')
                return
            if text[j] == '}':
                raise Unattributable('a stray }')
            if text[j] == ';':
                if head:
                    items.append((context, 'statement', head, ''))
                i = j + 1
                continue
            k = block_end(j + 1)
            body = text[j + 1:k]
            if head.startswith('@'):
                if head.split()[0].split('(')[0].lower() in CSS_NARROWING_AT:
                    parse(j + 1, k, context + (head,))
                else:
                    items.append((context, 'opaque', head, norm(body)))
            else:
                items.append((context, 'rule', head, norm(body)))
            i = k + 1

    parse(0, n, ())
    return items


def css_decls(body):
    """{property: value} of a rule body; a nested rule inside it makes the body one opaque value."""
    if '{' in body:
        return {'{nested}': body}
    out = {}
    for part in body.split(';'):
        if ':' in part:
            prop, value = part.split(':', 1)
            out[prop.strip().lower()] = value.strip()
    return out


def split_top(s, sep=','):
    parts, depth, cur, quote = [], 0, [], None
    for c in s:
        if quote:
            cur.append(c)
            quote = None if c == quote else quote
            continue
        if c in '"\'':
            quote = c
        elif c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(''.join(cur))
            cur = []
            continue
        cur.append(c)
    parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


def required_tokens(selector):
    """The classes and ids an element (or its ancestors) MUST carry to match one complex
    selector. Functional pseudo-classes (:not, :is, :where, :has, :nth-child(of ...)) and
    attribute selectors are dropped, since they do not require their tokens. Empty = the selector
    can match a page with none of its tokens (element, universal, :root): unattributable."""
    if '\\' in selector:
        return set()
    s = re.sub(r'"[^"]*"|\'[^\']*\'', '', selector)
    s = re.sub(r'\[[^\]]*\]', '', s)
    while True:
        m = FUNCTIONAL_PSEUDO.search(s)
        if not m:
            break
        depth, j = 1, m.end()
        while j < len(s) and depth:
            depth += {'(': 1, ')': -1}.get(s[j], 0)
            j += 1
        s = s[:m.start()] + s[j:]
    return set(re.findall(r'[.#](-?[_a-zA-Z][\w-]*)', s))


def css_changes(old, new):
    """[(old item or None, new item or None)] for every rule that differs, paired where a
    rewritten rule kept its place, context and selector."""
    import difflib
    a, b = css_items(old), css_items(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal':
            continue
        olds, news = list(a[i1:i2]), list(b[j1:j2])
        for o in list(olds):
            twin = next((x for x in news if x[:3] == o[:3]), None)
            if twin:
                out.append((o, twin))
                olds.remove(o)
                news.remove(twin)
        out += [(o, None) for o in olds] + [(None, x) for x in news]
    return out, a + b


class Selection:
    """Which screens a change reaches, and why; `everything` collects reasons to lint them all."""

    def __init__(self, est, screens):
        self.est, self.screens = est, screens
        self.closure = {s['slug']: est.closure(s['templates']) for s in screens}
        self.why = defaultdict(list)
        self.everything = []
        self._scripts = {}

    def add(self, slugs, reason):
        for slug in slugs:
            if reason not in self.why[slug]:
                self.why[slug].append(reason)

    def screen_scripts(self, slug):
        if slug not in self._scripts:
            self._scripts[slug] = self.est.scripts_of(self.closure[slug])
        return self._scripts[slug]

    def reaching(self, templates):
        return [slug for slug, c in self.closure.items() if c & templates]

    # template ---------------------------------------------------------------------------------
    def template(self, path, cfg):
        est = self.est
        name = est.template_name(path)
        named = est.code_hits(re.compile(re.escape(name)))
        own = [s['slug'] for s in self.screens if path in s['templates']]
        hits = [slug for slug, c in self.closure.items() if path in c]
        if hits:
            self.add(hits, f'{path}' + ('' if set(hits) <= set(own) else ' (its template graph reaches it)'))
        # A PAGE a view renders is a whole response: it shows inside another page only through the
        # graph. A partial a view renders may be a fragment some page fetches: unattributable.
        is_page = bool(cfg.get('page_marker')) and cfg['page_marker'] in est.templates.get(path, '')
        if named and not is_page:
            raise Unattributable(f'{path} is named in app code ({", ".join(named[:3])}), which may render it on any page')
        if hits:
            return
        if any(path in est.edges[t] for t in est.templates):
            print(f'note: {path} reaches only templates no screen registers (not linted)')
        elif is_page:
            print(f'note: changed page template no screen registers (not linted): {path}')
        else:
            raise Unattributable(f'{path}: no template reaches it and no screen registers it')

    # script -----------------------------------------------------------------------------------
    def script(self, path):
        name = served_name(path)
        named = self.est.code_hits(file_ref_re(name))
        if named:
            raise Unattributable(f'{path} is named in app code ({", ".join(named[:3])})')
        tpls, via = self.est.loaders(name)
        hits = self.reaching(tpls)
        if not hits:
            raise Unattributable(f'{path}: no registered screen\'s templates load it')
        self.add(hits, f'{path} (loaded' + (f' via {", ".join(sorted(via))}' if via else '') + ')')

    # stylesheet -------------------------------------------------------------------------------
    def stylesheet(self, path, old):
        est = self.est
        name = served_name(path)
        tpls, _ = est.loaders(name)
        loading = set(self.reaching(tpls))
        if not loading:
            raise Unattributable(f'{path}: no registered screen\'s templates load it')
        changes, all_items = css_changes(old, (est.app / path).read_text(encoding='utf-8', errors='replace'))
        for o, x in changes:
            item = x or o
            context, kind, head, body = item
            where = f'{path} "{head[:60]}"'
            if kind != 'rule':
                raise Unattributable(f'{where}: an at-rule ({kind}) the selector cannot attribute')
            selectors = split_top(head)
            per = [required_tokens(s) for s in selectors]
            if all(per):
                for s, toks in zip(selectors, per):
                    self.add(self.using_tokens(toks, loading, where), f'{path} {s[:60]}')
                continue
            # A root-ish rule: attributable only when what changed is custom properties.
            od, nd = css_decls(o[3]) if o else {}, css_decls(x[3]) if x else {}
            changed = {p for p in od.keys() | nd.keys() if od.get(p) != nd.get(p)}
            if not changed or not all(p.startswith('--') for p in changed):
                bad = next(s for s, t in zip(selectors, per) if not t)
                raise Unattributable(f'{path} "{bad[:60]}": an element, universal or :root selector')
            self.custom_properties(path, changed, all_items, loading)

    def using_tokens(self, tokens, loading, where):
        """The screens (among `loading`) whose templates or scripts carry every token."""
        est = self.est
        # A token app code names or builds may be on ANY page, so it narrows nothing; the
        # selector's other required tokens still do. All of them code-named: unattributable.
        built = {tok: self.token_in_code(tok) for tok in tokens}
        tokens = {tok for tok in tokens if not built[tok]}
        if not tokens:
            tok, files = next(iter(built.items()))
            raise Unattributable(f'{where}: app code names or builds "{tok}" ({", ".join(files[:3])})')
        hits = []
        for slug in sorted(loading):
            texts = [est.templates[t] for t in self.closure[slug]] + \
                    [est.scripts[f] for f in self.screen_scripts(slug)]
            if all(any(self.carries(text, tok) for text in texts) for tok in tokens):
                hits.append(slug)
        # A token only some unloaded script carries: that script may set it anywhere.
        for tok in tokens:
            for f, text in est.scripts.items():
                if self.carries(text, tok) and not est._script_loaders(f)[0]:
                    raise Unattributable(f'{where}: "{tok}" is in {f}, which no template loads')
        return hits

    @staticmethod
    def prefixes(tok):
        return [tok[:i + 1] for i, c in enumerate(tok) if c in '-_' and 0 < i < len(tok) - 1]

    def carries(self, text, tok):
        if word_re(tok).search(text):
            return True
        for p in self.prefixes(tok):     # class="pill-{{ state }}", `pill-${state}`, 'pill-' + state
            if prefix_re(p, r'''\{\{|\{%|\$\{|['"`]\s*\+''').search(text):
                return True
        return False

    def token_in_code(self, tok):
        rx = word_re(tok)
        pre = [prefix_re(p, r'$|\n') for p in self.prefixes(tok)]   # a string ENDING in the prefix
        return sorted(f for f, text in self.est.code.items()
                      if rx.search(text) or any(r.search(text) for r in pre))

    def custom_properties(self, path, props, items, loading):
        est = self.est
        props, users, todo = set(props), [], list(props)
        while todo:
            prop = todo.pop()
            rx = re.compile(r'var\(\s*' + re.escape(prop) + r'(?![\w-])')
            for item in items:
                if rx.search(item[3]) and item not in users:
                    users.append(item)
                    for p, v in css_decls(item[3]).items():
                        if p.startswith('--') and rx.search(v) and p not in props:
                            props.add(p)
                            todo.append(p)
        shown = ', '.join(sorted(props)[:4])
        if len({(u[0], u[2]) for u in users}) > est.var_fanout_max:
            raise Unattributable(f'{path} {shown}: read by {len(users)} rules (over css_var_fanout_max '
                                 f'{est.var_fanout_max}), a widely-used token')
        for prop in props:
            if est.code_hits(re.compile(re.escape(prop) + r'(?![\w-])')):
                raise Unattributable(f'{path} {prop}: named in app code')
            rx = re.compile(re.escape(prop) + r'(?![\w-])')
            for f, text in est.scripts.items():
                if rx.search(text):
                    t, _ = est._script_loaders(f)
                    if not t:
                        raise Unattributable(f'{path} {prop}: in {f}, which no template loads')
                    self.add([s for s in self.reaching(t) if s in loading], f'{path} {prop} (set by {f})')
            self.add([s for s in self.reaching({t for t, text in est.templates.items() if rx.search(text)})
                      if s in loading], f'{path} {prop} (in a template)')
        for context, kind, head, body in users:
            if kind != 'rule':
                raise Unattributable(f'{path} {shown}: read inside "{head[:40]}"')
            for s in split_top(head):
                toks = required_tokens(s)
                if not toks:
                    raise Unattributable(f'{path} {shown}: read by "{s[:40]}", an element, universal or :root selector')
                self.add(self.using_tokens(toks, loading, path), f'{path} {shown} (read by {s[:50]})')


def merge_base(app, ref):
    return git_lines(app, 'merge-base', ref, 'HEAD')[0]


def precise_selection(app, cfg, screens, ref):
    est = Estate(app, cfg)
    sel = Selection(est, screens)
    base = merge_base(app, ref)
    own = {t: s['slug'] for s in screens for t in s['templates']}
    for path in changed_files(app, ref):
        if path not in own and not matches_any(path, cfg.get('shared', [])):
            continue
        try:
            if not (app / path).exists():
                raise Unattributable(f'{path} was deleted')
            if path in est.templates:
                sel.template(path, cfg)
            elif path in own:
                sel.add([own[path]], path)
            elif path.endswith(SCRIPT_EXTS):
                sel.script(path)
            elif path.endswith('.css'):
                shown = subprocess.run(['git', '-C', str(app), 'show', f'{base}:{path}'],
                                       capture_output=True, text=True, encoding='utf-8', errors='replace')
                sel.stylesheet(path, shown.stdout if shown.returncode == 0 else '')
            else:
                raise Unattributable(f'{path}: not a template, script or stylesheet')
        except Unattributable as why:
            sel.everything.append(str(why))
    if sel.everything:
        for line in sel.everything:
            print(f'  all screens because: {line}')
        return screens, 'shared change(s) the selector cannot attribute: every registered screen'
    picked = [s for s in screens if sel.why.get(s['slug'])]
    for s in picked:
        reasons = sel.why[s['slug']]
        print(f'  {s["slug"]}: ' + '; '.join(reasons[:4]) + (f' (+{len(reasons) - 4} more)' if len(reasons) > 4 else ''))
    return picked, 'screens a changed file reaches (precise selection)'


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


def seed_batch(cfg, app, env, subs, data_dir, pairs):
    """Seed every (screen, setup) in ONE process, in order, into the same world: the app's
    `seed_batch` command reads `{batch_file}` (a JSON list of {"screen", "setup"}) and prints one
    JSON line per setup, {"screen", "setup", "url"} or {"screen", "setup", "error"}. It must keep
    going after a failed setup (rolling that one back), so every failure is reported per setup.
    Returns {(screen, setup): url}; exits naming each setup that failed or printed nothing."""
    batch_file = Path(data_dir) / 'seed-batch.json'
    batch_file.write_text(json.dumps([{'screen': s, 'setup': u} for s, u in pairs]), encoding='utf-8')
    cmd = [fill(part, **subs, batch_file=batch_file) for part in cfg['lint']['seed_batch']]
    out = subprocess.run(cmd, cwd=app, env=env, capture_output=True, text=True,
                         encoding='utf-8', errors='replace')
    urls, errors = {}, {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        key = (row.get('screen'), row.get('setup'))
        if key not in set(pairs):
            continue
        if 'url' in row and 'error' not in row:
            urls[key] = row['url']
        else:
            errors[key] = str(row.get('error', 'no url'))
    missing = [p for p in pairs if p not in urls and p not in errors]
    if errors or missing or out.returncode != 0:
        lines = [f'  seed {s} {u}: {errors[(s, u)]}' for s, u in pairs if (s, u) in errors]
        if missing and len(missing) == len(pairs):
            lines.append(f'  no setup printed a result (of {len(pairs)}): the batch failed before seeding')
        else:
            lines += [f'  seed {s} {u}: printed no result (the batch stopped before it)' for s, u in missing]
        sys.exit(f'seed_batch failed ({" ".join(cmd)}, exit {out.returncode}):\n' + '\n'.join(lines)
                 + f'\n{out.stderr[-2000:]}')
    return urls


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

class Unsettled(Exception):
    """A page that never went quiet within the settle timeout. Never a finding that a baseline
    could absorb: the whole run fails, because a measurement of a moving page is not one."""


# After `load`: wait for the page's fonts, then two animation frames (one to apply any style or
# layout a script queued at load, one to paint it). Run again until no request is in flight.
SETTLE_JS = """(ms) => Promise.race([
  document.fonts.ready.then(() => new Promise(r =>
    requestAnimationFrame(() => requestAnimationFrame(() => r(document.fonts.status))))),
  new Promise(r => setTimeout(() => r('timeout'), ms))])"""


def settle(page, inflight, timeout_ms):
    """Deterministic settle: network idle (no request of this page in flight) + fonts ready +
    two frames, repeated until a pass starts and ends with nothing in flight. Raises Unsettled
    when that has not happened within `timeout_ms`."""
    deadline = time.time() + timeout_ms / 1000
    while True:
        while inflight:
            if time.time() > deadline:
                raise Unsettled(f'{len(inflight)} request(s) still in flight after {timeout_ms} ms: '
                                + ', '.join(sorted(r.url for r in inflight))[:300])
            page.wait_for_timeout(10)       # pumps Playwright's events; not a settle guess
        status = page.evaluate(SETTLE_JS, max(1, int((deadline - time.time()) * 1000)))
        if not inflight and status == 'loaded':
            return
        if time.time() > deadline:
            raise Unsettled(f'page did not settle within {timeout_ms} ms (fonts {status}, '
                            f'{len(inflight)} request(s) in flight)')


def lint_page(context, base, url, screen, setup, width_name, theme, answer, button_sel, tap_sel,
              settle_ms):
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

    inflight = set()

    def on_failed(r):
        inflight.discard(r)
        errors.append(f'request failed {r.url}')

    page.on('console', on_console)
    page.on('pageerror', lambda e: errors.append(f'uncaught: {e}'))
    page.on('response', on_response)
    page.on('request', inflight.add)
    page.on('requestfinished', inflight.discard)
    page.on('requestfailed', on_failed)
    try:
        response = page.goto(base + url, wait_until='load', timeout=60000)
        settle(page, inflight, settle_ms)
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
    except Unsettled:
        raise
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


def lint_urls(targets, base, cfg, channel, workers=1):
    """Load every (screen, setup, url, answer) in all four variants; ({key: measured}, pages).

    Every page gets a FRESH browser context (cookies and storage start empty), so no page's
    measurement depends on which pages loaded before it. That is what lets `workers` > 1 browsers
    share the work: the jobs are dealt out, and the results merged back in the one fixed order
    (variant, then target), so the report is the same however the work was split."""
    import queue
    import threading
    from playwright.sync_api import sync_playwright
    lint_cfg = cfg['lint']
    settle_ms = int(lint_cfg.get('settle_timeout_ms', SETTLE_TIMEOUT_MS))
    variants = [(wn, wh, theme) for wn, wh in WIDTHS.items() for theme in THEMES]
    jobs = [(v, t) for v in range(len(variants)) for t in range(len(targets))]
    results, todo, fatal = {}, queue.Queue(), []
    for job in jobs:
        todo.put(job)

    def work():
        try:
            with sync_playwright() as pw:
                launch = {'headless': True}
                if channel != 'chromium':
                    launch['channel'] = channel
                browser = pw.chromium.launch(**launch)
                try:
                    while not fatal:
                        try:
                            v, t = todo.get_nowait()
                        except queue.Empty:
                            return
                        width_name, (w, h), theme = variants[v]
                        screen, setup, url, answer = targets[t]
                        context = browser.new_context(viewport={'width': w, 'height': h},
                                                      color_scheme=theme, **DEVICE[width_name])
                        try:
                            if lint_cfg.get('theme_init'):
                                context.add_init_script(fill(lint_cfg['theme_init'], theme=theme))
                            results[(v, t)] = lint_page(
                                context, base, url, screen, setup, width_name, theme, answer,
                                lint_cfg.get('button_selector', 'button'),
                                lint_cfg.get('tap_selector', 'button'), settle_ms)
                        except Unsettled as exc:
                            fatal.append(f'{screen} {setup} {width_name} {theme} ({url}): {exc}')
                        finally:
                            context.close()
                finally:
                    browser.close()
        except Exception as exc:             # a worker that dies must not leave pages unloaded quietly
            fatal.append(f'a page-loading worker failed: {type(exc).__name__}: {exc}')

    threads = [threading.Thread(target=work, daemon=True) for _ in range(max(1, workers))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    if fatal:
        sys.exit('surface lint: page(s) did not settle, so nothing measured is trustworthy:\n  '
                 + '\n  '.join(fatal))
    missing = [j for j in jobs if j not in results]
    if missing:
        sys.exit(f'surface lint: {len(missing)} page load(s) never ran.')
    failures = {}
    for job in jobs:
        for key, measured in results[job]:
            failures.setdefault(key, measured)
    return failures, len(jobs)


# ---------------------------------------------------------------------------------------------
# The world digest: proof that loading pages wrote nothing to the shared world
# ---------------------------------------------------------------------------------------------

def world_digest(cfg, app, env, subs, data_dir):
    """{part: hash} of the world's stored state. `world_digest = "sqlite"` (the default) hashes
    every table of every SQLite file in the data dir, rows sorted; a command list instead prints
    a digest on stdout (an app on a server database). `world_digest = "off"`: None (unproven)."""
    spec = cfg['lint'].get('world_digest', 'sqlite')
    if spec == 'off':
        return None
    if isinstance(spec, list):
        return {'command': run_command(spec, app, env, subs, 'world_digest').strip()}
    import hashlib
    import sqlite3
    out = {}
    for db in sorted(p for p in Path(data_dir).rglob('*') if p.suffix in ('.sqlite3', '.sqlite', '.db')):
        con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
        try:
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type = 'table' order by name")]
            for table in tables:
                rows = sorted(repr(r) for r in con.execute(f'select * from "{table}"'))
                out[f'{db.name}:{table}'] = hashlib.sha256('\n'.join(rows).encode()).hexdigest()
        finally:
            con.close()
    return out or None


def warm_up(base, url):
    """One plain GET before the digest, so a first-request write (a user row, a last-seen stamp)
    lands before the world is measured, exactly as the first page load would make it."""
    try:
        with urllib.request.urlopen(base + url, timeout=60):
            pass
    except (urllib.error.URLError, OSError):
        pass        # the page's own load will report it


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
    parser.add_argument('--parallel', type=int, help='browsers loading pages at once (default: [lint] '
                        'parallel, else 1); above 1 the world digest must prove the pages wrote nothing')
    parser.add_argument('--select-only', action='store_true',
                        help='print the screens a change selects, and why, then stop')
    parser.add_argument('--seed-each', action='store_true',
                        help='seed one process per setup even when the app has seed_batch')
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
    if opts.select_only:
        for s in selected:
            print(f'  {s["slug"]}')
        return 0

    data_dir = Path(tempfile.mkdtemp(prefix='surface-lint-'))
    port = pick_port(opts.port)
    subs = {'python': sys.executable, 'data_dir': data_dir, 'port': port}
    env = lint_env(cfg, subs)
    try:
        t0 = time.time()
        run_command(cfg['lint']['prepare'], app, env, subs, 'prepare')
        t_prepare = time.time() - t0
        pairs = [(s['slug'], setup) for s in selected for setup in s['setups']]
        if cfg['lint'].get('seed_batch') and not opts.seed_each:
            urls = seed_batch(cfg, app, env, subs, data_dir, pairs)
            how = 'in one batch process'
        else:
            urls = {}
            for screen, setup in pairs:
                out = run_command(cfg['lint']['seed'], app, env, {**subs, 'screen': screen, 'setup': setup},
                                  f'seed {screen} {setup}')
                urls[(screen, setup)] = seeded_url(out, f'seed {screen} {setup}')
            how = 'one process per setup'
        answers = {s['slug']: s for s in selected}
        targets = [(screen, setup, urls[(screen, setup)],
                    answers[screen]['answer_by_setup'].get(setup, answers[screen].get('answer', 'body')))
                   for screen, setup in pairs]
        t_seed = time.time() - t0
        print(f'- prepared in {t_prepare:.0f}s and seeded {len(targets)} screen setup(s) {how} in '
              f'{t_seed - t_prepare:.0f}s; serving on {port}')

        serve_cmd = [fill(part, **subs) for part in cfg['lint']['serve']]
        t0 = time.time()
        workers = opts.parallel or int(cfg['lint'].get('parallel', 1))
        with Server(serve_cmd, app, env, port, data_dir / 'serve.log') as server:
            if targets:
                warm_up(server.base, targets[0][2])
            before = world_digest(cfg, app, env, subs, data_dir)
            if workers > 1 and before is None:
                sys.exit('surface lint: parallel loading needs a world digest to prove pages write '
                         'nothing (world_digest is off, or no SQLite file was found); use parallel = 1.')
            failures, loaded = lint_urls(targets, server.base, cfg, opts.channel, workers)
            after = world_digest(cfg, app, env, subs, data_dir)
        t_pages = time.time() - t0
        if before is not None and before != after:
            moved = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
            msg = f'loading the pages wrote to the shared world ({", ".join(moved[:8])})'
            if workers > 1:
                sys.exit(f'surface lint: {msg}, so pages loaded in parallel could see each other\'s '
                         'writes. Make those GETs read-only, or set parallel = 1.')
            print(f'warning: {msg}; a page may depend on which pages loaded before it.')
        elif before is not None:
            print(f'- world digest unchanged across {loaded} page loads ({len(before)} tables): '
                  'the pages wrote nothing')
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
