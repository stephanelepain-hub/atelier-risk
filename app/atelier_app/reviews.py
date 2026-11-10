"""Review HTTP handlers. No score or level arithmetic; all judgements go through engine.py."""
import copy
import json

from . import calibrations, engine, views_review
from .review_store import ID_PATTERN
from .web import HTTPError, Response, redirect

MAX_WORKBOOK = 20 * 1024 * 1024
MAX_BODY = MAX_WORKBOOK + 256 * 1024


class ReviewRoutes:
    def add_review_routes(self, router):
        router.add('GET', r'/reviews', self.review_list)
        router.add('POST', r'/reviews', self.review_upload)
        base = rf'/r/({ID_PATTERN})'
        router.add('GET', base, self.review_import)
        router.add('GET', base + r'/ratings', self.review_ratings)
        router.add('POST', base + r'/ratings', self.review_save_ratings)
        router.add('GET', base + r'/result', self.review_result)
        router.add('GET', base + r'/export\.json', self.review_json)
        router.add('GET', base + r'/export\.xlsx', self.review_excel)
        router.add('POST', base + r'/delete', self.review_delete)

    def review_list(self, req, error='', status=200):
        return Response(views_review.listing(self.reviews.list(), calibrations.catalogue(), engine.review_layouts(),
                                            req.session, error), status)

    def review_upload(self, req):
        upload = req.files.get('file')
        if not upload or not upload[1]:
            return self.review_list(req, 'Choose an xlsx workbook.', 400)
        filename, raw = upload
        if len(raw) > MAX_WORKBOOK:
            return self.review_list(req, 'Workbook exceeds 20 MB.', 413)
        if not filename.lower().endswith('.xlsx'):
            return self.review_list(req, 'Only .xlsx workbooks are accepted.', 400)
        cal_id = req.field('calibration') or calibrations.DEFAULT
        if not calibrations.exists(cal_id):
            return self.review_list(req, 'Unknown calibration.', 400)
        layout = req.field('layout') or None
        if layout and layout not in engine.review_layouts():
            return self.review_list(req, 'Unknown layout.', 400)
        try:
            cal = calibrations.load(cal_id)
            imported = engine.import_review(raw, cal, layout)
        except (engine.SpreadsheetError, RuntimeError, calibrations.CalibrationError, ValueError, OSError) as e:
            return self.review_list(req, f'Import refused: {e}', 400)
        st = imported['study']
        st['study']['name'] = req.field('name').strip()[:200] or 'Risk analysis review'
        if calibrations.kind(cal_id) == 'private' or engine.review_layouts().get(imported['report'].get('layout')) == 'private':
            st['study']['confidential'] = True
        state = {'study': st, 'report': imported['report'], 'ratings': {}, 'notes': {}}
        with self.edit_lock:
            rid = self.reviews.create(raw, state)
        return redirect(f'/r/{rid}')

    def _review_context(self, rid, require_clean=False):
        state = self.reviews.load(rid)
        if require_clean and state['report'].get('errors'):
            raise HTTPError(409, 'Import errors block ratings and export. Correct the workbook and import again.')
        try:
            cal = calibrations.load(calibrations.of_study(state['study']))
            plugin = engine.review_plugin(self.private_dir)
            result = engine.review_result(state, cal, plugin)
        except (ValueError, RuntimeError, OSError, ImportError) as e:
            raise HTTPError(409, f'The engine or review plugin refused this review: {e}') from None
        return state, cal, plugin, result

    def review_import(self, req, rid):
        state, cal, plugin, result = self._review_context(rid)
        return Response(views_review.import_page(rid, state, result, cal, req.session, plugin))

    def review_ratings(self, req, rid):
        state, cal, plugin, result = self._review_context(rid, True)
        if plugin is None:
            raise HTTPError(409, 'Review plugin unavailable; scoring is unavailable.')
        return Response(views_review.rating_page(rid, state, result, plugin.STATUSES, req.session))

    def review_save_ratings(self, req, rid):
        with self.edit_lock:
            state, cal, plugin, result = self._review_context(rid, True)
            if plugin is None:
                raise HTTPError(409, 'Review plugin unavailable; scoring is unavailable.')
            candidate = copy.deepcopy(state)
            # A partial POST changes only rows it names. A full form can explicitly clear a row with blank status.
            for criterion in result['criteria']:
                cid = criterion['id']
                if 'status_' + cid in req.form:
                    value = req.field('status_' + cid)
                    if value:
                        candidate['ratings'][cid] = value
                    else:
                        candidate['ratings'].pop(cid, None)
                if 'note_' + cid in req.form:
                    candidate['notes'][cid] = req.field('note_' + cid)[:4000]
            try:
                engine.review_result(candidate, cal, plugin)  # validate before touching any stored bytes
            except (ValueError, RuntimeError) as e:
                sticky = {k: v[0] for k, v in req.form.items() if k != 'csrf'}
                return Response(views_review.rating_page(rid, state, result, plugin.STATUSES, req.session,
                                                         f'The review plugin refused the rating: {e}', sticky), 400)
            if candidate != state:
                self.reviews.save(rid, candidate)
        return redirect(f'/r/{rid}/result')

    def review_result(self, req, rid):
        state, cal, plugin, result = self._review_context(rid, True)
        return Response(views_review.result_page(rid, state, result, cal, req.session, plugin))

    def review_json(self, req, rid):
        state, _, _, _ = self._review_context(rid, True)
        return Response(json.dumps(state['study'], ensure_ascii=False, indent=1) + '\n', 200,
                        'application/json; charset=utf-8', [('Content-Disposition', 'attachment; filename="review-study.json"')])

    def review_excel(self, req, rid):
        state, cal, plugin, result = self._review_context(rid, True)
        if plugin is None:
            raise HTTPError(409, 'Review plugin unavailable; review Excel export is unavailable.')
        try:
            with self.edit_lock:
                data = engine.review_xlsx(result, plugin, self.reviews.directory(rid))
        except (RuntimeError, ValueError, OSError) as e:
            raise HTTPError(409, f'Review export refused: {e}') from None
        return Response(data, 200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        [('Content-Disposition', 'attachment; filename="review.xlsx"')])

    def review_delete(self, req, rid):
        with self.edit_lock:
            self.reviews.delete(rid)
        return redirect('/reviews')
