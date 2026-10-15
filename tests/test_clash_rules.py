"""Tests for scripts/setup/clash_rules.py: process rules before the China-direct rules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import clash_rules as cr  # noqa: E402

CN = list(cr.PREPEND_RULES)


def test_match_target_reads_the_last_match_rule() -> None:
    assert cr.match_target("rules:\n- DOMAIN,a.com,DIRECT\n- MATCH,PROXY\n") == "PROXY"
    assert cr.match_target("rules:\n  - 'MATCH,🐟 漏网之鱼'\n") == "🐟 漏网之鱼"
    assert cr.match_target("rules:\n- DOMAIN,a.com,DIRECT\n") is None


def test_process_rules_per_platform() -> None:
    assert cr.process_rules("chrome", "PROXY", "win32") == ["PROCESS-NAME,chrome.exe,PROXY",
                                                            "PROCESS-NAME,claude.exe,PROXY"]
    assert "PROCESS-NAME,Google Chrome Helper,PROXY" in cr.process_rules("chrome", "PROXY", "darwin")
    assert cr.process_rules(None, "PROXY", "win32") == ["PROCESS-NAME,claude.exe,PROXY"]


def test_merge_puts_process_rules_before_existing_china_rules() -> None:
    # 本机的真实情况：国内直连两条已经在了，进程规则要插到它们前面
    text = "prepend:\n- GEOSITE,cn,DIRECT\n- GEOIP,CN,DIRECT,no-resolve\n\nappend: []\n\ndelete: []\n"
    desired = cr.process_rules("edge", "PROXY", "win32") + CN
    new = cr.merge_prepend(text, desired)
    assert cr.prepend_entries(new) == desired
    assert "append: []" in new and "delete: []" in new


def test_merge_reorders_when_china_rules_came_first() -> None:
    text = "prepend:\n- GEOSITE,cn,DIRECT\n- PROCESS-NAME,claude.exe,PROXY\n- DOMAIN,x.com,DIRECT\nappend: []\n"
    desired = ["PROCESS-NAME,claude.exe,PROXY", *CN]
    entries = cr.prepend_entries(cr.merge_prepend(text, desired))
    assert entries == [*desired, "DOMAIN,x.com,DIRECT"]
    assert cr.in_order(entries, desired)


def test_merge_is_a_no_op_when_already_right() -> None:
    desired = ["PROCESS-NAME,claude.exe,PROXY", *CN]
    text = "prepend:\n" + "".join(f"- {r}\n" for r in desired) + "append: []\n"
    assert cr.merge_prepend(text, desired) == text


def test_merge_quotes_group_names_that_would_break_yaml() -> None:
    new = cr.merge_prepend("prepend: []\n", ["PROCESS-NAME,chrome.exe,a: b"])
    assert "- 'PROCESS-NAME,chrome.exe,a: b'" in new
    assert cr.prepend_entries(new) == ["PROCESS-NAME,chrome.exe,a: b"]


def test_in_order_needs_presence_and_order() -> None:
    assert not cr.in_order(["GEOSITE,cn,DIRECT"], ["PROCESS-NAME,claude.exe,PROXY", "GEOSITE,cn,DIRECT"])
    assert not cr.in_order(["GEOSITE,cn,DIRECT", "PROCESS-NAME,claude.exe,PROXY"],
                           ["PROCESS-NAME,claude.exe,PROXY", "GEOSITE,cn,DIRECT"])


def test_runtime_process_first() -> None:
    good = "proxies:\n- name: a\nrules:\n- PROCESS-NAME,chrome.exe,PROXY\n- GEOSITE,cn,DIRECT\n- MATCH,PROXY\n"
    late = "rules:\n- GEOSITE,cn,DIRECT\n- PROCESS-NAME,chrome.exe,PROXY\n"
    assert cr.runtime_process_first(good)
    assert not cr.runtime_process_first(late)
    assert not cr.runtime_process_first("rules:\n- GEOSITE,cn,DIRECT\n")
