---
name: claude-antiban
description: Use when a user (often in mainland China) wants to set up a computer from scratch for using Claude safely, or worries about Claude, claude.ai or Claude Code account bans or risk control, or wants to check or fix that environment - Clash Verge / v2rayN setup, proxy routing, exit IP quality, DNS leaks, WebRTC leaks (WebRTC Network Limiter), IPv6, timezone or language consistency, or the browser "China user" fingerprint score from fuck-claude, or asks what to buy first (static IP, Claude account or subscription). Triggers include Claude 防封, 封号, 风控, 从零配置, 要买什么, 买号, 新电脑配置代理, 环境检测, IP 纯净度, DNS 泄漏, WebRTC 泄漏, 时区对不对, 指纹, 中国用户检测.
---

# Claude 防封环境：从零配置，并用实测出口验收

## 核心

Claude 能看到的只有两样东西：发往它服务器的连接，和浏览器里的环境。目标有两条：

1. 浏览器、Claude 桌面端、Claude Code 这三个入口，都从**同一个固定的海外出口**出去；
2. 系统时区、语言、浏览器指纹都和这个出口一致。

路线是**系统代理 + 持久代理变量，不开 TUN**。代理设置只是一种约定，程序可以不听，所以一切以**实测出口**为准。

## 硬规则

- 测试时**不运行 `claude` 命令**，也不用 Python、curl 访问 claude.ai 或 anthropic.com：不走代理的那条路会把真实 IP 直接发给 Claude。自检脚本的 Python 部分在代码里就拒绝连这些域名；检测页先用 1.1.1.1 确认浏览器已经从海外出口出去，才会去读 `claude.ai/cdn-cgi/trace`。
- **不用** Playwright、无头浏览器或浏览器自动化扩展来跑指纹。要测的是用户平时登 Claude 的那个浏览器。
- 时区按**多个 IP 库的多数结果**对齐（自检输出里已算好），不凭节点名或记忆猜。
- 改系统、代理软件、浏览器设置前，先说清楚现状、要改什么、怎么回滚，用户确认后再动手。只改这次要改的项。Clash 只通过 `clash_verge.py` 改 `dns_config.yaml` 和当前订阅的规则文件；订阅、节点、`verge.yaml`、`config.yaml` 和生成出来的 `clash-verge.yaml` 都不碰。
- **你自己也是联网的程序。** 如果你是运行在用户电脑上的 Claude（例如 Claude Code），而用户还没做完 `SETUP.md` 的「一、先让代理跑起来」，那么你的流量很可能正从真实 IP 发出去。这时应先停下，请用户自己照这一节做完，或换别的工具来带，然后再继续。
- **不要让用户退出或重启代理软件。** 退出时 Clash 会关掉系统代理，浏览器和你自己都会改用真实 IP 连接。要让 Clash 重新加载配置，用「DNS 覆写」开关（交接 C）。

## 先判断用户要哪一种

- **新电脑或还没配过**（"从零配置""教我配""WebRTC 扩展怎么设"）→ 走**配置流程**。
- **已经配过，想检查或排障**（"帮我查查""是不是泄漏了""时区对不对"）→ 走**体检流程**。

## 和用户分工：交接

技术活都由你做。只有下面这几件必须用户亲手做，`SETUP.md` 里也只写了这些。轮到用户时，这条回复只做交接，然后停下等他回复，不要在同一条回复里接着调用工具。

| 交接 | 用户要做的 | 发给用户 |
|---|---|---|
| **A 准备** | 读 README，买独享静态 IP、Claude 账号和会员 | `README.md` 的「思路」和「要买的东西」 |
| **B 让代理跑起来** | 装 Clash、导入订阅、选节点和模式、拨好设置页开关、设代理变量、把 skill 交给 AI | `SETUP.md`「一、先让代理跑起来」，截图 `assets/clash-1-import-subscription.png` 到 `assets/clash-4-settings.png` |
| **C 重新加载 Clash** | 「DNS 覆写」关掉再打开（关着的直接打开） | `SETUP.md`「二、让 Clash 重新加载配置」 |
| **D 浏览器** | WebRTC 扩展、安全 DNS、语言、防开机抢跑 | `SETUP.md`「三、浏览器设置」，截图 `assets/webrtc-1-store.png` 到 `assets/webrtc-4-use-proxy.png` |
| **E 登录** | 登录 Claude；不在手机上装 Claude App | `SETUP.md`「五、登录 Claude」 |

另有一处不用停下：你运行提权命令时，用户要在管理员确认窗口里点「是」，在同一条回复里提前说一句即可。

交接按这个格式写：

