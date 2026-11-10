#!/usr/bin/env python3
"""End-to-end run against a real server process (not part of the unit suite).

  python3 app/tests/e2e.py --data-dir /tmp/atelier-e2e --out /tmp/e2e-report [--port 8770] [--screenshots DIR]

Starts app/serve.py on 127.0.0.1:<port> with a throwaway data directory, logs in with the token, loads the guide
example and walks it through workshops 1 to 5 (one edit per workshop, an engine refusal of a value outside 1-4,
severities taken from the engine), checks validate in the app and with the engine CLI, compares the register and
both grids with the CLI, downloads the Excel export and reopens it with openpyxl, then follows an error link of a
broken copy to its highlighted row. Iteration 3 adds: a refused value whose form comes back with what was typed;
a study on an invented private 4-level calibration (a temp private directory, never a real one) from W1 to the
register, the Excel export and a duplicate on the public calibration; and drafting against an in-process stub of an
OpenAI-compatible API on 127.0.0.1 (draft, accept, reject; the key never in the server log). With --screenshots it
also renders pages with headless Firefox, each run in its own throwaway profile, logged in through a one-time link.
Iteration 4 adds: the drafting route set in settings.json (local route on the stub's port), a synthetic docx and a
synthetic pdf uploaded to the guide example, drafts of W1 to W5 from them, some items accepted (the user's
severity, decision, likelihood and status), others rejected or left pending, the engine's validate in the app and in
the CLI, the JSON and Excel exports, the request log without document text, and the settings page switching to a
remote route that a private study refuses. Its screenshots: documents, the W2-W5 drafting panels, settings.
A refused form is a POST answer, so its screenshot is taken from the server's exact answer bytes, served with the
app's stylesheets by a throwaway static server. Stops the server at the end.
Writes <out>/e2e.json and <out>/ss-*.txt. Exits 1 on the first failed step. The token is never printed.
"""
import argparse
import functools
import html
import http.cookiejar
import http.server
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(APP_DIR.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR.parent))
from app.tests import helpers  # noqa: E402
from app.tests.stub_model import StubModel  # noqa: E402
CSRF_RE = re.compile(r'name="csrf" value="([^"]+)"')
PRE_RE = re.compile(r'name="pre" value="([^"]+)"')
SID_RE = re.compile(r"/s/(s-[0-9]{8}-[0-9a-f]{8})")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


