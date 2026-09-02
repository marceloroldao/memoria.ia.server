"""Unified local entry point for Memoria Admin and BDR Explorer."""

from __future__ import annotations

import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from auth import AuthManager
from autonomous_tests import AutonomousTestManager
from config import ShellConfig


APPS_DIR = Path(__file__).resolve().parents[1]
SHELL_STATIC = Path(__file__).with_name("static")
MEMORIA_STATIC = APPS_DIR / "memoria-admin" / "static"
BDR_STATIC = APPS_DIR / "bdr-explorer" / "explorer" / "static"

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def proxy_target(config: ShellConfig, path: str) -> tuple[str, str] | None:
    """Return (base URL, upstream path) for an allowed API namespace."""
    if path == "/api/v1" or path.startswith("/api/v1/"):
        return config.memoria_api_url, path
    prefix = "/api/bdr-explorer/v1"
    if path == prefix:
        return config.bdr_explorer_url, "/api"
    if path.startswith(prefix + "/"):
        return config.bdr_explorer_url, "/api/" + path[len(prefix) + 1 :]
    return None


def static_target(path: str) -> Path | None:
    routes = {
        "/": SHELL_STATIC / "index.html",
        "/index.html": SHELL_STATIC / "index.html",
        "/shell.css": SHELL_STATIC / "shell.css",
        "/shell.js": SHELL_STATIC / "shell.js",
        "/login": SHELL_STATIC / "login.html",
        "/login.css": SHELL_STATIC / "login.css",
        "/login.js": SHELL_STATIC / "login.js",
        "/admin/memoria": MEMORIA_STATIC / "index.html",
        "/admin/memoria/": MEMORIA_STATIC / "index.html",
        "/admin/memoria/style.css": MEMORIA_STATIC / "style.css",
        "/admin/memoria/app.js": MEMORIA_STATIC / "app.js",
        "/explorer/bdr": BDR_STATIC / "index.html",
        "/explorer/bdr/": BDR_STATIC / "index.html",
        "/explorer/bdr/styles.css": BDR_STATIC / "styles.css",
        "/explorer/bdr/app.js": BDR_STATIC / "app.js",
    }
    return routes.get(path)


