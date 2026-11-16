"""Minimal Nintendo Network account + file server for the SMM server, on port 8383.

What the game (or Cemu) asks account.nintendo.net for is answered here: a fake OAuth token, a fake service token and,
the important one, the NEX token that tells the game where the SMM server is. The same port serves the course files
(/smm/course/<id>, /datastore/<name>) and the static pickup lists under www/.

Caddy forwards account.nintendo.net and wup-ama.app.nintendo.net to this server (see caddy/Caddyfile); the game also
downloads course files from it directly, over plain HTTP, at the address given by SMM_PUBLIC_IP.

Adapted from SmmServer's pretendo.py (MIT, https://github.com/SmmServer/SmmServer).
Environment:
    SMM_BIND_IP    address to listen on (default 127.0.5.1, or 127.0.0.1 on macOS; a container uses 0.0.0.0)
    SMM_PUBLIC_IP  address the game is told to connect to (default: the same as SMM_BIND_IP)
"""
import configparser
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WWW_DIR = os.path.join(ROOT_DIR, "www")
CONFIGS_DIR = os.path.join(ROOT_DIR, "Configs")
PORT = 8383
EVENT_COURSE = "00000900000-00045"  # data ID 900000: the official course the game fetches at start-up


def _default_ip():
    return "127.0.0.1" if sys.platform == "darwin" else "127.0.5.1"


BIND_IP = os.environ.get("SMM_BIND_IP") or _default_ip()
PUBLIC_IP = os.environ.get("SMM_PUBLIC_IP") or BIND_IP

# The values Cemu's own SmmServer package ships in Configs/Pretendo++.ini. The password and token are placeholders the
# NEX server does not check; the pid must be one of the users in example_smm_server.py (1337).
SERVICES = {
    "00003200": {"port": "60000"},  # friends
    "1018DB00": {"port": "59900"},  # Super Mario Maker
}
COMMON = {
    "pid": "1337",
    "password": "password",
    "access_token": "1234567890abcdef1234567890abcdef",
    "refresh_token": "fedcba0987654321fedcba0987654321fedcba12",
    "expires_in": "3600",
    "service_token": "U0VSVklDRVNFUlZJQ0VTRVJWSUNFU0VSVklDRVNFUlZJQ0VTRVJWSUNFU0VSVklDRVNFUlZJQ0VTRVI=",
    # base64 of 128 placeholder bytes, as in the upstream ini
    "token": "U01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU01NU00=",
}


def _ini():
    """Optional Configs/Pretendo++.ini (the same file the upstream SmmServer package uses) overrides the defaults."""
    config = configparser.ConfigParser()
    config.read(os.path.join(CONFIGS_DIR, "Pretendo++.ini"))
    return config


def log(msg):
    print(f"[account] {msg}", flush=True)


