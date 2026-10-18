"""Turn raw probe data into findings. Pure functions, no network access.

Each finding: {"key", "title", "level", "summary", "fix"} where level is one of
"bad" (fix now), "warn" (inconsistent / risky), "ok", "info" (FYI / inconclusive).
"""
from __future__ import annotations

import ipaddress
from collections import Counter
from typing import Any, Optional

Json = dict[str, Any]
CHINA = {"CN", "HK", "MO"}
# Exits Anthropic does not serve: Greater China plus comprehensively sanctioned countries.
RESTRICTED = CHINA | {"RU", "BY", "IR", "KP", "SY", "CU"}
CN_TIMEZONES = {"Asia/Shanghai", "Asia/Urumqi", "Asia/Chongqing", "Asia/Chungking",
                "Asia/Harbin", "Asia/Kashgar", "Asia/Hong_Kong", "Asia/Macau", "PRC"}
WINDOWS_TZ = {
    "America/Los_Angeles": "Pacific Standard Time",
    "America/Denver": "Mountain Standard Time",
    "America/Phoenix": "US Mountain Standard Time",
    "America/Chicago": "Central Standard Time",
    "America/New_York": "Eastern Standard Time",
    "America/Anchorage": "Alaskan Standard Time",
    "Pacific/Honolulu": "Hawaiian Standard Time",
    "Europe/London": "GMT Standard Time",
    "Europe/Berlin": "W. Europe Standard Time",
    "Europe/Amsterdam": "W. Europe Standard Time",
    "Europe/Paris": "Romance Standard Time",
    "Asia/Tokyo": "Tokyo Standard Time",
    "Asia/Seoul": "Korea Standard Time",
    "Asia/Singapore": "Singapore Standard Time",
    "Asia/Taipei": "Taipei Standard Time",
}
ORDER = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
NO_BROWSER = "浏览器检测没有结果（已跳过、超时或出错）"
# 真实 IP 或真实的网络环境漏给 Claude 的那几项，每一项单独出现都够严重，结论里直接这么说
ALONE = "单独这一项就可能导致封号"
BROWSER_NAMES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox", "brave": "Brave"}
DEFAULT_OPENS = "Claude 桌面端、Claude Code 登录时，还有邮件里的登录链接，都会自动用默认浏览器打开"


def finding(key: str, title: str, level: str, summary: str, fix: str = "") -> Json:
    return {"key": key, "title": title, "level": level, "summary": summary, "fix": fix}


def mask_ip(ip: Optional[str]) -> str:
    if not ip:
        return "?"
    parts = ip.split(".")
    return ".".join(parts[:2] + ["x", "x"]) if len(parts) == 4 else ip[:9] + "…"


def _family(ip: Optional[str]) -> Optional[int]:
    try:
        return ipaddress.ip_address(ip).version if ip else None
    except ValueError:
        return None


def _majority(values: list) -> Optional[Any]:
    """Most common non-empty value; ties go to the earliest source."""
    values = [v for v in values if v not in (None, "")]
    return Counter(values).most_common(1)[0][0] if values else None


# ---------------------------------------------------------------- exit + geo

def consensus(geo: dict[str, Json]) -> Json:
    """Majority view of the geo databases (each source is one vote)."""
    rows = [g for g in geo.values() if "error" not in g]
    return {
        "ip": _majority([g.get("ip") for g in rows]),
        "ips": sorted({g.get("ip") for g in rows if g.get("ip")}),
        "country": _majority([g.get("country") for g in rows]),
        "timezone": _majority([g.get("timezone") for g in rows]),
        "offset_min": _majority([g.get("offset_min") for g in rows]),
        "places": [f"{n}: {g.get('city')}, {g.get('region')} ({g.get('timezone')})"
                   for n, g in geo.items() if "error" not in g],
        "sources": len(rows),
    }


def _browser(report: Json) -> Json:
    return report.get("browser") or {}


def browser_exit(report: Json) -> Json:
    """Where the browser exits: claude.ai's trace if loaded, else the neutral pre-flight."""
    b = _browser(report)
    return b.get("claudeTrace") or b.get("neutralTrace") or {}