class ShellHandler(BaseHTTPRequestHandler):
    config = ShellConfig()
    auth: AuthManager
    autotests: AutonomousTestManager

    def _session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get("memoria_session")
        return morsel.value if morsel else None

    def _cookie_header(self, token: str, max_age: int) -> str:
        parts = [
            f"memoria_session={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Strict",
            f"Max-Age={max_age}",
        ]
        if self.config.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _write_json(
        self,
        status: int,
        payload: object,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, file_path: Path) -> None:
        if not file_path.is_file():
            self._write_json(404, {"error": "asset_not_found"})
            return
        data = file_path.read_bytes()
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _read_body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._write_json(400, {"error": "invalid_content_length"})
            return None
        if length < 0 or length > self.config.max_request_bytes:
            self._write_json(413, {"error": "request_too_large"})
            return None
        return self.rfile.read(length) if length else b""

    def _proxy(self, target: tuple[str, str]) -> None:
        base_url, upstream_path = target
        parsed = urlsplit(self.path)
        url = base_url + upstream_path
        if parsed.query:
            url += "?" + parsed.query

        body = self._read_body()
        if body is None:
            return

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() not in {"host", "content-length"}
        }
        if base_url == self.config.memoria_api_url and self.config.memoria_api_key:
            headers["X-Memoria-Key"] = self.config.memoria_api_key
        request = Request(url, data=body if body else None, headers=headers, method=self.command)

        try:
            with urlopen(request, timeout=self.config.proxy_timeout_seconds) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-length":
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
        except HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            content_type = error.headers.get("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (URLError, socket.timeout, TimeoutError):
            self._write_json(502, {"error": "upstream_unavailable"})

    def _login(self) -> None:
        if self.command != "POST":
            self._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
            return
        body = self._read_body()
        if body is None:
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            username = str(payload.get("username", ""))
            password = str(payload.get("password", ""))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            self._write_json(400, {"error": "invalid_request"})
            return

        result = self.auth.login(username, password, self.client_address[0])
        if result.retry_after:
            self._write_json(
                429,
                {"error": "too_many_attempts"},
                {"Retry-After": str(result.retry_after)},
            )
            return
        if not result.token:
            self._write_json(401, {"error": "invalid_credentials"})
            return

        max_age = self.config.session_hours * 60 * 60
        self._write_json(
            200,
            {"status": "authenticated", "username": self.config.admin_username},
            {"Set-Cookie": self._cookie_header(result.token, max_age)},
        )

    def _logout(self) -> None:
        self.auth.logout(self._session_token())
        self._write_json(
            200,
            {"status": "logged_out"},
            {"Set-Cookie": self._cookie_header("", 0)},
        )

    def _component_health(self, base_url: str, path: str) -> dict[str, object]:
        try:
            request = Request(base_url + path, method="GET")
            with urlopen(request, timeout=min(self.config.proxy_timeout_seconds, 3.0)) as response:
                return {"status": "online" if response.status < 400 else "degraded", "code": response.status}
        except (HTTPError, URLError, socket.timeout, TimeoutError):
            return {"status": "offline"}

    def _health(self) -> None:
        memoria = self._component_health(self.config.memoria_api_url, "/api/v1/health")
        bdr = self._component_health(self.config.bdr_explorer_url, "/api/health")
        states = {memoria["status"], bdr["status"]}
        overall = "online" if states == {"online"} else "degraded"
        self._write_json(
            200,
            {
                "schema": "memoria-server-health/v1",
                "status": overall,
                "shell": {"status": "online"},
                "components": {"memoria": memoria, "bdr_explorer": bdr},
            },
        )

    def _dispatch(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path

        if path == "/api/server/v1/health":
            self._health()
            return
        if path == "/api/server/v1/login":
            self._login()
            return

        authenticated = self.auth.verify(self._session_token())
        if path == "/login":
            if authenticated:
                self._redirect("/")
            else:
                self._serve_static(SHELL_STATIC / "login.html")
            return
        if path in {"/login.css", "/login.js"}:
            self._serve_static(static_target(path))
            return

        if not authenticated:
            if path.startswith("/api/"):
                self._write_json(401, {"error": "authentication_required"})
            else:
                self._redirect("/login")
            return

        if self.autotests.dispatch(self, path, parse_qs(parsed.query)):
            return

        if path == "/api/server/v1/session":
            self._write_json(
                200,
                {"authenticated": True, "username": self.config.admin_username},
            )
            return
        if path == "/api/server/v1/logout":
            if self.command != "POST":
                self._write_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
            else:
                self._logout()
            return

        target = proxy_target(self.config, path)
        if target:
            self._proxy(target)
            return
        asset = static_target(path)
        if asset:
            self._serve_static(asset)
            return
        self._write_json(404, {"error": "route_not_found"})

    do_GET = _dispatch
    do_HEAD = _dispatch
    do_POST = _dispatch
    do_PUT = _dispatch
    do_PATCH = _dispatch
    do_DELETE = _dispatch

    def log_message(self, format: str, *args: object) -> None:
        print("[memoria-server] " + (format % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Memoria.ia Server shell")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    config = ShellConfig.from_env()
    if args.host:
        config = ShellConfig(**{**config.__dict__, "host": args.host})
    if args.port:
        config = ShellConfig(**{**config.__dict__, "port": args.port})
    if not config.admin_password:
        raise RuntimeError("MEMORIA_SERVER_ADMIN_PASSWORD is required")
    ShellHandler.config = config
    ShellHandler.auth = AuthManager(
        config.admin_username,
        config.admin_password,
        session_seconds=config.session_hours * 60 * 60,
    )
    ShellHandler.autotests = AutonomousTestManager(config)
    server = ThreadingHTTPServer((config.host, config.port), ShellHandler)
    print(f"Memoria.ia Server: http://{config.host}:{config.port}")
    print("Modules: Memoria Admin + BDR Explorer")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

