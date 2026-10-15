"""Tests for the local browser bridge and the report/privacy helpers (no third-party network)."""
from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import browser_bridge as bb  # noqa: E402
import netchecks as nc  # noqa: E402
import selfcheck as sc  # noqa: E402


# ---------------------------------------------------------------- bridge

@pytest.fixture()
def bridge(monkeypatch: pytest.MonkeyPatch):
    """Start run_in_browser in a thread without opening a browser; yield (port, token, holder)."""
    captured: dict[str, Any] = {}
    real_session = bb._Session

    def capture(config: dict[str, Any]) -> bb._Session:
        captured["session"] = real_session(config)
        return captured["session"]

    started = {}
    real_server = bb._ExclusiveServer

    def make_server(*args: Any, **kwargs: Any) -> bb._ExclusiveServer:
        started["server"] = real_server(*args, **kwargs)
        return started["server"]

    monkeypatch.setattr(bb, "_Session", capture)
    monkeypatch.setattr(bb, "_ExclusiveServer", make_server)
    holder: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: holder.update(
        result=bb.run_in_browser({"dnsIds": ["a"]}, open_browser=False, timeout=5)))
    thread.start()
    for _ in range(100):
        if "server" in started and "session" in captured:
            break
        time.sleep(0.02)
    yield started["server"].server_port, captured["session"].token, holder, thread
    captured["session"].done.set()
    thread.join(5)


def request(port: int, method: str, path: str, body: bytes = b"", headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data, resp


def test_static_page_has_security_headers(bridge):
    port, _, _, _ = bridge
    status, body, resp = request(port, "GET", "/check.html")
    assert status == 200 and b"FuckClaudeSignals" in body
    assert "default-src 'none'" in resp.getheader("Content-Security-Policy")
    assert resp.getheader("Referrer-Policy") == "no-referrer"


def test_config_requires_token_and_host(bridge):
    port, token, _, _ = bridge
    assert request(port, "GET", "/config?t=wrong")[0] == 404
    status, body, _ = request(port, "GET", f"/config?t={token}")
    assert status == 200 and json.loads(body) == {"dnsIds": ["a"]}
    assert request(port, "GET", f"/config?t={token}", headers={"Host": "evil.example"})[0] == 403


def test_path_traversal_is_not_served(bridge):
    port, _, _, _ = bridge
    for path in ("/../selfcheck.py", "/vendor/FUCKCLAUDE-LICENSE.txt", "/check.html/../netchecks.py"):
        assert request(port, "GET", path)[0] == 404


@pytest.mark.parametrize("body,headers,status", [
    (b"{}", {"Origin": "http://evil.example"}, 403),
    (b"[1,2]", {}, 400),
    (b"\xff\xfe", {}, 400),
    (b"not json", {}, 400),
])
def test_post_rejects_bad_input(bridge, body, headers, status):
    port, token, _, _ = bridge
    hdrs = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
    hdrs.update(headers)
    assert request(port, "POST", f"/result?t={token}", body, hdrs)[0] == status


def test_rejected_post_still_gets_a_clean_403(bridge):
    # 拒绝时若不读完请求体就关连接，Windows 会发 RST，客户端收不到 403 而是连接被重置。
    # 请求体越大越容易撞上；修之前 20 次里几乎必然出现一次。
    port, token, _, _ = bridge
    body = b'{"pad": "' + b"x" * 65536 + b'"}'
    hdrs = {"Origin": "http://evil.example", "Content-Type": "application/json"}
    for _ in range(20):
        assert request(port, "POST", f"/result?t={token}", body, hdrs)[0] == 403


def test_post_with_bad_content_length_is_rejected(bridge):
    port, token, _, _ = bridge
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", f"/result?t={token}")
    conn.putheader("Origin", f"http://127.0.0.1:{port}")
    conn.putheader("Content-Length", "-1")
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_valid_post_returns_result(bridge):
    port, token, holder, thread = bridge
    hdrs = {"Origin": f"http://127.0.0.1:{port}"}
    assert request(port, "POST", f"/result?t={token}", b'{"ok": true}', hdrs)[0] == 200
    thread.join(5)
    assert holder["result"] == {"ok": True}


# ---------------------------------------------------------------- privacy helpers

def test_redact_proxy_hides_credentials():
    assert sc.redact_proxy("http://alice:S3cret@1.2.3.4:8443") == "http://***@1.2.3.4:8443"
    assert sc.redact_proxy("http://127.0.0.1:7897") == "http://127.0.0.1:7897"
    assert sc.redact_proxy(None) is None


def test_out_strips_terminal_escapes(capsys):
    sc.out("city \x1b[2J\x1b]0;pwned\x07 ok")
    printed = capsys.readouterr().out
    assert "\x1b" not in printed and "\x07" not in printed and "ok" in printed


def test_sanitize_browser_drops_malformed_values():
    raw = {"claudeTrace": {"ip": "1.2.3.4\x1b[2J", "loc": "US"},
           "neutralTrace": {"ip": "5.6.7.8", "loc": "US;rm", "colo": "SJC\x1b"}, "ipv6": "<script>"}
    clean = sc.sanitize_browser(raw)
    assert clean["claudeTrace"] is None
    assert clean["neutralTrace"]["ip"] == "5.6.7.8" and clean["neutralTrace"]["loc"] is None
    assert clean["ipv6"] is None
    assert sc.sanitize_browser(["not", "a", "dict"]) is None


def test_save_report_masks_real_ip_unless_full(tmp_path):
    report = {"browser": {"claudeTrace": {"ip": "203.0.113.10"}},
              "paths": {"direct": {"echo": {"ip": "198.51.100.20", "raw": "当前 IP：198.51.100.20 来自于：某市"}},
                        "env_proxy": {"echo": {}}, "system_proxy": {"echo": {}}},
              "consensus": {"ip": "203.0.113.10"}}
    masked = tmp_path / "masked.json"
    sc.save_report(json.loads(json.dumps(report)), masked, full=False)
    text = masked.read_text(encoding="utf-8")
    assert "198.51.100.20" not in text and "198.51.x.x" in text and "某市" not in text
    full = tmp_path / "full.json"
    sc.save_report(json.loads(json.dumps(report)), full, full=True)
    assert "198.51.100.20" in full.read_text(encoding="utf-8")


# ---------------------------------------------------------------- netchecks guards

@pytest.mark.parametrize("url", [
    "https://claude.ai/cdn-cgi/trace", "https://api.anthropic.com/v1", "http://CLAUDE.COM/",
])
def test_fetch_refuses_claude_hosts(url):
    with pytest.raises(ValueError):
        nc.fetch(url)


def test_valid_ip_rejects_garbage():
    assert nc.valid_ip(" 1.2.3.4\n") == "1.2.3.4"
    assert nc.valid_ip("2001:db8::1") == "2001:db8::1"
    assert nc.valid_ip("1.2.3.4/../x") is None


def test_redirects_are_not_followed():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "https://claude.ai/")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=server.handle_request, daemon=True).start()
    with pytest.raises(Exception) as info:
        nc.fetch(f"http://127.0.0.1:{server.server_port}/", None, timeout=5)
    assert "302" in str(info.value)
    server.server_close()
