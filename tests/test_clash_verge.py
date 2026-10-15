"""Tests for scripts/setup/clash_verge.py, run against a fake Clash Verge Rev app directory."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import clash_verge as cv  # noqa: E402

SECRET_URL = "https://sub.example.com/api/v1/client/subscribe?token=SECRET123"

VERGE_GOOD = """\
enable_tun_mode: false
enable_auto_launch: true
enable_silent_start: true
enable_system_proxy: true
enable_dns_settings: true
verge_mixed_port: 7897
"""

CONFIG_GOOD = """\
mixed-port: 7897
allow-lan: false
ipv6: false
mode: rule
external-controller: 127.0.0.1:9097
secret: 'do-not-print'
tun:
  enable: false
"""

PROFILES = f"""\
# Profiles Config for Clash Verge

current: RemoteA
items:
- uid: Merge
  type: merge
  name: null
  file: Merge.yaml
- uid: rRules01
  type: rules
  name: null
  file: rRules01.yaml
- uid: RemoteA
  type: remote
  name: my-sub
  file: RemoteA.yaml
  url: {SECRET_URL}
  selected:
  - name: PROXY
    now: VPS-1
  option:
    update_interval: 1440
    merge: mMerge01
    rules: rRules01
"""

RULES_EMPTY = """\
# Profile Enhancement Rules Template for Clash Verge

prepend: []

append: []

delete: []
"""

ONE_PROXY = """\
mixed-port: 7890
proxies:
- name: VPS-1
  type: vless
  server: 203.0.113.5
proxy-groups:
- name: PROXY
  type: select
  proxies:
  - VPS-1
rules:
- MATCH,PROXY
"""

THREE_PROXIES = """\
proxies:
  - {name: HK-1, type: ss, server: a.example}
  - {name: JP-1, type: ss, server: b.example}
  - name: US-1
    type: vmess
proxy-groups:
  - name: Auto
    type: url-test
    proxies: [HK-1, JP-1, US-1]
"""

RUNTIME_DONE = """\
mixed-port: 7897
dns:
  enable: true
  nameserver:
  - https://1.1.1.1/dns-query#RULES
rules:
- PROCESS-NAME,claude.exe,PROXY
- GEOSITE,cn,DIRECT
- GEOIP,CN,DIRECT,no-resolve
- MATCH,PROXY
"""


def make_app(tmp_path: Path, *, verge: str = VERGE_GOOD, config: str = CONFIG_GOOD,
             profiles: str | None = PROFILES, rules: str | None = RULES_EMPTY,
             sub: str | None = ONE_PROXY, runtime: str | None = None,
             dns: str | None = None) -> Path:
    app = tmp_path / cv.APP_ID
    (app / "profiles").mkdir(parents=True)
    (app / "verge.yaml").write_text(verge, encoding="utf-8")
    (app / "config.yaml").write_text(config, encoding="utf-8")
    if profiles is not None:
        (app / "profiles.yaml").write_text(profiles, encoding="utf-8")
    if rules is not None:
        (app / "profiles" / "rRules01.yaml").write_text(rules, encoding="utf-8")
    if sub is not None:
        (app / "profiles" / "RemoteA.yaml").write_text(sub, encoding="utf-8")
    if runtime is not None:
        (app / "clash-verge.yaml").write_text(runtime, encoding="utf-8")
    if dns is not None:
        (app / "dns_config.yaml").write_text(dns, encoding="utf-8")
    return app


def checks_by_key(report: dict) -> dict:
    return {c["key"]: c for c in report["checks"]}


# ---------------------------------------------------------------- locating and parsing

def test_find_app_dir_uses_override_then_platform_default(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assert cv.find_app_dir(str(app)) == app
    assert cv.find_app_dir(None, env={"APPDATA": str(tmp_path)}, platform="win32", home=tmp_path) == app
    assert cv.find_app_dir(None, env={}, platform="win32", home=tmp_path / "nowhere") is None


def test_read_top_level_strips_quotes_and_ignores_nested_keys() -> None:
    parsed = cv.read_top_level("a: 'x'\nb: \"y\" # note\nc:\n  d: nested\nmode: rule\n")
    assert parsed == {"a": "x", "b": "y", "c": "", "mode": "rule"}


def test_current_profile_files_follow_the_rules_option(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    sub, rules = cv.current_profile_files(app)
    assert sub == app / "profiles" / "RemoteA.yaml"
    assert rules == app / "profiles" / "rRules01.yaml"


def test_current_profile_files_without_profiles_yaml(tmp_path: Path) -> None:
    app = make_app(tmp_path, profiles=None)
    assert cv.current_profile_files(app) == (None, None)


NESTED_FIRST_KEY = """\
proxies:
- client-fingerprint: chrome
  flow: xtls-rprx-vision
  name: VPS-1
  alpn:
  - h2
  - http/1.1
