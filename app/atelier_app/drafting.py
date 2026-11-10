"""Drafting adapter: the one place the app asks a language model for a draft.

Interface: Drafter(settings).draft(task, context) -> {"items", "model", "route", "requests", "covered", "total"}

- task: "w1" to "w5" (one per workshop; "w1-values-events" is the iteration 3 name of "w1").
- context: {"text": the source text (selected documents and pasted text), "private": True when the study is private,
  "study": a short plain-text summary of the study so far (ids and labels the model may refer to),
  "study_id": the study's id (rate limit and log)}.
- items: the proposals read from the model's answers (see SCHEMAS); model: the model that answered; route: "off",
  "local" or "remote"; requests: how many requests were sent; covered/total: characters of source text sent / given.

Routes (settings, see normalise):
  off     the default; nothing is sent anywhere.
  local   an OpenAI-compatible endpoint on 127.0.0.1:<port> (for example the local end of an ssh -L forward to a
          model on your own network). The app never runs ssh; the settings may hold the command as a hint to show.
  remote  any OpenAI-compatible URL, with an optional key file. Refused for private studies, before any request.

Trust rule: the model drafts, the engine computes and checks, the human validates. SCHEMAS lists, per workshop, the
only fields a proposal may carry; none of them is a severity, likelihood, level, decision, status, owner, due date or
rating (FORBIDDEN). Everything else in an answer is dropped here, so a draft can never set a level.

Limits (hard, per study): requests per minute and output tokens per request; the source text is cut into chunks
that fit the model's context (estimated at CHARS_PER_TOKEN characters a token) and at most max_chunks requests are
sent per draft. Every request, and every refused attempt, is logged to a local JSONL file without any document text.

The API key, if any, is read at call time from a file named in the settings (mode 0600, never in the repository).
It is sent only in the Authorization header. It is never logged, stored or put in an error message. The transport
ignores proxy settings and refuses redirects, so a local endpoint cannot pass a private request on.
"""
import collections
import datetime
import ipaddress
import json
import os
import pathlib
import re
import socket
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROUTES = ("off", "local", "remote")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
PROMPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "prompts"
CHARS_PER_TOKEN = 4  # estimate; no tokenizer in the standard library
MAX_TEXT = 20000  # pasted text box
MAX_SOURCE = 2_000_000  # all selected documents together
MAX_REPLY = 1024 * 1024
MAX_ITEMS = 50
MAX_STUDY_CONTEXT = 12000  # characters of "study so far" sent with each request
NATURES = ("process", "information")
CRITERIA = ("confidentiality", "integrity", "availability", "traceability")
DEFAULT_LIMITS = {"requests_per_minute": 6, "max_output_tokens": 2048, "context_tokens": 8192, "max_chunks": 4}
CEILINGS = {"requests_per_minute": 60, "max_output_tokens": 8192, "context_tokens": 262144, "max_chunks": 20}
FLOORS = {"requests_per_minute": 1, "max_output_tokens": 64, "context_tokens": 1024, "max_chunks": 1}

# Field types of a proposal: text (required when marked "!"), a choice, a reference (an id or a label of an existing
# element, checked when the user accepts), a list of references, attack paths (label + stakeholder reference).
TEXT, TEXT_REQ, REF, REFS, PATHS = "text", "text!", "ref", "refs", "paths"
SCHEMAS = {
    "w1": {
        "business_values": ("business_value", {"label": TEXT_REQ, "nature": NATURES}),
        "supporting_assets": ("supporting_asset", {"label": TEXT_REQ, "business_values": REFS}),
        "feared_events": ("feared_event", {"label": TEXT_REQ, "business_value": REF, "criterion": CRITERIA}),
    },
    "w2": {"risk_origins": ("risk_origin", {"origin": TEXT_REQ, "objective": TEXT, "feared_events": REFS})},
    "w3": {
        "stakeholders": ("stakeholder", {"name": TEXT_REQ, "category": TEXT}),
        "strategic_scenarios": ("strategic_scenario", {"risk_origin": REF, "feared_events": REFS, "paths": PATHS}),
    },
    "w4": {"operational_scenarios": ("operational_scenario", {"strategic_scenario": REF, "path": REF,
                                                              "description": TEXT_REQ})},
    "w5": {"measures": ("measure", {"label": TEXT_REQ, "risks": REFS})},
}
# Never accepted from a draft, whatever the workshop: people set these (and the engine computes the levels).
FORBIDDEN = frozenset({"severity", "likelihood", "likelihood_target", "level", "level_target", "risk_level",
                       "decision", "status", "owner", "due", "treatment", "motivation", "resources", "dependence",
                       "penetration", "maturity", "trust", "critical", "score", "rating", "id"})
