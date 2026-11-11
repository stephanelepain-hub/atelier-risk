"""Round 2 tone: positive wording, no fear words, plain severity and level labels, three-line findings, a closing line
computed from the real levels. Pages and the Excel workbook, English and French."""
import io
import re
import unittest
from html.parser import HTMLParser

from app.tests import test_quick_path as qp
from app.tests.helpers import HAVE_OPENPYXL
from atelier_app import engine, findings, labels, views_quick

EN_NEGATIVE = re.compile(
    r"\b(do not|don't|cannot|can't|won't|must not|never|does not|did not|is not|are not|was not|were not|has not|"
    r"have not|will not|would not|should not|isn't|aren't|doesn't|didn't|wasn't|hasn't|haven't|wouldn't|shouldn't)\b",
    re.I)
FR_NEGATIVE = re.compile(r"\bne\b[^.;:!?]{0,40}\bpas\b|\bn['’]\w+[^.;:!?]{0,40}\bpas\b|\bjamais\b|\bne peut\b", re.I)
FEAR = re.compile(r"danger|threat actor|attack|attaq|catastroph|critical|critique|you are exposed|vous êtes exposé|"
                  r"warning|avertissement|menace|!", re.I)
ANSSI_SEVERITY = ("Critical", "Critique", "Grave", "Significant", "Significative", "Mineure")


class Text(HTMLParser):
    """The words a person reads: text nodes plus placeholder, aria-label and title attributes; no script or style."""

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for k, v in attrs:
            if k in ("placeholder", "aria-label", "title") and v:
                self.out.append(v)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.out.append(data.strip())


def words_read(html):
    p = Text()
    p.feed(html)
    return "\n".join(p.out)


class Paragraphs(HTMLParser):
    """The text of every <p> that is not inside the honesty statement or a table."""

    def __init__(self):
        super().__init__()
        self.cur, self.items, self.depth_skip = None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "aside" and ("class", "honesty") in attrs:
            self.depth_skip += 1
        if tag == "p" and not self.depth_skip:
            self.cur = []

    def handle_endtag(self, tag):
        if tag == "aside" and self.depth_skip:
            self.depth_skip -= 1
        if tag == "p" and self.cur is not None:
            self.items.append(" ".join(self.cur))
            self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur.append(data.strip())


class ToneBase(qp.Base):
    def walk(self, lang):
        sid = self.start(lang=lang)
        self.keep_all(sid, lang=lang)
        self.rate_all(sid, lang=lang)
        return sid

    def pages(self, lang):
        """Every page of the reader's path in one language, as {path: html}."""
        sid = self.walk(lang)
        paths = ["/", "/how", "/studies", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks",
                 f"/quick/{sid}/now", f"/quick/{sid}/results"]
        out = {p: self.page(f"{p}{'&' if '?' in p else '?'}lang={lang}") for p in paths}
        out["/login"] = self.c.text(Client_public(self.app).get("/login"))
        return sid, out


def Client_public(app):
    from app.tests.helpers import Client
    return Client(app)


class WordsTest(ToneBase):
    def test_positive_wording_on_every_page(self):
        for lang, rx in (("en", EN_NEGATIVE), ("fr", FR_NEGATIVE)):
            _, pages = self.pages(lang)
            for path, html in pages.items():
                text = words_read(html)
                m = rx.search(text)
                self.assertIsNone(m, (lang, path, m and text[max(0, m.start() - 60):m.end() + 40]))

    def test_no_fear_words_and_no_exclamation_marks_on_any_page(self):
        for lang in ("en", "fr"):
            _, pages = self.pages(lang)
            for path, html in pages.items():
                text = words_read(html)
                m = FEAR.search(text)
                self.assertIsNone(m, (lang, path, m and text[max(0, m.start() - 60):m.end() + 40]))

    def test_the_not_sure_choice_and_its_french_form(self):
        sid = self.walk("en")
        self.assertIn("Not sure", self.page(f"/quick/{sid}/about?lang=en"))
        self.assertIn("Pas sûr", self.page(f"/quick/{sid}/about?lang=fr"))
        for lang in ("en", "fr"):
            for p in ("/quick/new", f"/quick/{sid}/now"):
                self.assertNotRegex(self.page(f"{p}{'&' if '?' in p else '?'}lang={lang}"), r"I don.t know|Je ne sais pas")

    def test_the_legal_notice_wording(self):
        en = self.page("/how?lang=en")
        fr = self.page("/how?lang=fr")
        self.assertIn("Atelier is an independent project, separate from ANSSI, SGDSN and Club EBIOS. "
                      "EBIOS is a registered trademark of SGDSN.", en)
        self.assertIn("Atelier est un projet indépendant, distinct de l&#x27;ANSSI, du SGDSN et du Club EBIOS. "
                      "EBIOS est une marque déposée du SGDSN.", fr)

    def test_no_paragraph_over_two_lines_on_the_quick_screens(self):
        for lang in ("en", "fr"):
            sid, pages = self.pages(lang)
            for path in ("/", "/quick/new", f"/quick/{sid}/risks", f"/quick/{sid}/now", f"/quick/{sid}/results"):
                p = Paragraphs()
                p.feed(pages[path])
                for text in p.items:
                    self.assertLessEqual(len(text), 200, (lang, path, text))