- name: VPS-2
  type: ss
proxy-groups: []
"""


@pytest.mark.parametrize("text, expected", [
    (ONE_PROXY, 1), (THREE_PROXIES, 3), (NESTED_FIRST_KEY, 2), ("proxies:\nrules: []\n", 0), ("rules: []\n", None),
])
def test_count_proxies(text: str, expected: int | None) -> None:
    assert cv.count_proxies(text) == expected


# ---------------------------------------------------------------- status

def test_status_all_switches_ok(tmp_path: Path) -> None:
    report = cv.status(make_app(tmp_path))
    assert report["port"] == 7897
    assert all(c["ok"] for c in report["checks"]), report["checks"]
    assert report["proxies"] == 1


def test_status_flags_wrong_switches_and_points_to_setup(tmp_path: Path) -> None:
    verge = VERGE_GOOD.replace("enable_tun_mode: false", "enable_tun_mode: true").replace(
        "enable_auto_launch: true\n", "")
    config = CONFIG_GOOD.replace("ipv6: false", "ipv6: true")
    checks = checks_by_key(cv.status(make_app(tmp_path, verge=verge, config=config)))
    assert not checks["enable_tun_mode"]["ok"]
    assert not checks["enable_auto_launch"]["ok"]  # missing key means the switch was never turned on
    assert not checks["ipv6"]["ok"]
    assert checks["enable_system_proxy"]["ok"]
    assert "apply" in checks["enable_tun_mode"]["fix"]  # 开关由 AI 改，不再让用户去点


def test_status_missing_ipv6_key_counts_as_on(tmp_path: Path) -> None:
    checks = checks_by_key(cv.status(make_app(tmp_path, config=CONFIG_GOOD.replace("ipv6: false\n", ""))))
    assert not checks["ipv6"]["ok"]


def test_status_recommends_global_mode_for_several_nodes(tmp_path: Path) -> None:
    checks = checks_by_key(cv.status(make_app(tmp_path, sub=THREE_PROXIES)))
    assert checks["mode"]["want"] == "global"
    assert not checks["mode"]["ok"]


def test_status_skips_mode_check_when_node_count_unknown(tmp_path: Path) -> None:
    assert "mode" not in checks_by_key(cv.status(make_app(tmp_path, sub=None)))


def test_status_reports_pending_dns_and_rules(tmp_path: Path) -> None:
    report = cv.status(make_app(tmp_path))
    assert report["dns_template"] is False
    assert report["prepend_rules"] is False
    assert report["runtime"] == {"dns": False, "rules": False, "process_first": False}


def test_status_never_leaks_subscription_url_or_secret(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    app = make_app(tmp_path)
    assert cv.main(["status", "--dir", str(app), "--json"]) == 0
    assert cv.main(["status", "--dir", str(app)]) == 0
    out = capsys.readouterr().out
    assert "SECRET123" not in out and "do-not-print" not in out


def test_main_reports_missing_app_dir(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert cv.main(["status", "--dir", str(tmp_path / "missing")]) == 2
    assert "没找到" in capsys.readouterr().out


# ---------------------------------------------------------------- prepend rules

def test_add_prepend_rules_to_empty_inline_list() -> None:
    new = cv.add_prepend_rules(RULES_EMPTY)
    assert cv.prepend_entries(new) == list(cv.PREPEND_RULES)
    assert "append: []" in new and "delete: []" in new


def test_add_prepend_rules_keeps_existing_entries_after_ours() -> None:
    text = "prepend:\n- DOMAIN,example.com,DIRECT\n\nappend: []\n"
    new = cv.add_prepend_rules(text)
    assert cv.prepend_entries(new) == [*cv.PREPEND_RULES, "DOMAIN,example.com,DIRECT"]


def test_add_prepend_rules_only_adds_missing_one() -> None:
    text = "prepend:\n  - 'GEOSITE,cn,DIRECT'\nappend: []\n"
    new = cv.add_prepend_rules(text)
    assert cv.prepend_entries(new) == list(cv.PREPEND_RULES)
    assert "\n  - GEOIP,CN,DIRECT,no-resolve\n" in new  # 和原有条目同样缩进，否则 YAML 解析失败


def test_add_prepend_rules_creates_file_content_from_nothing() -> None:
    assert cv.prepend_entries(cv.add_prepend_rules("")) == list(cv.PREPEND_RULES)


def test_add_prepend_rules_rejects_inline_lists_it_cannot_parse() -> None:
    with pytest.raises(ValueError):
        cv.add_prepend_rules("prepend: ['DOMAIN,a.com,DIRECT']\n")


# ---------------------------------------------------------------- apply / verify / restore

def test_apply_dry_run_writes_nothing(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    before = (app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8")
    messages = cv.apply(app, dry_run=True, stamp="20260101-000000")
    assert messages
    assert not (app / "dns_config.yaml").exists()
    assert (app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8") == before


def test_apply_writes_dns_and_rules_with_backups(tmp_path: Path) -> None:
    app = make_app(tmp_path, dns="dns:\n  enable: true\n  nameserver:\n  - https://8.8.8.8/dns-query#GLOBAL\n")
    cv.apply(app, dry_run=False, stamp="20260101-000000", platform="win32")
    dns = (app / "dns_config.yaml").read_text(encoding="utf-8")
    assert dns == cv.DNS_TEMPLATE
    assert (app / "dns_config.yaml.before-claude-antiban-20260101-000000.bak").exists()
    rules = (app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8")
    assert cv.prepend_entries(rules) == ["PROCESS-NAME,claude.exe,PROXY", *cv.PREPEND_RULES]
    assert (app / "profiles" / "rRules01.yaml.before-claude-antiban-20260101-000000.bak").exists()
    report = cv.status(app)
    assert report["dns_template"] and report["prepend_rules"]


def test_apply_is_idempotent(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    cv.apply(app, dry_run=False, stamp="20260101-000000")
    cv.apply(app, dry_run=False, stamp="20260101-000001")
    assert not list(app.rglob("*20260101-000001.bak"))


def test_apply_keeps_a_custom_dns_config_that_already_matches(tmp_path: Path) -> None:
    custom = cv.DNS_TEMPLATE.replace("  enable: true\n", "  enable: true\n  listen: :53\n")
    app = make_app(tmp_path, dns=custom)
    cv.apply(app, dry_run=False, stamp="20260101-000000")
    assert (app / "dns_config.yaml").read_text(encoding="utf-8") == custom


def test_apply_without_rules_file_still_writes_dns(tmp_path: Path) -> None:
    app = make_app(tmp_path, profiles=None)
    messages = cv.apply(app, dry_run=False, stamp="20260101-000000")
    assert (app / "dns_config.yaml").exists()
    assert any("规则文件" in m for m in messages)


def test_verify_needs_runtime_to_contain_both(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assert cv.verify(app)["ok"] is False
    (app / "clash-verge.yaml").write_text(RUNTIME_DONE, encoding="utf-8")
    assert cv.verify(app)["ok"] is True


def test_verify_fails_when_dns_override_is_off(tmp_path: Path) -> None:
    verge = VERGE_GOOD.replace("enable_dns_settings: true", "enable_dns_settings: false")
    assert cv.verify(make_app(tmp_path, verge=verge, runtime=RUNTIME_DONE))["ok"] is False


def test_restore_puts_back_the_latest_backup(tmp_path: Path) -> None:
    original = "dns:\n  enable: true\n"
    app = make_app(tmp_path, dns=original)
    cv.apply(app, dry_run=False, stamp="20260101-000000")
    cv.restore(app, dry_run=False)
    assert (app / "dns_config.yaml").read_text(encoding="utf-8") == original
    assert cv.prepend_entries((app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8")) == []


def test_main_apply_and_verify_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    app = make_app(tmp_path)
    assert cv.main(["apply", "--dir", str(app), "--dry-run"]) == 0
    assert cv.main(["verify", "--dir", str(app)]) == 1
    (app / "clash-verge.yaml").write_text(RUNTIME_DONE, encoding="utf-8")
    assert cv.main(["verify", "--dir", str(app), "--json"]) == 0
    payload = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(payload)["ok"] is True


# ---------------------------------------------------------------- switches and restart

class FakeApp:
    """Records stop/start and what verge.yaml looked like when Clash was stopped."""

    def __init__(self, app: Path, running: str | None = "C:/Clash Verge/clash-verge.exe") -> None:
        self.app, self.running, self.events = app, running, []
        self.verge_at_stop: str | None = None

    def running_exe(self) -> str | None:
        return self.running

    def stop(self) -> None:
        self.events.append("stop")
        self.verge_at_stop = (self.app / "verge.yaml").read_text(encoding="utf-8")
        self.running = None

    def start(self, exe: str) -> None:
        self.events.append(f"start {exe}")
        (self.app / "clash-verge.yaml").write_text(RUNTIME_DONE, encoding="utf-8")


def always_ready(port, runtime, since):
    return True


def test_set_top_level_replaces_or_appends() -> None:
    text = "a: 1\nenable_tun_mode: true\nnested:\n  enable_tun_mode: true\n"
    new = cv.set_top_level(text, "enable_tun_mode", "false")
    assert "enable_tun_mode: false\nnested:\n  enable_tun_mode: true\n" in new
    assert cv.set_top_level("a: 1\n", "ipv6", "false") == "a: 1\nipv6: false\n"
    assert cv.set_top_level("a: 1", "ipv6", "false") == "a: 1\nipv6: false\n"


def test_apply_stops_clash_before_touching_its_files_then_restarts(tmp_path: Path) -> None:
    verge = VERGE_GOOD.replace("enable_tun_mode: false", "enable_tun_mode: true")
    app = make_app(tmp_path, verge=verge, config=CONFIG_GOOD.replace("ipv6: false", "ipv6: true"))
    fake = FakeApp(app)
    cv.apply(app, dry_run=False, stamp="s", controller=fake, ready=always_ready)
    assert fake.events == ["stop", "start C:/Clash Verge/clash-verge.exe"]
    assert "enable_tun_mode: true" in fake.verge_at_stop  # 停下时还没改
    report = cv.status(app)
    assert all(c["ok"] for c in report["checks"]), report["checks"]
    assert (app / "verge.yaml.before-claude-antiban-s.bak").exists()
    assert (app / "config.yaml.before-claude-antiban-s.bak").exists()


def test_apply_starts_an_installed_clash_that_was_not_running(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    fake = FakeApp(app, running=None)
    messages = cv.apply(app, dry_run=False, stamp="s", controller=fake, ready=always_ready,
                        exe_finder=lambda running: "D:/Program Files/Clash Verge/clash-verge.exe")
    assert fake.events == ["start D:/Program Files/Clash Verge/clash-verge.exe"]
    assert any("已重启" in m or "已启动" in m for m in messages)


def test_apply_dry_run_touches_neither_files_nor_clash(tmp_path: Path) -> None:
    app = make_app(tmp_path, verge=VERGE_GOOD.replace("enable_tun_mode: false", "enable_tun_mode: true"))
    fake = FakeApp(app)
    messages = cv.apply(app, dry_run=True, stamp="s", controller=fake, ready=always_ready)
    assert fake.events == [] and "enable_tun_mode: true" in (app / "verge.yaml").read_text(encoding="utf-8")
    assert any("TUN" in m for m in messages) and any("重启" in m for m in messages)


def test_apply_with_everything_in_place_does_not_restart(tmp_path: Path) -> None:
    app = make_app(tmp_path, runtime=RUNTIME_DONE)
    cv.apply(app, dry_run=False, stamp="s", controller=FakeApp(app), ready=always_ready)
    fake = FakeApp(app)
    messages = cv.apply(app, dry_run=False, stamp="t", controller=fake, ready=always_ready)
    assert fake.events == [] and any("不用改" in m for m in messages)


def test_apply_reports_when_clash_does_not_come_back(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    messages = cv.apply(app, dry_run=False, stamp="s", controller=FakeApp(app),
                        ready=lambda port, runtime, since: False)
    assert any("没能确认" in m for m in messages)


def test_restore_puts_switch_files_back_and_restarts(tmp_path: Path) -> None:
    verge = VERGE_GOOD.replace("enable_tun_mode: false", "enable_tun_mode: true")
    app = make_app(tmp_path, verge=verge)
    cv.apply(app, dry_run=False, stamp="s", controller=FakeApp(app), ready=always_ready)
    fake = FakeApp(app)
    cv.restore(app, dry_run=False, controller=fake, ready=always_ready)
    assert "enable_tun_mode: true" in (app / "verge.yaml").read_text(encoding="utf-8")
    assert fake.events[0] == "stop" and fake.events[-1].startswith("start")


def test_apply_with_browser_routes_it_and_claude_through_the_match_group(tmp_path: Path) -> None:
    app = make_app(tmp_path, rules="prepend:\n- GEOSITE,cn,DIRECT\n- GEOIP,CN,DIRECT,no-resolve\nappend: []\n")
    cv.apply(app, dry_run=False, stamp="s", browser="chrome", platform="win32")
    entries = cv.prepend_entries((app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8"))
    assert entries == ["PROCESS-NAME,chrome.exe,PROXY", "PROCESS-NAME,claude.exe,PROXY", *cv.PREPEND_RULES]
    assert cv.status(app)["process_rules"] == entries[:2]


def test_apply_without_match_group_only_writes_china_rules(tmp_path: Path) -> None:
    app = make_app(tmp_path, sub=THREE_PROXIES)  # 这个订阅没有 MATCH 规则
    messages = cv.apply(app, dry_run=False, stamp="s", browser="chrome", platform="win32")
    entries = cv.prepend_entries((app / "profiles" / "rRules01.yaml").read_text(encoding="utf-8"))
    assert entries == list(cv.PREPEND_RULES)
    assert any("MATCH" in m for m in messages)


def test_verify_needs_the_process_rule_before_china_rules(tmp_path: Path) -> None:
    late = RUNTIME_DONE.replace("- PROCESS-NAME,claude.exe,PROXY\n", "") + "- PROCESS-NAME,claude.exe,PROXY\n"
    assert cv.verify(make_app(tmp_path, runtime=late))["ok"] is False


def test_status_adds_what_windows_actually_has(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    checks = checks_by_key(cv.status(app, os_state={"system_proxy": False, "autostart": True}))
    assert not checks["os_system_proxy"]["ok"] and checks["os_autostart"]["ok"]
    assert "os_system_proxy" not in checks_by_key(cv.status(app))
