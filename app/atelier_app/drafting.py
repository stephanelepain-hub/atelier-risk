"""Drafting adapter: the one place the app asks a language model for a draft.

Interface: Drafter(settings).draft(task, context) -> {"text", "items", "model", "route"}

- task: a name from TASKS (one task today: business values and feared events from pasted text, workshop 1).
- context: {"text": the pasted text, "private": True when the study is private}.
- text: the model's raw answer; items: the proposals the app could read from it; model: the model that answered;
  route: "off", "local" (an endpoint on this machine) or "remote".

Backends: "off" (the default: no call is made) and "openai-compatible" (POST <base_url>/chat/completions).

Trust rule: the model drafts, the engine computes and checks, the human validates. Items carry only labels and
descriptive choices (nature, criterion, the business value a feared event is about). Any severity, likelihood,
level or id in the answer is dropped here, so a draft can never set a level.

Route policy (enforced in Drafter.draft, before any network access): a private study may only use an endpoint whose
host is 127.0.0.1, localhost or ::1 and resolves to loopback addresses only (for example an ssh -L forward to a
model on your own network). Public studies may use any configured endpoint. The transport ignores proxy settings
and refuses redirects, so a local endpoint cannot pass a private request on.

The API key, if any, is read at call time from a file named in the settings (mode 0600, never in the repository).
It is sent only in the Authorization header. It is never logged, stored or put in an error message.
"""
import ipaddress
import json
import os
import re
import socket
import stat
import urllib.error
import urllib.parse
import urllib.request

BACKENDS = ("off", "openai-compatible")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_TEXT = 20000
MAX_REPLY = 1024 * 1024
MAX_ITEMS = 50
NATURES = ("process", "information")
CRITERIA = ("confidentiality", "integrity", "availability")

TASKS = {
    "w1-values-events": (
        "You help prepare workshop 1 of an EBIOS Risk Manager study. From the text you are given, propose the "
        "business values (the processes and information the organisation needs) and the feared events on them. "
        "Answer with one JSON object and nothing else, in this form: "
        '{"business_values": [{"label": "...", "nature": "process or information"}], '
        '"feared_events": [{"business_value": "label of one of the business values", "label": "...", '
        '"criterion": "confidentiality, integrity or availability"}]}. '
        "Do not give any severity, likelihood or level: people set them."
    ),
}


class DraftError(Exception):
    """A draft could not be made. The message is safe to show: it never holds the key or the key file."""


class RouteRefused(DraftError):
    """The route policy refuses this endpoint for this study."""


class EndpointError(DraftError):
    """The endpoint failed, could not be reached or gave an answer the adapter cannot read."""


def normalise(settings):
    """Settings dict -> a clean one. Unknown backend or missing fields fall back to "off" with a reason."""
    s = dict(settings or {})
    backend = s.get("backend") or "off"
    out = {"backend": backend, "base_url": s.get("base_url") or "", "model": s.get("model") or "",
           "key_file": s.get("key_file") or "", "timeout": s.get("timeout") or 60, "problem": s.get("problem")}
    if backend not in BACKENDS:
        out.update(backend="off", problem=f"unknown drafting backend {backend!r}")
    elif backend == "openai-compatible":
        u = urllib.parse.urlsplit(out["base_url"])
        if u.scheme not in ("http", "https") or not u.hostname:
            out.update(backend="off", problem="the drafting base_url must be an http:// or https:// URL")
        elif not out["model"]:
            out.update(backend="off", problem="the drafting settings name no model")
    try:
        out["timeout"] = max(1, min(int(out["timeout"]), 600))
    except (TypeError, ValueError):
        out["timeout"] = 60
    return out


