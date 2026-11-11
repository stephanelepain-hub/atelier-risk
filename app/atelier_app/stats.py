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
EVENTS = ("study_started", "step_reached", "risk_discarded", "risk_added", "measures", "download", "shared", "forget")
FIELDS = {   # event: the only fields its line may carry besides day and event
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
    if event == "study_started":
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
    return {"started": ev["study_started"],
            "reached": {s: steps[s] for s in STEPS},
            "discarded": discarded.most_common(top),
            "measures": [(m, n, planned[m], placed[m]) for m, n in chosen.most_common(top)],
            "downloads": {k: sum(1 for d in lines if d["event"] == "download" and d.get("kind") == k) for k in DOWNLOADS},
            "shared": ev["shared"], "forget": ev["forget"], "added": ev["risk_added"]}


def render(s, label, skipped=0, files=0):
    out = [f"Atelier anonymous counts: {label} ({files} file{'' if files == 1 else 's'} read)", f"Studies started: {s['started']}",
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
    a = ap.parse_args(argv)
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
    print(render(summary(lines), a.month or "all months", skipped, files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
