"""Tests for surface_lint.py's screen selection and seeding (stdlib only, no browser):

    python -m unittest test_surface_lint

Each selection test builds a tiny git repo: a config, a registry, templates, a script, a stylesheet,
then changes one file and asks which screens the change selects."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import surface_lint as lint

CONFIG = '''registry = "screens.toml"
lint_baseline = "records/_lint_baseline.json"
page_templates = ["app/templates/**/*.html"]
page_marker = "{% extends"
shared = ["static/*.css", "static/*.js", "app/templates/**/*.html"]
'''
SCREENS = '''[[screen]]
slug = "orders"
templates = ["app/templates/app/orders.html"]
setups = ["empty"]

[[screen]]
slug = "invoices"
templates = ["app/templates/app/invoices.html"]
setups = ["empty"]

[[screen]]
slug = "people"
templates = ["app/templates/app/people.html"]
setups = ["empty"]
'''
FILES = {
    'app/templates/app/base.html': '<link rel="stylesheet" href="{% static \'site.css\' %}">'
                                   '<script src="/static/everywhere.js"></script>{% block main %}{% endblock %}',
    'app/templates/app/orders.html': '{% extends "app/base.html" %}{% block main %}'
                                     '<table class="orders-table pill-{{ state }}"></table>'
                                     '<script src="/static/orders.js"></script>{% endblock %}',
    'app/templates/app/invoices.html': '{% extends "app/base.html" %}{% block main %}'
                                       '{% include "app/_dup_flag.html" %}{% endblock %}',
    'app/templates/app/_dup_flag.html': '<div class="dupflag"><button class="btn">Withdraw</button></div>',
    'app/templates/app/people.html': '{% extends "app/base.html" %}{% block main %}'
                                     '<ul class="roster" style="color: var(--roster-ink)"></ul>{% endblock %}',
    'app/templates/app/_orphan.html': '<p class="orphan">nobody includes me</p>',
    'app/views.py': 'def page():\n    """Mentions dupflag in a docstring only."""\n    return "btn-primary"\n',
    'static/everywhere.js': 'document.body.dataset.ready = 1;',
    'static/orders.js': 'import "./orders-helper.js";',
    'static/orders-helper.js': 'el.classList.add("is-open");',
    'static/site.css': ':root { --ink: #111; --roster-ink: #222; }\n'
                       '.orders-table { width: 100%; }\n'
                       '.dupflag .btn { white-space: nowrap; }\n'
                       '.roster { color: var(--ink); }\n'
                       '.is-open { display: block; }\n'
                       '.pill-open { color: green; }\n'
                       '@media (max-width: 600px) { .orders-table { width: auto; } }\n',
    'screens.toml': SCREENS,
    'surface-review.toml': CONFIG,
}


def git(app, *args):
    subprocess.run(['git', '-C', str(app), *args], check=True, capture_output=True)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.app = Path(tempfile.mkdtemp())
        for path, text in FILES.items():
            (self.app / path).parent.mkdir(parents=True, exist_ok=True)
            (self.app / path).write_text(text, encoding='utf-8')
        git(self.app, 'init', '-q', '-b', 'main')
        git(self.app, '-c', 'user.email=t@t', '-c', 'user.name=t', 'add', '-A')
        git(self.app, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'base')

    def change(self, path, text=None, append=None):
        p = self.app / path
        p.write_text(text if text is not None else p.read_text(encoding='utf-8') + append, encoding='utf-8')

    def select(self, **select_cfg):
        cfg, screens = lint.load_config(self.app)
        if select_cfg:
            cfg['select'] = select_cfg
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            picked, why = lint.select_screens(self.app, cfg, screens, 'HEAD')
        return sorted(s['slug'] for s in picked), out.getvalue()

    # templates
    def test_changed_partial_selects_only_the_pages_that_include_it(self):
        self.change('app/templates/app/_dup_flag.html', append='<p>more</p>')
        picked, out = self.select()
        self.assertEqual(picked, ['invoices'])
        self.assertIn('invoices: app/templates/app/_dup_flag.html', out)

    def test_changed_base_template_selects_every_page_extending_it(self):
        self.change('app/templates/app/base.html', append='<footer></footer>')
        self.assertEqual(self.select()[0], ['invoices', 'orders', 'people'])

    def test_a_template_no_page_reaches_lints_everything(self):
        self.change('app/templates/app/_orphan.html', append='!')
        picked, out = self.select()
        self.assertEqual(len(picked), 3)
        self.assertIn('no template reaches it', out)

    def test_a_partial_app_code_names_lints_everything(self):
        self.change('app/views.py', 'def f():\n    return render("app/_dup_flag.html")\n')
        self.change('app/templates/app/_dup_flag.html', append='!')
        picked, out = self.select()
        self.assertEqual(len(picked), 3)
        self.assertIn('named in app code', out)

    def test_a_deleted_shared_file_lints_everything(self):
        (self.app / 'static/orders-helper.js').unlink()
        self.assertEqual(len(self.select()[0]), 3)

    # scripts
    def test_changed_script_selects_the_pages_that_load_it_even_through_another_script(self):
        self.change('static/orders-helper.js', append='\n// tweak')
        picked, out = self.select()
        self.assertEqual(picked, ['orders'])
        self.assertIn('via static/orders.js', out)

    def test_a_script_base_loads_selects_every_page(self):
        self.change('static/everywhere.js', append='\n// tweak')
        self.assertEqual(self.select()[0], ['invoices', 'orders', 'people'])

    # stylesheets
    def test_changed_class_rule_selects_only_pages_carrying_the_class(self):
        self.change('static/site.css', append='.orders-table td { padding: 0; }\n')
        picked, out = self.select()
        self.assertEqual(picked, ['orders'])
        self.assertIn('.orders-table td', out)

    def test_a_token_app_code_builds_narrows_nothing_but_the_other_token_still_does(self):
        # app code names `btn` (it may be on any page); `dupflag` is only in a template, and the
        # rule needs both, so only the page carrying `dupflag` is selected.
        self.change('app/views.py', 'CLS = "btn"\n')
        self.change('static/site.css', append='.dupflag .btn { color: red; }\n')
        self.assertEqual(self.select()[0], ['invoices'])

    def test_a_docstring_does_not_count_as_app_code(self):
        self.change('static/site.css', append='.dupflag { margin: 0; }\n')
        self.assertEqual(self.select()[0], ['invoices'])

    def test_a_class_composed_in_a_template_counts(self):
        self.change('static/site.css', append='.pill-shipped { color: blue; }\n')
        self.assertEqual(self.select()[0], ['orders'])

    def test_a_class_a_loaded_script_adds_counts(self):
        self.change('static/site.css', append='.is-open { display: flex; }\n')
        self.assertEqual(self.select()[0], ['orders'])

    def test_a_rule_inside_media_is_attributed_by_its_selector(self):
        self.change('static/site.css', FILES['static/site.css'].replace('width: auto', 'width: 50%'))
        self.assertEqual(self.select()[0], ['orders'])

    def test_element_universal_and_root_selectors_lint_everything(self):
        for rule in ('button { margin: 0; }', '* { box-sizing: border-box; }', ':root { color: red; }',
                     '::placeholder { color: grey; }', ':is(.a, .b) { color: red; }'):
            with self.subTest(rule=rule):
                self.change('static/site.css', FILES['static/site.css'] + rule + '\n')
                picked, out = self.select()
                self.assertEqual(len(picked), 3, out)
                self.assertIn('element, universal or :root', out)

    def test_at_rules_it_cannot_attribute_lint_everything(self):
        for rule in ('@font-face { font-family: X; src: url(x.woff2); }', '@layer base, app;',
                     '@keyframes spin { to { transform: rotate(1turn); } }', '@import "other.css";'):
            with self.subTest(rule=rule):
                self.change('static/site.css', FILES['static/site.css'] + rule + '\n')
                self.assertEqual(len(self.select()[0]), 3)

    def test_an_unparseable_stylesheet_lints_everything(self):
        self.change('static/site.css', append='.broken { color: red;\n')
        picked, out = self.select()
        self.assertEqual(len(picked), 3)
        self.assertIn('unbalanced', out)

    def test_a_root_custom_property_selects_the_pages_reading_it(self):
        self.change('static/site.css', FILES['static/site.css'].replace('--ink: #111', '--ink: #000'))
        picked, out = self.select()
        self.assertEqual(picked, ['people'])
        self.assertIn('--ink', out)

    def test_a_custom_property_used_inline_in_a_template_counts(self):
        self.change('static/site.css', FILES['static/site.css'].replace('--roster-ink: #222', '--roster-ink: #333'))
        self.assertEqual(self.select()[0], ['people'])

    def test_a_widely_read_custom_property_lints_everything(self):
        self.change('static/site.css', FILES['static/site.css'].replace('--ink: #111', '--ink: #000'))
        picked, out = self.select(css_var_fanout_max=0)
        self.assertEqual(len(picked), 3)
        self.assertIn('widely-used token', out)

    def test_shared_all_mode_keeps_the_old_rule(self):
        self.change('app/templates/app/_dup_flag.html', append='<p>more</p>')
        self.assertEqual(len(self.select(mode='shared-all')[0]), 3)


class TokenTests(unittest.TestCase):
    def test_required_tokens_skip_functional_pseudo_classes_and_attributes(self):
        self.assertEqual(lint.required_tokens('.a:not(.b) > .c'), {'a', 'c'})
        self.assertEqual(lint.required_tokens('#x .y[data-k=".z"]'), {'x', 'y'})
        self.assertEqual(lint.required_tokens(':is(.a, .b)'), set())
        self.assertEqual(lint.required_tokens('a:hover'), set())

    def test_css_items_understand_nesting_contexts_and_strings(self):
        items = lint.css_items('@media (x) { .a { content: "}"; } }\n.b { .c & { d: e; } }')
        self.assertEqual([(i[0], i[1], i[2]) for i in items],
                         [(('@media (x)',), 'rule', '.a'), ((), 'rule', '.b')])


class SeedBatchTests(unittest.TestCase):
    def run_batch(self, script):
        data = Path(tempfile.mkdtemp())
        (data / 'seed.py').write_text(script, encoding='utf-8')
        cfg = {'lint': {'seed_batch': [sys.executable, str(data / 'seed.py'), '{batch_file}']}}
        return lint.seed_batch(cfg, data, None, {}, data, [('a', 'empty'), ('a', 'typical'), ('b', 'empty')])

    def test_every_setup_seeded_in_one_process_in_order(self):
        urls = self.run_batch('import json, sys\n'
                              'for i, r in enumerate(json.load(open(sys.argv[1]))):\n'
                              '    print(json.dumps({**r, "url": f"/{r[\'screen\']}/{i}"}))\n')
        self.assertEqual(urls, {('a', 'empty'): '/a/0', ('a', 'typical'): '/a/1', ('b', 'empty'): '/b/2'})

    def test_a_failing_setup_is_reported_by_name_and_a_missing_one_too(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(err):
            self.run_batch('import json, sys\n'
                           'rows = json.load(open(sys.argv[1]))\n'
                           'print(json.dumps({**rows[0], "url": "/ok"}))\n'
                           'print(json.dumps({**rows[1], "error": "KeyError: nope"}))\n'
                           'sys.exit(1)\n')
        msg = str(stop.exception.code)
        self.assertIn('seed a typical: KeyError: nope', msg)
        self.assertIn('seed b empty: printed no result', msg)
        self.assertNotIn('seed a empty', msg)


if __name__ == '__main__':
    unittest.main()
