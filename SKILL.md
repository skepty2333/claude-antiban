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

- 测试时**不运行 `claude` 命令**，也不用 Python、curl 访问 claude.ai 或 anthropic.com：不走代理的那条路会把真实 IP 直接发给 Claude。自检脚本的 Python 部分在代码里就拒绝连这些域名；检测页先用 1.1.1.1 确认浏览器已经从海外出口出去，才会去读 `claude.ai/cdn-cgi/trace`；加 `--no-claude` 时完全不碰 claude.ai。
- **不用** Playwright、无头浏览器或浏览器自动化扩展来跑指纹。要测的是用户平时登 Claude 的那个浏览器。
- 时区按**多个 IP 库的多数结果**对齐（自检输出里已算好），不凭节点名或记忆猜。
- 改系统、代理软件、浏览器设置前，先说清楚现状、要改什么、怎么回滚，用户确认后再动手。只改这次要改的项。Clash 只通过 `clash_verge.py` 改 `dns_config.yaml` 和当前订阅的规则文件；订阅、节点、`verge.yaml`、`config.yaml` 和生成出来的 `clash-verge.yaml` 都不碰。
- **你自己也是联网的程序。** 如果你是 Claude（Claude Code、Claude 桌面端都算），**不要带配置流程**：配好之前电脑用的是真实 IP 或临时代理的共用 IP，你的流量会把用户的 Claude 账号带到这些 IP 上。直接停下，请用户换别的 AI 来带：WorkBuddy 这类国产 agent、接 DeepSeek 等国产模型的 agent 工具，或者 Codex 接他自己的 API。体检流程只在用户已经换上自己的静态 IP、设好 `HTTPS_PROXY` 之后才可以由你来跑。
- **不要让用户退出或重启代理软件。** 退出时 Clash 会关掉系统代理，浏览器和你自己都会改用真实 IP 连接。要让 Clash 重新加载配置，用「DNS 覆写」开关（交接 B）。

## 先判断用户要哪一种

- **新电脑或还没配过**（"从零配置""教我配""WebRTC 扩展怎么设"）→ 走**配置流程**。
- **已经配过，想检查或排障**（"帮我查查""是不是泄漏了""时区对不对"）→ 走**体检流程**。

## 和用户分工：交接

技术活都由你做。只有下面这几件必须用户亲手做，`SETUP.md` 里也只写了这些。轮到用户时，这条回复只做交接，然后停下等他回复，不要在同一条回复里接着调用工具。

| 交接 | 用户要做的 | 发给用户 |
|---|---|---|
| **A 让代理跑起来** | 装 Clash Verge，导入他现在在用的订阅，选节点和模式，拨好设置页开关 | `SETUP.md`「一、让代理跑起来」，截图 `assets/clash-1-import-subscription.png` 到 `assets/clash-4-settings.png` |
| **B 重新加载 Clash** | 「DNS 覆写」关掉再打开（关着的直接打开） | `SETUP.md`「二、让 Clash 重新加载配置」 |
| **C 浏览器** | WebRTC 扩展、安全 DNS、语言、防开机抢跑 | `SETUP.md`「三、浏览器设置」，截图 `assets/webrtc-1-store.png` 到 `assets/webrtc-4-use-proxy.png` |
| **D 换上静态 IP** | **这时必须已经买好 IP**；导入新订阅、选节点和模式、删掉临时订阅 | `SETUP.md`「四、换上你买的静态 IP」；还没买的，发 `README.md`「要买的东西」 |
| **E 登录** | **这时必须已经有 Claude 账号**；登录，不在手机上装 Claude App；普号登录后先正常用至少 72 小时再充会员 | `SETUP.md`「六、登录 Claude」。交接时把 72 小时这一条单独说一遍 |

不要一开始就让用户去买东西。IP 到第 9 步才用得上，账号到第 12 步才用得上，前面的步骤照常做；做到这两步时用户还没买好，就停下等他。

还有三种配合，不用单独停下，但必须在同一条回复里事先说清楚：

- **检测页别关**：跑带浏览器的检测前，告诉用户会弹出一个检测页，大约 15 秒内不要关。
- **管理员确认点「是」**：运行提权命令前，告诉用户马上会弹窗、为什么要管理员权限。
- **删字体要同意**：见配置流程第 7 步。没有用户明确的"同意"，不删任何字体。

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

