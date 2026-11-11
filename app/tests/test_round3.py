"""Round 3 (owner's browser walk of the public edition): each measure answered once, a plain results page, rough
effort figures, numbers instead of codes, no document talk. One test or more per item of the brief."""
import html as html_mod
import re
import unittest

from app.tests.test_quick_path import Base, sid_of
from atelier_app import calibrations, engine, findings, labels

EXTRA = {"backup_offline", "mfa", "awareness", "updates", "password_manager"}
IN_PLACE = {"protection", "least_access"}


def visible_words(fragment, keep_svg_titles=False):
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    if not keep_svg_titles:
        t = re.sub(r"<title>.*?</title>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return len([w for w in html_mod.unescape(t).split() if any(ch.isalnum() for ch in w)])


class Round3Base(Base):
    def typical(self, lang="en", n=7):
        """The bakery of the owner's walk: seven risks kept, five measures to add, two already in place."""
        sid = self.start(lang=lang)
        html = self.page(f"/quick/{sid}/risks")
        ids = re.findall(r'<input class="keep-box" type="checkbox" name="keep" value="([A-Z0-9]+)" checked>', html)[:n]
        self.assertEqual(self.post(f"/quick/{sid}/risks", {"keep": ids, "lang": lang}).status, 303)
        now = self.page(f"/quick/{sid}/now")
        form = {"lang": lang, "go": "next"}
        for rid in re.findall(r'id="risk-([^"]+)"', now):
            form[f"lik_{rid}"] = "likely" if rid.startswith("D") else "sometimes"
        for mid in re.findall(r'name="m_([^"]+)" value="extra"', now):
            if mid in EXTRA:
                form[f"m_{mid}"] = "extra"
            elif mid in IN_PLACE:
                form[f"m_{mid}"] = "in"
        self.assertEqual(self.post(f"/quick/{sid}/now", form).status, 303)
        return sid


class MeasuresAnsweredOnceTest(Round3Base):
    """Item 1."""

    def setUp(self):
        super().setUp()
        self.sid = self.start()
        self.keep_all(self.sid)
        self.now = self.page(f"/quick/{self.sid}/now")
        self.kept = [e["id"] for e in self.study(self.sid)["quick"]["risks"] if e["decision"] == "keep"]

    def test_each_measure_is_listed_once_with_three_choices(self):
        names = re.findall(r'<input type="radio" name="(m_[^"]+)" value=""', self.now)
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse([n for n in names if re.match(r"m_[DAC]\d+_", n)])            # no per-risk question any more
        listed = {n[2:] for n in names}
        want = {m["id"] for r in self.cat["risks"] if r["id"] in self.kept for m in r["measures"]}
        self.assertEqual(listed, want)
        for n in names:
            self.assertEqual(len(re.findall(rf'name="{n}" value="(|in|extra)"', self.now)), 3, n)
        per_risk_old = sum(len(r["measures"]) for r in self.cat["risks"] if r["id"] in self.kept)
        self.assertLess(len(names), per_risk_old)                                        # the page is much shorter

    def test_the_measures_sit_under_a_few_plain_headings(self):
        legends = re.findall(r'<fieldset class="blk meas"><legend><span class="q-t">([^<]+)</span>', self.now)
        self.assertTrue(2 <= len(legends) <= len(labels.GROUPS), legends)
        self.assertEqual(len(legends), len(set(legends)))
        for mid in {n[2:] for n in re.findall(r'name="(m_[^"]+)" value=""', self.now)}:
            self.assertIn(mid, labels.MEASURE_GROUP)

    def test_every_catalogue_measure_belongs_to_a_group_with_an_english_and_french_heading(self):
        ids = {m["id"] for r in self.cat["risks"] for m in r["measures"]} | {m["id"] for m in self.cat["generic_measures"]}
        self.assertEqual(ids - set(labels.MEASURE_GROUP), set())
        self.assertEqual(set(labels.MEASURE_GROUP) - ids, set())
        self.assertEqual(set(labels.MEASURE_GROUP.values()), set(labels.GROUPS))
        for lang in ("en", "fr"):
            for g in labels.GROUPS:
                self.assertTrue(labels.group_title(g, lang))

    def test_one_compact_row_per_risk_with_severity_and_likelihood(self):
        self.assertEqual(len(re.findall(r'<article class="risk-row', self.now)), len(self.kept))
        for rid in self.kept:
            self.assertIn(f'name="sev_{rid}"', self.now)
            self.assertIn(f'name="lik_{rid}"', self.now)
        self.assertNotIn('class="row-card"', self.now)
        self.assertNotIn('class="r-desc"', self.now)                                     # no description repeated per risk

    def test_the_answer_applies_to_every_risk_and_is_saved_once(self):
        shared = [m for m in {n[2:] for n in re.findall(r'name="(m_[^"]+)" value=""', self.now)}
                  if len([r for r in self.cat["risks"] if r["id"] in self.kept and m in {x["id"] for x in r["measures"]}]) >= 3]
        mfa = "mfa" if "mfa" in shared else shared[0]
        form = {"lang": "en", "go": "stay", f"m_{mfa}": "in"}
        self.assertEqual(self.post(f"/quick/{self.sid}/now", form).status, 303)
        q = self.study(self.sid)["quick"]
        self.assertEqual(q["measures"], {"in_place": [mfa], "extra": [], "assessed": True})
        rows = engine.quick_compute(q, calibrations.load("anssi-v1.5"), self.cat)
        listing = [r for r in rows if mfa in {m["id"] for m in r["def"]["measures"]}]
        self.assertGreaterEqual(len(listing), 3)
        for r in listing:
            self.assertEqual(r["in_place"], [mfa])
            self.assertNotIn(mfa, r["extra"])
        self.assertIn(f'name="m_{mfa}" value="in" checked', self.page(f"/quick/{self.sid}/now"))

    def test_a_refused_form_keeps_the_measure_choices(self):
        rid = self.kept[0]
        form = {"lang": "en", "go": "stay", f"sev_{rid}": "1", "m_updates": "extra", "m_mfa": "in"}
        r = self.post(f"/quick/{self.sid}/now", form)
        self.assertEqual(r.status, 400)                                                  # another severity needs a reason
        t = self.c.text(r)
        self.assertIn('name="m_updates" value="extra" checked', t)
        self.assertIn('name="m_mfa" value="in" checked', t)

    def test_a_measure_never_shows_as_in_place_and_as_a_next_step(self):
        sid = self.typical()
        res = self.page(f"/quick/{sid}/results")
        placed = re.search(r'<details class="in-place-box"><summary>Already in place \((\d+)\)</summary>(.*?)</details>', res, re.S)
        names = re.findall(r"<li>([^<]*)</li>", placed.group(2))
        self.assertEqual(int(placed.group(1)), len(names))
        self.assertTrue(names)
        every_next_step = re.findall(r'<p class="f-fix"><b>[^<]+</b> ([^<:]*):', res)
        self.assertTrue(every_next_step)
        for name in names:
            self.assertNotIn(html_mod.unescape(name), [html_mod.unescape(x) for x in every_next_step])
        self.assertIn(labels.short_action("protection", "en"), names)

    def test_a_study_saved_with_answers_per_risk_is_migrated(self):
        sid = self.typical()
        st = self.study(sid)
        q = st["quick"]
        old = {"updates": [("D01", "in_place"), ("D02", "extra")], "mfa": [("D01", "extra"), ("D03", "extra")],
               "awareness": [("D02", "extra")]}
        del q["measures"]
        for e in q["risks"]:
            e["assessed"] = True
            e["in_place"], e["extra"] = [], []
        by = {e["id"]: e for e in q["risks"]}
        for mid, uses in old.items():
            for rid, kind in uses:
                by[rid][kind].append(mid)
        self.app.store.save(sid, st)
        self.assertNotIn("measures", self.study(sid)["quick"])
        t = self.page(f"/quick/{sid}/now")
        self.assertIn('name="m_updates" value="in" checked', t)                          # in place for D01, planned for D02: in place
        self.assertIn('name="m_mfa" value="extra" checked', t)
        self.assertIn('name="m_awareness" value="extra" checked', t)
        self.assertNotIn('name="m_backup_offline" value="extra" checked', t)
        form = {"lang": "en", "go": "stay", "m_updates": "in", "m_mfa": "extra", "m_awareness": "extra"}
        self.assertEqual(self.post(f"/quick/{sid}/now", form).status, 303)
        q2 = self.study(sid)["quick"]
        self.assertEqual(q2["measures"], {"in_place": ["updates"], "extra": ["mfa", "awareness"], "assessed": True})
        for e in q2["risks"]:
            for k in ("in_place", "extra", "assessed"):
                self.assertNotIn(k, e)
        self.assertEqual(engine.check(self.study(sid))["errors"], [])
        res = self.page(f"/quick/{sid}/results")
        self.assertIn("Already in place (1)", res)


class PlainResultsTest(Round3Base):
    """Items 4 and 5."""

    def test_at_most_350_visible_words_above_the_collapsed_sections(self):
        for lang in ("en", "fr"):
            sid = self.typical(lang)
            res = self.page(f"/quick/{sid}/results?lang={lang}")
            above = res[:res.index("<details")]
            self.assertLessEqual(visible_words(above.split("<main", 1)[1]), 350, lang)           # what people read
            if lang == "en":       # strictest count (header, tooltips, every text above): the English page; French words run longer
                self.assertLessEqual(visible_words(above, keep_svg_titles=True), 350, lang)
            self.assertGreaterEqual(visible_words(res.split("<main", 1)[1]), visible_words(above.split("<main", 1)[1]))

    def test_the_facts_line_is_gone_and_the_confidence_is_said_once(self):
        sid = self.typical()
        res = self.page(f"/quick/{sid}/results")
        for gone in ("Answers:", "Assumptions to confirm", "To add:", "Documents:", 'class="facts"'):
            self.assertNotIn(gone, res, gone)
        self.assertEqual(res.count("Confidence grows as you answer more questions yourself."), 1)
        self.assertEqual(len(re.findall(r'class="big-n"', res)), 1)
        self.assertIn("up to 75%", res)

    def test_the_summary_comes_first_and_the_risk_sections_are_collapsed(self):
        sid = self.typical()
        res = self.page(f"/quick/{sid}/results")
        self.assertRegex(res, r'class="summary" role="status">With \d+ actions?, \d+ of your 7 risks? moves? to Low or Moderate\.<')
        for name in ("see-all", "in-place-box"):
            self.assertIn(f'<details class="{name}">', res)
            self.assertNotIn(f'<details class="{name}" open', res)
        self.assertRegex(res, r"See all your risks \(7\)")

    def test_numbers_replace_codes_on_every_public_list_and_map(self):
        sid = self.typical()
        for path in (f"/quick/{sid}/now", f"/quick/{sid}/results"):
            main = self.page(path).split("<main", 1)[1]
            visible = html_mod.unescape(re.sub(r"<[^>]+>", " ", main))
            self.assertNotRegex(visible, r"\b[DAC]\d\d?\b", path)
        res = self.page(f"/quick/{sid}/results")
        for i in range(1, 8):
            self.assertIn(f'<li value="{i}">', res)
            self.assertIn(f'<span class="rid">{i}</span>', res)
        now = self.page(f"/quick/{sid}/now")
        self.assertEqual(re.findall(r'<h3><span class="rid">(\d+)</span>', now), [str(i) for i in range(1, 8)])

    def test_the_excel_file_keeps_the_codes(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl is not installed")
        import io
        sid = self.typical()
        wb = openpyxl.load_workbook(io.BytesIO(self.c.get(f"/s/{sid}/export.xlsx").body))
        ids = [row[0] for row in wb.worksheets[0].iter_rows(values_only=True)]
        self.assertIn("D01", ids)


class RoughGuideTest(Round3Base):
    """Item 6."""

    def test_the_label_is_shown_once_at_the_top_of_the_actions(self):
        for lang, label in (("en", "Rough guide"), ("fr", "Ordre d'idée")):
            sid = self.typical(lang)
            res = self.page(f"/quick/{sid}/results?lang={lang}")
            self.assertEqual(html_mod.unescape(res).count(label), 1, lang)
            self.assertLess(res.index('class="rough"'), res.index('class="actions-list"'))

    def test_the_label_is_there_even_before_any_action_is_planned(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid, go="next")
        self.assertIn("Rough guide", self.page(f"/quick/{sid}/results"))

    def test_only_safe_figures_are_kept_and_none_is_a_price(self):
        figures = {f[0] for f in labels.FIGURES}
        french = {f[1] for f in labels.FIGURES}
        for mid, e in labels.EFFORT.items():
            self.assertIn(e[2], figures, mid)
            self.assertIn(e[3], french, mid)
            for text in (e[2], e[3]):
                self.assertNotRegex(text, r"\d|€|\$|£|euro|dollar", (mid, text))
        self.assertTrue({"under an hour", "a day or two", "small monthly fee"} <= figures)

    def test_every_figure_line_stays_short(self):
        for mid in labels.EFFORT:
            for lang in ("en", "fr"):
                self.assertLessEqual(len(labels.effort_line(mid, lang).split()), 8, (mid, lang))
                self.assertLessEqual(findings.wc(findings.fix(mid, {mid: {"en": "x", "fr": "x"}}, lang)), 15)


class OneStartTest(Round3Base):
    """Item 7 and the home part of item 3."""

    def test_home_is_one_title_one_line_one_start(self):
        for lang in ("en", "fr"):
            t = self.page(f"/?lang={lang}")
            self.assertEqual(t.count("15 minutes"), 1)
            self.assertEqual(len(re.findall(r'class="button primary big"', t)), 1)
            self.assertEqual(t.count(engine.HONESTY[lang]), 1)           # shown as it is written, apostrophe included


if __name__ == "__main__":
    unittest.main()
