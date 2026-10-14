# 流量走向：让每个 Claude 入口走同一个出口

## 先懂一件事

系统代理和 `HTTPS_PROXY` 都只是**约定**：告诉程序"请走 127.0.0.1:7897"，听不听由程序决定。浏览器、大多数桌面软件听；微信主程序、很多命令行工具和 Node.js 程序不听，照样用真实 IP 直连。只有 **TUN（虚拟网卡）** 改的是路由表，程序躲不开。

Claude 只看得到发往它服务器的连接。所以只需保证这三个入口走同一个固定的海外出口，别的软件怎么连都与 Claude 无关：

| 入口 | 靠什么走代理 |
|---|---|
| 浏览器（claude.ai） | 系统代理 |
| Claude 桌面端（Electron） | 系统代理（Electron 的默认行为） |
| Claude Code 命令行 | `HTTPS_PROXY` 环境变量（官方文档），或 `~/.claude/settings.json` 的 `env` |

## 档位 A（推荐）：系统代理 + 持久代理变量

1. 代理软件开"系统代理"。订阅只有一个节点用规则模式，并在"编辑规则"里加前置规则 `GEOSITE,cn,DIRECT` 和 `GEOIP,CN,DIRECT,no-resolve`，让国内网站直连；有多个节点用全局模式（规则要求见下文）。
2. 把代理变量存成用户级，新打开的程序都会读到（端口换成你客户端的 HTTP/混合端口：Clash Verge 默认 7897，v2rayN 在"设置 → 参数设置"里查本地端口）：

   ```powershell
   [Environment]::SetEnvironmentVariable('HTTPS_PROXY', 'http://127.0.0.1:7897', 'User')
   [Environment]::SetEnvironmentVariable('HTTP_PROXY',  'http://127.0.0.1:7897', 'User')
   [Environment]::SetEnvironmentVariable('NO_PROXY',    'localhost,127.0.0.1,::1', 'User')
   ```

   macOS / Linux：写进 `~/.zshrc` 或 `~/.bashrc`：`export HTTPS_PROXY=http://127.0.0.1:7897` 等三行。
   只想管 Claude Code：在 `~/.claude/settings.json` 加 `{"env": {"HTTPS_PROXY": "http://127.0.0.1:7897"}}`。
3. 已经开着的终端读不到新变量，要重开。自检里"Claude Code 命令行"提示"重开终端"就是这个原因。

特点：Clash 一退出，Claude Code 这类读 `HTTPS_PROXY` 的程序**直接报错**，不会改用真实 IP 直连。

**但浏览器和桌面端不一样**：Clash Verge 正常退出时会主动关掉 Windows 的系统代理（源码里停止内核时调用 `proxy_control::clear`），浏览器随即用真实 IP 直连。只有 Clash 崩溃或被强杀时，系统代理设置才会留着，浏览器才会报错。所以：

- 开机自启 Clash，平时不要手动退出；
- 要退出时，先关掉 Claude 的网页和桌面端。

可选：再加用户变量 `NODE_USE_ENV_PROXY=1`（Node 24+），让其他 Node 程序的 `fetch` 也认 `HTTPS_PROXY`。代价是 Clash 关掉时这些程序也会报错。

## 档位 B：TUN（虚拟网卡）+ 严格路由

适合搞不清哪些程序走没走代理的人。Clash Verge 设置：开"虚拟网卡模式"、开"严格路由"（`strict-route: true`）、DNS 劫持 `any:53`、关 IPv6。v2rayN：启用 TUN、清除系统代理、路由选全局。

副作用要提前讲清：

- **Clash 退出或崩溃 → 全部回到直连**，Claude Code 这时会用真实 IP。所以开 TUN 也保留档位 A 的变量。
- 微信等国内软件也被强制出国，可能登录受限（不少教程写明"全局模式下无法登录微信"）。用"规则"模式并让国内流量直连就能避开，Claude 相关规则放在最前面：

  ```yaml
  rules:
    - DOMAIN-SUFFIX,claude.ai,PROXY
    - DOMAIN-SUFFIX,claude.com,PROXY
    - DOMAIN-SUFFIX,anthropic.com,PROXY
    - GEOSITE,cn,DIRECT
    - GEOIP,CN,DIRECT,no-resolve
    - MATCH,PROXY
  ```

  `PROXY` 换成你固定节点所在的 select 组名。
- 连自己的国内服务器（SSH、远程桌面）会绕道海外：加规则 `IP-CIDR,服务器IP/32,DIRECT,no-resolve`。
- 与电脑热点、虚拟机网卡冲突：在客户端里绑定真实的物理网卡；或把 TUN stack 在 `gvisor`/`system` 间切换。

## 两档都必须做

- **规则**：`claude.ai`、`claude.com`、`anthropic.com` 不能命中 `DIRECT`，也不要放进 `url-test`/`fallback`/`load-balance` 这类自动切换组。用 `select` 组固定一个节点。自检的"出口 IP 是否唯一"报警，通常就是这里出了问题。
- **IPv6**：代理软件里关 IPv6（Clash `ipv6: false`）。Windows 用管理员 PowerShell 关闭网卡的 IPv6：

  ```powershell
  Disable-NetAdapterBinding -Name "*" -ComponentID ms_tcpip6
  ```

  新出现的网卡（USB 网卡、手机共享、新 VPN 网卡）默认会开 IPv6。`scripts/setup/windows-setup.ps1 -NetworkTask` 会装一个计划任务，每次开机、每次联网都重新关一遍，同时把网卡 DNS 固定成 `1.1.1.1`/`8.8.8.8`（加 `-KeepDns` 则不动 DNS）；macOS 用 `macos-setup.sh --network`（对应 `--keep-dns`）。

## 验收

运行 `python scripts/selfcheck.py`，要求：浏览器、系统代理、Claude Code 三行都是 [OK]，出口相同，且出口国家不是 CN/HK/MO。
