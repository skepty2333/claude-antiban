"""Clash Verge Rev：读开关状态；改开关、DNS 覆写和前置规则，再重启 Clash 让它生效。

只用标准库。会改四个文件：verge.yaml、config.yaml（开关）、dns_config.yaml（DNS 覆写）、
当前订阅的规则文件（前置规则，见 clash_rules.py），改之前都会备份。verge.yaml 和 config.yaml
是 Clash 运行时自己会改写的，所以先停掉 Clash 再改，改完重新启动它（见 clash_app.py）。
订阅和节点不碰。不输出订阅链接和 secret。

    python clash_verge.py status [--json]                  # 开关、端口、节点数、DNS 和规则是否写入并生效
    python clash_verge.py apply --browser chrome [--dry-run]
        # 改开关、写 DNS 覆写和前置规则（专用浏览器和 Claude 程序全走节点、国内直连），重启 Clash
    python clash_verge.py verify [--json]                  # 确认 Clash 实际加载的配置已包含改动
    python clash_verge.py restore [--dry-run]              # 用最近一次备份还原，重启 Clash
    apply / restore 加 --no-restart：只改文件，不重启 Clash
    以上都可以加 --dir <Clash Verge 配置目录>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

import clash_app
from clash_rules import (BROWSERS, PREPEND_RULES, PROCESS_PREFIX, TOP_LEVEL, add_prepend_rules,  # noqa: F401
                         has_prepend_rules, in_order, match_target, merge_prepend, prepend_entries,
                         process_rules, runtime_process_first, unquote)

APP_ID = "io.github.clash-verge-rev.clash-verge-rev"
BACKUP_TAG = "before-claude-antiban"
DEFAULT_PORT = 7897

DNS_TEMPLATE = """\
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:
    - 'geosite:cn'
    - 'geosite:private'
    - '+.lan'
    - '+.local'
    - '+.msftncsi.com'
    - '+.msftconnecttest.com'
  default-nameserver:
    - 'tls://223.5.5.5'
  nameserver:
    - 'https://1.1.1.1/dns-query#RULES'
    - 'https://8.8.8.8/dns-query#RULES'
  nameserver-policy:
    'geosite:cn':
      - 'https://dns.alidns.com/dns-query'
      - 'https://doh.pub/dns-query'
  proxy-server-nameserver:
    - 'https://doh.pub/dns-query'
    - 'https://dns.alidns.com/dns-query'
"""
# 已有的 DNS 覆写同时满足这几处，就算推荐配置（用户自己加了 listen 等也不覆盖）
DNS_MARKERS = ("#RULES", "nameserver-policy:", "geosite:cn")

# (文件, 键, 目标值, 未设置时的默认值, 显示名)
SWITCHES = (
    ("verge.yaml", "enable_system_proxy", True, False, "系统代理"),
    ("verge.yaml", "enable_tun_mode", False, False, "虚拟网卡模式（TUN）"),
    ("verge.yaml", "enable_auto_launch", True, False, "开机自启"),
    ("verge.yaml", "enable_silent_start", True, False, "静默启动"),
    ("config.yaml", "ipv6", False, True, "IPv6"),
    ("config.yaml", "allow-lan", False, False, "局域网连接"),
    ("verge.yaml", "enable_dns_settings", True, False, "DNS 覆写"),
)
FIX_APPLY = "运行 clash_verge.py apply"
FIX_OS = "运行 clash_verge.py apply；还不行就请用户在 Clash「设置」页手动打开这个开关"
SETUP_MODE = "SETUP.md「三、换上你买的静态 IP」第 2 条（选节点和模式）"
ReadyCheck = Callable[[int, Path, float], bool]


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    current: str
    want: str
    ok: bool
    fix: str


# ---------------------------------------------------------------- 读文件

def find_app_dir(override: str | None, env: Mapping[str, str] = os.environ,
                 platform: str = sys.platform, home: Path | None = None) -> Path | None:
    """返回 Clash Verge Rev 的配置目录；找不到返回 None。"""
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    home = home or Path.home()
    if platform == "win32":
        base = Path(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = home / ".local" / "share"
    path = base / APP_ID
    return path if path.is_dir() else None


def _read(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def read_top_level(text: str) -> dict[str, str]:
    """只取顶层的 `key: value`，嵌套内容忽略。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = TOP_LEVEL.match(line)
        if match:
            result[match.group(1)] = unquote(match.group(2) or "")
    return result


