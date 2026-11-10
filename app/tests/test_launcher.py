"""The launcher app/atelier.py: start prints a one-time login link that works, status, token --new, stop.

Runs the real command in subprocesses, on a temp data dir, a temp private dir and a free port; never the user's.
"""
import http.client
import os
import pathlib
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse

from app.tests import helpers

LAUNCHER = helpers.APP_DIR / "atelier.py"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.data = pathlib.Path(tempfile.mkdtemp(prefix="atelier-launch-"))
        self.priv = helpers.make_private_dir()
        self.port = free_port()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ATELIER_")}

    def tearDown(self):
        self.run_cli("stop")
        helpers.cleanup(self.data)
        helpers.cleanup(self.priv)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(LAUNCHER), "--data-dir", str(self.data), *args], capture_output=True,
                              text=True, timeout=60, env=self.env)

    def test_start_status_token_stop(self):
        r = self.run_cli("start", "--port", str(self.port), "--private-dir", str(self.priv))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r"one-time login link \(single use, 10 minutes\): (http://127\.0\.0\.1:(\d+)/login/once\?n=\S+)",
                      r.stdout)
        self.assertTrue(m, r.stdout)
        self.assertEqual(int(m.group(2)), self.port)
        # the link logs in once (session cookie), and is not in the server log
        u = urllib.parse.urlsplit(m.group(1))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", f"{u.path}?{u.query}", headers={"Host": f"127.0.0.1:{self.port}"})
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 303)
        self.assertIn("atelier_session=", resp.getheader("Set-Cookie") or "")
        conn.close()
        log = (self.data / "server.log").read_text()
        self.assertNotIn(u.query, log)
        self.assertEqual(stat.S_IMODE((self.data / "server.log").stat().st_mode), 0o600)
        self.assertFalse((self.data / "run" / "login-url").exists())
        # status
        r = self.run_cli("status")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"Atelier is running at http://127.0.0.1:{self.port}/", r.stdout)
        self.assertIn("port answering", r.stdout)
        self.assertIn("Drafting route: off", r.stdout)
        # a second start does not start a second server
        r = self.run_cli("start", "--port", str(self.port))
        self.assertEqual(r.returncode, 0)
        self.assertIn("already running", r.stdout)
        # token --new: a new 0600 token, never printed
        old = (self.data / "token").read_text()
        r = self.run_cli("token", "--new")
        self.assertEqual(r.returncode, 0)
        new = (self.data / "token").read_text()
        self.assertNotEqual(old, new)
        self.assertNotIn(new.strip(), r.stdout + r.stderr)
        self.assertEqual(stat.S_IMODE((self.data / "token").stat().st_mode), 0o600)
        self.assertIn("still accepts the old token", r.stdout)
        # stop: process gone, port free
        r = self.run_cli("stop")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Atelier stopped", r.stdout)
        time.sleep(0.3)
        with socket.socket() as s:
            self.assertNotEqual(s.connect_ex(("127.0.0.1", self.port)), 0)
        r = self.run_cli("status")
        self.assertEqual(r.returncode, 3)
        self.assertIn("Atelier is not running", r.stdout)

    def test_stop_when_not_running_and_a_stale_pid_file(self):
        r = self.run_cli("stop")
        self.assertEqual(r.returncode, 0)
        self.assertIn("not running", r.stdout)
        (self.data / "run").mkdir(exist_ok=True)
        (self.data / "run" / "atelier.pid").write_text('{"pid": %d, "port": 1}' % os.getpid())  # not a server
        r = self.run_cli("stop")
        self.assertIn("not running", r.stdout)  # a pid that is not our serve.py is never signalled
        self.assertEqual(self.run_cli("status").returncode, 3)

    def test_start_refuses_a_busy_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            busy = s.getsockname()[1]
            r = self.run_cli("start", "--port", str(busy), "--private-dir", str(self.priv))
        self.assertEqual(r.returncode, 1)
        self.assertIn("already in use", r.stderr)


if __name__ == "__main__":
    unittest.main()