def real_ip(report: Json) -> Optional[str]:
    """The direct-path IP when it differs from every proxied answer (i.e. the user's own IP)."""
    direct = report["paths"]["direct"]["echo"].get("ip")
    proxied = {report["paths"][p]["echo"].get("ip") for p in ("env_proxy", "system_proxy")}
    proxied.add(browser_exit(report).get("ip"))
    if not direct or (direct in proxied and exit_country(report) not in RESTRICTED):
        return None
    return direct


def exit_ip(report: Json) -> Optional[str]:
    paths = report["paths"]
    return (browser_exit(report).get("ip") or paths["env_proxy"]["echo"].get("ip")
            or paths["system_proxy"]["echo"].get("ip") or report["consensus"].get("ip"))


def exit_country(report: Json) -> Optional[str]:
    return browser_exit(report).get("loc") or report["consensus"].get("country")


def eval_browser_exit(report: Json) -> Json:
    title = "浏览器访问 Claude 的出口"
    if not report.get("browser"):
        return finding("browser_exit", title, "info", NO_BROWSER)
    b = _browser(report)
    neutral, claude = b.get("neutralTrace"), b.get("claudeTrace")
    if not neutral:
        return finding("browser_exit", title, "bad",
                       "这个浏览器连不上 1.1.1.1（直连时会被墙），多半没走代理：用它打开 Claude，Claude 看到的就是"
                       "你的真实 IP。为保护真实 IP，这次没有去访问 claude.ai", "routing")
    if neutral.get("loc") in RESTRICTED:
        return finding("browser_exit", title, "bad",
                       f"这个浏览器的出口在 {neutral.get('loc')}，没走代理：用它打开 Claude，Claude 看到的就是你的真实 IP。"
                       "为保护真实 IP，这次没有去访问 claude.ai", "routing")
    if not claude and b.get("claudeSkipped"):
        return finding("browser_exit", title, "info",
                       f"浏览器出口 {neutral.get('ip')}（{neutral.get('loc')}）；这次按 --no-claude 没有访问 claude.ai")
    if not claude:
        return finding("browser_exit", title, "warn",
                       f"浏览器出口 {neutral.get('ip')}（{neutral.get('loc')}），但取不到 claude.ai 的出口信息", "routing")
    if claude.get("loc") in RESTRICTED:
        return finding("browser_exit", title, "bad",
                       f"Claude 看到的出口在 {claude.get('loc')}：claude.ai 被分流到了 Claude 不支持的地区，{ALONE}",
                       "routing")
    return finding("browser_exit", title, "ok", f"Claude 看到 {claude.get('ip')}（{claude.get('loc')}）")


def _reference_label(report: Json) -> str:
    return "浏览器访问 Claude 的出口" if browser_exit(report).get("ip") else "其他走代理的路径"


def _path_vs_exit(echo: Json, exit_addr: Optional[str], ref: str) -> tuple[str, str]:
    if "error" in echo:
        return "warn", f"经这条路查不到出口：{echo['error'][:120]}"
    ip = echo.get("ip")
    if exit_addr and _family(ip) != _family(exit_addr):
        return "info", f"出口 {ip}；{ref}是另一种 IP 版本（{exit_addr}），无法直接比较"
    if exit_addr and ip != exit_addr:
        return "bad", (f"出口 {ip} 与{ref} {exit_addr} 不同：Claude 会看到同一个账号从两个 IP 上来，{ALONE}"
                       "（多半是分流规则或自动选择节点造成的）")
    return "ok", f"出口 {ip}，与{ref}一致"


def eval_system_proxy(report: Json, exit_addr: Optional[str], tun: bool) -> Json:
    path = report["paths"]["system_proxy"]
    title = "认系统代理的程序（浏览器、Claude 桌面端）"
    if not path.get("proxy"):
        if tun:
            return finding("system_proxy", title, "ok", "没设系统代理，但直连流量已被 TUN 接管")
        if report.get("system_proxy_pac"):
            return finding("system_proxy", title, "warn",
                           "系统代理是 PAC/自动检测，脚本无法探测；以浏览器那一项为准", "routing")
        if report.get("platform", "win32") not in ("win32", "darwin"):
            return finding("system_proxy", title, "info", "这个系统不检测系统代理；以浏览器那一项为准")
        return finding("system_proxy", title, "bad",
                       f"没设系统代理，也没开 TUN：Claude 桌面端会用真实 IP 直连，{ALONE}", "routing")
    level, text = _path_vs_exit(path["echo"], exit_addr, _reference_label(report))
    return finding("system_proxy", title, level, f"系统代理 {path['proxy']}；{text}",
                   "routing" if level in ("bad", "warn") else "")


