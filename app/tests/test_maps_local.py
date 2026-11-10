"""Public/synthetic map integration and the local model route contract. No live calls."""
import copy
import json
import pathlib
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from xml.etree import ElementTree as ET

from app.tests import helpers
from atelier_app import drafting, engine, views
from atelier_engine import maps


class MapsTest(unittest.TestCase):
    def test_register_embeds_both_engine_maps_with_calibration_orientation(self):
        app, directory = helpers.make_app()
        try:
            c = helpers.Client(app)
            c.login()
            sid = c.load_example()
            cal = engine.load_cal('anssi-v1.5')
            cal['map_orientation'] = 'likelihood-rows'
            cal['name'] = '<script>not executable</script>'
            with mock.patch.object(engine.calibration, 'load', return_value=cal), \
                 mock.patch.object(maps, 'svg', wraps=maps.svg) as svg:
                response = c.get(f'/s/{sid}/register')
            body = c.text(response)
            self.assertEqual(response.status, 200)
            self.assertEqual(body.count('<svg '), 2)
            self.assertIn('class="engine-maps"', body)
            self.assertNotIn('<script>not executable', body)
            self.assertIn('&lt;script&gt;not executable', body)
            self.assertEqual([x.kwargs['stage'] for x in svg.call_args_list], ['now', 'target'])
            self.assertEqual([x.kwargs['orientation'] for x in svg.call_args_list], ['likelihood-rows'] * 2)
            # Exact SVG bytes and calibration orientation, not a copied app implementation.
            st = helpers.example_json()
            rows, _ = engine.register(st, cal)
            for stage, title in (('now', 'Now'), ('target', 'At target')):
                self.assertIn(maps.svg(rows, cal, stage, title, 'likelihood-rows'), body)
        finally:
            helpers.cleanup(directory)

    def test_synthetic_four_levels_and_both_orientations_place_risk_in_correct_cell(self):
        cal = copy.deepcopy(helpers.SYNTH_CAL)
        rows = [{'id': 'R-check', 'severity': 4, 'likelihood': 3, 'likelihood_target': 1}]
        ns = {'s': 'http://www.w3.org/2000/svg'}
        for orientation in ('severity-rows', 'likelihood-rows'):
            cal['map_orientation'] = orientation
            for stage, likelihood in (('now', 3), ('target', 1)):
                root = ET.fromstring(engine.risk_map(rows, cal, stage, stage))
                chip = next(x for x in root.findall('s:text', ns) if x.text == 'R-check')
                row = 4 if orientation == 'severity-rows' else likelihood
                col = likelihood if orientation == 'severity-rows' else 4
                self.assertEqual(float(chip.attrib['x']), 150 + (col - 1) * 150 + 75)
                self.assertEqual(float(chip.attrib['y']), 70 + (4 - row) * 90 + 22)
                rects = root.findall('s:rect', ns)
                self.assertEqual(len(rects), 16)
                self.assertEqual(len(set(x.attrib['fill'] for x in rects)), 4)


    def test_colour_attribute_injection_is_neutralised_without_changing_calibration(self):
        cal = copy.deepcopy(helpers.SYNTH_CAL)
        bad = 'FFFFFF" onload="alert(1)'
        cal['levels'][0]['colour'] = bad
        root = ET.fromstring(engine.risk_map([], cal, 'now', 'Synthetic'))
        svg = ET.tostring(root, encoding='unicode')
        self.assertNotIn('onload', svg)
        self.assertNotIn('alert(1)', svg)
        self.assertIn('#BBBBBB', svg)
        self.assertEqual(cal['levels'][0]['colour'], bad)


class LocalContractTest(unittest.TestCase):
    def settings(self):
        return drafting.normalise({'route': 'local', 'local': {'port': 11434, 'model': 'local-test'},
                                   'timeout': 1, 'limits': {'max_output_tokens': 8192}})

    def test_wire_parameters_and_timeout(self):
        s = self.settings()
        reply = json.dumps({'choices': [{'message': {'content': '{}'}}]}).encode()
        with mock.patch.object(drafting, '_post', return_value=(200, reply)) as post:
            drafting.complete(s, 'system', 'public synthetic text')
        payload = json.loads(post.call_args.args[1])
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(payload['max_tokens'], 4096)
        self.assertEqual(post.call_args.args[3], 360)
        self.assertFalse(payload['stream'])

    def test_one_local_request_at_a_time_across_adapters(self):
        state = {'active': 0, 'peak': 0, 'calls': 0}
        guard = threading.Lock()
        def post(*args):
            with guard:
                state['active'] += 1
                state['calls'] += 1
                state['peak'] = max(state['peak'], state['active'])
            time.sleep(0.03)
            with guard:
                state['active'] -= 1
            return 200, json.dumps({'choices': [{'message': {'content': '{}'}}]}).encode()
        with mock.patch.object(drafting, '_post', side_effect=post), ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _: drafting.complete(self.settings(), 's', 'u'), range(4)))
        self.assertEqual(state, {'active': 0, 'peak': 1, 'calls': 4})

    def test_impossible_context_budget_refused_before_network(self):
        d = drafting.Drafter({'route': 'local', 'local': {'port': 11434, 'model': 'test'},
                             'limits': {'context_tokens': 1024, 'max_output_tokens': 4096}})
        with mock.patch.object(drafting, '_post') as post:
            with self.assertRaisesRegex(drafting.DraftError, 'context is too small'):
                d.draft('w1', {'text': 'Invented text', 'private': False})
            post.assert_not_called()

    def test_progressive_drafting_state_exists_without_inline_script(self):
        app, directory = helpers.make_app()
        try:
            c = helpers.Client(app)
            c.login()
            sid = c.load_example()
            for n in range(1, 6):
                page = c.text(c.get(f'/s/{sid}/w{n}'))
                self.assertIn('class="draft-progress" role="status" hidden', page)
                self.assertIn('Drafting...', page)
            js = (helpers.APP_DIR / 'static/app.js').read_text()
            self.assertIn('status.hidden = false', js)
            self.assertIn('btn.disabled = true', js)
        finally:
            helpers.cleanup(directory)
