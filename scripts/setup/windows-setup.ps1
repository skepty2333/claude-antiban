<#
.SYNOPSIS
  Claude 防封：Windows 端设置（代理环境变量、系统时区、关 IPv6 计划任务）。

.DESCRIPTION
  不带参数运行：只显示当前状态，不改任何东西。
  每项改动都可以先加 -WhatIf 预演。

.EXAMPLE
  .\windows-setup.ps1                                   # 只看当前状态
.EXAMPLE
  .\windows-setup.ps1 -ProxyPort 7897                   # 持久代理变量（Claude Code 用），不需要管理员
.EXAMPLE
  .\windows-setup.ps1 -TimeZone "Pacific Standard Time" # 系统时区对齐出口；以管理员运行时同时关掉"自动设置时区"
.EXAMPLE
  .\windows-setup.ps1 -NetworkTask                      # 管理员：每次开机、联网都关掉 IPv6，并把网卡 DNS 固定为 1.1.1.1/8.8.8.8
.EXAMPLE
  .\windows-setup.ps1 -NetworkTask -KeepDns             # 管理员：只关 IPv6，网卡 DNS 不动
.EXAMPLE
  .\windows-setup.ps1 -Undo                             # 管理员：删掉本脚本加的变量和计划任务，恢复 IPv6 与自动 DNS
.EXAMPLE
  # AI 代为提权运行：弹出管理员确认，用户点「是」；输出写进日志，供 AI 读取
  Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"C:\path\windows-setup.ps1"','-NetworkTask','-TimeZone','"Pacific Standard Time"','-LogPath','"C:\path\setup.log"'
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 65535)][int]$ProxyPort,
    [string]$TimeZone,
    [switch]$NetworkTask,
    [switch]$KeepDns,
    [switch]$Undo,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ClaudeAntiban-NetworkSetup'
$TaskDir = Join-Path $env:ProgramData 'ClaudeAntiban'
$TaskScript = Join-Path $TaskDir 'network-setup.ps1'
$ProxyVars = 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'

