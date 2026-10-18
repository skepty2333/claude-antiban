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
- **不用** Playwright、无头浏览器或浏览器自动化扩展来跑指纹。要测的是用户登录 Claude 的那个浏览器：自检必须用 `--browser` 写明是哪个浏览器（不写就报错退出），检测页在它里面打开，不会自己去开默认浏览器；安全 DNS、默认浏览器这几项也按它来判断。
- 时区按**多个 IP 库的多数结果**对齐（自检输出里已算好），不凭节点名或记忆猜。
- 改系统、代理软件、浏览器设置前，先说清楚现状、要改什么、怎么回滚，用户确认后再动手。只改这次要改的项。Clash 只通过 `clash_verge.py` 改：开关（`verge.yaml`、`config.yaml`）、DNS 覆写、当前订阅的规则文件；订阅、节点和生成出来的 `clash-verge.yaml` 不碰。
- **只用本 skill 的脚本改东西。** 脚本没覆盖的，交给用户在界面上做（SETUP 里写了的照 SETUP），或者停下来说明。不要自己写注册表启动项（Run 键）、计划任务、浏览器组策略，不要新建浏览器配置文件或快捷方式，不要替用户改 Clash 的端口：这些不在备份和 `restore` 的范围里，改坏了不好还原。
- **你自己也是联网的程序。** 用户换上自己买的静态 IP 之前，电脑用的是真实 IP 或临时代理的共用 IP。要护住的是用户真正的 Claude 账号和订阅：如果你是登录着这个账号的 Claude（Claude 桌面端、用账号登录的 Claude Code），你的流量会把账号带到这些 IP 上，**不要带配置流程**，直接停下，请用户换别的 AI 来带，比如 WorkBuddy、Codex 这类 agent，或者 Claude Code 配上他自己的 API。走用户自己 API 的 Claude Code（设了 `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_BASE_URL`）不碰他的账号，可以带；拿不准是哪种，就问用户。体检流程只在用户已经换上自己的静态 IP、设好 `HTTPS_PROXY` 之后才可以由你来跑。
- **Clash 由你来重启，不要让用户点「退出」。** 正常退出时 Clash 会清掉系统代理，浏览器随即改用真实 IP。`clash_verge.py apply`、`restore` 是强制结束再启动，系统代理设置留着，中间那几秒只会连不上，不会走真实 IP；服务模式下内核由服务托管，连不上都不会。

## 怎么跟用户说

- 用大白话。DNS、IPv6、WebRTC、TUN 这些词非提不可时，顺带一句它对用户意味着什么，比如"WebRTC 会让网页绕过代理，直接拿到你的真实 IP"。
- 检测结果里的 [X]，说的都是同一件事：用户的真实 IP 或真实网络环境会被 Claude 看到。WebRTC 漏 IP、电脑的 IPv6 开着、电脑或浏览器在用国内的 DNS、登录 Claude 的浏览器开着安全 DNS、Claude 的入口没走代理、出口不止一个、默认浏览器没设好，**任何一项单独出现都可能导致封号**。用严肃的语气直接说出来，并且说清：修好之前不要登录 Claude。
- 不要加冲淡问题的话，比如"不代表封号概率""不能据此认定泄漏""只是提醒""影响不大"。拿不准的地方，说还要测什么、怎么测，不要说成问题不大。
- 汇报分三组：必须修的、建议改的、已经没问题的。每一项说清是什么问题、会怎样、谁来改、在第几步。
- fuck-claude 分数讲成"网页能看出你是中国用户的程度"，分越高越容易被认出来。

## 用户只发来 GitHub 链接时

脚本要在本地跑，先把仓库拉下来：`git clone https://github.com/skepty2333/claude-antiban "<用户主目录>/claude-antiban"`。直连 GitHub 拉不下来，就让 git 走用户现在的代理：`git -c http.proxy=http://127.0.0.1:<端口> clone …`。没有 git 的话，下载 `https://github.com/skepty2333/claude-antiban/archive/refs/heads/main.zip` 解压到同一个位置。之后下文的 `<skill>` 就指这个目录。告诉用户放在哪了，不用让他自己下载。

## 先判断用户要哪一种

