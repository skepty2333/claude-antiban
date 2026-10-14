"""Script-side network probes. Python standard library only.

Safety rule: nothing in this module contacts Claude or Anthropic hosts. The
"direct" path may expose the user's real IP, so it only talks to neutral
what-is-my-IP services.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

Json = dict[str, Any]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
TIMEOUT = 12
IPV4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

# Neutral IPv4 echo services. Overseas ones first: under rule mode, Chinese sites are often
# routed DIRECT and would report the real IP. The Chinese ones are a last resort.
ECHO_ENDPOINTS = ("https://checkip.amazonaws.com", "https://icanhazip.com", "https://ifconfig.me/ip",
                  "https://api.ipify.org", "https://myip.ipip.net", "https://4.ipw.cn")
DNSLEAKTEST_API = "https://www.dnsleaktest.com/api/v1/"
IPV6_PROBES = (("2606:4700:4700::1111", 443), ("2001:4860:4860::8888", 443))
FORBIDDEN_HOSTS = ("claude.ai", "claude.com", "anthropic.com")
MAX_BYTES = 1_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: a 3xx must not steer us to another host (e.g. claude.ai)."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _opener(proxy: Optional[str]) -> urllib.request.OpenerDirector:
    """proxy=None means a truly direct connection (ignores env and system proxy)."""
    mapping = {"http": proxy, "https": proxy} if proxy else {}
    return urllib.request.build_opener(urllib.request.ProxyHandler(mapping), _NoRedirect)


def _assert_allowed(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in FORBIDDEN_HOSTS):
        raise ValueError(f"refusing to contact {host} from a script")


def valid_ip(value: Any) -> Optional[str]:
    """Return value if it is a literal IPv4/IPv6 address, else None (untrusted input)."""
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def fetch(url: str, proxy: Optional[str] = None, payload: Any = None,
          timeout: float = TIMEOUT) -> str:
    _assert_allowed(url)
    headers = {"User-Agent": UA}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with _opener(proxy).open(req, timeout=timeout) as resp:
        return resp.read(MAX_BYTES).decode("utf-8", "replace")


def fetch_json(url: str, proxy: Optional[str] = None, payload: Any = None,
               timeout: float = TIMEOUT) -> Any:
    return json.loads(fetch(url, proxy, payload, timeout))


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


# ---------------------------------------------------------------- proxies

def _normalize_proxy(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if "://" not in value:
        value = "http://" + value
    return value


def system_proxy() -> Optional[str]:
    """The proxy that 'follow the system proxy' apps (browsers, Electron) use."""
    getter = None
    if sys.platform == "win32":
        getter = getattr(urllib.request, "getproxies_registry", None)
    elif sys.platform == "darwin":
        getter = getattr(urllib.request, "getproxies_macosx_sysconf", None)
    found = getter() if getter else {}
    return _normalize_proxy(found.get("https") or found.get("http"))


def system_proxy_pac() -> bool:
    """Windows: is a PAC script / auto-detect configured? (urllib cannot evaluate PAC.)"""
    if sys.platform != "win32":
        return False
    import winreg

    path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            for name in ("AutoConfigURL", "AutoDetect"):
                try:
                    if winreg.QueryValueEx(key, name)[0]:
                        return True
                except FileNotFoundError:
                    continue
    except OSError:
        pass
    return False


def claude_settings_proxy() -> Optional[str]:
    """HTTPS_PROXY / HTTP_PROXY set in ~/.claude/settings.json "env" (read by Claude Code)."""
    path = Path.home() / ".claude" / "settings.json"
    try:
        env = json.loads(path.read_text(encoding="utf-8")).get("env") or {}
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(env, dict):
        return None
    return _normalize_proxy(env.get("HTTPS_PROXY") or env.get("https_proxy")
                            or env.get("HTTP_PROXY") or env.get("http_proxy"))


def env_proxy() -> Optional[str]:
    """HTTPS_PROXY / HTTP_PROXY of this process (what Claude Code CLI reads)."""
    found = urllib.request.getproxies_environment()
    return _normalize_proxy(found.get("https") or found.get("http"))


def persistent_env_proxy() -> Optional[dict[str, str]]:
    """Windows only: proxy variables saved for new processes (User / Machine)."""
    if sys.platform != "win32":
        return None
    import winreg

    places = (
        (winreg.HKEY_CURRENT_USER, r"Environment", "User"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", "Machine"),
    )
    found = {}
    for root, path, scope in places:
        try:
            with winreg.OpenKey(root, path) as key:
                for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "NODE_USE_ENV_PROXY"):
                    try:
                        found[f"{scope}:{name}"] = winreg.QueryValueEx(key, name)[0]
                    except FileNotFoundError:
                        pass
        except OSError:
            continue
    return found


# ---------------------------------------------------------------- egress

def echo_ip(proxy: Optional[str]) -> Json:
    """Exit IPv4 seen by neutral echo services through `proxy` (None = direct)."""
    if proxy and proxy.lower().startswith("socks"):
        return {"error": "SOCKS 代理，脚本（标准库）无法经它探测"}
    errors = []
    for url in ECHO_ENDPOINTS:
        try:
            body = fetch(url, proxy, timeout=8)
        except Exception as exc:  # noqa: BLE001 - every failure is just "try next"
            errors.append(f"{url} {_err(exc)}")
            continue
        match = IPV4_RE.search(body)
        if match and valid_ip(match.group(1)):
            return {"ip": match.group(1), "endpoint": url, "raw": body.strip()[:160]}
        errors.append(f"{url} no IPv4 in reply")
    return {"error": " | ".join(errors)}


def cloudflare_colo(proxy: Optional[str]) -> Json:
    """Cloudflare edge that served us: a hint of where the exit node really is."""
    try:
        text = fetch("https://1.1.1.1/cdn-cgi/trace", proxy, timeout=8)
    except Exception as exc:  # noqa: BLE001
        return {"error": _err(exc)}
    trace = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return {"ip": trace.get("ip"), "colo": trace.get("colo"), "loc": trace.get("loc")}


# ---------------------------------------------------------------- geo + quality

def _geo_ipapi_com(proxy: Optional[str]) -> Json:
    j = fetch_json("http://ip-api.com/json/?fields=status,query,countryCode,regionName,"
                   "city,timezone,offset,isp,as,proxy,hosting,mobile", proxy)
    if j.get("status") != "success":
        raise ValueError(f"ip-api status {j.get('status')}")
    return {"ip": j.get("query"), "country": j.get("countryCode"), "region": j.get("regionName"),
            "city": j.get("city"), "timezone": j.get("timezone"),
            "offset_min": (j["offset"] // 60) if isinstance(j.get("offset"), int) else None,
            "isp": j.get("isp"), "flags": {k: j.get(k) for k in ("proxy", "hosting", "mobile")}}


def _geo_ipapi_co(proxy: Optional[str]) -> Json:
    j = fetch_json("https://ipapi.co/json/", proxy)
    if j.get("error"):
        raise ValueError(f"ipapi.co: {j.get('reason')}")
    off = j.get("utc_offset") or ""
    minutes = None
    if re.fullmatch(r"[+-]\d{4}", off):
        minutes = (1 if off[0] == "+" else -1) * (int(off[1:3]) * 60 + int(off[3:]))
    return {"ip": j.get("ip"), "country": j.get("country_code"), "region": j.get("region"),
            "city": j.get("city"), "timezone": j.get("timezone"), "offset_min": minutes,
            "isp": j.get("org")}


def _geo_ipwho_is(proxy: Optional[str]) -> Json:
    j = fetch_json("https://ipwho.is/", proxy)
    if j.get("success") is False:
        raise ValueError(f"ipwho.is: {j.get('message')}")
    tz = j.get("timezone") or {}
    offset = tz.get("offset")
    return {"ip": j.get("ip"), "country": j.get("country_code"), "region": j.get("region"),
            "city": j.get("city"), "timezone": tz.get("id"),
            "offset_min": offset // 60 if isinstance(offset, int) else None,
            "isp": (j.get("connection") or {}).get("isp")}


def _geo_ipinfo_io(proxy: Optional[str]) -> Json:
    j = fetch_json("https://ipinfo.io/json", proxy)
    return {"ip": j.get("ip"), "country": j.get("country"), "region": j.get("region"),
            "city": j.get("city"), "timezone": j.get("timezone"), "offset_min": None,
            "isp": j.get("org")}


GEO_SOURCES = {
    "ip-api.com": _geo_ipapi_com,
    "ipapi.co": _geo_ipapi_co,
    "ipwho.is": _geo_ipwho_is,
    "ipinfo.io": _geo_ipinfo_io,
}


def geo_lookup(proxy: Optional[str]) -> dict[str, Json]:
    """Ask several independent geo databases about the exit IP of `proxy`."""
    def run(item: tuple) -> tuple[str, Json]:
        name, func = item
        try:
            return name, func(proxy)
        except Exception as exc:  # noqa: BLE001
            return name, {"error": _err(exc)}

    with ThreadPoolExecutor(max_workers=len(GEO_SOURCES)) as pool:
        return dict(pool.map(run, GEO_SOURCES.items()))


def ip_reputation(ip: str, proxy: Optional[str]) -> Json:
    """Residential / datacenter / abuse view from ip.net.coffee (third-party, best effort)."""
    if not valid_ip(ip):
        return {"error": "not an IP address"}
    keys = ("isResidential", "is_datacenter", "is_proxy", "is_vpn", "is_abuser", "abuser_score",
            "company_type", "company_name", "asOrganization", "trust_score")
    try:
        j = fetch_json(f"https://ip.net.coffee/api/iprisk/{ip}", proxy, timeout=15)
    except Exception as exc:  # noqa: BLE001
        return {"error": _err(exc)}
    return {k: j.get(k) for k in keys}


# ---------------------------------------------------------------- DNS

def dns_register(api_proxy: Optional[str], count: int = 6) -> list[str]:
    ids = [str(uuid.uuid4()) for _ in range(count)]
    fetch_json(DNSLEAKTEST_API + "identifiers", api_proxy, {"identifiers": ids})
    return ids


def dns_servers(ids: list[str], api_proxy: Optional[str]) -> list[Json]:
    """Resolvers dnsleaktest.com saw for these identifiers."""
    rows = fetch_json(DNSLEAKTEST_API + "servers-for-result", api_proxy, {"queries": ids})
    keep = ("ip_address", "isp", "country_code", "country", "city")
    return [{k: row.get(k) for k in keep} for row in rows]


def _os_lookup(name: str) -> bool:
    try:
        socket.getaddrinfo(name, 443, socket.AF_INET)
        return True
    except OSError:
        return False


def dns_os_resolver(api_proxy: Optional[str]) -> Json:
    """Resolve fresh names through the operating-system resolver (no proxy involved)."""
    try:
        ids = dns_register(api_proxy)
        with ThreadPoolExecutor(max_workers=len(ids)) as pool:
            resolved = sum(pool.map(_os_lookup, [f"{i}.test.dnsleaktest.com" for i in ids]))
        servers = dns_servers(ids, api_proxy)
        if not servers and resolved:
            time.sleep(1.5)  # the API can lag a moment behind the lookups
            servers = dns_servers(ids, api_proxy)
        return {"servers": servers, "lookups_ok": resolved, "lookups": len(ids)}
    except Exception as exc:  # noqa: BLE001
        return {"error": _err(exc)}


# ---------------------------------------------------------------- IPv6

def direct_ipv6() -> Json:
    """Can this machine open an IPv6 connection without any proxy?"""
    last = ""
    for host, port in IPV6_PROBES:
        try:
            with socket.create_connection((host, port), timeout=4):
                pass
        except OSError as exc:
            last = _err(exc)
            continue
        result = {"reachable": True, "probe": host}
        try:
            result["ip"] = valid_ip(fetch("https://api6.ipify.org", None, timeout=8))
        except Exception as exc:  # noqa: BLE001
            result["ip_error"] = _err(exc)
        return result
    return {"reachable": False, "error": last}


def ip_country(ip: str, proxy: Optional[str]) -> Json:
    if not valid_ip(ip):
        return {"error": "not an IP address"}
    try:
        j = fetch_json(f"https://ipwho.is/{ip}", proxy)
        return {"country": j.get("country_code"), "isp": (j.get("connection") or {}).get("isp")}
    except Exception as exc:  # noqa: BLE001
        return {"error": _err(exc)}
