"""Round 2: the Expert switch (cookie, badge, links), expert screens that always answer, the edited-in-expert-mode
note, and the "How it works" page."""
import json
import re
import unittest

from app.tests import test_quick_path as qp
from app.tests.helpers import Client, make_app
from atelier_app import engine, views_how


class SwitchBase(qp.Base):
    def study_walk(self):
        sid = self.start()
        self.keep_all(sid)
        self.rate_all(sid)
        return sid

    EXPERT_LINK = r'href="/s/{sid}(?:/(?:w[1-5]|register|el/[^"]*|rename|duplicate|severities))?"'

    def expert_links(self, html, sid):
        return re.findall(self.EXPERT_LINK.format(sid=sid), html)


class SwitchOffTest(SwitchBase):
    def test_off_by_default_no_badge_no_expert_link_anywhere(self):
        sid = self.study_walk()
        for p in ("/", "/studies", "/how", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks",
                  f"/quick/{sid}/now", f"/quick/{sid}/results"):
            for lang in ("en", "fr"):
                html = self.page(f"{p}{'&' if '?' in p else '?'}lang={lang}")
                self.assertEqual(self.expert_links(html, sid), [], (p, lang))
                self.assertNotIn("Expert mode on", html)
                self.assertNotIn("Mode expert activé", html)
                self.assertNotIn("Open in expert view", html)
                self.assertNotIn("Ouvrir en vue expert", html)
                self.assertIn('role="switch" aria-checked="false"', html, (p, lang))
                self.assertRegex(html, r"</span>Expert</button>")

    def test_the_switch_is_a_post_form_with_a_csrf_token_and_the_next_value(self):
        html = self.page("/quick/new")
        m = re.search(r'<form method="post" action="/expert" class="inline expert-switch">(.*?)</form>', html, re.S)
        self.assertIsNotNone(m)
        self.assertIn('name="csrf"', m.group(1))
        self.assertIn('name="on" value="1"', m.group(1))
        self.assertIn('name="next" value="/quick/new"', m.group(1))

    def test_the_expert_routes_answer_even_with_the_switch_off(self):
        sid = self.study_walk()
        for p in ("", "/w1", "/w2", "/w3", "/w4", "/w5", "/register"):
            r = self.c.get(f"/s/{sid}{p}")
            self.assertEqual(r.status, 200, p)
        st = self.study(sid)
        first = st["risks"][0]["id"]
        self.assertEqual(self.c.get(f"/s/{sid}/el/{first}").status, 303)
        ro = st["risk_origins"][0]["id"]
        self.assertEqual(self.c.get(f"/s/{sid}/w2/ro/{ro}").status, 200)
        self.assertEqual(self.c.get(f"/s/{sid}/w1/bv/{st['business_values'][0]['id']}").status, 200)

    def test_expert_edits_work_with_the_switch_off(self):
        sid = self.study_walk()
        r = self.c.post_csrf(f"/s/{sid}/rename", {"name": "Renamed", "scope": "x"}, page=f"/s/{sid}")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.study(sid)["study"]["name"], "Renamed")
        n = len(self.app.store.list())
        r = self.c.post_csrf(f"/s/{sid}/duplicate", {}, page=f"/s/{sid}")
        self.assertEqual(r.status, 303)
        self.assertEqual(len(self.app.store.list()), n + 1)