```
**现在到了**：<做到哪了，一句话>
**该你做了**：<这一步需要你自己操作。照 SETUP.md 的「…」做，截图在 <完整路径>>
**做完回我**：<比如"好了"、界面截图、某个数字>
```

- 截图写完整的绝对路径（本 skill 目录 + `assets/…`）；界面支持发文件的话，直接把截图发过去。
- 用户的界面和截图对不上时，请他截一张自己的界面回来，对照着讲。
- 不要替用户下单付款，也不要向用户要订阅链接、账号或密码。

## 配置流程

下面 `<skill>` 指本 skill 目录，命令里一律写绝对路径。改东西的命令先预演（`--dry-run` / `-WhatIf`）给用户看，用户同意后再执行。

| # | 做什么 | 谁 | 怎么做 | 通过标准 |
|---|---|---|---|---|
| 1 | 摸底 | 你 | `python <skill>/scripts/setup/clash_verge.py status`；Windows 再跑 `<skill>/scripts/setup/windows-setup.ps1`（不带参数只看状态） | 知道用户做到哪了。再问一句：平时用哪个浏览器登录 Claude |
| 2 | 准备、让代理跑起来 | 用户 | 交接 A、B；status 里已经 [OK] 的部分跳过，只交没做的 | 用户回复做完 |
| 3 | 核对 Clash 开关 | 你 | 再跑 `clash_verge.py status` | 除「DNS 覆写」外全 [OK]（它在第 7 步才开）；不对的，按交接格式请用户改 SETUP 第一节里对应那一条 |
| 4 | 代理变量 | 你 | 摸底里 `HTTPS_PROXY` 没设，或端口和 status 的「代理端口」不一致时：`windows-setup.ps1 -ProxyPort <端口>`（macOS：`macos-setup.sh --proxy-port <端口>`） | 用户变量 `HTTPS_PROXY` 是 `http://127.0.0.1:<端口>` |
| 5 | 检查点 | 你 | `python <skill>/scripts/selfcheck.py --skip-browser` | 出口国家对，IP 没有滥用记录；不合格就停下，请用户找卖家。时区那一项告诉你要不要改、改成什么 |
| 6 | DNS 覆写、国内直连规则 | 你 | `clash_verge.py apply --dry-run`，用户同意后 `clash_verge.py apply`（会自动备份） | 输出「已写入」或「不改」 |
| 7 | 让 Clash 重新加载 | 用户 | 交接 C | `clash_verge.py verify` 为 [OK] |
| 8 | 系统 IPv6、网卡 DNS、时区 | 你；用户点「是」 | 见下面「提权运行」 | 日志里每块网卡 IPv6 关、DNS 为 `1.1.1.1, 8.8.8.8`，时区对，自动设置时区已关闭 |
| 9 | 浏览器 | 用户 | 交接 D | 第 10 步里 WebRTC、安全 DNS、指纹语言项通过 |
| 10 | 完整自检 | 你 | `python <skill>/scripts/selfcheck.py`。先告诉用户会弹出一个检测页，约 15 秒内不要关 | "严重"为 0，主要项 [OK] |
| 11 | 登录 | 用户 | 交接 E | 用户回复登录好了 |
| 12 | Claude Code（需要的话） | 你 | 按 Anthropic 官方文档安装，Windows 先装 Git for Windows | `Get-Command claude` 找得到。不要运行 `claude` 来测试 |

**用 v2rayN 的**：status 会报"没找到 Clash Verge"。交接 B 时让用户看 SETUP 附录 A；第 3、6、7 步跳过；端口是 v2rayN 左下角 `mixed:` 后面的数字（默认 10808）。

**时区**：第 5 步检查点里，时区那一项按 IP 库多数结果判断；不一致时，提示里带着 Windows 时区名（如 `Pacific Standard Time`），对得上就不用改。

**提权运行（第 8 步，Windows）**：

1. 先不提权预演：`windows-setup.ps1 -NetworkTask -TimeZone "<Windows 时区名>" -WhatIf`，把要改的内容给用户看。
2. 用户同意后，在同一条回复里先说"马上会弹出管理员确认窗口，请点「是」"，再运行（日志放在临时目录）：

   ```powershell
   Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"<skill>\scripts\setup\windows-setup.ps1"','-NetworkTask','-TimeZone','"<Windows 时区名>"','-LogPath','"<日志路径>"'
   ```

3. 读日志确认结果。用户点了「否」，`Start-Process` 会报错，问过用户再来一次。

- 时区不用改：去掉 `-TimeZone` 和后面的时区名。
- 用户经常连需要网页登录的 Wi-Fi（酒店、机场、部分校园网）：加 `'-KeepDns'`，只关 IPv6，不改网卡 DNS。

