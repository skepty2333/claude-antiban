"""Tests for scripts/setup/fonts.py with a fake registry and synthesized font files."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "setup"))
import fonts  # noqa: E402


def make_font(names: dict[int, str], collection: bool = False) -> bytes:
    """A minimal sfnt holding only a `name` table (platform 3, UTF-16BE)."""
    strings = b""
    records = b""
    for name_id, text in names.items():
        data = text.encode("utf-16-be")
        records += struct.pack(">6H", 3, 1, 0x409, name_id, len(data), len(strings))
        strings += data
    name_table = struct.pack(">3H", 0, len(names), 6 + len(records)) + records + strings
    sfnt_header_len = 12 + 16
    base = 16 if collection else 0  # a one-font TTC header: tag, version, count, one offset
    sfnt = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    sfnt += b"name" + struct.pack(">III", 0, base + sfnt_header_len, len(name_table))
    font = sfnt + name_table  # table offsets in a TTC are from the start of the file
    if collection:
        return b"ttcf" + struct.pack(">III", 0x00010000, 1, base) + font
    return font


class FakeRegistry:
    def __init__(self, data: dict[str, dict[str, str]]) -> None:
        self.data = {scope: dict(values) for scope, values in data.items()}

    def values(self, scope: str) -> list[tuple[str, str]]:
        return list(self.data.get(scope, {}).items())

    def delete(self, scope: str, name: str) -> None:
        del self.data[scope][name]

    def set(self, scope: str, name: str, value: str) -> None:
        self.data.setdefault(scope, {})[name] = value


@pytest.fixture()
def env(tmp_path: Path):
    machine_dir = tmp_path / "Windows" / "Fonts"
    user_dir = tmp_path / "LocalAppData" / "Fonts"
    machine_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    (machine_dir / "FZSSJW.TTF").write_bytes(make_font({1: "方正书宋简体", 4: "FZShuSong-Z01S"}))
    (machine_dir / "msyh.ttc").write_bytes(make_font({1: "Microsoft YaHei"}, collection=True))
    (user_dir / "MiSans-Medium.ttf").write_bytes(make_font({1: "MiSans Medium", 16: "MiSans"}))
    registry = FakeRegistry({
        "machine": {
            "方正书宋简体 (TrueType)": "FZSSJW.TTF",
            "Microsoft YaHei & Microsoft YaHei UI (TrueType)": "msyh.ttc",
        },
        "user": {"MiSans Medium (TrueType)": str(user_dir / "MiSans-Medium.ttf")},
    })
    return fonts.Paths(machine=machine_dir, user=user_dir), registry, tmp_path


# ---------------------------------------------------------------- reading

def test_vendor_families_come_from_the_vendored_fuckclaude_rules() -> None:
    families = fonts.vendor_families()
    assert "FZShuSong-Z01S" in families and "MiSans" in families and "Alibaba PuHuiTi" in families
    assert "Microsoft YaHei" not in families


def test_font_names_reads_sfnt_and_collections(tmp_path: Path) -> None:
    single = tmp_path / "a.ttf"
    single.write_bytes(make_font({1: "Foo", 4: "Foo Bold", 16: "Foo Family"}))
    ttc = tmp_path / "b.ttc"
    ttc.write_bytes(make_font({1: "Bar"}, collection=True))
    assert fonts.font_names(single) == {"Foo", "Foo Bold", "Foo Family"}
    assert fonts.font_names(ttc) == {"Bar"}


def test_font_names_tolerates_garbage(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"not a font at all")
    assert fonts.font_names(bad) == set()
    assert fonts.font_names(tmp_path / "missing.ttf") == set()


def test_find_matches_internal_names_not_just_registry_names(env) -> None:
    paths, registry, _ = env
    hits = fonts.find_vendor_fonts(registry, fonts.vendor_families(), paths)
    found = {(h.scope, h.matched) for h in hits}
    assert ("machine", "FZShuSong-Z01S") in found  # registry name is Chinese; matched via the name table
    assert ("user", "MiSans") in found
    assert all("YaHei" not in h.value_name for h in hits)


# ---------------------------------------------------------------- remove / restore

def test_remove_dry_run_changes_nothing(env) -> None:
    paths, registry, tmp = env
    hits = fonts.find_vendor_fonts(registry, fonts.vendor_families(), paths)
    before = json.dumps(registry.data, sort_keys=True)
    messages = fonts.remove(hits, registry, tmp / "backup", dry_run=True, is_admin=False, stamp="s")
    assert messages and json.dumps(registry.data, sort_keys=True) == before
    assert (paths.machine / "FZSSJW.TTF").exists()
    assert not (tmp / "backup").exists()


def test_remove_refuses_machine_fonts_without_admin(env) -> None:
    paths, registry, tmp = env
    hits = fonts.find_vendor_fonts(registry, fonts.vendor_families(), paths)
    with pytest.raises(PermissionError):
        fonts.remove(hits, registry, tmp / "backup", dry_run=False, is_admin=False, stamp="s")
    assert (paths.machine / "FZSSJW.TTF").exists()


def test_remove_backs_up_then_deletes_and_restore_puts_back(env) -> None:
    paths, registry, tmp = env
    original = json.dumps(registry.data, sort_keys=True)
    hits = fonts.find_vendor_fonts(registry, fonts.vendor_families(), paths)
    fonts.remove(hits, registry, tmp / "backup", dry_run=False, is_admin=True, stamp="s")
    backup = tmp / "backup" / "fonts-s"
    assert (backup / "FZSSJW.TTF").exists() and (backup / "MiSans-Medium.ttf").exists()
    assert json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert not (paths.machine / "FZSSJW.TTF").exists()
    assert "方正书宋简体 (TrueType)" not in registry.data["machine"]
    assert "Microsoft YaHei & Microsoft YaHei UI (TrueType)" in registry.data["machine"]

    fonts.restore(backup, registry, paths, dry_run=False, is_admin=True)
    assert (paths.machine / "FZSSJW.TTF").exists()
    assert json.dumps(registry.data, sort_keys=True) == original


def test_remove_schedules_locked_files_for_reboot(env) -> None:
    paths, registry, tmp = env
    hits = [h for h in fonts.find_vendor_fonts(registry, fonts.vendor_families(), paths) if h.scope == "machine"]
    scheduled: list[Path] = []

    def locked(_: Path) -> None:
        raise PermissionError("in use")

    messages = fonts.remove(hits, registry, tmp / "backup", dry_run=False, is_admin=True, stamp="s",
                            delete_file=locked, delete_on_reboot=scheduled.append)
    assert scheduled == [paths.machine / "FZSSJW.TTF"]
    assert any("重启" in m for m in messages)


def test_main_list_reports_nothing_found(env, capsys: pytest.CaptureFixture, monkeypatch) -> None:
    paths, _, _ = env
    monkeypatch.setattr(fonts, "default_paths", lambda: paths)
    monkeypatch.setattr(fonts, "WinRegistry", lambda: FakeRegistry({"machine": {}, "user": {}}))
    monkeypatch.setattr(fonts.sys, "platform", "win32")
    assert fonts.main(["list"]) == 0
    assert "没有找到" in capsys.readouterr().out