class Step(Exception):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--screenshots")
    ap.add_argument("--it3-shots", action="store_true", help="also take the iteration 3 screenshots")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{a.port}"
    report = {"base": base, "steps": [], "ok": False}

    def step(name, cond, detail=""):
        report["steps"].append({"step": name, "ok": bool(cond), "detail": detail})
        print(("PASS " if cond else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)
        if not cond:
            raise Step(name)

    # an invented private calibration in a temp dir (never the user's private directory), the stub model, its key
    priv = helpers.make_private_dir()
    pathlib.Path(a.data_dir).parent.mkdir(parents=True, exist_ok=True)
    keydir = pathlib.Path(tempfile.mkdtemp(prefix="atelier-e2e-key-", dir=pathlib.Path(a.data_dir).resolve().parent))
    key = "sk-e2e-" + os.urandom(12).hex()
    (keydir / "model.key").write_text(key + "\n")
    (keydir / "model.key").chmod(0o600)
    stub = StubModel(by_workshop=True, usage={"prompt_tokens": 900, "completion_tokens": 120}).__enter__()
    pathlib.Path(a.data_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
    local_settings = {"route": "local", "local": {"port": stub.port, "path": "/v1", "model": "stub-model-1",
                                                  "key_file": str(keydir / "model.key"),
                                                  "ssh_hint": "ssh -N -L 11434:127.0.0.1:11434 user@model-host"},
                      "limits": {"requests_per_minute": 30, "max_output_tokens": 2048, "context_tokens": 8192,
                                 "max_chunks": 4}}
    sfile = pathlib.Path(a.data_dir) / "settings.json"
    sfile.write_text(json.dumps(local_settings))
    sfile.chmod(0o600)
    env = {k: v for k, v in os.environ.items() if not k.startswith("ATELIER_")}
    proc = subprocess.Popen([sys.executable, str(APP_DIR / "serve.py"), "--port", str(a.port), "--data-dir", a.data_dir,
                             "--private-dir", str(priv)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=env)
    replays = {}
    try:
        banner = []
        deadline = time.time() + 15
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            banner.append(re.sub(r"n=\S+", "n=<one-time nonce>", line.rstrip()))
            if "One-time login link" in line:
                break
        report["banner"] = banner
        step("server started", any("listening on http://127.0.0.1:%d/" % a.port in b for b in banner), banner[0] if banner else "")

        ss = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
        (out / "ss-running.txt").write_text(ss)
        ours = [l for l in ss.splitlines() if re.search(rf":{a.port}\s", l)]
        step("ss: port bound on 127.0.0.1 only", len(ours) == 1 and f"127.0.0.1:{a.port}" in ours[0], ours[0] if ours else "none")

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)

        def call(method, path, form=None, data=None, headers=None):
            h = dict(headers or {})
            body = None
            if form is not None:
                body = urllib.parse.urlencode(form, doseq=True).encode()
                h["Content-Type"] = "application/x-www-form-urlencoded"
            elif data is not None:
                body = data
            req = urllib.request.Request(base + path, data=body, method=method, headers=h)
            try:
                r = opener.open(req, timeout=30)
            except urllib.error.HTTPError as e:
                return e.code, dict(e.headers), e.read()
            return r.status, dict(r.headers), r.read()

        st, h, _ = call("GET", "/")
        step("no cookie -> redirect to /login", st == 303 and h.get("Location") == "/login", f"{st} {h.get('Location')}")
        st, h, _ = call("GET", "/", headers={"Host": "rebind.example"})
        step("foreign Host header refused", st == 421, str(st))

        st, h, body = call("GET", "/login")
        pre = PRE_RE.search(body.decode()).group(1)
        st, h, body = call("POST", "/login", {"pre": pre, "token": "wrong-token-value"})
        step("wrong token refused", st == 403, str(st))
        token = (pathlib.Path(a.data_dir) / "token").read_text().strip()  # used, never printed
        st, h, body = call("GET", "/login")
        pre = PRE_RE.search(body.decode()).group(1)
        st, h, body = call("POST", "/login", {"pre": pre, "token": token})
        step("login with the token", st == 303 and any(c.name == "atelier_session" for c in jar), str(st))

        st, h, body = call("GET", "/")
        page = body.decode()
        step("study list renders", st == 200 and "<h1>Studies</h1>" in page, str(st))
        csrf = CSRF_RE.search(page).group(1)
        st, h, _ = call("POST", "/new", {"name": "no csrf"})
        step("POST without CSRF refused", st == 403, str(st))

        st, h, _ = call("POST", "/example", {"csrf": csrf})
        sid = SID_RE.search(h.get("Location", "")).group(1)
        step("load the guide example", st == 303, sid)
        study_file = pathlib.Path(a.data_dir) / "studies" / f"{sid}.json"

        def stored():
            return json.loads(study_file.read_text(encoding="utf-8"))

        def el(key, eid):
            return next(x for x in stored().get(key) or [] if x.get("id") == eid)

        def checks(path):
            page = call("GET", path)[2].decode()
            panel = page.split('<aside class="checks-panel"', 1)[1]
            return page, [(k, html.unescape(m).strip()) for k, m in re.findall(r'<li class="(err|wrn)">([^<]*)', panel)]

        page, msgs = checks(f"/s/{sid}/w1")
        step("W1 editor: example valid", "No error, no warning." in page and msgs == [])

        # W1: edit one object (BV1 owner), add a feared event (blind spot warning appears)
        st, h, _ = call("POST", f"/s/{sid}/w1/bv/BV1", {"csrf": csrf, "label": el("business_values", "BV1")["label"],
                                                        "nature": "information", "owner": "R&D director"})
        step("W1: edit BV1", st == 303 and el("business_values", "BV1").get("owner") == "R&D director", h.get("Location", ""))
        st, h, _ = call("POST", f"/s/{sid}/w1/fe/add", {"csrf": csrf, "business_value": "BV2", "label": "Batch records altered",
                                                         "criterion": "integrity", "severity": "3"})
        step("W1: add a feared event", st == 303, h.get("Location", ""))
        page, msgs = checks(f"/s/{sid}/w1")
        want = "FE4: severity 3 but no scenario targets it (blind spot, guide p.73)"
        step("validate updated after save", ("wrn", want) in msgs and "1 warning" in page, want)

        # W2: edit RO2 (motivation, resources); the engine refuses 5
        ro2 = el("risk_origins", "RO2")
        form = {"csrf": csrf, "origin": ro2["origin"], "objective": ro2["objective"], "motivation": "3", "resources": "4",
                "decision": "selected", "feared_events": ro2["feared_events"]}
        before = study_file.read_bytes()
        st, h, body = call("POST", f"/s/{sid}/w2/ro/RO2", dict(form, motivation="5", origin="Activist (typed, kept)"))
        refused = st == 400 and study_file.read_bytes() == before
        step("W2: motivation 5 refused by the engine, file unchanged", refused, str(st))
        page = body.decode()
        fm = page.split(f'action="/s/{sid}/w2/ro/RO2"', 1)[1].split("</form>", 1)[0]
        kept = ('name="origin" value="Activist (typed, kept)"' in fm and '<option value="5" selected>5 (not in the scale)'
                in fm and '<option value="4" selected>' in fm.split('name="resources"', 1)[1].split("</select>", 1)[0])
        msg = re.search(r'<select name="motivation">.*?</select><span class="field-error" role="alert">([^<]*)</span>',
                        fm, re.S)
        step("W2: the refused form keeps what was typed", kept)
        step("W2: the engine's message is next to the motivation field",
             msg is not None and html.unescape(msg.group(1)) ==
             "The engine refused the value: RO2: motivation 5 out of scale 1-4", msg.group(1) if msg else "none")
        replays["refused-form"] = body
        st, h, _ = call("POST", f"/s/{sid}/w2/ro/RO2", form)
        ro2 = el("risk_origins", "RO2")
        step("W2: edit RO2", st == 303 and (ro2.get("motivation"), ro2.get("resources")) == (3, 4), json.dumps(ro2))

        # W3: edit SS3 to also target FE4; the engine sets its severity; the blind spot goes away
        ss3 = el("strategic_scenarios", "SS3")
        form = {"csrf": csrf, "risk_origin": "RO2", "feared_events": ["FE3", "FE4"], "severity": "1",
                "path_id": [p["id"] for p in ss3["paths"]], "path_label": [p["label"] for p in ss3["paths"]],
                "path_stakeholder": [p.get("stakeholder", "") for p in ss3["paths"]]}
        st, h, _ = call("POST", f"/s/{sid}/w3/ss/SS3", form)
        ss3 = el("strategic_scenarios", "SS3")
        step("W3: edit SS3, severity from the engine (form said 1)", st == 303 and ss3["feared_events"] == ["FE3", "FE4"]
             and ss3["severity"] == 4, json.dumps(ss3))
        page, msgs = checks(f"/s/{sid}/w3")
        step("W3: blind spot gone, engine check passed", msgs == [] and "engine check passed" in page, json.dumps(msgs))

        # W4: add an operational scenario on SS1-P3, then edit it
        st, h, _ = call("POST", f"/s/{sid}/w4/os/add", {"csrf": csrf, "target": "SS1::SS1-P3", "likelihood": "4",
                                                         "description": "Provider account phished, data copied out"})
        loc = h.get("Location", "")
        step("W4: add an operational scenario", st == 303 and "hl=OS1" in loc, loc)
        st, h, _ = call("POST", f"/s/{sid}/w4/os/OS1", {"csrf": csrf, "target": "SS1::SS1-P3", "likelihood": "4",
                                                         "description": "Provider admin account phished; R&D files copied out"})
        os1 = el("operational_scenarios", "OS1")
        step("W4: edit OS1", st == 303 and os1 == {"id": "OS1", "strategic_scenario": "SS1", "path": "SS1-P3", "likelihood": 4,
                                                   "description": "Provider admin account phished; R&D files copied out"},
             json.dumps(os1))

        # W5: edit R3 (link to OS1, target likelihood, treatment, owner), add a measure for it
        r3 = el("risks", "R3")
        st, h, _ = call("POST", f"/s/{sid}/w5/rk/R3", {"csrf": csrf, "scenario": "os::OS1", "label": r3["label"],
                                                        "likelihood": "4", "likelihood_target": "2", "treatment": "reduce",
                                                        "owner": "CISO", "severity": "1"})
        r3 = el("risks", "R3")
        step("W5: edit R3, severity from the engine (form said 1)", st == 303 and r3.get("operational_scenario") == "OS1"
             and r3["severity"] == 3 and r3.get("likelihood_target") == 2, json.dumps(r3))
        page, msgs = checks(f"/s/{sid}/w5")
        want = "R3: target likelihood lower than today with no measure linked"
        step("W5: engine warns, no measure yet", msgs == [("wrn", want)], json.dumps(msgs))
        st, h, _ = call("POST", f"/s/{sid}/w5/ms/add", {"csrf": csrf, "label": "Provider access through a bastion with MFA",
                                                         "risks": ["R3"], "owner": "IT", "due": "2027-03-31",
                                                         "status": "planned"})
        step("W5: add a measure", st == 303 and el("measures", "M1")["risks"] == ["R3"], h.get("Location", ""))
        page, msgs = checks(f"/s/{sid}/w5")
        step("validate after W1-W5 edits: no error, no warning", msgs == [] and "No error, no warning." in page)
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "validate", str(study_file)],
                             cwd=APP_DIR.parent / "engine", capture_output=True, text=True)
        (out / "cli-validate.json").write_text(cli.stdout)
        step("engine CLI validate agrees", cli.returncode == 0 and json.loads(cli.stdout)["errors"] == []
             and json.loads(cli.stdout)["warnings"] == [], cli.stdout.strip()[:200])

        st, h, body = call("GET", f"/s/{sid}/register")
        page = body.decode()
        levels = dict(re.findall(r'<tr id="el-(R\d)">.*?<span class="lvl [^"]*">([^<]+)</span>', page, re.S))
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "register", str(study_file)],
                             cwd=APP_DIR.parent / "engine", capture_output=True, text=True)
        (out / "cli-register.json").write_text(cli.stdout)
        reg = json.loads(cli.stdout)
        cli_levels = {r["id"]: r["level"] for r in reg["risks"]}
        report["register_levels_app"] = levels
        report["register_levels_cli"] = cli_levels
        step("register levels equal engine CLI", st == 200 and levels == cli_levels and len(levels) == 5, json.dumps(levels))
        r3cli = next(r for r in reg["risks"] if r["id"] == "R3")
        report["r3_cli"] = r3cli
        tgt = page.split("<figcaption>At target</figcaption>")[1].split("</figure>")[0]
        step("grids: now holds 5 chips, at target holds R3 at its engine level",
             page.split("<figcaption>Now</figcaption>")[1].split("</figure>")[0].count('class="chip"') == 5
             and re.findall(r'class="chip"[^>]*>([^<]+)</a>', tgt) == ["R3"] and r3cli.get("level_target") in page,
             json.dumps(r3cli, ensure_ascii=False))
        st, h, body = call("GET", f"/s/{sid}/w5")
        step("W5 page shows both grids", st == 200 and "<figcaption>Now</figcaption>" in body.decode()
             and "<figcaption>At target</figcaption>" in body.decode())

        st, h, body = call("GET", f"/s/{sid}/export.xlsx")
        step("xlsx export downloaded", st == 200 and body[:2] == b"PK", f"{len(body)} bytes")
        import openpyxl
        (out / "export.xlsx").write_bytes(body)
        wb = openpyxl.load_workbook(out / "export.xlsx")
        report["xlsx_sheets"] = wb.sheetnames
        step("xlsx reopens with openpyxl, sheets exist",
             {"Risk register", "Feared events", "Risk origins", "Stakeholders", "Strategic scenarios",
              "Operational scenarios", "Measures", "About"} <= set(wb.sheetnames), ", ".join(wb.sheetnames))
        ws = wb["Risk register"]
        head = [c.value for c in ws[1]]
        rows = {r[0]: dict(zip(head, r)) for r in ws.iter_rows(min_row=2, values_only=True)}
        report["xlsx_r3"] = rows.get("R3")
        step("xlsx R3 row: engine levels now and at target, measure M1",
             rows.get("R3", {}).get("level") == r3cli["level"] and rows["R3"].get("level_target") == r3cli["level_target"]
             and rows["R3"].get("measures") == "M1", json.dumps(rows.get("R3"), ensure_ascii=False, default=str))
        osh = [r for r in wb["Operational scenarios"].iter_rows(values_only=True)]
        step("xlsx Operational scenarios sheet holds OS1", any(r and r[0] == "OS1" for r in osh[1:]), json.dumps(osh[:2], default=str))
        st, h, body = call("GET", f"/s/{sid}/export.json")
        exp = json.loads(body)
        step("json export holds the edits", st == 200 and len(exp["feared_events"]) == 4 and len(exp["operational_scenarios"]) == 1
             and len(exp["measures"]) == 1)

        # navigation: a study with an error in W3; its link lands on the row, highlighted
        broken = json.loads(json.dumps(exp))
        broken["study"]["name"] = "Broken copy (navigation check)"
        broken["strategic_scenarios"][1]["paths"][0]["stakeholder"] = "SH9"
        bnd = "----e2eBoundary"
        data = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{csrf}\r\n"
                f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"broken.json\"\r\n"
                f"Content-Type: application/json\r\n\r\n").encode() + json.dumps(broken).encode() + f"\r\n--{bnd}--\r\n".encode()
        st, h, _ = call("POST", "/import", data=data, headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
        bsid = SID_RE.search(h.get("Location", "")).group(1)
        page, msgs = checks(f"/s/{bsid}")
        step("broken copy: engine error listed", msgs == [("err", "SS2/SS2-P1: unknown stakeholder SH9")], json.dumps(msgs))
        step("error links to its row", f'href="/s/{bsid}/el/SS2-P1">SS2-P1 in W3</a>' in page)
        st, h, _ = call("GET", f"/s/{bsid}/el/SS2-P1")
        loc = h.get("Location", "")
        step("link redirects to W3 with the row marked", st == 303 and loc == f"/s/{bsid}/w3?hl=SS2-P1#el-SS2-P1", loc)
        st, h, body = call("GET", loc.split("#")[0])
        step("W3 row highlighted", '<li id="el-SS2-P1" class="hl">' in body.decode())
        page, _ = checks(f"/s/{bsid}")
        step("progress strip: W3 has the error", re.search(r'<li class="ps-bad"><a href="/s/' + bsid +
                                                          r'/w3"><b>W3</b>.*?1 error,', page) is not None)

        # ---------- a study on an invented private calibration (4 levels), W1 to the register ----------
        SY = helpers.SYNTH_ID
        st, h, body = call("GET", "/")
        pick = body.decode().split('<fieldset class="cal-pick">', 1)[1].split("</fieldset>", 1)[0]
        step("picker lists public and private calibrations, private badge, 4 levels",
             'value="anssi-v1.5"' in pick and f'value="{SY}"' in pick and '<span class="badge private"' in pick
             and "4 risk levels" in pick and '<span class="badge public">public</span>' in pick)
        st, h, _ = call("POST", "/new", {"csrf": csrf, "name": "Invented private study", "calibration": SY})
        psid = SID_RE.search(h.get("Location", "")).group(1)
        pfile = pathlib.Path(a.data_dir) / "studies" / f"{psid}.json"
        step("new study on the private calibration", st == 303 and json.loads(pfile.read_text())["study"]["calibration"] == SY)
        page = call("GET", f"/s/{psid}")[2].decode()
        step("overview: private badge, 4 risk levels, private reason", '<span class="badge private"' in page
             and "4 risk levels" in page and "it uses a private calibration" in page)
        for path, form in (
                ("w1/bv/add", {"label": "Order handling", "nature": "process"}),
                ("w1/fe/add", {"business_value": "BV1", "label": "Orders stopped", "criterion": "availability",
                               "severity": "4"}),
                ("w2/ro/add", {"origin": "Organised crime", "objective": "Ransom", "motivation": "3", "resources": "3",
                               "decision": "selected", "feared_events": ["FE1"]}),
                ("w3/ss/add", {"risk_origin": "RO1", "feared_events": ["FE1"], "new_path_label": "Direct intrusion"}),
                ("w5/rk/add", {"scenario": "ss::SS1", "label": "Orders stopped by ransomware", "likelihood": "3",
                               "likelihood_target": "1", "treatment": "reduce", "owner": "Operations"}),
                ("w5/ms/add", {"label": "Offline backups", "risks": ["R1"], "owner": "IT", "due": "2027-06-30",
                               "status": "planned"})):
            st, h, _ = call("POST", f"/s/{psid}/{path}", dict(form, csrf=csrf))
            step(f"private study: {path}", st == 303, h.get("Location", ""))
        page, msgs = checks(f"/s/{psid}/w5")
        step("private study: no error, no warning", msgs == [] and "No error, no warning." in page, json.dumps(msgs))
        page = call("GET", f"/s/{psid}/register")[2].decode()
        grids = re.findall(r'<table class="grid">(.*?)</table>', page, re.S)
        cells = [re.findall(r'<td class="(lvl-i\d)"><span class="lvl-name">([^<]+)</span>', g) for g in grids]
        names = {n for c in cells for _, n in c}
        step("private study: two grids of 16 cells, 4 levels and 4 colour classes",
             len(grids) == 2 and all(len(c) == 16 for c in cells) and names == {"Calm", "Watch", "Alert", "Stop"}
             and {k for c in cells for k, _ in c} == {"lvl-i0", "lvl-i1", "lvl-i2", "lvl-i3"}, json.dumps(sorted(names)))
        legend = re.search(r'<ul class="legend">(.*?)</ul>', page, re.S).group(1)
        step("private study: legend holds the 4 levels", len(re.findall(r'<span class="lvl ', legend)) == 4)
        app_lv = dict(re.findall(r'<tr id="el-(R\d)">.*?<span class="lvl [^"]*">([^<]+)</span>', page, re.S))
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "register", str(pfile)], cwd=APP_DIR.parent / "engine",
                             capture_output=True, text=True, env=dict(env, ATELIER_PRIVATE_DIR=str(priv)))
        (out / "cli-register-private.json").write_text(cli.stdout)
        cli_rows = json.loads(cli.stdout)["risks"] if cli.returncode == 0 else []
        step("private study: register equals the engine CLI (R1 Stop now, Watch at target)",
             app_lv == {r["id"]: r["level"] for r in cli_rows} and [(r["level"], r["level_target"]) for r in cli_rows]
             == [("Stop", "Watch")], json.dumps(app_lv))
        css = call("GET", f"/cal/{SY}.css")[2].decode()
        step("private study: calibration CSS has the 4 level colours",
             all(f".lvl-i{i}{{background:#{c};" in css for i, (_, c) in enumerate(helpers.SYNTH_LEVELS)))
        if helpers.HAVE_OPENPYXL:
            st, h, body = call("GET", f"/s/{psid}/export.xlsx")
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(body))
            ws = wb["Risk register"]
            hd = [c.value for c in ws[1]]
            r1 = dict(zip(hd, [c.value for c in ws[2]]))
            step("private study: xlsx opens, R1 at the engine's levels", st == 200 and (r1.get("level"),
                 r1.get("level_target")) == ("Stop", "Watch"), json.dumps(r1, default=str))
        else:
            print("SKIP private study xlsx: openpyxl not installed", flush=True)
            report["steps"].append({"step": "private study xlsx", "ok": True, "detail": "skipped: no openpyxl"})
        st, h, _ = call("POST", f"/s/{psid}/duplicate", {"csrf": csrf, "calibration": "anssi-v1.5"})
        dsid_ = SID_RE.search(h.get("Location", "")).group(1)
        cp = json.loads((pathlib.Path(a.data_dir) / "studies" / f"{dsid_}.json").read_text())
        step("duplicate with calibration anssi-v1.5: copy on the public calibration, marked confidential",
             st == 303 and cp["study"]["calibration"] == "anssi-v1.5" and cp["study"].get("confidential") is True
             and json.loads(pfile.read_text())["study"]["calibration"] == SY, json.dumps(cp["study"]))

        # ---------- drafting against the stub (OpenAI-compatible, 127.0.0.1, in this process) ----------
        st, h, _ = call("POST", "/new", {"csrf": csrf, "name": "Drafting demo", "calibration": "anssi-v1.5"})
        dsid = SID_RE.search(h.get("Location", "")).group(1)
        dfile = pathlib.Path(a.data_dir) / "studies" / f"{dsid}.json"
        page = call("GET", f"/s/{dsid}/w1")[2].decode()
        step("W1 shows the drafting box and the endpoint on this machine", "Draft from documents or text" in page
             and "<b>stub-model-1</b>" in page and "(on this machine)" in page and "route: local" in page)
        before = dfile.read_bytes()
        st, h, _ = call("POST", f"/s/{dsid}/draft", {"csrf": csrf, "text": "We take customer orders by phone and buy "
                                                     "from a few suppliers whose price list we keep."})
        step("draft from text", st == 303 and h.get("Location") == f"/s/{dsid}/w1?f=drafted#draft", str(st))
        step("the stub got one request, with the key in its Authorization header",
             len(stub.requests) == 1 and stub.requests[0]["headers"].get("Authorization") == "Bearer " + key)
        page = call("GET", f"/s/{dsid}/w1")[2].decode()
        panel = page.split('id="draft"', 1)[1].split("</section>", 1)[0]
        step("4 items listed, each marked draft; the study file unchanged",
             panel.count('<span class="badge draft">draft</span>') == 4 and dfile.read_bytes() == before)
        dr = json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{dsid}.json").read_text())
        step("no severity, likelihood or level in any draft item",
             all(not ({"severity", "likelihood", "level"} & set(x)) for x in dr["items"]), json.dumps(dr["items"])[:300])
        st, h, _ = call("POST", f"/s/{dsid}/draft/D1/accept", {"csrf": csrf, "label": "Customer order handling",
                                                                "nature": "process", "owner": "Sales"})
        step("accept D1 as a business value", st == 303 and json.loads(dfile.read_text())["business_values"] ==
             [{"id": "BV1", "label": "Customer order handling", "nature": "process", "owner": "Sales"}])
        st, h, _ = call("POST", f"/s/{dsid}/draft/D3/accept", {"csrf": csrf, "business_value": "BV1",
                                                                "label": "Orders cannot be taken for two days",
                                                                "criterion": "availability", "severity": ""})
        step("accept D3 without a severity: refused (the user must pick it)", st == 400)
        st, h, _ = call("POST", f"/s/{dsid}/draft/D3/accept", {"csrf": csrf, "business_value": "BV1",
                                                                "label": "Orders cannot be taken for two days",
                                                                "criterion": "availability", "severity": "3"})
        fe = json.loads(dfile.read_text())["feared_events"]
        step("accept D3 with the user's severity 3 (the stub said 4)", st == 303 and [x["severity"] for x in fe] == [3],
             json.dumps(fe))
        st, h, _ = call("POST", f"/s/{dsid}/draft/D2/reject", {"csrf": csrf})
        left = [x["id"] for x in json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{dsid}.json").read_text())["items"]]
        step("reject D2; D4 stays pending", st == 303 and left == ["D4"], json.dumps(left))
        # one more draft so the screenshot shows several pending items
        call("POST", f"/s/{dsid}/draft", {"csrf": csrf, "text": "Second paste: the same shop, more detail."})
        st, h, _ = call("POST", f"/s/{psid}/draft", {"csrf": csrf, "text": "Invented private text."})
        pd = json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{psid}.json").read_text())
        step("private study: drafting through the local stub is allowed (route local)",
             st == 303 and pd["batches"][0]["route"] == "local")

        # ---------- iteration 4: documents in, drafting W1 to W5 on the guide example ----------
        st, h, _ = call("POST", "/example", {"csrf": csrf})
        gsid = SID_RE.search(h.get("Location", "")).group(1)
        gfile = pathlib.Path(a.data_dir) / "studies" / f"{gsid}.json"

        def gstored():
            return json.loads(gfile.read_text(encoding="utf-8"))
        step("iteration 4: a fresh copy of the guide example", st == 303, gsid)
        docx_line = "DOCX-SOURCE: the company makes vaccines and keeps its research results on internal servers."
        pdf_line = "PDF-SOURCE: an IT service provider runs the production servers under contract."
        docx = helpers.make_docx([docx_line, "Labels are printed on site and checked before shipping."],
                                 [["Asset", "Business value"], ["Research servers", "Research and development"]])
        pdf = helpers.make_pdf([pdf_line, "Backups are copied every night to a second site."])

        def upload(name, data):
            page = call("GET", f"/s/{gsid}/docs")[2].decode()
            body, ctype = helpers.multipart({"csrf": CSRF_RE.search(page).group(1)}, {"file": (name, data)})
            return call("POST", f"/s/{gsid}/docs", data=body, headers={"Content-Type": ctype})
        st, h, _ = upload("scope-notes.docx", docx)
        step("upload a synthetic docx", st == 303 and h.get("Location") == f"/s/{gsid}/docs?f=uploaded", str(st))
        st, h, body = upload("provider-contract.pdf", pdf)
        if shutil.which("pdftotext"):
            step("upload a synthetic pdf (pdftotext on PATH)", st == 303, str(st))
        else:
            step("pdf refused with a clear message (no pdftotext on PATH)", st == 400 and b"pdftotext" in body, str(st))
        page = call("GET", f"/s/{gsid}/docs")[2].decode()
        ddir = pathlib.Path(a.data_dir) / "documents" / gsid
        metas = sorted((json.loads(p.read_text()) for p in ddir.glob("d*.json")), key=lambda m: m["uploaded"])
        step("documents listed with name, size and date; stored 0700/0600",
             all(m["name"] in page for m in metas) and len(metas) == (2 if shutil.which("pdftotext") else 1)
             and oct(ddir.stat().st_mode & 0o777) == "0o700"
             and all(oct(p.stat().st_mode & 0o777) == "0o600" for p in ddir.iterdir()),
             json.dumps([(m["name"], m["size"], m["chars"]) for m in metas]))
        doc_ids = [m["id"] for m in metas]
        for n in range(1, 6):
            k0 = len(stub.requests)
            st, h, _ = call("POST", f"/s/{gsid}/draft", {"csrf": csrf, "ws": str(n), "docs": doc_ids})
            got = stub.requests[k0:]
            user = got[0]["json"]["messages"][1]["content"] if got else ""
            system = got[0]["json"]["messages"][0]["content"] if got else ""
            items = [x for x in json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{gsid}.json").read_text())["items"]]
            step(f"W{n}: draft from both documents through the local route",
                 st == 303 and h.get("Location") == f"/s/{gsid}/w{n}?f=drafted#draft" and len(got) == 1
                 and docx_line in user and (pdf_line in user or not shutil.which("pdftotext"))
                 and system.startswith(f"# Workshop {n} draft") and got[0]["json"]["max_tokens"] == 2048,
                 f"{st}, {len(got)} request(s)")
        allitems = json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{gsid}.json").read_text())["items"]
        bad = sorted({k for x in allitems for k in x} & {"severity", "likelihood", "decision", "status", "owner", "due",
                                                          "motivation", "resources", "dependence", "penetration",
                                                          "maturity", "trust", "level"})
        step("no draft item of any workshop holds a severity, likelihood, decision, status, owner, due or rating",
             not bad and len(allitems) >= 10, f"{len(allitems)} items, forbidden keys: {bad}")

        def pending(kind):
            return [x for x in json.loads((pathlib.Path(a.data_dir) / "drafts" / f"{gsid}.json").read_text())["items"]
                    if x["kind"] == kind]
        # W1: accept all text-only items, then one feared event with the user's severity
        nbv = len(gstored()["business_values"])
        st, h, _ = call("POST", f"/s/{gsid}/draft/accept-all", {"csrf": csrf, "ws": "1"})
        step("W1: accept all text-only items (business values); feared events stay pending",
             st == 303 and len(gstored()["business_values"]) == nbv + 2 and len(pending("feared_event")) == 2)
        fe = pending("feared_event")[0]
        bv = next(b["id"] for b in gstored()["business_values"] if b["label"] == fe["business_value"])
        st, h, _ = call("POST", f"/s/{gsid}/draft/{fe['id']}/accept", {"csrf": csrf, "business_value": bv,
                                                                        "label": fe["label"], "criterion": "availability",
                                                                        "severity": "2"})
        step("W1: accept a feared event with the user's severity 2 (the stub said 4)",
             st == 303 and gstored()["feared_events"][-1]["severity"] == 2, json.dumps(gstored()["feared_events"][-1]))
        # W2: a risk origin with the user's decision; the other one stays pending
        ro = pending("risk_origin")[0]
        st, h, body = call("POST", f"/s/{gsid}/draft/{ro['id']}/accept", {"csrf": csrf, "origin": ro["origin"],
                                                                           "objective": ro.get("objective", ""),
                                                                           "feared_events": ["FE1"]})
        step("W2: accept without a decision refused (the user must pick it)", st == 400 and b"pick a decision" in body)
        st, h, _ = call("POST", f"/s/{gsid}/draft/{ro['id']}/accept", {"csrf": csrf, "origin": ro["origin"],
                                                                        "objective": ro.get("objective", ""),
                                                                        "feared_events": ["FE1"], "decision": "selected"})
        new_ro = gstored()["risk_origins"][-1]
        step("W2: accept a risk origin with the user's decision", st == 303 and new_ro["decision"] == "selected"
             and "motivation" not in new_ro, json.dumps(new_ro))
        # W3: stakeholders all at once (no ratings), one strategic scenario (severity from the engine)
        nsh = len(gstored()["stakeholders"])
        call("POST", f"/s/{gsid}/draft/accept-all", {"csrf": csrf, "ws": "3"})
        added = gstored()["stakeholders"][nsh:]
        step("W3: accept all stakeholders, no rating stored", len(added) == 2 and not any(
            k in x for x in added for k in ("dependence", "penetration", "maturity", "trust")), json.dumps(added))
        ss = pending("strategic_scenario")[0]
        st, h, _ = call("POST", f"/s/{gsid}/draft/{ss['id']}/accept", {
            "csrf": csrf, "risk_origin": new_ro["id"], "feared_events": ["FE1"],
            "new_path_label": ss["paths"][0]["label"], "new_path_stakeholder": added[0]["id"]})
        new_ss = gstored()["strategic_scenarios"][-1]
        fe1 = next(x for x in gstored()["feared_events"] if x["id"] == "FE1")
        step("W3: accept a strategic scenario; its severity is the engine's (from FE1), not the draft's 1",
             st == 303 and new_ss["severity"] == fe1["severity"] != 1, json.dumps(new_ss))
        # W4: an operational scenario with the user's likelihood
        osd = pending("operational_scenario")[0]
        st, h, _ = call("POST", f"/s/{gsid}/draft/{osd['id']}/accept", {"csrf": csrf, "target": "SS1::SS1-P1",
                                                                         "description": osd["description"], "likelihood": "2"})
        new_os = gstored()["operational_scenarios"][-1]
        step("W4: accept an operational scenario with the user's likelihood 2 (the stub said 4)",
             st == 303 and new_os["likelihood"] == 2, json.dumps(new_os))
        # W5: one measure with the user's status, one rejected
        ms = pending("measure")
        st, h, _ = call("POST", f"/s/{gsid}/draft/{ms[0]['id']}/accept", {"csrf": csrf, "label": ms[0]["label"],
                                                                           "risks": ["R1"], "status": "planned"})
        new_ms = gstored()["measures"][-1]
        step("W5: accept a measure with the user's status, no owner or due from the draft (the stub said done)",
             st == 303 and new_ms["status"] == "planned" and "owner" not in new_ms and "due" not in new_ms,
             json.dumps(new_ms))
        st, h, _ = call("POST", f"/s/{gsid}/draft/{ms[1]['id']}/reject", {"csrf": csrf})
        step("W5: reject the other measure", st == 303 and pending("measure") == [])
        # validate: in the app and in the engine CLI
        page, msgs = checks(f"/s/{gsid}/w5")
        errs = [m for k, m in msgs if k == "err"]
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "validate", str(gfile)], cwd=str(APP_DIR.parent / "engine"),
                             capture_output=True, text=True)
        step("validate: no error in the app, the engine CLI agrees", not errs and cli.returncode == 0,
             f"app errors {len(errs)}, warnings {len(msgs) - len(errs)}, cli rc {cli.returncode}: {cli.stdout.strip()[-200:]}")
        st, h, body = call("GET", f"/s/{gsid}/export.json")
        step("export JSON equals the stored study", st == 200 and json.loads(body) == gstored())
        if helpers.HAVE_OPENPYXL:
            import openpyxl
            st, h, body = call("GET", f"/s/{gsid}/export.xlsx")
            wb = openpyxl.load_workbook(io.BytesIO(body))
            step("export xlsx opens, with the accepted measure", st == 200 and "Risk register" in wb.sheetnames and any(
                new_ms["label"] in [c.value for c in row] for ws_ in wb.worksheets for row in ws_.iter_rows()),
                ", ".join(wb.sheetnames))
        else:
            report["steps"].append({"step": "iteration 4 xlsx", "ok": True, "detail": "skipped: no openpyxl"})
        logp = pathlib.Path(a.data_dir) / "drafting-log.jsonl"
        recs = [json.loads(l) for l in logp.read_text().splitlines()]
        raw = logp.read_text()
        step("request log: one line per request, no document text, mode 600",
             sum(1 for r_ in recs if r_.get("study") == gsid and r_["outcome"] == "ok") == 5 and docx_line not in raw
             and pdf_line not in raw and "DOCX-SOURCE" not in raw and oct(logp.stat().st_mode & 0o777) == "0o600",
             f"{len(recs)} lines")
        # settings page: switch to a remote route; a private study refuses it, nothing is sent
        page = call("GET", "/settings")[2].decode()
        step("settings page shows the local route and the file", "route: local (this machine)" in page
             and str(sfile) in page)
        remote_form = {"csrf": csrf, "route": "remote", "local_port": str(stub.port), "local_path": "/v1",
                       "local_model": "stub-model-1", "local_key_file": str(keydir / "model.key"),
                       "local_ssh_hint": "ssh -N -L 11434:127.0.0.1:11434 user@model-host",
                       "remote_base_url": "http://203.0.113.10:8080/v1", "remote_model": "remote-model",
                       "remote_key_file": "", "limits_requests_per_minute": "30", "limits_max_output_tokens": "2048",
                       "limits_context_tokens": "8192", "limits_max_chunks": "4"}
        st, h, _ = call("POST", "/settings", remote_form)
        step("settings saved (remote route), file mode 600", st == 303 and json.loads(sfile.read_text())["route"] == "remote"
             and oct(sfile.stat().st_mode & 0o777) == "0o600")
        k0 = len(stub.requests)
        st, h, body = call("POST", f"/s/{psid}/draft", {"csrf": csrf, "ws": "2", "text": "Invented private text."})
        step("private study + remote route: refused, nothing sent", st == 403 and b"Nothing was sent" in body
             and len(stub.requests) == k0, str(st))
        st, h, _ = call("POST", "/settings", dict(remote_form, route="local"))
        step("settings back to the local route", st == 303 and json.loads(sfile.read_text())["route"] == "local")
        # one more draft per workshop so the screenshots show pending items
        for n in (2, 3, 4, 5):
            call("POST", f"/s/{gsid}/draft", {"csrf": csrf, "ws": str(n), "docs": doc_ids})

        if a.screenshots:
            shots = pathlib.Path(a.screenshots)
            shots.mkdir(parents=True, exist_ok=True)
            report["screenshots"] = []
            std = ((1400, 1000), (900, 1300))
            tall = ((1400, 1700), (900, 2600))
            plan = [("register-maps", f"/s/{sid}/register", ((1400, 1500), (900, 1900))),
                    ("synthetic-register-maps", f"/s/{psid}/register", ((1400, 1500), (900, 1900))),
                    ("documents-panel", f"/s/{gsid}/docs", std),
                    ("w2-drafting", f"/s/{gsid}/w2", tall),
                    ("w3-drafting", f"/s/{gsid}/w3", tall),
                    ("w4-drafting", f"/s/{gsid}/w4", tall),
                    ("w5-drafting", f"/s/{gsid}/w5", tall),
                    ("settings-route", "/settings", ((1400, 1300), (900, 1900)))]
            if a.it3_shots:
                plan += [("calibration-picker", "/", std),
                         ("drafting-panel", f"/s/{dsid}/w1", ((1400, 1600), (900, 2400))),
                         ("private-overview", f"/s/{psid}", ((1400, 1800), (900, 2700))),
                         ("private-grid-4-levels", f"/s/{psid}/register", ((1400, 1200), (900, 1800))),
                         ("w2-editor", f"/s/{sid}/w2", std)]
            else:
                replays.clear()
            for label, path, sizes in plan:
                for w, hgt in sizes:
                    st, h, body = call("POST", "/login/link", {"csrf": csrf, "next": path.split("#")[0]})
                    link = re.search(r'<code id="once-link">([^<]+)</code>', body.decode()).group(1).replace("&amp;", "&")
                    if "#" in path:
                        link += "#" + path.split("#", 1)[1]
                    png = shots / f"{label}-{w}.png"
                    prof = tempfile.mkdtemp(prefix="atelier-ff-profile-")
                    try:
                        env = dict(os.environ, MOZ_HEADLESS="1")
                        r = subprocess.run(["firefox", "--headless", "--no-remote", "--profile", prof, "--screenshot",
                                            str(png), f"--window-size={w},{hgt}", link],
                                           capture_output=True, text=True, timeout=120, env=env)
                    finally:
                        shutil.rmtree(prof, ignore_errors=True)
                    ok = png.is_file() and png.stat().st_size > 10000
                    report["screenshots"].append({"file": png.name, "path": path, "width": w, "rc": r.returncode,
                                                  "bytes": png.stat().st_size if png.exists() else 0})
                    step(f"screenshot {png.name}", ok, f"rc={r.returncode}")
            # a refused form is a POST answer: serve its exact bytes with the app's stylesheets, then shoot that
            rdir = pathlib.Path(tempfile.mkdtemp(prefix="atelier-replay-"))
            try:
                (rdir / "static").mkdir()
                (rdir / "cal").mkdir()
                for name in ("app.css", "app.js"):
                    (rdir / "static" / name).write_bytes(call("GET", f"/static/{name}")[2])
                (rdir / "cal" / "anssi-v1.5.css").write_bytes(call("GET", "/cal/anssi-v1.5.css")[2])
                for label, body in replays.items():
                    (rdir / f"{label}.html").write_bytes(body)
                class Quiet(http.server.SimpleHTTPRequestHandler):
                    def log_message(self, *x):
                        pass
                rs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(rdir)))
                threading.Thread(target=rs.serve_forever, daemon=True).start()
                try:
                    for label in replays:
                        for w, hgt in ((1400, 1700), (900, 2600)):
                            png = shots / f"{label}-{w}.png"
                            prof = tempfile.mkdtemp(prefix="atelier-ff-profile-")
                            try:
                                r = subprocess.run(["firefox", "--headless", "--no-remote", "--profile", prof,
                                                    "--screenshot", str(png), f"--window-size={w},{hgt}",
                                                    f"http://127.0.0.1:{rs.server_address[1]}/{label}.html"],
                                                   capture_output=True, text=True, timeout=120,
                                                   env=dict(os.environ, MOZ_HEADLESS="1"))
                            finally:
                                shutil.rmtree(prof, ignore_errors=True)
                            ok = png.is_file() and png.stat().st_size > 10000
                            report["screenshots"].append({"file": png.name, "path": f"replay of {label}", "width": w,
                                                          "rc": r.returncode, "bytes": png.stat().st_size if png.exists() else 0})
                            step(f"screenshot {png.name} (replayed POST answer)", ok, f"rc={r.returncode}")
                finally:
                    rs.shutdown()
                    rs.server_close()
            finally:
                shutil.rmtree(rdir, ignore_errors=True)
        report["ok"] = True
    except Step:
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        err = proc.stderr.read()
        stub.__exit__()
        key_logged = key in err or str(keydir) in err
        (out / "server-log.txt").write_text(re.sub(r"n=\S+", "n=<one-time nonce>", err))
        report["steps"].append({"step": "the key and its file path are not in the server log", "ok": not key_logged})
        print(("FAIL" if key_logged else "PASS") + " the key and its file path are not in the server log", flush=True)
        if key_logged:
            report["ok"] = False
        shutil.rmtree(priv, ignore_errors=True)
        shutil.rmtree(keydir, ignore_errors=True)
        time.sleep(0.5)
        ss = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
        (out / "ss-stopped.txt").write_text(ss)
        stopped = not any(re.search(rf":{a.port}\s", l) for l in ss.splitlines())
        report["steps"].append({"step": "server stopped, port free", "ok": stopped})
        print(("PASS" if stopped else "FAIL") + " server stopped, port free", flush=True)
        report["ok"] = report["ok"] and stopped and not key_logged
        (out / "e2e.json").write_text(json.dumps(report, indent=1))
    print("E2E " + ("PASS" if report["ok"] else "FAIL"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