- **新电脑或还没配过**（"从零配置""教我配""WebRTC 扩展怎么设"）→ 走**配置流程**。
- **已经配过，想检查或排障**（"帮我查查""是不是泄漏了""时区对不对"）→ 走**体检流程**。

## 开工前先问清两件事

两种流程都一样。用户第一条消息里没说的，先问，问清楚再跑检测。

1. **静态 IP**：买了没有，现在电脑上是不是就在用它。
   - **已经在用**：基线检测直接查这个 IP（不加 `--no-claude`），第 2 步的结果就当 IP 的检查点；第 8 步不用交接 C，只做检查；第 6、9 步可以合成一次提权运行。IP 是用户买来的，多半没问题，问题通常出在别的地方，重点查那些；IP 真查出滥用记录、出口国家不对，照样直说，请他找卖家。
   - **还没买，或者买了还没到**：先用他现在的代理，做不依赖 IP 的步骤，做到第 8 步停下来等。
2. **登录 Claude 用哪个浏览器**：先运行 `python <skill>/scripts/browsers.py`，看默认浏览器是哪个、装了哪些，再问用户。**不要把默认浏览器当成答案，也不要替用户挑一个。** 他用的是 360、QQ、夸克这类国产浏览器的，请他换成 Chrome、Edge、Firefox 或 Brave。

**默认浏览器和登录 Claude 的浏览器不是同一个时**，停下来讲给用户：Claude 桌面端、Claude Code 登录时，还有邮件里的登录链接，都会自动用默认浏览器打开，用户选不了，所以默认浏览器也会碰到 Claude。让他二选一：

- **把登录 Claude 的浏览器设成默认浏览器（推荐）**。Windows 不让程序替用户改默认浏览器：运行 `start ms-settings:defaultapps` 帮他打开「默认应用」这一页，请他找到这个浏览器，点「设为默认值」，做完再跑一次 `browsers.py` 确认。之后只设这一个浏览器。
- **不想换默认浏览器**：两个浏览器都要照交接 B 设好，都不能是国产浏览器。`clash_verge.py apply --browser` 两个都写上，两个都全走节点；自检两个都要测，`--browser <登录 Claude 的> --also <默认的>` 跑一次，再 `--browser <默认的> --also <登录 Claude 的>` 跑一次。代价是两个浏览器上国内网站都会慢，国内网站最好用第三个浏览器。

比特浏览器、AdsPower 这类指纹浏览器，本 skill 没有测过，检测结论不能套到它们身上。

## 和用户分工：交接

技术活都由你做。只有下面这几件必须用户亲手做，`SETUP.md` 里也只写了这些。轮到用户时，这条回复只做交接，然后停下等他回复，不要在同一条回复里接着调用工具。

| 交接 | 用户要做的 | 发给用户 |
|---|---|---|
| **A 让代理跑起来** | 装 Clash Verge，导入他现在在用的订阅，选节点和模式 | `SETUP.md`「一、让代理跑起来」，截图 `assets/clash-1-import-subscription.png` 到 `assets/clash-3-node-mode.png` |
| **B 浏览器** | 在登录 Claude 的浏览器里（默认浏览器不是它、又不想换的，两个都做）装 WebRTC 扩展、关安全 DNS、语言改成英文并删掉中文、防开机抢跑；以后网页版 Claude 只用这个浏览器，国内网站用另一个 | `SETUP.md`「二、浏览器设置」，截图 `assets/webrtc-1-store.png` 到 `assets/webrtc-4-use-proxy.png`，安全 DNS 是 `assets/chrome-secure-dns.png`（Edge 是 `assets/edge-secure-dns-1.png`、`edge-secure-dns-2.png`） |
| **C 换上静态 IP** | **这时必须已经买好 IP**；导入新订阅、选节点和模式、删掉临时订阅 | `SETUP.md`「三、换上你买的静态 IP」；还没买的，发 `README.md`「要买的东西」 |
| **D 登录** | **这时必须已经有 Claude 账号**；登录，不在手机上装 Claude App；普号登录后先正常用至少 72 小时再充会员 | `SETUP.md`「五、登录 Claude」。交接时把 72 小时这一条单独说一遍 |

