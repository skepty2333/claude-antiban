"""Default browser lookup, browser identification from the page's UA, and opening a named browser."""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import browsers as br  # noqa: E402
import findings as fd  # noqa: E402
from clash_rules import BROWSERS  # noqa: E402

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"


def test_browser_keys_match_the_clash_rules_and_findings():
    assert set(br.KNOWN) == set(BROWSERS) == set(fd.BROWSER_NAMES)
    assert all(br.KNOWN[k].name == fd.BROWSER_NAMES[k] for k in br.KNOWN)


@pytest.mark.parametrize("progid,exe,key", [
    ("ChromeHTML", r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome"),
    ("MSEdgeHTM", None, "edge"),
    ("FirefoxURL-308046B0AF4A39CB", None, "firefox"),
    ("BraveHTML", None, "brave"),
    ("AppXq0fevzme2pys62n3e0fbqa7peapykr8v", r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome"),
    ("360SE6HTML", r"C:\Users\a\AppData\Roaming\360se6\Application\360se.exe", None),
    ("SomethingElse", None, None),
    ("ChromeHTML", r"C:\Users\li360\AppData\Local\Google\Chrome\Application\chrome.exe", "chrome"),  # user name
])
def test_key_for_progid_or_exe(progid, exe, key):
    assert br.key_for(progid=progid, exe_path=exe) == key


@pytest.mark.parametrize("env,key", [
    ({"userAgent": CHROME_UA}, "chrome"),
    ({"userAgent": CHROME_UA, "brave": True}, "brave"),
    ({"userAgent": CHROME_UA + " Edg/141.0.0.0"}, "edge"),
    ({"userAgent": "Mozilla/5.0 (Windows NT 10.0; rv:131.0) Gecko/20100101 Firefox/131.0"}, "firefox"),
    ({"userAgent": CHROME_UA + " QQBrowser/13.0"}, None),
    ({"userAgent": CHROME_UA.replace("141.0.0.0", "136.0.7103.360")}, "chrome"),  # "360" in a version number
    ({"userAgent": CHROME_UA + " OPR/120.0.0.0"}, None),                           # Opera is not Chrome
    ({"userAgent": CHROME_UA + " Vivaldi/7.1"}, None),
    ({}, None),
])
def test_identify_from_user_agent(env, key):
    assert br.identify(env) == key


def test_command_exe_handles_quotes_and_bare_paths():
    assert br._command_exe('"C:\\Program Files\\x\\chrome.exe" --single-argument %1') == "C:\\Program Files\\x\\chrome.exe"
    assert br._command_exe("C:\\x\\firefox.exe -osint -url %1") == "C:\\x\\firefox.exe"
    assert br._command_exe(None) is None


def test_windows_default_prefers_user_choice_latest_then_user_choice_then_http(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("uses winreg constants")
    values = {"http\\UserChoice": "FirefoxURL-1"}

    def fake_reg(root, path, name=""):
        for key, value in values.items():
            if path.endswith(key) and name == "ProgId":
                return value
        return None

    monkeypatch.setattr(br, "_reg", fake_reg)
    assert br._windows_default()["progid"] == "FirefoxURL-1"          # https missing: falls back to http
    values["https\\UserChoice"] = "MSEdgeHTM"
    assert br._windows_default()["progid"] == "MSEdgeHTM"
    values["https\\UserChoiceLatest\\ProgId"] = "ChromeHTML"
    assert br._windows_default()["progid"] == "ChromeHTML"


def test_default_browser_on_windows_names_domestic_ones(monkeypatch):
    monkeypatch.setattr(br, "_windows_default",
                        lambda: {"progid": "360SE6HTML", "exe": r"C:\x\360se6\Application\360se.exe"})
    result = br.default_browser("win32")
    assert result["key"] is None and result["domestic"] and result["name"] == "360se"


def test_mac_default_reads_launch_services(tmp_path):
    plist = tmp_path / br.MAC_LAUNCH_SERVICES
    plist.parent.mkdir(parents=True)
    plist.write_bytes(plistlib.dumps({"LSHandlers": [
        {"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"},
        {"LSHandlerURLScheme": "https", "LSHandlerRoleAll": "com.google.Chrome"},
    ]}))
    assert br._mac_default(tmp_path) == {"bundle": "com.google.Chrome"}
    assert br.key_for(bundle="com.google.Chrome") == "chrome"


def test_mac_default_without_settings_is_safari(tmp_path):
    assert br._mac_default(tmp_path) == {"bundle": "com.apple.safari"}


def test_open_url_starts_the_named_browser(monkeypatch):
    started = []
    monkeypatch.setattr(br, "find_exe", lambda key, platform=None: r"C:\x\chrome.exe" if key == "chrome" else None)
    monkeypatch.setattr(br.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    assert br.open_url("chrome", "http://127.0.0.1:1/check.html", "win32")
    assert started == [[r"C:\x\chrome.exe", "http://127.0.0.1:1/check.html"]]
    assert not br.open_url("firefox", "http://127.0.0.1:1/check.html", "win32")


def test_windows_exe_falls_back_to_install_dirs(monkeypatch, tmp_path):
    if sys.platform != "win32":
        pytest.skip("reads the Windows registry first")
    exe = tmp_path / "Mozilla Firefox" / "firefox.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(br, "_reg", lambda *a, **k: None)
    assert br._windows_exe("firefox", {"ProgramFiles": str(tmp_path)}) == str(exe)
