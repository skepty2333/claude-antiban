"""Where Claude's traffic lands (clash_groups), the mode verdict built on it, and the proxy-port check."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import clash_app  # noqa: E402
import clash_groups as cg  # noqa: E402
import clash_verge as cv  # noqa: E402
from clash_rules import process_rules, unquote  # noqa: E402
from test_clash_verge import PROFILES, checks_by_key, make_app  # noqa: E402

# Clash Verge writes clash-verge.yaml with serde_yaml: block style, lists not indented under their key
RUNTIME = """\
mixed-port: 7897
proxies:
- name: VPS-1
  type: vless
- name: 'HK #2'
  type: ss
proxy-groups:
- name: PROXY
  type: select
  proxies:
  - Auto
  - VPS-1
  - DIRECT
- type: url-test
  name: Auto
  proxies:
  - VPS-1
  - 'HK #2'
- name: Inline
  type: select
  proxies: [VPS-1, DIRECT]
rules:
- MATCH,PROXY
"""


def test_proxy_groups_reads_serde_layout_any_key_order_and_inline_lists():
    groups = cg.proxy_groups(RUNTIME)
    assert groups["PROXY"] == {"name": "PROXY", "type": "select", "proxies": ["Auto", "VPS-1", "DIRECT"]}
    assert groups["Auto"]["type"] == "url-test" and groups["Auto"]["proxies"] == ["VPS-1", "HK #2"]
    assert groups["Inline"]["proxies"] == ["VPS-1", "DIRECT"]


def test_proxy_groups_handles_an_indented_list():
    text = "proxy-groups:\n  - name: G\n    type: select\n    proxies:\n      - A\n      - B\nrules: []\n"
    assert cg.proxy_groups(text)["G"]["proxies"] == ["A", "B"]


def test_selected_nodes_only_reads_the_current_profile():
    profiles = PROFILES + "- uid: Other\n  selected:\n  - name: PROXY\n    now: HK-9\n"
    assert cg.selected_nodes(profiles, "RemoteA") == {"PROXY": "VPS-1"}
    assert cg.selected_nodes(profiles, "Other") == {"PROXY": "HK-9"}
    assert cg.selected_nodes(profiles, None) is None
    assert cg.selected_nodes(profiles, "Gone") is None          # unknown profile: don't guess the defaults
    assert cg.selected_nodes("current: U\nitems:\n- uid: U\n  selected: []\n", "U") == {}


@pytest.mark.parametrize("selected,kind,chain", [
    ({"PROXY": "VPS-1"}, "node", ("PROXY", "VPS-1")),
    ({}, "auto", ("PROXY", "Auto")),                    # nothing picked: a select group uses its first entry
    ({"PROXY": "DIRECT"}, "direct", ("PROXY", "DIRECT")),
])
def test_resolve_follows_the_users_picks(selected, kind, chain):
    route = cg.resolve("PROXY", cg.proxy_groups(RUNTIME), selected)
    assert (route.kind, route.chain) == (kind, chain)


def test_stale_pick_falls_back_to_the_first_entry_and_says_so():
    groups = cg.proxy_groups("proxy-groups:\n- name: PROXY\n  type: select\n  proxies:\n  - DIRECT\n  - VPS-1\n")
    route = cg.resolve("PROXY", groups, {"PROXY": "VPS-old-84GB"})  # renamed by a subscription refresh
    assert (route.kind, route.chain, route.stale) == ("direct", ("PROXY", "DIRECT"), ("VPS-old-84GB",))
    check = cv.mode_check({"mode": "rule"}, 1, route)
    assert not check.ok and "VPS-old-84GB" in check.current and "真实 IP" in check.fix


def test_stale_pick_onto_a_node_is_ok_but_still_reported():
    groups = cg.proxy_groups("proxy-groups:\n- name: PROXY\n  type: select\n  proxies:\n  - VPS-1\n  - DIRECT\n")
    check = cv.mode_check({"mode": "rule"}, 1, cg.resolve("PROXY", groups, {"PROXY": "VPS-old"}))
    assert check.ok and "VPS-old" in check.current and "PROXY → VPS-1" in check.current


def test_pick_outside_a_provider_group_is_trusted():
    text = "proxy-groups:\n- name: P\n  type: select\n  use:\n  - provider1\n  proxies:\n  - DIRECT\n"
    route = cg.resolve("P", cg.proxy_groups(text), {"P": "node-from-provider"})
    assert route.kind == "node" and not route.stale


def test_resolve_gives_up_on_loops_and_unknown_group_types():
    loop = "proxy-groups:\n- name: A\n  type: select\n  proxies:\n  - B\n- name: B\n  type: select\n  proxies:\n  - A\n"
    assert cg.resolve("A", cg.proxy_groups(loop), {}).kind == "unknown"
    relay = "proxy-groups:\n- name: R\n  type: relay\n  proxies:\n  - VPS-1\n"
    assert cg.resolve("R", cg.proxy_groups(relay), {}).kind == "unknown"


def test_runtime_target_prefers_the_claude_process_rule():
    runtime = RUNTIME.replace("rules:\n- MATCH,PROXY\n", "rules:\n- PROCESS-NAME,claude.exe,Inline\n- MATCH,PROXY\n")
    assert cg.runtime_target(runtime) == "Inline"
    assert cg.runtime_target(RUNTIME) == "PROXY"
    route = cg.claude_route("rule", "PROXY", runtime, PROFILES, "RemoteA")
    assert route.chain == ("Inline", "VPS-1")


def test_claude_route_in_global_mode_starts_at_global():
    profiles = "current: U\nitems:\n- uid: U\n  selected:\n  - name: GLOBAL\n    now: VPS-1\n"
    route = cg.claude_route("global", "PROXY", RUNTIME, profiles, "U")
    assert route.kind == "node" and route.chain == ("GLOBAL", "VPS-1")
    assert cg.claude_route("global", "PROXY", RUNTIME, "", None) is None  # GLOBAL never picked: unknown
    assert cg.claude_route("rule", "PROXY", "", PROFILES, "RemoteA") is None  # no runtime config yet


def test_unquote_keeps_a_hash_inside_quotes():
    assert unquote("'HK #2'") == "HK #2"
    assert unquote("'it''s'") == "it's"
    assert unquote("VPS-1  # comment") == "VPS-1"


# ---------------------------------------------------------------- mode verdict in status

def test_rule_mode_with_several_nodes_is_fine_when_claude_lands_on_a_fixed_node(tmp_path):
    profiles = PROFILES  # RemoteA picked PROXY -> VPS-1
    app = make_app(tmp_path, profiles=profiles, runtime=RUNTIME, sub=RUNTIME)
    report = cv.status(app)
    check = checks_by_key(report)["mode"]
    assert check["ok"] and "PROXY → VPS-1" in check["current"]
    assert report["claude_route"] == {"kind": "node", "chain": ["PROXY", "VPS-1"]}


def test_rule_mode_landing_on_an_auto_group_is_flagged(tmp_path):
    app = make_app(tmp_path, profiles=PROFILES.replace("now: VPS-1", "now: Auto"), runtime=RUNTIME, sub=RUNTIME)
    check = checks_by_key(cv.status(app))["mode"]
    assert not check["ok"] and "「PROXY」选成静态 IP 节点" in check["fix"] and "会跳" in check["fix"]


def test_picking_direct_is_flagged_as_real_ip(tmp_path):
    app = make_app(tmp_path, profiles=PROFILES.replace("now: VPS-1", "now: DIRECT"), runtime=RUNTIME, sub=RUNTIME)
    check = checks_by_key(cv.status(app))["mode"]
    assert not check["ok"] and "真实 IP" in check["fix"]


@pytest.mark.parametrize("mode,proxies,ok", [("rule", 1, True), ("global", 1, True), ("rule", 3, False),
                                             ("global", 3, True), ("direct", 1, False)])
def test_mode_fallback_by_node_count_when_route_is_unknown(mode, proxies, ok):
    check = cv.mode_check({"mode": mode}, proxies, None)
    assert check.ok is ok


# ---------------------------------------------------------------- proxy port

@pytest.mark.parametrize("listeners,ok", [
    (["verge-mihomo"], True),
    (["clash-verge-service", "verge-mihomo"], True),
    (["verge-mihomo", "com.vortex.helper"], False),   # another proxy app shares the port
    ([], False),                                       # nothing listening
])
def test_port_check(listeners, ok):
    check = cv.port_check(7897, listeners)
    assert check.ok is ok
    if listeners and not ok:
        assert "com.vortex.helper" in check.current and "退出或卸载" in check.fix


@pytest.mark.parametrize("returncode,stdout,expected", [
    (0, "verge-mihomo\r\nv2rayN\r\n", ["verge-mihomo", "v2rayN"]),
    (0, "", []),
    (1, "", None),                       # blocked or failed: unknown, not "nothing is listening"
])
def test_port_listeners_reads_powershell(monkeypatch, returncode, stdout, expected):
    monkeypatch.setattr(clash_app.sys, "platform", "win32")
    monkeypatch.setattr(clash_app.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": returncode, "stdout": stdout})())
    assert clash_app.port_listeners(7897) == expected


def test_port_listeners_timeout_is_unknown(monkeypatch):
    monkeypatch.setattr(clash_app.sys, "platform", "win32")

    def boom(*a, **k):
        raise clash_app.subprocess.TimeoutExpired("powershell", 30)

    monkeypatch.setattr(clash_app.subprocess, "run", boom)
    assert clash_app.port_listeners(7897) is None


def test_port_check_skipped_when_unknown(tmp_path):
    assert cv.port_check(7897, None) is None
    report = cv.status(make_app(tmp_path), os_state={"port_listeners": ["verge-mihomo", "other"]})
    assert not checks_by_key(report)["port_owner"]["ok"]


def test_foreign_listeners_and_autostart_path_match():
    # another Clash-family client (Mihomo Party's mihomo) on the same port is exactly what to catch
    assert clash_app.foreign_listeners(["verge-mihomo", "verge-mihomo.exe", "mihomo", "v2rayN"]) == ["mihomo", "v2rayN"]
    assert clash_app._is_clash_path(r"C:\Program Files\Clash Verge\Clash Verge.exe")
    assert not clash_app._is_clash_path(r"C:\x\v2rayN.exe")


# ---------------------------------------------------------------- two browsers

def test_process_rules_for_two_browsers_keep_order_and_no_duplicates():
    assert process_rules(["chrome", "edge", "chrome"], "PROXY", "win32") == [
        "PROCESS-NAME,chrome.exe,PROXY", "PROCESS-NAME,msedge.exe,PROXY", "PROCESS-NAME,claude.exe,PROXY"]
    assert process_rules("firefox", "PROXY", "win32")[0] == "PROCESS-NAME,firefox.exe,PROXY"


def test_main_apply_accepts_two_browsers(tmp_path, capsys):
    app = make_app(tmp_path)
    assert cv.main(["apply", "--dir", str(app), "--browser", "chrome", "edge", "--no-restart"]) == 0
    rules = cv.prepend_entries((app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8"))
    if sys.platform == "win32":
        assert rules[:3] == ["PROCESS-NAME,chrome.exe,PROXY", "PROCESS-NAME,msedge.exe,PROXY",
                             "PROCESS-NAME,claude.exe,PROXY"]
