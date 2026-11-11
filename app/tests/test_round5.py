"""Round 5: the cloud infrastructure pack end to end, "Send my study to CPLT", anonymous counts, the privacy page, the
footer punctuation. Public-mode tests use an in-process client (no socket, no outbound call)."""
import datetime
import html
import io
import json
import os
import pathlib
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from app.tests import helpers
from app.tests import test_quick_path as qp
from app.tests.helpers import HAVE_OPENPYXL, PRE_RE, SID_RE_ANY
from app.tests.test_tone import EN_NEGATIVE, FEAR, FR_NEGATIVE, words_read
from atelier_app import app as app_mod, labels, shares, stats, views, views_how, views_privacy, views_share, workspaces

PUBLISHER = {"name": "CPLT", "url": "https://cplt.tech", "email": "hello@cplt.tech"}
TYPED = "Zorblax"      # a word only a visitor types: it must never reach the counts


class Client(helpers.Client):
    def text(self, resp):
        return html.unescape(super().text(resp))


def make(publisher=PUBLISHER, public=True, **kw):
    """An app on a fresh data dir; publisher.json is written first so the app reads it."""
    d = tempfile.mkdtemp(prefix="atelier-r5-")
    if publisher is not None:
        (pathlib.Path(d) / "publisher.json").write_text(json.dumps(publisher))
    return app_mod.App(d, port=8770, public=public, invite_code=None, **kw), d


def visitor(app):
    c = Client(app)
    page = c.text(c.get("/join"))
    assert c.post("/join", {"pre": PRE_RE.search(page).group(1)}).status == 303
    return c


def walk(c, tools=("cloud_infra",), lang="en", discard=(), custom="", name=TYPED + " Bakery", go="next", stop="results"):
    """A visitor goes through the screens; returns the study id."""
    form = {"name": name, "activity": TYPED + " activity", "values": TYPED + " orders", "tools": list(tools), "downtime": "day",
            "sensitivity": "internal", "lang": lang}
    r = c.post_csrf("/quick/new", form, page="/quick/new")
    assert r.status == 303, c.text(r)[:300]
    sid = SID_RE_ANY.search(r.get("Location")).group(0)
    if stop == "risks":
        return sid
    ids = re.findall(r'name="keep" value="([^"]+)"', c.text(c.get(f"/quick/{sid}/risks")))
    form = {"keep": [i for i in ids if i not in discard], "lang": lang}
    for i in discard:
        form[f"reason_{i}"] = TYPED + " reason"
    if custom:
        form["new_title_1"] = custom
    r = c.post_csrf(f"/quick/{sid}/risks", form, page=f"/quick/{sid}/risks")
    assert r.status == 303, c.text(r)[:300]
    if stop == "now":
        return sid
    page = c.text(c.get(f"/quick/{sid}/now"))
    form = {"lang": lang, "go": go}
    for rid in re.findall(r'id="risk-([^"]+)"', page):
        form[f"lik_{rid}"] = "possible" if rid.startswith("D") else "once"
    for i, m in enumerate(re.findall(r'name="m_([^"]+)" value="extra"', page)):
        if i % 3 == 0:
            form[f"m_{m}"] = "extra"
        elif i % 3 == 1:
            form[f"m_{m}"] = "in"
    r = c.post_csrf(f"/quick/{sid}/now", form, page=f"/quick/{sid}/now")
    assert r.status == 303, c.text(r)[:300]
    return sid


def share_form(**over):
    f = {"email": "zorblax@example.org", "message": TYPED + " message", "consent": "1", "lang": "en"}
    f.update(over)
    return {k: v for k, v in f.items() if v is not None}


def shared_dirs(app):
    return sorted(p for p in (app.data_dir / "shared").iterdir())


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def stat_lines(app):
    out = []
    for f in sorted((app.data_dir / "stats").glob("*.jsonl")):
        out += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    return out


class Cleanup:
    def make(self, **kw):
        app, d = make(**kw)
        self.addCleanup(shutil.rmtree, d, True)
        self.addCleanup(setattr, views, "PUBLISHER", None)
        return app


# ------------------------------------------------------------------ A. cloud infrastructure