不要一开始就让用户去买东西。IP 到第 8 步才用得上，账号到第 11 步才用得上，前面的步骤照常做；做到这两步时用户还没买好，就停下等他。

还有几种配合，不用单独停下，但必须在同一条回复里事先说清楚：

- **检测页别关**：跑带浏览器的检测前，告诉用户会弹出一个检测页，大约 15 秒内不要关。
- **管理员确认点「是」**：运行提权命令前，告诉用户马上会弹窗、为什么要管理员权限。
- **重启 Clash**：`clash_verge.py apply`、`restore` 会重启 Clash，事先告诉用户网页会断几秒，正常。
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
| 1 | 摸底 | 你 | `python <skill>/scripts/setup/clash_verge.py status`、`python <skill>/scripts/browsers.py`；Windows 再跑 `<skill>/scripts/setup/windows-setup.ps1`（不带参数只看状态） | 知道用户做到哪了，「开工前先问清两件事」都问清了，默认浏览器的事也定了。登录 Claude 的浏览器以后全走节点，国内网站要换另一个浏览器，这一点讲清楚 |
| 2 | 基线检测 | 你；用户别关检测页 | `python <skill>/scripts/selfcheck.py --browser <登录 Claude 的浏览器>`（两个浏览器都设的，加 `--also <另一个>`）。还没在用买的 IP 就加 `--no-claude` | 用大白话讲给用户：fuck-claude 现在多少分，命中了哪几项，每一项在后面第几步、由谁来改；中文字体那一项改不了，也要说明。记下报告 JSON 的路径，第 10 步要对比 |
| 3 | 让代理跑起来 | 用户 | 交接 A，只交 status 里没做好的部分；先用他现有的订阅 | 用户回复做完 |
| 4 | Clash 配置 | 你 | `clash_verge.py apply --browser <chrome/edge/firefox/brave，两个都设的写两个> --dry-run` 给用户看；同意后去掉 `--dry-run` 再跑：备份，改开关（系统代理开、TUN 关、开机自启、静默启动、IPv6 关、局域网关、DNS 覆写开），写 DNS 覆写和前置规则（登录 Claude 的浏览器和 `claude.exe` 全走节点，排在国内直连前面），重启 Clash | `clash_verge.py status` 全 [OK]，包括「系统里实际的代理设置」「系统里登记的开机自启」「代理端口上的程序」；`verify` 为 [OK]（进程规则已加载，排在国内直连前面）。端口上还有别的程序的，按那一项的提示请用户退出或卸载它（多半是别的代理软件、加速器），不要自己换端口绕过去。「代理模式」那一项会写出 Claude 的流量最后落在哪个节点，落在自动选择的组或 DIRECT 上的，按提示请用户在 Clash 里改。模式不对的，请用户在 Clash 首页改；系统里没生效的，请用户在 Clash「设置」页手动打开那个开关（截图 `assets/clash-4-settings.png`，图里虚拟网卡开着，那是原教程的状态） |
| 5 | 代理变量 | 你 | `HTTPS_PROXY` 没设或端口和 status 的「代理端口」不一致时，`windows-setup.ps1 -ProxyPort <端口>`（macOS：`macos-setup.sh --proxy-port <端口>`） | 用户变量 `HTTPS_PROXY` 是 `http://127.0.0.1:<端口>` |
| 6 | 系统 IPv6、网卡 DNS | 你；用户点「是」 | 见下面「提权运行」，只带 `-NetworkTask` | 日志里每块网卡 IPv6 关、DNS 为 `1.1.1.1, 8.8.8.8` |
| 7 | 浏览器和指纹 | 用户设浏览器；你删字体，用户同意并点「是」 | 第 2 步命中的指纹项，除了时区（第 9 步），都在这一步处理。先交接 B：命中「国产浏览器」的，请用户先换成 Chrome、Edge、Firefox 或 Brave；两个浏览器都设的，两个都要做。命中「国产厂商字体」的，再按下面「删字体」处理，没命中就跳过 | 用户回复浏览器设完；字体删完、重启过，或者用户决定不删（尊重他的决定，最后报告里这一项照样是 [!]） |
| 8 | 换上静态 IP，检查 IP | 用户先换，你再查 | 交接 C（用户还没买好 IP，就停在这里等）→ `clash_verge.py status`，核对 Claude 的流量落在新买的节点上 → `clash_verge.py apply --browser <同上>`，给新订阅补前置规则并重启 → `selfcheck.py --skip-browser --browser <同第 2 步>`（两个浏览器都设的带上 `--also`） | 出口国家对，IP 没有滥用记录；不合格就停下，请用户找卖家。时区那一项告诉你要不要改、改成什么 |
| 9 | 时区 | 你；用户点「是」 | 见下面「提权运行」，只带 `-TimeZone` | 日志里时区对，自动设置时区已关闭 |
| 10 | 完整检测，和起点对比 | 你；用户别关检测页 | `python <skill>/scripts/selfcheck.py --browser <同第 2 步>`；两个浏览器都设的，`--browser A --also B` 和 `--browser B --also A` 各跑一次 | "严重"为 0，主要项 [OK]。把起点和现在的 fuck-claude 分数、各项变化列给用户看 |
| 11 | 登录 | 用户 | 交接 D（用户还没有账号，就停在这里等） | 用户回复登录好了 |
| 12 | Claude Code（需要的话） | 你 | 按 Anthropic 官方文档安装，Windows 先装 Git for Windows | `Get-Command claude` 找得到。不要运行 `claude` 来测试 |

