# 浏览器与设备：时区、语言、WebRTC、指纹

浏览器指纹评分用的是 [fuck-claude](https://fuck-claude.vercel.app/zh/) 的规则（源码 `LinXiaoTao/FuckClaude`，MIT），自检里内置了同一份代码，分数与网站一致。总分 0–30 低风险，31–60 中风险，61–100 高风险。

| 信号 | 权重 | 怎么处理 |
|---|---|---|
| 系统时区 | 24 | **最重要**，见下文 |
| 浏览器语言 | 18 | 浏览器设置 → 语言：把出口国语言（如 English (United States)）移到第一位，删除中文或移到后面 |
| 中文字体 | 14 | 见下文"中文字体" |
| 国产厂商字体 | 10 | 卸载 WPS 自带的方正 FZ* 字体、MiSans、鸿蒙黑体、阿里巴巴普惠体等（控制面板 → 字体） |
| WebRTC 泄露 | 10 | 见下文 |
| 国产浏览器 / WebView | 8 | 不要用 360、QQ、夸克、微信内置浏览器登 Claude |
| 国产品牌设备 | 6 | 不要在手机上下载 Claude App，也不要用手机登录 |
| Intl 区域设置 | 4 | 跟随浏览器或系统语言；改了语言就会好 |
| 时区偏移 | 3 | 跟随系统时区 |
| Emoji 风格 | 3 | 由操作系统决定，忽略 |

## 系统时区

- 据公开逆向分析，Claude Code 会读**操作系统时区**，命中中国时区（`Asia/Shanghai`、`Asia/Urumqi` 等）会被写进它的提示词。浏览器 `Intl` 读到的也是同一个系统时区。台湾时区不扣分，香港、澳门扣部分分。
- 目标时区以自检给出的"IP 所在地多数库判为 X"为准，不要只看一个 IP 库，也不要凭节点名字猜。几个库给的城市可能不同，看多数。
- 先关掉"自动设置时区"，否则系统会按定位改回北京时间：设置 → 时间和语言 → 日期和时间。
- 修改命令：
  - Windows：`tzutil /s "Pacific Standard Time"`（美西）、`"Mountain Standard Time"`、`"Central Standard Time"`、`"Eastern Standard Time"`（美东）、`"Tokyo Standard Time"`、`"Singapore Standard Time"`、`"Taipei Standard Time"`。完整列表用 `tzutil /l`。
  - macOS：`sudo systemsetup -settimezone America/Los_Angeles`。
- 换节点后要重新对齐。

## WebRTC

- Chrome：安装 Google 官方扩展 WebRTC Network Limiter，在扩展选项里选最后一项 **Use my proxy server (if present)**。
- Edge：可以装上面这个扩展（Edge 能装 Chrome 应用商店的扩展），或 WebRTC Leak Prevent。
- Firefox：`about:config` 里把 `media.peerconnection.ice.default_address_only` 设为 `true`；完全不用 WebRTC 时，把 `media.peerconnection.enabled` 设为 `false`。
- Safari：默认不泄露。
- 判定看自检的 WebRTC 项：只出现 `.local`（mDNS）或代理出口 IP 才算通过。

## 安全 DNS（DoH）：统一关掉

浏览器的"安全 DNS"会绕过系统和 Clash，自己去问 DoH 服务器：

- 走系统代理时，被代理的网页由节点解析，它其实用不上；
- 开 TUN 时，它会绕开 Clash 的 DNS 劫持，fake-ip 和按域名的分流规则随之失效；
- 有的设置还会指向国内 DoH。

统一关掉最稳，自检里的"浏览器安全 DNS"一项会直接读取各浏览器的设置。

- Chrome：地址栏打开 `chrome://settings/security`，关闭"使用安全 DNS"。
- Edge：打开 `edge://settings/privacy`，在"安全性"里关闭"使用安全 DNS 指定如何查找网站的网络地址"。
- Firefox：设置 → 隐私与安全 → 基于 HTTPS 的 DNS，选"关闭"。
- 设置显示"由组织管理"的，是组策略锁定的，要去组策略或注册表改。

## 中文字体（中文版 Windows 稳定 +14）

中文版 Windows 自带微软雅黑、宋体，macOS 自带苹方，都是系统字体，**不能删**，删了系统界面会出问题。这一项只是网页指纹，Claude Code 不读它。可选做法：

1. 接受：把其他信号都清干净，总分仍在低风险区间。大多数人选这个。
2. 另开一套干净的环境专门登 Claude，比如英文系统的虚拟机，或专门的指纹浏览器。成本高。
3. Linux：可以用 fontconfig 的 `rejectfont` 屏蔽中文字体，参考 FuckClaude 的设备配置指南。

## 清理与习惯

- 换 IP 后先清空这个浏览器的 Cookie 和缓存，或者新建一个浏览器配置文件专门登 Claude。
- 不要用无头浏览器或自动化工具登录 claude.ai：它们会带上 `navigator.webdriver` 等自动化特征。