**macOS**：`macos-setup.sh --network` 和 `--timezone <IANA 时区名>` 要 sudo，把带绝对路径的命令按交接格式交给用户，在「终端」里运行，先加 `--dry-run`。macOS 脚本没有在真机上完整验证过，预演不能省。

**Clash 改坏了**（用户说网页打不开）：先请用户关掉「DNS 覆写」，再运行 `clash_verge.py restore` 还原备份，然后交接 C。

## 体检流程

1. 运行 `python <本 skill 目录>/scripts/selfcheck.py`。需要 Python 3.9+，不用装依赖，约 15 秒。
   - 用户平时不在默认浏览器里登 Claude：加 `--no-open`，把打印出的地址给用户，让他在那个浏览器里打开。
   - 没有图形界面：加 `--skip-browser`。
2. 读结果。最后一行是完整 JSON 的路径。真实 IP 和代理密码都已打码，可以放心读；`--full` 生成的不打码版本只给用户本人看，不要打开。
   - `[X]` 必须修；
   - `[!]` 讲清风险，由用户决定改不改；
   - `[i]` 只做说明。
3. 每条结果都标了修法所在的文件：
   - `references/routing.md`：两种路线、Clash 规则、IPv6、Clash 退出时会关掉系统代理；
   - `references/dns.md`：三层 DNS、国内软件断网的根因与预防、DNS 覆写模板；
   - `references/browser-and-device.md`：时区、语言、WebRTC、安全 DNS、字体、fuck-claude 各项权重；
   - `references/ip.md`：IP 怎么选、质量怎么看。

   需要具体操作步骤时，对照 `SETUP.md` 里的同一步。
4. 改完再跑一遍自检，把前后结果对比给用户看。

## 结果速查

| 项 | 通过条件 |
|---|---|
| 浏览器 / 系统代理 / Claude Code 三个入口 | 出口相同，且不在 CN、HK、MO |
| 不认代理的程序（直连） | 仅供参考；等于代理出口，说明 TUN 在接管 |
| 出口 IP 是否唯一 | 只有一个；出现多个，通常是用了自动测速组或分流规则 |
| DNS：浏览器这条路 | 解析服务器只在出口所在国 |
| DNS：系统解析 | 只影响不走代理的程序 |
| WebRTC | 只出现 `.local` 地址或代理出口 IP |
| IPv6 | 浏览器拿不到出口所在国以外的 IPv6 |
| 系统时区 | 不是中国时区，且与 IP 库多数结果一致 |
| fuck-claude 评分 | 0–30 为低风险；中文版 Windows 的字体固定约 +14，正常 |
| 出口 IP 质量 | 有滥用记录要换；机房或代理标记说明不理想，但能用 |
| 浏览器安全 DNS | 都已关闭 |
| 国内软件会不会断网（DNS） | 国内域名拿到真实 IP |

## 常见误区

| 误区 | 实际 |
|---|---|
| 代理开着，所以都走代理了 | 微信主程序、很多命令行和 Node 程序不认系统代理，要看实测出口 |
| 开 TUN 最安全 | 微信会被迫出国；Clash 一退出就退回直连。`HTTPS_PROXY` 在代理断开时直接报错，不会漏出真实 IP |
| 退出 Clash 后 Claude 也连不上 | 只有 Claude Code 如此。Clash 正常退出时会关掉系统代理，浏览器和桌面端随即用真实 IP 直连 |
| 网卡 DNS 改成 `127.0.0.1` 就防泄漏了 | 不开 TUN 时，迅雷、网易云等会拿到 Clash 的假 IP 而断网 |
| DoH 写 `#GLOBAL` | GLOBAL 组常停在 DIRECT，结果 DoH 被墙；改用 `#RULES` |
| 一个 IP 库说在哪就在哪 | 各库常有出入，按多数结果算 |
| 删掉微软雅黑来降分 | 系统字体不能删；字体只是网页指纹，Claude Code 不读 |

## 维护

- `scripts/vendor/fuckclaude-signals.js` 来自 `LinXiaoTao/FuckClaude`（MIT 许可）。上游改了评分规则时，用 `scripts/update_fuckclaude_signals.py` 同步：先只看 commit，再用 `--commit` 构建，最后加 `--yes` 写入。
- `assets/` 里的截图改编自第三方配置教程：已打码，并按本路线重新标注。Clash Verge 界面改版后需要重新截图。
- `scripts/setup/clash_verge.py` 依赖 Clash Verge Rev 的配置文件布局：`profiles.yaml` 里的 `current` 和 `option.rules`、`dns_config.yaml`、生成出来的 `clash-verge.yaml`。Clash Verge 大改版后要核对一遍。
