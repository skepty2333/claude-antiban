"""netchecks / selfcheck / update script with the network replaced by fakes."""
from __future__ import annotations

import json
import socket
import sys
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import netchecks as nc  # noqa: E402
import selfcheck as sc  # noqa: E402
import update_fuckclaude_signals as up  # noqa: E402

EXIT, REAL = "203.0.113.10", "198.51.100.20"


def fake_fetch(routes: dict[str, Any]):
    """fetch() stand-in: first route whose key is a substring of the URL wins."""
    calls: list[tuple[str, Any]] = []

    def _fetch(url: str, proxy: Any = None, payload: Any = None, timeout: float = 0) -> str:
        calls.append((url, proxy))
        for key, value in routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value if isinstance(value, str) else json.dumps(value)
        raise OSError(f"no route for {url}")

    _fetch.calls = calls  # type: ignore[attr-defined]
    return _fetch


# ---------------------------------------------------------------- netchecks

def test_normalize_proxy_adds_scheme():
    assert nc._normalize_proxy(" 127.0.0.1:7897 ") == "http://127.0.0.1:7897"
    assert nc._normalize_proxy("socks5://h:1") == "socks5://h:1"
    assert nc._normalize_proxy("") is None


def test_echo_ip_prefers_overseas_and_falls_back(monkeypatch):
    fetch = fake_fetch({"amazonaws": OSError("reset"), "icanhazip": f"{EXIT}\n"})
    monkeypatch.setattr(nc, "fetch", fetch)
    assert nc.echo_ip("http://p:1")["ip"] == EXIT
    assert [u for u, _ in fetch.calls][:2] == ["https://checkip.amazonaws.com", "https://icanhazip.com"]


def test_echo_ip_reports_all_failures(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({}))
    assert "error" in nc.echo_ip(None)


def test_echo_ip_refuses_socks():
    assert "SOCKS" in nc.echo_ip("socks5://127.0.0.1:7898")["error"]


def test_geo_lookup_maps_every_source(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({
        "ip-api.com": {"status": "success", "query": EXIT, "countryCode": "US", "regionName": "California",
                       "city": "Exampleville", "timezone": "America/Los_Angeles", "offset": -25200,
                       "isp": "X", "proxy": True, "hosting": False, "mobile": False},
        "ipapi.co": {"ip": EXIT, "country_code": "US", "timezone": "America/Los_Angeles", "utc_offset": "-0700"},
        "ipwho.is": {"success": True, "ip": EXIT, "country_code": "US",
                     "timezone": {"id": "America/Los_Angeles", "offset": -25200}},
        "ipinfo.io": {"ip": EXIT, "country": "US", "timezone": "America/Los_Angeles"},
    }))
    geo = nc.geo_lookup("http://p:1")
    assert {g["offset_min"] for n, g in geo.items() if n != "ipinfo.io"} == {-420}
    assert geo["ip-api.com"]["flags"]["proxy"] is True


def test_geo_lookup_turns_soft_failures_into_errors(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({
        "ip-api.com": {"status": "fail"}, "ipapi.co": {"error": True, "reason": "RateLimited"},
        "ipwho.is": {"success": False, "message": "limit"}, "ipinfo.io": OSError("eof"),
    }))
    assert all("error" in g for g in nc.geo_lookup(None).values())


def test_cloudflare_colo_parses_trace(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({"1.1.1.1": f"ip={EXIT}\ncolo=SJC\nloc=US\n"}))
    assert nc.cloudflare_colo(None) == {"ip": EXIT, "colo": "SJC", "loc": "US"}
    monkeypatch.setattr(nc, "fetch", fake_fetch({}))
    assert "error" in nc.cloudflare_colo(None)


def test_ip_reputation_and_country(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({
        "net.coffee": {"isResidential": False, "is_datacenter": True, "trust_score": 82, "extra": 1},
        "ipwho.is": {"country_code": "US", "connection": {"isp": "X"}},
    }))
    rep = nc.ip_reputation(EXIT, None)
    assert rep["trust_score"] == 82 and "extra" not in rep
    assert nc.ip_country("2001:db8::1", None) == {"country": "US", "isp": "X"}
    assert "error" in nc.ip_reputation("not-an-ip", None)
    assert "error" in nc.ip_country("../x", None)