class CloudToolFlow(qp.Base):
    def test_the_tool_is_ticked_on_about_you_in_both_languages(self):
        en = html.unescape(self.page("/quick/new?lang=en"))
        self.assertIn('name="tools" value="cloud_infra"', en)
        self.assertIn("Servers, apps or data on AWS, Google Cloud or Microsoft Azure", en)
        self.assertIn("A virtual server, a hosted company application, a cloud database", en)
        self.assertNotIn('name="tools" value="cloud_infra" checked', en)
        fr = html.unescape(self.page("/quick/new?lang=fr"))
        self.assertIn("Serveurs, applications ou données sur AWS, Google Cloud ou Microsoft Azure", fr)

    def test_a_cloud_study_reaches_the_results_with_the_new_risks_and_based_on(self):
        sid = self.start(tools=["cloud_infra"])
        self.assertEqual([s["label"] for s in self.study(sid)["supporting_assets"]],
                         ["Servers, apps or data on AWS, Google Cloud or Microsoft Azure"])
        ids = self.keep_all(sid)
        self.assertTrue({"D16", "D17", "D18", "D19", "D20", "A18", "A19", "A20", "A21", "D11", "A05", "A09", "D07", "D13"} <= set(ids), ids)
        r, _ = self.rate_all(sid)
        self.assertEqual(r.status, 303)
        res = html.unescape(self.page(f"/quick/{sid}/results"))
        self.assertIn("You run servers, apps or data in the cloud.", res)          # the "Based on" line quotes the tool
        for risk in ("Cloud account taken over through a leaked access key or secret", "A runaway cloud bill after a mistake"):
            self.assertIn(risk, res)
        fr = html.unescape(self.page(f"/quick/{sid}/results?lang=fr"))
        self.assertIn("Vous faites tourner serveurs, applications ou données dans le cloud.", fr)
        self.assertEqual(self.c.get(f"/quick/{sid}/results").status, 200)

    def test_maps_excel_and_expert_mode_work_unchanged(self):
        sid = self.start(tools=["cloud_infra"])
        self.keep_all(sid)
        self.rate_all(sid)
        res = self.page(f"/quick/{sid}/results")
        self.assertEqual(res.count("<svg"), 2)                                        # the two maps
        self.c.expert()
        for path in (f"/s/{sid}", f"/s/{sid}/register", f"/s/{sid}/w2", f"/s/{sid}/w3", f"/s/{sid}/w4"):
            self.assertEqual(self.c.get(path).status, 200, path)
        if HAVE_OPENPYXL:
            import openpyxl
            r = self.c.get(f"/s/{sid}/export.xlsx")
            self.assertEqual(r.status, 200)
            wb = openpyxl.load_workbook(io.BytesIO(r.body))
            cells = {str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c}
            for rid in ("D16", "A21"):
                self.assertIn(rid, cells)
            self.assertTrue(any("leaked access key" in c for c in cells))

    def test_the_how_it_works_page_has_one_line_about_cloud_infrastructure(self):
        self.assertIn("Cloud infrastructure (servers, apps or data on a public cloud) is covered with the same method.",
                      html.unescape(self.page("/how?lang=en")))
        self.assertIn("L'infrastructure cloud (serveurs, applications ou données sur un cloud public) est couverte avec la même méthode.",
                      html.unescape(self.page("/how?lang=fr")))

    def test_every_new_measure_has_a_short_name_a_figure_and_a_group(self):
        new = {"secrets_vault", "key_rotation", "admin_device", "resource_inventory", "exposure_review", "separate_backup",
               "activity_logs", "ir_help", "cost_limits", "data_location", "encrypt_own_keys", "qualified_provider"}
        ids = {m["id"] for r in self.cat["risks"] for m in r["measures"]}
        self.assertTrue(new <= ids)
        for mid in new:
            self.assertIn(mid, labels.EFFORT)
            self.assertIn(mid, labels.MEASURE_GROUP)

    def test_wording_of_the_cloud_content_and_pages(self):
        """Positive wording and no fear words in every new text, EN and FR (catalogue, labels, how page, results)."""
        texts = []
        for r in self.cat["risks"]:
            if "cloud-infra" in r["packs"]:
                for lang in ("en", "fr"):
                    texts += [r["title"][lang], r["description"][lang], r["why"][lang]] + [m[lang] for m in r["measures"]]
        for lang in ("en", "fr"):
            texts += [labels.short_action(m, lang) for m in labels.EFFORT] + [labels.effort_line(m, lang) for m in labels.EFFORT]
        for t in self.cat["tools"]:
            if t["id"] == "cloud_infra":
                texts += [t["en"], t["fr"], t["example"]["en"], t["example"]["fr"]]
        for t in texts:
            lang_rx = (EN_NEGATIVE, FR_NEGATIVE)
            for rx in lang_rx:
                self.assertIsNone(rx.search(t), t)
            self.assertIsNone(FEAR.search(t), t)
        sid = self.start(tools=["cloud_infra"], lang="en")
        self.keep_all(sid)
        self.rate_all(sid)
        for lang, rx in (("en", EN_NEGATIVE), ("fr", FR_NEGATIVE)):
            for path in (f"/quick/{sid}/risks", f"/quick/{sid}/now", f"/quick/{sid}/results", "/how", "/quick/new"):
                text = words_read(self.page(f"{path}?lang={lang}"))
                self.assertIsNone(rx.search(text), (lang, path, rx.search(text)))
                self.assertIsNone(FEAR.search(text), (lang, path, FEAR.search(text)))


