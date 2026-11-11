"""Command line entry point: python3 app/serve.py [--port 8770] [--data-dir DIR]."""
import argparse
import ipaddress
import re
import signal
import socket
import sys
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
        req = Request(self.command, self.path, dict(self.headers.items()), body)
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
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    if not is_loopback(a.host) and not a.allow_remote:
        print(f"refusing to bind {a.host}: not a loopback address (pass --allow-remote to override)", file=sys.stderr)
        return 2
    if a.allowed_host and not a.allow_remote:
        print("--allowed-host needs --allow-remote", file=sys.stderr)
        return 2
    host = "127.0.0.1" if a.host == "localhost" else a.host
    data = a.data_dir or config.default_data_dir()
    extra = list(a.allowed_host)
    if a.allow_remote and not is_loopback(host):
        extra.append(f"{host}:{a.port}")
    app = App(data, port=a.port, extra_hosts=extra, max_upload=MAX_UPLOAD)
    srv = (Server6 if ":" in host else Server)((host, a.port), Handler)
    srv.app = app
    port = srv.server_address[1]
    app.set_port(port)
    shown = f"[{host}]" if ":" in host else host
    nonce = app.auth.mint_once("/")
    print(f"Atelier listening on http://{shown}:{port}/", flush=True)
    print(f"Data directory: {app.data_dir}", flush=True)
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


if __name__ == "__main__":
    sys.exit(main())
