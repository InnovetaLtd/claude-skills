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


class MarkTests(unittest.TestCase):
    """The diff aligns rows like a text diff, so only what changed is boxed, never the page below it."""

    def page(self, bands, width=200):
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (width, sum(h for h, _ in bands)), 'white')
        draw, y = ImageDraw.Draw(img), 0
        for height, colour in bands:
            if colour:
                draw.rectangle((20, y + 2, 120, y + height - 3), fill=colour)
            y += height
        return img

    def setUp(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest('Pillow is not installed')

    def test_an_inserted_band_is_boxed_and_the_shifted_page_below_is_not(self):
        before = self.page([(40, 'navy'), (40, 'teal'), (40, 'olive')])
        after = self.page([(40, 'navy'), (30, 'red'), (40, 'teal'), (40, 'olive')])
        on_after, on_before = surface_record.changed_boxes(after, before)
        self.assertEqual(len(on_after), 1)
        x0, y0, x1, y1 = on_after[0]
        self.assertTrue(36 <= y0 <= 42 and 67 <= y1 < 72, on_after)   # the red block (42-67), not the teal shifted to 72
        self.assertTrue(18 <= x0 <= 22 and 118 <= x1 <= 122, on_after)
        self.assertEqual(on_before, [])

    def test_a_change_in_place_is_boxed_on_both_and_a_removal_on_the_before(self):
        before = self.page([(40, 'navy'), (40, 'teal'), (40, 'olive')])
        changed = self.page([(40, 'navy'), (40, 'maroon'), (40, 'olive')])
        on_after, on_before = surface_record.changed_boxes(changed, before)
        self.assertEqual([b[1:4:2] for b in on_after], [b[1:4:2] for b in on_before])
        removed = self.page([(40, 'navy'), (40, 'olive')])
        on_after, on_before = surface_record.changed_boxes(removed, before)
        self.assertEqual(on_after, [])
        self.assertEqual(len(on_before), 1)

    def test_mark_writes_clean_views_and_keeps_the_boxes_as_fractions(self):
        import hashlib
        base = Path(tempfile.mkdtemp())
        for label, img in (('after', self.page([(40, 'navy'), (30, 'red'), (40, 'teal')])),
                           ('before', self.page([(40, 'navy'), (40, 'teal')]))):
            (base / label).mkdir()
            name = f'{label}-w001-1.png'
            img.save(base / label / name)
            digest = hashlib.sha256((base / label / name).read_bytes()).hexdigest()
            (base / label / 'manifest.json').write_text(json.dumps({'walks': [{'key': 'k', 'shots': [
                {'file': name, 'caption': 'c', 'sha256': digest, 'stopped': False}]}]}))
        surface_record.mark(base / 'after', base / 'before')
        shot = json.loads((base / 'after' / 'manifest.json').read_text())['walks'][0]['shots'][0]
        self.assertEqual(shot['view'], 'after-w001-1.jpg')
        self.assertEqual(shot['changes'], 1)
        x0, y0, x1, y1 = shot['boxes'][0]
        self.assertTrue(0 < x0 < x1 <= 1 and 0.3 < y0 < y1 < 0.7, shot['boxes'])
        from PIL import Image
        view = Image.open(base / 'after' / 'after-w001-1.jpg').convert('RGB')
        self.assertGreater(sum(view.getpixel((160, 55))), 740)   # inside the box's area, still white: nothing drawn in


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
