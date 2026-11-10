#!/usr/bin/env python3
"""End-to-end run against a real server process (not part of the unit suite).

  python3 app/tests/e2e.py --data-dir /tmp/atelier-e2e --out /tmp/e2e-report [--port 8770] [--screenshots DIR]

Starts app/serve.py on 127.0.0.1:<port> with a throwaway data directory, logs in with the token, loads the guide
example and walks it through workshops 1 to 5 (one edit per workshop, an engine refusal of a value outside 1-4,
severities taken from the engine), checks validate in the app and with the engine CLI, compares the register and
both grids with the CLI, downloads the Excel export and reopens it with openpyxl, then follows an error link of a
broken copy to its highlighted row. With --screenshots it also renders pages with headless
Firefox, each run in its own throwaway profile, logged in through a one-time link. Stops the server at the end.
Writes <out>/e2e.json and <out>/ss-*.txt. Exits 1 on the first failed step. The token is never printed.
"""
import argparse
import html
import http.cookiejar
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
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

    proc = subprocess.Popen([sys.executable, str(APP_DIR / "serve.py"), "--port", str(a.port), "--data-dir", a.data_dir],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
        st, h, _ = call("POST", f"/s/{sid}/w2/ro/RO2", dict(form, motivation="5"))
        st2, _, body = call("GET", f"/s/{sid}/w2/ro/RO2")
        refused = st == 400 and "motivation" not in el("risk_origins", "RO2")
        step("W2: motivation 5 refused by the engine", refused, str(st))
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

        if a.screenshots:
            shots = pathlib.Path(a.screenshots)
            shots.mkdir(parents=True, exist_ok=True)
            report["screenshots"] = []
            std = ((1400, 1000), (900, 1300))
            plan = [("overview-progress", f"/s/{bsid}", ((1400, 1000),)), ("study-list", "/", ((1400, 1000),))]
            plan += [(f"w{n}-editor", f"/s/{sid}/w{n}", std) for n in (1, 2, 3, 4, 5)]
            # headless screenshots do not scroll to a #fragment, so the full W5 page (grids at the bottom) needs height
            plan += [("w3-edit-scenario", f"/s/{sid}/w3/ss/SS1", std),
                     ("w5-full-with-grids", f"/s/{sid}/w5", ((1400, 2200), (900, 3400))),
                     ("register-grid", f"/s/{sid}/register", std),
                     ("error-highlighted", f"/s/{bsid}/el/SS2-P1", std)]
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
        (out / "server-log.txt").write_text(re.sub(r"n=\S+", "n=<one-time nonce>", err))
        time.sleep(0.5)
        ss = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
        (out / "ss-stopped.txt").write_text(ss)
        stopped = not any(re.search(rf":{a.port}\s", l) for l in ss.splitlines())
        report["steps"].append({"step": "server stopped, port free", "ok": stopped})
        print(("PASS" if stopped else "FAIL") + " server stopped, port free", flush=True)
        report["ok"] = report["ok"] and stopped
        (out / "e2e.json").write_text(json.dumps(report, indent=1))
    print("E2E " + ("PASS" if report["ok"] else "FAIL"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
