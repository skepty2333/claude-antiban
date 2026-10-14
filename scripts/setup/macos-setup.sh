#!/bin/bash
# Claude 防封：macOS 端设置（代理环境变量、系统时区、联网时关 IPv6 并设 DNS）。
# 改编自常见的 launchd 网络脚本；作者只在 Windows 上验证过整套流程，macOS 部分请先用 --dry-run 看清楚再执行。
#
#   bash macos-setup.sh                         # 只看当前状态
#   bash macos-setup.sh --proxy-port 7897       # 代理变量写进 ~/.zshrc（Claude Code 用）
#   bash macos-setup.sh --timezone America/Los_Angeles
#   bash macos-setup.sh --network               # 需要 sudo：每次网络变化时关 IPv6，并把 DNS 固定为 1.1.1.1/8.8.8.8
#   bash macos-setup.sh --network --keep-dns    # 同上，但 DNS 不动
#   bash macos-setup.sh --undo                  # 需要 sudo：删掉以上改动
#   任意命令加 --dry-run 只打印将要执行的操作
set -euo pipefail

LABEL="com.claude-antiban.network"
SCRIPT="/usr/local/bin/claude-antiban-network.sh"
PLIST="/Library/LaunchDaemons/${LABEL}.plist"
RC="$HOME/.zshrc"
MARK_BEGIN="# >>> claude-antiban proxy >>>"
MARK_END="# <<< claude-antiban proxy <<<"
DRY=0 PORT="" TZ_NAME="" NETWORK=0 UNDO=0 PIN_DNS=1

while [ $# -gt 0 ]; do
  case "$1" in
    --proxy-port) PORT="$2"; shift 2 ;;
    --timezone) TZ_NAME="$2"; shift 2 ;;
    --network) NETWORK=1; shift ;;
    --keep-dns) PIN_DNS=0; shift ;;
    --undo) UNDO=1; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo "未知参数：$1"; exit 2 ;;
  esac
done

run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$@"; fi; }

show_state() {
  echo "== 当前状态 =="
  echo "HTTPS_PROXY（当前终端）：${HTTPS_PROXY:-未设置}"
  grep -q "$MARK_BEGIN" "$RC" 2>/dev/null && echo "~/.zshrc：已写入代理变量" || echo "~/.zshrc：未写入代理变量"
  echo "系统时区：$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
  [ -f "$PLIST" ] && echo "网络脚本：已安装" || echo "网络脚本：未安装"
  networksetup -listallnetworkservices | tail -n +2 | grep -v '^\*' | while read -r svc; do
    echo "  [$svc] DNS: $(networksetup -getdnsservers "$svc" | tr '\n' ' ')"
  done
}

set_proxy() {
  local proxy="http://127.0.0.1:$1"
  run "sed -i '' '/$MARK_BEGIN/,/$MARK_END/d' '$RC' 2>/dev/null || true"
  run "printf '%s\n' '$MARK_BEGIN' 'export HTTPS_PROXY=$proxy' 'export HTTP_PROXY=$proxy' 'export NO_PROXY=localhost,127.0.0.1,::1' '$MARK_END' >> '$RC'"
  echo "已写入 $RC。新开的终端才会生效。"
}

write_root_file() {  # $1 = 目标路径，内容来自标准输入
  if [ "$DRY" = 1 ]; then echo "[dry-run] 将写入 $1："; sed 's/^/    /'; else sudo tee "$1" >/dev/null; fi
}

install_network() {
  {
    printf '%s\n' '#!/bin/bash' 'sleep 2' \
      "/usr/sbin/networksetup -listallnetworkservices | /usr/bin/grep -v '^\*' | /usr/bin/tail -n +2 | while read -r svc; do" \
      '  /usr/sbin/networksetup -setv6off "$svc"'
    if [ "$PIN_DNS" = 1 ]; then printf '%s\n' '  /usr/sbin/networksetup -setdnsservers "$svc" 1.1.1.1 8.8.8.8'; fi
    printf '%s\n' 'done'
  } | write_root_file "$SCRIPT"
  run "sudo chown root:wheel '$SCRIPT' && sudo chmod 755 '$SCRIPT'"
  cat <<EOF | write_root_file "$PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SCRIPT</string></array>
  <key>RunAtLoad</key><true/>
  <key>WatchPaths</key><array><string>/Library/Preferences/SystemConfiguration</string></array>
</dict></plist>
EOF
  run "sudo chown root:wheel '$PLIST' && sudo chmod 644 '$PLIST'"
  run "sudo launchctl bootout system/$LABEL 2>/dev/null || true"
  run "sudo launchctl bootstrap system '$PLIST' && sudo launchctl kickstart -k system/$LABEL"
  if [ "$PIN_DNS" = 1 ]; then echo "已安装：以后每次网络变化都会关 IPv6，并把 DNS 设为 1.1.1.1 / 8.8.8.8。"
  else echo "已安装：以后每次网络变化都会关 IPv6。"; fi
}

undo_all() {
  run "sed -i '' '/$MARK_BEGIN/,/$MARK_END/d' '$RC' 2>/dev/null || true"
  run "sudo launchctl bootout system/$LABEL 2>/dev/null || true"
  run "sudo rm -f '$PLIST' '$SCRIPT'"
  networksetup -listallnetworkservices | tail -n +2 | grep -v '^\*' | while read -r svc; do
    run "sudo networksetup -setv6automatic '$svc'"
    run "sudo networksetup -setdnsservers '$svc' Empty"
  done
  echo "已撤销。时区不会自动改回。"
}

show_state
[ "$UNDO" = 1 ] && undo_all
[ -n "$PORT" ] && set_proxy "$PORT"
[ -n "$TZ_NAME" ] && run "sudo systemsetup -settimezone '$TZ_NAME'"
[ "$NETWORK" = 1 ] && install_network
exit 0
