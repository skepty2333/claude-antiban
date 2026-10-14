"""Unit tests for the pure verdict logic in scripts/findings.py (run: python -m pytest tests)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import findings as fd  # noqa: E402

EXIT = "203.0.113.10"
REAL = "198.51.100.20"


def make_report(**overrides: Any) -> dict[str, Any]:
    """A healthy baseline: proxied everywhere, US exit, no leaks."""
    geo = {
        "ip-api.com": {"ip": EXIT, "country": "US", "city": "Exampleville", "region": "California",
                       "timezone": "America/Los_Angeles", "offset_min": -420,
                       "flags": {"proxy": False, "hosting": False}},
        "ipwho.is": {"ip": EXIT, "country": "US", "city": "Sampletown", "region": "California",
                     "timezone": "America/Los_Angeles", "offset_min": -420},
    }
    report = {
        "browser": {
            "neutralTrace": {"ip": EXIT, "loc": "US"},
            "claudeTrace": {"ip": EXIT, "loc": "US"},
            "webrtc": {"candidates": [{"address": "abc.local"}]},
            "fuckClaude": {"score": 0, "band": "low", "signals": []},
        },
        "paths": {
            "system_proxy": {"proxy": "http://127.0.0.1:7897", "echo": {"ip": EXIT}},
            "env_proxy": {"proxy": "http://127.0.0.1:7897", "echo": {"ip": EXIT}, "persistent": {}},
            "direct": {"echo": {"ip": REAL, "raw": f"当前 IP：{REAL}  来自于：中国 某省 某市  某运营商"}},
        },
        "geo": geo,
        "consensus": fd.consensus(geo),
        "dns": {"browser": {"servers": [{"country_code": "US", "isp": "Cloudflare"}]},
                "os": {"servers": []}},
        "ipv6": {"direct": {"reachable": False}, "browser": None},
        "clock": {"timezone": "America/Los_Angeles", "offset_min": -420},
        "reputation": {"isResidential": True, "trust_score": 90},
    }
    for path, value in overrides.items():
        target = report
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return report


def by_key(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["key"]: f for f in fd.evaluate(report)}


def test_healthy_report_has_no_bad_or_warn():
    levels = {f["level"] for f in fd.evaluate(make_report())}
    assert levels <= {"ok", "info"}


def test_evaluate_sorts_most_severe_first():
    report = make_report(clock={"timezone": "Asia/Shanghai", "offset_min": 480})
    assert fd.evaluate(report)[0]["level"] == "bad"


def test_mask_ip_hides_last_two_octets():
    assert fd.mask_ip("198.51.100.20") == "198.51.x.x"
    assert fd.mask_ip(None) == "?"


def test_direct_info_never_prints_full_real_ip_or_city():
    summary = by_key(make_report())["direct"]["summary"]
    assert REAL not in summary and "198.51.x.x" in summary and "某市" not in summary


def test_no_proxy_with_cn_exit_is_not_mistaken_for_tun():
    report = make_report(browser__claudeTrace={"ip": REAL, "loc": "CN"},
                         paths__system_proxy={"proxy": None, "echo": {}},
                         paths__env_proxy={"proxy": None, "echo": {}, "persistent": {}},
                         paths__direct={"echo": {"ip": REAL}})
    items = by_key(report)
    assert items["browser_exit"]["level"] == "bad"
    assert items["system_proxy"]["level"] == "bad" and items["env_proxy"]["level"] == "bad"


def test_consensus_takes_majority_and_lists_all_ips():
    geo = {"a": {"ip": "1.1.1.1", "timezone": "X"}, "b": {"ip": "1.1.1.1", "timezone": "X"},
           "c": {"ip": "2.2.2.2", "timezone": "Y"}, "d": {"error": "timeout"}}
    cons = fd.consensus(geo)
    assert cons["ip"] == "1.1.1.1" and cons["timezone"] == "X"
    assert cons["ips"] == ["1.1.1.1", "2.2.2.2"] and cons["sources"] == 3


@pytest.mark.parametrize("loc,level", [("US", "ok"), ("CN", "bad"), ("HK", "bad")])
def test_browser_exit_country(loc, level):
    report = make_report(browser__claudeTrace={"ip": EXIT, "loc": loc})
    assert by_key(report)["browser_exit"]["level"] == level


def test_missing_https_proxy_without_tun_is_bad():
    report = make_report(paths__env_proxy={"proxy": None, "echo": {}, "persistent": {}})
    assert by_key(report)["env_proxy"]["level"] == "bad"


def test_saved_but_not_loaded_https_proxy_asks_to_reopen_terminal():
    report = make_report(paths__env_proxy={"proxy": None, "echo": {},
                                           "persistent": {"User:HTTPS_PROXY": "http://127.0.0.1:7897"}})
    finding = by_key(report)["env_proxy"]
    assert finding["level"] == "warn" and "重开终端" in finding["summary"]


def test_tun_detected_when_direct_path_uses_exit_ip():
    report = make_report(paths__env_proxy={"proxy": None, "echo": {}, "persistent": {}},
                         paths__direct={"echo": {"ip": EXIT}})
    items = by_key(report)
    assert items["env_proxy"]["level"] == "warn" and "TUN" in items["env_proxy"]["summary"]
    assert "TUN" in items["direct"]["summary"]


def test_system_proxy_with_different_exit_warns():
    report = make_report(paths__system_proxy={"proxy": "http://127.0.0.1:7897", "echo": {"ip": "9.9.9.9"}})
    items = by_key(report)
    assert items["system_proxy"]["level"] == "warn"
    assert items["exit_stability"]["level"] == "warn"


@pytest.mark.parametrize("addresses,level", [
    ([], "ok"),                          # WebRTC restricted by extension/settings
    (["abc.local"], "info"),             # mDNS only: STUN may be blocked, inconclusive
    (["abc.local", EXIT], "ok"),         # public candidate is the proxy exit
    (["192.168.1.5"], "warn"),           # LAN address exposed
    (["8.8.4.4"], "warn"),               # some other public IP (e.g. separate UDP exit)
    (["abc.local", REAL], "bad"),        # the user's real IP
])
def test_webrtc_candidate_classification(addresses, level):
    report = make_report(browser__webrtc={"candidates": [{"address": a} for a in addresses]})
    assert by_key(report)["webrtc"]["level"] == level


@pytest.mark.parametrize("countries,level", [
    (["US"], "ok"), (["JP"], "warn"), (["HK"], "bad"), (["US", "CN"], "bad"),
])
def test_dns_browser_path(countries, level):
    servers = [{"country_code": c, "isp": "x"} for c in countries]
    report = make_report(dns__browser={"servers": servers})
    assert by_key(report)["dns_browser"]["level"] == level


def test_dns_os_path_empty_means_intercepted():
    assert by_key(make_report())["dns_os"]["level"] == "ok"


def test_dns_os_path_public_resolver_abroad_is_ok():
    report = make_report(dns__os={"servers": [{"country_code": "HK", "isp": "Google"}]})
    assert by_key(report)["dns_os"]["level"] == "ok"


def test_dns_os_path_cn_resolver_warns_with_fix():
    report = make_report(dns__os={"servers": [{"country_code": "CN", "isp": "China Mobile"}]})
    finding = by_key(report)["dns_os"]
    assert finding["level"] == "warn" and finding["fix"] == "dns"


def test_ipv6_browser_address_outside_exit_country_is_bad():
    report = make_report(ipv6={"direct": {"reachable": True}, "browser": "2409:8a00::1",
                               "browser_geo": {"country": "CN"}})
    assert by_key(report)["ipv6"]["level"] == "bad"


def test_ipv6_native_but_unused_by_browser_warns():
    report = make_report(ipv6={"direct": {"reachable": True, "ip": "2409:8a00::1"}, "browser": None})
    assert by_key(report)["ipv6"]["level"] == "warn"


@pytest.mark.parametrize("tz,offset,level", [
    ("America/Los_Angeles", -420, "ok"),
    ("America/Vancouver", -420, "ok"),
    ("America/New_York", -240, "warn"),
    ("Asia/Shanghai", 480, "bad"),
    (None, 480, "warn"),                 # UTC+8 but zone unknown (could be Taipei/Singapore)
    ("Asia/Taipei", 480, "warn"),        # not China, but still mismatched with a US exit
])
def test_timezone_against_ip_consensus(tz, offset, level):
    report = make_report(clock={"timezone": tz, "offset_min": offset})
    assert by_key(report)["timezone"]["level"] == level


def test_timezone_mismatch_suggests_windows_command():
    report = make_report(clock={"timezone": "America/New_York", "offset_min": -240})
    summary = by_key(report)["timezone"]["summary"]
    assert 'tzutil /s "Pacific Standard Time"' in summary and "相差 3 小时" in summary


@pytest.mark.parametrize("band,level", [("low", "ok"), ("medium", "warn"), ("high", "bad")])
def test_fingerprint_band(band, level):
    fc = {"score": 50, "band": band,
          "signals": [{"id": "fonts", "score": 0.83, "contribution": 12, "raw": "SimSun"}]}
    finding = by_key(make_report(browser__fuckClaude=fc))["fingerprint"]
    assert finding["level"] == level and "fonts +12" in finding["summary"]


def test_ip_quality_flags():
    report = make_report(reputation={"is_datacenter": True, "company_name": "ACME"})
    report["geo"]["ip-api.com"]["flags"] = {"proxy": True, "hosting": True}
    finding = by_key(report)["ip_quality"]
    assert finding["level"] == "warn" and "机房" in finding["summary"] and "代理" in finding["summary"]
    report["reputation"]["is_abuser"] = True
    assert by_key(report)["ip_quality"]["level"] == "bad"


def test_browser_skipped_degrades_to_info():
    report = make_report(browser=None, dns__browser=None)
    items = by_key(copy.deepcopy(report))
    for key in ("webrtc", "fingerprint", "dns_browser", "browser_exit"):
        assert items[key]["level"] == "info"


# ---------------------------------------------------------------- added after review

def test_browser_not_proxied_never_reaches_claude_check():
    report = make_report(browser__neutralTrace=None, browser__claudeTrace=None)
    finding = by_key(report)["browser_exit"]
    assert finding["level"] == "bad" and "没有去访问 claude.ai" in finding["summary"]


def test_browser_exit_in_china_is_bad_without_claude_trace():
    report = make_report(browser__neutralTrace={"ip": REAL, "loc": "CN"}, browser__claudeTrace=None)
    assert by_key(report)["browser_exit"]["level"] == "bad"


def test_claude_trace_missing_after_good_preflight_warns():
    report = make_report(browser__claudeTrace=None)
    assert by_key(report)["browser_exit"]["level"] == "warn"


def test_ipv6_exit_vs_ipv4_echo_is_not_a_mismatch():
    report = make_report(browser__claudeTrace={"ip": "2001:db8::5", "loc": "US"})
    items = by_key(report)
    assert items["system_proxy"]["level"] == "info"
    assert items["exit_stability"]["level"] == "ok"


def test_ipv6_with_unknown_country_is_not_called_a_bypass():
    report = make_report(ipv6={"direct": {"reachable": False}, "browser": "2001:db8::9", "browser_geo": {}})
    assert by_key(report)["ipv6"]["level"] == "warn"


def test_ip_quality_without_data_is_info():
    report = make_report(reputation={"error": "timeout"})
    report["geo"]["ip-api.com"]["flags"] = {"proxy": None, "hosting": None}
    assert by_key(report)["ip_quality"]["level"] == "info"


def test_settings_json_source_is_reported():
    report = make_report()
    report["paths"]["env_proxy"]["source"] = "~/.claude/settings.json"
    assert "settings.json" in by_key(report)["env_proxy"]["summary"]


def test_pac_system_proxy_warns_instead_of_bad():
    report = make_report(paths__system_proxy={"proxy": None, "echo": {}}, system_proxy_pac=True)
    assert by_key(report)["system_proxy"]["level"] == "warn"


def test_linux_without_system_proxy_is_info():
    report = make_report(paths__system_proxy={"proxy": None, "echo": {}}, platform="linux")
    assert by_key(report)["system_proxy"]["level"] == "info"


def test_only_node_use_env_proxy_saved_is_not_a_saved_proxy():
    report = make_report(paths__env_proxy={"proxy": None, "echo": {},
                                           "persistent": {"User:NODE_USE_ENV_PROXY": "1"}})
    assert by_key(report)["env_proxy"]["level"] == "bad"


def test_dns_os_all_lookups_failed_is_info():
    report = make_report(dns__os={"servers": [], "lookups_ok": 0, "lookups": 6})
    assert by_key(report)["dns_os"]["level"] == "info"


def test_real_ip_is_none_under_tun_and_set_without_proxy():
    tun = make_report(paths__direct={"echo": {"ip": EXIT}})
    assert fd.real_ip(tun) is None
    assert fd.real_ip(make_report()) == REAL
    leak = make_report(browser__neutralTrace={"ip": REAL, "loc": "CN"}, browser__claudeTrace=None,
                       paths__direct={"echo": {"ip": REAL}})
    assert fd.real_ip(leak) == REAL


def test_partial_browser_data_does_not_crash():
    report = make_report(browser__fuckClaude={"score": None, "band": None, "signals": [{"id": "x", "score": None}]},
                         clock={"timezone": None, "offset_min": None})
    items = by_key(report)
    assert items["fingerprint"]["level"] == "info" and items["timezone"]["level"] == "info"
