#Requires -Version 5.1
<#
.SYNOPSIS
    打印管理口令（管理员面板、模型登记页要填的那一串）。
.DESCRIPTION
    对应 macOS / Linux 的 scripts/show-admin-token.sh。
#>

$ErrorActionPreference = 'Stop'

$EnvFile = Join-Path (Split-Path -Parent $PSScriptRoot) '.env.runtime'

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Error "没有找到 ${EnvFile}：先跑一次启动脚本，它会自动生成口令。"
    exit 1
}

$line = Select-String -LiteralPath $EnvFile -Pattern '^AGENT_ADMIN_TOKEN=' -Encoding UTF8 | Select-Object -Last 1
$token = if ($line) { $line.Line.Substring('AGENT_ADMIN_TOKEN='.Length).Trim('"') } else { '' }

if (-not $token) {
    Write-Error "${EnvFile} 里没有 AGENT_ADMIN_TOKEN：跑一次启动脚本会自动生成。"
    exit 1
}

Write-Output $token