KIND_WS = {kind: ws for ws, sch in SCHEMAS.items() for _, (kind, _) in sch.items()}
KIND_COLLECTION = {kind: coll for sch in SCHEMAS.values() for coll, (kind, _) in sch.items()}
# Kinds whose stored fields are all text the draft may set: only these may be accepted all at once.
TEXT_ONLY_KINDS = ("business_value", "supporting_asset", "stakeholder")
TASK_ALIASES = {"w1-values-events": "w1"}
UNUSABLE = "The model's answer could not be used"


class DraftError(Exception):
    """A draft could not be made. The message is safe to show: it never holds the key, the key file or source text."""


class RouteRefused(DraftError):
    """The route policy refuses this route for this study."""


class EndpointError(DraftError):
    """The endpoint failed, could not be reached or gave an answer that is not a chat completion."""


class RateLimited(DraftError):
    """The study's requests-per-minute limit would be passed."""


class Unusable(DraftError):
    """The model answered, but no proposal could be read from the answer. Nothing is stored."""


# ---------- settings ----------

def _int(v, key):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return DEFAULT_LIMITS[key]
    return max(FLOORS[key], min(n, CEILINGS[key]))


def normalise(settings):
    """Settings dict -> a clean one. Unknown route or missing fields fall back to "off" with a reason.

    Format (settings.json): {"route": "off"|"local"|"remote",
      "local": {"port": 11434, "path": "/v1", "model": "...", "key_file": "", "ssh_hint": "ssh -N -L ..."},
      "remote": {"base_url": "https://...", "model": "...", "key_file": "~/.config/.../key"},
      "limits": {"requests_per_minute", "max_output_tokens", "context_tokens", "max_chunks"}, "timeout": 120}
    The iteration 3 format {"backend": "openai-compatible", "base_url", "model", "key_file"} is read as local when
    its endpoint is on this machine, else as remote. {"backend": "off"} is off.
    """
    s = dict(settings or {})
    if "route" not in s and "backend" in s:
        s = _from_it3(s)
    route = s.get("route") or "off"
    loc = s.get("local") if isinstance(s.get("local"), dict) else {}
    rem = s.get("remote") if isinstance(s.get("remote"), dict) else {}
    lim = s.get("limits") if isinstance(s.get("limits"), dict) else {}
    out = {"route": route, "base_url": "", "model": "", "key_file": "", "problem": s.get("problem"),
           "ssh_hint": str(loc.get("ssh_hint") or "")[:400], "local": dict(loc), "remote": dict(rem),
           "limits": {k: _int(lim.get(k, d), k) for k, d in DEFAULT_LIMITS.items()}}
    try:
        out["timeout"] = max(1, min(int(s.get("timeout") or 120), 600))
    except (TypeError, ValueError):
        out["timeout"] = 120
    if route not in ROUTES:
        out.update(route="off", problem=f"unknown drafting route {route!r}")
    elif route == "local":
        try:
            port = int(loc.get("port"))
        except (TypeError, ValueError):
            port = 0
        path = str(loc.get("path") or "/v1")
        base = loc.get("base_url")  # iteration 3 settings: kept as given, but it must be on this machine
        if not base:
            base = f"http://127.0.0.1:{port}{path if path.startswith('/') else '/' + path}" if 0 < port < 65536 else ""
        if not base:
            out.update(route="off", problem="the local route needs a port between 1 and 65535")
        elif endpoint_host(base) not in LOCAL_HOSTS:
            out.update(route="off", problem="the local route must point to 127.0.0.1")
        elif not loc.get("model"):
            out.update(route="off", problem="the local route names no model")
        else:
            out.update(base_url=base, model=str(loc["model"])[:200], key_file=str(loc.get("key_file") or ""))
    elif route == "remote":
        base = str(rem.get("base_url") or "")
        u = urllib.parse.urlsplit(base)
        if u.scheme not in ("http", "https") or not u.hostname:
            out.update(route="off", problem="the remote route needs an http:// or https:// base URL")
        elif not rem.get("model"):
            out.update(route="off", problem="the remote route names no model")
        else:
            out.update(base_url=base, model=str(rem["model"])[:200], key_file=str(rem.get("key_file") or ""))
    return out