def endpoint_host(base_url):
    return (urllib.parse.urlsplit(base_url).hostname or "").lower()


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
    """The route a draft would take: "off", "local" or "remote". Raises RouteRefused for a private study on a
    non-local endpoint. Makes no request (only a name lookup for localhost)."""
    if settings["backend"] == "off":
        return "off"
    local = is_local_endpoint(settings["base_url"])
    if private and not local:
        raise RouteRefused(
            "Refused: this study is private, so drafting may only use an endpoint on this machine (host 127.0.0.1 "
            "or localhost, for example an ssh -L forward to a model on your own network). The configured endpoint "
            f"is on {endpoint_host(settings['base_url']) or 'an unknown host'}. Nothing was sent.")
    return "local" if local else "remote"


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


def _clean(v, limit=500):
    if not isinstance(v, str):
        return None
    v = " ".join(v.split())
    return v[:limit] if v else None


def parse_items(content):
    """Proposals from the model's answer. Only labels and descriptive choices are kept; never a level."""
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    items = []
    for x in (data.get("business_values") or [])[:MAX_ITEMS] if isinstance(data.get("business_values"), list) else []:
        if isinstance(x, dict) and _clean(x.get("label")):
            it = {"kind": "business_value", "label": _clean(x.get("label"))}
            if x.get("nature") in NATURES:
                it["nature"] = x["nature"]
            items.append(it)
    for x in (data.get("feared_events") or [])[:MAX_ITEMS] if isinstance(data.get("feared_events"), list) else []:
        if isinstance(x, dict) and _clean(x.get("label")):
            it = {"kind": "feared_event", "label": _clean(x.get("label"))}
            if _clean(x.get("business_value")):
                it["business_value_label"] = _clean(x.get("business_value"))
            crit = x.get("criterion").strip().lower() if isinstance(x.get("criterion"), str) else None
            if crit in CRITERIA:
                it["criterion"] = crit
            items.append(it)
    return items


class OffBackend:
    def draft(self, task, context):
        return {"text": "", "items": [], "model": None}


class OpenAICompatibleBackend:
    def __init__(self, settings):
        self.s = settings

    def draft(self, task, context):
        key = read_key(self.s["key_file"])
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        body = json.dumps({"model": self.s["model"], "temperature": 0, "messages": [
            {"role": "system", "content": TASKS[task]},
            {"role": "user", "content": context["text"]}]}).encode("utf-8")
        url = self.s["base_url"].rstrip("/") + "/chat/completions"
        status, data = _post(url, body, headers, self.s["timeout"])
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
        model = reply.get("model") if isinstance(reply.get("model"), str) else self.s["model"]
        return {"text": content[:MAX_TEXT], "items": parse_items(content), "model": model[:200]}


class Drafter:
    def __init__(self, settings=None):
        self.settings = normalise(settings)
        b = self.settings["backend"]
        self.backend = OpenAICompatibleBackend(self.settings) if b == "openai-compatible" else OffBackend()

    def describe(self, private):
        """What the UI says about drafting for a study: backend, model, endpoint host, route or refusal."""
        s = self.settings
        d = {"backend": s["backend"], "model": s["model"] or None, "host": endpoint_host(s["base_url"]) or None,
             "problem": s.get("problem"), "route": None, "refused": None}
        try:
            d["route"] = route_for(s, private)
        except RouteRefused as e:
            d["refused"] = str(e)
        return d

    def draft(self, task, context):
        if task not in TASKS:
            raise DraftError(f"unknown drafting task {task!r}")
        text = context.get("text") if isinstance(context.get("text"), str) else ""
        text = text.strip()
        if not text:
            raise DraftError("paste some text to draft from")
        if len(text) > MAX_TEXT:
            raise DraftError(f"the text is over {MAX_TEXT} characters; paste a shorter part")
        if self.settings["backend"] == "off":
            why = f" ({self.settings['problem']})" if self.settings.get("problem") else ""
            raise DraftError("drafting is off" + why + "; docs/app.md says how to set up an endpoint")
        route = route_for(self.settings, bool(context.get("private", True)))  # unknown privacy: treated as private
        out = self.backend.draft(task, {"text": text})
        out["route"] = route
        return out
