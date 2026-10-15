"""Tests for scripts/setup/clash_app.py (process control and OS state), all with fakes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import clash_app as ca  # noqa: E402


def test_exe_candidates_follow_program_files_and_local_appdata(tmp_path: Path) -> None:
    env = {"ProgramFiles": str(tmp_path / "PF"), "LOCALAPPDATA": str(tmp_path / "LA")}
    candidates = ca.exe_candidates(env)
    assert tmp_path / "PF" / "Clash Verge" / "clash-verge.exe" in candidates
    assert tmp_path / "LA" / "Programs" / "Clash Verge" / "clash-verge.exe" in candidates


def test_find_exe_prefers_the_running_process(tmp_path: Path) -> None:
    installed = tmp_path / "PF" / "Clash Verge" / "clash-verge.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"")
    env = {"ProgramFiles": str(tmp_path / "PF")}
    assert ca.find_exe("D:/elsewhere/clash-verge.exe", env) == "D:/elsewhere/clash-verge.exe"
    assert ca.find_exe(None, env) == str(installed)
    assert ca.find_exe(None, {"ProgramFiles": str(tmp_path / "none")}) is None


def test_wait_ready_needs_the_port_and_a_fresh_runtime_file(tmp_path: Path) -> None:
    runtime = tmp_path / "clash-verge.yaml"
    runtime.write_text("old", encoding="utf-8")
    since = runtime.stat().st_mtime + 1  # 文件比"重启时刻"旧
    clock = iter(range(100))
    assert ca.wait_ready(7897, runtime, since, timeout=3, connect=lambda port: True,
                         sleep=lambda s: None, now=lambda: next(clock)) is False

    calls = {"n": 0}

    def connect(port: int) -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    clock = iter(range(100))
    assert ca.wait_ready(7897, runtime, since - 10, timeout=10, connect=connect,
                         sleep=lambda s: None, now=lambda: next(clock)) is True


def test_parse_proxy_settings() -> None:
    assert ca.proxy_points_to(1, "127.0.0.1:7897", 7897) is True
    assert ca.proxy_points_to(1, "http=127.0.0.1:7897;https=127.0.0.1:7897", 7897) is True
    assert ca.proxy_points_to(0, "127.0.0.1:7897", 7897) is False
    assert ca.proxy_points_to(1, "127.0.0.1:7890", 7897) is False
    assert ca.proxy_points_to(1, None, 7897) is False