def _profile_items(text: str) -> dict[str, dict[str, str]]:
    """profiles.yaml 的 items：uid -> {type, file, rules}。"""
    items: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        start = re.match(r"^- uid:\s*(\S+)", line)
        if start:
            current = {}
            items[unquote(start.group(1))] = current
            continue
        if current is None:
            continue
        field = re.match(r"^  (type|file):\s*(\S+)", line) or re.match(r"^    (rules):\s*(\S+)", line)
        if field:
            current[field.group(1)] = unquote(field.group(2))
    return items


def current_profile_files(app: Path) -> tuple[Path | None, Path | None]:
    """当前订阅的配置文件和它的规则文件；没有就返回 None。"""
    text = _read(app / "profiles.yaml")
    if not text:
        return None, None
    current = read_top_level(text).get("current")
    items = _profile_items(text)
    profile = items.get(current or "")
    if not profile:
        return None, None
    sub = app / "profiles" / profile["file"] if profile.get("file") else None
    rules_uid = profile.get("rules")
    rules_item = items.get(rules_uid or "", {})
    rules_name = rules_item.get("file") or (f"{rules_uid}.yaml" if rules_uid else None)
    return sub, (app / "profiles" / rules_name if rules_name else None)


def count_proxies(text: str) -> int | None:
    """订阅里顶层 proxies 列表的节点数；没有 proxies 段返回 None。"""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if re.match(r"^proxies:\s*$", line))
    except StopIteration:
        return None
    block = []
    for line in lines[start + 1:]:
        if TOP_LEVEL.match(line):
            break
        block.append(line)
    items = [re.match(r"^(\s*)-\s+\S", line) for line in block]
    indents = [m.group(1) for m in items if m]
    # 只数第一层的条目；节点内部的嵌套列表（如 alpn）缩进更深
    return sum(1 for indent in indents if indent == indents[0]) if indents else 0


def _as_bool(value: str | None) -> bool | None:
    if value is None or value in ("", "null", "~"):
        return None
    return value.lower() == "true"


# ---------------------------------------------------------------- 状态

def _switch(key: str, label: str, value: bool | None, want: bool, default: bool) -> Check:
    actual = default if value is None else value
    shown = ("开" if actual else "关") + ("（未设置，按默认）" if value is None else "")
    return Check(key, label, shown, "开" if want else "关", actual == want, FIX_APPLY)


def switch_checks(files: Mapping[str, Mapping[str, str]]) -> list[Check]:
    return [_switch(key, label, _as_bool(files[name].get(key)), want, default)
            for name, key, want, default, label in SWITCHES]


def mode_check(clash: Mapping[str, str], proxies: int | None) -> Check | None:
    if not proxies:
        return None
    want = "rule" if proxies == 1 else "global"
    current = clash.get("mode") or "rule"
    return Check("mode", f"代理模式（订阅里有 {proxies} 个节点）", current, want, current == want, SETUP_MODE)


def os_checks(os_state: Mapping[str, bool | None]) -> list[Check]:
    """Windows 里实际生效的状态：配置文件写着开，不等于系统里真的开了。"""
    labels = {"system_proxy": "系统里实际的代理设置", "autostart": "系统里登记的开机自启"}
    return [Check(f"os_{key}", labels[key], "已生效" if value else "没生效", "已生效", bool(value), FIX_OS)
            for key, value in os_state.items() if value is not None and key in labels]


def dns_template_applied(text: str | None) -> bool:
    return bool(text) and all(marker in text for marker in DNS_MARKERS)


