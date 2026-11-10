"""Source documents: docx and pdf extraction, upload caps and types, storage modes, list, delete, escaping, CSRF.

Every document here is synthetic (built by helpers.make_docx / make_pdf from invented text). The pdf tests that need
pdftotext skip when it is not on PATH; the refusal without pdftotext is tested by hiding it.
"""
import io
import os
import re
import stat
import unittest
import zipfile
from unittest import mock

from app.tests import helpers
from app.tests.helpers import Client, make_app, make_docx, make_pdf, upload
from atelier_app import config, documents

HAVE_PDFTOTEXT = documents.pdftotext_path() is not None


class ExtractionTest(unittest.TestCase):
    def test_docx_paragraphs_and_table(self):
        data = make_docx(["The shop takes orders online.", "Payments go through a provider & a bank."],
                         [["Asset", "Owner"], ["Web shop", "IT"]])
        text = documents.extract_text("docx", data)
        self.assertEqual(text.splitlines(), ["The shop takes orders online.", "Payments go through a provider & a bank.",
                                             "Asset | Owner", "Web shop | IT"])

    def test_docx_refusals(self):
        with self.assertRaisesRegex(documents.DocumentError, "not a zip archive"):
            documents.extract_text("docx", b"plain text, not a docx")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.xml", "<x/>")
        with self.assertRaisesRegex(documents.DocumentError, "no word/document.xml"):
            documents.extract_text("docx", buf.getvalue())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:  # an entity declaration: refused before parsing
            z.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><d>&a;</d>')
        with self.assertRaisesRegex(documents.DocumentError, "declares a document type"):
            documents.extract_text("docx", buf.getvalue())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:  # expands 1000 times: refused unread
            z.writestr("word/document.xml", "<d>" + " " * 3_000_000 + "</d>")
        with self.assertRaisesRegex(documents.DocumentError, "expands to too much data"):
            documents.extract_text("docx", buf.getvalue())

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext is not on PATH")
    def test_pdf_text(self):
        text = documents.tidy(documents.extract_text("pdf", make_pdf(["Vaccine batches are labelled on site.",
                                                                       "Labels (and lots) are printed daily."])))
        self.assertEqual(text.splitlines(), ["Vaccine batches are labelled on site.", "Labels (and lots) are printed daily."])

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext is not on PATH")
    def test_pdf_damaged_or_not_a_pdf(self):
        with self.assertRaisesRegex(documents.DocumentError, "does not start like a PDF"):
            documents.extract_text("pdf", b"hello")
        with self.assertRaises(documents.DocumentError):
            documents.extract_text("pdf", b"%PDF-1.4\n garbage garbage")

    def test_pdf_refused_without_pdftotext(self):
        with mock.patch.object(documents.shutil, "which", return_value=None):
            with self.assertRaisesRegex(documents.DocumentError, "pdftotext program .* not on this machine's PATH"):
                documents.extract_text("pdf", make_pdf(["x"]))

    def test_plain_text_encodings(self):
        self.assertEqual(documents.extract_text("text", "café".encode("utf-8")), "café")
        self.assertEqual(documents.extract_text("text", "﻿café".encode("utf-8")), "café")
        self.assertEqual(documents.extract_text("markdown", "café".encode("cp1252")), "café")
        self.assertEqual(documents.extract_text("text", "café".encode("utf-16")), "café")
        with self.assertRaisesRegex(documents.DocumentError, "binary"):
            documents.extract_text("text", b"\x7fELF\x00\x01")


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.app, self.d = make_app()
        self.c = Client(self.app)
        self.c.login()
        r = self.c.post_csrf("/new", {"name": "Docs study", "calibration": "anssi-v1.5"})
        self.sid = helpers.SID_RE.search(r.get("Location")).group(1)

    def tearDown(self):
        helpers.cleanup(self.d)

    def page(self):
        r = self.c.get(f"/s/{self.sid}/docs")
        self.assertEqual(r.status, 200)
        return self.c.text(r)

    def test_upload_docx_listed_with_size_and_date_files_private(self):
        data = make_docx(["Invented text about a shop."])
        r = upload(self.c, self.sid, "notes.docx", data)
        self.assertEqual((r.status, r.get("Location")), (303, f"/s/{self.sid}/docs?f=uploaded"))
        docs = self.app.docs.list(self.sid)
        self.assertEqual(len(docs), 1)
        m = docs[0]
        self.assertEqual((m["name"], m["type"], m["size"], m["chars"]), ("notes.docx", "docx", len(data), 27))
        self.assertRegex(m["uploaded"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(self.app.docs.text(self.sid, m["id"]), "Invented text about a shop.")
        page = self.page()
        self.assertIn("notes.docx", page)
        self.assertIn(m["uploaded"][:16].replace("T", " "), page)
        self.assertRegex(page, r'<td class="num">\d+ KB</td>|<td class="num">\d+ B</td>')
        root = self.app.docs.root
        self.assertEqual(stat.S_IMODE(os.stat(root).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(root / self.sid).st_mode), 0o700)
        for f in (root / self.sid).iterdir():
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, f.name)

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext is not on PATH")
    def test_upload_pdf(self):
        r = upload(self.c, self.sid, "scope.pdf", make_pdf(["Invented scope line."]))
        self.assertEqual(r.status, 303)
        self.assertEqual(self.app.docs.text(self.sid, self.app.docs.list(self.sid)[0]["id"]), "Invented scope line.")

    def test_pdf_refused_with_a_clear_message_when_pdftotext_is_absent(self):
        with mock.patch.object(documents.shutil, "which", return_value=None):
            self.assertNotIn("PDF text is extracted with pdftotext", self.page())
            r = upload(self.c, self.sid, "scope.pdf", make_pdf(["x"]))
        self.assertEqual(r.status, 400)
        self.assertIn("PDF files need the pdftotext program", self.c.text(r))
        self.assertEqual(self.app.docs.list(self.sid), [])

    def test_types(self):
        for name, data in (("tool.exe", b"MZ"), ("study.json", b"{}"), ("noext", b"abc"), ("sheet.xlsx", b"PK")):
            r = upload(self.c, self.sid, name, data)
            self.assertEqual(r.status, 400, name)
            self.assertIn("only .txt, .md, .docx and .pdf files are accepted", self.c.text(r))
        self.assertEqual(upload(self.c, self.sid, "Notes.MD", b"# Title\ntext").status, 303)
        self.assertEqual(upload(self.c, self.sid, "a.txt", b"").status, 400)
        self.assertEqual([d["type"] for d in self.app.docs.list(self.sid)], ["markdown"])

    def test_caps(self):
        self.assertEqual(documents.MAX_DOC, 20 * 1024 * 1024)
        with self.assertRaisesRegex(documents.DocumentError, "over 20 MB"):
            self.app.docs.add(self.sid, "big.txt", b"a" * (documents.MAX_DOC + 1))
        # exactly 20 MB is accepted
        self.assertEqual(self.app.docs.add(self.sid, "max.txt", b"a" * documents.MAX_DOC)["size"], documents.MAX_DOC)
        # the request cap: 20 MB plus the envelope on the upload route, 5 MB anywhere else
        self.assertEqual(self.app.body_limit(f"/s/{self.sid}/docs"), config.MAX_DOCUMENT_BODY)
        self.assertEqual(self.app.body_limit("/import"), config.MAX_UPLOAD)
        body, ctype = helpers.multipart({"csrf": self.c.csrf()}, {"file": ("big.txt", b"a" * (config.MAX_DOCUMENT_BODY + 1))})
        r = self.c.req("POST", f"/s/{self.sid}/docs", body=body, ctype=ctype)
        self.assertEqual(r.status, 413)
        body, ctype = helpers.multipart({"csrf": self.c.csrf()}, {"file": ("s.json", b"a" * (config.MAX_UPLOAD + 1))})
        self.assertEqual(self.c.req("POST", "/import", body=body, ctype=ctype).status, 413)

    def test_delete_and_unknown_ids(self):
        upload(self.c, self.sid, "a.txt", b"one")
        did = self.app.docs.list(self.sid)[0]["id"]
        r = self.c.post_csrf(f"/s/{self.sid}/docs/{did}/delete", page=f"/s/{self.sid}/docs")
        self.assertEqual(r.status, 303)
        self.assertEqual(self.app.docs.list(self.sid), [])
        self.assertEqual(list((self.app.docs.root / self.sid).iterdir()), [])
        for bad in ("d000000000000", "..%2F..%2Ftoken", "dzzzzzzzzzzzz"):
            self.assertEqual(self.c.post_csrf(f"/s/{self.sid}/docs/{bad}/delete").status, 404, bad)

    def test_file_name_is_escaped_and_never_a_path(self):
        upload(self.c, self.sid, '../../<img src=x onerror=alert(1)>.txt', b"text")
        m = self.app.docs.list(self.sid)[0]
        self.assertEqual(m["name"], "<img src=x onerror=alert(1)>.txt")
        page = self.page()
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;.txt", page)
        self.assertTrue(re.fullmatch(r"d[0-9a-f]{12}", m["id"]))
        self.assertEqual(sorted(p.name for p in (self.app.docs.root / self.sid).iterdir()),
                         sorted(f"{m['id']}{e}" for e in (".bin", ".json", ".txt")))

    def test_csrf_on_upload_and_delete(self):
        body, ctype = helpers.multipart({}, {"file": ("a.txt", b"x")})
        self.assertEqual(self.c.req("POST", f"/s/{self.sid}/docs", body=body, ctype=ctype).status, 403)
        body, ctype = helpers.multipart({"csrf": "wrong"}, {"file": ("a.txt", b"x")})
        self.assertEqual(self.c.req("POST", f"/s/{self.sid}/docs", body=body, ctype=ctype).status, 403)
        upload(self.c, self.sid, "a.txt", b"x")
        did = self.app.docs.list(self.sid)[0]["id"]
        self.assertEqual(self.c.post(f"/s/{self.sid}/docs/{did}/delete", {}).status, 403)
        self.assertEqual(len(self.app.docs.list(self.sid)), 1)

    def test_logged_out_cannot_list_or_upload(self):
        anon = Client(self.app)
        self.assertEqual(anon.get(f"/s/{self.sid}/docs").status, 303)
        body, ctype = helpers.multipart({}, {"file": ("a.txt", b"x")})
        self.assertEqual(anon.req("POST", f"/s/{self.sid}/docs", body=body, ctype=ctype).status, 403)

    def test_deleting_the_study_moves_its_documents_to_the_trash(self):
        upload(self.c, self.sid, "a.txt", b"x")
        self.c.post_csrf(f"/s/{self.sid}/delete")
        self.assertFalse((self.app.docs.root / self.sid).exists())
        moved = [p for p in self.app.store.trash.iterdir() if p.name.endswith(".documents")]
        self.assertEqual(len(moved), 1)


if __name__ == "__main__":
    unittest.main()