def _from_it3(s):
    if s.get("backend") != "openai-compatible":
        out = {"route": "off"}
        if s.get("backend") not in (None, "off"):
            out["problem"] = f"unknown drafting backend {s.get('backend')!r}"
        if s.get("problem"):
            out["problem"] = s["problem"]
        return out
    base = s.get("base_url") or ""
    u = urllib.parse.urlsplit(base)
    if u.scheme not in ("http", "https") or not u.hostname:
        return {"route": "off", "problem": "the drafting base_url must be an http:// or https:// URL"}
    if not s.get("model"):
        return {"route": "off", "problem": "the drafting settings name no model"}
    entry = {"base_url": base, "model": s.get("model"), "key_file": s.get("key_file") or ""}
    route = "local" if is_local_endpoint(base) else "remote"
    return {"route": route, route: entry, "timeout": s.get("timeout"), "limits": s.get("limits")}


def endpoint_host(base_url):
    return (urllib.parse.urlsplit(base_url).hostname or "").lower()


def endpoint_label(base_url):
    u = urllib.parse.urlsplit(base_url)
    if not u.hostname:
        return ""
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    return f"{host}:{u.port}" if u.port else host


def is_local_endpoint(base_url):
    """True when the endpoint host is 127.0.0.1, localhost or ::1 and every address it resolves to is loopback."""
    host = endpoint_host(base_url)
    if host not in LOCAL_HOSTS:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    try:
        return bool(addrs) and all(ipaddress.ip_address(a.split("%", 1)[0]).is_loopback for a in addrs)
    except ValueError:
        return False


def route_for(settings, private):
    """The route a draft would take: "off", "local" or "remote". Raises RouteRefused for a private study on the
    remote route (or on a "local" endpoint that does not resolve to loopback only). Makes no request."""
    route = settings["route"]
    if route == "off":
        return "off"
    if route == "remote" and private:
        raise RouteRefused(
            "Refused: this study is private, so drafting may only use the local route (an endpoint on 127.0.0.1, "
            "for example an ssh -L forward to a model on your own network). The remote route is set, with an "
            f"endpoint on {endpoint_host(settings['base_url']) or 'an unknown host'}. Nothing was sent.")
    if route == "local" and not is_local_endpoint(settings["base_url"]):
        raise RouteRefused("Refused: the local route's endpoint does not resolve to this machine only. Nothing was sent.")
    return route


def read_key(path):
    """The API key from its file. The file must be a regular file with no access for group or others."""
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        raise DraftError("the API key file named in the drafting settings cannot be read")
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077:
        raise DraftError("the API key file must be a regular file readable by its owner only (chmod 600)")
    try:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
    except (OSError, UnicodeDecodeError):
        raise DraftError("the API key file named in the drafting settings cannot be read")
    if not key or any(c in key for c in "\r\n"):
        raise DraftError("the API key file must hold one key on one line")
    return key


# ---------- prompts ----------

def task_name(task):
    t = TASK_ALIASES.get(task, task)
    if t not in SCHEMAS:
        raise DraftError(f"unknown drafting task {task!r}")
    return t


def prompt_path(task):
    return PROMPTS_DIR / f"{task_name(task)}.md"


def load_prompt(task):
    """The workshop's prompt file (app/prompts/wN.md), sent as the system message."""
    try:
        return prompt_path(task).read_text(encoding="utf-8")
    except OSError:
        raise DraftError(f"the prompt file for {task_name(task)} is missing")