def test_dns_os_resolver_counts_lookups_and_retries(monkeypatch):
    answers = iter([[], [{"ip_address": "9.9.9.9", "country_code": "US", "isp": "Q", "x": 1}]])
    monkeypatch.setattr(nc, "dns_register", lambda proxy, count=6: ["a", "b"])
    monkeypatch.setattr(nc, "dns_servers", lambda ids, proxy: next(answers))
    monkeypatch.setattr(nc.socket, "getaddrinfo", lambda *a, **k: [])
    monkeypatch.setattr(nc.time, "sleep", lambda s: None)
    result = nc.dns_os_resolver(None)
    assert result["lookups_ok"] == 2 and result["servers"][0]["ip_address"] == "9.9.9.9"


def test_dns_os_resolver_all_lookups_fail(monkeypatch):
    monkeypatch.setattr(nc, "dns_register", lambda proxy, count=6: ["a"])
    monkeypatch.setattr(nc, "dns_servers", lambda ids, proxy: [])

    def boom(*a: Any, **k: Any) -> None:
        raise socket.gaierror("nope")

    monkeypatch.setattr(nc.socket, "getaddrinfo", boom)
    assert nc.dns_os_resolver(None) == {"servers": [], "lookups_ok": 0, "lookups": 1}


def test_dns_api_helpers_shape(monkeypatch):
    monkeypatch.setattr(nc, "fetch", fake_fetch({
        "identifiers": {"status": 200},
        "servers-for-result": [{"ip_address": "1.1.1.1", "isp": "CF", "country_code": "US", "dnssec": True}],
    }))
    ids = nc.dns_register(None, count=3)
    assert len(ids) == 3 and nc.dns_servers(ids, None)[0] == {
        "ip_address": "1.1.1.1", "isp": "CF", "country_code": "US", "country": None, "city": None}


def test_direct_ipv6_unreachable(monkeypatch):
    def refuse(*a: Any, **k: Any) -> None:
        raise OSError("no route")

    monkeypatch.setattr(nc.socket, "create_connection", refuse)
    assert nc.direct_ipv6()["reachable"] is False


def test_direct_ipv6_reachable(monkeypatch):
    class Conn:
        def __enter__(self) -> "Conn":
            return self

        def __exit__(self, *a: Any) -> None:
            pass

    monkeypatch.setattr(nc.socket, "create_connection", lambda *a, **k: Conn())
    monkeypatch.setattr(nc, "fetch", fake_fetch({"api6.ipify": "2409:8a00::1"}))
    assert nc.direct_ipv6() == {"reachable": True, "probe": "2606:4700:4700::1111", "ip": "2409:8a00::1"}


def test_claude_settings_proxy(monkeypatch, tmp_path):
    monkeypatch.setattr(nc.Path, "home", classmethod(lambda cls: tmp_path))
    assert nc.claude_settings_proxy() is None
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"env": {"HTTPS_PROXY": "127.0.0.1:7897"}}), encoding="utf-8")
    assert nc.claude_settings_proxy() == "http://127.0.0.1:7897"
    (tmp_path / ".claude" / "settings.json").write_text("{broken", encoding="utf-8")
    assert nc.claude_settings_proxy() is None


