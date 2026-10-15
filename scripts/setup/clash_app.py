"""Clash Verge Rev 程序本身：找到它、重启它、等它就绪；读系统里实际生效的代理和开机自启。

重启用"强制结束再启动"：强制结束不会清掉 Windows 的系统代理设置，Clash 没起来的那几秒，
浏览器只会连不上，不会改用真实 IP。服务模式下内核由服务托管，界面重启期间代理照常可用。
macOS 部分没有在真机上验证过。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Protocol

PROCESS = "clash-verge"
TASK_NAME = "Clash Verge"  # Clash Verge Rev 在 Windows 上用这个计划任务做开机自启
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
INTERNET_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


class ClashApp(Protocol):
    def running_exe(self) -> str | None: ...
    def stop(self) -> None: ...
    def start(self, exe: str) -> None: ...


def exe_candidates(env: Mapping[str, str] = os.environ) -> list[Path]:
    """Clash Verge 常见的安装位置（没在运行时用来找程序）。"""
    roots = [env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("ProgramW6432")]
    candidates = [Path(root) / "Clash Verge" / "clash-verge.exe" for root in roots if root]
    if env.get("LOCALAPPDATA"):
        candidates.append(Path(env["LOCALAPPDATA"]) / "Programs" / "Clash Verge" / "clash-verge.exe")
    return candidates


def find_exe(running: str | None, env: Mapping[str, str] = os.environ) -> str | None:
    if running:
        return running
    return next((str(path) for path in exe_candidates(env) if path.is_file()), None)


def _can_connect(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def wait_ready(port: int, runtime: Path, since: float, timeout: float = 30,
               connect: Callable[[int], bool] = _can_connect, sleep: Callable[[float], None] = time.sleep,
               now: Callable[[], float] = time.monotonic) -> bool:
    """等到代理端口能连上、并且 Clash 重新生成了运行配置（clash-verge.yaml 比 since 新）。"""
    deadline = now() + timeout
    while now() < deadline:
        fresh = runtime.is_file() and runtime.stat().st_mtime >= since
        if fresh and connect(port):
            return True
        sleep(0.5)
    return False


class WindowsApp:
    def running_exe(self) -> str | None:
        command = f"(Get-Process -Name '{PROCESS}' -ErrorAction SilentlyContinue | Select-Object -First 1).Path"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=20)
        path = result.stdout.strip()
        return path or None

    def stop(self) -> None:
        subprocess.run(["taskkill", "/IM", f"{PROCESS}.exe", "/F"], capture_output=True, timeout=20)
        for _ in range(40):
            if not self.running_exe():
                return
            time.sleep(0.25)

    def start(self, exe: str) -> None:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([exe], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class MacApp:
    def running_exe(self) -> str | None:
        result = subprocess.run(["pgrep", "-x", PROCESS], capture_output=True, text=True)
        return "Clash Verge" if result.returncode == 0 else None

    def stop(self) -> None:
        subprocess.run(["pkill", "-x", PROCESS], capture_output=True)
        time.sleep(2)

    def start(self, exe: str) -> None:
        subprocess.run(["open", "-a", "Clash Verge"], capture_output=True)


def platform_app() -> ClashApp | None:
    if sys.platform == "win32":
        return WindowsApp()
    if sys.platform == "darwin":
        return MacApp()
    return None


# ---------------------------------------------------------------- 系统里实际生效的状态（Windows）

def proxy_points_to(enabled: int | None, server: str | None, port: int) -> bool:
    return bool(enabled) and bool(server) and f"127.0.0.1:{port}" in server


def _reg_value(root: int, key: str, name: str) -> object | None:
    import winreg
    try:
        with winreg.OpenKey(root, key) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except OSError:
        return None


def system_proxy_ok(port: int) -> bool | None:
    """Windows 系统代理是否开着并指向 Clash；非 Windows 返回 None（不检查）。"""
    if sys.platform != "win32":
        return None
    import winreg
    enabled = _reg_value(winreg.HKEY_CURRENT_USER, INTERNET_KEY, "ProxyEnable")
    server = _reg_value(winreg.HKEY_CURRENT_USER, INTERNET_KEY, "ProxyServer")
    return proxy_points_to(enabled if isinstance(enabled, int) else None, server if isinstance(server, str) else None, port)


def autostart_registered() -> bool | None:
    """Windows 上 Clash Verge 有没有真的登记开机自启：计划任务、Run 键或启动文件夹，任一即可。"""
    if sys.platform != "win32":
        return None
    task = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, timeout=20)
    if task.returncode == 0:
        return True
    import winreg
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, RUN_KEY) as handle:
                count = winreg.QueryInfoKey(handle)[1]
                if any(PROCESS in str(winreg.EnumValue(handle, i)[1]).lower() for i in range(count)):
                    return True
        except OSError:
            continue
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return any("clash" in p.name.lower() for p in startup.glob("*")) if startup.is_dir() else False
