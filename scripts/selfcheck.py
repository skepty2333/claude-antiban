"""Claude anti-ban environment self-check (Python 3.9+, standard library only).

    python selfcheck.py --browser chrome                 # full check, opens check.html in Chrome
    python selfcheck.py --browser chrome --also edge     # the default browser (Edge) is set up for Claude too
    python selfcheck.py --browser chrome --no-open       # print the URL; the user opens it in Chrome
    python selfcheck.py --browser chrome --skip-browser  # script-side checks only

--browser is always required: ask the user which browser they log in to Claude with. The page
never opens in "whatever the default browser is", and the secure-DNS and default-browser verdicts
are judged against --browser / --also.

Python never contacts Claude/Anthropic (netchecks refuses those hosts). Only the
browser page loads claude.ai/cdn-cgi/trace, and only after a neutral pre-flight
shows the browser already exits outside China.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import browsers as br  # noqa: E402
import envchecks as ec  # noqa: E402
import findings as fd  # noqa: E402
import netchecks as nc  # noqa: E402
from browser_bridge import run_in_browser  # noqa: E402

Json = dict[str, Any]
ICON = {"bad": "[X]", "warn": "[!]", "ok": "[OK]", "info": "[i]"}
FIX_REFS = {
    "routing": "references/routing.md",
    "dns": "references/dns.md",
    "browser": "references/browser-and-device.md",
    "ip": "references/ip.md",
}
CTRL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
CREDENTIALS = re.compile(r"//[^/@\s]*@")
PROBE_TIMEOUT = 90
WINDOWS_TO_IANA = {win: iana for iana, win in reversed(list(fd.WINDOWS_TZ.items()))}
WINDOWS_TO_IANA.update({"China Standard Time": "Asia/Shanghai", "Taipei Standard Time": "Asia/Taipei"})


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude 防封环境自检")
    p.add_argument("--browser", choices=sorted(br.KNOWN),
                   help="必填。用户登录 Claude 的浏览器，检测页在它里面打开（先问用户，不要猜）")
    p.add_argument("--also", choices=sorted(br.KNOWN),
                   help="另一个也会碰到 Claude 的浏览器：默认浏览器和 --browser 不是同一个、两个都设好了时填默认浏览器")
    p.add_argument("--no-open", action="store_true", help="不自动打开浏览器，只打印检测页地址")
    p.add_argument("--skip-browser", action="store_true", help="跳过浏览器部分（指纹、WebRTC、浏览器 DNS）")
    p.add_argument("--no-claude", action="store_true",
                   help="检测页完全不访问 claude.ai（还在用临时代理做基线检测时用）")
    p.add_argument("--timeout", type=float, default=180, help="等待浏览器回传的秒数")
    p.add_argument("--full", action="store_true", help="JSON 里保留真实 IP（默认打码，便于交给 AI 解读）")
    p.add_argument("--json", type=Path, default=Path(tempfile.gettempdir()) / "claude-antiban-report.json",
                   help="完整结果 JSON 的保存路径")
    args = p.parse_args(argv)
    if not args.browser:
        p.error(f"先问用户登录 Claude 用的是哪个浏览器，再加 --browser <浏览器>（这台电脑的默认浏览器是 "
                f"{default_browser()['name']}）。检测页不会自动在默认浏览器里打开：要测的是登录 Claude 的那个浏览器")
    if args.also == args.browser:
        p.error("--also 是另一个也会碰到 Claude 的浏览器，不能和 --browser 相同")
    return args


def out(text: str = "") -> None:
    """Single print choke point: remote strings must not inject terminal escapes."""
    print(CTRL_CHARS.sub("?", text))


def redact_proxy(value: Optional[str]) -> Optional[str]:
    """Hide user:password in proxy URLs before printing or saving them."""
    return CREDENTIALS.sub("//***@", value) if value else value


# ---------------------------------------------------------------- discovery

def discover_proxies() -> Json:
    env_p, source = nc.env_proxy(), "HTTPS_PROXY"
    if not env_p:
        env_p, source = nc.claude_settings_proxy(), "~/.claude/settings.json"
    sys_p = nc.system_proxy()
    persistent = nc.persistent_env_proxy() or {}
    return {"system": sys_p, "env": env_p, "env_source": source if env_p else None,
            "api": env_p or sys_p, "pac": nc.system_proxy_pac(),
            "persistent": {k: redact_proxy(v) for k, v in persistent.items()}}


def local_clock() -> Json:
    """System time zone from the OS (IANA name when it can be determined)."""
    now = time.localtime()
    clock = {"timezone": None, "name": time.tzname[now.tm_isdst > 0],
             "offset_min": (now.tm_gmtoff or 0) // 60, "source": "system"}
    if sys.platform == "win32":
        import winreg

        try:
            path = r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                win_name = winreg.QueryValueEx(key, "TimeZoneKeyName")[0]
            clock["name"], clock["timezone"] = win_name, WINDOWS_TO_IANA.get(win_name)
        except OSError:
            pass
    else:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            clock["timezone"] = target.split("zoneinfo/", 1)[1]
    return clock


# ---------------------------------------------------------------- probes

def start_script_probes(pool: ThreadPoolExecutor, px: Json) -> dict[str, Any]:
    """Kick off every script-side probe; they run while the browser page works.

    Geo, Cloudflare and reputation lookups only run through a proxy, so the
    real IP is not fanned out to extra third parties when no proxy is set.
    """
    proxied = px["api"] is not None
    return {
        "echo_system": pool.submit(nc.echo_ip, px["system"]) if px["system"] else None,
        "echo_env": pool.submit(nc.echo_ip, px["env"]) if px["env"] else None,
        "echo_direct": pool.submit(nc.echo_ip, None),
        "geo": pool.submit(nc.geo_lookup, px["api"]) if proxied else None,
        "colo": pool.submit(nc.cloudflare_colo, px["api"]) if proxied else None,
        "dns_os": pool.submit(nc.dns_os_resolver, px["api"]),
        "ipv6_direct": pool.submit(nc.direct_ipv6),
        "domestic_dns": pool.submit(ec.domestic_dns_probe),
    }


def sanitize_browser(browser: Optional[Json]) -> Optional[Json]:
    """The page's answers come from third-party responses: keep only well-formed values."""
    if not isinstance(browser, dict):
        return None
    for key in ("neutralTrace", "claudeTrace"):
        trace = browser.get(key)
        if isinstance(trace, dict) and nc.valid_ip(trace.get("ip")):
            loc = str(trace.get("loc") or "")
            browser[key] = {"ip": nc.valid_ip(trace.get("ip")), "colo": str(trace.get("colo") or "")[:8],
                            "loc": loc if re.fullmatch(r"[A-Z]{2}", loc) else None}
        else:
            browser[key] = None
    browser["ipv6"] = nc.valid_ip(browser.get("ipv6")) if browser.get("ipv6") else None
    return browser