def eval_env_proxy(report: Json, exit_addr: Optional[str], tun: bool) -> Json:
    path = report["paths"]["env_proxy"]
    title = "Claude Code 命令行（HTTPS_PROXY / settings.json）"
    saved = {k: v for k, v in (path.get("persistent") or {}).items()
             if k.split(":")[-1].upper() in ("HTTPS_PROXY", "HTTP_PROXY")}
    if path.get("proxy"):
        level, text = _path_vs_exit(path["echo"], exit_addr, _reference_label(report))
        source = path.get("source") or "HTTPS_PROXY"
        return finding("env_proxy", title, level, f"{source}={path['proxy']}；{text}",
                       "routing" if level in ("bad", "warn") else "")
    if saved:
        return finding("env_proxy", title, "warn",
                       "变量已持久保存，但当前终端是之前打开的，没读到：重开终端再用 Claude Code", "routing")
    if tun:
        return finding("env_proxy", title, "warn",
                       "没设 HTTPS_PROXY，目前靠 TUN 接管；Clash 一退出 Claude Code 就会直连", "routing")
    return finding("env_proxy", title, "bad",
                   f"没设 HTTPS_PROXY 也没开 TUN：Claude Code 会用真实 IP 直连，{ALONE}", "routing")


def eval_direct(report: Json, tun: bool) -> Json:
    echo = report["paths"]["direct"]["echo"]
    title = "不认代理的程序（直连）"
    if "error" in echo:
        return finding("direct", title, "info", "直连查不到出口（网络被拦或离线）")
    if tun:
        return finding("direct", title, "info",
                       "直连也从代理出口出去：TUN/全局接管中。注意 Clash 退出后会回到真实 IP")
    return finding("direct", title, "info",
                   f"直连用真实 IP {mask_ip(echo.get('ip'))}。只要 Claude 的入口都走代理，这条与 Claude 无关")


def eval_exit_stability(report: Json, exit_addr: Optional[str]) -> Json:
    title = "出口 IP 是否唯一"
    seen = {ip for ip in report["consensus"]["ips"] if _family(ip) == 4}
    for name in ("system_proxy", "env_proxy"):
        ip = report["paths"][name]["echo"].get("ip")
        if report["paths"][name].get("proxy") and _family(ip) == 4:
            seen.add(ip)
    if _family(exit_addr) == 4:
        seen.add(exit_addr)
    if len(seen) <= 1:
        return finding("exit_stability", title, "ok" if seen else "info",
                       "所有走代理的请求都是同一个出口" if seen else "没有可比较的代理出口")
    return finding("exit_stability", title, "bad",
                   f"走代理的请求出现了多个出口 {sorted(seen)}：Claude 看到的 IP 会变来变去，{ALONE}。"
                   "检查是不是用了自动选择、负载均衡组或分流规则", "routing")


# ---------------------------------------------------------------- DNS

def _dns_level(servers: list[Json], country: Optional[str]) -> tuple[str, str]:
    countries = sorted({s.get("country_code") or "?" for s in servers})
    isps = sorted({s.get("isp") or "?" for s in servers})
    desc = f"解析服务器 {len(servers)} 个，国家 {countries}，运营商 {isps[:3]}"
    if set(countries) & CHINA:
        return "bad", desc
    if country and set(countries) != {country}:
        return "warn", desc
    return "ok", desc


def eval_dns_browser(report: Json, country: Optional[str]) -> Json:
    title = "DNS：浏览器这条路"
    data = (report.get("dns") or {}).get("browser")
    if data is None or not report.get("browser"):
        return finding("dns_browser", title, "info", NO_BROWSER)
    if "error" in data:
        return finding("dns_browser", title, "info", f"dnsleaktest 接口失败：{data['error'][:100]}")
    if not data["servers"]:
        return finding("dns_browser", title, "info", "没观察到解析服务器（远端解析或测试失败）")
    level, desc = _dns_level(data["servers"], country)
    if level == "bad":
        desc += f"：浏览器查域名用到了国内的 DNS 服务器，国内那边能看到你在访问 Claude，{ALONE}"
    elif level == "warn":
        desc += "：解析服务器和出口不在同一个国家"
    return finding("dns_browser", title, level, desc, "dns" if level != "ok" else "")


