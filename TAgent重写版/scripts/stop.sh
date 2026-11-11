#!/usr/bin/env bash
# TAgent 停止脚本（macOS / Linux）—— 对应 Windows 的 scripts/stop.ps1。
#
# 读取 .run 目录下的 PID 文件，校验进程确实是 start.sh 启动的那一个后再结束。
# 不会按端口结束未知程序。
#
# 停 basic-agent (5001)、tagentnote (5173)，以及 start.sh 拉起的
# OpenNotebook 容器（compose stop，笔记数据保留）。
#
# 用法：
#   ./scripts/stop.sh                  全停
#   ./scripts/stop.sh --keep-notebook  只停前后端，OpenNotebook 容器继续跑

# ！！改本脚本前先看这条 ！！
# macOS 自带的是 bash 3.2，在 UTF-8 locale（终端默认就是）下，紧跟在变量名后面
# 的中文会被吞掉首字节当成变量名的一部分：
#     echo "退出码 $code，继续"   ->   code?: unbound variable
# 所以凡是「变量后面直接跟中文」的地方，一律写成 ${code}。英文标点、空格不受影响。

set -uo pipefail

KEEP_NOTEBOOK=0
while [ $# -gt 0 ]; do
    case "$1" in
        -KeepNotebook|-keepnotebook|--keep-notebook) KEEP_NOTEBOOK=1 ;;
        -h|-Help|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) printf '未知参数: %s\n' "$1" >&2; exit 1 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PACK_ROOT="$(dirname "$ROOT")"
RUN_DIR="$ROOT/.run"
NOTEBOOK_COMPOSE="$PACK_ROOT/opennotebook/docker-compose.yml"

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }
warn() { printf '    [!] %s\n' "$1"; }

for extra in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    case ":$PATH:" in
        *":$extra:"*) ;;
        *) [ -d "$extra" ] && PATH="$PATH:$extra" ;;
    esac
done
export PATH

have() { command -v "$1" >/dev/null 2>&1; }

port_busy() {
    if have lsof; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    elif have ss; then
        ss -ltn "( sport = :$1 )" 2>/dev/null | grep -q LISTEN
    else
        netstat -an 2>/dev/null | grep -qE "[.:]$1[[:space:]].*LISTEN"
    fi
}

proc_stamp() { ps -p "$1" -o lstart= 2>/dev/null | tr -s ' ' | sed 's/^ *//; s/ *$//'; }
proc_cmd()   { ps -p "$1" -o command= 2>/dev/null; }

children_of() { ps -A -o pid=,ppid= 2>/dev/null | awk -v p="$1" '$2==p {print $1}'; }

# 深度优先收集整棵进程树，子进程排在父进程前面。
# 必须连子进程一起结束：vite 在某些配置下会再派生一个 node 子进程，
# 只结束记录的那个 PID，端口会被留下来的子进程继续占着。
pid_tree() {
    local pid="$1" child
    for child in $(children_of "$pid"); do
        pid_tree "$child"
    done
    printf '%s\n' "$pid"
}

# $1 服务名 $2 PID 文件 $3 身份特征（进程命令行里必须出现的路径）
stop_tracked() {
    local name="$1" pid_file="$2" ident="$3"

    if [ ! -f "$pid_file" ]; then
        warn "$name : 未找到 PID 文件，可能未启动"
        return
    fi

    local raw pid stamp cur_stamp
    raw="$(cat "$pid_file" 2>/dev/null | tr -d '\n')"
    pid="${raw%%|*}"
    stamp=''
    case "$raw" in *'|'*) stamp="${raw#*|}" ;; esac

    if ! printf '%s' "$pid" | grep -qE '^[0-9]+$'; then
        warn "$name : PID 文件内容无效，已清理"
        rm -f "$pid_file"
        return
    fi

    if ! kill -0 "$pid" 2>/dev/null; then
        warn "$name : 进程 $pid 已不存在，清理 PID 文件"
        rm -f "$pid_file"
        return
    fi

    # 身份校验：只为防 PID 复用误杀别人的程序。宁可不停，也不能停错。
    #   首选启动时刻指纹 —— start.sh 记下启动那一刻，PID 被复用时时刻必然不同；
    #   旧格式（只有 PID）退回命令行校验：命令行里必须出现本项目的绝对路径。
    if [ -n "$stamp" ]; then
        cur_stamp="$(proc_stamp "$pid")"
        if [ "$cur_stamp" != "$stamp" ]; then
            warn "$name : PID $pid 的启动时刻与记录不符（本项目的进程已退出，PID 被别的程序占用），已跳过并清理 PID 文件"
            rm -f "$pid_file"
            return
        fi
    else
        if ! proc_cmd "$pid" | grep -qF "$ident"; then
            warn "$name : PID $pid 的命令行里没有 ${ident}，无法确认是本项目的进程，已跳过并清理 PID 文件"
            rm -f "$pid_file"
            return
        fi
    fi

    local tree p waited=0
    tree="$(pid_tree "$pid")"
    for p in $tree; do kill -TERM "$p" 2>/dev/null || true; done

    # 最多等 10 秒优雅退出，超时再强制
    while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        for p in $tree; do kill -9 "$p" 2>/dev/null || true; done
        sleep 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        warn "$name : 停止 PID $pid 失败，请手动结束该进程"
        return
    fi
    # 树里可能还剩下没退的子进程（父进程先退时会被 launchd/init 收养）
    for p in $tree; do kill -9 "$p" 2>/dev/null || true; done

    ok "$name : 已停止 (PID $pid)"
    rm -f "$pid_file"
}

echo 'TAgent 停止脚本'

step '停止服务'
# 逐个停：任何一个失败都不能连累另一个，否则会留下半停状态
if [ -f "$RUN_DIR/notebook-ui.pid" ]; then
    stop_tracked '笔记本页面' "$RUN_DIR/notebook-ui.pid" "$PACK_ROOT"
fi
stop_tracked 'tagentnote'  "$RUN_DIR/frontend.pid" "$PACK_ROOT"
stop_tracked 'basic-agent' "$RUN_DIR/agent.pid"    "$ROOT"

step '停止旧的 OpenNotebook 容器（若还在）'
COMPOSE_CMD=''
if have docker && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD='docker compose'
elif have docker-compose; then
    COMPOSE_CMD='docker-compose'
fi

if [ "$KEEP_NOTEBOOK" = "1" ]; then
    warn '按 --keep-notebook 跳过，容器继续运行。'
elif [ ! -f "$NOTEBOOK_COMPOSE" ]; then
    warn '未找到 opennotebook/docker-compose.yml，跳过。'
elif [ -z "$COMPOSE_CMD" ]; then
    warn '没有可用的 docker compose 命令，跳过。'
else
    # 只 stop 不 down：down 会删掉容器，下次启动要重建。
    # 数据本来就在 bind mount 上（notebook_data / surreal_data），两种方式都不会丢。
    if $COMPOSE_CMD -f "$NOTEBOOK_COMPOSE" stop >/dev/null 2>&1; then
        ok '已停止（笔记数据保留在 opennotebook/notebook_data）'
    else
        warn "$COMPOSE_CMD stop 失败（Docker 可能没在跑）。"
    fi
fi

step '检查端口占用'
for p in 5001 5173; do
    if port_busy "$p"; then
        warn "端口 $p 仍被占用（可能是其他程序）。本脚本不会结束未确认的进程，请自行核实："
        warn "    lsof -nP -iTCP:$p -sTCP:LISTEN"
    else
        ok "端口 $p 已释放"
    fi
done

printf '\n完成。\n\n'