def prompt_example(task):
    """The JSON example of the expected answer in the prompt file (its ```json block), as text."""
    m = re.search(r"```json\s*\n(.*?)\n```", load_prompt(task), re.S)
    return m.group(1) if m else ""


# ---------- answers ----------

def _clean(v, limit=500):
    if not isinstance(v, str):
        return None
    v = " ".join(v.split())
    return v[:limit] if v else None


def _candidates(content):
    """JSON texts to try, best first: fenced blocks, then every {...} the decoder can read from a "{" onward."""
    text = re.sub(r"<think>.*?(</think>|$)", " ", content or "", flags=re.S | re.I)
    for m in re.finditer(r"```(?:json|JSON)?\s*\n?(.*?)```", text, re.S):
        yield m.group(1).strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        yield obj


def extract_json(content, task):
    """The answer's JSON object holding at least one of the workshop's lists. Raises Unusable with the reason."""
    keys = set(SCHEMAS[task_name(task)])
    seen_json = False
    for c in _candidates(content):
        if isinstance(c, str):
            try:
                c = json.loads(c)
            except ValueError:
                continue
        seen_json = True
        if isinstance(c, dict) and keys & set(c):
            return c
    if not (content or "").strip():
        raise Unusable(f"{UNUSABLE}: it was empty.")
    if seen_json:
        raise Unusable(f"{UNUSABLE}: its JSON holds none of the expected lists ({', '.join(sorted(keys))}).")
    raise Unusable(f"{UNUSABLE}: no JSON object could be read from it.")


def _field(ftype, v):
    if ftype in (TEXT, TEXT_REQ):
        return _clean(v, 4000 if ftype == TEXT_REQ else 1000)
    if ftype == REF:
        return _clean(v, 300)
    if ftype == REFS:
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return None
        out = [c for c in (_clean(x, 300) for x in v[:20]) if c]
        return list(dict.fromkeys(out)) or None
    if ftype == PATHS:
        if not isinstance(v, list):
            return None
        out = []
        for p in v[:10]:
            if isinstance(p, str):
                p = {"label": p}
            if isinstance(p, dict) and _clean(p.get("label"), 1000):
                q = {"label": _clean(p["label"], 1000)}
                if _clean(p.get("stakeholder"), 300):
                    q["stakeholder"] = _clean(p["stakeholder"], 300)
                out.append(q)
        return out or None
    if isinstance(ftype, tuple):  # a choice
        c = v.strip().lower() if isinstance(v, str) else None
        return c if c in ftype else None
    raise KeyError(ftype)


def parse_items(content, task="w1"):
    """Proposals from a model answer (text, or an already decoded dict). Only the workshop's schema fields are kept;
    never a level, a severity or any FORBIDDEN field. Raises Unusable when nothing can be used."""
    t = task_name(task)
    data = content if isinstance(content, dict) else extract_json(content, t)
    items = []
    for coll, (kind, fields) in SCHEMAS[t].items():
        rows = data.get(coll)
        if not isinstance(rows, list):
            continue
        for x in rows[:MAX_ITEMS]:
            if not isinstance(x, dict):
                continue
            it = {"kind": kind}
            for name, ftype in fields.items():
                if name in FORBIDDEN:  # cannot happen (a test checks the schemas), kept as a second guard
                    continue
                v = _field(ftype, x.get(name))
                if v is not None:
                    it[name] = v
            required = [n for n, ft in fields.items() if ft == TEXT_REQ] or ([n for n, ft in fields.items()
                                                                             if ft == PATHS])
            if all(it.get(n) for n in required):
                items.append(it)
    if not items:
        raise Unusable(f"{UNUSABLE}: its JSON holds no proposal with the required fields.")
    return items


def merge(items):
    """Drop duplicates (same kind and same main text) from several chunks' answers, keeping the first."""
    out, seen = [], set()
    for it in items:
        main = next((it.get(k) for k in ("label", "origin", "name", "description") if it.get(k)), None)
        if main is None and it.get("paths"):
            main = " / ".join(p["label"] for p in it["paths"])
        key = (it["kind"], (main or "").lower())
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


