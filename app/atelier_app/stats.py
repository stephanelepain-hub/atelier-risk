"""Public mode: anonymous counts.

One JSON line per event is appended to `<data>/stats/<YYYY-MM>.jsonl` (file 0600, folder 0700):

    {"day": "2026-11-11", "event": "study_started", "tools": ["office"], "sensitivity": "internal", "downtime": "day"}

A line holds the UTC day, the event name and fields from a fixed list of values (catalogue ids and short answer
words, see SCHEMA). It never holds a workspace id or hash, a study id, an IP address, a browser name, a time finer
than the day, a typed text or an email: `clean` builds each line from the schema and drops everything else, so a
caller cannot add such a field by mistake.

Read the counts with:  python3 -m atelier_app.stats <data_dir> [--month YYYY-MM]
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import sys
import threading

ID_RE = re.compile(r"[A-Za-z0-9_]{1,40}")
MONTH_RE = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
STEPS = ("about", "risks", "now", "results")
SENSITIVITY = ("internal", "confidential", "critical", "dont_know", "unanswered")
DOWNTIME = ("hours", "day", "days", "week", "dont_know", "unanswered")
MEASURE_ANSWERS = ("in", "extra", "none")
DOWNLOADS = ("xlsx", "study", "maps")
SOURCES = ("linkedin", "x", "github", "cplt", "search", "other", "direct")
SOURCE_HOSTS = (("linkedin", ("linkedin.com", "lnkd.in")), ("x", ("t.co", "x.com", "twitter.com")),
                ("github", ("github.com",)), ("cplt", ("cplt.tech", "cplt.online")),
                ("search", ("google.", "bing.com", "duckduckgo.com", "qwant.com", "ecosia.org", "yahoo.")))
BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|curl|wget|python|httpx|go-http|headless|"
                    r"monitor|uptime|scan", re.I)


def source_of(referer, own_host=""):
    """The kind of site a visitor came from, as one word of SOURCES. Only the word is kept, never the address."""
    try:
        import urllib.parse
        host = (urllib.parse.urlsplit(referer or "").hostname or "").lower()
    except ValueError:
        return "other"
    if not host or (own_host and host == own_host.lower()):
        return "direct"
    for word, hosts in SOURCE_HOSTS:
        if any(host == h or host.endswith("." + h) or (h.endswith(".") and h in host) for h in hosts):
            return word
    return "other"


def is_bot(user_agent):
    """True for link previews, crawlers and scripts: they are not counted. The browser name is never kept."""
    return not user_agent or bool(BOT_RE.search(user_agent))
EVENTS = ("visit", "joined", "study_started", "step_reached", "risk_discarded", "risk_added", "measures", "download", "shared", "forget")
FIELDS = {   # event: the only fields its line may carry besides day and event
    "visit": ("source",),
    "joined": ("source",),
    "study_started": ("tools", "sensitivity", "downtime"),
    "step_reached": ("step",),
    "risk_discarded": ("risk",),
    "risk_added": (),
    "measures": ("measures",),
    "download": ("kind",),
    "shared": (),
    "forget": (),
}
ALLOWED_KEYS = {"day", "event"} | {k for f in FIELDS.values() for k in f}


def _id(x):
    return x if isinstance(x, str) and ID_RE.fullmatch(x) else None


def clean(event, fields, today=None):
    """The line for `event` (a dict), built only from the allowed fields with allowed values; None when the event or a
    required value is not recognised."""
    if event not in EVENTS:
        return None
    line = {"day": today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), "event": event}
    f = fields or {}
    if event in ("visit", "joined"):
        line["source"] = f.get("source") if f.get("source") in SOURCES else "other"
    elif event == "study_started":
        tools = sorted({t for t in (f.get("tools") or []) if _id(t)})
        sens = f.get("sensitivity") if f.get("sensitivity") in SENSITIVITY else "unanswered"
        down = f.get("downtime") if f.get("downtime") in DOWNTIME else "unanswered"
        line.update(tools=tools, sensitivity=sens, downtime=down)
    elif event == "step_reached":
        if f.get("step") not in STEPS:
            return None
        line["step"] = f["step"]
    elif event == "risk_discarded":
        if not _id(f.get("risk")):
            return None
        line["risk"] = f["risk"]
    elif event == "measures":
        m = f.get("measures")
        if not isinstance(m, dict):
            return None
        line["measures"] = {k: (v if v in MEASURE_ANSWERS else "none") for k, v in sorted(m.items()) if _id(k)}
    elif event == "download":
        if f.get("kind") not in DOWNLOADS:
            return None
        line["kind"] = f["kind"]
    return line


class Stats:
    def __init__(self, data_dir):
        self.root = pathlib.Path(data_dir) / "stats"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.lock = threading.Lock()

    def record(self, event, **fields):
        """Append one line. Never raises: counting must not break a page."""
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            line = clean(event, fields, now.strftime("%Y-%m-%d"))
            if line is None:
                return False
            path = self.root / f"{now.strftime('%Y-%m')}.jsonl"
            data = (json.dumps(line, ensure_ascii=True, separators=(", ", ": ")) + "\n").encode("ascii")
            with self.lock:
                fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                    os.write(fd, data)
                finally:
                    os.close(fd)
            return True
        except Exception as e:  # a full disk or a bad folder must not stop the visitor
            print(f"Stats: could not record {event}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return False


# ---------------------------------------------------------------- reading the counts

def read(data_dir, month=None):
    """(lines, skipped, files): the valid lines of the month (every month when None), the number of lines that were
    skipped because they are not a JSON object, and the number of files read. An unreadable file raises OSError."""
    root = pathlib.Path(data_dir) / "stats"
    files = sorted(root.glob("????-??.jsonl")) if root.is_dir() else []
    if month:
        files = [f for f in files if f.name == f"{month}.jsonl"]
    lines, skipped = [], 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    d = json.loads(raw)
                except ValueError:
                    skipped += 1
                    continue
                if isinstance(d, dict) and d.get("event") in EVENTS:
                    lines.append(d)
                else:
                    skipped += 1
    return lines, skipped, len(files)


def summary(lines, top=10):
    """The numbers behind the printed summary."""
    ev = collections.Counter(d["event"] for d in lines)
    steps = collections.Counter(d.get("step") for d in lines if d["event"] == "step_reached")
    discarded = collections.Counter(d.get("risk") for d in lines if d["event"] == "risk_discarded")
    planned, placed = collections.Counter(), collections.Counter()
    for d in lines:
        if d["event"] == "measures" and isinstance(d.get("measures"), dict):
            for m, a in d["measures"].items():
                if a == "extra":
                    planned[m] += 1
                elif a == "in":
                    placed[m] += 1
    chosen = collections.Counter()
    chosen.update(planned)
    chosen.update(placed)
    by_src = lambda e: {k: sum(1 for d in lines if d["event"] == e and d.get("source") == k) for k in SOURCES}  # noqa: E731
    days = sorted({d.get("day") for d in lines if d.get("day")})
    return {"visits": ev["visit"], "visits_by_source": by_src("visit"), "joined": ev["joined"],
            "joined_by_source": by_src("joined"), "first_day": days[0] if days else "", "last_day": days[-1] if days else "",
            "started": ev["study_started"],
            "reached": {s: steps[s] for s in STEPS},
            "discarded": discarded.most_common(top),
            "measures": [(m, n, planned[m], placed[m]) for m, n in chosen.most_common(top)],
            "downloads": {k: sum(1 for d in lines if d["event"] == "download" and d.get("kind") == k) for k in DOWNLOADS},
            "shared": ev["shared"], "forget": ev["forget"], "added": ev["risk_added"]}


def render(s, label, skipped=0, files=0):
    src = lambda d: ", ".join(f"{k} {v}" for k, v in d.items() if v) or "none"  # noqa: E731
    out = [f"Atelier anonymous counts: {label} ({files} file{'' if files == 1 else 's'} read)",
           f"Visits to the start page: {s['visits']} (from: {src(s['visits_by_source'])})",
           f"Invite code entered: {s['joined']} (from: {src(s['joined_by_source'])})",
           f"Studies started: {s['started']}",
           "Reached: " + ", ".join(f"{k} {v}" for k, v in s["reached"].items()),
           "Top discarded risks: " + (", ".join(f"{r} ({n})" for r, n in s["discarded"]) or "none yet"),
           "Most chosen measures: " + (", ".join(f"{m} ({n}: {p} planned, {i} in place)" for m, n, p, i in s["measures"]) or "none yet"),
           "Risks added by people: " + str(s["added"]),
           "Downloads: " + ", ".join(f"{k} {v}" for k, v in s["downloads"].items()),
           f"Studies shared: {s['shared']}", f"Data deleted by visitors: {s['forget']}"]
    if skipped:
        out.append(f"Lines skipped (not valid): {skipped}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m atelier_app.stats", description="Print the anonymous counts of a public Atelier instance.")
    ap.add_argument("data_dir")
    ap.add_argument("--month", help="YYYY-MM (default: every month)")
    ap.add_argument("--since", help="YYYY-MM-DD: only days from this one on (e.g. the last 7 days)")
    a = ap.parse_args(argv)
    if a.since and not DAY_RE.fullmatch(a.since):
        print("--since must look like 2026-11-13", file=sys.stderr)
        return 2
    if a.month and not MONTH_RE.fullmatch(a.month):
        print("--month must look like 2026-11", file=sys.stderr)
        return 2
    d = pathlib.Path(a.data_dir)
    if not d.is_dir():
        print(f"{d} is not a folder", file=sys.stderr)
        return 2
    try:
        lines, skipped, files = read(d, a.month)
    except OSError as e:
        print(f"cannot read the counts: {e}", file=sys.stderr)
        return 1
    if a.since:
        lines = [d for d in lines if str(d.get("day", "")) >= a.since]
    label = (a.month or "all months") + (f", from {a.since}" if a.since else "")
    print(render(summary(lines), label, skipped, files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
