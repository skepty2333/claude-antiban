"""Run check.html in the user's own browser and collect its result.

A throwaway HTTP server listens on 127.0.0.1 only. The page fetches its config
and posts the result back with a random token, so other local pages can't.
No browser automation is involved: the checks run in the browser the user
really uses for Claude, with its real extensions, language and fonts.
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
STATIC = {
    "/check.html": ("check.html", "text/html; charset=utf-8"),
    "/fuckclaude-signals.js": ("vendor/fuckclaude-signals.js", "application/javascript; charset=utf-8"),
}
MAX_BODY = 2_000_000
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    # WebRTC/STUN is not covered by CSP; everything else the page may load is listed here.
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self' https://1.1.1.1 https://claude.ai https://api6.ipify.org; "
        "img-src https://*.test.dnsleaktest.com; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
}


class _Session:
    def __init__(self, config: dict[str, Any]) -> None:
        self.token = secrets.token_urlsafe(16)
        self.config = config
        self.result: Optional[dict[str, Any]] = None
        self.done = threading.Event()


class _ExclusiveServer(ThreadingHTTPServer):
    """No SO_REUSEADDR, and SO_EXCLUSIVEADDRUSE on Windows: nobody can share our port."""

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def _handler(session: _Session) -> type:
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def log_message(self, *args: Any) -> None:  # keep the terminal clean
            pass

        def _origin(self) -> str:
            return f"http://127.0.0.1:{self.server.server_port}"

        def _host_ok(self) -> bool:  # blocks DNS-rebinding style access
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def _token_ok(self) -> bool:
            given = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            return secrets.compare_digest(given.encode(), session.token.encode())

        def _send(self, status: int, body: bytes, ctype: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            path = urlparse(self.path).path
            if not self._host_ok():
                return self._send(403, b"forbidden")
            if path in STATIC:
                rel, ctype = STATIC[path]
                return self._send(200, (HERE / rel).read_bytes(), ctype)
            if path == "/config" and self._token_ok():
                return self._send(200, json.dumps(session.config).encode(), "application/json")
            return self._send(404, b"not found")

        def _discard_body(self) -> None:
            # 请求体没读完就关连接，Windows 会发 RST，对方收不到我们的错误响应
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return
            if 0 < length <= MAX_BODY:
                self.rfile.read(length)

        def do_POST(self) -> None:  # noqa: N802
            if (urlparse(self.path).path != "/result" or not self._host_ok() or not self._token_ok()
                    or self.headers.get("Origin") != self._origin()):
                self._discard_body()
                return self._send(403, b"forbidden")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._send(411, b"length required")
            if not 0 < length <= MAX_BODY:
                return self._send(413, b"bad length")
            try:
                result = json.loads(self.rfile.read(length))
            except (ValueError, RecursionError):  # also JSONDecodeError / UnicodeDecodeError
                return self._send(400, b"bad json")
            if not isinstance(result, dict):
                return self._send(400, b"expected an object")
            session.result = result
            self._send(200, b"ok")
            session.done.set()

    return Handler


def run_in_browser(config: dict[str, Any], open_browser: bool = True,
                   timeout: float = 180) -> Optional[dict[str, Any]]:
    """Serve check.html, open it, wait for the posted result (None on timeout)."""
    session = _Session(config)
    server = _ExclusiveServer(("127.0.0.1", 0), _handler(session))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/check.html?t={session.token}"
    print(f"\n浏览器检测页：{url}")
    if open_browser and webbrowser.open(url):
        print("已在默认浏览器打开。平时不用默认浏览器登 Claude 的话，把上面的地址复制到那个浏览器里。")
    else:
        print("请把上面的地址复制到你平时登 Claude 的浏览器里打开。")
    print(f"等待浏览器回传结果（最多 {int(timeout)} 秒）…")
    try:
        session.done.wait(timeout)
    finally:
        server.shutdown()
        server.server_close()
    return session.result
