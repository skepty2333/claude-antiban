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
- 改系统、代理软件、浏览器设置前，先说清楚现状、要改什么、怎么回滚，用户确认后再动手。只改这次要改的项，不碰订阅、节点和程序生成的配置文件。
- **你自己也是联网的程序。** 如果你是运行在用户电脑上的 Claude（例如 Claude Code），而用户还没做完 `SETUP.md` 的第 1–4 步，那么你的流量很可能正从真实 IP 发出去。这时应先停下，请用户按 `SETUP.md` 手动做完第 1–4 步，或换别的工具来带，然后再继续。

## 先判断用户要哪一种

- **新电脑或还没配过**（"从零配置""教我配""WebRTC 扩展怎么设"）→ 走**配置流程**。
- **已经配过，想检查或排障**（"帮我查查""是不是泄漏了""时区对不对"）→ 走**体检流程**。

## 和用户分工：到交接点就停

技术活由你做：跑脚本、读自检结果、对照文档讲解。下面这些只能用户本人做。到了这些地方，这条回复只做交接，然后停下等用户回复，不要接着往下做。

| 交接点 | 用户要做的 |
|---|---|
| **开场**（配置流程的第一条回复） | 读 `README.md`，弄懂思路；按 README「要买的东西」买独享静态 IP 和 Claude 账号；装好 Clash Verge（或 v2rayN）和 Python。提醒他：账号先别登录 |
| **图形界面**（第 1–3 步、第 6 步；v2rayN 是附录 A） | 照 `SETUP.md` 的截图在界面上操作 |
| **管理员终端**（第 5 步） | 自己打开管理员终端，运行你给的命令 |
| **自检通过后**（第 9 步） | 用配好的浏览器注册或登录 Claude；要开会员的，按 `SETUP.md` 第 9 步去开 |

交接时一次只交一步，按这个格式写：

```
**现在到了**：第 X 步，<这一步是干什么的，一句话>
**该你做了**：<要做的事，附链接或截图的完整路径>
**做完回我**：<要用户回复什么，比如"好了"、界面截图、某个数字>
```

不要替用户下单付款，也不要向用户要订阅链接、账号或密码。

## 配置流程：按 `SETUP.md` 一步一步带

`SETUP.md` 是给人看的完整教程：第 0 步到第 11 步，外加 v2rayN、macOS、虚拟机、TUN 四个附录。每步都有截图（`assets/`）和"怎么确认"。

1. 第一条回复就是开场交接。除了上表里的事，再问清楚三件事：
   - 用 Clash Verge 还是 v2rayN；
   - Windows 还是 macOS；
   - 平时用哪个浏览器登录 Claude。

   用户说已经准备好了，就直接从第 1 步开始。
2. 一次只带一步，做完这步的"怎么确认"再进下一步。
   - **图形界面的步骤**（导入订阅、选节点、Clash 设置、装扩展）：照 `SETUP.md` 讲给用户，并告诉用户对应截图的完整路径（在 `assets/` 里）；界面支持发送文件的话，直接发过去。用户的界面和截图对不上时，请他截一张自己的界面回来，再对照着讲。
   - **能用脚本的步骤**（第 4 步代理变量、第 5 步关 IPv6、第 7 步时区）：命令里一律写**脚本的绝对路径**。先用 `-WhatIf` 或 `--dry-run` 预演给用户看，用户同意后再执行。第 5 步要管理员权限，请用户自己开管理员终端；`-NetworkTask` 默认会把网卡 DNS 固定为 `1.1.1.1`/`8.8.8.8`；用户经常连需要网页登录的 Wi-Fi 时，加 `-KeepDns`。
   - **代理软件必须开机自启**，不管是 Clash Verge 还是 v2rayN。做第 3 步时（v2rayN 是附录 A），务必确认用户打开了开机自启。
3. 第 4 步之后有个"检查点"：运行 `python scripts/selfcheck.py --skip-browser`。出口国家不对，或者 IP 有滥用记录，就先停下，让用户找卖家处理。这次输出里 IP 库的多数结果，第 7 步对时区还要用。
4. 做第 8 步完整自检。"严重"为 0、主要项都是 [OK]，环境才算配好。
5. 然后是第 9 步的交接：用户登录 Claude、开会员。用户需要 Claude Code 的话，再带第 11 步。

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
