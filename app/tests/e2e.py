#!/usr/bin/env python3
"""End-to-end run against a real server process (not part of the unit suite).

  python3 app/tests/e2e.py --data-dir /tmp/atelier-e2e --out /tmp/e2e-report [--port 8770] [--screenshots DIR]

Starts app/serve.py on 127.0.0.1:<port> with a throwaway data directory, logs in with the token, loads the guide
example, adds a feared event in workshop 1, checks that the engine checks changed, opens the register and grid,
downloads the Excel export and opens it with openpyxl. With --screenshots it also renders pages with headless
Firefox, each run in its own throwaway profile, logged in through a one-time link. Stops the server at the end.
Writes <out>/e2e.json and <out>/ss-*.txt. Exits 1 on the first failed step. The token is never printed.
"""
import argparse
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
        st, h, body = call("GET", f"/s/{sid}/w1")
        page = body.decode()
        step("W1 editor: example valid", st == 200 and "No error, no warning." in page)

        st, h, _ = call("POST", f"/s/{sid}/w1/fe/add", {"csrf": csrf, "business_value": "BV2", "label": "Batch records altered",
                                                         "criterion": "integrity", "severity": "3"})
        step("add a feared event in W1", st == 303, h.get("Location", ""))
        st, h, body = call("GET", f"/s/{sid}/w1")
        page = body.decode()
        want = "FE4: severity 3 but no scenario targets it (blind spot, guide p.73)"
        step("validate updated after save", want in page and "1 warning" in page, want)

        st, h, body = call("GET", f"/s/{sid}/register")
        page = body.decode()
        levels = dict(re.findall(r'<tr id="el-(R\d)">.*?<span class="lvl [^"]*">([^<]+)</span>', page, re.S))
        cli = subprocess.run([sys.executable, "-m", "atelier_engine", "register",
                              str(pathlib.Path(a.data_dir) / "studies" / f"{sid}.json")],
                             cwd=APP_DIR.parent / "engine", capture_output=True, text=True)
        cli_levels = {r["id"]: r["level"] for r in json.loads(cli.stdout)["risks"]}
        report["register_levels_app"] = levels
        report["register_levels_cli"] = cli_levels
        step("register levels equal engine CLI", st == 200 and levels == cli_levels and len(levels) == 5, json.dumps(levels))
        step("grid rendered", "<figcaption>Now</figcaption>" in page and page.count('class="chip"') == 5)

        st, h, body = call("GET", f"/s/{sid}/export.xlsx")
        step("xlsx export downloaded", st == 200 and body[:2] == b"PK", f"{len(body)} bytes")
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(body))
        report["xlsx_sheets"] = wb.sheetnames
        (out / "export.xlsx").write_bytes(body)
        step("xlsx opens with openpyxl, sheets exist",
             {"Risk register", "Feared events", "Strategic scenarios", "About"} <= set(wb.sheetnames), ", ".join(wb.sheetnames))
        st, h, body = call("GET", f"/s/{sid}/export.json")
        step("json export downloaded", st == 200 and len(json.loads(body)["feared_events"]) == 4)

        if a.screenshots:
            shots = pathlib.Path(a.screenshots)
            shots.mkdir(parents=True, exist_ok=True)
            report["screenshots"] = []
            for label, path in (("study-list", "/"), ("w1-editor", f"/s/{sid}/w1"), ("register-grid", f"/s/{sid}/register"),
                                ("w3-readonly", f"/s/{sid}/w3")):
                for w, hgt in ((1400, 1400), (900, 1600)):
                    st, h, body = call("POST", "/login/link", {"csrf": csrf, "next": path})
                    link = re.search(r'<code id="once-link">([^<]+)</code>', body.decode()).group(1)
                    png = shots / f"{label}-{w}.png"
                    prof = tempfile.mkdtemp(prefix="atelier-ff-profile-")
                    try:
                        env = dict(os.environ, MOZ_HEADLESS="1")
                        r = subprocess.run(["firefox", "--headless", "--no-remote", "--profile", prof, "--screenshot",
                                            str(png), f"--window-size={w},{hgt}", link.replace("&amp;", "&")],
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
