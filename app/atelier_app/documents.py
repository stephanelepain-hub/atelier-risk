"""Source documents of a study, for drafting: upload, local text extraction, list, delete.

Storage: <data dir>/documents/<study id>/ (0700), per document <doc id>.bin (the file as uploaded), <doc id>.txt
(the extracted text) and <doc id>.json (name, type, size, date, characters). Files are 0600 and written atomically.
Document ids are generated here (d + 12 hex digits); the uploaded file name is only shown, never used in a path.

Extraction happens on this machine only:
- .txt and .md: UTF-8 (with or without BOM), UTF-16 with a BOM, else Windows-1252; a file with NUL bytes is refused.
- .docx: the standard library's zipfile and XML parser read word/document.xml (paragraphs, tabs, line breaks and
  table rows). A document type declaration is refused, and so are oversized or over-compressed archives.
- .pdf: `pdftotext` (poppler) when it is on PATH, run without a shell and with a time limit. Without it, PDFs are
  refused with a message saying so. Nothing is installed by the app.
Documents never leave this machine through this module. Drafting sends their text only through the route policy
of drafting.py (a private study: only to an endpoint on 127.0.0.1).
"""
import datetime
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import zipfile
import xml.etree.ElementTree as ET

from .storage import ID_RE, NotFound, atomic_write

MAX_DOC = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_DOCX_XML = 64 * 1024 * 1024
MAX_DOCX_RATIO = 200
PDF_TIMEOUT = 120
TYPES = {".txt": "text", ".md": "markdown", ".docx": "docx", ".pdf": "pdf"}
DOC_ID_RE = re.compile(r"d[0-9a-f]{12}")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(Exception):
    """A document cannot be accepted. The message is safe to show."""


def pdftotext_path():
    return shutil.which("pdftotext")


def file_type(name):
    ext = pathlib.PurePath(name or "").suffix.lower()
    return TYPES.get(ext)