def eval_dns_os(report: Json, country: Optional[str]) -> Json:
    title = "DNS：系统解析（不走代理的程序）"
    data = (report.get("dns") or {}).get("os") or {}
    if "error" in data:
        return finding("dns_os", title, "info", f"dnsleaktest 接口失败：{data['error'][:100]}")
    if not data.get("servers"):
        if data.get("lookups_ok") == 0:
            return finding("dns_os", title, "info", "系统解析全部失败，无法判断")
        return finding("dns_os", title, "ok", "系统解析没有到达外部解析服务器：已被代理软件接管")
    _, desc = _dns_level(data["servers"], country)
    if any(srv.get("country_code") == "CN" for srv in data["servers"]):  # mainland ISP resolver
        return finding("dns_os", title, "bad",
                       desc + "。电脑在用国内运营商的 DNS：不走代理的程序一查域名，运营商就能看到这台电脑访问过哪些网站，"
                       f"可能包括 Claude 的，{ALONE}。用 windows-setup.ps1 -NetworkTask 把网卡 DNS 固定为 "
                       "1.1.1.1/8.8.8.8（SKILL 配置流程第 6 步）", "dns")
    return finding("dns_os", title, "ok", desc + "（只影响不走代理的软件）")


# ---------------------------------------------------------------- WebRTC + IPv6

def _classify_candidate(addr: str, exit_addr: Optional[str], mine: Optional[str]) -> str:
    if not addr or addr.endswith(".local"):
        return "mdns"
    if addr == exit_addr:
        return "exit"
    if addr == mine:
        return "real"
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return "mdns"
    if ip.is_private or ip.is_link_local or ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10"):
        return "private"
    return "other"


def eval_webrtc(report: Json, exit_addr: Optional[str]) -> Json:
    title = "WebRTC"
    if not report.get("browser"):
        return finding("webrtc", title, "info", NO_BROWSER)
    cands = (_browser(report).get("webrtc") or {}).get("candidates") or []
    mine = real_ip(report)
    kinds = {c.get("address"): _classify_candidate(c.get("address") or "", exit_addr, mine) for c in cands}
    by_kind = {k: [a for a, kind in kinds.items() if kind == k] for k in ("real", "other", "private", "exit")}
    if by_kind["real"]:
        return finding("webrtc", title, "bad",
                       f"WebRTC 漏出了你的真实 IP {mask_ip(by_kind['real'][0])}：网页不经过代理就能拿到它，{ALONE}",
                       "browser")
    if by_kind["other"]:
        return finding("webrtc", title, "bad",
                       f"WebRTC 漏出了代理出口以外的公网 IP {[mask_ip(a) for a in by_kind['other']]}："
                       f"网页能绕过代理看到它，{ALONE}", "browser")
    if by_kind["private"]:
        return finding("webrtc", title, "warn",
                       f"WebRTC 漏出了内网 IP {by_kind['private']}：WebRTC 没限制住，扩展没装好或者没选对选项",
                       "browser")
    if not cands:
        return finding("webrtc", title, "ok", "没有任何候选地址：WebRTC 已被扩展或设置限制")
    if not by_kind["exit"]:
        return finding("webrtc", title, "info",
                       f"只有 {len(cands)} 个 mDNS 候选、没拿到公网候选（STUN 可能不通），本地地址已隐藏")
    return finding("webrtc", title, "ok", f"没有泄露（{len(cands)} 个候选，均为 mDNS 或代理出口）")


def eval_ipv6(report: Json, country: Optional[str]) -> Json:
    title = "IPv6"
    v6 = report.get("ipv6") or {}
    browser_ip = v6.get("browser")
    if browser_ip:
        found = (v6.get("browser_geo") or {}).get("country")
        if not found:
            return finding("ipv6", title, "warn", f"浏览器拿到了 IPv6 {mask_ip(browser_ip)}，但查不到归属地", "routing")
        if found in RESTRICTED or (country and found != country):
            return finding("ipv6", title, "bad",
                           f"浏览器拿到了 IPv6 {mask_ip(browser_ip)}（{found}），这条连接绕过了代理，{ALONE}", "routing")
        return finding("ipv6", title, "ok", f"浏览器 IPv6 {browser_ip} 也从代理出口所在国出去")
    direct = v6.get("direct") or {}
    if direct.get("reachable"):
        return finding("ipv6", title, "bad",
                       f"电脑的 IPv6 开着（{mask_ip(direct.get('ip'))}）：代理只管 IPv4，走 IPv6 的连接会绕过代理，"
                       f"直接用你的真实地址出去。这次浏览器碰巧没用上，不代表下次不会，{ALONE}。"
                       "必须关掉（SKILL 配置流程第 6 步）", "routing")
    return finding("ipv6", title, "ok", "本机没有可用的 IPv6 出口")


