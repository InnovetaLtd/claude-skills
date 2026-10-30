"""Tests for check_surface_reviews.py (stdlib only):  python -m unittest test_check_surface_reviews

Each test builds a tiny app in a temp folder: a config, a registry, page templates and records."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_surface_reviews as gate

CONFIG = '''plugin_repo = "x"
plugin_ref = "y"
registry = "screens.toml"
records = "records"
unregistered = "records/_unregistered.txt"
lint_baseline = "records/_lint_baseline.json"
page_templates = ["templates/**/*.html"]
page_marker = "{% extends"
shared = ["templates/**/*.html"]
'''
SCREEN = '''[[screen]]
slug = "orders"
templates = ["templates/orders.html"]
who = "w"
job = "j"
questions = ["q"]
done = "d"
answer = "h1"
setups = ["empty", "typical"]
'''


class GateTests(unittest.TestCase):
    def setUp(self):
        self.app = Path(tempfile.mkdtemp())
        (self.app / 'templates').mkdir()
        (self.app / 'records').mkdir()
        (self.app / 'surface-review.toml').write_text(CONFIG)
        (self.app / 'screens.toml').write_text(SCREEN)
        (self.app / 'templates' / 'orders.html').write_text('{% extends "base.html" %}orders')
        (self.app / 'templates' / '_row.html').write_text('a shared include')
        (self.app / 'records' / '_unregistered.txt').write_text('')

    def record(self, *, kind='review', findings='', fingerprint=None, reason=''):
        fp = fingerprint or gate.fingerprint(self.app, ['templates/orders.html'])
        reason = f'reason = "{reason}"\n' if reason else ''
        (self.app / 'records' / 'orders.md').write_text(
            '+++\nscreen = "orders"\n\n[[entry]]\nkind = "review"\nfingerprint = "old"\n\n'
            f'[[entry]]\nkind = "{kind}"\nfingerprint = "{fp}"\n{reason}{findings}+++\n# prose\n')

    def run_gate(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main(['--app', str(self.app), *extra])
        return code, out.getvalue()

    def test_a_reviewed_screen_passes_and_line_endings_do_not_matter(self):
        self.record()
        self.assertEqual(self.run_gate()[0], 0)
        (self.app / 'templates' / 'orders.html').write_bytes(b'{% extends "base.html" %}orders'.replace(b'\n', b'\r\n'))
        self.assertEqual(self.run_gate()[0], 0)

    def test_a_new_page_must_register(self):
        self.record()
        (self.app / 'templates' / 'invoices.html').write_text('{% extends "base.html" %}')
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn('templates/invoices.html is a new screen', out)

    def test_a_screen_changed_after_its_review_is_refused_unless_an_na_says_why(self):
        self.record()
        (self.app / 'templates' / 'orders.html').write_text('{% extends "base.html" %}orders, changed')
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn('orders: changed since its last review', out)
        self.record(kind='na', reason='typo in a heading')
        code, out = self.run_gate()
        self.assertEqual(code, 0)
        self.assertIn('n/a - typo in a heading', out)

    def test_findings_need_an_outcome_and_only_minor_may_be_waived(self):
        self.record(findings='[[entry.finding]]\nid = "1"\nseverity = "moderate"\noutcome = "waived"\nreason = "r"\n'
                             '[[entry.finding]]\nid = "2"\nseverity = "minor"\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn('orders finding 1: only a minor finding may be waived', out)
        self.assertIn('orders finding 2: has no outcome', out)

    def test_an_unregistered_page_must_register_when_touched_and_the_list_entry_goes_when_stale(self):
        self.record()
        (self.app / 'templates' / 'legacy.html').write_text('{% extends "base.html" %}old')
        fp = gate.fingerprint(self.app, ['templates/legacy.html'])
        (self.app / 'records' / '_unregistered.txt').write_text(f'templates/legacy.html {fp}\ntemplates/gone.html x\n')
        code, out = self.run_gate()
        self.assertIn('templates/gone.html is no longer a page template', out)
        (self.app / 'records' / '_unregistered.txt').write_text(f'templates/legacy.html {fp}\n')
        self.assertEqual(self.run_gate()[0], 0)
        (self.app / 'templates' / 'legacy.html').write_text('{% extends "base.html" %}touched')
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn('templates/legacy.html changed but is not registered', out)

    def test_the_lists_only_shrink_against_the_base(self):
        self.record()
        (self.app / 'records' / '_lint_baseline.json').write_text(json.dumps(['a']))
        for cmd in (['init', '-q'], ['add', '-A'], ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base']):
            subprocess.run(['git', *cmd], cwd=self.app, check=True)
        (self.app / 'records' / '_lint_baseline.json').write_text(json.dumps(['a', 'b']))
        code, out = self.run_gate('--base', 'HEAD')
        self.assertEqual(code, 1)
        self.assertIn('lint baseline grew: b', out)


if __name__ == '__main__':
    unittest.main()