**用 v2rayN 的**：status 会报"没找到 Clash Verge"。交接 A、C 时让用户看 SETUP 附录 A，开关也请他照附录 A 自己设，路由选「全局」（v2rayN 做不了专用浏览器的进程规则）；第 4 步和第 8 步里的 `apply` 跳过；端口是 v2rayN 左下角 `mixed:` 后面的数字（默认 10808）。

**时区**：第 8 步检查里，时区那一项按 IP 库多数结果判断；不一致时，提示里带着 Windows 时区名（如 `Pacific Standard Time`），对得上就不用改。

**提权运行（第 6、9 步，Windows）**：

1. 先不提权预演：`windows-setup.ps1 -NetworkTask -WhatIf`（第 9 步是 `-TimeZone "<Windows 时区名>" -WhatIf`），把要改的内容给用户看。
2. 用户同意后，在同一条回复里先说"马上会弹出管理员确认窗口，请点「是」。关 IPv6、改网卡 DNS、改时区都是系统设置，要管理员权限"，再运行（日志放在临时目录）：

   ```powershell
   Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"<skill>\scripts\setup\windows-setup.ps1"','-NetworkTask','-LogPath','"<日志路径>"'
   ```

   第 9 步把 `'-NetworkTask'` 换成 `'-TimeZone','"<Windows 时区名>"'`；两步合在一起做就两个都带上。
3. 读日志确认结果。用户点了「否」，`Start-Process` 会报错，问过用户再来一次。

用户经常连需要网页登录的 Wi-Fi（酒店、机场、部分校园网）的，第 6 步加 `'-KeepDns'`，只关 IPv6，不改网卡 DNS。

**删字体（第 7 步里，Windows）**：WPS、小米、华为、阿里这些厂商会往电脑里装自己的字体，网页能测出来，fuck-claude 记 10 分。`fonts.py` 的名单直接读自 fuck-claude 的规则，系统自带的微软雅黑、宋体不在名单里。

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

**macOS**：`macos-setup.sh --network` 和 `--timezone <IANA 时区名>` 要 sudo，把带绝对路径的命令按交接格式交给用户，在「终端」里运行，先加 `--dry-run`。macOS 脚本和 `clash_app.py` 里的 macOS 部分都没有在真机上完整验证过，预演不能省；`apply` 没能重启 Clash 的话，请用户自己退出再打开。

**Clash 改坏了**（用户说网页打不开）：运行 `clash_verge.py restore`，用备份还原并重启 Clash。

## 体检流程