# ---------------------------------------------------------------- environment

def eval_timezone(report: Json) -> Json:
    title = "系统时区 vs IP 所在地"
    clock, cons = report["clock"], report["consensus"]
    tz, off = clock.get("timezone"), clock.get("offset_min")
    shown = tz or clock.get("name") or (f"UTC{off / 60:+g}" if off is not None else "未知")
    if tz in CN_TIMEZONES:
        return finding("timezone", title, "bad",
                       f"系统时区是 {shown}：Claude Code 会读系统时区，这是最直接的中国用户信号", "browser")
    if tz is None and off == 480:
        return finding("timezone", title, "warn",
                       f"系统时区是 UTC+8（{shown}），没能确认具体时区；如果是北京时间就是最直接的中国用户信号",
                       "browser")
    target, target_off = cons.get("timezone"), cons.get("offset_min")
    if not target or off is None:
        return finding("timezone", title, "info", f"系统时区 {shown}；查不到 IP 所在时区")
    if tz == target or (tz is None and off == target_off):
        return finding("timezone", title, "ok", f"系统时区 {shown} 与 IP 所在地 {target} 一致")
    summary = f"系统时区 {shown}，IP 所在地多数库判为 {target}"
    if target_off is not None and off == target_off:
        return finding("timezone", title, "ok", summary + "，当前偏移相同")
    win = WINDOWS_TZ.get(target)
    hint = f"改成 {target}" + (f'（Windows：tzutil /s "{win}"）' if win else "")
    gap = f"，相差 {abs(off - target_off) / 60:g} 小时" if target_off is not None else ""
    return finding("timezone", title, "warn", f"{summary}{gap}；{hint}", "browser")


def eval_fingerprint(report: Json) -> Json:
    title = "浏览器中文环境指纹（fuck-claude 评分）"
    fc = _browser(report).get("fuckClaude")
    if not fc:
        return finding("fingerprint", title, "info", NO_BROWSER)
    hits = [f"{s.get('id')} +{s.get('contribution')}（{s.get('raw')}）"
            for s in fc.get("signals") or [] if (s.get("score") or 0) >= 0.25]
    level = {"low": "ok", "medium": "warn", "high": "bad"}.get(fc.get("band"), "info")
    summary = f"{fc.get('score')}/100（{fc.get('band')}）" + (f"；命中：{'；'.join(hits)}" if hits else "；无命中")
    if any(s.get("id") == "vendorFonts" and (s.get("score") or 0) >= 0.25 for s in fc.get("signals") or []):
        summary += "。国产厂商字体可以用 scripts/setup/fonts.py 清理（用户同意后再删，SKILL 配置流程第 7 步）"
    return finding("fingerprint", title, level, summary, "browser" if hits else "")


def eval_ip_quality(report: Json) -> Json:
    title = "出口 IP 质量"
    rep = report.get("reputation") or {}
    flags = ((report.get("geo") or {}).get("ip-api.com") or {}).get("flags") or {}
    known = {k: v for k, v in rep.items() if k != "error" and v is not None}
    if not known and not any(v is not None for v in flags.values()):
        return finding("ip_quality", title, "info", "IP 质量接口都没有返回数据")
    notes, level = [], "ok"
    if rep.get("is_abuser"):
        notes.append(f"有滥用记录（{rep.get('abuser_score')}）")
        level = "bad"
    if rep.get("isResidential"):
        notes.append("住宅 IP")
    elif rep.get("is_datacenter") or flags.get("hosting"):
        notes.append(f"机房 IP（{rep.get('company_name') or rep.get('asOrganization') or '?'}）")
        level = "warn" if level == "ok" else level
    if flags.get("proxy") or rep.get("is_proxy") or rep.get("is_vpn"):
        notes.append("被标记为代理/VPN")
        level = "warn" if level == "ok" else level
    if rep.get("trust_score") is not None:
        notes.append(f"net.coffee 信任分 {rep['trust_score']}")
    return finding("ip_quality", title, level, "；".join(notes) or "没有负面标记", "ip" if level != "ok" else "")


