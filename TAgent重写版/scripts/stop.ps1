#Requires -Version 5.1
<#
.SYNOPSIS
    TAgent 停止脚本（Windows）。
.DESCRIPTION
    读取 .run 目录下的 PID 文件，校验进程确实是 start.bat 启动的那一个后再结束。
    不会按端口结束未知程序。

    停 basic-agent (5001)、tagentnote (5173)，以及 start.bat 拉起的
    OpenNotebook 容器（docker compose stop，数据保留）。
.PARAMETER KeepNotebook
    只停 basic-agent 与前端，OpenNotebook 容器继续跑。
#>
[CmdletBinding()]
param(
    [switch]$KeepNotebook
)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$PackRoot = Split-Path -Parent $Root
$RunDir   = Join-Path $Root '.run'

$NotebookCompose = Join-Path $PackRoot 'opennotebook\docker-compose.yml'

function Write-Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok($Message)   { Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn2($Message){ Write-Host "    $Message" -ForegroundColor Yellow }

<#
.SYNOPSIS
    调用外部命令，丢掉输出，只要退出码。
.DESCRIPTION
    PowerShell 5.1 下，对原生命令做 stderr 重定向（2>&1 / *>）会把每一行 stderr
    包成 ErrorRecord；本脚本又是 $ErrorActionPreference = 'Stop'，于是 docker、
    taskkill 只要往 stderr 写一个字（哪怕退出码是 0）整个脚本就直接中断。
    所以这里临时把 ErrorActionPreference 降成 Continue，再取 $LASTEXITCODE。
#>
function Invoke-Native([string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & $File @Arguments 2>&1
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Stop-Tracked($Name, $PidFile) {
    if (-not (Test-Path $PidFile)) {
        Write-Warn2 "$Name : 未找到 PID 文件，可能未启动"
        return
    }

    # 空文件时 Get-Content -Raw 返回 $null，直接 .Trim() 会抛异常；本脚本
    # $ErrorActionPreference='Stop'，异常会中断整个脚本，导致排在后面的服务
    # （basic-agent）根本没机会停止。先转成字符串再 Trim。
    $raw = ''
    try {
        $raw = ([string](Get-Content $PidFile -Raw -ErrorAction Stop)).Trim()
    } catch {
        Write-Warn2 "$Name : PID 文件无法读取（$($_.Exception.Message)），已清理"
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    # PID 文件格式：新版 "PID|启动时刻Ticks"，旧版只有 "PID"
    $parts = $raw.Split('|')
    $procId = 0
    if (-not [int]::TryParse($parts[0], [ref]$procId) -or $procId -le 0) {
        Write-Warn2 "$Name : PID 文件内容无效，已清理"
        Remove-Item $PidFile -Force
        return
    }
    $stamp = 0L
    $hasStamp = $parts.Count -ge 2 -and [long]::TryParse($parts[1], [ref]$stamp)

    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Warn2 "$Name : 进程 $procId 已不存在，清理 PID 文件"
        Remove-Item $PidFile -Force
        return
    }

    # 身份校验：只为防 PID 复用误杀别人的程序。
    #
    # 首选启动时刻指纹：start.ps1 记下启动那一刻，PID 被复用时时刻必然不同。
    # 这条判据不依赖可执行文件位置——venv 里的 python.exe 是符号链接，进程实际
    # 路径会解析到 uv / 系统 Python 目录，老的"必须在项目目录下"校验对正常启动
    # 的服务反而永远不成立，stop.bat 因此根本停不掉自己启动的服务。
    $identified = $false
    if ($hasStamp) {
        try { $identified = ($proc.StartTime.Ticks -eq $stamp) } catch { $identified = $false }
        if (-not $identified) {
            Write-Warn2 "$Name : PID $procId 的启动时刻与记录不符（应为本项目启动的进程已退出，PID 已被别的程序占用），已跳过并清理 PID 文件"
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            return
        }
    } else {
        # 旧格式 PID 文件（只有 PID、没有启动时刻）无法确认归属。
        # 绝不能退回到"是不是 python 进程"这种弱校验就动手——机器上 python 进程
        # 很多（uv / 系统 Python / 其它项目），PID 一旦被复用就会误杀无关程序。
        # 宁可不停，也不能停错。
        Write-Warn2 "$Name : PID 文件为旧格式（缺少启动时刻），无法确认 PID $procId 是否就是本项目启动的进程，已跳过。"
        Write-Warn2 "         请重新执行一次 start.bat（会写入新格式），或手动结束 PID $procId。"
        return
    }

    # 必须连子进程一起杀，只杀记录的那个 PID 不够：
    #   * venv 里的 python.exe 是个转发壳，真正 bind 5001 的是它 re-exec 出来的
    #     uv 目录下的解释器（子进程）；
    #   * vite 也会再派生一个 node 子进程。
    # 只 Stop-Process 记录的 PID，端口会被留下来的子进程继续占着。
    # 身份校验（启动时刻指纹）已经在上面做过，这里连树杀是安全的。
    $killed = ((Invoke-Native 'taskkill' @('/PID', "$procId", '/T', '/F')) -eq 0)

    Start-Sleep -Milliseconds 300
    if (-not $killed -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
        Write-Warn2 "$Name : 停止 PID $procId 失败，请手动结束该进程"
        return
    }
    Write-Ok "$Name : 已停止 (PID $procId)"
    Remove-Item $PidFile -Force
}

Write-Host 'TAgent 停止脚本' -ForegroundColor White

Write-Step '停止服务'
# 逐个 try：任何一个服务停止失败都不能连累另一个，否则会留下半停状态
$notebookUiPid = Join-Path $RunDir 'notebook-ui.pid'
if (Test-Path $notebookUiPid) {
    try { Stop-Tracked '笔记本页面' $notebookUiPid } catch {
        Write-Warn2 "笔记本页面 : 停止过程出错 - $($_.Exception.Message)"
    }
}
foreach ($svc in @(
    @{ Name = 'tagentnote';  File = 'frontend.pid' },
    @{ Name = 'basic-agent'; File = 'agent.pid' }
)) {
    try {
        Stop-Tracked $svc.Name (Join-Path $RunDir $svc.File)
    } catch {
        Write-Warn2 "$($svc.Name) : 停止过程出错 - $($_.Exception.Message)"
    }
}

Write-Step '停止旧的 OpenNotebook 容器（若还在）'
if ($KeepNotebook) {
    Write-Warn2 '按 -KeepNotebook 跳过，容器继续运行。'
} elseif (-not (Test-Path $NotebookCompose)) {
    Write-Warn2 '未找到 opennotebook\docker-compose.yml，跳过。'
} elseif (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warn2 '没有 docker 命令，跳过。'
} else {
    # 只 stop 不 down：down 会删掉容器，下次启动要重建。
    # 数据本来就在 bind mount 上（notebook_data / surreal_data），两种方式都不会丢。
    $code = Invoke-Native 'docker' @('compose', '-f', $NotebookCompose, 'stop')
    if ($code -eq 0) {
        Write-Ok '已停止（笔记数据保留在 opennotebook\notebook_data）'
    } else {
        Write-Warn2 "docker compose stop 退出码 $code（Docker 可能没在跑）。"
    }
}

Write-Step '检查端口占用'
foreach ($p in @(5001, 5173)) {
    $busy = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        $busy = ($null -ne $conn)
    } catch {
        $busy = ($null -ne (netstat -ano | Select-String -Pattern ":$p\s+.*LISTENING"))
    }
    if ($busy) {
        Write-Warn2 "端口 $p 仍被占用（可能是其他程序）。本脚本不会结束未确认的进程，请自行核实。"
    } else {
        Write-Ok "端口 $p 已释放"
    }
}

Write-Host "`n完成。`n" -ForegroundColor Green