def _safe_join(base, *parts):
    path = os.path.normpath(os.path.join(base, *parts))
    if path != base and not path.startswith(base + os.sep):
        return None
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "nginx"  # what the game sees; it does not care

    def log_message(self, fmt, *args):
        log(f"{self.command} {self.path} - {args[1] if len(args) > 1 else ''}")

    def do_HEAD(self):
        self.route("HEAD")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def respond(self, code, ctype, body, method):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)

    def route(self, method):
        try:
            self.route_inner(method)
        except Exception as e:  # never leave the game hanging on a bug
            log(f"error on {self.path}: {e!r}")
            self.respond(500, "text/plain", b"Server Error", method)

    def route_inner(self, method):
        url = urlparse(self.path)
        path = url.path
        config = _ini()

        # drain a request body so the connection closes cleanly
        if method == "POST":
            self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))

        if path == "/ping":
            return self.respond(200, "text/plain", b"pong", method)

        if method == "POST" and path == "/v1/api/oauth20/access_token/generate":
            s = config["OAuth20"] if "OAuth20" in config else {}
            xml = (
                "<OAuth20><access_token>"
                f"<token>{s.get('access_token', COMMON['access_token'])}</token>"
                f"<refresh_token>{s.get('refresh_token', COMMON['refresh_token'])}</refresh_token>"
                f"<expires_in>{s.get('expires_in', COMMON['expires_in'])}</expires_in>"
                "</access_token></OAuth20>"
            )
            return self.respond(200, "text/xml", xml.encode(), method)

        if path == "/v1/api/provider/nex_token/@me":
            gid = parse_qs(url.query).get("game_server_id", [""])[0]
            key = gid.upper()
            if key in ("1018DC00", "1018DD00"):  # the other SMM regions share one server
                key = "1018DB00"
            if key not in SERVICES:
                return self.respond(400, "text/plain", f"unknown game_server_id {gid}".encode(), method)
            s = config[key] if key in config else {}
            host = PUBLIC_IP if os.environ.get("SMM_PUBLIC_IP") else s.get("host", PUBLIC_IP)
            xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><nex_token>'
                f"<host>{host}</host>"
                f"<nex_password>{s.get('password', COMMON['password'])}</nex_password>"
                f"<pid>{s.get('pid', COMMON['pid'])}</pid>"
                f"<port>{s.get('port', SERVICES[key]['port'])}</port>"
                f"<token>{s.get('token', COMMON['token'])}</token>"
                "</nex_token>"
            )
            log(f"nex_token for {gid}: {host}:{s.get('port', SERVICES[key]['port'])}")
            return self.respond(200, "application/xml;charset=UTF-8", xml.encode(), method)

        if path == "/v1/api/provider/service_token/@me":
            s = config["OAuth20"] if "OAuth20" in config else {}
            xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><service_token>'
                f"<token>{s.get('service_token', COMMON['service_token'])}</token></service_token>"
            )
            return self.respond(200, "application/xml;charset=UTF-8", xml.encode(), method)

        if path.startswith("/v1/api"):
            log(f"not implemented: {method} {self.path}")
            return self.respond(404, "text/plain", b"Not Found", method)

        # uploads are accepted and thrown away (this server keeps no player data)
        if path == "/smm/upload":
            return self.respond(200, "text/plain", b"OK", method)
        if path == "/smm/upload_success":
            return self.respond(200, "text/plain", b"OK", method)

        found = self.find_file(path)
        if found is None and os.path.basename(path) == EVENT_COURSE:
            # The game asks for this official course at start-up. It is not shipped with the server; the game accepts
            # an empty one, so serve that (put the real file in www/datastore/ to replace it).
            log(f"{EVENT_COURSE} is not in www/datastore/; serving an empty placeholder")
            return self.respond(200, "application/octet-stream", b"", method)
        if found is None:
            log(f"file not found: {path}")
            return self.respond(404, "text/plain", b"Not Found", method)
        with open(found, "rb") as f:
            return self.respond(200, "application/octet-stream", f.read(), method)

    def find_file(self, path):
        """Course files and static pages under www/."""
        name = os.path.basename(path)

        if path.startswith("/smm/course/"):
            m = re.search(r"(\d+)", name)
            if not m:
                return None
            name = "{:011d}-00001".format(int(m.group(1)))
            candidates = [os.path.join(WWW_DIR, "datastore", name)]
            for source in ("courseworld", "smmdb"):
                candidates += [os.path.join(WWW_DIR, source, str(i), name) for i in range(4)]
        else:
            direct = _safe_join(WWW_DIR, path.lstrip("/"))  # /datastore/<name>, /api/v1/pickup/<x>
            candidates = [direct] if direct else []
            candidates.append(os.path.join(WWW_DIR, "datastore", name))

        for c in candidates:
            if os.path.isfile(c):
                return c
        return None


def main():
    server = ThreadingHTTPServer((BIND_IP, PORT), Handler)
    log(f"listening on {BIND_IP}:{PORT}; the game is told to connect to {PUBLIC_IP}")
    server.serve_forever()


if __name__ == "__main__":
    main()