def _doh_desc(items: dict[str, Json]) -> str:
    return "，".join(f"{b} 为 {d.get('mode')}（{d.get('detail')}）" for b, d in items.items())


def eval_secure_dns(report: Json) -> Json:
    title = "浏览器安全 DNS（DoH）"
    data = report.get("secure_dns") or {}
    if not data:
        return finding("secure_dns", title, "info", "没找到 Chrome、Edge、Firefox 或 Brave 的设置")
    on = {b: d for b, d in data.items() if d.get("mode") not in ("off", "unknown")}
    why = ("浏览器会绕开 Clash 自己去查域名，查询走哪条路不受控制，可能把你访问 Claude 的记录交给国内的 DNS，"
           f"{ALONE}，必须关掉")
    claude = [BROWSER_NAMES[b] for b in report.get("claude_browsers") or [] if b in BROWSER_NAMES]
    if not claude:
        if not on:
            return finding("secure_dns", title, "ok", f"{'、'.join(data)} 的安全 DNS 都已关闭")
        return finding("secure_dns", title, "warn",
                       f"{_doh_desc(on)}。没指定使用 Claude 网页版的浏览器：如果是它，{why}", "browser")
    risky = {b: d for b, d in on.items() if b in claude}
    if risky:
        return finding("secure_dns", title, "bad", f"{_doh_desc(risky)}：{why}", "browser")
    unread = [b for b in claude if data.get(b, {}).get("mode") in (None, "unknown")]
    if unread:
        detail = "；".join(f"{b}：{data[b].get('detail')}" for b in unread if data.get(b, {}).get("detail"))
        return finding("secure_dns", title, "warn",
                       f"没能确认 {'、'.join(unread)} 的安全 DNS 已关闭" + (f"（{detail}）" if detail else "")
                       + "：请用户照 SETUP 2.2 在设置里明确关掉", "browser")
    others = {b: d for b, d in on.items() if b not in claude}
    if others:
        return finding("secure_dns", title, "info",
                       f"{'、'.join(claude)} 已关闭；{_doh_desc(others)}：只要不用它打开 Claude 网页版、它也不是默认浏览器，就没关系")
    return finding("secure_dns", title, "ok", f"{'、'.join(claude)} 的安全 DNS 已关闭")


def eval_tested_browser(report: Json) -> Optional[Json]:
    """检测页实际跑在哪个浏览器里：浏览器那几项只代表它。"""
    b = report.get("browser")
    if not b or "seen" not in b:
        return None
    title = "这次测的是哪个浏览器"
    seen, wanted = b.get("seen"), (report.get("claude_browsers") or [None])[0]
    if seen not in BROWSER_NAMES:
        ua = str((b.get("env") or {}).get("userAgent") or "")[:100]
        return finding("tested_browser", title, "warn",
                       f"检测页跑在一个认不出的浏览器里（{ua}）：360、QQ 这类国产浏览器不能用来打开 Claude 网页版", "browser")
    shown = BROWSER_NAMES[seen]
    if wanted and seen != wanted:
        return finding("tested_browser", title, "warn",
                       f"检测页是在 {shown} 里跑的，不是 {BROWSER_NAMES[wanted]}：WebRTC、浏览器 DNS、指纹这几项测的是 "
                       f"{shown}，要在 {BROWSER_NAMES[wanted]} 里重测", "browser")
    others = [b for b in report.get("claude_browsers") or [] if b in BROWSER_NAMES and b != seen]
    tail = "".join(f"；{BROWSER_NAMES[b]} 这次没测，要用 --browser {b} --also {seen} 再测一次" for b in others)
    return finding("tested_browser", title, "info",
                   f"检测页在 {shown} 里跑的：WebRTC、浏览器 DNS、指纹这几项只代表 {shown}{tail}")