# ------------------------------------------------------------------ B. Send my study to CPLT

class ShareTest(Cleanup, unittest.TestCase):
    def setUp(self):
        self.app = self.make()
        self.c = visitor(self.app)
        self.sid = walk(self.c)

    def test_the_card_is_the_last_block_of_the_results_page_with_an_unticked_consent_box(self):
        en = self.c.text(self.c.get(f"/quick/{self.sid}/results?lang=en"))
        self.assertIn("Want a deeper look?", en)
        self.assertIn("Send your study to CPLT. We reply by email with a fuller strategy.", en)
        self.assertIn("I agree to send my answers, including the text I typed, to CPLT, who keeps them for 12 months to reply to me.", en)
        self.assertEqual(en.count('class="card share-card"'), 1)
        self.assertGreater(en.index("share-card"), en.index('class="closing"'))
        self.assertLess(en.index("share-card"), en.index("</main>"))
        form = re.search(r'<form method="post" action="/quick/[^"]+/share".*?</form>', en, re.S).group(0)
        self.assertIn('name="csrf"', form)
        self.assertIn('type="email" name="email"', form)
        self.assertIn('name="message"', form)
        box = re.search(r'<input type="checkbox" name="consent"[^>]*>', form).group(0)
        self.assertNotIn("checked", box)
        fr = self.c.text(self.c.get(f"/quick/{self.sid}/results?lang=fr"))
        self.assertIn("Envie d'aller plus loin ?", fr)
        self.assertIn("J'accepte d'envoyer mes réponses, y compris les textes saisis, à CPLT, qui les conserve 12 mois pour me répondre.", fr)

    def test_happy_path_stores_the_study_and_the_contact_outside_the_workspace(self):
        r = self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page=f"/quick/{self.sid}/results")
        self.assertEqual(r.status, 200)
        page = self.c.text(r)
        self.assertIn("Thank you", page)
        self.assertIn("12 months", page)
        self.assertIn("reply by email", page)
        self.assertIn("hello@cplt.tech", page)                    # who to write to for an earlier removal
        self.assertNotIn("zorblax@example.org", page)             # what the visitor typed is not printed back
        (folder,) = shared_dirs(self.app)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.assertRegex(folder.name, rf"^{today}-[0-9a-f]{{16}}$")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["contact.json", "study.json"])
        contact = json.loads((folder / "contact.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(contact), ["created", "email", "lang", "message", "study_name"])
        self.assertEqual((contact["email"], contact["message"], contact["lang"], contact["study_name"]),
                         ("zorblax@example.org", TYPED + " message", "en", TYPED + " Bakery"))
        self.assertRegex(contact["created"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        study = (folder / "study.json").read_bytes()
        dl = self.c.get(f"/s/{self.sid}/export.json").body
        self.assertEqual(study, dl)                                # the same text as the study file download
        self.assertEqual(json.loads(study)["format"], "atelier-study")
        self.assertNotIn(self.app.data_dir / "workspaces", folder.parents)
        self.assertFalse(any(self.app.data_dir.joinpath("workspaces").rglob("contact.json")))

    def test_file_modes(self):
        self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        (folder,) = shared_dirs(self.app)
        self.assertEqual(mode(self.app.data_dir / "shared"), 0o700)
        self.assertEqual(mode(folder), 0o700)
        for f in folder.iterdir():
            self.assertEqual(mode(f), 0o600, f.name)

    def test_no_consent_bad_email_and_a_long_message_get_a_kind_400_and_store_nothing(self):
        cases = [(share_form(consent=None), "tick the box"), (share_form(consent=""), "tick the box"),
                 (share_form(email="not-an-email"), "check the email"), (share_form(email=""), "check the email"),
                 (share_form(email="a@b"), "check the email"), (share_form(email="a b@example.org"), "check the email"),
                 (share_form(email="a@example.org\nBcc: x@y.org"), "check the email"),
                 (share_form(message="x" * 501), "500 characters")]
        for form, words in cases:
            r = self.c.post_csrf(f"/quick/{self.sid}/share", form, page="/")
            self.assertEqual(r.status, 400, form)
            self.assertIn(words, self.c.text(r))
        self.assertEqual(shared_dirs(self.app), [])
        ok = self.c.post_csrf(f"/quick/{self.sid}/share", share_form(message="x" * 500), page="/")   # 500 is allowed
        self.assertEqual(ok.status, 200)

    def test_csrf_is_required(self):
        r = self.c.post(f"/quick/{self.sid}/share", share_form())
        self.assertEqual(r.status, 403)
        self.assertEqual(shared_dirs(self.app), [])

    def test_a_visitor_cannot_share_another_visitors_study(self):
        other = visitor(self.app)
        r = other.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        self.assertEqual(r.status, 404)
        self.assertEqual(shared_dirs(self.app), [])

    def test_three_a_day_per_workspace_then_429(self):
        for i in range(3):
            self.assertEqual(self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/").status, 200, i)
        r = self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        self.assertEqual(r.status, 429)
        self.assertIn("tomorrow", self.c.text(r))
        self.assertEqual(len(shared_dirs(self.app)), 3)
        other = visitor(self.app)                                  # the limit counts per workspace
        sid2 = walk(other)
        self.assertEqual(other.post_csrf(f"/quick/{sid2}/share", share_form(), page="/").status, 200)
        self.assertEqual(len(shared_dirs(self.app)), 4)

    def test_the_limits_are_those_of_the_brief(self):
        self.assertEqual((shares.MAX_PER_DAY, shares.MAX_SHARED, shares.KEEP_DAYS, shares.MAX_MESSAGE), (3, 2000, 365, 500))
        self.assertEqual(self.app.shares.max_shared, 2000)

    def test_a_full_instance_gets_a_kind_page_with_the_email(self):
        self.app.shares.max_shared = 1
        self.assertEqual(self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/").status, 200)
        r = self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        self.assertEqual(r.status, 503)
        t = self.c.text(r)
        self.assertIn("We are full for now, please write to hello@cplt.tech.", t)
        self.assertEqual(len(shared_dirs(self.app)), 1)

    def test_two_thousand_folders_is_full(self):
        root = self.app.data_dir / "shared"
        for i in range(2000):
            (root / f"2026-01-01-{i:016x}").mkdir()
        r = self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        self.assertEqual(r.status, 503)
        self.assertEqual(len(list(root.iterdir())), 2000)

    def test_purge_shared_deletes_folders_older_than_a_year_only(self):
        for _ in range(2):
            self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        a, b = shared_dirs(self.app)
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
        a.rename(a.with_name(old + a.name[10:]))
        near = self.app.data_dir / "shared" / ((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=360)).strftime("%Y-%m-%d") + "-" + "0" * 16)
        near.mkdir()
        self.assertEqual(self.app.purge_shared(), 1)
        self.assertEqual(sorted(p.name for p in shared_dirs(self.app)), sorted([b.name, near.name]))
        self.assertEqual(self.app.purge_shared(days=365), 0)
        os.utime(b, (1, 1))                                        # a folder that is old by its own time is deleted too
        self.assertEqual(self.app.purge_shared(days=365), 1)
        self.assertEqual([p.name for p in shared_dirs(self.app)], [near.name])

    def test_the_purge_loop_runs_purge_shared_next_to_purge_idle(self):
        from atelier_app import server
        import threading
        calls = []
        app = mock.Mock(purge_idle=lambda: calls.append("idle") or 0, purge_shared=lambda: calls.append("shared") or 0)
        stop = threading.Event()
        stop.set()
        server.purge_loop(app, every=0, stop=stop)
        self.assertEqual(calls, ["idle", "shared"])

    def test_delete_my_data_keeps_the_shared_copy_and_the_privacy_page_says_how_to_remove_it(self):
        self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/")
        r = self.c.post_csrf("/forget", {}, page="/")
        self.assertEqual(r.status, 200)
        self.assertEqual(len(shared_dirs(self.app)), 1)
        self.assertEqual(len(list((self.app.data_dir / "workspaces").iterdir())), 0)
        en = self.c.text(self.c.get("/privacy?lang=en"))
        self.assertIn("Delete my data leaves this copy in place", en)
        self.assertIn('<a href="mailto:hello@cplt.tech">hello@cplt.tech</a>', en)

    def test_the_app_makes_no_outbound_call_and_sends_no_email(self):
        def refuse(*a, **k):
            raise AssertionError("outbound call")
        with mock.patch.object(socket.socket, "connect", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse):
            self.assertEqual(self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/").status, 200)
        src = "".join((helpers.APP_DIR / "atelier_app" / f).read_text(encoding="utf-8")
                      for f in ("shares.py", "stats.py", "views_share.py", "quick_routes.py", "app.py"))
        for module in ("smtplib", "urllib.request", "http.client", "requests", "import socket", "imaplib", "ftplib"):
            self.assertNotIn(module, src, module)

    def test_hidden_without_an_email_in_publisher_json(self):
        for pub in (None, {"name": "CPLT", "url": "https://cplt.tech"}):
            app = self.make(publisher=pub)
            c = visitor(app)
            sid = walk(c)
            self.assertNotIn("share-card", c.text(c.get(f"/quick/{sid}/results")))
            self.assertNotIn("Want a deeper look?", c.text(c.get(f"/quick/{sid}/results")))
            r = c.post_csrf(f"/quick/{sid}/share", share_form(), page="/")
            self.assertEqual(r.status, 404)
            self.assertEqual(shared_dirs(app), [])

    def test_hidden_in_local_mode(self):
        app = self.make(public=False)
        c = Client(app)
        c.login()
        sid = walk_local(c)
        res = c.text(c.get(f"/quick/{sid}/results"))
        self.assertNotIn("share-card", res)
        self.assertNotIn("Want a deeper look?", res)
        self.assertEqual(c.post_csrf(f"/quick/{sid}/share", share_form(), page="/").status, 404)
        self.assertFalse((app.data_dir / "shared").exists())
        self.assertFalse((app.data_dir / "stats").exists())

    def test_the_new_pages_keep_the_tone_in_both_languages(self):
        pages = {}
        for lang, rx in (("en", EN_NEGATIVE), ("fr", FR_NEGATIVE)):
            pages[(lang, "card")] = self.c.text(self.c.get(f"/quick/{self.sid}/results?lang={lang}"))
            for name, form in (("consent", share_form(consent=None, lang=lang)), ("email", share_form(email="x", lang=lang)),
                               ("long", share_form(message="x" * 501, lang=lang)), ("ok", share_form(lang=lang))):
                pages[(lang, name)] = self.c.text(self.c.post_csrf(f"/quick/{self.sid}/share", form, page="/"))
            for (lg, name), body in pages.items():
                if lg != lang:
                    continue
                text = words_read(body)
                self.assertIsNone(rx.search(text), (lang, name, rx.search(text)))
                self.assertIsNone(FEAR.search(text), (lang, name, FEAR.search(text)))
        self.app.shares.max_shared = 0
        self.assertEqual(self.c.post_csrf(f"/quick/{self.sid}/share", share_form(), page="/").status, 503)
        for lang, rx in (("en", EN_NEGATIVE), ("fr", FR_NEGATIVE)):
            for fn in (lambda: views_share.full_page(lang, None, self.sid, "a@b.org"), lambda: views_share.limit_page(lang, None, self.sid)):
                text = words_read(fn())
                self.assertIsNone(rx.search(text))
                self.assertIsNone(FEAR.search(text))
        for lang in ("en", "fr"):
            self.assertLessEqual(len(views_share.T[lang]["card_p"].split()), 16)


def walk_local(c, tools=("cloud_infra",)):
    sid = walk_login(c, tools)
    return sid


def walk_login(c, tools):
    form = {"name": "Local", "activity": "x", "values": "y", "tools": list(tools), "downtime": "day", "sensitivity": "internal", "lang": "en"}
    r = c.post_csrf("/quick/new", form, page="/quick/new")
    sid = SID_RE_ANY.search(r.get("Location")).group(0)
    ids = re.findall(r'name="keep" value="([^"]+)"', c.text(c.get(f"/quick/{sid}/risks")))
    c.post_csrf(f"/quick/{sid}/risks", {"keep": ids, "lang": "en"}, page="/")
    page = c.text(c.get(f"/quick/{sid}/now"))
    form = {"lang": "en", "go": "next"}
    for rid in re.findall(r'id="risk-([^"]+)"', page):
        form[f"lik_{rid}"] = "possible" if rid.startswith("D") else "once"
    c.post_csrf(f"/quick/{sid}/now", form, page="/")
    return sid


# ------------------------------------------------------------------ C. anonymous counts

class StatsTest(Cleanup, unittest.TestCase):
    def setUp(self):
        self.app = self.make()
        self.c = visitor(self.app)

    def test_a_study_leaves_the_expected_lines_and_only_allowed_keys(self):
        sid = walk(self.c, discard=["D16"], custom=TYPED + " custom risk")
        self.c.get(f"/s/{sid}/export.json")
        self.c.get(f"/s/{sid}/export.xlsx")
        self.c.post_csrf(f"/quick/{sid}/share", share_form(), page="/")
        self.c.post_csrf("/forget", {}, page="/")
        lines = stat_lines(self.app)
        events = [d["event"] for d in lines]
        self.assertEqual(events[:3], ["study_started", "step_reached", "step_reached"])
        for ev in ("risk_discarded", "risk_added", "measures", "download", "shared", "forget"):
            self.assertIn(ev, events, ev)
        self.assertEqual([d["step"] for d in lines if d["event"] == "step_reached"], ["about", "risks", "now", "results"])
        started = lines[0]
        self.assertEqual((started["tools"], started["sensitivity"], started["downtime"]), (["cloud_infra"], "internal", "day"))
        self.assertEqual([d["risk"] for d in lines if d["event"] == "risk_discarded"], ["D16"])
        m = next(d for d in lines if d["event"] == "measures")["measures"]
        self.assertTrue(m and set(m.values()) <= {"in", "extra", "none"} and {"in", "extra"} <= set(m.values()))
        self.assertEqual(sorted(d["kind"] for d in lines if d["event"] == "download"), (["study", "xlsx"] if helpers.HAVE_OPENPYXL else ["study"]))
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        for d in lines:
            self.assertLessEqual(set(d), stats.ALLOWED_KEYS, d)
            self.assertEqual(d["day"], today)
            self.assertRegex(d["day"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn(d["event"], stats.EVENTS)
            self.assertLessEqual(set(d) - {"day", "event"}, set(stats.FIELDS[d["event"]]), d)

    def test_no_identifier_no_typed_text_no_email_in_the_files(self):
        sid = walk(self.c, discard=["D16"], custom=TYPED + " custom risk")
        self.c.post_csrf(f"/quick/{sid}/share", share_form(), page="/")
        self.c.get(f"/s/{sid}/export.json")
        blob = "".join(f.read_text(encoding="utf-8") for f in (self.app.data_dir / "stats").glob("*.jsonl"))
        self.assertTrue(blob)
        wid = self.c.cookies["atelier_session"]
        h = workspaces.hash_id(wid)
        for secret in (wid, h, h[:16], sid, "zorblax", "example.org", "@", TYPED.lower(), "127.0.0.1", "Mozilla", "T1", ":00"):
            self.assertNotIn(secret.lower(), blob.lower(), secret)
        self.assertEqual(self.c.csrf("/"), self.c.csrf("/"))
        self.assertNotIn(self.c.csrf("/"), blob)

    def test_the_files_and_folder_are_private_and_named_by_month(self):
        walk(self.c, stop="risks")
        (f,) = (self.app.data_dir / "stats").iterdir()
        self.assertRegex(f.name, r"^\d{4}-\d{2}\.jsonl$")
        self.assertEqual(f.name[:7], datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m"))
        self.assertEqual(mode(f), 0o600)
        self.assertEqual(mode(f.parent), 0o700)

    def test_a_risk_of_the_visitors_own_and_unknown_ids_are_not_counted(self):
        sid = walk(self.c, custom="Own risk", stop="now")
        self.assertEqual([d["event"] for d in stat_lines(self.app)].count("risk_added"), 1)
        page = self.c.text(self.c.get(f"/quick/{sid}/risks"))
        ids = [i for i in re.findall(r'name="keep" value="([^"]+)"', page) if i != "C1"]
        self.c.post_csrf(f"/quick/{sid}/risks", {"keep": ids, "lang": "en"}, page="/")     # the own risk is set aside
        self.assertEqual([d for d in stat_lines(self.app) if d["event"] == "risk_discarded"], [])
        self.app._stat("risk_discarded", risk="C1")
        self.app._stat("risk_discarded", risk="Zorblax secret")
        self.assertEqual([d for d in stat_lines(self.app) if d["event"] == "risk_discarded"], [])

    def test_clean_drops_every_other_field(self):
        line = stats.clean("study_started", {"tools": ["office", "bad id!"], "sensitivity": "internal", "downtime": "day",
                                             "email": "a@b.org", "workspace": "abc", "study": "s-1", "ip": "1.2.3.4", "time": "12:00"})
        self.assertEqual(sorted(line), ["day", "downtime", "event", "sensitivity", "tools"])
        self.assertEqual(line["tools"], ["office"])
        self.assertIsNone(stats.clean("risk_discarded", {"risk": "free text with spaces"}))
        self.assertIsNone(stats.clean("nope", {}))
        self.assertEqual(stats.clean("download", {"kind": "xlsx", "path": "/x"})["kind"], "xlsx")
        self.assertIsNone(stats.clean("download", {"kind": "../../etc"}))
        self.assertEqual(sorted(stats.clean("shared", {"email": "a@b"})), ["day", "event"])
        self.assertEqual(sorted(stats.clean("forget", {"x": 1})), ["day", "event"])
        self.assertEqual(stats.clean("measures", {"measures": {"mfa": "in", "free text": "in", "x": "weird"}})["measures"], {"mfa": "in", "x": "none"})

    def test_a_broken_stats_folder_never_breaks_a_page(self):
        shutil.rmtree(self.app.data_dir / "stats")
        (self.app.data_dir / "stats").write_text("a file where a folder should be")
        with mock.patch("sys.stderr", new=io.StringIO()):
            sid = walk(self.c)
        self.assertEqual(self.c.get(f"/quick/{sid}/results").status, 200)

    def test_local_mode_counts_nothing(self):
        app = self.make(public=False)
        c = Client(app)
        c.login()
        walk_local(c)
        c.get("/s/%s/export.json" % SID_RE_ANY.search(c.text(c.get("/studies"))).group(0))
        self.assertFalse((app.data_dir / "stats").exists())

    def test_the_stats_command_prints_a_summary(self):
        a, b = self.app, self.c
        sid = walk(b, discard=["D16"], custom="Own risk")
        walk(visitor(a), tools=("office",), stop="risks")
        b.get(f"/s/{sid}/export.json")
        b.post_csrf(f"/quick/{sid}/share", share_form(), page="/")
        month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run = lambda *args: subprocess.run([sys.executable, "-m", "atelier_app.stats", *args], cwd=helpers.APP_DIR, env=env,
                                           capture_output=True, text=True, timeout=60)
        for extra in ([], ["--month", month]):
            r = run(str(a.data_dir), *extra)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = r.stdout
            self.assertIn("Studies started: 2", out)
            self.assertIn("Reached: about 2, risks 2, now 1, results 1", out)
            self.assertIn("Top discarded risks: D16 (1)", out)
            self.assertRegex(out, r"Most chosen measures: \w+ \(\d+: \d+ planned, \d+ in place\)")
            self.assertIn("Downloads: xlsx 0, study 1, maps 0", out)
            self.assertIn("Studies shared: 1", out)
            self.assertLess(len(out.splitlines()), 15)
        other = run(str(a.data_dir), "--month", "1999-01")
        self.assertEqual(other.returncode, 0)
        self.assertIn("Studies started: 0", other.stdout)
        self.assertEqual(run(str(a.data_dir), "--month", "2026-13").returncode, 2)
        self.assertEqual(run(str(a.data_dir / "missing")).returncode, 2)

    def test_the_stats_command_reports_what_it_cannot_read_and_skips_bad_lines_out_loud(self):
        f = self.app.data_dir / "stats" / "2026-01.jsonl"
        f.write_text('{"day": "2026-01-02", "event": "forget"}\nnot json\n[1]\n')
        r = subprocess.run([sys.executable, "-m", "atelier_app.stats", str(self.app.data_dir)], cwd=helpers.APP_DIR,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Data deleted by visitors: 1", r.stdout)
        self.assertIn("Lines skipped (not valid): 2", r.stdout)
        f.chmod(0)
        if os.access(f, os.R_OK):
            self.skipTest("this user reads files whatever their mode")
        r = subprocess.run([sys.executable, "-m", "atelier_app.stats", str(self.app.data_dir)], cwd=helpers.APP_DIR,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Studies started", r.stdout)


# ------------------------------------------------------------------ D. privacy page

class PrivacyTest(Cleanup, unittest.TestCase):
    def test_the_facts_in_english_and_french(self):
        app = self.make(publisher=dict(PUBLISHER, legal_url="https://cplt.tech/legal"))
        c = Client(app)
        en = c.text(c.get("/privacy?lang=en"))
        for fact in ("If you send us your study", "12 months", "6(1)(a)", "6(1)(f)", "anonymous counts", "consent",
                     "with one email to", '<a href="mailto:hello@cplt.tech">hello@cplt.tech</a>', "Delete my data leaves this copy in place",
                     "including the text you typed", "30 days", "6(1)(b)"):
            self.assertIn(fact, en)
        fr = c.text(c.get("/privacy?lang=fr"))
        for fact in ("Si vous nous envoyez votre étude", "12 mois", "6(1)(a)", "6(1)(f)", "comptages anonymes", "consentement",
                     "Effacer mes données laisse cette copie en place", "y compris les textes saisis", "30 jours", "6(1)(b)"):
            self.assertIn(fact, fr)
        for lang, body, rx in (("en", en, EN_NEGATIVE), ("fr", fr, FR_NEGATIVE)):
            text = words_read(body)
            self.assertIsNone(rx.search(text), (lang, rx.search(text)))
            self.assertIsNone(FEAR.search(text), (lang, FEAR.search(text)))
        self.assertEqual(en.count("<h2>"), len(views_privacy.T["en"]["sections"]))
        self.assertEqual(fr.count("<h2>"), len(views_privacy.T["fr"]["sections"]))
        self.assertTrue(views_privacy.UPDATED["en"].endswith("2026") and "2026" in views_privacy.UPDATED["fr"])

    def test_the_counts_statement_names_no_identifier(self):
        app = self.make()
        c = Client(app)
        en = c.text(c.get("/privacy?lang=en"))
        sec = re.search(r"<h2>What we keep</h2><p>(.*?)</p>", en, re.S).group(1)
        for word in ("anonymous counts", "no identifier", "improve Atelier", "6(1)(f)"):
            self.assertIn(word, sec)


# ------------------------------------------------------------------ E. footer punctuation

class FooterTest(Cleanup, unittest.TestCase):
    def footer(self, email, feedback, privacy):
        pub = dict(PUBLISHER)
        if not email:
            pub.pop("email")
        if feedback:
            pub["feedback_url"] = "https://cplt.tech/contact"
        app = self.make(publisher=pub, public=privacy)      # the privacy link exists in public mode only
        c = Client(app)
        if not privacy:
            c.login()
        m = re.search(r'<footer class="publisher">(.*?)</footer>', c.text(c.get("/how?lang=en")), re.S)
        self.assertIsNotNone(m)
        return m.group(1), re.sub(r"<[^>]+>", "", m.group(1))      # the text as a person reads it: tags removed, nothing added

    def test_every_combination_reads_cleanly(self):
        for email in (True, False):
            for feedback in (True, False):
                for privacy in (True, False):
                    raw, text = self.footer(email, feedback, privacy)
                    key = (email, feedback, privacy)
                    one_line = " ".join(html.unescape(text).split())
                    self.assertTrue(one_line.startswith("Atelier is offered by CPLT, cplt.tech"), (key, one_line))
                    for bad in (". ·", "·.", "..", "· ·", ",.", ". .", "· Your feedback"):
                        self.assertNotIn(bad, one_line, (key, one_line))
                    self.assertFalse(one_line.endswith("·"), (key, one_line))
                    self.assertEqual("hello@cplt.tech" in one_line, email, key)
                    self.assertEqual("Share it" in one_line, feedback, key)
                    self.assertEqual("Your data and legal notice" in one_line, privacy, key)
                    # a middle dot joins the email to the site, and the feedback line to the privacy link
                    self.assertEqual(one_line.count("·"), (1 if email else 0) + (1 if feedback and privacy else 0), (key, one_line))
                    self.assertEqual(raw.count("</a>"), 1 + email + feedback + privacy, key)

    def test_the_reported_case_reads_with_one_full_stop(self):
        raw, text = self.footer(True, False, True)
        self.assertIn('<a href="mailto:hello@cplt.tech">hello@cplt.tech</a>. <a href="/privacy?lang=en">Your data and legal notice</a>', raw)
        self.assertNotIn(". ·", " ".join(text.split()))
        raw, text = self.footer(False, False, True)
        self.assertIn('>cplt.tech</a>. <a href="/privacy?lang=en">', raw)

    def test_the_french_footer_reads_cleanly_too(self):
        app = self.make(publisher=dict(PUBLISHER))
        c = Client(app)
        m = re.search(r'<footer class="publisher">(.*?)</footer>', c.text(c.get("/how?lang=fr")), re.S)
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).split())
        self.assertIn("hello@cplt.tech. Vos données et mentions légales", text)
        self.assertNotIn(". ·", text)


if __name__ == "__main__":
    unittest.main()