def run_browser(px: Json, args: argparse.Namespace) -> tuple[Optional[Json], list[str], str]:
    if args.skip_browser:
        return None, [], "skipped"
    try:
        ids = nc.dns_register(px["api"])
    except Exception as exc:  # noqa: BLE001 - DNS part is optional
        out(f"（dnsleaktest 注册失败，浏览器 DNS 检测跳过：{exc}）")
        ids = []
    target = getattr(args, "browser", None)
    opener = None if args.no_open or not target else (lambda url: br.open_url(target, url))
    label = br.display(target) if target else "你登录 Claude 的那个浏览器"
    raw = run_in_browser({"dnsIds": ids, "skipClaude": args.no_claude},
                         opener=opener, label=label, timeout=args.timeout)
    if isinstance(raw, dict) and raw.get("error"):
        out(f"浏览器检测页出错：{str(raw['error'])[:200]}")
        return None, ids, "error"
    result = sanitize_browser(raw)
    if result is not None:
        result["claudeSkipped"] = bool(args.no_claude)  # 以脚本自己的参数为准，不信页面传回的
        env = result.get("env")
        result["seen"] = br.identify(env if isinstance(env, dict) else {})  # 检测页实际跑在哪个浏览器里
    return result, ids, "ok" if result else "timeout"


def browser_clock(browser: Json) -> Json:
    env = browser.get("env") or {}
    offset = env.get("utcOffsetMinutes")
    return {"timezone": env.get("timeZone"), "source": "browser",
            "offset_min": offset if isinstance(offset, int) else None}


def default_browser() -> Json:
    try:
        return br.default_browser()
    except Exception as exc:  # noqa: BLE001 - registry layouts vary; this item is optional
        return {"key": None, "name": f"没查到（{type(exc).__name__}）", "domestic": False}