1. 先按「开工前先问清两件事」问清，再运行 `python <本 skill 目录>/scripts/selfcheck.py --browser <登录 Claude 的浏览器>`。需要 Python 3.9+，不用装依赖，约 15 秒。
   - 默认浏览器不是它的，结果里「默认浏览器」一项会是 [X]，按那一节让用户二选一。
   - 浏览器打不开检测页：加 `--no-open`（`--browser` 照样要写），把打印出的地址给用户，让他在那个浏览器里打开；结果里「这次测的是哪个浏览器」一项会告诉你实际测的是哪个。
   - 用户的浏览器里有好几个用户（配置文件）的，确认检测页开在他登录 Claude 的那一个里：WebRTC 扩展是按配置文件装的。
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
| 这次测的是哪个浏览器 | 就是登录 Claude 的那个；浏览器那几项只代表它 |
| 默认浏览器 | 就是登录 Claude 的浏览器；或者也照样设好了，并且用 `--browser <它>` 单独测过 |
| 浏览器 / 系统代理 / Claude Code 三个入口 | 出口相同，且不在 CN、HK、MO |
| 不认代理的程序（直连） | 仅供参考；等于代理出口，说明 TUN 在接管 |
| 出口 IP 是否唯一 | 只有一个；出现多个，通常是用了自动测速组或分流规则 |
| DNS：浏览器这条路 | 解析服务器只在出口所在国 |
| DNS：系统解析 | 不是国内运营商的 DNS |
| WebRTC | 只出现 `.local` 地址或代理出口 IP |
| IPv6 | 电脑上没有能用的 IPv6；开着就是 [X] |
| 系统时区 | 不是中国时区，且与 IP 库多数结果一致 |
| fuck-claude 评分 | 0–30 为低风险；中文版 Windows 的字体固定约 +14，正常 |
| 出口 IP 质量 | 有滥用记录要换；机房或代理标记说明不理想，但能用 |
| 浏览器安全 DNS | 登录 Claude 的浏览器（`--browser`、`--also`）都已关闭 |
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
| 订阅里有好几个节点，就必须开全局模式 | 看 status 的「代理模式」：Claude 的流量最后落在一个固定节点上就行，规则模式也没问题；落在自动选择的组或 DIRECT 上才要改 |
| 代理端口被别的程序也占着，没关系 | 别的代理软件、加速器也在听同一个端口时，Clash 一停，流量就进了它那里，出口不受控制（真实情况：出口一下变成了日本）。status 的「代理端口上的程序」必须只有 Clash |
| 只要登录 Claude 的浏览器设好就行 | 默认浏览器也会碰到 Claude：桌面端、Claude Code 的登录页和邮件里的登录链接都用它打开 |
| 删掉微软雅黑来降分 | 系统字体不能删；字体只是网页指纹，Claude Code 不读 |
| 国内直连就够了 | 网页、邮件能让浏览器去请求国内地址，借直连拿到真实 IP（ip.net.coffee 的「中国出口 IPv4」就是这么测的）。专用浏览器和 `claude.exe` 要用进程规则全走节点；不开 TUN 时 mihomo 也能认出系统代理连接的进程（Windows 实测） |
| Claude 的邮件随手在手机上看 | 赠金、活动邮件带追踪像素和跳转链接，打开、点击时的 IP 会被发件方看到；只在专用浏览器里用网页邮箱看（全走节点），最好 Gmail 网页版。登录交接时顺带提醒 |

## 维护

- `scripts/vendor/fuckclaude-signals.js` 来自 `LinXiaoTao/FuckClaude`（MIT 许可）。上游改了评分规则时，用 `scripts/update_fuckclaude_signals.py` 同步：先只看 commit，再用 `--commit` 构建，最后加 `--yes` 写入。
- `assets/` 里的截图改编自第三方配置教程：已打码，并按本路线重新标注。Clash Verge 界面改版后需要重新截图。
- `scripts/setup/fonts.py` 的名单直接从 `vendor/fuckclaude-signals.js` 的 `FONTS_CN_VENDOR` 读，同步上游规则后自动跟着变；上游改了变量名，脚本会报错。
- `scripts/setup/clash_verge.py` 依赖 Clash Verge 的配置文件布局：`profiles.yaml` 里的 `current` 和 `option.rules`、`dns_config.yaml`、生成出来的 `clash-verge.yaml`。Clash Verge 大改版后要核对一遍。