def runtime_state(app: Path) -> dict[str, bool]:
    """Clash 实际加载的配置（clash-verge.yaml）里有没有这几处改动。"""
    text = _read(app / "clash-verge.yaml") or ""
    return {"dns": "#RULES" in text, "rules": PREPEND_RULES[0] in text, "process_first": runtime_process_first(text)}


def _port(verge: Mapping[str, str], clash: Mapping[str, str]) -> int:
    for value in (verge.get("verge_mixed_port"), clash.get("mixed-port")):
        if value and value.isdigit():
            return int(value)
    return DEFAULT_PORT


def _switch_files(app: Path) -> dict[str, dict[str, str]]:
    return {name: read_top_level(_read(app / name) or "") for name in ("verge.yaml", "config.yaml")}


def _entries(text: str | None) -> list[str]:
    try:
        return prepend_entries(text or "")
    except ValueError:
        return []


def status(app: Path, os_state: Mapping[str, bool | None] | None = None) -> dict:
    files = _switch_files(app)
    sub, rules = current_profile_files(app)
    sub_text = _read(sub)
    proxies = count_proxies(sub_text) if sub_text else None
    mode = mode_check(files["config.yaml"], proxies)
    checks = switch_checks(files) + ([mode] if mode else []) + os_checks(os_state or {})
    rules_text = _read(rules)
    return {
        "app_dir": str(app),
        "port": _port(files["verge.yaml"], files["config.yaml"]),
        "proxies": proxies,
        "checks": [asdict(c) for c in checks],
        "rules_file": rules.name if rules else None,
        "match_group": match_target(sub_text or ""),
        "dns_template": dns_template_applied(_read(app / "dns_config.yaml")),
        "prepend_rules": has_prepend_rules(rules_text),
        "process_rules": [e for e in _entries(rules_text) if e.startswith(PROCESS_PREFIX)],
        "runtime": runtime_state(app),
    }


def verify(app: Path) -> dict:
    report = status(app)
    dns_on = next(c["ok"] for c in report["checks"] if c["key"] == "enable_dns_settings")
    runtime = report["runtime"]
    return {"dns_override_on": dns_on, **runtime, "ok": dns_on and all(runtime.values())}


# ---------------------------------------------------------------- 算出要改什么