def build_report(px: Json, futures: dict[str, Any], browser: Optional[Json],
                 dns_ids: list[str], browser_status: str,
                 claude_browsers: Optional[list[str]] = None) -> Json:
    def value(name: str) -> Json:
        fut = futures.get(name)
        if not fut:
            return {}
        try:
            return fut.result(timeout=PROBE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - includes TimeoutError
            return {"error": f"{type(exc).__name__}: {exc}"[:200]}

    geo = value("geo")
    report: Json = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "platform": sys.platform,
        "browser_status": browser_status,
        "browser": browser,
        # 用户登录 Claude 的浏览器（--browser，加上 --also）；默认浏览器也要算在里面才安全
        "claude_browsers": claude_browsers or [],
        "default_browser": default_browser(),
        "system_proxy_pac": px["pac"],
        "paths": {
            "system_proxy": {"proxy": redact_proxy(px["system"]), "echo": value("echo_system")},
            "env_proxy": {"proxy": redact_proxy(px["env"]), "source": px["env_source"],
                          "echo": value("echo_env"), "persistent": px["persistent"]},
            "direct": {"echo": value("echo_direct")},
        },
        "geo": geo if "error" not in geo else {},
        "consensus": fd.consensus(geo if "error" not in geo else {}),
        "colo": value("colo"),
        "dns": {"os": value("dns_os"), "browser": None},
        "ipv6": {"direct": value("ipv6_direct"), "browser": (browser or {}).get("ipv6")},
        "clock": browser_clock(browser) if browser else local_clock(),
        "secure_dns": ec.browser_secure_dns(),
        "domestic_dns": value("domestic_dns"),
    }
    add_followups(report, px, dns_ids)
    return report


def add_followups(report: Json, px: Json, dns_ids: list[str]) -> None:
    """Checks that need the browser result or the final exit IP (only through a proxy)."""
    if dns_ids and report["browser"]:
        try:
            report["dns"]["browser"] = {"servers": nc.dns_servers(dns_ids, px["api"])}
        except Exception as exc:  # noqa: BLE001
            report["dns"]["browser"] = {"error": str(exc)}
    if report["ipv6"]["browser"] and px["api"]:
        report["ipv6"]["browser_geo"] = nc.ip_country(report["ipv6"]["browser"], px["api"])
    exit_addr = fd.exit_ip(report)
    exposed = exit_addr is None or exit_addr == fd.real_ip(report)
    report["reputation"] = {} if exposed or not px["api"] else nc.ip_reputation(exit_addr, px["api"])


# ---------------------------------------------------------------- output

def print_report(report: Json, items: list[Json], json_path: Path) -> None:
    cons, colo = report["consensus"], report["colo"]
    mine, exit_addr = fd.real_ip(report), fd.exit_ip(report)
    hide = (lambda s: s.replace(mine, fd.mask_ip(mine))) if mine else (lambda s: s)
    exposed = fd.exit_country(report) in fd.RESTRICTED or (exit_addr is not None and exit_addr == mine)
    out("\n================ Claude 防封环境自检 ================")
    out(hide(f"代理出口：{exit_addr}，Cloudflare 机房 {colo.get('colo', '?')}"))
    for place in [] if exposed else cons["places"]:
        out(f"  IP 库  {place}")
    if report["browser_status"] in ("timeout", "error"):
        out("浏览器部分没有结果：指纹、WebRTC、浏览器 DNS 这几项缺失。")
    out()
    for item in items:
        out(f"{ICON[item['level']]:<5}{item['title']}")
        out(hide(f"      {item['summary']}"))
        if item.get("fix"):
            out(f"      → 修法见 {FIX_REFS.get(item['fix'], item['fix'])}")
    counts = {lvl: sum(1 for i in items if i["level"] == lvl) for lvl in ("bad", "warn", "ok", "info")}
    out(f"\n汇总：严重 {counts['bad']}，注意 {counts['warn']}，通过 {counts['ok']}，提示 {counts['info']}")
    out(f"完整结果：{json_path}")


def save_report(report: Json, path: Path, full: bool) -> None:
    """Write the JSON (owner-only on POSIX); the real IP is masked unless --full."""
    mine = fd.real_ip(report)
    if mine and not full:
        report["paths"]["direct"]["echo"].pop("raw", None)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if mine and not full:
        text = text.replace(mine, fd.mask_ip(mine))
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(text)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    px = discover_proxies()
    out(f"系统代理：{redact_proxy(px['system']) or ('PAC/自动检测' if px['pac'] else '未设置')}；"
        f"Claude Code 代理：{redact_proxy(px['env']) or '未设置'}")
    pool = ThreadPoolExecutor(max_workers=8)
    try:
        futures = start_script_probes(pool, px)
        browser, dns_ids, status = run_browser(px, args)
        claude_browsers = [b for b in (args.browser, args.also) if b]
        report = build_report(px, futures, browser, dns_ids, status, claude_browsers)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)  # never block on a stuck probe
    items = fd.evaluate(report)
    report["findings"] = items
    save_report(report, args.json, args.full)
    print_report(report, items, args.json)
    return 1 if any(i["level"] == "bad" for i in items) else 0


if __name__ == "__main__":
    sys.exit(main())
