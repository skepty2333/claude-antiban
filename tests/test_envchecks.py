"""Browser Secure DNS detection, the tiny DNS client, and the domestic-app DNS verdicts."""
from __future__ import annotations

import json
import socket
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import envchecks as ec  # noqa: E402
import findings as fd  # noqa: E402
from test_findings import by_key, make_report  # noqa: E402


# ---------------------------------------------------------------- Secure DNS detection

def write_local_state(path: Path, doh: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"browser": {}} if doh is None else {"dns_over_https": doh}
    path.write_text(json.dumps(data), encoding="utf-8")


def test_browser_secure_dns_reads_local_state(monkeypatch, tmp_path):
    chrome, edge = tmp_path / "chrome" / "Local State", tmp_path / "edge" / "Local State"
    write_local_state(chrome, {"mode": "off"})
    write_local_state(edge, None)  # key absent -> browser default (automatic)
    monkeypatch.setattr(ec, "_chromium_local_states", lambda: {"Chrome": chrome, "Edge": edge,
                                                                "Missing": tmp_path / "nope"})
    monkeypatch.setattr(ec, "_windows_policy", lambda b: None)
    monkeypatch.setattr(ec, "_firefox_trr", lambda: None)
    found = ec.browser_secure_dns()
    assert found["Chrome"]["mode"] == "off"
    assert found["Edge"]["mode"] == "automatic" and found["Edge"]["detail"] == "默认值"
    assert "Missing" not in found


def test_group_policy_overrides_user_setting(monkeypatch, tmp_path):
    chrome = tmp_path / "Local State"
    write_local_state(chrome, {"mode": "off"})
    monkeypatch.setattr(ec, "_chromium_local_states", lambda: {"Chrome": chrome})
    monkeypatch.setattr(ec, "_windows_policy", lambda b: "secure")
    monkeypatch.setattr(ec, "_firefox_trr", lambda: None)
    assert ec.browser_secure_dns()["Chrome"] == {"mode": "secure", "templates": "", "detail": "组策略"}


def test_unreadable_local_state_is_unknown(monkeypatch, tmp_path):
    chrome = tmp_path / "Local State"
    chrome.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(ec, "_chromium_local_states", lambda: {"Chrome": chrome})
    monkeypatch.setattr(ec, "_firefox_trr", lambda: None)
    assert ec.browser_secure_dns()["Chrome"]["mode"] == "unknown"


@pytest.mark.parametrize("prefs,mode", [('user_pref("network.trr.mode", 2);', "on"),
                                        ('user_pref("network.trr.mode", 5);', "off"),
                                        ("// no trr pref", "off")])
def test_firefox_trr_modes(monkeypatch, tmp_path, prefs, mode):
    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    profile = tmp_path / "Mozilla" / "Firefox" / "Profiles" / "abc.default"
    profile.mkdir(parents=True)
    (profile / "prefs.js").write_text(prefs + "\n", encoding="utf-8")
    assert ec._firefox_trr()["mode"] == mode


def test_no_firefox_profiles(monkeypatch, tmp_path):
    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert ec._firefox_trr() is None


# ---------------------------------------------------------------- tiny DNS client

def fake_dns_server(reply_ips: list[str], rcode: int = 0) -> tuple[int, threading.Thread]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))

    def serve() -> None:
        data, addr = sock.recvfrom(512)
        question = data[12:]
        header = data[:2] + bytes([0x81, 0x80 | rcode]) + b"\x00\x01" + len(reply_ips).to_bytes(2, "big") + b"\x00\x00\x00\x00"
        answers = b"".join(b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton(ip) for ip in reply_ips)
        sock.sendto(header + question + answers, addr)
        sock.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return sock.getsockname()[1], thread


@pytest.mark.parametrize("ips,rcode,status", [(["198.18.0.6"], 0, "answer"), ([], 2, "servfail"), ([], 0, "empty")])
def test_dns_query_a_parses_replies(ips, rcode, status):
    port, thread = fake_dns_server(ips, rcode)
    answer = ec.dns_query_a("www.qq.com", port=port)
    thread.join(2)
    assert answer["status"] == status and answer["ips"] == ips


def test_classify():
    assert ec.classify(["198.18.0.6"]) == "fake"
    assert ec.classify(["198.19.255.1"]) == "fake"
    assert ec.classify(["183.3.226.35"]) == "real"
    assert ec.classify([]) == "fail"


def test_domestic_probe_treats_all_silence_as_no_listener(monkeypatch):
    monkeypatch.setattr(ec, "_os_resolve", lambda name: ["1.2.3.4"])
    monkeypatch.setattr(ec, "dns_query_a", lambda name: {"status": "timeout"})
    assert ec.domestic_dns_probe() == {"os": {"www.qq.com": "real", "www.baidu.com": "real"}, "clash": {}}


def test_domestic_probe_partial_silence_is_failure(monkeypatch):
    answers = {"www.qq.com": {"status": "answer", "ips": ["198.18.0.6"]}, "www.baidu.com": {"status": "timeout"}}
    monkeypatch.setattr(ec, "_os_resolve", lambda name: ["1.2.3.4"])
    monkeypatch.setattr(ec, "dns_query_a", lambda name: answers[name])
    assert ec.domestic_dns_probe()["clash"] == {"www.qq.com": "fake", "www.baidu.com": "fail"}


# ---------------------------------------------------------------- verdicts

@pytest.mark.parametrize("data,level", [
    ({}, "info"),
    ({"Chrome": {"mode": "off"}, "Edge": {"mode": "off"}}, "ok"),
    ({"Chrome": {"mode": "off"}, "Edge": {"mode": "automatic", "detail": "默认值"}}, "warn"),
    ({"Chrome": {"mode": "unknown"}}, "ok"),
])
def test_secure_dns_verdict(data, level):
    assert by_key(make_report(secure_dns=data))["secure_dns"]["level"] == level


@pytest.mark.parametrize("os_states,clash_states,direct,level", [
    ({"a": "real"}, {}, None, "ok"),                       # no Clash DNS listener at all
    ({"a": "fake"}, {"a": "fake"}, None, "bad"),           # system DNS -> Clash fake-ip, no TUN
    ({"a": "fake"}, {"a": "fake"}, "EXIT", "ok"),          # same, but TUN routes 198.18/15
    ({"a": "fail"}, {}, None, "bad"),
    ({"a": "real"}, {"a": "fake", "b": "fail"}, None, "warn"),  # latent: #GLOBAL stuck on DIRECT
    ({"a": "real"}, {"a": "fake"}, None, "info"),
])
def test_domestic_apps_verdict(os_states, clash_states, direct, level):
    report = make_report(domestic_dns={"os": os_states, "clash": clash_states})
    if direct == "EXIT":
        report["paths"]["direct"]["echo"] = {"ip": fd.exit_ip(report)}
    assert by_key(report)["domestic_apps"]["level"] == level


def test_dns_query_a_no_listener_or_silence():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))  # bound but never answers
    port = sock.getsockname()[1]
    assert ec.dns_query_a("www.qq.com", timeout=0.5, port=port)["status"] == "timeout"
    sock.close()
    closed = ec.dns_query_a("www.qq.com", timeout=0.5, port=port)["status"]
    assert closed in ("absent", "timeout")  # Windows resets, other OSes may stay silent
