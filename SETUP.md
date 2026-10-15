# 从零配置：让 Claude 只从一个干净的海外出口出去

**适用范围**：Windows 10/11，一个刚装好、没改过设置的 Clash Verge Rev。用 v2rayN 的看[附录 A](#附录-a用-v2rayn-的)，用 Mac 的看[附录 B](#附录-bmacos)。

**走的路线**：系统代理 + 持久代理变量，**不开虚拟网卡（TUN）**。不少教程让你开 TUN，这里不开，原因有两个：

- 开了 TUN，微信等国内软件也会被强制出国，容易登录受限；
- Clash 一退出，所有程序都会退回真实 IP。

这套做法下，浏览器、Claude 桌面端和 Claude Code 都走同一个出口，各项检测都能过。原理见 `references/routing.md`。

**用时**：大约 30 分钟。每一步末尾都有"怎么确认"，确认通过再做下一步。

> **⚠ 第 1–4 步做完之前，不要打开 Claude。** 这包括 claude.ai 网页、Claude 桌面端，也包括"用 Claude Code 来带你做这份配置"——在那之前，它们的流量会直接用你的真实 IP 发出去。前四步请照本文手动做，或者让别的工具帮你。

**两个基本操作**（后面会反复用到）：

- **在 skill 文件夹里打开终端**：在文件资源管理器里打开 `claude-antiban` 文件夹，在空白处按住 Shift 再点右键，选「在终端中打开」（或「在此处打开 PowerShell 窗口」）。
- **打开管理员终端**：右键开始按钮，选「终端（管理员）」或「Windows PowerShell（管理员）」。管理员终端默认在 `C:\Windows\System32`，要先进入 skill 文件夹，例如：

  ```powershell
  cd "$HOME\.claude\skills\claude-antiban"
  ```

  把路径换成你实际放 `claude-antiban` 文件夹的位置。不确定的话，在文件夹地址栏点一下，就能复制完整路径。

---

## 第 0 步：准备

1. **一个独享的静态 IP 节点。** 选购标准见 `references/ip.md`：独享、IP 固定不变、在 Anthropic 支持的地区、住宅或 ISP 类型优先。卖家会给你一个订阅链接（`https://…`，Clash 用）或一个节点链接（`vless://…`，v2rayN 用）。**不要外传，也不要和别人共用。**
2. **电脑上只留一个代理软件。** 其他代理客户端全部退出，两个同时开会抢端口。
3. **下载 Clash Verge Rev**：到 GitHub 上的 `clash-verge-rev/clash-verge-rev`，进 Releases 页面，下载稳定版的 Windows x64 安装包（文件名带 `setup.exe`）并安装。如果安全软件拦截，选择允许；拦得太凶，可以在安装期间临时关掉它。
4. **安装 Python 3.9 或更高版本**，后面的自检脚本要用：到 python.org 下载，安装时勾选 "Add python.exe to PATH"。装好后新开一个终端，输入 `python --version`，能看到版本号就行。

## 第 1 步：导入订阅

1. 打开 Clash Verge，在首页点「导入订阅」，粘贴订阅链接后导入。

   ![导入订阅](assets/clash-1-import-subscription.png)

2. 进入「订阅」页，右键刚导入的订阅，选「使用」。

   ![使用订阅](assets/clash-2-use-subscription.png)

**怎么确认**：打开「代理」页，能看到节点列表；点测速，节点能显示延迟。导入失败或节点超时，看文末[常见问题](#常见问题)。

## 第 2 步：选节点、选模式、打开系统代理

![选节点、模式、系统代理](assets/clash-3-node-mode.png)

1. **选节点。** 在首页「当前节点」里选你买的那个静态 IP 节点，一般以 VPS 或 ISP 开头。**选定以后不要来回换。**
2. **选代理模式：看订阅里有几个节点。**

   | 订阅里的节点 | 用哪个模式 | 为什么 |
   |---|---|---|
   | **只有一个**（买静态 IP 通常是这样） | **规则** | 海外网站走节点，国内网站直连，出口也不会跳 |
   | **有好几个** | **全局**（图里选的就是全局） | 规则模式下，订阅常把 Claude 分进"自动选择"组，出口会跳来跳去 |

   全局模式下，所有网页都从海外出去。国内网站会变慢；银行、12306、学校教务系统这类网站，可能要求额外验证，甚至直接拒绝访问。遇到这种情况，临时切到「规则」或「直连」，用完再切回来。切换期间不要访问 Claude。

   不管选哪个模式，微信、QQ 的主程序都不受影响，它们本来就不走系统代理。

   **用规则模式时，再加两条前置规则，让国内网站直连**（订阅自带同类规则也没关系，重复不影响）：在「订阅」页右键你的订阅 →「编辑规则」，添加两条**前置**规则：

   - 类型 `GEOSITE`，内容 `cn`，策略 `DIRECT`；
   - 类型 `GEOIP`，内容 `CN`，策略 `DIRECT`，勾选 `no-resolve`。

   如果编辑器有高级（YAML）模式，也可以直接写成：

   ```yaml
   prepend:
     - GEOSITE,cn,DIRECT
     - GEOIP,CN,DIRECT,no-resolve
   ```

   按钮名称以你的版本为准。全局模式不看规则，这一步可以跳过。
3. **打开系统代理。** 在「网络设置」里点「系统代理」并打开开关。「虚拟网卡模式」不要开。

**怎么确认**：用浏览器打开 `https://ip.net.coffee/claude/`，显示的应该是你节点所在的国家。

## 第 3 步：Clash 的其余设置

进入「设置」页，按图逐项设好：

![设置页](assets/clash-4-settings.png)

| 设置项 | 应设为 | 为什么 |
|---|---|---|
| 系统代理 | 开 | 浏览器和 Claude 桌面端靠它走代理 |
| 虚拟网卡模式 | 关（图里是开着的，那是原教程的状态） | 本路线不用 TUN |
| 开机自启、静默启动 | **必须开** | 开机后代理软件没起来，浏览器就会用真实 IP 上网。不管用哪个代理软件，都要设成开机自启 |
| IPv6 | 关 | 防止 IPv6 流量绕开代理 |
| 局域网连接 | 关 | 不需要 |
| 端口设置 | **记下这个数字**（默认 `7897`） | 第 4 步要用 |
| DNS 覆写 | 开，并换成下面的配置 | 见下文 |

**DNS 覆写**：点它旁边的齿轮，打开 DNS 覆写设置，切到 YAML 编辑（不同版本按钮位置略有不同）。

1. **先把里面原来的内容全选、复制，存到一个记事本里**，这就是回滚用的备份。
2. 把内容整个换成下面这段，然后保存：

```yaml
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:
    - 'geosite:cn'
    - 'geosite:private'
    - '+.lan'
    - '+.local'
    - '+.msftncsi.com'
    - '+.msftconnecttest.com'
  default-nameserver:
    - 'tls://223.5.5.5'
  nameserver:
    - 'https://1.1.1.1/dns-query#RULES'
    - 'https://8.8.8.8/dns-query#RULES'
  nameserver-policy:
    'geosite:cn':
      - 'https://dns.alidns.com/dns-query'
      - 'https://doh.pub/dns-query'
  proxy-server-nameserver:
    - 'https://doh.pub/dns-query'
    - 'https://dns.alidns.com/dns-query'
```

这段配置的作用：

- **海外域名**（包括 claude.ai）用加密 DNS 查询，查询本身也经代理出去；`#RULES` 表示跟着你选的模式和节点走。
- **国内域名**交给阿里或腾讯的加密 DNS，速度快，代理断了也照样能解析。
- **不会把"你在访问 claude.ai"这件事告诉国内的 DNS。**

保存后如果打不开网页，有两种回滚方式：把备份粘回去，或者直接关掉「DNS 覆写」开关。

**不要**把电脑网卡的 DNS 改成 `127.0.0.1`，否则迅雷、网易云等软件会断网，原因见 `references/dns.md`。

## 第 4 步：让 Claude Code 也走代理（持久代理变量）

浏览器和桌面端听系统代理，但 Claude Code 命令行只认 `HTTPS_PROXY` 这个环境变量。把它存成永久的用户变量。

**做法一：用脚本。** 在 skill 文件夹里打开终端，先预演一遍（端口换成第 3 步记下的数字）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup\windows-setup.ps1 -ProxyPort 7897 -WhatIf
```

确认显示的改动没问题后，去掉末尾的 `-WhatIf` 再运行一次。

**做法二：手动设置。** 打开 开始菜单 → 搜"编辑账户的环境变量" → 在"用户变量"里新建下面三个：

| 变量名 | 值 |
|---|---|
| `HTTPS_PROXY` | `http://127.0.0.1:7897` |
| `HTTP_PROXY` | `http://127.0.0.1:7897` |
| `NO_PROXY` | `localhost,127.0.0.1,::1` |

**要知道的两个影响**：

- 好处：哪天 Clash 没开，Claude Code 会直接报错，而不是偷偷用真实 IP 直连。
- 代价：pip、npm、git 这些读环境变量的工具也会走代理。所以 Clash 关着的时候，它们会连不上，开着 Clash 就正常。

**怎么确认**：**新开**一个终端，输入 `echo $env:HTTPS_PROXY`，能看到 `http://127.0.0.1:7897`。已经开着的终端读不到新变量，要关掉重开。

### 检查点：节点合格吗？

在 skill 文件夹里打开终端，运行：

```powershell
python scripts\selfcheck.py --skip-browser
```

看结果里的两样：

- **出口国家**：应该是你买的那个国家；
- **"出口 IP 质量"**：如果有"滥用记录"，先找卖家换 IP，再往下做，不然后面都白配。

这次输出开头的"IP 库"几行，第 7 步对时区还要用。

## 第 5 步：关掉系统 IPv6、固定网卡 DNS（管理员，做一次即可）

为什么要做：

- Clash 里关掉 IPv6 还不够。系统的 IPv6 如果开着，IPv6 流量会绕过代理直接出去。
- 网卡 DNS 固定成 `1.1.1.1` / `8.8.8.8`，不走代理的软件就不会再用运营商的 DNS，DNS 检测里系统这条路也不会出现国内运营商。
- 换 Wi-Fi、插 USB 网卡、用手机热点时，新网卡默认又会打开 IPv6，DNS 也会变回自动。所以要装一个计划任务，**每次开机、每次联网**都自动再设一遍。

做法：打开管理员终端，`cd` 到 skill 文件夹（见文首），先预演：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup\windows-setup.ps1 -NetworkTask -WhatIf
```

确认显示的改动没问题后，去掉末尾的 `-WhatIf` 再运行一次。以后想撤销，加 `-Undo` 运行。

- **只关 IPv6、不动网卡 DNS**：加 `-KeepDns`。适合经常连需要网页登录的 Wi-Fi 的人（酒店、机场、部分校园网）。
- **认证页弹不出来**：固定 DNS 后，这类 Wi-Fi 的登录页可能打不开。临时把网卡 DNS 改回自动（管理员终端：`Set-DnsClientServerAddress -InterfaceAlias "WLAN" -ResetServerAddresses`），登录完成后，下次联网时计划任务会自动改回来。

**怎么确认**：脚本最后打印的"当前状态"里，每块网卡都显示"IPv6 关"，DNS 是 `1.1.1.1, 8.8.8.8`。

## 第 6 步：浏览器（你用来登录 Claude 的那个）

### 6.1 WebRTC：装 WebRTC Network Limiter

WebRTC 是浏览器做音视频通话用的功能。它会绕过代理，直接探测你的真实 IP，必须限制住。下面的截图是 Chrome；用 Edge 的看本节末尾。

1. 打开扩展页面（作者是 Google），点「添加至 Chrome」：`https://chromewebstore.google.com/detail/webrtc-network-limiter/npeicpdbkakmehahjeeohfdhnlpdklia`

   ![应用商店页面](assets/webrtc-1-store.png)

2. 点地址栏右边的拼图图标，打开扩展菜单。

   ![扩展图标](assets/webrtc-2-extension-icon.png)

3. 找到 WebRTC Network Limiter，点它右边的三个点 → 「选项」。

   ![扩展菜单](assets/webrtc-3-menu.png)

4. 选**最后一项**：**Use my proxy server (if present)**。

   ![选择最后一项](assets/webrtc-4-use-proxy.png)

**Edge 的做法**：

1. 用 Edge 打开上面同一个链接。页面顶部会提示「允许来自其他应用商店的扩展」，点允许，再点「添加至 Chrome」（Edge 里也是这个按钮）。
2. 地址栏输入 `edge://extensions`，找到 WebRTC Network Limiter，点「详细信息」→「扩展选项」，同样选最后一项。

**其他浏览器**：

- **Firefox**：地址栏输入 `about:config`，把 `media.peerconnection.ice.default_address_only` 设为 `true`。
- **Safari**：默认不泄露，不用设。

### 6.2 关闭"安全 DNS"

- **Chrome**：地址栏输入 `chrome://settings/security`，关闭「使用安全 DNS」。
- **Edge**：地址栏输入 `edge://settings/privacy`，在「安全性」里关闭「使用安全 DNS」。
- **Firefox**：设置 → 隐私与安全 → 基于 HTTPS 的 DNS，选「关闭」。

### 6.3 浏览器语言（两处都要改）

1. **首选语言**：把节点所在国的语言（比如 English (United States)）**移到第一位**，中文删掉或移到后面。
   - Chrome：`chrome://settings/languages`
   - Edge：`edge://settings/languages`
2. **浏览器界面显示语言**：同一页里有「以这种语言显示 Google Chrome / Microsoft Edge」，也换成同一种语言，然后重启浏览器。检测网站读到的"区域设置"看的是这一项。

### 6.4 防止开机时抢跑

开机后，浏览器可能比 Clash 先启动，并自动恢复上次的 claude.ai 标签页，这一下走的就是真实 IP。

- **启动时打开**：选「打开新标签页」，不要选「继续上次浏览的内容」。
  - Chrome：`chrome://settings/onStartup`
  - Edge：`edge://settings/startHomeNTP`
- **Edge 还要多关两项**：在 `edge://settings/system` 里，关闭「启动增强」和「在 Microsoft Edge 关闭后继续运行后台扩展和应用」。

### 6.5 清理与习惯

- **清理痕迹**：接入新 IP 之前，清空这个浏览器的 Cookie 和缓存。更好的做法是新建一个浏览器用户（配置文件），专门登录 Claude。
- **无痕窗口**：Chrome 叫无痕模式，Edge 叫 InPrivate。它们默认不运行扩展，要在扩展详情里打开「在无痕模式 / InPrivate 中启用」，否则 WebRTC 扩展不起作用。
- **浏览器选择**：不要用 360、QQ、夸克、微信内置浏览器登录 Claude。

## 第 7 步：系统时区对齐节点所在地

据公开的逆向分析，Claude Code 会读取电脑的系统时区。时区是中国时区，或者和 IP 所在地对不上，都是风险信号。

1. **确认节点在哪个时区。** 看检查点那次输出开头的"IP 库"几行，以**多数**给出的时区为准。不要只看一个库，也不要按节点名字猜。
2. **关掉自动时区。** 打开 设置 → 时间和语言 → 日期和时间，关闭「自动设置时区」。不关的话，系统会按定位把时区改回北京时间。
   - 如果这个开关是灰色的，说明定位服务关着，自动时区本来就不会生效，直接下一步。
3. **改时区。** 在同一页手动选择时区，或者在 skill 文件夹的终端里运行（时区名换成你的）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup\windows-setup.ps1 -TimeZone "Pacific Standard Time"
   ```

   常用对照：

   | IP 库显示 | Windows 里的名字 |
   |---|---|
   | America/Los_Angeles（美西） | Pacific Standard Time |
   | America/Phoenix（亚利桑那） | US Mountain Standard Time |
   | America/Denver | Mountain Standard Time |
   | America/Chicago | Central Standard Time |
   | America/New_York（美东） | Eastern Standard Time |
   | America/Anchorage（阿拉斯加） | Alaskan Standard Time |
   | Pacific/Honolulu（夏威夷） | Hawaiian Standard Time |
   | Asia/Tokyo | Tokyo Standard Time |
   | Asia/Singapore | Singapore Standard Time |
   | Asia/Taipei | Taipei Standard Time |
   | Europe/London | GMT Standard Time |

**以后换了节点、而节点所在地变了，要重新对齐时区。**

## 第 8 步：完整自检

用 Chrome 或 Edge 登录 Claude 之前，先跑一遍完整自检。在 skill 文件夹的终端里运行：

```powershell
python scripts\selfcheck.py
```

它会在默认浏览器里打开一个检测页，大约 15 秒后在终端给出结果。如果默认浏览器不是你登录 Claude 用的那个，加 `--no-open`，再把打印出来的地址复制到那个浏览器里打开。

**期望结果**："严重"为 0，并且下面这些项都是 [OK]：

- 浏览器、系统代理、Claude Code 三个入口
- 出口唯一
- 浏览器那条路的 DNS
- WebRTC
- IPv6
- 时区
- 安全 DNS
- 国内软件会不会断网

下面几项是 [!] 也可以接受：

- **IP 被标为机房 IP 或代理 IP**：这改设置解决不了，只能换住宅或 ISP 类型的 IP。
- **fuck-claude 评分里中文字体 +14**：中文版 Windows 都有这一项，属正常。

**人工复核（可选）**：用浏览器逐个打开下面的网站，结果应该和自检一致。

1. **IP 检测**：`https://ip.net.coffee/claude/`，一站式查看 IP、DNS、WebRTC。
2. **whatismyip**：`https://www.whatismyip.com/`。IP 归属地是节点所在国，并且 IPv6 显示 Not Detected。

   ![whatismyip](assets/check-1-whatismyip.png)

3. **DNS 泄露检测**：`https://www.dnsleaktest.com/`，点 Standard Test，结果里不应出现 China。

   ![dnsleaktest](assets/check-2-dnsleaktest.png)

4. **WebRTC 检测**：`https://browserleaks.com/webrtc`，应显示 No Leak。

   ![browserleaks](assets/check-3-browserleaks-webrtc.png)

5. **指纹评分**：`https://fuck-claude.vercel.app/zh/`，点「开始检测」，分数越低越好。

## 第 9 步：日常使用习惯

- **开机后**：Clash 会自动连上。等任务栏右下角出现 Clash 图标，再打开浏览器访问 Claude。
- **"关窗口"不是"退出"**：
  - 点 Clash 窗口右上角的 ×，只是把窗口收到任务栏，代理照常运行；
  - 右键任务栏图标选「退出」，才是真正关掉。
- **Claude 开着的时候，不要退出 Clash。** Clash 退出时会顺手关掉系统代理，浏览器和桌面端会改用真实 IP 连接。要退出，先关掉 Claude 的网页和桌面端。
- **节点固定**，不要来回切换。一个 IP 只登录一个 Claude 账号。
- **出现以下情况后，跑一次自检**：换了网络（换 Wi-Fi、出差）、更新了订阅、换了节点。更新订阅后，原来选中的节点可能失效，要回第 2 步确认。
- **手机**：不建议用手机登录 Claude。必须用的话，先拔掉 SIM 卡或打开飞行模式，再连 Wi-Fi 并开启代理。

## 第 10 步：安装和使用 Claude Code（需要的话）

- **什么时候装**：第 8 步自检通过之后。
- **怎么装**：按 Anthropic 官方文档安装。在 Windows 上，一般要先装 Git for Windows。
- **用哪个终端**：只在第 4 步之后**新开的**终端里使用，它才会读到 `HTTPS_PROXY`。
- **另一种代理设置方式**：也可以在 `~/.claude/settings.json` 的 `env` 里写 `HTTPS_PROXY`，自检同样能识别。
- **之后**：可以把这个 skill 装进 Claude Code（复制到 `~/.claude/skills/`），以后让它帮你体检。

---

## 常见问题

- **订阅导入失败**：
  - 先检查链接是否复制完整；
  - 有的订阅地址在国内打不开，换个时间重试，或者找卖家要备用链接；
  - 实在不行，让卖家直接发配置文件，在「订阅」页用「新建」导入。
- **节点测速超时**：
  1. 确认电脑的系统时间准确。时间偏差大，加密连接会失败。
  2. 关掉其他代理软件和加速器。
  3. 仍然不通，联系卖家。
- **打开 DNS 覆写后网页打不开**：按第 3 步的方法回滚，再把 Clash 的版本号和设置页截图发给帮你配置的人。

## 附录 A：用 v2rayN 的

1. 右键 v2rayN.exe，选「以管理员身份运行」。

   ![管理员运行](assets/v2rayn-1-run-as-admin.png)

2. 在节点列表空白处点一下，按 `Ctrl+V` 粘贴节点链接，再右键这个节点 →「设为活动」。

   ![粘贴节点](assets/v2rayn-2-paste-node.png)

3. 底部的三个设置：
   - 「启用 Tun」：**关**；
   - 「系统代理」：选「自动配置系统代理」；
   - 「路由」：单节点选「绕过大陆」，需要全部走代理就选「全局」。

   左下角的 `mixed:10808` 就是端口号，第 4 步把 7897 换成 10808。

   ![系统代理设置](assets/v2rayn-3-system-proxy.png)

4. **设成开机自启**：在「设置 → 参数设置」里勾选「开机自动启动」（不同版本位置略有不同）。和 Clash 一样，代理软件必须开机自启。
5. v2rayN 没有第 3 步里的 DNS 覆写，DNS 设置保持默认即可。第 4 步到第 10 步照常做。

## 附录 B：macOS

- **Clash Verge Rev**：下载 macOS 版，Apple 芯片选 aarch64，Intel 芯片选 x64。第 1 到 3 步的界面和 Windows 一样，同样要打开「开机自启」。如果没生效，在 系统设置 → 通用 → 登录项 里把它加进去。
- **第 4 步（代理变量）**：

  ```bash
  bash scripts/setup/macos-setup.sh --proxy-port 7897
  ```

  这会把三行代理变量写进 `~/.zshrc`，新开的终端才会生效。
- **第 5 步（关 IPv6）**：

  ```bash
  bash scripts/setup/macos-setup.sh --network
  ```

  需要输入开机密码。可以先加 `--dry-run` 看看会做什么；不想固定 DNS 就加 `--keep-dns`，和 Windows 的 `-KeepDns` 一样。
- **第 7 步（时区）**：系统设置 → 通用 → 日期与时间，关掉自动设置；或者运行：

  ```bash
  bash scripts/setup/macos-setup.sh --timezone America/Los_Angeles
  ```

- **浏览器**：Chrome 的设置和 Windows 一样；Safari 默认不泄露 WebRTC。
- **注意**：macOS 脚本改编自常见的 launchd 网络脚本，作者只在 Windows 上完整验证过这套流程，执行前请先加 `--dry-run` 看清楚。

## 附录 C：电脑上装了虚拟机（VMware / VirtualBox / Hyper-V）

系统代理这条路线基本不受虚拟网卡影响。如果 Clash 连不上，按顺序排查：

1. 确认没开「虚拟网卡模式」。
2. 在设备管理器里临时禁用虚拟机的网卡，看问题是否消失。
3. 电脑开着热点时，不要同时开 TUN（本路线本来就不开）。

## 附录 D：想开 TUN 怎么办

只有一种情况值得开：搞不清哪些软件走没走代理，又必须让所有软件都走代理。做法和副作用见 `references/routing.md` 的"档位 B"。