class LabelsTest(ToneBase):
    def test_no_anssi_severity_word_on_screen_and_plain_words_instead(self):
        for lang, sev in (("en", ("Minor", "Noticeable", "Serious", "Very serious")),
                          ("fr", ("Mineur", "Notable", "Sérieux", "Très sérieux"))):
            sid, pages = self.pages(lang)
            for path in ("/how", f"/quick/{sid}/now", f"/quick/{sid}/results"):
                for w in ANSSI_SEVERITY:
                    self.assertNotRegex(words_read(pages[path]), rf"\b{w}\b", (lang, path, w))
            self.assertIn(sev[3], words_read(pages["/how"]))
            self.assertIn(sev[3], words_read(pages[f"/quick/{sid}/results"]))   # the map axis
            self.assertIn(sev[3], words_read(pages[f"/quick/{sid}/now"]))       # the severity choice

    def test_level_names_are_plain_and_the_numbers_are_unchanged(self):
        for lang, names in (("en", ("Low", "Moderate", "High")), ("fr", ("Faible", "Modéré", "Élevé"))):
            sid, pages = self.pages(lang)
            res = pages[f"/quick/{sid}/results"]
            for n in names:
                self.assertIn(f">{n}</span>", res)            # a level chip
            self.assertIn(f"{names[1]}</title>", res)         # a map cell
        st = self.study(self.walk("en"))
        rows = engine.register(st, self.cal)[0]
        plain = labels.display_cal(self.cal, "en")
        for r in rows:  # same cell of the grid, only another name
            self.assertEqual(engine.level(plain, r["severity"], r["likelihood"]),
                             labels.level_label(self.cal, engine.level(self.cal, r["severity"], r["likelihood"]), "en"))

    def test_the_engine_and_the_calibration_keep_the_anssi_terms(self):
        self.assertEqual([x["label_en"] for x in self.cal["severity"]], ["Minor", "Significant", "Serious", "Critical"])
        self.assertEqual(engine.SEVERITY_WORDS["en"][4].split(":")[0], "Critical")
        d = labels.display_cal(self.cal, "en")
        self.assertEqual([x["label_en"] for x in d["severity"]], ["Minor", "Noticeable", "Serious", "Very serious"])
        self.assertEqual([x["label_en"] for x in self.cal["severity"]][3], "Critical")  # the original is untouched

    def test_the_calibration_has_three_levels_so_three_plain_names(self):
        self.assertEqual(len(self.cal["levels"]), 3)
        self.assertEqual(sorted(labels.LEVEL_LABEL["en"].values()), ["High", "Low", "Moderate"])