function Test-Admin {
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Admin([string]$What) {
    if ($WhatIfPreference) { return }  # 预演不改任何东西，不需要管理员
    if (-not (Test-Admin)) { throw "$What 需要管理员权限：右键 PowerShell →「以管理员身份运行」后再执行。" }
}

function Show-State {
    Write-Host "`n== 当前状态 ==" -ForegroundColor Cyan
    foreach ($name in $ProxyVars) {
        $value = [Environment]::GetEnvironmentVariable($name, 'User')
        Write-Host ("用户变量 {0,-11} {1}" -f $name, $(if ($value) { $value } else { '(未设置)' }))
    }
    $tz = Get-TimeZone
    Write-Host "系统时区       $($tz.Id)（$($tz.DisplayName)）"
    $auto = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\tzautoupdate' -ErrorAction SilentlyContinue).Start
    Write-Host "自动设置时区   $(if ($auto -eq 4) { '已关闭' } elseif ($null -eq $auto) { '未知' } else { '开启（会按定位改回北京时间）' })"
    Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up' | ForEach-Object {
        $v6 = (Get-NetAdapterBinding -Name $_.Name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue).Enabled
        $dns = (Get-DnsClientServerAddress -InterfaceAlias $_.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses -join ', '
        Write-Host ("网卡 {0,-12} IPv6 {1,-5} DNS {2}" -f $_.Name, $(if ($v6) { '开' } else { '关' }), $(if ($dns) { $dns } else { '自动' }))
    }
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "计划任务       $(if ($task) { "$TaskName（$($task.State)）" } else { '未安装' })"
}

function Set-ProxyEnv([int]$Port) {
    $proxy = "http://127.0.0.1:$Port"
    $values = @{ HTTPS_PROXY = $proxy; HTTP_PROXY = $proxy; NO_PROXY = 'localhost,127.0.0.1,::1' }
    foreach ($name in $ProxyVars) {
        if ($PSCmdlet.ShouldProcess("用户环境变量 $name", "设为 $($values[$name])")) {
            [Environment]::SetEnvironmentVariable($name, $values[$name], 'User')
        }
    }
    Write-Host '已设置。已经开着的终端和程序读不到新变量，要关掉重开。' -ForegroundColor Green
}

function Set-SystemTimeZone([string]$Id) {
    $target = Get-TimeZone -ListAvailable | Where-Object Id -eq $Id
    if (-not $target) { throw "没有叫 '$Id' 的时区。用 Get-TimeZone -ListAvailable 查看可用名称，例如 'Pacific Standard Time'。" }
    if ($PSCmdlet.ShouldProcess('系统时区', "改为 $Id")) {
        Set-TimeZone -Id $Id
        Write-Host "时区已改为 $Id。" -ForegroundColor Green
    }
    Disable-AutoTimeZone
}

function Disable-AutoTimeZone {
    # 「自动设置时区」就是 tzautoupdate 服务：Start=3 开，Start=4 关
    $key = 'HKLM:\SYSTEM\CurrentControlSet\Services\tzautoupdate'
    if (-not (Test-Path $key) -or (Get-ItemProperty $key).Start -eq 4) { return }
    if (-not (Test-Admin) -and -not $WhatIfPreference) {
        Write-Host '「自动设置时区」还开着，系统可能按定位把时区改回去：以管理员身份再运行一次带 -TimeZone 的命令即可关掉。' -ForegroundColor Yellow
        return
    }
    if ($PSCmdlet.ShouldProcess('自动设置时区', '关闭（tzautoupdate 服务设为禁用）')) {
        Stop-Service -Name tzautoupdate -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $key -Name Start -Value 4
        Write-Host '已关闭「自动设置时区」。' -ForegroundColor Green
    }
}

function Get-TaskScriptBody([bool]$SetDns) {
    $dnsLine = if ($SetDns) {
        'Get-NetAdapter | Where-Object Status -eq "Up" | ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name -ServerAddresses ("1.1.1.1", "8.8.8.8") }'
    } else { '# 网卡 DNS 保持不变（-KeepDns）' }
    return @"
# 由 claude-antiban windows-setup.ps1 生成：每次开机和联网时关闭所有网卡的 IPv6$(if ($SetDns) { '，并把网卡 DNS 设为 1.1.1.1/8.8.8.8' })
Disable-NetAdapterBinding -Name "*" -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue
$dnsLine
"@
}

function Install-NetworkTask([bool]$SetDns) {
    Assert-Admin '安装计划任务'
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>claude-antiban: disable IPv6 (and pin DNS) on boot and on every network change</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled></BootTrigger>
    <EventTrigger><Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational"&gt;&lt;Select Path="Microsoft-Windows-NetworkProfile/Operational"&gt;*[System[EventID=10000]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "$TaskScript"</Arguments>
    </Exec>
  </Actions>
</Task>
"@
    if ($PSCmdlet.ShouldProcess($TaskScript, '写入联网时执行的脚本')) {
        New-Item -ItemType Directory -Force -Path $TaskDir | Out-Null
        Set-Content -LiteralPath $TaskScript -Value (Get-TaskScriptBody $SetDns) -Encoding UTF8
    }
    if ($PSCmdlet.ShouldProcess($TaskName, '注册计划任务（开机 + 每次联网触发，SYSTEM 身份）')) {
        Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
        & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $TaskScript
        Write-Host '计划任务已安装并立即执行了一次。' -ForegroundColor Green
    }
}

function Invoke-Undo {
    Assert-Admin '撤销'
    foreach ($name in $ProxyVars) {
        if ($PSCmdlet.ShouldProcess("用户环境变量 $name", '删除')) {
            [Environment]::SetEnvironmentVariable($name, $null, 'User')
        }
    }
    if ((Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) -and $PSCmdlet.ShouldProcess($TaskName, '删除计划任务')) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Remove-Item -LiteralPath $TaskDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
        if ($PSCmdlet.ShouldProcess("网卡 $($_.Name)", '恢复 IPv6 并把 DNS 改回自动')) {
            Enable-NetAdapterBinding -Name $_.Name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue
            Set-DnsClientServerAddress -InterfaceAlias $_.Name -ResetServerAddresses
        }
    }
    Write-Host '已撤销。时区不会自动改回，需要的话用 -TimeZone 指定。' -ForegroundColor Green
}

if ($LogPath) { Start-Transcript -LiteralPath $LogPath -Force -WhatIf:$false | Out-Null }  # 预演时也要写日志
try {
    Show-State
    if ($Undo) { Invoke-Undo }
    if ($ProxyPort) { Set-ProxyEnv $ProxyPort }
    if ($TimeZone) { Set-SystemTimeZone $TimeZone }
    if ($NetworkTask) { Install-NetworkTask (-not $KeepDns) }
    if ($Undo -or $ProxyPort -or $TimeZone -or $NetworkTask) { Show-State }
} catch {
    Write-Host "出错：$($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    if ($LogPath) { Stop-Transcript | Out-Null }
}
