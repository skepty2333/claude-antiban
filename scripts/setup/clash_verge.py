"""Clash Verge Rev：读开关状态、写 DNS 覆写和国内直连前置规则、确认 Clash 已加载。

只用标准库。只改两个文件：dns_config.yaml 和当前订阅的规则文件，改之前都会备份。
verge.yaml、config.yaml 由 Clash 运行时自己改写，这里只读不写，那些开关交给用户在界面上点。
不输出订阅链接和 secret。

    python clash_verge.py status [--json]        # 各开关对不对、端口、节点数、DNS 和规则是否已写入并生效
    python clash_verge.py apply [--dry-run]      # 写入 DNS 覆写模板和两条前置规则
    python clash_verge.py verify [--json]        # 用户切过「DNS 覆写」后，确认 Clash 实际加载的配置已包含改动
    python clash_verge.py restore [--dry-run]    # 用最近一次备份还原
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
from typing import Mapping

APP_ID = "io.github.clash-verge-rev.clash-verge-rev"
BACKUP_TAG = "before-claude-antiban"
PREPEND_RULES = ("GEOSITE,cn,DIRECT", "GEOIP,CN,DIRECT,no-resolve")
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
RULES_SKELETON = "# Profile Enhancement Rules Template for Clash Verge\n\nprepend: []\n\nappend: []\n\ndelete: []\n"

SETUP_SWITCHES = "SETUP.md「一、先让代理跑起来」第 4 条（设置页的开关）"
SETUP_MODE = "SETUP.md「一、先让代理跑起来」第 3 条（选节点和模式）"
SETUP_RELOAD = "SETUP.md「二、让 Clash 重新加载配置」"

TOP_LEVEL = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*?))?\s*$")
LIST_ITEM = re.compile(r"^\s*-\s+(.*?)\s*$")


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


def _unquote(value: str) -> str:
    value = re.sub(r"\s+#.*$", "", value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def read_top_level(text: str) -> dict[str, str]:
    """只取顶层的 `key: value`，嵌套内容忽略。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = TOP_LEVEL.match(line)
        if match:
            result[match.group(1)] = _unquote(match.group(2) or "")
    return result


def _profile_items(text: str) -> dict[str, dict[str, str]]:
    """profiles.yaml 的 items：uid -> {type, file, rules}。"""
    items: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        start = re.match(r"^- uid:\s*(\S+)", line)
        if start:
            current = {}
            items[_unquote(start.group(1))] = current
            continue
        if current is None:
            continue
        field = re.match(r"^  (type|file):\s*(\S+)", line) or re.match(r"^    (rules):\s*(\S+)", line)
        if field:
            current[field.group(1)] = _unquote(field.group(2))
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

def _switch(key: str, label: str, value: bool | None, want: bool, default: bool, fix: str) -> Check:
    actual = default if value is None else value
    shown = ("开" if actual else "关") + ("（未设置，按默认）" if value is None else "")
    return Check(key, label, shown, "开" if want else "关", actual == want, fix)


def switch_checks(verge: Mapping[str, str], clash: Mapping[str, str]) -> list[Check]:
    v, c = verge.get, clash.get
    return [
        _switch("enable_system_proxy", "系统代理", _as_bool(v("enable_system_proxy")), True, False, SETUP_SWITCHES),
        _switch("enable_tun_mode", "虚拟网卡模式（TUN）", _as_bool(v("enable_tun_mode")), False, False, SETUP_SWITCHES),
        _switch("enable_auto_launch", "开机自启", _as_bool(v("enable_auto_launch")), True, False, SETUP_SWITCHES),
        _switch("enable_silent_start", "静默启动", _as_bool(v("enable_silent_start")), True, False, SETUP_SWITCHES),
        _switch("ipv6", "IPv6", _as_bool(c("ipv6")), False, True, SETUP_SWITCHES),
        _switch("allow-lan", "局域网连接", _as_bool(c("allow-lan")), False, False, SETUP_SWITCHES),
        _switch("enable_dns_settings", "DNS 覆写", _as_bool(v("enable_dns_settings")), True, False, SETUP_RELOAD),
    ]