class FindingsTest(ToneBase):
    def lines(self, html):
        return re.findall(r'<div class="finding">(.*?)</div>', html, re.S)

    def test_every_action_and_every_risk_has_exactly_three_labelled_lines(self):
        for lang, lbl in (("en", ("To strengthen", "Based on", "Next step")), ("fr", ("À renforcer", "D&#x27;après", "Prochaine étape"))):
            sid = self.walk(lang)
            html = self.page(f"/quick/{sid}/results?lang={lang}")
            blocks = self.lines(html)
            self.assertGreaterEqual(len(blocks), 2)
            for b in blocks:
                ps = re.findall(r"<p class=\"f-(gap|evid|fix)\"><b>([^<]+)</b> ([^<]*)</p>", b)
                self.assertEqual([x[1] for x in ps], list(lbl))
                self.assertEqual(len(re.findall(r"<p\b", b)), 3)
                for _, _, text in ps:
                    self.assertLessEqual(findings.wc(text), 15, text)
            n_risks = len(self.study(sid)["risks"])
            self.assertEqual(html.count('class="risk-finding"'), n_risks)

    LIK_WORDS = ("Unlikely", "Possible", "Likely", "Very likely", "Peu probable", "Probable", "Très probable",
                 "Yes, once", "Yes, a few times", "Yes, regularly")

    def evidences(self, html):
        return re.findall(r'<p class="f-evid"><b>[^<]+</b> ([^<]*)</p>', html)

    def test_the_evidence_quotes_the_business_not_the_likelihood(self):
        sid = self.start(sensitivity="confidential", downtime="hours")        # tools: office and an online shop
        self.keep_all(sid)
        self.rate_all(sid)
        html = self.page(f"/quick/{sid}/results")
        ev = self.evidences(html)
        self.assertGreaterEqual(len(ev), 4)
        for text in ev:
            self.assertNotIn("You said", text)
            self.assertNotIn("how likely", text)
            for w in self.LIK_WORDS:
                self.assertNotIn(f"“{w}”", text)
        self.assertIn("Customer data is confidential for you.", ev)
        self.assertIn("You use an online shop.", ev)

    def test_the_evidence_never_quotes_the_likelihood_even_when_it_was_answered(self):
        sid = self.start(sensitivity="dont_know", downtime="dont_know", tools=[])
        self.keep_all(sid)
        form = {"lang": "en", "go": "next"}
        for r in re.findall(r'id="risk-([^"]+)"', self.page(f"/quick/{sid}/now")):
            form[f"lik_{r}"] = "very_likely" if r.startswith("D") else "often"
        self.post(f"/quick/{sid}/now", form)
        for lang in ("en", "fr"):
            res = self.page(f"/quick/{sid}/results?lang={lang}")
            ev = self.evidences(res)
            self.assertTrue(ev)
            for text in ev:
                for w in self.LIK_WORDS + ("You said", "Vous avez répondu"):
                    self.assertNotIn(w, text)

    def test_with_no_other_answer_the_catalogue_reason_is_the_evidence(self):
        sid = self.start(tools=[], sensitivity="dont_know", downtime="dont_know", values="Taking orders by email")
        self.keep_all(sid)
        form = {"lang": "en", "go": "next"}
        for r in re.findall(r'id="risk-([^"]+)"', self.page(f"/quick/{sid}/now")):
            form[f"lik_{r}"] = "dont_know"
        self.post(f"/quick/{sid}/now", form)
        res = self.page(f"/quick/{sid}/results")
        why = {r["why"]["en"] for r in self.cat["risks"]}
        shown = [t.replace("&#x27;", "'") for t in self.evidences(res)]
        self.assertTrue(shown)
        for text in shown:
            self.assertIn(text, why)
        q = self.study(sid)["quick"]
        rows = engine.quick_compute(q, self.cal, self.cat)
        for lang in ("en", "fr"):
            for r in rows:
                self.assertEqual(findings.evidence(r, q, self.cat, lang), r["def"]["why"][lang])

    def test_each_line_stays_within_fifteen_words_for_every_risk_and_measure(self):
        cat = self.cat
        keep = [{"id": r["id"], "decision": "keep", "assessed": True,
                 "extra": [m["id"] for m in r["measures"]][:3]} for r in cat["risks"]]
        for lang in ("en", "fr"):
            quick = {"format": "atelier-quick", "version": "0.1", "lang": lang, "step": "results",
                     "profile": {"name": "All", "tools": {"value": [t["id"] for t in cat["tools"]]},
                                 "downtime": {"answer": "hours"}, "sensitivity": {"answer": "critical"},
                                 "activity": {"value": "We run a shop", "dont_know": False},
                                 "values": {"value": ["Taking orders by email from our regular customers every day"]}},
                     "risks": keep}
            rows = engine.quick_compute(quick, self.cal, cat)
            acts = engine.quick_actions(quick, self.cal, cat, 50)
            f = findings.build(quick, cat, self.cal, rows, acts, lang)
            self.assertEqual(len(f["risks"]), len(cat["risks"]))
            for item in f["risks"] + f["actions"]:
                for key in ("gap", "evidence", "fix"):
                    self.assertTrue(item[key].strip(), item)
                    self.assertLessEqual(findings.wc(item[key]), 15, (lang, item["id"], key, item[key]))
            self.assertLessEqual(findings.wc(f["closing"]), 15, f["closing"])
        for mid in labels.EFFORT:   # every measure line, alone
            for lang in ("en", "fr"):
                self.assertLessEqual(findings.wc(findings.fix(mid, {mid: {"en": "x", "fr": "x"}}, lang)), 15, (mid, lang))

    def test_every_catalogue_measure_has_a_short_name_a_time_and_a_person(self):
        ids = {m["id"] for r in self.cat["risks"] for m in r["measures"]} | {m["id"] for m in self.cat["generic_measures"]}
        self.assertEqual(ids - set(labels.EFFORT), set())
        for mid in ids:
            for lang in ("en", "fr"):
                self.assertTrue(labels.short_action(mid, lang) and labels.effort_line(mid, lang), (mid, lang))

    def test_the_results_order_and_the_collapsed_sections(self):
        sid = self.walk("en")
        html = self.page(f"/quick/{sid}/results")
        marks = ('class="summary"', "Your top actions", "<svg", '<div class="map-key">', '<details class="see-all"><summary>See all your risks (',
                 '<details class="in-place-box"><summary>Already in place (', "Confidence", "Honesty statement", 'class="closing"')
        order = [html.index(x) for x in marks]
        self.assertEqual(order, sorted(order))
        self.assertEqual(html.count('class="summary"'), 1)
        self.assertEqual(html.count('class="closing"'), 1)
        self.assertEqual(re.search(r'class="summary" role="status">([^<]+)<', html).group(1),
                         re.search(r'class="closing" role="status">([^<]+)<', html).group(1))

    def test_a_measure_is_never_in_place_and_a_next_step_at_once(self):
        sid = self.walk("en")
        html = self.page(f"/quick/{sid}/results")
        q = self.study(sid)["quick"]
        org = engine.quick_org_measures(q)
        self.assertTrue(org["in_place"] and org["extra"])
        self.assertFalse(set(org["in_place"]) & set(org["extra"]))
        placed_names = {labels.short_action(m, "en") for m in org["in_place"]}
        box = html.split('<details class="in-place-box">')[1].split("</details>")[0]
        for m in org["in_place"]:
            self.assertIn(f"<li>{labels.short_action(m, 'en')}</li>", box)
        self.assertIn("Already in place (%d)" % len(org["in_place"]), html)
        actions = html.split('<ol class="actions-list">')[1].split("</ol>")[0]
        for name in placed_names:
            self.assertNotIn(name + ":", actions)         # a measure already in place is not offered as a next step

    def test_the_risks_have_plain_numbers_that_match_the_list_next_to_the_maps(self):
        sid = self.walk("en")
        html = self.page(f"/quick/{sid}/results")
        q = self.study(sid)["quick"]
        rows = engine.quick_compute(q, self.cal, self.cat)
        key = re.findall(r'<li value="(\d+)">([^<]*)</li>', html)
        self.assertEqual([int(n) for n, _ in key], list(range(1, len(rows) + 1)))
        for (n, title), r in zip(key, rows):
            self.assertEqual(title.replace("&#x27;", "'"), r["def"]["title"]["en"])
        visible = re.sub(r"<[^>]+>", " ", html.split("<main", 1)[1])
        self.assertNotRegex(visible, r"\b[DAC]\d\d?\b")                  # no D01 / A02 in what people read
        maps = re.findall(r"<svg.*?</svg>", html, re.S)
        self.assertEqual(len(maps), 2)
        for svg in maps:
            texts = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
            self.assertNotRegex(texts, r"\b[DAC]\d\d?\b")
            self.assertRegex(texts, r"\b1\b")


