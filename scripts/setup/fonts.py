"""清理国产厂商字体（Windows）：fuck-claude 的"国产厂商字体"一项（10 分）检测的就是这些。

只用标准库。要找的字体名单直接读自 vendor/fuckclaude-signals.js 的 FONTS_CN_VENDOR，
和网页检测保持一致。匹配看字体文件内部的名字表，因为 WPS 装的方正字体在注册表里是中文名。
删除前把字体文件和注册表项备份到一个文件夹，随时可以用 restore 装回去。
系统自带的中文字体（微软雅黑、宋体等）不在名单里，不会动。

    python fonts.py list [--json]                       # 列出装了哪些厂商字体，不改任何东西
    python fonts.py remove --dry-run                    # 预演
    python fonts.py remove [--log 日志路径]              # 备份后删除；装在系统里的字体需要管理员
    python fonts.py restore <备份文件夹> [--log 日志路径]  # 按备份装回去
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Protocol

HERE = Path(__file__).resolve().parent
SIGNALS_JS = HERE.parent / "vendor" / "fuckclaude-signals.js"
FONTS_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
NAME_IDS = (1, 4, 16)  # 字体族名、完整名、排版用族名
SCOPES = ("machine", "user")


@dataclass(frozen=True)
class Paths:
    machine: Path  # C:\Windows\Fonts
    user: Path     # %LOCALAPPDATA%\Microsoft\Windows\Fonts


@dataclass(frozen=True)
class FontHit:
    scope: str       # machine：装给所有用户（要管理员）；user：只装给当前用户
    value_name: str  # 注册表里的名字
    data: str        # 注册表里记的文件名或路径
    path: str
    matched: str     # 命中了名单里的哪一个


class FontRegistry(Protocol):
    def values(self, scope: str) -> list[tuple[str, str]]: ...
    def delete(self, scope: str, name: str) -> None: ...
    def set(self, scope: str, name: str, value: str) -> None: ...


class WinRegistry:
    """HKLM / HKCU 下的 ...\\CurrentVersion\\Fonts。"""

    def __init__(self) -> None:
        import winreg  # 只在 Windows 上有
        self._winreg = winreg
        self._roots = {"machine": winreg.HKEY_LOCAL_MACHINE, "user": winreg.HKEY_CURRENT_USER}

    def values(self, scope: str) -> list[tuple[str, str]]:
        wr = self._winreg
        try:
            key = wr.OpenKey(self._roots[scope], FONTS_KEY)
        except OSError:
            return []
        with key:
            count = wr.QueryInfoKey(key)[1]
            return [(name, str(value)) for name, value, _ in (wr.EnumValue(key, i) for i in range(count))]

    def delete(self, scope: str, name: str) -> None:
        wr = self._winreg
        with wr.OpenKey(self._roots[scope], FONTS_KEY, 0, wr.KEY_SET_VALUE) as key:
            wr.DeleteValue(key, name)

    def set(self, scope: str, name: str, value: str) -> None:
        wr = self._winreg
        with wr.CreateKeyEx(self._roots[scope], FONTS_KEY, 0, wr.KEY_SET_VALUE) as key:
            wr.SetValueEx(key, name, 0, wr.REG_SZ, value)


# ---------------------------------------------------------------- 读名单和字体名

def vendor_families(js_path: Path = SIGNALS_JS) -> list[str]:
    """从 fuck-claude 规则里取 FONTS_CN_VENDOR 名单。"""
    text = js_path.read_text(encoding="utf-8")
    block = re.search(r"FONTS_CN_VENDOR\s*=\s*\[(.*?)\]", text, re.S)
    if not block:
        raise ValueError(f"{js_path.name} 里没找到 FONTS_CN_VENDOR，fuck-claude 规则可能改版了")
    return re.findall(r'"([^"]+)"', block.group(1))


def _read(handle: BinaryIO, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("文件被截断")
    return data


def _sfnt_offsets(handle: BinaryIO) -> list[int]:
    tag = _read(handle, 0, 4)
    if tag != b"ttcf":
        return [0]
    count = struct.unpack(">I", _read(handle, 8, 4))[0]
    return list(struct.unpack(f">{count}I", _read(handle, 12, 4 * min(count, 64))))


def _names_in_sfnt(handle: BinaryIO, base: int) -> set[str]:
    num_tables = struct.unpack(">H", _read(handle, base + 4, 2))[0]
    for i in range(num_tables):
        tag, _, offset, _ = struct.unpack(">4sIII", _read(handle, base + 12 + 16 * i, 16))
        if tag == b"name":
            return _decode_name_table(handle, offset)
    return set()


def _decode_name_table(handle: BinaryIO, table: int) -> set[str]:
    _, count, string_offset = struct.unpack(">3H", _read(handle, table, 6))
    names = set()
    for i in range(count):
        platform, _, _, name_id, length, offset = struct.unpack(">6H", _read(handle, table + 6 + 12 * i, 12))
        if name_id not in NAME_IDS:
            continue
        raw = _read(handle, table + string_offset + offset, length)
        text = raw.decode("utf-16-be" if platform in (0, 3) else "latin-1", errors="ignore").strip("\x00 ")
        if text:
            names.add(text)
    return names


def font_names(path: Path) -> set[str]:
    """字体文件名字表里的族名、完整名；读不了就返回空集合。"""
    try:
        with open(path, "rb") as handle:
            return set().union(*(_names_in_sfnt(handle, base) for base in _sfnt_offsets(handle)))
    except (OSError, ValueError, struct.error):
        return set()


def _resolve(scope: str, data: str, paths: Paths) -> Path:
    path = Path(data)
    return path if path.is_absolute() else (paths.machine if scope == "machine" else paths.user) / path


def _match(names: set[str], families: list[str]) -> str | None:
    lowered = {n.lower() for n in names}
    for family in families:
        f = family.lower()
        if f in lowered or any(n.startswith(f + " ") for n in lowered):
            return family
    return None


def find_vendor_fonts(registry: FontRegistry, families: list[str], paths: Paths) -> list[FontHit]:
    hits = []
    for scope in SCOPES:
        for value_name, data in registry.values(scope):
            path = _resolve(scope, data, paths)
            label = re.sub(r"\s*\((TrueType|OpenType)\)\s*$", "", value_name)
            matched = _match(font_names(path) | {label}, families)
            if matched:
                hits.append(FontHit(scope, value_name, data, str(path), matched))
    return hits


# ---------------------------------------------------------------- 删除和还原

def _delete_on_reboot(path: Path) -> None:
    import ctypes  # MoveFileExW(path, NULL, MOVEFILE_DELAY_UNTIL_REBOOT)
    if not ctypes.windll.kernel32.MoveFileExW(str(path), None, 0x4):
        raise ctypes.WinError()


def _delete_file(path: Path, delete_file: Callable[[Path], None],
                 delete_on_reboot: Callable[[Path], None]) -> str:
    try:
        delete_file(path)
        return "已删除"
    except FileNotFoundError:
        return "文件本来就不在"
    except PermissionError:
        delete_on_reboot(path)
        return "文件正被占用，已安排在重启时删除"


def remove(hits: list[FontHit], registry: FontRegistry, backup_root: Path, dry_run: bool, is_admin: bool,
           stamp: str | None = None, delete_file: Callable[[Path], None] = os.remove,
           delete_on_reboot: Callable[[Path], None] = _delete_on_reboot) -> list[str]:
    if not hits:
        return ["没有要删的厂商字体"]
    backup = backup_root / f"fonts-{stamp or time.strftime('%Y%m%d-%H%M%S')}"
    if dry_run:
        return [f"[预演] 将删除 {h.value_name}（{h.matched}，{h.path}）" for h in hits] + [f"[预演] 备份位置：{backup}"]
    if any(h.scope == "machine" for h in hits) and not is_admin:
        raise PermissionError("装给所有用户的字体要管理员权限才能删")
    backup.mkdir(parents=True, exist_ok=True)
    manifest, messages = [], []
    for hit in hits:
        source = Path(hit.path)
        if source.exists():
            shutil.copy2(source, backup / source.name)
        manifest.append({**asdict(hit), "backup_file": source.name if source.exists() else None})
    (backup / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for hit in hits:  # 先备份完再删
        registry.delete(hit.scope, hit.value_name)
        result = _delete_file(Path(hit.path), delete_file, delete_on_reboot)
        messages.append(f"{hit.value_name}（{hit.matched}）：注册表项已删除，{result}")
    messages.append(f"备份在 {backup}，要装回去运行：python fonts.py restore \"{backup}\"")
    messages.append("重启电脑后生效（浏览器会缓存字体列表）")
    return messages


def restore(backup: Path, registry: FontRegistry, paths: Paths, dry_run: bool, is_admin: bool) -> list[str]:
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if dry_run:
        return [f"[预演] 将装回 {item['value_name']}" for item in manifest]
    if any(item["scope"] == "machine" for item in manifest) and not is_admin:
        raise PermissionError("装给所有用户的字体要管理员权限才能装回去")
    messages = []
    for item in manifest:
        target = _resolve(item["scope"], item["data"], paths)
        if item.get("backup_file") and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / item["backup_file"], target)
        registry.set(item["scope"], item["value_name"], item["data"])
        messages.append(f"已装回 {item['value_name']}")
    messages.append("重启电脑后生效")
    return messages


# ---------------------------------------------------------------- 命令行

def default_paths() -> Paths:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return Paths(machine=windir / "Fonts", user=local / "Microsoft" / "Windows" / "Fonts")


def _is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


@contextlib.contextmanager
def _tee(log: str | None) -> Iterator[Callable[[str], None]]:
    handle = open(log, "w", encoding="utf-8") if log else None
    try:
        def say(line: str) -> None:
            print(line)
            if handle:
                handle.write(line + "\n")
        yield say
    finally:
        if handle:
            handle.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清理国产厂商字体（claude-antiban）")
    parser.add_argument("command", choices=["list", "remove", "restore"])
    parser.add_argument("backup", nargs="?", help="restore 用：备份文件夹")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="list 输出 JSON")
    parser.add_argument("--log", help="同时把输出写进这个文件（AI 提权运行时用）")
    parser.add_argument("--backup-root", default=str(Path.home() / "claude-antiban-backup"))
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("只支持 Windows。macOS 请在「字体册」里手动移除这些字体。")
        return 2

    registry, paths = WinRegistry(), default_paths()
    with _tee(args.log) as say:
        try:
            if args.command == "restore":
                if not args.backup:
                    parser.error("restore 需要备份文件夹")
                for line in restore(Path(args.backup), registry, paths, args.dry_run, _is_admin()):
                    say(line)
                return 0
            hits = find_vendor_fonts(registry, vendor_families(), paths)
            if args.command == "list":
                if args.json:
                    say(json.dumps([asdict(h) for h in hits], ensure_ascii=False))
                elif not hits:
                    say("没有找到 fuck-claude 名单里的国产厂商字体")
                else:
                    for hit in hits:
                        where = "所有用户" if hit.scope == "machine" else "当前用户"
                        say(f"{hit.value_name}  →  命中 {hit.matched}（装给{where}，{hit.path}）")
                return 0
            for line in remove(hits, registry, Path(args.backup_root), args.dry_run, _is_admin()):
                say(line)
            return 0
        except PermissionError as exc:
            say(f"出错：{exc}。请用管理员身份运行。")
            return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
