"""Local-machine probes: browser Secure DNS settings and "will Chinese apps lose network".

Standard library only, read-only. Nothing here talks to Claude/Anthropic.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import socket
import sys
from pathlib import Path
from typing import Any, Optional

Json = dict[str, Any]
FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")  # Clash/Mihomo fake-ip range
DOMESTIC_DOMAINS = ("www.qq.com", "www.baidu.com")


# ---------------------------------------------------------------- browser Secure DNS

def _chromium_local_states() -> dict[str, Path]:
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return {"Chrome": base / "Google/Chrome/User Data/Local State",
                "Edge": base / "Microsoft/Edge/User Data/Local State",
                "Brave": base / "BraveSoftware/Brave-Browser/User Data/Local State"}
    if sys.platform == "darwin":
        base = home / "Library/Application Support"
        return {"Chrome": base / "Google/Chrome/Local State", "Edge": base / "Microsoft Edge/Local State",
                "Brave": base / "BraveSoftware/Brave-Browser/Local State"}
    return {"Chrome": home / ".config/google-chrome/Local State",
            "Edge": home / ".config/microsoft-edge/Local State",
            "Brave": home / ".config/BraveSoftware/Brave-Browser/Local State"}


def _windows_policy(browser: str) -> Optional[str]:
    """DnsOverHttpsMode set by group policy wins over the user setting (Windows only)."""
    if sys.platform != "win32":
        return None
    import winreg

    key = {"Chrome": r"SOFTWARE\Policies\Google\Chrome", "Edge": r"SOFTWARE\Policies\Microsoft\Edge",
           "Brave": r"SOFTWARE\Policies\BraveSoftware\Brave"}[browser]
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, key) as handle:
                return str(winreg.QueryValueEx(handle, "DnsOverHttpsMode")[0])
        except OSError:
            continue
    return None


def _firefox_trr() -> Optional[Json]:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles"
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support/Firefox/Profiles"
    else:
        root = Path.home() / ".mozilla/firefox"
    modes = []
    for prefs in root.glob("*/prefs.js"):
        text = prefs.read_text(encoding="utf-8", errors="replace")
        match = (re.search(r'user_pref\("network\.trr\.mode",\s*(\d+)\)', text)
                 or re.search(r'user_pref\("doh-rollout\.mode",\s*(\d+)\)', text))
        modes.append(int(match.group(1)) if match else None)
    if not modes:
        return None
    # 2 = DoH first, 3 = DoH only; 0/5 = off. Not set at all: Firefox turns DoH on by itself in some
    # regions (the US among them), judged by the IP, so it is unknown until set to off explicitly.
    if any(m in (2, 3) for m in modes):
        return {"mode": "on", "detail": f"network.trr.mode={sorted({m for m in modes if m is not None})}"}
    if None in modes:
        return {"mode": "unknown", "detail": "没设置过（Firefox 在美国等地区会自己打开），要在设置里明确选「关闭」"}
    return {"mode": "off", "detail": f"network.trr.mode={sorted(set(modes))}"}


def browser_secure_dns() -> dict[str, Json]:
    """Secure DNS (DoH) state per installed browser."""
    found: dict[str, Json] = {}
    for name, path in _chromium_local_states().items():
        if not path.exists():
            continue
        try:
            doh = json.loads(path.read_text(encoding="utf-8")).get("dns_over_https") or {}
        except (OSError, ValueError):
            found[name] = {"mode": "unknown", "detail": "Local State 读不出来"}
            continue
        policy = _windows_policy(name)
        mode = policy or doh.get("mode") or "automatic"  # absent key = browser default (automatic)
        found[name] = {"mode": mode, "templates": doh.get("templates") or "",
                       "detail": "组策略" if policy else ("设置" if doh.get("mode") else "默认值")}
    firefox = _firefox_trr()
    if firefox:
        found["Firefox"] = firefox
    return found


# ---------------------------------------------------------------- will Chinese apps lose network?

def _encode_name(name: str) -> bytes:
    return b"".join(len(p).to_bytes(1, "big") + p.encode("ascii") for p in name.split(".")) + b"\0"


def _skip_name(buf: bytes, off: int) -> int:
    while True:
        length = buf[off]
        if length == 0:
            return off + 1
        if length & 0xC0 == 0xC0:  # compression pointer
            return off + 2
        off += length + 1


def dns_query_a(name: str, server: str = "127.0.0.1", timeout: float = 4, port: int = 53) -> Json:
    """Minimal UDP DNS A query (used to ask Clash's own DNS listener directly)."""
    tid = secrets.token_bytes(2)
    packet = tid + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + _encode_name(name) + b"\x00\x01\x00\x01"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (server, port))
            buf, _ = sock.recvfrom(4096)
        except socket.timeout:  # something may listen but did not answer in time
            return {"status": "timeout"}
        except OSError as exc:  # connection reset / refused: nothing listening on port 53
            return {"status": "absent", "error": type(exc).__name__}
    if buf[:2] != tid or len(buf) < 12:
        return {"status": "timeout", "error": "bad reply"}
    rcode, answers = buf[3] & 0x0F, int.from_bytes(buf[6:8], "big")
    off = _skip_name(buf, 12) + 4
    ips = []
    for _ in range(answers):
        off = _skip_name(buf, off)
        rtype, rdlen = int.from_bytes(buf[off:off + 2], "big"), int.from_bytes(buf[off + 8:off + 10], "big")
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(buf[off + 10:off + 14]))
        off += 10 + rdlen
    return {"status": "answer" if ips else ("servfail" if rcode else "empty"), "ips": ips, "rcode": rcode}


def classify(ips: list[str]) -> str:
    if not ips:
        return "fail"
    return "fake" if any(ipaddress.ip_address(ip) in FAKE_IP_NET for ip in ips) else "real"


def _os_resolve(name: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(name, 443, socket.AF_INET)})
    except OSError:
        return []


def domestic_dns_probe() -> Json:
    """How Chinese domains resolve via the OS resolver and via a local Clash DNS (if any)."""
    result: Json = {"os": {}, "clash": {}}
    answers = {}
    for name in DOMESTIC_DOMAINS:
        result["os"][name] = classify(_os_resolve(name))
        answers[name] = dns_query_a(name)
    # Every query silent or refused = no local DNS listener; otherwise silence is a failure.
    if all(a["status"] in ("absent", "timeout") for a in answers.values()):
        result["clash"] = {}
    else:
        result["clash"] = {n: classify(a.get("ips", [])) for n, a in answers.items()}
    return result