顺序是：先测，看清起点；把不依赖 IP 的都做完；换上用户买的 IP，检查它、对时区；最后再测一遍，和起点对比。

下面 `<skill>` 指本 skill 目录，命令里一律写绝对路径。改东西的命令先预演（`--dry-run` / `-WhatIf`）给用户看，用户同意后再执行。

| # | 做什么 | 谁 | 怎么做 | 通过标准 |
|---|---|---|---|---|
| 1 | 摸底 | 你 | `python <skill>/scripts/setup/clash_verge.py status`；Windows 再跑 `<skill>/scripts/setup/windows-setup.ps1`（不带参数只看状态） | 知道用户做到哪了。问清：现在用什么代理上网；静态 IP 买了没、是不是已经在用；平时用哪个浏览器登录 Claude |
| 2 | 基线检测 | 你；用户别关检测页 | `python <skill>/scripts/selfcheck.py`（带浏览器的完整检测）。还没在用买的 IP 就加 `--no-claude` | 用大白话讲给用户：fuck-claude 现在多少分，命中了哪几项，每一项在后面第几步、由谁来改；中文字体那一项改不了，也要说明。记下报告 JSON 的路径，第 11 步要对比 |
| 3 | 让代理跑起来 | 用户 | 交接 A，只交 status 里没做好的部分；先用他现有的订阅 | 用户回复做完 |
| 4 | Clash 开关、代理变量 | 你 | `clash_verge.py status`；`HTTPS_PROXY` 没设或端口和 status 的「代理端口」不一致时，`windows-setup.ps1 -ProxyPort <端口>`（macOS：`macos-setup.sh --proxy-port <端口>`） | 除「DNS 覆写」外全 [OK]（它在第 5 步才开），不对的按交接格式请用户改；用户变量 `HTTPS_PROXY` 是 `http://127.0.0.1:<端口>` |
| 5 | DNS 覆写、国内直连规则 | 你，然后用户 | `clash_verge.py apply --dry-run`，用户同意后 `apply`（会自动备份）→ 交接 B | `clash_verge.py verify` 为 [OK] |
| 6 | 系统 IPv6、网卡 DNS | 你；用户点「是」 | 见下面「提权运行」，只带 `-NetworkTask` | 日志里每块网卡 IPv6 关、DNS 为 `1.1.1.1, 8.8.8.8` |
| 7 | 国产厂商字体 | 你；用户同意并点「是」 | 第 2 步命中「国产厂商字体」时才做，见下面「删字体」 | 用户同意并删完、重启过；或者用户决定不删（尊重他的决定，最后报告里这一项照样是 [!]） |
| 8 | 浏览器 | 用户 | 交接 C。第 2 步命中「国产浏览器」的，请用户改用 Chrome 或 Edge 登录 Claude。还没定买哪国 IP 的，语言先不改 | 用户回复做完 |
| 9 | 换上静态 IP，检查 IP | 用户先换，你再查 | 交接 D（用户还没买好 IP，就停在这里等）→ `clash_verge.py status`，核对新订阅的节点数和模式 → `clash_verge.py apply`，给新订阅补前置规则 → 交接 B → `verify` → `selfcheck.py --skip-browser` | 出口国家对，IP 没有滥用记录；不合格就停下，请用户找卖家。时区那一项告诉你要不要改、改成什么。语言没改的，请用户现在改 |
| 10 | 时区 | 你；用户点「是」 | 见下面「提权运行」，只带 `-TimeZone` | 日志里时区对，自动设置时区已关闭 |
| 11 | 完整检测，和起点对比 | 你；用户别关检测页 | `python <skill>/scripts/selfcheck.py` | "严重"为 0，主要项 [OK]。把起点和现在的 fuck-claude 分数、各项变化列给用户看 |
| 12 | 登录 | 用户 | 交接 E（用户还没有账号，就停在这里等） | 用户回复登录好了 |
| 13 | Claude Code（需要的话） | 你 | 按 Anthropic 官方文档安装，Windows 先装 Git for Windows | `Get-Command claude` 找得到。不要运行 `claude` 来测试 |