def set_top_level(text: str, key: str, value: str) -> str:
    """把顶层的 `key:` 改成 value；没有这个键就加在末尾。嵌套的同名键不动。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = TOP_LEVEL.match(line)
        if match and match.group(1) == key:
            lines[i] = f"{key}: {value}"
            return "\n".join(lines) + "\n"
    return "\n".join([*lines, f"{key}: {value}"]) + "\n"


def _switch_changes(app: Path) -> list[tuple[Path, str, str]]:
    changes = []
    for name in ("verge.yaml", "config.yaml"):
        path = app / name
        text = _read(path) or ""
        current = read_top_level(text)
        wrong = [(key, want, label) for file, key, want, default, label in SWITCHES
                 if file == name and (_as_bool(current.get(key)) if current.get(key) else default) != want]
        for key, want, _ in wrong:
            text = set_top_level(text, key, "true" if want else "false")
        if wrong:
            what = "开关（" + "、".join(f"{label}{'开' if want else '关'}" for _, want, label in wrong) + "）"
            changes.append((path, text, what))
    return changes


def _desired_rules(sub_text: str, browser: str | None, platform: str) -> tuple[list[str], list[str]]:
    group, notes = match_target(sub_text), []
    if not group or group.upper() == "DIRECT":
        notes.append("订阅里没找到兜底规则 MATCH 走的代理组，进程规则没写，只写国内直连两条；请看一下订阅的规则")
        return list(PREPEND_RULES), notes
    if not browser:
        notes.append("没指定 --browser：只给 Claude 程序写了进程规则，Claude 专用浏览器的还没写")
    return process_rules(browser, group, platform) + list(PREPEND_RULES), notes


def plan(app: Path, browser: str | None = None,
         platform: str = sys.platform) -> tuple[list[tuple[Path, str, str]], list[str]]:
    """要写的文件 (路径, 新内容, 说明)，以及不用改或改不了的说明。"""
    changes, notes = _switch_changes(app), []
    dns_path = app / "dns_config.yaml"
    if dns_template_applied(_read(dns_path)):
        notes.append("DNS 覆写已经是推荐配置")
    else:
        changes.append((dns_path, DNS_TEMPLATE, " DNS 覆写"))
    sub, rules = current_profile_files(app)
    if rules is None:
        notes.append("没找到当前订阅的规则文件（还没导入订阅，或用的是本地配置），前置规则没写；"
                     "请让用户在订阅上右键「编辑规则」手动加")
        return changes, notes
    desired, rule_notes = _desired_rules(_read(sub) or "", browser, platform)
    notes += rule_notes
    text = _read(rules) or ""
    try:
        new_text = merge_prepend(text, desired)
    except ValueError:
        notes.append(f"规则文件 {rules.name} 的格式看不懂，没改；请让用户在订阅上右键「编辑规则」手动加")
        return changes, notes
    if new_text == text:
        notes.append("前置规则已经齐了")
    else:
        changes.append((rules, new_text, "前置规则（" + "；".join(desired) + "）"))
    return changes, notes


# ---------------------------------------------------------------- 写文件、重启

def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _backup(path: Path, stamp: str) -> Path:
    target = path.with_name(f"{path.name}.{BACKUP_TAG}-{stamp}.bak")
    shutil.copy2(path, target)
    return target


def _restart(app: Path, controller: clash_app.ClashApp | None, ready: ReadyCheck,
             exe_finder: Callable[[str | None], str | None], write: Callable[[], list[str]]) -> list[str]:
    """停 Clash → 写文件 → 启动 Clash → 等它就绪。没有 controller 时只写文件。"""
    if controller is None:
        return write() + ["Clash 要重启后才会生效"]
    running = controller.running_exe()
    exe = exe_finder(running)
    if running:
        controller.stop()
    messages = write()
    if not exe:
        return messages + ["没找到 Clash Verge 程序，请用户手动打开 Clash Verge"]
    since = time.time() - 1
    controller.start(exe)
    files = _switch_files(app)
    if ready(_port(files["verge.yaml"], files["config.yaml"]), app / "clash-verge.yaml", since):
        return messages + [f"已{'重启' if running else '启动'} Clash，新配置已加载"]
    return messages + ["已启动 Clash，但没能确认它加载了新配置：请用户看一下 Clash 是否在运行，再运行 verify"]


def apply(app: Path, dry_run: bool, stamp: str | None = None, controller: clash_app.ClashApp | None = None,
          ready: ReadyCheck = clash_app.wait_ready,
          exe_finder: Callable[[str | None], str | None] = clash_app.find_exe,
          browser: str | None = None, platform: str = sys.platform) -> list[str]:
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    changes, notes = plan(app, browser, platform)
    if not changes and all(runtime_state(app).values()):
        return notes + ["都已经是推荐设置，不用改"]
    if dry_run:
        return ([f"[预演] 将写入{what}：{path}" + ("（会先备份）" if path.exists() else "")
                 for path, _, what in changes] + notes + ["[预演] 然后重启 Clash，让它加载新配置"])

    def write() -> list[str]:
        written = []
        for path, content, what in changes:
            note = f"，原文件备份为 {_backup(path, stamp).name}" if path.exists() else ""
            _write(path, content)
            written.append(f"已写入{what}：{path}{note}")
        return written

    return _restart(app, controller, ready, exe_finder, write) + notes


def restore(app: Path, dry_run: bool, controller: clash_app.ClashApp | None = None,
            ready: ReadyCheck = clash_app.wait_ready,
            exe_finder: Callable[[str | None], str | None] = clash_app.find_exe) -> list[str]:
    _, rules = current_profile_files(app)
    targets = [app / "dns_config.yaml", app / "verge.yaml", app / "config.yaml"] + ([rules] if rules else [])
    plans = [(path, sorted(path.parent.glob(f"{path.name}.{BACKUP_TAG}-*.bak"))) for path in targets]
    if dry_run:
        return [f"[预演] 将用 {b[-1].name} 还原 {p.name}" if b else f"{p.name} 没有本脚本留下的备份" for p, b in plans]

    def write() -> list[str]:
        messages = []
        for path, backups in plans:
            if not backups:
                messages.append(f"{path.name} 没有本脚本留下的备份，没动")
                continue
            shutil.copy2(backups[-1], path)
            messages.append(f"已用 {backups[-1].name} 还原 {path.name}")
        return messages

    return _restart(app, controller, ready, exe_finder, write)


# ---------------------------------------------------------------- 命令行

def _print_status(report: dict) -> None:
    print(f"Clash Verge 配置目录：{report['app_dir']}")
    print(f"代理端口：{report['port']}")
    for check in report["checks"]:
        mark = "[OK]" if check["ok"] else "[X] "
        tail = "" if check["ok"] else f"，应为{check['want']} → {check['fix']}"
        print(f"{mark} {check['label']}：{check['current']}{tail}")
    print(f"DNS 覆写内容：{'推荐配置' if report['dns_template'] else '还不是推荐配置 → 运行 apply'}")
    rules = report["rules_file"] or "（没找到当前订阅的规则文件）"
    print(f"国内直连前置规则（{rules}）：{'已写入' if report['prepend_rules'] else '未写入 → 运行 apply'}")
    process = "；".join(report["process_rules"]) or "未写入 → 运行 apply --browser <浏览器>"
    print(f"全走节点的进程规则（兜底代理组 {report['match_group'] or '未找到'}）：{process}")
    runtime = report["runtime"]
    loaded = all(runtime.values())
    print(f"Clash 实际加载的配置：{'已包含以上改动' if loaded else '还没包含 → 运行 apply（会重启 Clash）'}")


def _print_verify(result: dict) -> None:
    if result["ok"]:
        print("[OK] Clash 已加载新的 DNS 覆写、进程规则和国内直连规则，进程规则排在前面")
        return
    if not result["dns_override_on"]:
        print("[X] 「DNS 覆写」开关没开 → 运行 apply")
    missing = [name for key, name in (("dns", "DNS 覆写"), ("rules", "国内直连规则"),
                                      ("process_first", "排在国内直连前面的进程规则")) if not result[key]]
    if missing:
        print(f"[X] Clash 实际加载的配置里还没有：{'、'.join(missing)} → 运行 apply")


def _os_state(app: Path) -> dict[str, bool | None]:
    files = _switch_files(app)
    port = _port(files["verge.yaml"], files["config.yaml"])
    return {"system_proxy": clash_app.system_proxy_ok(port), "autostart": clash_app.autostart_registered()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clash Verge Rev 配置检查与修改（claude-antiban）")
    parser.add_argument("command", choices=["status", "apply", "verify", "restore"])
    parser.add_argument("--dir", help="Clash Verge 配置目录，默认按系统自动找")
    parser.add_argument("--browser", choices=sorted(BROWSERS), help="apply 用：用户专门登录 Claude 的浏览器")
    parser.add_argument("--dry-run", action="store_true", help="apply / restore 只预演，不写文件、不重启")
    parser.add_argument("--json", action="store_true", help="status / verify 输出 JSON")
    parser.add_argument("--no-restart", action="store_true", help="apply / restore 只改文件，不重启 Clash")
    args = parser.parse_args(argv)

    app = find_app_dir(args.dir)
    if app is None:
        print("没找到 Clash Verge Rev 的配置目录：用户还没装 Clash Verge Rev，或者用的是 v2rayN 等别的软件。")
        return 2
    if args.command in ("status", "verify"):
        result = status(app, _os_state(app)) if args.command == "status" else verify(app)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            (_print_status if args.command == "status" else _print_verify)(result)
        return 0 if args.command == "status" or result["ok"] else 1
    controller = None if args.dry_run or args.no_restart else clash_app.platform_app()
    if args.command == "apply":
        messages = apply(app, dry_run=args.dry_run, controller=controller, browser=args.browser)
    else:
        messages = restore(app, dry_run=args.dry_run, controller=controller)
    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
