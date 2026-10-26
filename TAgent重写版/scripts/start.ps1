#Requires -Version 5.1
<#
.SYNOPSIS
    TAgent 一键启动脚本（Windows）。
.DESCRIPTION
    按顺序拉起三个服务：

        OpenNotebook 8502 页面 / 5055 接口   笔记本（Docker Compose）
        basic-agent  127.0.0.1:5001          出题 / 判卷 / 检索
        tagentnote   127.0.0.1:5173          前端（先构建，再用 Vite preview 提供生产包）

    OpenNotebook 走 ..\opennotebook\docker-compose.yml，需要 Docker Desktop
    在跑。起不来时会说明原因并继续启动其余两个服务 —— 此时答疑只用本地教材。

    脚本可重复执行；已有的 .env.runtime 里的密钥永远不会被改写。
.PARAMETER Lan
    前端监听 0.0.0.0，供局域网访问（默认仅本机 127.0.0.1）。
.PARAMETER SkipInstall
    跳过 uv sync 与 npm install（确认依赖已装好时可省几十秒）。
.PARAMETER SkipNotebook
    不启动 OpenNotebook（自己已经用别的方式起好了，或这次不需要笔记本）。
.PARAMETER WithTts
    连 aliyun-tts-bridge 一起启动（做播客用）。需要先在 opennotebook\.env
    里填 DASHSCOPE_API_KEY，且会现场 docker build。
.PARAMETER Dev
    前端改用开发服务器（改代码时用）。默认先构建生产包再用 vite preview 提供：
    开发服务器把几百个源文件逐个现编现发，页面打开慢约 10 倍，第一次遇到新依赖还会整页刷新。
.PARAMETER Prepare
    只装依赖、生成密钥，不启动任何服务。deploy\windows\install.ps1 用它做前置，
    这样"怎么装依赖"这条流程两边共用一份，不会走偏。
.PARAMETER PypiMirror
    装 Python 依赖失败时改用哪个 PyPI 镜像重试，默认阿里云。
    官方源装得动就不会用到它。
.PARAMETER AgentTimeout
    等待 basic-agent 健康的最长秒数，默认 900（首次要加载嵌入模型并建向量索引）。
.PARAMETER NotebookTimeout
    等待 OpenNotebook 接口就绪的最长秒数，默认 180。
.EXAMPLE
    .\scripts\start.ps1
.EXAMPLE
    .\scripts\start.ps1 -Lan
#>
[CmdletBinding()]
param(
    [switch]$Lan,
    [switch]$SkipInstall,
    [switch]$SkipNotebook,
    [switch]$WithTts,
    [switch]$Prepare,
    [switch]$Dev,
    [string]$PypiMirror = 'https://mirrors.aliyun.com/pypi/simple/',
    # Windows 测试机首次启动全流程约 221 秒（2026-10-11，含建检索索引），慢的电脑更久。超时会关掉后端，
    # 而向量缓存要建完才保存，设短了慢电脑会一直起不来；后端一就绪就不再等，设长不影响平时启动。
    [int]$AgentTimeout = 900,
    [int]$NotebookTimeout = 180
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 常量
# 5001 不是随便挑的：tagentnote/vite.config.ts 里的 /agent-api 代理写死了
# http://127.0.0.1:5001。改这里就必须同步改那边，否则前端所有请求 502。
$AgentPort    = 5001
$FrontendPort = 5173
# OpenNotebook 的 REST 接口。8502 是 Streamlit 页面，拿它打 /api/* 只会拿到 HTML。
$NotebookApi  = 'http://localhost:5055'

$Root     = Split-Path -Parent $PSScriptRoot
# 交接包根目录：TAgent重写版 的上一级。opennotebook / tagentnote 都挂在这一层。
$PackRoot = Split-Path -Parent $Root
$AgentDir = Join-Path $Root 'basic-agent'
$EnvFile  = Join-Path $Root '.env.runtime'
$RunDir   = Join-Path $Root '.run'
$LogDir   = Join-Path $Root 'logs\runtime'
$AgentPy  = Join-Path $AgentDir '.venv\Scripts\python.exe'

$NotebookDir     = Join-Path $PackRoot 'opennotebook'
$NotebookCompose = Join-Path $NotebookDir 'docker-compose.yml'

function Write-Step($Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok($Message)   { Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn2($Message){ Write-Host "    $Message" -ForegroundColor Yellow }

function Stop-WithError($Message) {
    Write-Host "`n[错误] $Message" -ForegroundColor Red
    exit 1
}

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

function Test-Cmd($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

<#
.SYNOPSIS
    写 PID 文件：记录 "PID|进程启动时刻"。
.DESCRIPTION
    只记 PID 无法防 PID 复用，所以 stop.ps1 原本靠"可执行文件必须在项目目录下"
    来确认归属。但 venv 里的 python.exe 是符号链接，进程实际路径会解析到
    uv / 系统 Python 目录，这条校验对正常启动的服务必然失败 —— 结果 stop.bat
    根本停不掉自己启动的服务。改用启动时刻做指纹：PID 复用时启动时刻必然不同，
    既保住了防误杀，又不再依赖可执行文件的位置。
#>
function Write-PidFile($Process, $Path) {
    "$($Process.Id)|$($Process.StartTime.Ticks)" |
        Out-File -FilePath $Path -Encoding ascii
}

# 加密安全随机字节
function New-RandomBytes([int]$Count) {
    $bytes = New-Object byte[] $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return $bytes
}

function New-HexToken([int]$ByteCount = 32) {
    return (-join ((New-RandomBytes $ByteCount) | ForEach-Object { $_.ToString('x2') }))
}

# Fernet 密钥：32 字节的 url-safe base64（44 字符）
function New-FernetKey {
    return [Convert]::ToBase64String((New-RandomBytes 32)).Replace('+', '-').Replace('/', '_')
}

# 端口是否已被监听
function Test-PortBusy($Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return ($null -ne $conn)
    } catch {
        # 老系统无 Get-NetTCPConnection 时退回 netstat
        $out = netstat -ano | Select-String -Pattern ":$Port\s+.*LISTENING"
        return ($null -ne $out)
    }
}

# 轮询健康检查
# 传了 $Process 的话，它一退出就不再等（和 start.sh 的 wait_health 一样）：
# 后端启动即崩溃时（配置写错、依赖缺失等），不用干等到超时。
function Wait-Health($Url, $TimeoutSec, $Process = $null) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) { return $true }
        } catch {
            if ($Process -and $Process.HasExited) { return $false }
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

# 必须写成无 BOM 的 UTF-8：带 BOM 会让首个变量名多出前缀，python-dotenv 读不到
function Write-Utf8NoBom($Path, $Text) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

<#
.SYNOPSIS
    就地更新 .env 风格文件里的若干个键，不动其余内容。
.DESCRIPTION
    已存在的键改值，不存在的键追加到末尾。注释、顺序、以及所有没点名的键
    （尤其是密钥）原样保留 —— 这是"永不覆盖已生成密钥"这条承诺的落点。
#>
function Update-EnvFile($Path, [hashtable]$Updates) {
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content $Path -Encoding UTF8)
    }
    $seen = @{}
    $result = @()

    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith('#') -and $trimmed.Contains('=')) {
            $key = $trimmed.Substring(0, $trimmed.IndexOf('=')).Trim()
            if ($Updates.ContainsKey($key)) {
                $result += "$key=$($Updates[$key])"
                $seen[$key] = $true
                continue
            }
        }
        $result += $line
    }

    foreach ($key in $Updates.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $result += "$key=$($Updates[$key])"
        }
    }

    Write-Utf8NoBom $Path (($result -join "`n") + "`n")
}

