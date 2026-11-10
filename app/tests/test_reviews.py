"""Review HTTP routes on synthetic workbook + temp plugin, never on private fixtures."""
import copy
import io
import json
import os
import pathlib
import re
import shutil
import unittest
from unittest.mock import patch

from .helpers import Client, HAVE_OPENPYXL, cleanup, make_app, multipart
from .review_fixture import install_stub, workbook
from atelier_app import calibrations, engine
from atelier_app.storage import NotFound


@unittest.skipUnless(HAVE_OPENPYXL, 'xlsx imports need openpyxl')
class Reviews(unittest.TestCase):
    def setUp(self):
        self.app, self.d = make_app()
        install_stub(self.app.private_dir)
        self.c = Client(self.app)
        self.c.login()
        self.csrf = self.c.csrf('/reviews')

    def tearDown(self):
        cleanup(self.d)

    def upload(self, data=None, filename='invented.xlsx', **fields):
        body, ctype = multipart({'csrf': self.csrf, 'calibration': 'anssi-v1.5', **fields},
                                {'file': (filename, workbook() if data is None else data)})
        return self.c.req('POST', '/reviews', body=body, ctype=ctype)

    def create(self):
        r = self.upload(name='Fictional workshop review', layout='synthetic-register')
        self.assertEqual(r.status, 303, r.body)
        self.base = r.get('Location')
        self.rid = self.base.split('/')[-1]
        return self.rid

    def test_import_report_register_maps(self):
        self.create()
        r = self.c.get(self.base)
        self.assertEqual(r.status, 200, r.body)
        for text in ('synthetic-register', 'risks_columns', 'pictures', 'stages', 'Import errors (0)', 'Risk register',
                     'Risk map: now', 'Risk map: target', 'Risk map: initial', '&lt;script&gt;'):
            self.assertIn(text, r.body.decode())
        self.assertNotIn('<script>alert', r.body.decode())
        self.assertIn("form-action 'self'", r.get('Content-Security-Policy'))
        state = self.app.reviews.load(self.rid)
        self.assertEqual(state['study']['study']['mode'], 'review')
        p = self.app.reviews.directory(self.rid)
        self.assertEqual(p.stat().st_mode & 0o777, 0o700)
        for name in ('upload.xlsx', 'state.json'):
            self.assertEqual((p / name).stat().st_mode & 0o777, 0o600)
        self.assertIn(b'Fictional workshop review', self.c.get('/reviews').body)

    def test_upload_bytes_exact(self):
        raw = workbook()
        r = self.upload(data=raw)
        self.assertEqual(r.status, 303)
        rid = r.get('Location').split('/')[-1]
        self.assertEqual((self.app.reviews.directory(rid) / 'upload.xlsx').read_bytes(), raw)

    def test_caps_types_and_bad_workbooks(self):
        for data, filename, code, message in ((b'x', 'bad.txt', 400, 'Only .xlsx'),
                                               (b'x', 'bad.xlsx', 400, 'not an xlsx'),
                                               (b'', 'empty.xlsx', 400, 'Choose an xlsx'),
                                               (b'x' * (20 * 1024 * 1024 + 1), 'large.xlsx', 413, 'exceeds 20 MB')):
            with self.subTest(filename=filename, code=code):
                r = self.upload(data=data, filename=filename)
                self.assertEqual(r.status, code)
                self.assertIn(message, r.body.decode())
        self.assertEqual(self.app.reviews.list(), [])
        r = self.c.req('POST', '/reviews', body=b'x' * (self.app.body_limit('/reviews') + 1))
        self.assertEqual(r.status, 413)

    def test_size_boundary(self):
        with patch.object(engine, 'import_review', wraps=engine.import_review) as imported:
            r = self.upload(data=b'x' * (20 * 1024 * 1024))
            self.assertEqual(r.status, 400)  # permitted size, rejected content by engine
            self.assertEqual(imported.call_count, 1)

    def test_expanded_zip_limit(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in range(3001):
                z.writestr(f'f{i}', '')
        r = self.upload(data=buf.getvalue())
        self.assertEqual(r.status, 400)
        self.assertIn(b'safe import limit', r.body)

    def test_engine_spreadsheet_error(self):
        from atelier_engine import importer
        with patch.object(importer, 'read_xlsx', side_effect=importer.SpreadsheetError('synthetic no risk rows <bad>')):
            r = self.upload()
        self.assertEqual(r.status, 400)
        self.assertIn(b'synthetic no risk rows &lt;bad&gt;', r.body)
        self.assertEqual(self.app.reviews.list(), [])

    def test_report_errors_block_notes_do_not(self):
        self.create()
        state = self.app.reviews.load(self.rid)
        state['report']['notes'].append('Synthetic note <tag>')
        state['report']['findings'].append({'message': 'Synthetic inconsistency <tag>'})
        self.app.reviews.save(self.rid, state)
        body = self.c.get(self.base).body
        self.assertIn(b'Synthetic note &lt;tag&gt;', body)
        self.assertIn(b'Synthetic inconsistency &lt;tag&gt;', body)
        self.assertEqual(self.c.get(self.base + '/ratings').status, 200)
        state['report']['errors'].append('Synthetic unread cell')
        self.app.reviews.save(self.rid, state)
        plugin = engine.review_plugin(self.app.private_dir)
        with patch.object(plugin, 'review', side_effect=AssertionError('incomplete import must not be scored')):
            r = self.c.get(self.base)
        self.assertEqual(r.status, 200)
        self.assertIn(b'Import errors block', r.body)
        self.assertNotIn(b'<svg', r.body)
        for suffix in ('/ratings', '/result', '/export.json', '/export.xlsx'):
            self.assertEqual(self.c.get(self.base + suffix).status, 409)
        self.assertEqual(self.c.post(self.base + '/ratings', {'csrf': self.csrf, 'status_C01': 'S'}).status, 409)

    def test_rating_roundtrip_override_and_atomic_idempotence(self):
        self.create()
        r = self.c.get(self.base + '/ratings')
        body = r.body.decode()
        self.assertEqual(r.status, 200)
        self.assertEqual(len(re.findall(r'<article class="rating-row"', body)), 66)
        self.assertIn('Synthetic evidence &lt;example&gt; &amp; explanation', body)
        self.assertIn('<option value="S" selected>', body)
        self.assertIn('Axis 1 · Workshop 1', body)
        result = self.c.get(self.base + '/result').body.decode()
        self.assertIn('Unrated: 54', result)
        self.assertNotIn('<h3>Score:', result)
        self.assertIn('/ratings#criterion-C66', result)
        form = {'csrf': self.csrf, 'status_C01': 'N', 'note_C01': '<img src=x onerror=alert(1)>'}
        r = self.c.post(self.base + '/ratings', form)
        self.assertEqual(r.status, 303)
        state = self.app.reviews.load(self.rid)
        self.assertEqual(state['ratings'], {'C01': 'N'})
        result = engine.review_result(state, engine.load_cal('anssi-v1.5'), engine.review_plugin(self.app.private_dir))
        self.assertEqual(result['sources']['C01'], 'reviewer')
        self.assertEqual(result['ratings']['C01'], 'N')
        path = self.app.reviews.directory(self.rid) / 'state.json'
        before, mtime = path.read_bytes(), path.stat().st_mtime_ns
        self.assertEqual(self.c.post(self.base + '/ratings', form).status, 303)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertIn(b'&lt;img src=x onerror=alert(1)&gt;', self.c.get(self.base + '/result').body)
        with patch('atelier_app.review_store.atomic_write', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                self.app.reviews.save(self.rid, dict(state, notes={}))
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_status_kept_and_nothing_saved(self):
        self.create()
        path = self.app.reviews.directory(self.rid) / 'state.json'
        before = path.read_bytes()
        r = self.c.post(self.base + '/ratings', {'csrf': self.csrf, 'status_C01': 'bad<script>',
                                                 'note_C01': 'typed <note>', 'status_C02': 'P'})
        self.assertEqual(r.status, 400)
        self.assertIn(b'invalid status: bad&lt;script&gt;', r.body)
        self.assertIn(b'<option value="bad&lt;script&gt;" selected>', r.body)
        self.assertIn(b'typed &lt;note&gt;', r.body)
        self.assertIn(b'<option value="P" selected>', r.body)
        self.assertEqual(path.read_bytes(), before)

    def test_score_and_exports(self):
        self.create()
        form = {f'status_C{i:02}': 'NA' if i == 66 else 'S' for i in range(1, 67)}
        r = self.c.post(self.base + '/ratings', {'csrf': self.csrf, **form})
        self.assertEqual(r.status, 303)
        r = self.c.get(self.base + '/result')
        self.assertIn(b'Score: 72', r.body)
        self.assertIn(b'Confidence: 81%', r.body)
        self.assertIn(b'Invented major finding', r.body)
        self.assertIn(b'reviewer', r.body)
        self.assertNotIn(b'Unrated: ', r.body)
        j = self.c.get(self.base + '/export.json')
        self.assertEqual(j.status, 200)
        self.assertEqual(json.loads(j.body)['study']['mode'], 'review')
        x = self.c.get(self.base + '/export.xlsx')
        self.assertEqual(x.status, 200)
        self.assertIn('attachment;', x.get('Content-Disposition'))
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(x.body))
        self.assertEqual(wb.sheetnames, ['Summary', 'Findings', 'Risk levels', 'Measures', 'Not checked'])
        self.assertEqual(wb['Summary'].cell(2, 2).value, 72)
        wb.close()
        self.assertEqual(sorted(p.name for p in self.app.reviews.directory(self.rid).iterdir()), ['state.json', 'upload.xlsx'])

    def test_confidence_only_when_returned(self):
        self.create()
        result = engine.review_result(self.app.reviews.load(self.rid), engine.load_cal('anssi-v1.5'),
                                      engine.review_plugin(self.app.private_dir))
        result['score'] = {'final_score': 0, 'confidence': None, 'findings': {}}
        with patch.object(engine, 'review_result', return_value=result):
            r = self.c.get(self.base + '/result')
        self.assertEqual(r.status, 200)
        self.assertIn(b'Score: 0', r.body)
        self.assertNotIn(b'Confidence:', r.body)

    def test_unknown_calibration_and_layout(self):
        self.assertEqual(self.upload(calibration='unknown').status, 400)
        self.assertEqual(self.upload(layout='../../layout').status, 400)
        self.assertEqual(self.app.reviews.list(), [])

    def test_no_plugin_hides_scoring(self):
        self.create()
        # Load it first, then remove the disposable install: a stale import cache must not enable scoring.
        self.assertIsNotNone(engine.review_plugin(self.app.private_dir))
        shutil.rmtree(self.app.private_dir / 'plugins')
        self.assertIsNone(engine.review_plugin(self.app.private_dir))
        r = self.c.get(self.base + '/result')
        self.assertEqual(r.status, 200)
        self.assertIn(b'Review plugin unavailable', r.body)
        self.assertIn(b'Risk map: now', r.body)
        self.assertNotIn(b'Score:', r.body)
        self.assertNotIn(b'Download review Excel', r.body)
        self.assertEqual(self.c.get(self.base + '/ratings').status, 409)
        self.assertEqual(self.c.get(self.base + '/export.xlsx').status, 409)
        self.assertEqual(self.c.get(self.base + '/export.json').status, 200)

    def test_csrf_auth_host_and_traversal(self):
        self.create()
        for path in ('/reviews', self.base + '/ratings', self.base + '/delete'):
            self.assertEqual(self.c.post(path, {}).status, 403)
        for path in ('/reviews', self.base, self.base + '/ratings', self.base + '/result', self.base + '/export.xlsx'):
            self.assertEqual(Client(self.app).get(path).status, 303)
            self.assertEqual(self.c.get(path, host='hostile.example').status, 421)
        for path in ('/r/../../token', '/r/%2e%2e%2fprivate', self.base + '%2f..', self.base + '/../../token'):
            self.assertEqual(self.c.get(path).status, 404)
        for rid in ('../private', '%2e%2e', 'r-00000000-aaaaaaaaaaaaaaaa/..'):
            with self.assertRaises(NotFound):
                self.app.reviews.load(rid)
        self.assertEqual(self.c.post(self.base + '/delete', {'csrf': self.csrf}).status, 303)
        self.assertEqual(self.c.get(self.base).status, 404)
        self.assertEqual(self.app.reviews.list(), [])

    def test_private_calibration_confidential_and_no_drafting_route(self):
        from .helpers import SYNTH_CAL, SYNTH_ID
        (self.app.private_dir / (SYNTH_ID + '.json')).write_text(json.dumps(SYNTH_CAL))
        r = self.upload(calibration=SYNTH_ID)
        self.assertEqual(r.status, 303)
        base = r.get('Location')
        st = self.app.reviews.load(base.split('/')[-1])['study']
        self.assertTrue(st['study']['confidential'])
        self.assertTrue(calibrations.study_privacy(st)[0])
        self.assertEqual(self.c.post(base + '/draft', {'csrf': self.csrf}).status, 404)
        self.assertIn(b'Confidential:', self.c.get(base).body)