def eval_default_browser(report: Json) -> Optional[Json]:
    """默认浏览器也会碰到 Claude：要么就是使用 Claude 网页版的那个，要么也照样设好。"""
    d = report.get("default_browser")
    if not d:
        return None
    title, name, key = "默认浏览器", d.get("name") or "?", d.get("key")
    claude = [b for b in report.get("claude_browsers") or [] if b in BROWSER_NAMES]
    if d.get("domestic"):
        return finding("default_browser", title, "bad",
                       f"默认浏览器是 {name}，是国产浏览器：{DEFAULT_OPENS}，{ALONE}。要把默认浏览器改成使用 Claude 网页版的那个",
                       "browser")
    readable = any(d.get(k) for k in ("progid", "exe", "bundle"))
    if not claude or (key is None and not readable):
        return finding("default_browser", title, "info", f"默认浏览器是 {name}")
    seen = (report.get("browser") or {}).get("seen")
    if key in claude and report.get("browser") and seen != key:
        return finding("default_browser", title, "warn",
                       f"默认浏览器是 {name}，按 --also 算作也设好了，但这次检测页没在 {name} 里跑："
                       f"再用 --browser {key} --also {seen or claude[0]} 测一次", "browser")
    if key in claude:
        return finding("default_browser", title, "ok",
                       f"默认浏览器就是 {name}：Claude 桌面端、Claude Code 登录和邮件里的登录链接，打开的都是它")
    main = BROWSER_NAMES[claude[0]]
    way_out = (f"要么 {name} 也照 SETUP 第二节设好，再用 --browser {key} --also {claude[0]} 测一遍" if key
               else "要么换成本 skill 支持的浏览器（Chrome、Edge、Firefox、Brave）当默认浏览器，也照样设好")
    return finding("default_browser", title, "bad",
                   f"默认浏览器是 {name}，不是使用 Claude 网页版的 {main}：{DEFAULT_OPENS}，没设好的 {name} 会把你的真实环境"
                   f"带给 Claude。要么把默认浏览器改成 {main}（推荐），{way_out}", "browser")


def eval_domestic_apps(report: Json, tun: bool) -> Json:
    title = "国内软件会不会断网（DNS）"
    probe = report.get("domestic_dns") or {}
    os_states, clash_states = set((probe.get("os") or {}).values()), set((probe.get("clash") or {}).values())
    if not os_states:
        return finding("domestic_apps", title, "info", "没有检测")
    if "fake" in os_states and not tun:
        return finding("domestic_apps", title, "bad",
                       "系统 DNS 给国内域名返回了 Clash 的假 IP（198.18.x.x），而 TUN 没开：迅雷、网易云这类"
                       "不走代理的软件会连不上网", "dns")
    if "fail" in os_states:
        return finding("domestic_apps", title, "bad", "系统 DNS 解析不了国内域名：不走代理的软件都会断网", "dns")
    if "fail" in clash_states:
        return finding("domestic_apps", title, "warn",
                       "现在正常；但 Clash 自己的 DNS 解析不了国内域名（常见原因：nameserver 写了 #GLOBAL，而 GLOBAL "
                       "停在 DIRECT 或不存在的节点）。一旦把系统 DNS 指向 Clash，国内软件会断网", "dns")
    if "fake" in clash_states and not tun:
        return finding("domestic_apps", title, "info",
                       "现在正常；Clash 会给国内域名发假 IP，以后若把系统 DNS 指向 Clash 又不开 TUN，"
                       "国内软件会断网（预防：fake-ip-filter 加 geosite:cn）", "dns")
    return finding("domestic_apps", title, "ok", "国内域名解析正常，不走代理的国内软件不会因 DNS 断网")


def evaluate(report: Json) -> list[Json]:
    """All findings, most severe first."""
    exit_addr, country = exit_ip(report), exit_country(report)
    direct_ip = report["paths"]["direct"]["echo"].get("ip")
    # Direct traffic leaving via the proxy exit means TUN; a restricted "exit" just means no proxy.
    tun = bool(exit_addr) and direct_ip == exit_addr and country not in RESTRICTED
    items = [
        eval_browser_exit(report),
        eval_system_proxy(report, exit_addr, tun),
        eval_env_proxy(report, exit_addr, tun),
        eval_direct(report, tun),
        eval_exit_stability(report, exit_addr),
        eval_dns_browser(report, country),
        eval_dns_os(report, country),
        eval_webrtc(report, exit_addr),
        eval_ipv6(report, country),
        eval_timezone(report),
        eval_fingerprint(report),
        eval_ip_quality(report),
        eval_secure_dns(report),
        eval_tested_browser(report),
        eval_default_browser(report),
        eval_domestic_apps(report, tun),
    ]
    return sorted((f for f in items if f), key=lambda f: ORDER.get(f["level"], 9))