<#
.SYNOPSIS
    读取 .env 里的密钥；空值等同于没有。
.DESCRIPTION
    「怎么跑.txt」让人直接把 .env.runtime.example 复制成 .env.runtime，而模板里
    所有密钥都是空的。空的 AGENT_ADMIN_TOKEN 会让 /admin/model-providers 直接
    返回 503 —— 于是"登记模型"这一步根本做不了，而且报错信息完全看不出是这个
    原因。所以"键存在但值为空"必须和"键不存在"一样对待：照样生成。
#>
function Get-EnvSecret($Path, $Key) {
    $value = Read-EnvValue $Path $Key
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value
}

function Read-EnvValue($Path, $Key) {
    if (-not (Test-Path $Path)) { return $null }
    foreach ($line in (Get-Content $Path -Encoding UTF8)) {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith('#') -and $trimmed.Contains('=')) {
            $idx = $trimmed.IndexOf('=')
            if ($trimmed.Substring(0, $idx).Trim() -eq $Key) {
                return $trimmed.Substring($idx + 1).Trim()
            }
        }
    }
    return $null
}

Write-Host 'TAgent 启动脚本' -ForegroundColor White
Write-Host "项目目录: $Root"

# ---------------------------------------------------------------- 0. 环境检查
Write-Step '检查运行环境'

if (-not (Test-Cmd 'uv')) {
    Stop-WithError '未找到 uv。请先安装：python -m pip install uv'
}

# 前端默认先 vite build，再用 vite preview 提供生产包（开发服务器实测慢约 10 倍，见 start.sh 同一处）。
# /agent-api 代理两种模式都有：vite preview 的 proxy 默认沿用 vite.config.ts 里 server.proxy 那份。
if (-not (Test-Cmd 'node')) {
    Stop-WithError '未找到 Node.js。前端需要它，请安装 Node.js 22 LTS。'
}
if (-not (Test-Cmd 'npm')) {
    Stop-WithError '未找到 npm。请随 Node.js 22 LTS 一并安装。'
}
$nodeVer = (& node -v).TrimStart('v')
$nodeMajor = [int]($nodeVer.Split('.')[0])
if ($nodeMajor -lt 18) {
    Stop-WithError "Node.js 版本为 $nodeVer，本项目要求 >= 18。"
}
Write-Ok "uv / Node.js $nodeVer / npm 就绪"

# 前端与后端是两个仓库：交接包里 tagentnote 是 TAgent重写版 的同级目录。
$FrontendDir = $null
foreach ($candidate in @(
    (Join-Path (Split-Path -Parent $Root) 'tagentnote'),
    (Join-Path $Root 'tagentnote')
)) {
    if (Test-Path (Join-Path $candidate 'package.json')) {
        $FrontendDir = $candidate
        break
    }
}
if ($null -eq $FrontendDir) {
    Stop-WithError "未找到前端目录 tagentnote（找过 $Root\..\tagentnote 和 $Root\tagentnote）。请确认交接包解压完整。"
}
Write-Ok "前端目录: $FrontendDir"

