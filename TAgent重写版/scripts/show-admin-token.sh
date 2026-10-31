#!/usr/bin/env bash
# 打印管理口令（管理员面板、模型登记页要填的那一串）。对应 Windows 的 scripts/show-admin-token.ps1。
#
# 部署在服务器上时在自己电脑上跑一条就行：
#   ssh 账号@服务器 'bash 部署目录/TAgent重写版/scripts/show-admin-token.sh'

set -uo pipefail

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env.runtime"

if [[ ! -f "$ENV_FILE" ]]; then
    printf '没有找到 %s：先跑一次启动脚本，它会自动生成口令。\n' "$ENV_FILE" >&2
    exit 1
fi

token="$(grep -E '^AGENT_ADMIN_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2-)"
token="${token%\"}"
token="${token#\"}"

if [[ -z "$token" ]]; then
    printf '%s 里没有 AGENT_ADMIN_TOKEN：跑一次启动脚本会自动生成。\n' "$ENV_FILE" >&2
    exit 1
fi

printf '%s\n' "$token"