class ClosingLineTest(ToneBase):
    def expected(self, sid, lang="en"):
        quick = self.study(sid)["quick"]
        rows = engine.quick_compute(quick, self.cal, self.cat)
        top = max(l["rank"] for l in self.cal["levels"])
        land = [r for r in rows if r["rank_target"] < r["rank"] and r["rank_target"] < top]
        m = len({x for r in rows for x in r["extra"]})
        return rows, land, m

    def test_the_closing_line_is_computed_from_the_before_and_after_levels(self):
        sid = self.walk("en")
        rows, land, m = self.expected(sid)
        self.assertGreater(len(land), 0)
        html = self.page(f"/quick/{sid}/results")
        verb = "moves" if len(land) == 1 else "move"
        line = f"With {m} actions, {len(land)} of your {len(rows)} risks {verb} to Low or Moderate."
        self.assertIn(f'<p class="summary" role="status">{line}</p>', html)                     # at the top
        self.assertIn(f'<p class="closing" role="status">{line}</p>', html)                     # and at the very end
        self.assertGreater(html.index('class="closing"'), html.index("Download"))
        self.assertLess(html.index('class="summary"'), html.index("Your top actions"))
        fr = self.page(f"/quick/{sid}/results?lang=fr")
        self.assertIn(f"Avec {m} actions, {len(land)} de vos {len(rows)} risques passent à Faible ou Modéré.", fr)

    def test_the_line_follows_the_answers(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid, per_risk={})
        a = self.page(f"/quick/{sid}/results")
        # untick every extra measure: the line changes with the real levels
        html = self.page(f"/quick/{sid}/now")
        ids = re.findall(r'id="risk-([^"]+)"', html)
        form = {"lang": "en", "go": "next"}
        for rid in ids:
            form[f"lik_{rid}"] = "possible" if rid.startswith("D") else "once"
        self.post(f"/quick/{sid}/now", form)
        b = self.page(f"/quick/{sid}/results")
        line_a = re.search(r'<p class="closing" role="status">([^<]+)</p>', a).group(1)
        line_b = re.search(r'<p class="closing" role="status">([^<]+)</p>', b).group(1)
        self.assertNotEqual(line_a, line_b)
        self.assertNotIn(" actions", line_b)


