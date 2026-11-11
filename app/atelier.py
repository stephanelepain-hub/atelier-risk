#!/usr/bin/env python3
"""Atelier launcher: start, stop and check the local web app, and renew its login token.

  python3 app/atelier.py start [--port 8770] [--data-dir DIR]
      Starts the server in the background on 127.0.0.1 and prints the one-time login link. Opens nothing else
      (no browser). The server log goes to <data dir>/server.log (mode 600); the link is never written there.
  python3 app/atelier.py stop     Stops the server this launcher started.
  python3 app/atelier.py status   Says whether it runs and where. Exit 0 if running, 3 if not.
  python3 app/atelier.py token --new
      Writes a new login token (mode 600). A running server keeps the old one until you stop and start it.

The data directory is $ATELIER_DATA_DIR, else ~/.local/share/atelier (see docs/app.md). Standard library only.
"""
import argparse
import json
import os
import pathlib
import secrets
import signal
import socket
import subprocess
import sys
import time

APP_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from atelier_app import config  # noqa: E402
from atelier_app.storage import atomic_write  # noqa: E402

START_WAIT = 20


def run_dir(data):
    d = pathlib.Path(data) / "run"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(d, 0o700)
    return d


def read_pid(data):
    try:
        info = json.loads((run_dir(data) / "atelier.pid").read_text())
        return info if isinstance(info, dict) and isinstance(info.get("pid"), int) else None
    except (OSError, ValueError):
        return None


def is_ours(pid):
    """True when pid is alive and runs this checkout's serve.py (so a reused pid is never signalled)."""
    try:
        cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return False  # alive but cannot be checked: never signal it
    return str(APP_DIR / "serve.py").encode() in cmd


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def cmd_start(a, data):
    info = read_pid(data)
    if info and is_ours(info["pid"]):
        print(f"Atelier is already running at http://127.0.0.1:{info.get('port')}/ (pid {info['pid']}). Log in with "
              f"the token in {pathlib.Path(data) / 'token'}, or stop and start it for a new one-time link.")
        return 0
    if listening(a.port):
        print(f"Port {a.port} on 127.0.0.1 is already in use by another program; pick another with --port.",
              file=sys.stderr)
        return 1
    rd = run_dir(data)
    url_file = rd / "login-url"
    try:
        url_file.unlink()
    except FileNotFoundError:
        pass
    cmd = [sys.executable, str(APP_DIR / "serve.py"), "--port", str(a.port), "--data-dir", str(data),
           "--url-file", str(url_file)]
    log = pathlib.Path(data) / "server.log"
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(log, 0o600)
    with os.fdopen(fd, "ab") as out:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True,
                                close_fds=True)
    atomic_write(rd / "atelier.pid", json.dumps({"pid": proc.pid, "port": a.port,
                                                  "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}).encode())
    deadline = time.time() + START_WAIT
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"Atelier did not start (exit code {proc.returncode}). See {log}.", file=sys.stderr)
            (rd / "atelier.pid").unlink(missing_ok=True)
            return 1
        if url_file.exists():
            link = url_file.read_text().strip()
            url_file.unlink()
            print(f"Atelier is running at http://127.0.0.1:{a.port}/ (pid {proc.pid}).")
            print(f"Open this one-time login link (single use, 10 minutes): {link}")
            print(f"Stop it with: python3 {APP_DIR / 'atelier.py'} stop")
            return 0
        time.sleep(0.2)
    print(f"Atelier started (pid {proc.pid}) but gave no login link within {START_WAIT} s. See {log}.", file=sys.stderr)
    return 1


def cmd_stop(a, data):
    info = read_pid(data)
    pidfile = run_dir(data) / "atelier.pid"
    if not info or not is_ours(info["pid"]):
        pidfile.unlink(missing_ok=True)
        print("Atelier is not running (no server started by this launcher).")
        return 0
    pid = info["pid"]
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not is_ours(pid):
            break
        time.sleep(0.2)
    else:
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
    pidfile.unlink(missing_ok=True)
    print(f"Atelier stopped (pid {pid}).")
    return 0


def cmd_status(a, data):
    info = read_pid(data)
    if info and is_ours(info["pid"]):
        port = info.get("port")
        print(f"Atelier is running at http://127.0.0.1:{port}/ (pid {info['pid']}, since {info.get('started')}); "
              f"port {'answering' if listening(int(port)) else 'NOT answering'}.")
        print(f"Data directory: {data}")
        return 0
    print("Atelier is not running.")
    print(f"Data directory: {data}")
    return 3


def cmd_token(a, data):
    if not a.new:
        print("Use: atelier.py token --new (the token itself is in the token file; it is never printed).")
        return 2
    path = pathlib.Path(data) / "token"
    pathlib.Path(data).mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(path, (secrets.token_urlsafe(32) + "\n").encode())
    os.chmod(path, 0o600)
    print(f"New login token written to {path} (mode 600).")
    info = read_pid(data)
    if info and is_ours(info["pid"]):
        print("The running server still accepts the old token until you stop and start it.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atelier.py", description="Start, stop and check the Atelier web app.")
    ap.add_argument("--data-dir", default=None, help="data directory (default $ATELIER_DATA_DIR or ~/.local/share/atelier)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("start", help="start the server in the background and print the one-time login link")
    st.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    sub.add_parser("stop", help="stop the server")
    sub.add_parser("status", help="is it running?")
    tk = sub.add_parser("token", help="renew the login token")
    tk.add_argument("--new", action="store_true", help="write a new token")
    a = ap.parse_args(argv)
    data = pathlib.Path(a.data_dir).expanduser() if a.data_dir else config.default_data_dir()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    return {"start": cmd_start, "stop": cmd_stop, "status": cmd_status, "token": cmd_token}[a.cmd](a, data)


if __name__ == "__main__":
    sys.exit(main())