if ($Prepare) {
    # -Prepare 只装依赖不起服务，端口被占（比如服务已经在跑）不该拦着它
    Write-Ok '端口检查已跳过（-Prepare 不启动服务）'
} else {
    foreach ($p in @($AgentPort, $FrontendPort)) {
        if (Test-PortBusy $p) {
            Stop-WithError "端口 $p 已被占用。请先运行 .\stop.bat，或自行确认占用程序后处理（本脚本不会结束未知进程）。"
        }
    }
    Write-Ok "端口 $AgentPort / $FrontendPort 可用"
}

New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null

# ------------------------------------------------- 1. OpenNotebook
Write-Step 'OpenNotebook'

function Test-NotebookApi {
    try {
        $resp = Invoke-WebRequest -Uri "$NotebookApi/api/notebooks" -UseBasicParsing -TimeoutSec 5
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

<#
.SYNOPSIS
    Docker 引擎是否可用。
.DESCRIPTION
    CLI 装了不代表引擎在跑 —— Docker Desktop 没启动、或 WSL2 组件没装时，
    CLI 都还在，但每条真正要连引擎的命令都会失败。

    注意别用 `docker info` 探测：Docker 29 即使连不上引擎，它照样打印客户端
    信息并**退出码 0**。要用 `docker version --format {{.Server.Version}}`，
    这条拿不到服务端就返回非 0。
#>
function Test-DockerEngine {
    if (-not (Test-Cmd 'docker')) { return $false }
    return ((Invoke-Native 'docker' @('version', '--format', '{{.Server.Version}}')) -eq 0)
}

function Write-DockerHelp {
    Write-Warn2 'Docker 引擎不可用，OpenNotebook 起不来。常见原因与排查：'
    Write-Warn2 '  1. Docker Desktop 没启动 —— 打开它，等鲸鱼图标变绿再重跑本脚本。'
    Write-Warn2 '  2. 提示"未检测到虚拟化支持"：多数情况 BIOS 是好的，缺的是 Windows 组件。'
    Write-Warn2 '     以管理员身份运行  wsl --install --no-distribution  然后重启电脑。'
    Write-Warn2 '     自查：wsl --status；若报 WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED 即是此项。'
    Write-Warn2 '  3. 确实没装 Docker Desktop：https://www.docker.com/products/docker-desktop/'
}

# -Prepare 只做准备，容器交给服务管理器（计划任务 / start.ps1）去拉
if ($Prepare) { $SkipNotebook = $true }

$notebookUp = Test-NotebookApi

if ($notebookUp) {
    Write-Ok "已在运行（$NotebookApi）"
} elseif ($SkipNotebook) {
    Write-Warn2 '按 -SkipNotebook 跳过。'
} elseif (-not (Test-Path $NotebookCompose)) {
    Write-Warn2 "未找到 $NotebookCompose，跳过。请自行启动 OpenNotebook（页面 8502 / 接口 5055）。"
} elseif (-not (Test-DockerEngine)) {
    Write-DockerHelp
} else {
    # 加密密钥：compose 里读 ${OPEN_NOTEBOOK_ENCRYPTION_KEY}，
    # 上游默认值是 change-me-to-a-secret-string，不能就这么用。
    $notebookEnv = Join-Path $NotebookDir '.env'
    if (-not (Get-EnvSecret $notebookEnv 'OPEN_NOTEBOOK_ENCRYPTION_KEY')) {
        Update-EnvFile $notebookEnv @{ 'OPEN_NOTEBOOK_ENCRYPTION_KEY' = (New-HexToken 32) }
        Write-Ok '已生成 opennotebook\.env 里的加密密钥'
    }

    # 默认不带 aliyun-tts-bridge：它要阿里云 DashScope Key（交接包里没有），
    # 而且要现场 docker build，白等一轮。需要播客再加 -WithTts。
    $composeArgs = @('compose', '-f', $NotebookCompose, 'up', '-d')
    if ($WithTts) {
        $composeArgs += @('--build')
    } else {
        $composeArgs += @('surrealdb', 'open_notebook')
    }

    Write-Warn2 '首次启动要从 Docker Hub 拉镜像（GB 级），可能要几分钟到十几分钟。'
    Write-Warn2 '拉取失败请先配镜像加速，见 opennotebook\readme.md 第三步。'
    Push-Location $NotebookDir
    try {
        & docker @composeArgs
        $composeCode = $LASTEXITCODE
    } finally { Pop-Location }

    if ($composeCode -ne 0) {
        Write-Warn2 "docker compose 退出码 $composeCode，OpenNotebook 没能起来。"
        Write-DockerHelp
    } else {
        Write-Warn2 "等待 OpenNotebook 接口就绪（最长 $NotebookTimeout 秒）..."
        $deadline = (Get-Date).AddSeconds($NotebookTimeout)
        while ((Get-Date) -lt $deadline) {
            if (Test-NotebookApi) { $notebookUp = $true; break }
            Start-Sleep -Seconds 3
        }
        if ($notebookUp) {
            Write-Ok "已就绪（页面 http://localhost:8502 / 接口 $NotebookApi）"
        } else {
            Write-Warn2 "$NotebookTimeout 秒内接口仍不可达。看日志：docker compose -f `"$NotebookCompose`" logs open_notebook"
        }
    }
}

if (-not $notebookUp) {
    Write-Warn2 '继续启动其余服务。但答疑与出题只会检索本地教材 book1.md，笔记本里的内容一条都取不到。'
}

# ------------------------------------------------- 2. basic-agent 依赖
#
# 这里有个坑，值得先说清楚：
#   uv.lock 里每个包都写死了 https://files.pythonhosted.org/... 的下载地址，
#   而 `uv sync --frozen` 会照着这些地址下，**镜像设置一概不生效**
#   （UV_DEFAULT_INDEX / UV_INDEX_URL / -i 全都被忽略，见 astral-sh/uv#19625）。
#   所以国内网络下"先设 $env:UV_DEFAULT_INDEX 再 uv sync --frozen"是没用的，
#   表现就是卡上两分钟然后 operation timed out。
#   真正管用的是去掉 --frozen 让 uv 照镜像重新解析一次 —— 版本仍由 pyproject.toml
#   里的 == 钉死，变的只是 uv.lock 里记录的下载地址。
function Invoke-UvSyncViaMirror([string]$Index) {
    # 备份只做一次：第二次失败时别把已经改写过的 lock 当原件覆盖掉
    $lock = Join-Path $AgentDir 'uv.lock'
    $bak  = Join-Path $AgentDir 'uv.lock.bak'
    if ((Test-Path $lock) -and -not (Test-Path $bak)) {
        Copy-Item $lock $bak
        Write-Warn2 '原 uv.lock 已备份为 basic-agent\uv.lock.bak（想还原就把它改回去，或 git checkout uv.lock）。'
    }

    $previous = $env:UV_DEFAULT_INDEX
    $env:UV_DEFAULT_INDEX = $Index
    Push-Location $AgentDir
    try {
        # 必须 | Out-Host：函数里原生命令的 stdout 会被塞进返回值，
        # 那样调用方拿到的就不是 $true/$false 而是"一堆日志行 + 布尔"的数组，
        # -not 判断随之失灵（非空数组恒为真），失败会被当成成功。
        & uv sync | Out-Host
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $env:UV_DEFAULT_INDEX = $previous
    }
    return ($code -eq 0)
}

if ($SkipInstall) {
    Write-Step '跳过 basic-agent 依赖检查（-SkipInstall）'
} else {
    # uv sync 是幂等的：环境已完整时几秒内返回；环境残缺时会自动补齐。
    Write-Step '准备 basic-agent 依赖'
    # uv 单次请求默认 30 秒就超时，网速一般时 torch / faiss 这种大包必挂。
    if (-not $env:UV_HTTP_TIMEOUT) { $env:UV_HTTP_TIMEOUT = '120' }

    $userIndex = $env:UV_DEFAULT_INDEX
    if (-not $userIndex) { $userIndex = $env:UV_INDEX_URL }

    if ($userIndex) {
        # 人家已经指定镜像了，就别再拿 --frozen 去撞官方源白等两分钟。
        Write-Warn2 "检测到已设置 PyPI 镜像：$userIndex"
        Write-Warn2 '直接按镜像重新解析（不用 --frozen，否则镜像会被 uv 忽略）。'
        if (-not (Invoke-UvSyncViaMirror $userIndex)) {
            Stop-WithError "basic-agent 依赖安装失败（镜像 $userIndex）。
       换一个镜像再试：.\start.bat -PypiMirror https://pypi.tuna.tsinghua.edu.cn/simple"
        }
        Write-Ok '就绪（走镜像装的）'
    } else {
        Push-Location $AgentDir
        try {
            & uv sync --frozen
            $syncCode = $LASTEXITCODE
        } finally { Pop-Location }

        if ($syncCode -eq 0) {
            Write-Ok '就绪'
        } else {
            Write-Warn2 'uv sync --frozen 失败。'
            Write-Warn2 '注意 uv 的已知行为：--frozen 只认 uv.lock 里写死的 files.pythonhosted.org'
            Write-Warn2 '地址，镜像设置全都不生效（astral-sh/uv#19625）—— 所以这里换成走镜像'
            Write-Warn2 "重新解析一次：$PypiMirror"
            Write-Warn2 '包版本不变（由 pyproject.toml 的 == 钉死），变的只是 uv.lock 里的下载地址。'
            if (-not (Invoke-UvSyncViaMirror $PypiMirror)) {
                Stop-WithError "basic-agent 依赖安装失败（官方源和镜像 $PypiMirror 都没成）。
       可以换个镜像重试：
         .\start.bat -PypiMirror https://pypi.tuna.tsinghua.edu.cn/simple
         .\start.bat -PypiMirror https://mirrors.cloud.tencent.com/pypi/simple
       或者挂上代理再跑。"
            }
            Write-Ok '就绪（走镜像装的）'
        }
    }
}
if (-not (Test-Path $AgentPy)) {
    Stop-WithError "未找到 $AgentPy。请去掉 -SkipInstall 重跑一次。"
}

# ------------------------------------------------- 3. .env.runtime
Write-Step '准备 .env.runtime'
$isNew = -not (Test-Path $EnvFile)

$updates = @{
    'BASIC_AGENT_HOST'      = '127.0.0.1'
    'BASIC_AGENT_PORT'      = "$AgentPort"
    'BASIC_AGENT_BASE_URL'  = "http://127.0.0.1:$AgentPort"
}

if (-not $isNew) {
    $oldPort = Read-EnvValue $EnvFile 'BASIC_AGENT_PORT'
    if ($oldPort -and $oldPort -ne "$AgentPort") {
        Write-Warn2 "BASIC_AGENT_PORT 原为 $oldPort，已改为 $AgentPort（前端代理写死了 $AgentPort）。密钥不受影响。"
    }
}

# 密钥：已有值的一律原样保留，缺失或为空的才生成。
$generated = @()

# 两对 token 必须成对相同：AGENT_* 由 basic-agent 校验，BASIC_AGENT_* 由调用方携带发送。
foreach ($pair in @(
    @{ A = 'AGENT_ADMIN_TOKEN';    B = 'BASIC_AGENT_ADMIN_TOKEN';    Label = '管理 token' },
    @{ A = 'AGENT_INTERNAL_TOKEN'; B = 'BASIC_AGENT_INTERNAL_TOKEN'; Label = '内部 token' }
)) {
    $value = Get-EnvSecret $EnvFile $pair.A
    if (-not $value) { $value = Get-EnvSecret $EnvFile $pair.B }
    if (-not $value) {
        $value = New-HexToken 32
        $generated += $pair.Label
    }
    $updates[$pair.A] = $value
    $updates[$pair.B] = $value
}

# .env.runtime.example 里列了这一项，就照样补齐，免得两边对不上。
# 但要说清楚：当前的 basic-agent 代码里没有任何地方读它，
# API Key 是**明文**存在 basic-agent/config/model_providers.json 的
# （加密是 open-webui 时期的事，那套已经不在本包里了）。
if (-not (Get-EnvSecret $EnvFile 'AGENT_PROVIDER_ENCRYPTION_KEY')) {
    $updates['AGENT_PROVIDER_ENCRYPTION_KEY'] = New-FernetKey
}

# 非密钥的默认值：只在整个键都不存在时补。空值对它们是合法的
# （比如 KNOWLEDGE_SOURCE= 表示按 OPEN_NOTEBOOK_URL 自动判断）。
foreach ($item in @(
    @{ K = 'OPEN_NOTEBOOK_API_URL';        V = $NotebookApi },
    @{ K = 'OPEN_NOTEBOOK_URL';            V = 'http://localhost:8502/notebooks' },
    @{ K = 'OPEN_NOTEBOOK_PASSWORD';       V = '' },
    @{ K = 'KNOWLEDGE_SOURCE';             V = '' },
    @{ K = 'AGENT_PROVIDER_ALLOWED_HOSTS'; V = '' },
    @{ K = 'AGENT_PROVIDER_ALLOWED_CIDRS'; V = '' }
)) {
    if ($null -eq (Read-EnvValue $EnvFile $item.K)) {
        $updates[$item.K] = $item.V
    }
}

Update-EnvFile $EnvFile $updates

if ($generated.Count -gt 0) {
    Write-Ok "已生成：$($generated -join '、')（内含密钥，切勿提交或外传）"
} else {
    Write-Ok '密钥齐全，原样保留'
}

# 文件里刚落进了新密钥就收紧 ACL：仅当前用户可读写
if ($generated.Count -gt 0) {
    try {
        $acl = Get-Acl $EnvFile
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            "$env:USERDOMAIN\$env:USERNAME", 'FullControl', 'Allow')
        $acl.SetAccessRule($rule)
        Set-Acl -Path $EnvFile -AclObject $acl
    } catch {
        Write-Warn2 "未能收紧 .env.runtime 权限（不影响运行）：$($_.Exception.Message)"
    }
}

# ------------------------------------------------- 4. 载入环境变量
Write-Step '载入环境变量'
# 写入时用的是无 BOM 的 UTF-8（Write-Utf8NoBom）；Windows PowerShell 5.1 的 Get-Content
# 不指定编码会按系统代码页（中文 Windows 是 GBK）读，值里有中文就会读乱。
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        Set-Item -Path "env:$key" -Value $val
    }
}
# 进程环境优先级高于 .env 文件（python-dotenv 不覆盖已存在的变量），
# 这样即便 basic-agent\.env 里写了别的端口，也一定按 $AgentPort 起。
$env:BASIC_AGENT_HOST = '127.0.0.1'
$env:BASIC_AGENT_PORT = "$AgentPort"
# 嵌入模型 shibing624/text2vec-base-chinese（约 400MB）在第一次检索时才下载。
# 裸奔直连 huggingface.co 在国内基本必然超时，表现是答疑请求一直卡住不返回，
# 日志里只有一句 unauthenticated requests 提示，完全看不出是被墙。
# basic-agent\.env.example 里本来写了 HF_ENDPOINT，但这个脚本从不生成
# basic-agent\.env（只生成 tagentnote\.env 和 opennotebook\.env），那行等于
# 从没生效过 —— 所以直接放进进程环境。
#
# 两种情况不要碰：
#   1. 用户自己设过 HF_ENDPOINT，尊重原值；
#   2. 机器挂了代理。hf-mirror 只镜像元数据，大文件仍旧跳去 HF 的 CDN；而且
#      它会把经代理出去的请求判定为墙外来源，直接 308 跳回 huggingface.co，
#      huggingface_hub 的解析链在这一跳上会断，报错是看着毫不相干的
#      "does not appear to have a file named pytorch_model.bin or
#      model.safetensors"。有代理的机器让它直连反而是对的。
if ((-not $env:HF_ENDPOINT) -and (-not $env:HTTPS_PROXY) -and (-not $env:ALL_PROXY)) {
    $env:HF_ENDPOINT = 'https://hf-mirror.com'
}
Write-Ok "basic-agent 监听 127.0.0.1:$AgentPort"

# ------------------------------------------------- 4b. 参考文献
# 《系统仿真学报》等论文：出题、答疑、批改检索时和教材一起用。仓库是公开的、版权在期刊，
# 仓库里只有篇目清单（basic-agent\references\manifest.json），全文在这一步从期刊官网下到本机。
# 必须在 basic-agent 起来之前：它启动时建索引，晚到的论文要等下次启动才用得上。
# 已经下过的直接跳过；下载失败只提示、照常启动，下次启动再补。.env.runtime 里 TAGENT_REFERENCES=0 可关掉。
# 不走 Invoke-Native：它把输出丢掉了，这里要让人看见下了几篇。
if ($env:TAGENT_REFERENCES -ne '0') {
    Write-Step '参考文献（系统仿真学报）'
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    # 这一步的输出和 PowerShell 自己的提示写进同一个地方。直接显示在窗口上时没问题（Python 走控制台接口）；
    # 被别的程序接管（重定向）时，Python 默认按系统代码页写，PowerShell 按 [Console]::OutputEncoding 写，
    # 接管的一方把窗口改成 UTF-8 的话，就只有这一段是乱码（2026-10-10 Windows 测试报告）。
    # 让 Python 跟 PowerShell 用同一个编码；写不出的字符替换掉，别因为编码让这一步失败。
    $previousIoEncoding = $env:PYTHONIOENCODING
    $env:PYTHONIOENCODING = "cp$([Console]::OutputEncoding.CodePage):replace"
    Push-Location $AgentDir
    try {
        & $AgentPy (Join-Path 'tools' 'fetch_references.py')
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 '参考文献没准备好，这次先只用教材，下次启动再补。'
        }
    } catch {
        Write-Warn2 '参考文献没准备好，这次先只用教材，下次启动再补。'
    } finally {
        Pop-Location
        $env:PYTHONIOENCODING = $previousIoEncoding
        $ErrorActionPreference = $previous
    }
}

# ------------------------------------------------- 5. 前端依赖与 .env
Write-Step '准备前端'
$frontEnv = Join-Path $FrontendDir '.env'
$frontEnvExample = Join-Path $FrontendDir '.env.example'
if ((-not (Test-Path $frontEnv)) -and (Test-Path $frontEnvExample)) {
    Copy-Item $frontEnvExample $frontEnv
    Write-Ok '已从 .env.example 生成 tagentnote\.env'
}

# 只看 node_modules 在不在是不够的：队友加了新依赖之后它照样在，
# 于是跳过安装，直到构建到一半才报缺包。比对 package-lock.json 的指纹才准。
$lockFile = Join-Path $FrontendDir 'package-lock.json'
$lockStamp = Join-Path $FrontendDir 'node_modules\.tagent-lock-stamp'
function Get-LockFingerprint {
    if (-not (Test-Path $lockFile)) { return '' }
    return (Get-FileHash -Algorithm SHA256 -Path $lockFile).Hash
}
function Test-DepsFresh {
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) { return $false }
    if (-not (Test-Path $lockStamp)) { return $false }
    return ((Get-Content $lockStamp -Raw -ErrorAction SilentlyContinue).Trim() -eq (Get-LockFingerprint))
}
function Save-LockStamp {
    try { Get-LockFingerprint | Set-Content -Path $lockStamp -NoNewline -Encoding ascii } catch { }
}

if ($SkipInstall) {
    Write-Warn2 '跳过 npm install（-SkipInstall）'
} elseif (Test-DepsFresh) {
    Write-Ok 'node_modules 与 package-lock.json 一致，跳过 npm install'
} else {
    if (Test-Path (Join-Path $FrontendDir 'node_modules')) {
        Write-Warn2 'package-lock.json 与已装依赖对不上（队友可能加了依赖），重新 npm install'
    }
    Push-Location $FrontendDir
    try {
        Write-Warn2 '首次安装前端依赖，可能要几分钟...'
        # 先走 npmmirror（国内快得多），失败了再退回官方源 —— 反过来在国外网络下也成立。
        & npm install --registry=https://registry.npmmirror.com --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 'npmmirror 装失败，退回官方源 registry.npmjs.org 再试一次...'
            & npm install --registry=https://registry.npmjs.org --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) {
                Stop-WithError 'npm install 两个源都失败了。检查网络/代理，或手动执行：cd tagentnote; npm install'
            }
            $script:npmFromOfficial = $true
        }
    } finally { Pop-Location }
    # 留下这次装的是哪份 lock，下次才能判断依赖有没有变
    Save-LockStamp
    if ($npmFromOfficial) { Write-Ok '就绪（官方源）' } else { Write-Ok '就绪' }
}

$viteBin = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
if (-not (Test-Path $viteBin)) {
    Stop-WithError "未找到 $viteBin。请去掉 -SkipInstall 重跑，或在 tagentnote 下手动执行 npm install。"
}

if ($Prepare) {
    Write-Host "`n准备完成（-Prepare：没有启动任何服务）。" -ForegroundColor Green
    Write-Host "  Python 依赖:  $AgentPy"
    Write-Host "  前端依赖:     $FrontendDir\node_modules"
    Write-Host "  运行时配置:   $EnvFile"
    Write-Host "`n接下来可以装成开机自启的服务，见 deploy\ 下对应系统的说明。`n"
    exit 0
}

# ------------------------------------------------- 6. 启动 basic-agent
Write-Step "启动 basic-agent (127.0.0.1:$AgentPort)"
$agentOut = Join-Path $LogDir 'basic-agent.out.log'
$agentErr = Join-Path $LogDir 'basic-agent.err.log'
# 后端的输出被重定向到上面两个日志文件。中文 Windows 上 Python 写重定向的文件默认用 GBK，
# 按 UTF-8 打开就是乱码（2026-10-06 Windows 测试报告），所以让后端用 UTF-8 写。
# 放在这里而不是「载入环境变量」那一步：参考文献那一步的 Python 直接输出到这个窗口，
# 不该跟着改编码。
$env:PYTHONUTF8 = '1'
$agentProc = Start-Process -FilePath $AgentPy -ArgumentList 'main.py' `
    -WorkingDirectory $AgentDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $agentOut -RedirectStandardError $agentErr
# 和下面的构建进程一样先取一次句柄，等待时用 HasExited 判断它是不是已经退出了
$null = $agentProc.Handle
Write-PidFile $agentProc (Join-Path $RunDir 'agent.pid')

# 前端构建和 basic-agent 加载互不相干：趁等后端的这几秒在后台先构建（实测省 4~5 秒）。
# 每次都重新构建：源码改过而包是旧的，比多等几秒难查得多。
$frontMode = 'preview'
$buildProc = $null
$buildOut = Join-Path $LogDir 'tagentnote.build.log'
$buildErr = Join-Path $LogDir 'tagentnote.build.err.log'
if ($Dev) {
    $frontMode = 'dev'
} else {
    $buildProc = Start-Process -FilePath 'node' -ArgumentList @($viteBin, 'build') `
        -WorkingDirectory $FrontendDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $buildOut -RedirectStandardError $buildErr
    # 必须马上取一次句柄：Start-Process -PassThru 拿到的进程对象如果没取过 Handle，
    # 进程结束后 ExitCode 读出来是空的，后面拿空值比 0 会把成功的构建判成失败、
    # 每次都退回慢得多的开发服务器（2026-10-06 Windows 测试报告）。
    $null = $buildProc.Handle
    Write-Ok '前端生产包已在后台开始构建（和 basic-agent 加载同时进行，结果见后面「构建前端」一步）'
}

Write-Warn2 "首次启动要加载嵌入模型、建检索索引，约 1–5 分钟（慢的电脑更久），最长等待 $AgentTimeout 秒；之后用缓存，几秒就好..."
if (-not (Wait-Health "http://127.0.0.1:$AgentPort/health" $AgentTimeout $agentProc)) {
    # 还在跑的后台构建一起停掉：它不在 PID 文件里，stop 停不了，紧接着重新启动的话两次构建会同时写一个输出目录
    if ($buildProc -and -not $buildProc.HasExited) {
        $null = Invoke-Native 'taskkill' @('/PID', "$($buildProc.Id)", '/T', '/F')
    }
    if ($agentProc.HasExited) {
        Write-Host "`n[错误] basic-agent 启动后随即退出。日志：$agentErr" -ForegroundColor Red
    } else {
        $null = Invoke-Native 'taskkill' @('/PID', "$($agentProc.Id)", '/T', '/F')
        Write-Host "`n[错误] basic-agent 在 $AgentTimeout 秒内未就绪。日志：$agentErr" -ForegroundColor Red
        Write-Host "电脑较慢的话可以在命令行里加大超时：.\start.bat -AgentTimeout 1800" -ForegroundColor Yellow
    }
    if (Test-Path $agentErr) {
        Write-Host "--- 日志最后 20 行 ---"
        Get-Content -Encoding UTF8 -Tail 20 $agentErr | Write-Host
        Write-Host "---"
    }
    Remove-Item (Join-Path $RunDir 'agent.pid') -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Ok "已就绪 (PID $($agentProc.Id))"

# 「怎么跑.txt」让人手动开 /knowledge 看这一项，这里直接替他看了。
Write-Step '检查知识来源'
# 这个接口已经不阻塞（探活挪到后台），刚启动时头一两次读到的 notebook_reachable 还是 null（还没探完）：
# 以前把 null 也当成「连不上」报。现在是 null 就隔 1 秒再读，最多 10 秒。
# 只用本地教材时这一项本来就一直是 null，不用等。
try {
    for ($i = 0; $i -lt 10; $i++) {
        $knowledge = Invoke-RestMethod -Uri "http://127.0.0.1:$AgentPort/knowledge" -TimeoutSec 10
        if ($knowledge.source -eq 'local' -or $null -ne $knowledge.notebook_reachable) { break }
        Start-Sleep -Seconds 1
    }
    Write-Ok "source = $($knowledge.source)"
    # 本地知识库（教材 + 参考文献）：只用本地时在顶层，composite 时在 sources 里
    $localKb = @($knowledge.knowledge_base) + @($knowledge.knowledge_base.sources) |
        Where-Object { $_ -and $_.kind -eq 'local' } | Select-Object -First 1
    if ($localKb -and $null -ne $localKb.references) {
        Write-Ok "本地知识库：教材 book1.md + 参考文献 $($localKb.references) 篇"
    }
    if ($knowledge.source -eq 'local') {
        Write-Warn2 '当前只用本地教材 book1.md。想接笔记本，请确认 OpenNotebook 已启动且 OPEN_NOTEBOOK_API_URL 指向 5055。'
    } elseif ($knowledge.notebook_reachable -eq $true) {
        Write-Ok "notebook_reachable = true（$($knowledge.notebook_url)）"
    } elseif ($null -eq $knowledge.notebook_reachable) {
        Write-Warn2 "笔记本服务还在探测，暂时没有结论。稍后打开 http://localhost:$AgentPort/knowledge 看 notebook_reachable。"
    } else {
        Write-Warn2 "notebook_reachable = $($knowledge.notebook_reachable)，笔记本连不上（$($knowledge.notebook_url)）。"
        Write-Warn2 '答疑仍能作答，但内容只来自本地教材。8502 是页面端口，接口在 5055。'
    }
} catch {
    Write-Warn2 "读 /knowledge 失败：$($_.Exception.Message)"
    Write-Warn2 "服务本身已经起来了，可稍后手动打开 http://localhost:$AgentPort/knowledge 再看一次。"
}

# ------------------------------------------------- 7. 启动前端
if ($Lan) { $viteHost = '0.0.0.0' } else { $viteHost = '127.0.0.1' }
$frontOut = Join-Path $LogDir 'tagentnote.out.log'
$frontErr = Join-Path $LogDir 'tagentnote.err.log'

# 构建是在启动 basic-agent 时就放到后台开始的，这里等它收尾。
# 构建失败不致命：退回开发服务器，慢一些但能用，并把原因留在日志里。
if ($buildProc) {
    Write-Step '构建前端（生产包）'
    $buildProc.WaitForExit()
    if ($buildProc.ExitCode -eq 0) {
        Write-Ok '构建完成'
    } else {
        Write-Warn2 "构建失败，改用开发服务器启动（页面打开会慢一些）。构建日志：$buildOut / $buildErr"
        $frontMode = 'dev'
    }
}

Write-Step "启动 tagentnote (${viteHost}:${FrontendPort}，${frontMode})"
# 直接用 node 跑 vite，不经 npm.cmd：npm 会再派生一个 node 子进程，
# PID 文件记到的是 npm 那一层，stop 时杀不掉真正监听端口的进程。
$viteArgs = @($viteBin, $frontMode, '--port', "$FrontendPort", '--strictPort', '--host', $viteHost)
$frontProc = Start-Process -FilePath 'node' -ArgumentList $viteArgs `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $frontOut -RedirectStandardError $frontErr
Write-PidFile $frontProc (Join-Path $RunDir 'frontend.pid')

if (-not (Wait-Health "http://127.0.0.1:$FrontendPort/" 120)) {
    Write-Host "`n[错误] 前端在 120 秒内未就绪。日志：$frontErr" -ForegroundColor Red
    # 一并停掉已起来的 basic-agent，别留下半停状态占着端口
    foreach ($item in @(@{ P = $frontProc; F = 'frontend.pid' }, @{ P = $agentProc; F = 'agent.pid' })) {
        $null = Invoke-Native 'taskkill' @('/PID', "$($item.P.Id)", '/T', '/F')
        Remove-Item (Join-Path $RunDir $item.F) -Force -ErrorAction SilentlyContinue
    }
    exit 1
}
Write-Ok "已就绪 (PID $($frontProc.Id))"

# ------------------------------------------------- 完成
Write-Host "`n启动完成。" -ForegroundColor Green
Write-Host "  浏览器访问:   http://localhost:$FrontendPort"
if ($notebookUp) { Write-Host "  笔记本页面:   http://localhost:8502" }
if ($Lan) { Write-Host "  局域网访问:   http://<本机IP>:$FrontendPort（请确认防火墙已放行 $FrontendPort）" }
Write-Host "  知识来源自检: http://localhost:$AgentPort/knowledge"
Write-Host "  运行日志:     logs\runtime\"
Write-Host "  停止服务:     stop.bat`n"
# 登记提示只在**确实没登记**时给。已经登记过还照念一串 curl，既吓人又没必要，
# 而且早就有网页版登记页了。
$registered = $false
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:$AgentPort/v1/models" -TimeoutSec 10
    $registered = ($models.data -and $models.data.Count -gt 0)
} catch { }
if ($registered) {
    Write-Ok '已登记模型，可以直接用'
} else {
    Write-Host '还没登记模型。请用自己的 DeepSeek Key 登记一个（不要用别人的 Key），' -ForegroundColor Yellow
    Write-Host '否则前端顶栏会是"选择模型"，答疑和出题都会失败。' -ForegroundColor Yellow
    Write-Host "  登记页面:     http://localhost:$FrontendPort/models"
    Write-Host '（页面要填管理口令，它在 TAgent重写版\.env.runtime 里的 AGENT_ADMIN_TOKEN。）'
}
