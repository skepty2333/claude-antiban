"""本机的浏览器：默认浏览器是哪个、装了哪些；在指定的浏览器里打开网址；认出检测页跑在哪个浏览器里。

只用标准库，只读。Claude 桌面端、Claude Code 登录时，还有邮件里的登录链接，都用默认浏览器打开，
所以默认浏览器也会碰到 Claude，配置前要先弄清它是哪个。

    python browsers.py          # 默认浏览器、装了哪些浏览器
    python browsers.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

Json = dict[str, Any]


@dataclass(frozen=True)
class Browser:
    name: str
    exe: str                   # Windows 进程名
    progids: tuple[str, ...]   # Windows 默认浏览器登记的 ProgId（前缀匹配）
    win_dirs: tuple[str, ...]  # 常见安装位置：(环境变量, 相对路径)
    mac_app: str
    bundle: str


# 键名和 setup/clash_rules.py 的 BROWSERS 一致
KNOWN: dict[str, Browser] = {
    "chrome": Browser("Chrome", "chrome.exe", ("ChromeHTML",),
                      ("ProgramFiles|Google/Chrome/Application", "ProgramFiles(x86)|Google/Chrome/Application",
                       "LOCALAPPDATA|Google/Chrome/Application"),
                      "Google Chrome", "com.google.chrome"),
    "edge": Browser("Edge", "msedge.exe", ("MSEdgeHTM",),
                    ("ProgramFiles(x86)|Microsoft/Edge/Application", "ProgramFiles|Microsoft/Edge/Application"),
                    "Microsoft Edge", "com.microsoft.edgemac"),
    "firefox": Browser("Firefox", "firefox.exe", ("FirefoxURL", "FirefoxHTML"),
                       ("ProgramFiles|Mozilla Firefox", "ProgramFiles(x86)|Mozilla Firefox"),
                       "Firefox", "org.mozilla.firefox"),
    "brave": Browser("Brave", "brave.exe", ("BraveHTML",),
                     ("ProgramFiles|BraveSoftware/Brave-Browser/Application",
                      "LOCALAPPDATA|BraveSoftware/Brave-Browser/Application"),
                     "Brave Browser", "com.brave.browser"),
}
# 国产浏览器在 ProgId、程序路径里（DOMESTIC_HINTS）和 UA 里（DOMESTIC_UA）常带的字样，小写。
# UA 里不能只找 "360"：版本号里也可能出现。
DOMESTIC_HINTS = ("360", "qqbrowser", "sogou", "2345explorer", "quark", "ucbrowser", "liebao", "maxthon",
                  "huaweibrowser", "bitbrowser")
DOMESTIC_UA = ("qihu", "360se", "360ee", "qqbrowser", "metasr", "2345explorer", "quark", "ucbrowser",
               "lbbrowser", "maxthon", "huaweibrowser", "bitbrowser")
# 带着 Chrome/ 字样、却不是 Chrome 的 Chromium 系浏览器
OTHER_CHROMIUM_UA = ("opr/", "vivaldi/", "yabrowser/", "samsungbrowser/", "slbrowser/", "whale/")
USER_CHOICE = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{}\{}"
APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{}"
MAC_LAUNCH_SERVICES = "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"


def is_domestic(*texts: Optional[str], hints: tuple[str, ...] = DOMESTIC_HINTS) -> bool:
    joined = " ".join(t for t in texts if t).lower()
    return any(hint in joined for hint in hints)


def _exe_names(exe_path: Optional[str]) -> str:
    """程序名和它所在的文件夹名：只看这两级，用户名里带 360 之类的不算。"""
    if not exe_path:
        return ""
    path = Path(exe_path)
    return f"{path.parent.name} {path.name}"


def key_for(progid: Optional[str] = None, exe_path: Optional[str] = None, bundle: Optional[str] = None) -> Optional[str]:
    """把 ProgId、程序路径或 macOS 的 bundle id 对到 KNOWN 里的键；国产浏览器、认不出的返回 None。"""
    if is_domestic(progid, _exe_names(exe_path)):
        return None
    exe = Path(exe_path).name.lower() if exe_path else ""
    for key, browser in KNOWN.items():
        if progid and progid.startswith(browser.progids):
            return key
        if exe and exe == browser.exe:
            return key
        if bundle and bundle.lower() == browser.bundle:
            return key
    return None


def identify(env: Mapping[str, Any]) -> Optional[str]:
    """检测页回传的 userAgent（加上 navigator.brave 有没有）认出是哪个浏览器；国产或认不出的返回 None。"""
    ua = str(env.get("userAgent") or "")
    if not ua or is_domestic(ua, hints=DOMESTIC_UA) or is_domestic(ua, hints=OTHER_CHROMIUM_UA):
        return None
    if "Edg/" in ua:
        return "edge"
    if "Firefox/" in ua:
        return "firefox"
    if env.get("brave"):
        return "brave"
    if "Chrome/" in ua:
        return "chrome"
    return None


def display(key: Optional[str]) -> str:
    return KNOWN[key].name if key in KNOWN else "认不出的浏览器"


# ---------------------------------------------------------------- Windows

def _reg(root: Any, path: str, name: str = "") -> Optional[str]:
    import winreg
    try:
        with winreg.OpenKey(root, path) as handle:
            value = winreg.QueryValueEx(handle, name)[0]
            return str(value) if value else None
    except OSError:
        return None


def _command_exe(command: Optional[str]) -> Optional[str]:
    """`"C:\\...\\chrome.exe" --single-argument %1` 里的程序路径。"""
    if not command:
        return None
    match = re.match(r'\s*"([^"]+)"', command) or re.match(r"\s*(\S+)", command)
    return match.group(1) if match else None


def _windows_default() -> Json:
    import winreg
    progid = None
    for scheme in ("https", "http"):
        progid = (_reg(winreg.HKEY_CURRENT_USER, USER_CHOICE.format(scheme, r"UserChoiceLatest\ProgId"), "ProgId")
                  or _reg(winreg.HKEY_CURRENT_USER, USER_CHOICE.format(scheme, "UserChoice"), "ProgId"))
        if progid:
            break
    exe = _command_exe(_reg(winreg.HKEY_CLASSES_ROOT, rf"{progid}\shell\open\command")) if progid else None
    return {"progid": progid, "exe": exe}


def _windows_exe(key: str, env: Mapping[str, str] = os.environ) -> Optional[str]:
    import winreg
    browser = KNOWN[key]
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        path = _reg(root, APP_PATHS.format(browser.exe))
        if path and Path(path.strip('"')).is_file():
            return path.strip('"')
    for entry in browser.win_dirs:
        var, rel = entry.split("|")
        if env.get(var) and (Path(env[var]) / rel / browser.exe).is_file():
            return str(Path(env[var]) / rel / browser.exe)
    return None


# ---------------------------------------------------------------- macOS（没有在真机上验证过）

def _mac_default(home: Optional[Path] = None) -> Json:
    path = (home or Path.home()) / MAC_LAUNCH_SERVICES
    try:
        handlers = plistlib.loads(path.read_bytes()).get("LSHandlers", [])
    except (OSError, plistlib.InvalidFileException, ValueError):
        handlers = []
    bundle = next((h.get("LSHandlerRoleAll") for h in handlers if h.get("LSHandlerURLScheme") == "https"), None)
    return {"bundle": bundle or "com.apple.safari"}


def _mac_exe(key: str) -> Optional[str]:
    app = f"{KNOWN[key].mac_app}.app"
    for root in (Path("/Applications"), Path.home() / "Applications"):
        if (root / app).is_dir():
            return str(root / app)
    return None


# ---------------------------------------------------------------- 对外

def default_browser(platform: str = sys.platform) -> Json:
    """{"key": chrome/edge/firefox/brave 或 None, "name", "domestic", 以及原始的 progid/exe/bundle}。"""
    if platform == "win32":
        raw = _windows_default()
        key = key_for(progid=raw["progid"], exe_path=raw["exe"])
        domestic = is_domestic(raw["progid"], _exe_names(raw["exe"]))
        shown = display(key) if key else (Path(raw["exe"]).stem if raw["exe"] else raw["progid"] or "没查到")
    elif platform == "darwin":
        raw = _mac_default()
        key = key_for(bundle=raw["bundle"])
        domestic = False
        shown = display(key) if key else ("Safari" if raw["bundle"] == "com.apple.safari" else raw["bundle"])
    else:
        return {"key": None, "name": "没查（这个系统不检查默认浏览器）", "domestic": False}
    return {"key": key, "name": shown, "domestic": domestic, **raw}


def find_exe(key: str, platform: str = sys.platform) -> Optional[str]:
    if key not in KNOWN:
        return None
    if platform == "win32":
        return _windows_exe(key)
    if platform == "darwin":
        return _mac_exe(key)
    return None


def installed(platform: str = sys.platform) -> list[str]:
    return [key for key in KNOWN if find_exe(key, platform)]


def open_url(key: str, url: str, platform: str = sys.platform) -> bool:
    """在指定的浏览器里打开网址；没找到这个浏览器返回 False。"""
    exe = find_exe(key, platform)
    if not exe:
        return False
    try:
        if platform == "darwin":
            return subprocess.run(["open", "-a", exe, url], capture_output=True, timeout=20).returncode == 0
        subprocess.Popen([exe, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="默认浏览器和装了哪些浏览器（claude-antiban）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = {"default": default_browser(), "installed": installed()}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    default = result["default"]
    tail = "（国产浏览器，不能用来打开 Claude 网页版）" if default["domestic"] else ""
    print(f"默认浏览器：{default['name']}{tail}")
    print(f"装了的浏览器：{'、'.join(display(k) for k in result['installed']) or '没找到 Chrome、Edge、Firefox、Brave'}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