def mode_check(clash: Mapping[str, str], proxies: int | None) -> Check | None:
    if not proxies:
        return None
    want = "rule" if proxies == 1 else "global"
    current = clash.get("mode") or "rule"
    return Check("mode", f"代理模式（订阅里有 {proxies} 个节点）", current, want, current == want, SETUP_MODE)


def prepend_entries(text: str) -> list[str]:
    """规则文件里 prepend 的条目；没有 prepend 返回空列表，看不懂的行内列表抛 ValueError。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^prepend:\s*(.*?)\s*$", line)
        if not match:
            continue
        inline = match.group(1)
        if inline in ("[]", ""):
            return [] if inline == "[]" else _block_items(lines[i + 1:])
        raise ValueError("prepend 写成了行内列表")
    return []


def _block_items(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        if not line.strip():
            continue
        item = LIST_ITEM.match(line)
        if not item:
            break
        items.append(_unquote(item.group(1)))
    return items


def has_prepend_rules(text: str | None) -> bool:
    try:
        entries = prepend_entries(text or "")
    except ValueError:
        return False
    return all(rule in entries for rule in PREPEND_RULES)


def dns_template_applied(text: str | None) -> bool:
    return bool(text) and all(marker in text for marker in DNS_MARKERS)


def runtime_state(app: Path) -> dict[str, bool]:
    """Clash 实际加载的配置（clash-verge.yaml）里有没有这两处改动。"""
    text = _read(app / "clash-verge.yaml") or ""
    return {"dns": "#RULES" in text, "rules": PREPEND_RULES[0] in text}


def _port(verge: Mapping[str, str], clash: Mapping[str, str]) -> int:
    for value in (verge.get("verge_mixed_port"), clash.get("mixed-port")):
        if value and value.isdigit():
            return int(value)
    return DEFAULT_PORT


def status(app: Path) -> dict:
    verge = read_top_level(_read(app / "verge.yaml") or "")
    clash = read_top_level(_read(app / "config.yaml") or "")
    sub, rules = current_profile_files(app)
    sub_text = _read(sub)
    proxies = count_proxies(sub_text) if sub_text else None
    checks = switch_checks(verge, clash)
    mode = mode_check(clash, proxies)
    return {
        "app_dir": str(app),
        "port": _port(verge, clash),
        "proxies": proxies,
        "checks": [asdict(c) for c in checks + ([mode] if mode else [])],
        "rules_file": rules.name if rules else None,
        "dns_template": dns_template_applied(_read(app / "dns_config.yaml")),
        "prepend_rules": has_prepend_rules(_read(rules)),
        "runtime": runtime_state(app),
    }


def verify(app: Path) -> dict:
    report = status(app)
    dns_on = next(c["ok"] for c in report["checks"] if c["key"] == "enable_dns_settings")
    runtime = report["runtime"]
    return {"dns_override_on": dns_on, **runtime, "ok": dns_on and runtime["dns"] and runtime["rules"]}


# ---------------------------------------------------------------- 写文件

def add_prepend_rules(text: str) -> str:
    """把缺的前置规则加到 prepend 最前面，原有条目保留在后面。"""
    if not text.strip():
        text = RULES_SKELETON
    entries = prepend_entries(text)  # 看不懂的格式在这里抛 ValueError
    missing = [rule for rule in PREPEND_RULES if rule not in entries]
    if not missing:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^prepend:", line):
            indent = _item_indent(lines[i + 1:]) if entries else ""  # 同一列表的缩进必须一致
            lines[i:i + 1] = ["prepend:", *(f"{indent}- {rule}" for rule in missing)]
            return "\n".join(lines) + "\n"
    return "\n".join(["prepend:", *(f"- {rule}" for rule in missing), *lines]) + "\n"


def _item_indent(lines: list[str]) -> str:
    first = next(line for line in lines if line.strip())
    return first[: len(first) - len(first.lstrip())]


def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _backup(path: Path, stamp: str) -> Path:
    target = path.with_name(f"{path.name}.{BACKUP_TAG}-{stamp}.bak")
    shutil.copy2(path, target)
    return target


def _replace(path: Path, content: str, dry_run: bool, stamp: str, what: str) -> str:
    if dry_run:
        return f"[预演] 将写入{what}：{path}" + ("（会先备份原文件）" if path.exists() else "")
    note = f"，原文件备份为 {_backup(path, stamp).name}" if path.exists() else ""
    _write(path, content)
    return f"已写入{what}：{path}{note}"


def apply(app: Path, dry_run: bool, stamp: str | None = None) -> list[str]:
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    messages = []
    dns_path = app / "dns_config.yaml"
    if dns_template_applied(_read(dns_path)):
        messages.append("DNS 覆写已经是推荐配置，不改")
    else:
        messages.append(_replace(dns_path, DNS_TEMPLATE, dry_run, stamp, " DNS 覆写"))
    _, rules = current_profile_files(app)
    if rules is None:
        messages.append("没找到当前订阅的规则文件（还没导入订阅，或用的是本地配置），前置规则没写；"
                        "全局模式下可以不管，规则模式请让用户在订阅上右键「编辑规则」手动加")
        return messages
    text = _read(rules) or ""
    if has_prepend_rules(text):
        messages.append("国内直连前置规则已经有了，不改")
        return messages
    try:
        new_text = add_prepend_rules(text)
    except ValueError:
        messages.append(f"规则文件 {rules.name} 的格式看不懂，没改；请让用户在订阅上右键「编辑规则」手动加")
        return messages
    messages.append(_replace(rules, new_text, dry_run, stamp, "国内直连前置规则"))
    return messages


def restore(app: Path, dry_run: bool) -> list[str]:
    _, rules = current_profile_files(app)
    messages = []
    for path in [app / "dns_config.yaml"] + ([rules] if rules else []):
        backups = sorted(path.parent.glob(f"{path.name}.{BACKUP_TAG}-*.bak"))
        if not backups:
            messages.append(f"{path.name} 没有本脚本留下的备份，没动")
            continue
        if not dry_run:
            shutil.copy2(backups[-1], path)
        messages.append(f"{'[预演] 将用' if dry_run else '已用'} {backups[-1].name} 还原 {path.name}")
    return messages


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
    runtime = report["runtime"]
    loaded = runtime["dns"] and runtime["rules"]
    print(f"Clash 实际加载的配置：{'已包含以上改动' if loaded else '还没包含 → ' + SETUP_RELOAD}")


def _print_verify(result: dict) -> None:
    if result["ok"]:
        print("[OK] Clash 已加载新的 DNS 覆写和国内直连规则")
        return
    if not result["dns_override_on"]:
        print(f"[X] 「DNS 覆写」开关没开 → {SETUP_RELOAD}")
    if not (result["dns"] and result["rules"]):
        print(f"[X] Clash 实际加载的配置里还没有改动（DNS：{result['dns']}，规则：{result['rules']}）→ {SETUP_RELOAD}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clash Verge Rev 配置检查与写入（claude-antiban）")
    parser.add_argument("command", choices=["status", "apply", "verify", "restore"])
    parser.add_argument("--dir", help="Clash Verge 配置目录，默认按系统自动找")
    parser.add_argument("--dry-run", action="store_true", help="apply / restore 只预演，不写文件")
    parser.add_argument("--json", action="store_true", help="status / verify 输出 JSON")
    args = parser.parse_args(argv)

    app = find_app_dir(args.dir)
    if app is None:
        print("没找到 Clash Verge Rev 的配置目录：用户还没装 Clash Verge Rev，或者用的是 v2rayN 等别的软件。")
        return 2
    if args.command in ("status", "verify"):
        result = status(app) if args.command == "status" else verify(app)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            (_print_status if args.command == "status" else _print_verify)(result)
        return 0 if args.command == "status" or result["ok"] else 1
    action = apply if args.command == "apply" else restore
    for message in action(app, dry_run=args.dry_run):
        print(message)
    if not args.dry_run:
        print(f"下一步：{SETUP_RELOAD}，然后运行 verify 确认")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
