# DNS：三层解析，各管各的

| 层 | 谁在用 | 走向 |
|---|---|---|
| 浏览器 / 走 HTTP 代理的程序 | Claude 三个入口 | 域名交给代理，由节点那边解析，本地不发 DNS |
| 浏览器自带的安全 DNS（DoH） | 开了它的浏览器，在直连或 TUN 下 | 浏览器绕过系统和 Clash，自己去问 DoH 服务器 |
| 系统解析（网卡 DNS） | 不走代理的程序 | 网卡上设的是谁就发给谁 |
| 代理软件自己的 DNS | Clash 的规则匹配、直连流量、fake-ip | 由 DNS 覆写配置决定 |

所以 Claude 入口的 DNS 天然跟着出口走。自检"DNS：浏览器这条路"应只出现出口所在国的解析服务器；出现 CN/HK，说明浏览器没走代理，或浏览器绕过代理自己做了 DoH。

## 系统解析：三种处理方式

把网卡 DNS 设成 `1.1.1.1`/`8.8.8.8` 只是换了解析服务器：查询仍是明文出境，墙能看到也能改（实测 `www.google.com` 的 AAAA 记录被污染成 `2001::1`），解析服务器还会落在香港等地，暴露你在亚洲。可选做法：

1. **TUN 档**：开 DNS 劫持 `any:53` 加严格路由。网卡 DNS 设成什么都会被 Clash 接管；严格路由还会堵住 Windows 多网卡同时发 DNS 查询的泄漏。
2. **系统代理档，让系统 DNS 也进 Clash**（下面每一步都要先确认再做）：
   1. 在 Clash 界面开"DNS 覆写"（模板见下），并把 `enhanced-mode` 改成 `redir-host`。原因见下一节"国内软件断网"。不要手改生成出来的 `clash-verge.yaml`。
   2. 确认 TCP 和 UDP 53 端口都被 `verge-mihomo` 占用：`Get-NetUDPEndpoint -LocalPort 53`。
   3. `Resolve-DnsName example.com -Server 127.0.0.1 -DnsOnly` 能成功。
   4. 再把网卡 DNS 设为 `127.0.0.1`：`Set-DnsClientServerAddress -InterfaceAlias "WLAN" -ServerAddresses 127.0.0.1`。
   5. **不要**再加公共 DNS 作备用：Windows 会同时查多个服务器。

   代价：Clash 一退出就没有 DNS，退出前先改回自动（见回滚）。
3. **接受现状**：Claude 三个入口都走代理时，系统 DNS 只影响其他程序。自检里这一项会是 [!]，可以记录在案、不改。

## 国内软件断网（迅雷、网易云等）：根因与预防

**症状**：系统 DNS 改成 `127.0.0.1`（交给 Clash）之后，迅雷、网易云音乐、百度网盘、夸克、B 站客户端这类软件打开就没网，浏览器却正常。

**根因（两层）**：

1. **假 IP 走不通。** `enhanced-mode: fake-ip` 时，Clash 对域名一律先回一个 `198.18.x.x` 的假 IP。走代理的程序（浏览器）把流量交给 Clash，Clash 认得这个假 IP，所以没事。不认代理的程序（上面那些国内软件）拿着假 IP 自己直连，而**没开 TUN 时**这个地址在网上不存在，于是连不上。逐个往 `fake-ip-filter` 里加域名，就是在给这些软件发真 IP，能治但永远加不完。
2. **Clash 自己的 DNS 解析不了。** 加进过滤名单的域名需要 Clash 去查真实 IP。如果 `nameserver` 写的是 `...#GLOBAL`，而 GLOBAL 组停在 `DIRECT`（换订阅后常见：原来选中的节点没了，就退回第一个 DIRECT），DoH 查询会直连 1.1.1.1、8.8.8.8 并被墙，结果是解析失败，照样没网。

**一开始就防住**：