def test_env_proxy_reads_process_env(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    assert nc.env_proxy() == "http://127.0.0.1:9"


@pytest.mark.skipif(sys.platform != "win32", reason="registry readers are Windows-only")
def test_windows_registry_readers_do_not_crash():
    assert isinstance(nc.persistent_env_proxy(), dict)
    assert isinstance(nc.system_proxy_pac(), bool)
    nc.system_proxy()


# ---------------------------------------------------------------- selfcheck

def done(value: Any) -> Future:
    fut: Future = Future()
    fut.set_result(value)
    return fut


def test_discover_proxies_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(nc, "env_proxy", lambda: None)
    monkeypatch.setattr(nc, "claude_settings_proxy", lambda: "http://u:pw@127.0.0.1:1")
    monkeypatch.setattr(nc, "system_proxy", lambda: None)
    monkeypatch.setattr(nc, "persistent_env_proxy", lambda: {"User:HTTPS_PROXY": "http://u:pw@h:1"})
    monkeypatch.setattr(nc, "system_proxy_pac", lambda: False)
    px = sc.discover_proxies()
    assert px["env_source"] == "~/.claude/settings.json" and px["api"] == "http://u:pw@127.0.0.1:1"
    assert px["persistent"] == {"User:HTTPS_PROXY": "http://***@h:1"}


def test_local_clock_has_offset():
    clock = sc.local_clock()
    assert isinstance(clock["offset_min"], int) and clock["source"] == "system"


def proxies() -> dict[str, Any]:
    return {"system": "http://127.0.0.1:7897", "env": "http://127.0.0.1:7897", "env_source": "HTTPS_PROXY",
            "api": "http://127.0.0.1:7897", "pac": False, "persistent": {}}


def test_build_report_tolerates_probe_failures(monkeypatch):
    bad: Future = Future()
    bad.set_exception(TimeoutError("stuck"))
    futures = {"echo_system": done({"ip": EXIT}), "echo_env": done({"ip": EXIT}),
               "echo_direct": done({"ip": REAL}), "geo": bad, "colo": done({}),
               "dns_os": done({"servers": []}), "ipv6_direct": done({"reachable": False})}
    monkeypatch.setattr(nc, "ip_reputation", lambda ip, proxy: {"trust_score": 50})
    report = sc.build_report(proxies(), futures, None, [], "skipped")
    assert report["geo"] == {} and report["consensus"]["sources"] == 0
    assert report["reputation"] == {"trust_score": 50}
    assert report["clock"]["source"] == "system"


def test_run_browser_handles_page_error(monkeypatch):
    monkeypatch.setattr(nc, "dns_register", lambda proxy: ["id"])
    monkeypatch.setattr(sc, "run_in_browser", lambda *a, **k: {"error": "boom"})
    args = SimpleNamespace(skip_browser=False, no_open=True, timeout=1)
    assert sc.run_browser(proxies(), args) == (None, ["id"], "error")
    monkeypatch.setattr(sc, "run_in_browser", lambda *a, **k: None)
    assert sc.run_browser(proxies(), args)[2] == "timeout"
    assert sc.run_browser(proxies(), SimpleNamespace(skip_browser=True))[2] == "skipped"


def test_main_end_to_end_with_fake_network(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sc, "discover_proxies", proxies)
    monkeypatch.setattr(nc, "echo_ip", lambda proxy: {"ip": EXIT if proxy else REAL})
    monkeypatch.setattr(nc, "geo_lookup", lambda proxy: {"ip-api.com": {
        "ip": EXIT, "country": "US", "city": "Exampleville", "region": "CA",
        "timezone": "America/Los_Angeles", "offset_min": -420}})
    monkeypatch.setattr(nc, "cloudflare_colo", lambda proxy: {"colo": "SJC"})
    monkeypatch.setattr(nc, "dns_os_resolver", lambda proxy: {"servers": [], "lookups_ok": 6})
    monkeypatch.setattr(nc, "direct_ipv6", lambda: {"reachable": False})
    monkeypatch.setattr(nc, "dns_register", lambda proxy: ["id"])
    monkeypatch.setattr(nc, "dns_servers", lambda ids, proxy: [{"country_code": "US", "isp": "CF"}])
    monkeypatch.setattr(nc, "ip_reputation", lambda ip, proxy: {"isResidential": True})
    browser = {"neutralTrace": {"ip": EXIT, "loc": "US"}, "claudeTrace": {"ip": EXIT, "loc": "US"},
               "webrtc": {"candidates": []}, "fuckClaude": {"score": 0, "band": "low", "signals": []},
               "env": {"timeZone": "America/Los_Angeles", "utcOffsetMinutes": -420}}
    monkeypatch.setattr(sc, "run_in_browser", lambda *a, **k: browser)
    out_json = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["selfcheck.py", "--no-open", "--json", str(out_json)])
    assert sc.main() == 0
    printed = capsys.readouterr().out
    assert "严重 0" in printed and REAL not in printed
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert REAL not in json.dumps(saved) and saved["findings"]


# ---------------------------------------------------------------- update script

def test_update_script_requires_valid_sha(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["up", "--commit", "abc"])
    with pytest.raises(SystemExit):
        up.main()


def test_update_script_without_commit_only_reports(monkeypatch, capsys):
    monkeypatch.setattr(up, "latest_commit", lambda: "f" * 40)
    monkeypatch.setattr(sys, "argv", ["up"])
    up.main()
    assert "f" * 40 in capsys.readouterr().out


def test_update_script_writes_only_with_yes(monkeypatch, tmp_path, capsys):
    target = tmp_path / "out.js"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(up, "OUT", target)
    monkeypatch.setattr(up, "build", lambda sha: "new\n")
    monkeypatch.setattr(sys, "argv", ["up", "--commit", "a" * 40])
    up.main()
    assert target.read_text(encoding="utf-8") == "old"
    monkeypatch.setattr(sys, "argv", ["up", "--commit", "a" * 40, "--yes"])
    up.main()
    assert target.read_bytes() == b"new\n"