def display_name(name):
    """The uploaded file name, without any directory part and control characters, at most 200 characters."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(c for c in base if c.isprintable()).strip()
    return base[:200] or "document"


# ---------- extraction ----------

def extract_text(kind, data):
    if kind in ("text", "markdown"):
        return _plain(data)
    if kind == "docx":
        return _docx(data)
    if kind == "pdf":
        return _pdf(data)
    raise DocumentError("only .txt, .md, .docx and .pdf files are accepted")


def _plain(data):
    if b"\0" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise DocumentError("the file holds binary data, not text")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            raise DocumentError("the file starts like UTF-16 text but cannot be read as such")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        raise DocumentError("the text is neither UTF-8 nor Windows-1252")


def _docx(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocumentError("this .docx file is not a valid Word document (not a zip archive)")
    with z:
        try:
            info = z.getinfo("word/document.xml")
        except KeyError:
            raise DocumentError("this .docx file has no word/document.xml")
        if info.file_size > MAX_DOCX_XML or (info.compress_size and info.file_size / info.compress_size > MAX_DOCX_RATIO):
            raise DocumentError("this .docx file expands to too much data")
        try:
            xml = z.read(info)
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as e:
            raise DocumentError(f"this .docx file cannot be read ({type(e).__name__})")
    if b"<!DOCTYPE" in xml[:4096].upper() or b"<!ENTITY" in xml.upper():
        raise DocumentError("this .docx file declares a document type, which a Word document never does; refused")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise DocumentError("the text of this .docx file is not well-formed XML")
    body = root.find(f"{W}body")
    if body is None:
        return ""
    lines = []
    for el in body:
        if el.tag == f"{W}p":
            lines.append(_para(el))
        elif el.tag == f"{W}tbl":
            for tr in el.iter(f"{W}tr"):
                cells = [" ".join(_para(p) for p in tc.iter(f"{W}p")).strip() for tc in tr.findall(f"{W}tc")]
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _para(p):
    out = []
    for el in p.iter():
        if el.tag == f"{W}t" and el.text:
            out.append(el.text)
        elif el.tag == f"{W}tab":
            out.append("\t")
        elif el.tag in (f"{W}br", f"{W}cr"):
            out.append("\n")
    return "".join(out)


def _pdf(data):
    exe = pdftotext_path()
    if not exe:
        raise DocumentError("PDF files need the pdftotext program (poppler), which is not on this machine's PATH; "
                            "nothing is installed by the app. Upload a .docx or .txt version instead.")
    if not data.startswith(b"%PDF-"):
        raise DocumentError("this .pdf file does not start like a PDF")
    with tempfile.TemporaryDirectory(prefix="atelier-pdf-") as d:
        os.chmod(d, 0o700)
        src = pathlib.Path(d) / "in.pdf"
        fd = os.open(src, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([exe, "-q", "-enc", "UTF-8", "-eol", "unix", str(src), "-"], capture_output=True,
                               timeout=PDF_TIMEOUT, stdin=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        except subprocess.TimeoutExpired:
            raise DocumentError(f"pdftotext took more than {PDF_TIMEOUT} s on this PDF; refused")
        except OSError:
            raise DocumentError("pdftotext could not be started")
    if r.returncode != 0:
        raise DocumentError(f"pdftotext could not read this PDF (exit code {r.returncode}; encrypted or damaged?)")
    text = r.stdout.decode("utf-8", "replace").replace("\f", "\n")
    if not text.strip():
        raise DocumentError("this PDF holds no text layer (a scanned image?); no text could be extracted")
    return text


def tidy(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------- storage ----------

class DocStore:
    def __init__(self, root):
        self.root = pathlib.Path(root) / "documents"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.lock = threading.Lock()

    def _dir(self, sid, create=False):
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            raise NotFound(sid)
        d = self.root / sid
        if create:
            d.mkdir(exist_ok=True, mode=0o700)
            os.chmod(d, 0o700)
        return d

    def _doc(self, sid, did):
        if not isinstance(did, str) or not DOC_ID_RE.fullmatch(did):
            raise NotFound(did)
        return self._dir(sid) / did

    def add(self, sid, filename, data):
        """Check, extract and store one upload. Returns its metadata. Raises DocumentError (nothing stored)."""
        kind = file_type(filename)
        if kind is None:
            raise DocumentError("only .txt, .md, .docx and .pdf files are accepted")
        if not data:
            raise DocumentError("the file is empty")
        if len(data) > MAX_DOC:
            raise DocumentError(f"the file is over {MAX_DOC // (1024 * 1024)} MB")
        text = tidy(extract_text(kind, data))
        cut = len(text) > MAX_TEXT_CHARS
        text = text[:MAX_TEXT_CHARS]
        meta = {"id": "d" + secrets.token_hex(6), "name": display_name(filename), "type": kind, "size": len(data),
                "chars": len(text), "truncated": cut,
                "uploaded": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        with self.lock:
            d = self._dir(sid, create=True)
            while (d / f"{meta['id']}.json").exists():
                meta["id"] = "d" + secrets.token_hex(6)
            base = d / meta["id"]
            atomic_write(base.with_suffix(".bin"), data)
            atomic_write(base.with_suffix(".txt"), text.encode("utf-8"))
            atomic_write(base.with_suffix(".json"), (json.dumps(meta, ensure_ascii=False) + "\n").encode("utf-8"))
        return meta

    def list(self, sid):
        d = self._dir(sid)
        out = []
        if not d.is_dir():
            return out
        for p in sorted(d.glob("d*.json")):
            if not DOC_ID_RE.fullmatch(p.stem):
                continue
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(m, dict) and m.get("id") == p.stem:
                out.append(m)
        out.sort(key=lambda m: m.get("uploaded") or "")
        return out

    def text(self, sid, did):
        p = self._doc(sid, did).with_suffix(".txt")
        try:
            return p.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise NotFound(did)

    def delete(self, sid, did):
        base = self._doc(sid, did)
        with self.lock:
            if not base.with_suffix(".json").exists():
                raise NotFound(did)
            for ext in (".json", ".txt", ".bin"):
                try:
                    base.with_suffix(ext).unlink()
                except FileNotFoundError:
                    pass

    def move_to(self, sid, dest):
        """When a study is deleted: move its documents folder next to the study in the trash (nothing unlinked)."""
        d = self._dir(sid)
        if d.is_dir():
            with self.lock:
                shutil.move(str(d), str(dest))