class SwitchTest(SwitchBase):
    def cookie(self, resp):
        return [v for v in resp.all("Set-Cookie") if v.startswith("expert=")]

    def test_post_expert_sets_the_cookie_and_redirects_back(self):
        r = self.c.post_csrf("/expert", {"on": "1", "next": "/quick/new"}, page="/")
        self.assertEqual((r.status, r.get("Location")), (303, "/quick/new"))
        [ck] = self.cookie(r)
        self.assertTrue(ck.startswith("expert=1;"), ck)
        for attr in ("Path=/", "HttpOnly", "SameSite=Lax"):
            self.assertIn(attr, ck)
        r = self.c.post_csrf("/expert", {"on": "0"}, page="/")
        self.assertEqual((r.status, r.get("Location")), (303, "/"))
        [ck] = self.cookie(r)
        self.assertTrue(ck.startswith("expert=0;"), ck)
        self.assertIn("HttpOnly", ck)

    def test_it_needs_a_csrf_token_a_login_and_a_valid_value(self):
        r = self.c.post("/expert", {"on": "1"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.cookie(r), [])
        for bad in ("", "2", "yes", "on"):
            r = self.c.post_csrf("/expert", {"on": bad}, page="/")
            self.assertEqual(r.status, 400, bad)
            self.assertEqual(self.cookie(r), [])
        anon = Client(self.app)
        r = anon.post("/expert", {"on": "1", "csrf": "x"})
        self.assertEqual(r.status, 403)

    def test_next_must_be_a_local_path(self):
        for nxt in ("//evil.example/x", "https://evil.example/", "/a b", "javascript:alert(1)"):
            r = self.c.post_csrf("/expert", {"on": "1", "next": nxt}, page="/")
            self.assertEqual(r.get("Location"), "/", nxt)

    def test_on_shows_the_badge_the_results_link_and_the_studies_link(self):
        sid = self.study_walk()
        self.c.expert(True)
        self.assertEqual(self.c.cookies.get("expert"), "1")
        home = self.page("/")
        self.assertIn('<span class="badge expert-on">Expert mode on</span>', home)
        self.assertIn('role="switch" aria-checked="true"', home)
        self.assertIn('name="on" value="0"', home)
        res = self.page(f"/quick/{sid}/results")
        self.assertRegex(res, rf'<a class="button secondary" href="/s/{sid}"[^>]*>Open in expert view</a>')
        studies = self.page("/studies")
        self.assertIn(f'href="/s/{sid}">Expert view</a>', studies)
        fr = self.page(f"/quick/{sid}/results?lang=fr")
        self.assertIn("Mode expert activé", fr)
        self.assertIn("Ouvrir en vue expert", fr)

    def test_off_again_removes_every_expert_link(self):
        sid = self.study_walk()
        self.c.expert(True)
        self.c.expert(False)
        for p in ("/studies", f"/quick/{sid}/results"):
            html = self.page(p)
            self.assertEqual(self.expert_links(html, sid), [], p)
            self.assertNotIn("Expert mode on", html)

    def test_only_the_value_1_turns_it_on(self):
        sid = self.study_walk()
        for v in ("0", "true", "yes", ""):
            self.c.cookies["expert"] = v
            self.assertNotIn("Expert mode on", self.page("/"), v)
            self.assertNotIn("Open in expert view", self.page(f"/quick/{sid}/results"), v)
        self.c.cookies["expert"] = "1"
        self.assertIn("Expert mode on", self.page("/"))

    def test_without_next_the_referer_path_is_used_then_the_home_page(self):
        r = self.c.post_csrf("/expert", {"on": "1"}, page="/")
        self.assertEqual(r.get("Location"), "/")
        form = {"on": "1", "csrf": self.c.csrf("/")}
        r = self.c.post("/expert", form, headers={"Referer": "http://127.0.0.1:8770/how?lang=fr"})
        self.assertEqual(r.get("Location"), "/how")
        r = self.c.post("/expert", form, headers={"Referer": "http://evil.example//x"})
        self.assertEqual(r.get("Location"), "/")

    def test_the_switch_returns_to_the_page_it_was_on(self):
        html = self.page("/how")
        self.assertIn('name="next" value="/how"', html)
        r = self.c.post_csrf("/expert", {"on": "1", "next": "/how"}, page="/how")
        self.assertEqual(r.get("Location"), "/how")


class ExpertScreensTest(SwitchBase):
    """The restored expert screens, on a study made with the quick path."""

    def test_the_quick_study_opens_in_the_existing_screens(self):
        sid = self.study_walk()
        for p in ("", "/w1", "/w2", "/w3", "/w4", "/w5", "/register"):
            self.assertEqual(self.c.get(f"/s/{sid}{p}").status, 200, p)
        t = self.page(f"/s/{sid}/w5")
        self.assertIn("Ransomware locks your files and systems", t)
        self.assertIn(f'href="/quick/{sid}/results"', self.page(f"/s/{sid}"))
        reg = self.page(f"/s/{sid}/register")
        self.assertIn("Risk grid, now and at target", reg)
        self.assertEqual(reg.count("<svg"), 2)

    def test_the_expert_pages_have_no_documents_tab_no_privacy_row_no_draft_panel(self):
        sid = self.study_walk()
        for p in ("", "/w1", "/w2", "/w5"):
            t = self.page(f"/s/{sid}{p}")
            for gone in ("/docs", ">Documents<", "/confidential", "Mark this study confidential", "badge private", "Draft", "/settings"):
                self.assertNotIn(gone, t, (p, gone))

    def test_a_refused_expert_form_keeps_the_typed_values(self):
        sid = self.study_walk()
        r = self.c.post_csrf(f"/s/{sid}/w1/bv/add", {"label": "", "owner": "kept@example"}, page=f"/s/{sid}/w1")
        self.assertEqual(r.status, 400)
        self.assertIn("kept@example", self.c.text(r))


class EditedInExpertModeTest(SwitchBase):
    def test_a_quick_study_changed_in_expert_mode_keeps_its_note(self):
        sid = self.study_walk()
        for p in ("about", "risks", "now", "results"):
            self.assertNotIn("changed in expert mode", self.page(f"/quick/{sid}/{p}"), p)
        r = self.c.post_csrf(f"/s/{sid}/w1/bv/add", {"label": "Our recipes", "nature": "information", "owner": "Ana"},
                             page=f"/s/{sid}/w1")
        self.assertEqual(r.status, 303, self.c.text(r)[:300])
        for lang, text in (("en", "This study was changed in expert mode."), ("fr", "Cette étude a été modifiée en mode expert.")):
            for p in ("about", "risks", "now", "results"):
                self.assertIn(text, self.page(f"/quick/{sid}/{p}?lang={lang}"), (p, lang))
        # saving a quick screen rebuilds the study from the answers (the old file is kept as .bak)
        r = self.post(f"/quick/{sid}/now", {"lang": "en", "go": "stay"})
        self.assertEqual(r.status, 303)
        self.assertNotIn("changed in expert mode", self.page(f"/quick/{sid}/results"))
        self.assertTrue((self.app.store.dir / f"{sid}.json.bak").exists())


class HowPageTest(qp.Base):
    def test_the_page_answers_in_english_and_french_without_a_login(self):
        anon = Client(self.app)
        for lang, title in (("en", "How it works"), ("fr", "Comment ça marche")):
            r = anon.get(f"/how?lang={lang}")
            self.assertEqual(r.status, 200)
            html = anon.text(r)
            self.assertIn(f"<h1>{title}</h1>", html)
            self.assertIn(f'<html lang="{lang}">', html)

    def test_the_link_is_in_the_header_of_every_page_and_on_the_home_page(self):
        sid = self.start()
        for p in ("/", "/studies", "/how", "/quick/new", f"/quick/{sid}/about", f"/quick/{sid}/risks",
                  f"/quick/{sid}/now", f"/quick/{sid}/results", f"/s/{sid}/delete", "/no-such-page"):
            html = self.c.text(self.c.get(p))
            self.assertRegex(html, r'<nav>.*<a href="/how">How it works</a>', p)
        self.assertIn('<a href="/how">How it works</a>', Client(self.app).text(Client(self.app).get("/login")))
        home = self.page("/")
        self.assertIn('<a href="/how?lang=en">How it works</a>', home)
        self.assertIn("Built on EBIOS Risk Manager, the method of ANSSI, the French national cybersecurity agency", home)
        fr = self.page("/?lang=fr")
        self.assertIn("Fondé sur EBIOS Risk Manager, la méthode de l&#x27;ANSSI, l&#x27;agence nationale française de la cybersécurité", fr)
        self.assertIn('<a href="/how?lang=fr">Comment ça marche</a>', fr)

    def test_the_seven_sections_and_their_content(self):
        en = self.page("/how?lang=en")
        h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", en)
        self.assertEqual(h2, ["The method", "Your four screens and the five workshops of the method", "Where the numbers come from",
                              "What the confidence figure means", "Honesty statement", "Your data", "Independence"])
        for must in ("<b>EBIOS Risk Manager</b>", "<b>ANSSI</b>", "French national cybersecurity agency",
                     "conforms with ISO/IEC 27005:2022",
                     'href="https://cyber.gouv.fr/securisation/analyse-des-risques/methode-ebios-rm"',
                     'href="https://messervices.cyber.gouv.fr/guides/la-methode-ebios-risk-manager-le-guide"',
                     "ANSSI guide, version 1.5", "NIST SP 800-30", "75% at most",
                     "stays on the computer that runs Atelier",
                     "Atelier is an independent project, separate from ANSSI, SGDSN and Club EBIOS. "
                     "EBIOS is a registered trademark of SGDSN."):
            self.assertIn(must, en, must)
        self.assertEqual(en.count(engine.HONESTY["en"]), 1)
        fr = self.page("/how?lang=fr")
        self.assertEqual(len(re.findall(r"<h2[^>]*>", fr)), 7)
        self.assertEqual(fr.count(engine.HONESTY["fr"]), 1)
        self.assertIn("conforme à la norme ISO/IEC 27005:2022", fr)
        self.assertIn("{n}", views_how.T["en"]["conf"])

    def test_four_screens_map_to_the_five_workshops_one_line_each(self):
        en = self.page("/how")
        block = re.search(r"<ol><li><b>About you</b>.*?</ol>", en, re.S).group(0)
        items = re.findall(r"<li>(.*?)</li>", block)
        self.assertEqual(len(items), 4)
        self.assertIn("workshop 1", items[0])
        self.assertIn("workshops 2 and 3", items[1])
        self.assertIn("workshops 4 and 5", items[2])
        self.assertIn("workshop 5", items[3])

    def test_the_sources_named_are_those_of_the_catalogue(self):
        cat = engine.quick_catalogue()
        ids = {s["id"] for s in cat["sources"]}
        self.assertEqual(ids, {"ebios-rm-1.5", "nist-800-30r1"})
        en = self.page("/how")
        self.assertIn("ANSSI guide", en)
        self.assertIn("NIST SP 800-30", en)
        for other in ("ISO/IEC 27001", "CIS ", "OWASP", "MITRE", "ENISA"):
            self.assertNotIn(other, en)

    def test_the_scales_are_described_in_the_plain_words(self):
        en = self.page("/how?lang=en")
        for w in ("Minor", "Noticeable", "Serious", "Very serious", "Low, Moderate, High"):
            self.assertIn(w, en)
        self.assertNotIn("Critical", en)
        fr = self.page("/how?lang=fr")
        for w in ("Mineur", "Notable", "Sérieux", "Très sérieux", "Faible, Modéré, Élevé"):
            self.assertIn(w, fr)
        self.assertNotIn("Critique", fr)

    def test_no_outgoing_call_in_the_code(self):
        """"Nothing is sent elsewhere": the app and the engine import no network client."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        banned = re.compile(r"^\s*(?:import|from)\s+(?:urllib\.request|http\.client|requests|smtplib|ftplib|xmlrpc\.client)\b", re.M)
        for f in list((root / "app" / "atelier_app").glob("*.py")) + list((root / "engine" / "atelier_engine").glob("*.py")):
            self.assertIsNone(banned.search(f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()