# ---------- chunks ----------

def chunk_budget(limits, fixed_chars):
    """Characters of source text one request may carry: the context minus the output tokens, the prompt and the
    study summary, in estimated tokens, and a small margin."""
    tokens = limits["context_tokens"] - limits["max_output_tokens"] - fixed_chars // CHARS_PER_TOKEN - 256
    return max(500, tokens * CHARS_PER_TOKEN)


def chunks(text, size):
    """Cut text into pieces of at most `size` characters, on paragraph, then line, then word boundaries."""
    text = text.strip()
    out = []
    while text:
        if len(text) <= size:
            out.append(text)
            break
        cut = -1
        for sep in ("\n\n", "\n", " "):
            cut = text.rfind(sep, size // 2, size)
            if cut > 0:
                break
        if cut <= 0:
            cut = size
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    return [c for c in out if c]


# ---------- rate limit and log ----------

class RateLimiter:
    """Requests per minute, per study, in memory (the limit is per running server)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sent = collections.defaultdict(collections.deque)

    def reserve(self, study_id, n, per_minute, now=None):
        """Reserve n requests for the study or raise RateLimited (nothing reserved)."""
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.sent[study_id]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) + n > per_minute:
                wait = int(60 - (now - q[0])) + 1 if q else 60
                raise RateLimited(f"Refused: this study may send at most {per_minute} drafting requests a minute "
                                  f"and this draft needs {n}; wait about {wait} s, or select less text. Nothing was "
                                  "sent.")
            q.extend([now] * n)


class DraftLog:
    """One JSON line per drafting request or refused attempt. Never document text, never the answer, never the key."""

    FIELDS = ("time", "study", "workshop", "route", "model", "endpoint", "outcome", "request", "of", "source_chars",
              "documents", "max_output_tokens", "prompt_tokens", "completion_tokens", "tokens_from", "items",
              "latency_ms")

    def __init__(self, path):
        self.path = pathlib.Path(path) if path else None
        self.lock = threading.Lock()

    def write(self, **rec):
        if self.path is None:
            return
        rec["time"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        line = json.dumps({k: rec[k] for k in self.FIELDS if k in rec}, ensure_ascii=False) + "\n"
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)


# ---------- transport ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None  # urllib then raises HTTPError with the 3xx status


def _post(url, body, headers, timeout):
    """POST JSON, no proxy, no redirect. Returns (status, bytes)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with opener.open(req, timeout=timeout) as r:
            data = r.read(MAX_REPLY + 1)
            return r.status, data
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, b""
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", None) or type(e).__name__
        raise EndpointError(f"the drafting endpoint could not be reached ({reason})")


def complete(settings, system, user):
    """One chat completion. Returns (content, model, usage dict or None)."""
    key = read_key(settings["key_file"])
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = json.dumps({"model": settings["model"], "temperature": 0, "stream": False,
                       "max_tokens": settings["limits"]["max_output_tokens"],
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode("utf-8")
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    status, data = _post(url, body, headers, settings["timeout"])
    if status != 200:
        raise EndpointError(f"the drafting endpoint answered HTTP {status}")
    if len(data) > MAX_REPLY:
        raise EndpointError("the drafting endpoint's answer is too large")
    try:
        reply = json.loads(data.decode("utf-8"))
        content = reply["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError, UnicodeDecodeError):
        raise EndpointError("the drafting endpoint's answer is not an OpenAI-compatible chat completion")
    if not isinstance(content, str):
        raise EndpointError("the drafting endpoint's answer holds no text")
    model = reply.get("model") if isinstance(reply.get("model"), str) else settings["model"]
    usage = reply.get("usage") if isinstance(reply.get("usage"), dict) else None
    return content, model[:200], usage


def _tok(usage, name):
    v = (usage or {}).get(name)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


# ---------- the adapter ----------

class Drafter:
    def __init__(self, settings=None, log_path=None, limiter=None):
        self.settings = normalise(settings)
        self.log = DraftLog(log_path)
        self.limiter = limiter or RateLimiter()

    def describe(self, private):
        """What a drafting panel says: route, model, endpoint, limits, the ssh hint, or why it is refused/off."""
        s = self.settings
        d = {"route": s["route"], "model": s["model"] or None, "host": endpoint_host(s["base_url"]) or None,
             "endpoint": endpoint_label(s["base_url"]) or None, "problem": s.get("problem"), "refused": None,
             "limits": dict(s["limits"]), "ssh_hint": s["ssh_hint"] if s["route"] == "local" else "",
             "backend": "off" if s["route"] == "off" else "openai-compatible", "allowed": None}
        try:
            d["allowed"] = route_for(s, private)
        except RouteRefused as e:
            d["refused"] = str(e)
        d["budget"] = chunk_budget(s["limits"], 4000)  # shown as an order of size; a real draft computes its own
        return d

    def draft(self, task, context):
        t = task_name(task)
        text = context.get("text") if isinstance(context.get("text"), str) else ""
        text = text.strip()
        sid = str(context.get("study_id") or "-")
        base = {"study": sid, "workshop": t, "route": self.settings["route"], "model": self.settings["model"] or None,
                "endpoint": endpoint_label(self.settings["base_url"]) or None,
                "documents": int(context.get("documents") or 0), "source_chars": len(text)}
        if not text:
            raise DraftError("select a document or paste some text to draft from")
        if len(text) > MAX_SOURCE:
            raise DraftError(f"the selected text is over {MAX_SOURCE} characters; select fewer documents")
        if self.settings["route"] == "off":
            why = f" ({self.settings['problem']})" if self.settings.get("problem") else ""
            raise DraftError("drafting is off" + why + "; set a route in Settings (docs/app.md says how)")
        try:
            route = route_for(self.settings, bool(context.get("private", True)))  # unknown privacy: private
        except RouteRefused:
            self.log.write(outcome="refused-route", **base)
            raise
        system = load_prompt(t)
        study = (context.get("study") or "")[:MAX_STUDY_CONTEXT]
        lim = self.settings["limits"]
        size = chunk_budget(lim, len(system) + len(study))
        parts = chunks(text, size)
        sent = parts[:lim["max_chunks"]]
        try:
            self.limiter.reserve(sid, len(sent), lim["requests_per_minute"])
        except RateLimited:
            self.log.write(outcome="rate-limited", of=len(sent), **base)
            raise
        items, model, errors = [], self.settings["model"], []
        for i, part in enumerate(sent, 1):
            user = (f"Study so far (ids you may refer to):\n{study or '(nothing yet)'}\n\n"
                    f"Source text, part {i} of {len(sent)}:\n{part}")
            rec = dict(base, request=i, of=len(sent), max_output_tokens=lim["max_output_tokens"])
            t0 = time.monotonic()
            try:
                content, model, usage = complete(self.settings, system, user)
            except DraftError as e:
                self.log.write(outcome="endpoint-error", latency_ms=int((time.monotonic() - t0) * 1000), **rec)
                raise e
            rec.update(latency_ms=int((time.monotonic() - t0) * 1000), model=model)
            pt, ct = _tok(usage, "prompt_tokens"), _tok(usage, "completion_tokens")
            if pt is None or ct is None:
                rec.update(prompt_tokens=(len(system) + len(user)) // CHARS_PER_TOKEN,
                           completion_tokens=len(content) // CHARS_PER_TOKEN, tokens_from="estimate")
            else:
                rec.update(prompt_tokens=pt, completion_tokens=ct, tokens_from="endpoint")
            try:
                got = parse_items(content, t)
            except Unusable as e:
                errors.append(str(e))
                self.log.write(outcome="unusable", items=0, **rec)
                continue
            items.extend(got)
            self.log.write(outcome="ok", items=len(got), **rec)
        if not items:
            raise Unusable(errors[0] if len(errors) == 1 else
                           f"{UNUSABLE}: none of the {len(sent)} answers held a usable proposal. Nothing was stored.")
        covered = sum(len(p) for p in sent)
        return {"items": merge(items), "model": model, "route": route, "requests": len(sent),
                "covered": covered, "total": sum(len(p) for p in parts), "unusable": len(errors)}