- **系统代理档**：最省事的是系统 DNS 不指向 Clash。一定要指向的话，用 `enhanced-mode: redir-host`。这一档浏览器和 Claude 把域名直接交给代理，根本用不到假 IP，改成 redir-host 没有损失。
- **TUN 档**：可以继续用 fake-ip，因为 TUN 会把 `198.18.0.0/16` 接走。但要把国内域名排除在假 IP 之外，并让它们直连（规则见 `routing.md`）。
- **两档都要做**：`nameserver` 不要用 `#GLOBAL`，改用 `#RULES`（跟随当前模式和规则；或者写你自己的 select 组名）；国内域名用 `nameserver-policy` 交给国内 DoH。这样就算代理断了，国内域名也照样能解析。
- **改完先验证**：自检里的"国内软件会不会断网（DNS）"一项会直接问 Clash 的 DNS，看国内域名拿到的是假 IP、真 IP 还是解析失败。**把系统 DNS 指向 Clash 之前先跑一遍**，这一项是 [OK] 再改。

## Clash DNS 覆写模板

`scripts/setup/clash_verge.py apply` 写入的就是这份模板（不带 `listen` 那一行，所以不占用 53 端口）。已有的配置包含 `#RULES`、`nameserver-policy` 和 `geosite:cn` 时，脚本会保留原样。写入后要在 Clash 里把「DNS 覆写」关掉再打开，Clash 才会加载。

```yaml
dns:
  enable: true
  listen: ':53'
  ipv6: false
  enhanced-mode: fake-ip                # 系统代理档且系统 DNS 指向 Clash 时改成 redir-host
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:                       # 这些域名返回真实 IP
    - 'geosite:cn'                      # 所有国内域名，免得逐个加迅雷、网易云……
    - 'geosite:private'
    - '+.lan'
    - '+.local'
    - '+.msftncsi.com'                  # Windows 联网检测，不然任务栏会显示"无 Internet"
    - '+.msftconnecttest.com'
  default-nameserver:
    - 'tls://223.5.5.5'
  nameserver:
    - 'https://1.1.1.1/dns-query#RULES'   # 跟随当前模式和规则走代理；不要用 #GLOBAL
    - 'https://8.8.8.8/dns-query#RULES'
  nameserver-policy:                    # 国内域名交给国内 DoH，直连，不依赖代理
    'geosite:cn':
      - 'https://dns.alidns.com/dns-query'
      - 'https://doh.pub/dns-query'
  proxy-server-nameserver:              # 只用来解析节点自己的域名，避免死循环
    - 'https://doh.pub/dns-query'
    - 'https://dns.alidns.com/dns-query'
```

`geosite:` 依赖 Clash 目录里的 `geosite.dat`；Clash Verge 自带这个文件。

- 带 `#` 的地址必须加引号，否则 YAML 会把 `#` 后面当注释。
- `#GLOBAL` 的坑：它跟随 GLOBAL 组当前选中的节点。规则模式下 GLOBAL 常常停在 `DIRECT`；换了订阅、原来的节点消失后，也会退回 `DIRECT`。结果 DoH 是直连出去的，在国内会被墙。用 `#RULES` 就不依赖 GLOBAL：全局模式下它走选中的节点，规则模式下按规则走。
- 返回 `198.18.x.x` 只说明查询进了 Clash（fake-ip），不能证明上游没有泄漏，要以自检结果为准。

## 和自动改 DNS 的脚本冲突

有的教程会注册一个计划任务（例如 `NetworkSetup`），每次联网时把网卡 DNS 改回 `1.1.1.1`/`8.8.8.8`。本 skill 的 `windows-setup.ps1 -NetworkTask` 默认也会这样做。选方式 2 时，有两种处理：要么加 `-KeepDns` 重新安装任务，要么先删掉任务脚本里设置 DNS 的那一行。否则一换 Wi-Fi，DNS 就被改回去。查这些任务需要管理员权限：`Get-ScheduledTask -TaskName NetworkSetup`、`Get-ScheduledTask -TaskName ClaudeAntiban-NetworkSetup`。

## 回滚

```powershell
Set-DnsClientServerAddress -InterfaceAlias "WLAN" -ResetServerAddresses
ipconfig /flushdns
```

然后只关掉这次打开的 DNS 覆写或 TUN。不要动订阅、节点、代理组。
