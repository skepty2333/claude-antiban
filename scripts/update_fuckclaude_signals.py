"""Re-vendor the fuck-claude scoring rules (maintainers only; needs Node.js for npx).

    python update_fuckclaude_signals.py                 # show the latest upstream commit, change nothing
    python update_fuckclaude_signals.py --commit <sha>  # build that commit and show a size diff
    python update_fuckclaude_signals.py --commit <sha> --yes   # ...and overwrite the vendored file

The output runs in the user's browser, so review the upstream diff on GitHub
before passing --yes.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = "LinXiaoTao/FuckClaude"
ESBUILD = "esbuild@0.24.0"
OUT = Path(__file__).resolve().parent / "vendor" / "fuckclaude-signals.js"
SHA_RE = re.compile(r"[0-9a-f]{40}")


def latest_commit() -> str:
    url = f"https://api.github.com/repos/{REPO}/commits/master"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read())["sha"]


def download(sha: str, dest: Path) -> None:
    url = f"https://raw.githubusercontent.com/{REPO}/{sha}/src/config/signals.ts"
    with urllib.request.urlopen(url, timeout=20) as resp:
        dest.write_bytes(resp.read(2_000_000))


def transpile(src: Path, dest: Path) -> None:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("需要 Node.js（npx）")
    subprocess.run([npx, "-y", ESBUILD, src.name, "--format=iife", "--global-name=FuckClaudeSignals",
                    "--target=es2020", f"--outfile={dest.name}"], check=True, cwd=src.parent)


def build(sha: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        src, built = Path(tmp) / "signals.ts", Path(tmp) / "signals.js"
        download(sha, src)
        if "export const SIGNALS" not in src.read_text(encoding="utf-8"):
            sys.exit("上游 signals.ts 结构变了（找不到 SIGNALS），请人工检查")
        transpile(src, built)
        body = built.read_text(encoding="utf-8")
    header = (f"/*! Vendored from https://github.com/{REPO} src/config/signals.ts\n"
              f" * commit {sha}, transpiled with {ESBUILD} (iife, global FuckClaudeSignals).\n"
              " * Copyright (c) 2026 LinXiaoTao. MIT License, see FUCKCLAUDE-LICENSE.txt. "
              "Regenerate with update_fuckclaude_signals.py. */\n")
    return header + body


def main() -> None:
    parser = argparse.ArgumentParser(description="同步 fuck-claude 评分规则")
    parser.add_argument("--commit", help="要使用的上游 commit（40 位 sha）")
    parser.add_argument("--yes", action="store_true", help="确认覆盖 vendor 文件")
    args = parser.parse_args()
    if not args.commit:
        print(f"上游最新 commit：{latest_commit()}\n先在 GitHub 上看过改动，再用 --commit <sha> 构建。")
        return
    if not SHA_RE.fullmatch(args.commit):
        sys.exit("--commit 必须是 40 位小写十六进制 sha")
    new = build(args.commit)
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    print(f"旧文件 {len(old.splitlines())} 行，新文件 {len(new.splitlines())} 行，"
          f"{'内容相同' if old.replace(chr(13), '') == new.replace(chr(13), '') else '内容有变化'}")
    if not args.yes:
        print("加 --yes 才会写入。")
        return
    OUT.write_bytes(new.encode("utf-8"))  # keep LF
    print(f"已更新到 {args.commit[:7]}：{OUT}")


if __name__ == "__main__":
    main()