class ClosingBranchesTest(ToneBase):
    """Every branch of the closing line, from rows shaped like the engine's (rank before and after, extra measures)."""

    def row(self, rank, target, extra=()):
        return {"rank": rank, "rank_target": target, "extra": list(extra)}

    def line(self, rows, lang="en"):
        return findings.closing(rows, self.cal, lang)

    def test_each_branch_in_both_languages(self):
        rows = [self.row(3, 2, ["a", "b"]), self.row(3, 3, ["a"]), self.row(2, 1, ["c"]), self.row(3, 3)]
        self.assertEqual(self.line(rows), "With 3 actions, 2 of your 4 risks move to Low or Moderate.")
        self.assertEqual(self.line(rows, "fr"), "Avec 3 actions, 2 de vos 4 risques passent à Faible ou Modéré.")
        one = [self.row(3, 2, ["a"]), self.row(3, 3)]
        self.assertEqual(self.line(one), "With 1 action, 1 of your 2 risks moves to Low or Moderate.")
        self.assertEqual(self.line(one, "fr"), "Avec 1 action, 1 de vos 2 risques passe à Faible ou Modéré.")
        start = [self.row(3, 3, ["a", "b"]), self.row(3, 3)]            # a plan, no level change yet
        self.assertEqual(self.line(start), "Your 2 actions are a first step on 2 risks.")
        self.assertEqual(self.line(start, "fr"), "Vos 2 actions sont un premier pas sur 2 risques.")
        self.assertEqual(self.line([self.row(3, 3, ["a"])]), "Your action is a first step on 1 risks.")
        now = [self.row(1, 1), self.row(3, 3)]                          # no plan, one risk already low
        self.assertEqual(self.line(now), "1 of your 2 risks is already at Low or Moderate.")
        self.assertEqual(self.line(now, "fr"), "1 de vos 2 risques est déjà à Faible ou Modéré.")
        now2 = [self.row(1, 1), self.row(2, 2), self.row(3, 3)]
        self.assertEqual(self.line(now2), "2 of your 3 risks are already at Low or Moderate.")
        mapped = [self.row(3, 3), self.row(3, 3)]
        self.assertEqual(self.line(mapped), "You have mapped 2 risks: a solid start for choosing your first actions.")
        self.assertEqual(self.line([]), "")

    def test_the_improve_branch_needs_a_level_above_the_top_of_a_four_level_scale(self):
        import copy
        cal4 = copy.deepcopy(self.cal)
        cal4["levels"].append({"name": "Très haut", "name_en": "Very high", "rank": 4, "colour": "8E1B10"})
        rows = [self.row(4, 3, ["a"]), self.row(4, 4)]                  # a step down that still ends at the top of the old scale
        self.assertEqual(findings.closing(rows, cal4, "en"), "With 1 action, 1 of your 2 risks improves by a level.")
        self.assertEqual(findings.closing(rows, cal4, "fr"), "Avec 1 action, 1 de vos 2 risques gagne un niveau.")
        rows = [self.row(4, 3, ["a", "b"]), self.row(4, 3)]
        self.assertEqual(findings.closing(rows, cal4, "en"), "With 2 actions, 2 of your 2 risks improve by a level.")

    def test_no_branch_names_a_level_the_rows_do_not_show(self):
        for rows in ([self.row(3, 2, ["a"])], [self.row(2, 1)], [self.row(3, 3)]):
            for lang in ("en", "fr"):
                self.assertLessEqual(findings.wc(self.line(rows, lang)), 15)