**用户一开始就在用买好的 IP**：第 2 步不加 `--no-claude`，第 2 步的结果就当检查点看；第 9 步跳过交接 D，只做检查；第 6、10 步可以合成一次提权运行。

**用 v2rayN 的**：status 会报"没找到 Clash Verge"。交接 A、D 时让用户看 SETUP 附录 A；第 5 步和第 9 步里补规则、交接 B 的部分跳过；端口是 v2rayN 左下角 `mixed:` 后面的数字（默认 10808）。

**时区**：第 9 步检查里，时区那一项按 IP 库多数结果判断；不一致时，提示里带着 Windows 时区名（如 `Pacific Standard Time`），对得上就不用改。

**提权运行（第 6、10 步，Windows）**：

1. 先不提权预演：`windows-setup.ps1 -NetworkTask -WhatIf`（第 10 步是 `-TimeZone "<Windows 时区名>" -WhatIf`），把要改的内容给用户看。
2. 用户同意后，在同一条回复里先说"马上会弹出管理员确认窗口，请点「是」。关 IPv6、改网卡 DNS、改时区都是系统设置，要管理员权限"，再运行（日志放在临时目录）：

   ```powershell
   Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"<skill>\scripts\setup\windows-setup.ps1"','-NetworkTask','-LogPath','"<日志路径>"'
   ```

   第 10 步把 `'-NetworkTask'` 换成 `'-TimeZone','"<Windows 时区名>"'`；两步合在一起做就两个都带上。
3. 读日志确认结果。用户点了「否」，`Start-Process` 会报错，问过用户再来一次。

用户经常连需要网页登录的 Wi-Fi（酒店、机场、部分校园网）的，第 6 步加 `'-KeepDns'`，只关 IPv6，不改网卡 DNS。

**删字体（第 7 步，Windows）**：WPS、小米、华为、阿里这些厂商会往电脑里装自己的字体，网页能测出来，fuck-claude 记 10 分。`fonts.py` 的名单直接读自 fuck-claude 的规则，系统自带的微软雅黑、宋体不在名单里。

1. `python <skill>/scripts/setup/fonts.py list`，列出装了哪几款。
2. 讲清楚，再问用户同不同意，**不能悄悄删**：
   - 删哪几款（把 list 的结果原样给他）；
   - 影响：用到这些字体的文档（多半是 WPS 里的）会改用别的字体显示，排版可能变样；
   - 删之前会备份到 `%USERPROFILE%\claude-antiban-backup\fonts-<时间>`，随时能用 `fonts.py restore <备份文件夹>` 装回去；
   - 删完要重启电脑才生效；以后重装或更新 WPS，可能又装回来。
3. 用户明确同意后，先预演 `fonts.py remove --dry-run`，再提权运行（同样先提醒弹窗点「是」）：

   ```powershell
   Start-Process (Get-Command python).Source -Verb RunAs -Wait -ArgumentList '"<skill>\scripts\setup\fonts.py"','remove','--log','"<日志路径>"'
   ```

4. 读日志，告诉用户备份在哪，请他重启电脑；重启后回来说"重启好了"，再跑 `fonts.py list` 确认已经清空。

macOS 没有这个脚本：请用户在「字体册」里找到这些字体，自己移除。

**macOS**：`macos-setup.sh --network` 和 `--timezone <IANA 时区名>` 要 sudo，把带绝对路径的命令按交接格式交给用户，在「终端」里运行，先加 `--dry-run`。macOS 脚本没有在真机上完整验证过，预演不能省。

**Clash 改坏了**（用户说网页打不开）：先请用户关掉「DNS 覆写」，再运行 `clash_verge.py restore` 还原备份，然后交接 B。

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
- `scripts/setup/fonts.py` 的名单直接从 `vendor/fuckclaude-signals.js` 的 `FONTS_CN_VENDOR` 读，同步上游规则后自动跟着变；上游改了变量名，脚本会报错。
- `scripts/setup/clash_verge.py` 依赖 Clash Verge Rev 的配置文件布局：`profiles.yaml` 里的 `current` 和 `option.rules`、`dns_config.yaml`、生成出来的 `clash-verge.yaml`。Clash Verge 大改版后要核对一遍。
