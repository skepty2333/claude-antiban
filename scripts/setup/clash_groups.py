"""Claude 的流量最后落在哪个节点上：顺着代理组和用户在 Clash 里选的节点一层层找下去。

规则模式下，进程规则把专用浏览器和 Claude 程序指向订阅的兜底组（MATCH）；全局模式下一切都走 GLOBAL。
这个组如果是"自动选择""故障转移""负载均衡"，或者手动选的是 DIRECT，出口就会跳，或者干脆是真实 IP。

只读两个文件：Clash 实际加载的 clash-verge.yaml（由 Clash Verge 生成，格式固定）里的 proxy-groups，
和 profiles.yaml 里当前订阅的 selected（用户在界面上选中的节点）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from clash_rules import TOP_LEVEL, unquote

AUTO_TYPES = ("url-test", "fallback", "load-balance")
DIRECT_NAMES = ("DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE")
# 组里有这些键时，proxies 列表不全（节点来自订阅提供者），保存的选择不在列表里也不能算失效
OPEN_KEYS = ("use", "include-all", "include-all-proxies", "include-all-providers")
MAX_DEPTH = 10


@dataclass(frozen=True)
class Route:
    kind: str        # node：落在一个固定节点上；auto：自动切换的组；direct：直连；unknown：判断不了
    chain: tuple[str, ...]
    stale: tuple[str, ...] = ()  # 已经不在组里的旧选择（订阅更新后节点名变了），Clash 改用组里第一项

    @property
    def shown(self) -> str:
        return " → ".join(self.chain)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _inline_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [unquote(v) for v in value[1:-1].split(",") if v.strip()]
    return []


def proxy_groups(text: str) -> dict[str, dict]:
    """proxy-groups：组名 -> {"type": ..., "proxies": [...]}。"""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^proxy-groups:\s*(#.*)?$", line)), None)
    if start is None:
        return {}
    groups: list[dict] = []
    item_indent, field = None, None
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if TOP_LEVEL.match(line):
            break
        indent, body = _indent(line), line.strip()
        if item_indent is None and body.startswith("- "):
            item_indent = indent
        if indent == item_indent and body.startswith("- "):
            groups.append({"proxies": []})
            body, field = body[2:].strip(), None
        if not groups:
            continue
        pair = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", body)
        if pair and not body.startswith("- "):
            field = pair.group(1)
            if field == "proxies":
                groups[-1]["proxies"] = _inline_list(pair.group(2))
            else:
                groups[-1][field] = unquote(pair.group(2)) if pair.group(2) else ""  # 空值也记下：键在就算
        elif body.startswith("- ") and field == "proxies":
            groups[-1]["proxies"].append(unquote(body[2:]))
    return {g["name"]: g for g in groups if g.get("name")}


def selected_nodes(profiles: str, uid: str | None) -> dict[str, str] | None:
    """profiles.yaml 里当前订阅的 selected：组名 -> 用户选中的节点；找不到这个订阅返回 None。"""
    if not uid:
        return None
    lines = profiles.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(rf"^- uid:\s*['\"]?{re.escape(uid)}['\"]?\s*$", line)), None)
    if start is None:
        return None
    chosen: dict[str, str] = {}
    name, inside = None, False
    for line in lines[start + 1:]:
        if line.startswith("- ") or TOP_LEVEL.match(line):
            break
        if re.match(r"^  selected:", line):
            inside = True
            continue
        if inside and re.match(r"^  [A-Za-z]", line):
            break
        if not inside:
            continue
        named = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
        now = re.match(r"^\s+now:\s*(.+?)\s*$", line)
        if named:
            name = unquote(named.group(1))
        elif now and name:
            chosen[name] = unquote(now.group(1))
    return chosen


def _pick(name: str, group: dict, selected: Mapping[str, str]) -> tuple[str, str | None]:
    """select 组实际用的是哪一项，以及失效的旧选择（没有就是 None）。

    Clash 只能选组里有的名字：保存的选择不在组里了（订阅更新后，带流量、天数的节点名会变），
    它就停在组里第一项上，那一项可能就是 DIRECT。
    """
    proxies, picked = group["proxies"], selected.get(name)
    if picked and (picked in proxies or any(key in group for key in OPEN_KEYS)):
        return picked, None
    return (proxies[0] if proxies else ""), picked


def resolve(start: str, groups: Mapping[str, dict], selected: Mapping[str, str]) -> Route:
    """从 start（进程规则指向的组、MATCH 组或 GLOBAL）一层层往下找，直到一个节点、一个自动切换的组或直连。"""
    chain, stale, name = [], [], start
    for _ in range(MAX_DEPTH):
        chain.append(name)
        if name.upper() in DIRECT_NAMES:
            return Route("direct", tuple(chain), tuple(stale))
        group = groups.get(name)
        if group is None:
            # GLOBAL 是内核自带的组，不在 proxy-groups 里；它没被选过就判断不了
            return Route("unknown" if name == "GLOBAL" else "node", tuple(chain), tuple(stale))
        kind = (group.get("type") or "").lower()
        if kind in AUTO_TYPES:
            return Route("auto", tuple(chain), tuple(stale))
        if kind != "select":
            return Route("unknown", tuple(chain), tuple(stale))
        name, old = _pick(name, group, selected)
        if old:
            stale.append(old)
        if not name:
            return Route("unknown", tuple(chain), tuple(stale))
    return Route("unknown", tuple(chain), tuple(stale))


def runtime_target(runtime: str) -> str | None:
    """Clash 实际加载的规则里，Claude 程序的进程规则指向哪个组；没有就用兜底的 MATCH。"""
    rules = [unquote(m.group(1)) for m in re.finditer(r"^\s*-\s+(.+?)\s*$", runtime, re.M)]
    for rule in rules:
        parts = [p.strip() for p in rule.split(",")]
        if len(parts) >= 3 and parts[0] == "PROCESS-NAME" and parts[1].lower() in ("claude.exe", "claude"):
            return parts[2]
    match = [r.split(",", 1)[1].strip() for r in rules if r.startswith("MATCH,")]
    return match[-1] if match else None


def claude_route(mode: str, match_group: str | None, runtime: str, profiles: str, uid: str | None) -> Route | None:
    """Claude 专用浏览器和 Claude 程序的流量最后落在哪；判断不了返回 None。

    以 Clash 实际加载的配置为准：先找进程规则指向的组，再找 MATCH，最后才用订阅里的 MATCH（match_group）。
    """
    groups = proxy_groups(runtime)
    selected = selected_nodes(profiles, uid)
    if not groups or selected is None:
        return None
    if mode == "global":
        if "GLOBAL" in groups:
            return resolve("GLOBAL", groups, selected)
        if "GLOBAL" not in selected:
            return None
        inner = resolve(selected["GLOBAL"], groups, selected)
        return Route(inner.kind, ("GLOBAL", *inner.chain), inner.stale)
    start = runtime_target(runtime) or match_group
    if not start:
        return None
    return resolve(start, groups, selected)
