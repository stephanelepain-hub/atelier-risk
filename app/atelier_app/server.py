"""Command line entry point: python3 app/serve.py [--port 8770] [--data-dir DIR]."""
import argparse
import ipaddress
import os
import re
import signal
import socket
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .app import MAX_UPLOAD, App
from .web import Request

QUERY_RE = re.compile(r"\?\S*")


class Handler(BaseHTTPRequestHandler):
    server_version = "Atelier"
    sys_version = ""

    def _send(self, resp):
        self.send_response(resp.status)
        for k, v in resp.headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.body)

    def _run(self):
        app = self.server.app
        if len(self.headers.get_all("Host") or []) > 1:
            self.close_connection = True
            return self.send_error(400, "duplicate Host header")
        body = b""
        if self.command == "POST":
            cl = self.headers.get("Content-Length")
            if cl is None:
                self.close_connection = True
                return self.send_error(411, "Content-Length required")
            try:
                n = int(cl)
            except ValueError:
                n = -1
            if n < 0:
                self.close_connection = True
                return self.send_error(400, "bad Content-Length")
            path = self.path.split("?", 1)[0]
            if n > app.body_limit(path):
                self.close_connection = True  # do not read the body
                return self._send(app.too_large(path))
            body = self.rfile.read(n)
        req = Request(self.command, self.path, dict(self.headers.items()), body, peer=self.client_address[0])
        self._send(app.handle(req))

    do_GET = do_POST = do_HEAD = _run

    def log_message(self, fmt, *args):  # never log query strings: one-time login nonces travel there
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), QUERY_RE.sub("?...", fmt % args)))


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Server6(Server):
    address_family = socket.AF_INET6


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="serve.py", description="Atelier web app (local, single user).")
    ap.add_argument("--host", default=config.DEFAULT_HOST, help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=config.DEFAULT_PORT, help="port (default 8770)")
    ap.add_argument("--data-dir", default=None, help="data directory (default $ATELIER_DATA_DIR or ~/.local/share/atelier)")
    ap.add_argument("--allow-remote", action="store_true", help="allow a non-loopback bind address (not recommended)")
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="extra Host header value to accept, as host:port (only with --allow-remote)")
    ap.add_argument("--url-file", default=None,
                    help="write the one-time login link to this file (mode 600) instead of printing it (the launcher "
                         "app/atelier.py reads it, prints it and deletes it)")
    ap.add_argument("--public", action="store_true",
                    help="public mode for an internet server: no token login, an anonymous private workspace per visitor")
    ap.add_argument("--invite-code-file", default=None,
                    help="public mode: a file holding the invite code on one line (readable by its owner only)")
    ap.add_argument("--behind-proxy", action="store_true",
                    help="take the client address from X-Real-IP, set by the local reverse proxy (else the socket address)")
    return ap.parse_args(argv)


class InviteCodeError(Exception):
    pass


def read_invite_code(path):
    """The invite code, the first line of the file. The file must be readable by its owner only."""
    p = os.path.abspath(os.path.expanduser(path))
    try:
        mode = stat.S_IMODE(os.stat(p).st_mode)
        if mode & 0o077:
            raise InviteCodeError(f"{p} can be read by other users (mode {mode:03o}); run chmod 600 on it, then start again")
        with open(p, encoding="utf-8") as f:
            code = f.readline().strip()
    except OSError as e:
        raise InviteCodeError(f"cannot read the invite code file {p}: {e.strerror or e}") from e
    if not code:
        raise InviteCodeError(f"the invite code file {p} is empty; put the code on its first line")
    return code


def purge_loop(app, every=3600, stop=None):
    """Delete the workspaces idle for 30 days and the shared studies kept for 12 months, now and then once an hour (a daemon thread; `stop` is an Event for tests)."""
    stop = stop or threading.Event()
    while True:
        for what, fn, said in (("workspaces", app.purge_idle, "Cleared {n} workspace(s) idle for 30 days."),
                               ("shared studies", app.purge_shared, "Deleted {n} shared stud(ies) kept for 12 months.")):
            try:
                n = fn()
                if n:
                    print(said.format(n=n), flush=True)
            except Exception as e:  # keep the loop alive: the next hour tries again
                print(f"Clean-up of {what} failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if stop.wait(every):
            return


def main(argv=None):
    a = parse_args(argv)
    if not is_loopback(a.host) and not a.allow_remote:
        print(f"refusing to bind {a.host}: not a loopback address (pass --allow-remote to override)", file=sys.stderr)
        return 2
    if a.allowed_host and not a.allow_remote:
        print("--allowed-host needs --allow-remote", file=sys.stderr)
        return 2
    if a.invite_code_file and not a.public:
        print("--invite-code-file needs --public", file=sys.stderr)
        return 2
    code = None
    if a.invite_code_file:
        try:
            code = read_invite_code(a.invite_code_file)
        except InviteCodeError as e:
            print(f"refusing to start: {e}", file=sys.stderr)
            return 2
    host = "127.0.0.1" if a.host == "localhost" else a.host
    data = a.data_dir or config.default_data_dir()
    extra = list(a.allowed_host)
    if a.allow_remote and not is_loopback(host):
        extra.append(f"{host}:{a.port}")
    app = App(data, port=a.port, extra_hosts=extra, max_upload=MAX_UPLOAD, public=a.public, invite_code=code,
              behind_proxy=a.behind_proxy)
    srv = (Server6 if ":" in host else Server)((host, a.port), Handler)
    srv.app = app
    port = srv.server_address[1]
    app.set_port(port)
    shown = f"[{host}]" if ":" in host else host
    print(f"Atelier listening on http://{shown}:{port}/", flush=True)
    print(f"Data directory: {app.data_dir}", flush=True)
    if app.public:
        print("Public mode: visitors join at /join" + (" with the invite code." if code else " (no invite code)."), flush=True)
        threading.Thread(target=purge_loop, args=(app,), daemon=True, name="purge-idle").start()
    else:
        serve_login(app, a, shown, port)

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        print("Atelier stopped.", flush=True)
    return 0


def serve_login(app, a, shown, port):
    """Local mode: print the token file and the one-time login link (or write the link for the launcher)."""
    nonce = app.auth.mint_once("/")
    print(f"Login token file{' (new)' if app.token_created else ''}: {app.token_path}", flush=True)
    link = f"http://{shown}:{port}/login/once?n={nonce}"
    if a.url_file:
        import os
        uf = os.path.abspath(os.path.expanduser(a.url_file))
        fd = os.open(uf + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(link + "\n")
        os.replace(uf + ".tmp", uf)
        print("One-time login link written for the launcher (not shown in this log).", flush=True)
    else:
        print(f"One-time login link (single use, 10 minutes): {link}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