class EvidenceBranchesTest(ToneBase):
    def test_a_changed_severity_is_quoted_with_its_reason_and_a_custom_risk_has_three_short_lines(self):
        sid = self.start()
        ids = self.keep_all(sid, new_title_1="Our delivery van breaks down " + "and keeps on going " * 3,
                            new_family_1="accidental", new_crit_1=["availability"])
        html = self.page(f"/quick/{sid}/now")
        rid = ids[0]
        form = {"lang": "en", "go": "next", f"sev_{rid}": "2", f"sevreason_{rid}": "Customers rarely notice " + "this one " * 12}
        for r in re.findall(r'id="risk-([^"]+)"', html):
            form[f"lik_{r}"] = "dont_know"
        self.post(f"/quick/{sid}/now", form)
        res = self.page(f"/quick/{sid}/results")
        self.assertIn("You rated it “Noticeable”, noting: “Customers rarely notice", res)
        for b in re.findall(r'<div class="finding">(.*?)</div>', res, re.S):
            for text in re.findall(r"</b> ([^<]*)</p>", b):
                self.assertLessEqual(findings.wc(text), 15, text)
        n_kept = len([e for e in self.study(sid)["quick"]["risks"] if e["decision"] == "keep"])
        self.assertIn(f'class="rid">{n_kept}</span>', res)        # the risk added by the person has the last plain number


@unittest.skipUnless(HAVE_OPENPYXL, "openpyxl is not installed")
class ExcelToneTest(ToneBase):
    def book(self, lang):
        import openpyxl
        sid = self.walk(lang)
        r = self.c.get(f"/s/{sid}/export.xlsx?lang={lang}")
        self.assertEqual(r.status, 200)
        return openpyxl.load_workbook(io.BytesIO(r.body)), sid

    def cells(self, wb):
        return [(ws.title, str(c.value)) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]

    def test_no_anssi_severity_word_negative_wording_or_fear_word_in_the_workbook(self):
        for lang, rx in (("en", EN_NEGATIVE), ("fr", FR_NEGATIVE)):
            wb, _ = self.book(lang)
            for sheet, v in self.cells(wb):
                for w in ANSSI_SEVERITY:
                    self.assertNotRegex(v, rf"\b{w}\b", (lang, sheet, v[:80]))
                self.assertIsNone(rx.search(v), (lang, sheet, v[:120]))
                self.assertIsNone(FEAR.search(v), (lang, sheet, v[:120]))

    def test_three_lines_per_item_and_a_closing_line(self):
        for lang, lbl in (("en", ("To strengthen", "Based on", "Next step")), ("fr", ("À renforcer", "D'après", "Prochaine étape"))):
            wb, sid = self.book(lang)
            for name in wb.sheetnames:
                if name in ("Top actions", "Actions", "Your risks", "Vos risques"):
                    rows = [r for r in wb[name].iter_rows(min_row=2, values_only=True)]
                    body = [r for r in rows if r[1]]
                    self.assertEqual(len(body) % 3, 0, name)
                    for i in range(0, len(body), 3):
                        self.assertEqual(tuple(x[1] for x in body[i:i + 3]), lbl)
                        self.assertEqual(len({x[0] for x in body[i:i + 3]}), 1)
                        for x in body[i:i + 3]:
                            self.assertLessEqual(findings.wc(x[2]), 15, x)
            quick = self.study(sid)["quick"]
            rows = engine.quick_compute(quick, self.cal, self.cat)
            closing = findings.closing(rows, self.cal, lang)
            first = wb.worksheets[0]
            self.assertEqual(first["A3"].value, closing)              # the summary closes on the encouraging line
            mine = wb[views_quick.tr(lang, "risks_h")]
            self.assertEqual([r for r in mine.iter_rows(values_only=True) if any(r)][-1][2], closing)

    def test_the_excel_levels_use_the_plain_names(self):
        wb, _ = self.book("en")
        text = " ".join(v for _, v in self.cells(wb))
        self.assertIn("Moderate", text)
        self.assertNotIn("Medium", text)
        self.assertIn("Very serious", text)


if __name__ == "__main__":
    unittest.main()
