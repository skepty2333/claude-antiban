"""Clash 前置规则：让 Claude 专用浏览器和 Claude 程序全走节点，再让国内网站直连。

为什么要进程规则：规则模式下国内网站直连，任何网页或邮件只要让浏览器去请求一个国内地址，
这个请求就绕过代理、带着真实 IP 出去。给 Claude 专用的浏览器和 Claude 程序加 PROCESS-NAME
规则、排在国内直连规则前面，它们的流量就一律走节点。不开 TUN 时 mihomo 也能认出系统代理
连接来自哪个进程（Windows 上实测过）；macOS 的进程名没有在真机上验证过。
"""
from __future__ import annotations

import re

PREPEND_RULES = ("GEOSITE,cn,DIRECT", "GEOIP,CN,DIRECT,no-resolve")
BROWSERS = {
    "chrome": {"win32": ("chrome.exe",), "darwin": ("Google Chrome", "Google Chrome Helper")},
    "edge": {"win32": ("msedge.exe",), "darwin": ("Microsoft Edge", "Microsoft Edge Helper")},
    "firefox": {"win32": ("firefox.exe",), "darwin": ("firefox",)},
    "brave": {"win32": ("brave.exe",), "darwin": ("Brave Browser", "Brave Browser Helper")},
}
# Claude 桌面端和原生安装的 Claude Code 在 Windows 上都是 claude.exe
CLAUDE_APPS = {"win32": ("claude.exe",), "darwin": ("Claude", "Claude Helper", "claude")}
PROCESS_PREFIX = "PROCESS-NAME,"

TOP_LEVEL = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*?))?\s*$")
LIST_ITEM = re.compile(r"^\s*-\s+(.*?)\s*$")
RULES_SKELETON = "# Profile Enhancement Rules Template for Clash Verge\n\nprepend: []\n\nappend: []\n\ndelete: []\n"


def unquote(value: str) -> str:
    """去掉 YAML 标量的引号和行尾注释；引号里的 " #" 不算注释（节点名里常有）。"""
    value = value.strip()
    quote = value[:1]
    if quote in ("'", '"'):
        end = value.find(quote, 1)
        while quote == "'" and end != -1 and value[end + 1:end + 2] == "'":  # '' 是转义的单引号
            end = value.find(quote, end + 2)
        if end != -1:
            inner = value[1:end]
            return inner.replace("''", "'") if quote == "'" else inner
    return re.sub(r"\s+#.*$", "", value).strip()


def _block_items(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        if not line.strip():
            continue
        item = LIST_ITEM.match(line)
        if not item:
            break
        items.append(unquote(item.group(1)))
    return items


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


def match_target(subscription: str) -> str | None:
    """订阅里兜底规则 MATCH 指向的代理组，也就是"其余流量"走的那个组。"""
    found = re.findall(r"^\s*-\s*['\"]?MATCH,([^'\"\n]+?)['\"]?\s*$", subscription, re.M)
    return found[-1].strip() if found else None


def process_rules(browsers: list[str] | str | None, group: str, platform: str) -> list[str]:
    chosen = [browsers] if isinstance(browsers, str) else list(browsers or [])
    names = [name for b in chosen for name in BROWSERS.get(b, {}).get(platform, ())]
    names += list(CLAUDE_APPS.get(platform, ()))
    return [f"{PROCESS_PREFIX}{name},{group}" for name in dict.fromkeys(names)]


def in_order(entries: list[str], desired: list[str]) -> bool:
    """desired 里的规则都在，并且先后顺序不变（进程规则必须排在国内直连前面）。"""
    if any(rule not in entries for rule in desired):
        return False
    positions = [entries.index(rule) for rule in desired]
    return positions == sorted(positions)


def _yaml_item(entry: str) -> str:
    if re.search(r":\s|\s#|^[\[\]{}&*!|>'\"%@`]", entry):
        return "'" + entry.replace("'", "''") + "'"
    return entry


def merge_prepend(text: str, desired: list[str]) -> str:
    """把 desired 按顺序放在 prepend 最前面，原有的其他条目保留在后面。"""
    if not text.strip():
        text = RULES_SKELETON
    entries = prepend_entries(text)  # 看不懂的格式在这里抛 ValueError
    merged = list(desired) + [entry for entry in entries if entry not in desired]
    if merged == entries:
        return text
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^prepend:", line)), None)
    if start is None:
        return "\n".join(["prepend:", *(f"- {_yaml_item(e)}" for e in merged), *lines]) + "\n"
    end = start + 1
    while end < len(lines) and LIST_ITEM.match(lines[end]):
        end += 1
    indent = re.match(r"^(\s*)", lines[start + 1]).group(1) if end > start + 1 else ""  # 沿用原来的缩进
    lines[start:end] = ["prepend:", *(f"{indent}- {_yaml_item(e)}" for e in merged)]
    return "\n".join(lines) + "\n"


def add_prepend_rules(text: str) -> str:
    """只加国内直连两条（不带进程规则）。"""
    return merge_prepend(text, list(PREPEND_RULES))


def has_prepend_rules(text: str | None) -> bool:
    try:
        return in_order(prepend_entries(text or ""), list(PREPEND_RULES))
    except ValueError:
        return False


def runtime_process_first(runtime: str) -> bool:
    """Clash 实际加载的规则里，进程规则排在国内直连规则前面。"""
    lines = [unquote(m.group(1)) for m in map(LIST_ITEM.match, runtime.splitlines()) if m]
    process = next((i for i, rule in enumerate(lines) if rule.startswith(PROCESS_PREFIX)), None)
    domestic = next((i for i, rule in enumerate(lines) if rule == PREPEND_RULES[0]), None)
    return process is not None and (domestic is None or process < domestic)
