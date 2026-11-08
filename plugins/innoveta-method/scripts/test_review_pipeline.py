"""Tests for the review pipeline's pure parts (stdlib only):  python -m unittest test_review_pipeline

surface_record's walk list and checklist page, and review_report's reading of the records. Recording
itself needs a browser and a running app; it is proved by a real run, not here."""
import json
import tempfile
import unittest
from pathlib import Path

import review_report
import surface_record

SCREENS = [
    {'slug': 'order', 'title': 'Order', 'setups': ['empty', 'typical', 'S22'], 'job': 'Log the order',
     'flow': [{'name': 'S22-held', 'setup': 'S22', 'sees': 'Acknowledge is refused',
               'steps': [{'shot': 'the order'}]}]},
    {'slug': 'ack', 'title': 'Acknowledgement', 'setups': ['empty', 'typical'], 'job': 'Issue the ack'},
]


class WalkListTests(unittest.TestCase):
    def test_flows_then_plan_then_stills_for_what_no_flow_covers(self):
        plan = [{'screen': 'ack', 'setup': 'empty', 'name': 'adhoc', 'sees': 's', 'steps': [{'shot': 'x'}]}]
        walks = surface_record.walks_for(SCREENS, plan, stills=True)
        self.assertEqual([w['key'] for w in walks],
                         ['order/S22-held', 'ack/adhoc', 'order/typical-desk', 'order/typical-phone',
                          'ack/typical-desk', 'ack/typical-phone'])
        self.assertEqual(walks[0]['viewport'], 'desk')
        self.assertEqual(walks[3]['viewport'], 'phone')

    def test_no_stills_unless_asked(self):
        self.assertEqual([w['key'] for w in surface_record.walks_for(SCREENS, [], stills=False)],
                         ['order/S22-held'])


class PageTests(unittest.TestCase):
    def manifest(self, digests, label=''):
        return {'walks': [{'key': 'order/S22-held', 'sees': 'Acknowledge is refused',
                           'shots': [{'file': f'{label}w001-{n}.jpg', 'caption': f'step {n}', 'sha256': d,
                                      'stopped': False} for n, d in enumerate(digests, 1)]}]}

    def page_data(self, html):
        return json.loads(html.split('<script id="walk-data" type="application/json">')[1].split('</script>')[0])

    def test_pictures_pair_with_their_before_and_identical_ones_say_so(self):
        walk = {'title': 'T <b>', 'checks': [{'n': 1, 'title': 'Held ack', 'walks': ['order/S22-held', 'order/gone']}]}
        html = surface_record.build_page(walk, self.manifest(['a', 'b', 'c']), self.manifest(['a', 'z'], 'before-'),
                                         {'w001-1.jpg': '/_blob/1', 'w001-2.jpg': '/_blob/2', 'w001-3.jpg': '/_blob/3',
                                          'before-w001-1.jpg': '/_blob/b1', 'before-w001-2.jpg': '/_blob/b2'})
        self.assertIn('<title>T &lt;b></title>', html)
        check = self.page_data(html)['checks'][0]
        self.assertEqual(check['see'], 'Acknowledge is refused')
        same, changed, new, missing = check['shots']
        self.assertTrue(same['same'])
        self.assertIsNone(same['before_url'])
        self.assertFalse(changed['same'])
        self.assertEqual(changed['before_url'], '/_blob/b2')
        self.assertEqual(changed['url'], '/_blob/2')
        self.assertFalse(new['same'])
        self.assertTrue(missing['stopped'])

    def test_a_script_close_in_the_data_cannot_end_the_page_script(self):
        walk = {'title': 'T', 'checks': [{'n': 1, 'title': '</script><script>alert(1)</script>'}]}
        html = surface_record.build_page(walk, {'walks': []})
        self.assertNotIn('</script><script>alert', html)


class ReportTests(unittest.TestCase):
    def test_the_leak_where_it_leaks_what_repeats_and_what_waits(self):
        app = Path(tempfile.mkdtemp())
        (app / 'records').mkdir()
        (app / 'surface-review.toml').write_text('registry = "screens.toml"\nrecords = "records"\n')
        entry = ('+++\n[[entry]]\nkind = "review"\ndate = "2026-11-01"\n'
                 '[[entry.finding]]\nid = "1"\nseverity = "minor"\noutcome = "fixed"\nrow = 5\n'
                 '[[entry]]\nkind = "walkthrough"\ndate = "2026-11-08"\n'
                 '[[entry.finding]]\nid = "w1"\nseverity = "moderate"\noutcome = "open"\ndoc = "d"\n'
                 'caught_by = "review"\nrow = 5\nwhat = "{what}"\n'
                 '[[entry.finding]]\nid = "w2"\nseverity = "minor"\noutcome = "parked"\ncaught_by = "taste"\n+++\n')
        (app / 'records' / 'order.md').write_text(entry.replace('{what}', 'act where you see it'))
        (app / 'records' / 'ack.md').write_text(entry.replace('{what}', 'a trip off the page'))
        (app / 'records' / '_unregistered.txt').write_text('')
        result = review_report.report(review_report.findings(app))
        self.assertEqual(result['leak'], {'2026-11-08': {'not taste': 2, 'taste': 2}})
        self.assertEqual(result['caught_by'], {'review': 2, 'taste': 2})
        self.assertEqual(result['promote'], {'checklist row 5': ['ack', 'order']})
        self.assertEqual(len(result['waiting']), 2)
        self.assertEqual(review_report.report(review_report.findings(app), since='2026-11-09')['leak'], {})


if __name__ == '__main__':
    unittest.main()
