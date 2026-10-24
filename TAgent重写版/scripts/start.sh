#!/usr/bin/env bash
# TAgent 一键启动脚本（macOS / Linux）—— 对应 Windows 的 scripts/start.ps1。
#
# 按顺序拉起三个服务：
#
#     OpenNotebook 8502 页面 / 5055 接口   笔记本（Docker Compose）
#     basic-agent  127.0.0.1:5001          出题 / 判卷 / 检索
#     tagentnote   127.0.0.1:5173          前端（先构建，再用 Vite preview 提供生产包）
#
# OpenNotebook 走 ../opennotebook/docker-compose.yml，需要 Docker 引擎在跑
# （Docker Desktop / OrbStack / colima 都行）。起不来时会说明原因并继续启动
# 其余两个服务 —— 此时答疑只用本地教材 book1.md。
#
# 脚本可重复执行；已有的 .env.runtime 里的密钥永远不会被改写。
#
# 用法：
#   ./scripts/start.sh                     仅本机访问
#   ./scripts/start.sh --lan               前端监听 0.0.0.0，供局域网访问
#   ./scripts/start.sh --skip-install      跳过 uv sync 与 npm install
#   ./scripts/start.sh --skip-notebook     不启动 OpenNotebook
#   ./scripts/start.sh --with-tts          连 aliyun-tts-bridge 一起起（需 DashScope Key）
#   ./scripts/start.sh --agent-timeout 1800 等 basic-agent 就绪的超时，默认 900
#   ./scripts/start.sh --notebook-timeout 300 等 OpenNotebook 接口就绪的超时，默认 180
#   ./scripts/start.sh --no-open           启动完成后不自动打开浏览器
#   ./scripts/start.sh --dev               前端改用开发服务器（改代码时用；页面打开慢约 10 倍）
#   ./scripts/start.sh --prepare           只装依赖、生成密钥，不启动任何服务
#                                          （deploy/ 下的服务安装脚本用它做前置）
#   ./scripts/start.sh --pypi-mirror <URL> 装 Python 依赖失败时改用哪个镜像重试
#                                          （默认阿里云；官方源装得动就不会用到）
#
# 为了方便照着 README 抄命令，PowerShell 风格的 -Lan / -SkipInstall 等写法也认。

# ！！改本脚本前先看这条 ！！
# macOS 自带的是 bash 3.2，在 UTF-8 locale（终端默认就是）下，紧跟在变量名后面
# 的中文会被吞掉首字节当成变量名的一部分：
#     echo "退出码 $code，继续"   ->   code?: unbound variable
# 所以凡是「变量后面直接跟中文」的地方，一律写成 ${code}。英文标点、空格不受影响。

# 不用 set -e：这个脚本要在多处"失败但继续"（比如 Docker 起不来仍然起前后端），
# 关键步骤一律显式 || die。
set -uo pipefail

LAN=0
SKIP_INSTALL=0
SKIP_NOTEBOOK=0
WITH_TTS=0
OPEN_BROWSER=1
# 前端默认构建后用 vite preview 提供生产包；--dev 改回开发服务器
FRONTEND_DEV=0
# 只做前置准备（装依赖、写 .env.runtime），不拉起服务。deploy/ 下的
# systemd / launchd / 计划任务安装脚本靠它复用这条已经跑熟的准备流程。
PREPARE_ONLY=0
# uv sync 失败时用来重试的 PyPI 镜像（--pypi-mirror 可改）
PYPI_MIRROR='https://mirrors.aliyun.com/pypi/simple/'
# 首次启动要建检索索引：Windows 测试机首次启动全流程约 221 秒（2026-10-11，含建索引），慢的电脑会更久。
# 超时会关掉后端，而向量缓存要建完才保存，下次又得从头建——超时设短了，慢电脑会一直起不来。
# 后端一就绪就不再等，设长不影响平时启动。
AGENT_TIMEOUT=900
NOTEBOOK_TIMEOUT=180

# 打印文件开头那段注释（第 2 行起，到第一个不以 # 开头的行为止）。原来写死 2–26 行，后加的 --pypi-mirror 说明没打出来。
usage() { awk 'NR == 1 { next } /^#/ { print; next } { exit }' "$0"; }

while [ $# -gt 0 ]; do
    case "$1" in
        -Lan|-lan|--lan)                                  LAN=1 ;;
        -SkipInstall|-skipinstall|--skip-install)         SKIP_INSTALL=1 ;;
        -SkipNotebook|-skipnotebook|--skip-notebook)      SKIP_NOTEBOOK=1 ;;
        -WithTts|-withtts|--with-tts)                     WITH_TTS=1 ;;
        --no-open)                                        OPEN_BROWSER=0 ;;
        -Dev|-dev|--dev)                                  FRONTEND_DEV=1 ;;
        -Prepare|--prepare)                               PREPARE_ONLY=1 ;;
        --pypi-mirror)                                    shift; PYPI_MIRROR="${1:-}" ;;
        -AgentTimeout|--agent-timeout)                    shift; AGENT_TIMEOUT="${1:-900}" ;;
        -NotebookTimeout|--notebook-timeout)              shift; NOTEBOOK_TIMEOUT="${1:-180}" ;;
        -h|-Help|--help)                                  usage; exit 0 ;;
        *) printf '未知参数: %s\n（--help 看用法）\n' "$1" >&2; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------------- 常量
# 5001 不是随便挑的，两个理由：
#   1. tagentnote/vite.config.ts 里的 /agent-api 代理写死了 http://127.0.0.1:5001；
#   2. macOS 的「隔空播放接收器」常年占着 5000。
# 改这里就必须同步改 vite.config.ts，否则前端所有请求 502。
AGENT_PORT=5001
FRONTEND_PORT=5173
# OpenNotebook 的 REST 接口。8502 是 Streamlit 页面，拿它打 /api/* 只会拿到 HTML。
NOTEBOOK_API='http://localhost:5055'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
# 交接包根目录：TAgent重写版 的上一级。opennotebook / tagentnote 都挂在这一层。
PACK_ROOT="$(dirname "$ROOT")"
AGENT_DIR="$ROOT/basic-agent"
ENV_FILE="$ROOT/.env.runtime"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs/runtime"
AGENT_PY="$AGENT_DIR/.venv/bin/python"

NOTEBOOK_DIR="$PACK_ROOT/opennotebook"
NOTEBOOK_COMPOSE="$NOTEBOOK_DIR/docker-compose.yml"

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }
warn() { printf '    [!] %s\n' "$1"; }
die()  { printf '\n[错误] %s\n\n' "$1" >&2; exit 1; }

# 双击 .command 打开的窗口不一定继承完整 PATH（nvm / Homebrew / uv 装在这些位置）。
for extra in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    case ":$PATH:" in
        *":$extra:"*) ;;
        *) [ -d "$extra" ] && PATH="$PATH:$extra" ;;
    esac
done
export PATH

have() { command -v "$1" >/dev/null 2>&1; }

# 端口是否已被监听。lsof 是 macOS 自带的；Linux 上没有就退回 ss / netstat。
port_busy() {
    if have lsof; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    elif have ss; then
        ss -ltn "( sport = :$1 )" 2>/dev/null | grep -q LISTEN
    else
        netstat -an 2>/dev/null | grep -qE "[.:]$1[[:space:]].*LISTEN"
    fi
}

# 占端口的是谁，用于把"端口被占"这句话说得能落地
port_owner() {
    have lsof || return 0
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (PID " $2 ")"}'
}

# 进程启动时刻，作为 PID 指纹：PID 被复用时启动时刻必然不同。
# stop.sh 靠它确认"这个 PID 确实是本脚本启动的那一个"，避免误杀。
proc_stamp() { ps -p "$1" -o lstart= 2>/dev/null | tr -s ' ' | sed 's/^ *//; s/ *$//'; }

write_pid_file() { printf '%s|%s\n' "$1" "$(proc_stamp "$1")" > "$2"; }

# 轮询健康检查；进程中途死掉就立刻返回，不用干等到超时
wait_health() {
    local url="$1" timeout="$2" pid="${3:-}" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        if curl -fsS -m 5 -o /dev/null "$url" 2>/dev/null; then return 0; fi
        if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then return 2; fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

show_log_tail() {
    [ -f "$1" ] || return 0
    printf '\n--- %s（最后 20 行）---\n' "$1"
    tail -n 20 "$1"
    printf -- '---\n'
}

kill_pid_tree() {
    local pid="$1" child
    for child in $(ps -A -o pid=,ppid= 2>/dev/null | awk -v p="$pid" '$2==p {print $1}'); do
        kill_pid_tree "$child"
    done
    kill -9 "$pid" 2>/dev/null || true
}

# ------------------------------------------------- .env 读写
# 读一个键。键不存在返回 1，键存在（哪怕值为空）返回 0 并打印值。
read_env_value() {
    local file="$1" key="$2" line
    [ -f "$file" ] || return 1
    line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" 2>/dev/null | head -n 1)"
    [ -n "$line" ] || return 1
    printf '%s' "${line#*=}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
    return 0
}

# 读一个密钥。空值等同于没有 —— .env.runtime.example 里所有密钥都是空的，
# 直接复制过来的话，空的 AGENT_ADMIN_TOKEN 会让 /admin/model-providers 返回 503，
# 而报错信息完全看不出是这个原因。所以"键存在但值为空"必须照样重新生成。
get_env_secret() {
    local value
    value="$(read_env_value "$1" "$2")" || return 1
    [ -n "$value" ] || return 1
    printf '%s' "$value"
}

# 待写入的键值对攒在这个临时文件里（bash 3.2 没有关联数组）
UPDATES_FILE=""
queue_update() { printf '%s=%s\n' "$1" "$2" >> "$UPDATES_FILE"; }

# 就地更新 .env 风格文件里的若干个键，不动其余内容：
# 已存在的键改值，不存在的键追加到末尾。注释、顺序、以及所有没点名的键
# （尤其是密钥）原样保留 —— 这是"永不覆盖已生成密钥"这条承诺的落点。
apply_env_updates() {
    local file="$1" tmp
    [ -f "$file" ] || : > "$file"
    tmp="$(mktemp "${file}.XXXXXX")" || die "无法在 $(dirname "$file") 下创建临时文件。"
    awk -v updfile="$UPDATES_FILE" '
        BEGIN {
            n = 0
            while ((getline line < updfile) > 0) {
                i = index(line, "=")
                if (i == 0) continue
                k = substr(line, 1, i - 1)
                if (!(k in vals)) { keys[++n] = k }
                vals[k] = substr(line, i + 1)
                used[k] = 0
            }
        }
        {
            t = $0
            sub(/^[ \t]+/, "", t); sub(/[ \t]+$/, "", t)
            if (t != "" && substr(t, 1, 1) != "#" && index(t, "=") > 0) {
                i = index(t, "=")
                k = substr(t, 1, i - 1)
                sub(/^[ \t]+/, "", k); sub(/[ \t]+$/, "", k)
                if (k in vals) { print k "=" vals[k]; used[k] = 1; next }
            }
            print $0
        }
        END { for (i = 1; i <= n; i++) if (!used[keys[i]]) print keys[i] "=" vals[keys[i]] }
    ' "$file" > "$tmp" || { rm -f "$tmp"; die "更新 $file 失败。"; }
    mv "$tmp" "$file" || die "写入 $file 失败。"
}

printf 'TAgent 启动脚本（%s）\n' "$(uname -s)"
printf '项目目录: %s\n' "$ROOT"

# ---------------------------------------------------------------- 0. 环境检查
step '检查运行环境'

have curl || die '未找到 curl。'

if ! have uv; then
    die '未找到 uv。安装任选其一：
       brew install uv
       curl -LsSf https://astral.sh/uv/install.sh | sh   （装到 ~/.local/bin，装完新开一个终端）
       python3 -m pip install --user uv'
fi

# 前端默认先 vite build，再用 vite preview 提供生产包：开发服务器把几百个源文件逐个现编现发，
# 实测答疑页首次打开 159 个请求、2.5MB、1.3 秒，生产包是 35 个请求、142KB、0.12 秒（2026-10-02）；
# 开发服务器第一次遇到新依赖还会「优化依赖后整页刷新」，演示时点到一半页面自己刷掉。
# /agent-api 代理两种模式都有：vite preview 的 proxy 默认沿用 vite.config.ts 里 server.proxy 那份。
have node || die '未找到 Node.js。前端需要它，请安装 Node.js 22 LTS（22.13 及以上）：https://nodejs.org/dist/latest-v22.x/'
have npm  || die '未找到 npm。请随 Node.js 22 LTS 一并安装。'
NODE_VER="$(node -v | sed 's/^v//')"
NODE_MAJOR="${NODE_VER%%.*}"
NODE_MINOR="$(printf %s "${NODE_VER#*.}" | cut -d. -f1)"
# 前端工具链（eslint 10 / vite 8）的 engines 是 ^20.19 || ^22.13 || >=24，
# 而 tagentnote/.npmrc 里开了 engine-strict=true —— 不满足就不是警告而是直接
# EBADENGINE 装不上。这里必须连小版本一起卡：只看大版本会放过 22.11 这种，
# 脚本这一关轻松通过，几分钟后卡在 npm install，报错还完全看不出是版本问题。
NODE_OK=0
case "$NODE_MAJOR" in
    2[4-9]|[3-9][0-9]) NODE_OK=1 ;;
    22) [ "$NODE_MINOR" -ge 13 ] && NODE_OK=1 ;;
    20) [ "$NODE_MINOR" -ge 19 ] && NODE_OK=1 ;;
esac
if [ "$NODE_OK" != 1 ]; then
    die "Node.js 版本为 ${NODE_VER}，前端工具链要求 20.19+ / 22.13+ / 24+。
       当前这个在：$(command -v node)
       装 22 LTS 最新版即可：https://nodejs.org/dist/latest-v22.x/"
fi
ok "uv $(uv --version 2>/dev/null | awk '{print $2}') / Node.js $NODE_VER / npm 就绪"

# 前端与后端是两个仓库：交接包里 tagentnote 是 TAgent重写版 的同级目录。
FRONTEND_DIR=''
for candidate in "$PACK_ROOT/tagentnote" "$ROOT/tagentnote"; do
    if [ -f "$candidate/package.json" ]; then
        FRONTEND_DIR="$candidate"
        break
    fi
done
[ -n "$FRONTEND_DIR" ] || die "未找到前端目录 tagentnote（找过 $PACK_ROOT/tagentnote 和 $ROOT/tagentnote）。请确认交接包解压完整。"
ok "前端目录: $FRONTEND_DIR"

# --prepare 只装依赖不起服务，端口被占（比如服务已经在跑）不该拦着它
if [ "$PREPARE_ONLY" = "1" ]; then
    ok '端口检查已跳过（--prepare 不启动服务）'
else
for p in "$AGENT_PORT" "$FRONTEND_PORT"; do
    if port_busy "$p"; then
        owner="$(port_owner "$p")"
        msg="端口 $p 已被占用"
        [ -n "$owner" ] && msg="${msg}，占用者：$owner"
        die "${msg}。
       请先运行 ./stop.command（或 ./scripts/stop.sh），或自行确认占用程序后处理
       —— 本脚本不会结束未知进程。
       （macOS 上若占用者是 ControlCenter，那是「隔空播放接收器」：
         系统设置 -> 通用 -> 隔空播放与接力，关掉它。）"
    fi
done
ok "端口 $AGENT_PORT / $FRONTEND_PORT 可用"
fi

mkdir -p "$RUN_DIR" "$LOG_DIR" || die "无法创建 $RUN_DIR / ${LOG_DIR}。"

# ------------------------------------------------- 1. OpenNotebook
step 'OpenNotebook'

notebook_api_up() { curl -fsS -m 5 -o /dev/null "$NOTEBOOK_API/api/notebooks" 2>/dev/null; }

# docker compose（v2 插件）还是 docker-compose（v1 独立命令）
COMPOSE_CMD=''
detect_compose() {
    if have docker && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD='docker compose'
    elif have docker-compose; then
        COMPOSE_CMD='docker-compose'
    fi
    [ -n "$COMPOSE_CMD" ]
}

# CLI 装了不代表引擎在跑。别用 `docker info` 探测：Docker 29 即使连不上引擎，
# 照样打印客户端信息并**退出码 0**。要用 version --format {{.Server.Version}}，
# 这条拿不到服务端就返回非 0。
docker_engine_ok() {
    have docker || return 1
    docker version --format '{{.Server.Version}}' >/dev/null 2>&1
}

docker_help() {
    warn 'Docker 引擎不可用，OpenNotebook 起不来。常见原因与排查：'
    warn '  1. Docker Desktop 没启动 —— 打开它，等菜单栏的鲸鱼图标不再闪动再重跑本脚本。'
    warn '     命令行确认：docker ps 能通就说明引擎是好的（面板有时只是没刷新）。'
    warn '  2. 装了 OrbStack / colima 的话，先把它启动：colima start'
    warn '  3. 确实没装：https://www.docker.com/products/docker-desktop/ （Apple 芯片选 Apple Silicon 版）'
    warn '  4. 首次跑还要在 Docker Desktop -> Settings -> Resources -> File Sharing'
    warn "     里确认交接包所在目录可被共享（当前：${PACK_ROOT}）。"
}

NOTEBOOK_UP=0
# --prepare 只做准备，容器交给服务管理器去拉
if [ "$PREPARE_ONLY" = "1" ]; then SKIP_NOTEBOOK=1; fi
if notebook_api_up; then
    NOTEBOOK_UP=1
    ok "已在运行（${NOTEBOOK_API}）"
elif [ "$SKIP_NOTEBOOK" = "1" ]; then
    warn '按 --skip-notebook 跳过。'
elif [ ! -f "$NOTEBOOK_COMPOSE" ]; then
    warn "未找到 ${NOTEBOOK_COMPOSE}，跳过。请自行启动 OpenNotebook（页面 8502 / 接口 5055）。"
elif ! docker_engine_ok; then
    docker_help
elif ! detect_compose; then
    warn '有 docker 但没有 compose 子命令（也没有 docker-compose）。请升级 Docker Desktop。'
else
    # 加密密钥：compose 里读 ${OPEN_NOTEBOOK_ENCRYPTION_KEY}，
    # 上游默认值是 change-me-to-a-secret-string，不能就这么用。
    NOTEBOOK_ENV="$NOTEBOOK_DIR/.env"
    if ! get_env_secret "$NOTEBOOK_ENV" 'OPEN_NOTEBOOK_ENCRYPTION_KEY' >/dev/null; then
        UPDATES_FILE="$(mktemp)"
        queue_update 'OPEN_NOTEBOOK_ENCRYPTION_KEY' "$(openssl rand -hex 32)"
        apply_env_updates "$NOTEBOOK_ENV"
        rm -f "$UPDATES_FILE"
        chmod 600 "$NOTEBOOK_ENV" 2>/dev/null || true
        ok '已生成 opennotebook/.env 里的加密密钥'
    fi

    # 默认不带 aliyun-tts-bridge：它要阿里云 DashScope Key（交接包里没有），
    # 而且要现场 docker build，白等一轮。需要播客再加 --with-tts。
    if [ "$WITH_TTS" = "1" ]; then
        COMPOSE_SERVICES='--build'
    else
        COMPOSE_SERVICES='surrealdb open_notebook'
    fi

    warn '首次启动要从 Docker Hub 拉镜像（GB 级），可能要几分钟到十几分钟。'
    warn '拉取失败请先配镜像加速，见 opennotebook/readme.md 第三步。'
    ( cd "$NOTEBOOK_DIR" && $COMPOSE_CMD -f "$NOTEBOOK_COMPOSE" up -d $COMPOSE_SERVICES )
    compose_code=$?

    if [ "$compose_code" -ne 0 ]; then
        warn "$COMPOSE_CMD 退出码 ${compose_code}，OpenNotebook 没能起来。"
        if docker_engine_ok; then
            # 引擎是通的，那就不是"Docker 没起来"，而是拉镜像失败 —— 国内直连
            # Docker Hub 经常超时（context deadline exceeded / failed to resolve
            # reference）。两种情况的处置办法完全不同，别把人往错误的方向指。
            warn 'Docker 引擎本身是通的，是拉镜像那一步失败了。国内直连 Docker Hub 经常超时。'
            warn '配一个镜像加速再重跑：Docker Desktop -> Settings -> Docker Engine，'
            warn '在 JSON 里加 "registry-mirrors"（推荐填自己的阿里云/华为云专属地址），'
            warn '点 Apply & restart 后再跑一次本脚本。细节见 opennotebook/readme.md 第三步。'
            warn '另外 docker-compose.yml 里写了 pull_policy: always —— 镜像已经在本地也会'
            warn '每次重新拉一遍；实在拉不动可以把那两行注释掉，用本地镜像起。'
            warn '只想先把课程用起来：加 --skip-notebook 跳过笔记本，答疑走本地教材。'
        else
            docker_help
        fi
    else
        warn "等待 OpenNotebook 接口就绪（最长 $NOTEBOOK_TIMEOUT 秒）..."
        waited=0
        while [ "$waited" -lt "$NOTEBOOK_TIMEOUT" ]; do
            if notebook_api_up; then NOTEBOOK_UP=1; break; fi
            sleep 3
            waited=$((waited + 3))
        done
        if [ "$NOTEBOOK_UP" = "1" ]; then
            ok "已就绪（页面 http://localhost:8502 / 接口 ${NOTEBOOK_API}）"
        else
            warn "$NOTEBOOK_TIMEOUT 秒内接口仍不可达。看日志：$COMPOSE_CMD -f \"$NOTEBOOK_COMPOSE\" logs open_notebook"
        fi
    fi
fi

if [ "$NOTEBOOK_UP" != "1" ]; then
    warn '继续启动其余服务。但答疑与出题只会检索本地教材 book1.md，笔记本里的内容一条都取不到。'
fi

# ------------------------------------------------- 2. basic-agent 依赖
#
# 这里有个坑，值得先说清楚：
#   uv.lock 里每个包都写死了 https://files.pythonhosted.org/... 的下载地址，
#   而 `uv sync --frozen` 会照着这些地址下，**镜像设置一概不生效**
#   （UV_DEFAULT_INDEX / UV_INDEX_URL / -i 全都被忽略，见 astral-sh/uv#19625）。
#   所以国内网络下"先 export UV_DEFAULT_INDEX 再 uv sync --frozen"是没用的，
#   表现就是卡上两分钟然后 operation timed out。
#   真正管用的是去掉 --frozen 让 uv 照镜像重新解析一次 —— 版本仍由 pyproject.toml
#   里的 == 钉死，变的只是 uv.lock 里记录的下载地址。
sync_agent_deps_via_mirror() {
    local index="$1"
    # 备份只做一次：第二次失败时别把已经改写过的 lock 当原件覆盖掉
    if [ -f "$AGENT_DIR/uv.lock" ] && [ ! -f "$AGENT_DIR/uv.lock.bak" ]; then
        cp "$AGENT_DIR/uv.lock" "$AGENT_DIR/uv.lock.bak"
        warn '原 uv.lock 已备份为 basic-agent/uv.lock.bak（想还原就把它改回去，或 git checkout uv.lock）。'
    fi
    ( cd "$AGENT_DIR" && UV_DEFAULT_INDEX="$index" uv sync )
}

if [ "$SKIP_INSTALL" = "1" ]; then
    step '跳过 basic-agent 依赖检查（--skip-install）'
else
    # uv sync 是幂等的：环境已完整时几秒内返回；环境残缺时会自动补齐。
    # Python 3.12 本机没有的话 uv 会自己下一个，不用预装。
    step '准备 basic-agent 依赖'
    # uv 单次请求默认 30 秒就超时，网速一般时 torch / faiss 这种大包必挂。
    [ -n "${UV_HTTP_TIMEOUT:-}" ] || export UV_HTTP_TIMEOUT=120

    USER_INDEX="${UV_DEFAULT_INDEX:-${UV_INDEX_URL:-}}"
    if [ -n "$USER_INDEX" ]; then
        # 人家已经指定镜像了，就别再拿 --frozen 去撞官方源白等两分钟。
        warn "检测到已设置 PyPI 镜像：${USER_INDEX}"
        warn '直接按镜像重新解析（不用 --frozen，否则镜像会被 uv 忽略）。'
        sync_agent_deps_via_mirror "$USER_INDEX" \
            || die "basic-agent 依赖安装失败（镜像 ${USER_INDEX}）。
       换一个镜像再试：./scripts/start.sh --pypi-mirror https://pypi.tuna.tsinghua.edu.cn/simple"
        ok '就绪（走镜像装的）'
    elif ( cd "$AGENT_DIR" && uv sync --frozen ); then
        ok '就绪'
    else
        warn 'uv sync --frozen 失败。'
        warn '注意 uv 的已知行为：--frozen 只认 uv.lock 里写死的 files.pythonhosted.org'
        warn '地址，镜像设置全都不生效（astral-sh/uv#19625）—— 所以这里换成走镜像'
        warn "重新解析一次：${PYPI_MIRROR}"
        warn '包版本不变（由 pyproject.toml 的 == 钉死），变的只是 uv.lock 里的下载地址。'
        sync_agent_deps_via_mirror "$PYPI_MIRROR" \
            || die "basic-agent 依赖安装失败（官方源和镜像 ${PYPI_MIRROR} 都没成）。
       可以换个镜像重试：
         ./scripts/start.sh --pypi-mirror https://pypi.tuna.tsinghua.edu.cn/simple
         ./scripts/start.sh --pypi-mirror https://mirrors.cloud.tencent.com/pypi/simple
       或者挂上代理再跑。"
        ok '就绪（走镜像装的）'
    fi
fi
[ -x "$AGENT_PY" ] || die "未找到 ${AGENT_PY}。请去掉 --skip-install 重跑一次。"

# ------------------------------------------------- 3. .env.runtime
step '准备 .env.runtime'
UPDATES_FILE="$(mktemp)"
trap 'rm -f "$UPDATES_FILE"' EXIT

if [ -f "$ENV_FILE" ]; then
    OLD_PORT="$(read_env_value "$ENV_FILE" 'BASIC_AGENT_PORT')" || OLD_PORT=''
    if [ -n "$OLD_PORT" ] && [ "$OLD_PORT" != "$AGENT_PORT" ]; then
        warn "BASIC_AGENT_PORT 原为 ${OLD_PORT}，已改为 ${AGENT_PORT}（前端代理写死了 ${AGENT_PORT}）。密钥不受影响。"
    fi
fi

queue_update 'BASIC_AGENT_HOST'     '127.0.0.1'
queue_update 'BASIC_AGENT_PORT'     "$AGENT_PORT"
queue_update 'BASIC_AGENT_BASE_URL' "http://127.0.0.1:$AGENT_PORT"

# 密钥：已有值的一律原样保留，缺失或为空的才生成。
GENERATED=''
# 两对 token 必须成对相同：AGENT_* 由 basic-agent 校验，BASIC_AGENT_* 由调用方携带发送。
for pair in 'AGENT_ADMIN_TOKEN:BASIC_AGENT_ADMIN_TOKEN:管理 token' \
            'AGENT_INTERNAL_TOKEN:BASIC_AGENT_INTERNAL_TOKEN:内部 token'; do
    key_a="${pair%%:*}"
    rest="${pair#*:}"
    key_b="${rest%%:*}"
    label="${rest#*:}"

    value="$(get_env_secret "$ENV_FILE" "$key_a")" \
        || value="$(get_env_secret "$ENV_FILE" "$key_b")" \
        || value=''
    if [ -z "$value" ]; then
        value="$(openssl rand -hex 32)"
        GENERATED="${GENERATED:+${GENERATED}、}$label"
    fi
    queue_update "$key_a" "$value"
    queue_update "$key_b" "$value"
done

# .env.runtime.example 里列了这一项，就照样补齐，免得两边对不上。
# 但要说清楚：当前的 basic-agent 代码里没有任何地方读它，
# API Key 是**明文**存在 basic-agent/config/model_providers.json 的
# （加密是 open-webui 时期的事，那套已经不在本包里了）。
if ! get_env_secret "$ENV_FILE" 'AGENT_PROVIDER_ENCRYPTION_KEY' >/dev/null; then
    # Fernet 密钥：32 字节的 url-safe base64
    queue_update 'AGENT_PROVIDER_ENCRYPTION_KEY' \
        "$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"
fi

# 非密钥的默认值：只在整个键都不存在时补。空值对它们是合法的
# （比如 KNOWLEDGE_SOURCE= 表示按 OPEN_NOTEBOOK_URL 自动判断）。
add_default() {
    read_env_value "$ENV_FILE" "$1" >/dev/null || queue_update "$1" "$2"
}
add_default 'OPEN_NOTEBOOK_API_URL'        "$NOTEBOOK_API"
add_default 'OPEN_NOTEBOOK_URL'            'http://localhost:8502/notebooks'
add_default 'OPEN_NOTEBOOK_PASSWORD'       ''
add_default 'KNOWLEDGE_SOURCE'             ''
add_default 'AGENT_PROVIDER_ALLOWED_HOSTS' ''
add_default 'AGENT_PROVIDER_ALLOWED_CIDRS' ''

apply_env_updates "$ENV_FILE"
rm -f "$UPDATES_FILE"
trap - EXIT

if [ -n "$GENERATED" ]; then
    chmod 600 "$ENV_FILE" 2>/dev/null || warn '未能把 .env.runtime 权限收紧到 600（不影响运行）。'
    ok "已生成：${GENERATED}（内含密钥，权限 600，切勿提交或外传）"
else
    ok '密钥齐全，原样保留'
fi

# ------------------------------------------------- 4. 载入环境变量
step '载入环境变量'
# 逐行解析而不是 `. "$ENV_FILE"`：.env 里的值不带引号，source 会把
# 含空格或 $ 的值当成 shell 语法解释。
while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    val="${line#*=}"
    key="$(printf '%s' "$key" | sed 's/[[:space:]]*$//')"
    case "$key" in
        [A-Za-z_]*)
            printf '%s' "$key" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$' && export "$key=$val"
            ;;
    esac
done < "$ENV_FILE"
# 进程环境优先级高于 .env 文件（python-dotenv 不覆盖已存在的变量），
# 这样即便 basic-agent/.env 里写了别的端口，也一定按 $AGENT_PORT 起。
export BASIC_AGENT_HOST='127.0.0.1'
export BASIC_AGENT_PORT="$AGENT_PORT"
# 嵌入模型 shibing624/text2vec-base-chinese（约 400MB）在第一次检索时才下载。
# 裸奔直连 huggingface.co 在国内基本必然超时，表现是答疑请求一直卡住不返回，
# 日志里只有一句 unauthenticated requests 提示，完全看不出是被墙。
# basic-agent/.env.example 里本来写了 HF_ENDPOINT，但这个脚本从不生成
# basic-agent/.env（只生成 tagentnote/.env 和 opennotebook/.env），那行等于
# 从没生效过 —— 所以直接放进进程环境。
#
# 两种情况不要碰：
#   1. 用户自己设过 HF_ENDPOINT，尊重原值；
#   2. 机器挂了代理。hf-mirror 只镜像元数据，大文件仍旧跳去 HF 的 CDN；而且
#      它会把经代理出去的请求判定为墙外来源，直接 308 跳回 huggingface.co，
#      huggingface_hub 的解析链在这一跳上会断，报错是看着毫不相干的
#      "does not appear to have a file named pytorch_model.bin or
#      model.safetensors"。有代理的机器让它直连反而是对的。
if [ -z "${HF_ENDPOINT:-}" ] \
   && [ -z "${HTTPS_PROXY:-}" ] && [ -z "${https_proxy:-}" ] \
   && [ -z "${ALL_PROXY:-}" ] && [ -z "${all_proxy:-}" ]; then
    export HF_ENDPOINT='https://hf-mirror.com'
fi
ok "basic-agent 监听 127.0.0.1:$AGENT_PORT"

# ------------------------------------------------- 4b. 参考文献
# 《系统仿真学报》等论文：出题、答疑、批改检索时和教材一起用。仓库是公开的、版权在期刊，
# 仓库里只有篇目清单（basic-agent/references/manifest.json），全文在这一步从期刊官网下到本机。
# 必须在 basic-agent 起来之前：它启动时建索引，晚到的论文要等下次启动才用得上。
# 已经下过的直接跳过；下载失败只提示、照常启动，下次启动再补。.env.runtime 里 TAGENT_REFERENCES=0 可关掉。
if [ "${TAGENT_REFERENCES:-1}" != "0" ]; then
    step '参考文献（系统仿真学报）'
    ( cd "$AGENT_DIR" && "$AGENT_PY" tools/fetch_references.py ) \
        || warn '参考文献没准备好，这次先只用教材，下次启动再补。'
fi

# ------------------------------------------------- 5. 前端依赖与 .env
step '准备前端'
FRONT_ENV="$FRONTEND_DIR/.env"
if [ ! -f "$FRONT_ENV" ] && [ -f "$FRONTEND_DIR/.env.example" ]; then
    cp "$FRONTEND_DIR/.env.example" "$FRONT_ENV" && ok '已从 .env.example 生成 tagentnote/.env'
fi

# 微信 / 浏览器传来的 zip 会给文件打上 com.apple.quarantine。
# JS 不受影响，但 Vite 8 的 rolldown 是 Mach-O 原生绑定（.node），
# Gatekeeper 会拒绝 dlopen，进程瞬间退出；rolldown 却把原因包装成
# "Cannot find native binding"，看起来像 npm 没装全。清掉隔离属性即可，
# 不必一上来就删 node_modules。
if [ "$(uname -s)" = Darwin ] && have xattr && [ -d "$FRONTEND_DIR/node_modules" ]; then
    xattr -cr "$FRONTEND_DIR/node_modules" 2>/dev/null || true
fi

install_frontend_deps() {
    warn '安装前端依赖，可能要几分钟...'
    # 先走 npmmirror（国内快得多），失败了再退回官方源 —— 反过来在国外网络下也成立。
    if ( cd "$FRONTEND_DIR" && npm install --registry=https://registry.npmmirror.com --no-audit --no-fund ); then
        ok '就绪'
    else
        warn 'npmmirror 装失败，退回官方源 registry.npmjs.org 再试一次...'
        ( cd "$FRONTEND_DIR" && npm install --registry=https://registry.npmjs.org --no-audit --no-fund ) \
            || die 'npm install 两个源都失败了。检查网络/代理，或手动执行：
       cd tagentnote && npm install'
        ok '就绪（官方源）'
    fi
}

VITE_BIN="$FRONTEND_DIR/node_modules/vite/bin/vite.js"
frontend_vite_ok() {
    [ -f "$VITE_BIN" ] || return 1
    ( cd "$FRONTEND_DIR" && node "$VITE_BIN" --version >/dev/null 2>&1 )
}

# 只看「Vite 跑不跑得起来」是不够的：队友加了新依赖之后，旧的 node_modules
# 照样能跑 vite --version，于是跳过安装，直到构建到一半才报缺包。
# 装完留一份 package-lock.json 的指纹，下次比对才能发现依赖变了。
LOCK_FILE="$FRONTEND_DIR/package-lock.json"
LOCK_STAMP="$FRONTEND_DIR/node_modules/.tagent-lock-stamp"
lock_fingerprint() {
    [ -f "$LOCK_FILE" ] || return 1
    if have shasum; then shasum -a 256 "$LOCK_FILE" | cut -d' ' -f1
    elif have sha256sum; then sha256sum "$LOCK_FILE" | cut -d' ' -f1
    else wc -c <"$LOCK_FILE" | tr -d ' '
    fi
}
frontend_deps_fresh() {
    frontend_vite_ok || return 1
    [ -f "$LOCK_STAMP" ] || return 1
    [ "$(cat "$LOCK_STAMP" 2>/dev/null)" = "$(lock_fingerprint)" ]
}
stamp_lock() { lock_fingerprint >"$LOCK_STAMP" 2>/dev/null || true; }

if [ "$SKIP_INSTALL" = "1" ]; then
    warn '跳过 npm install（--skip-install）'
elif frontend_deps_fresh; then
    ok 'node_modules 与 package-lock.json 一致，跳过 npm install'
elif frontend_vite_ok && [ ! -f "$LOCK_STAMP" ]; then
    warn 'node_modules 没有依赖指纹（旧版本装的），对齐一次 package-lock.json'
    install_frontend_deps
    stamp_lock
elif frontend_vite_ok; then
    warn 'package-lock.json 变了（队友可能加了依赖），重新 npm install'
    install_frontend_deps
    stamp_lock
elif [ -d "$FRONTEND_DIR/node_modules" ]; then
    warn '已有 node_modules，但 Vite 原生绑定加载失败，删掉重装。'
    rm -rf "$FRONTEND_DIR/node_modules"
    install_frontend_deps
    stamp_lock
else
    install_frontend_deps
    stamp_lock
fi

VITE_BIN="$FRONTEND_DIR/node_modules/vite/bin/vite.js"
[ -f "$VITE_BIN" ] || die "未找到 ${VITE_BIN}。请去掉 --skip-install 重跑，或在 tagentnote 下手动执行 npm install。"

if [ "$PREPARE_ONLY" = "1" ]; then
    printf '\n准备完成（--prepare：没有启动任何服务）。\n'
    printf '  Python 依赖:  %s\n' "$AGENT_PY"
    printf '  前端依赖:     %s\n' "$FRONTEND_DIR/node_modules"
    printf '  运行时配置:   %s\n' "$ENV_FILE"
    printf '\n接下来可以装成开机自启的服务，见 deploy/ 下对应系统的说明。\n\n'
    exit 0
fi

# ------------------------------------------------- 6. 启动 basic-agent
step "启动 basic-agent (127.0.0.1:$AGENT_PORT)"
AGENT_OUT="$LOG_DIR/basic-agent.out.log"
AGENT_ERR="$LOG_DIR/basic-agent.err.log"
cd "$AGENT_DIR" || die "无法进入 ${AGENT_DIR}。"
nohup "$AGENT_PY" main.py >"$AGENT_OUT" 2>"$AGENT_ERR" &
AGENT_PID=$!
# 从作业表里摘掉：否则本脚本清理时的 kill 会在终端上多打一行
# "Killed: 9 nohup ..."，看着像是脚本自己出错了。
disown %+ 2>/dev/null || disown 2>/dev/null || true
cd "$ROOT" || true
write_pid_file "$AGENT_PID" "$RUN_DIR/agent.pid"

# 前端构建和 basic-agent 加载互不相干：趁等后端的这几秒在后台先构建（实测省 4~5 秒）。
# 每次都重新构建：源码改过而包是旧的，比多等几秒难查得多。
FRONT_MODE='preview'
FRONT_BUILD_PID=''
FRONT_BUILD_LOG="$LOG_DIR/tagentnote.build.log"
if [ "$FRONTEND_DEV" = "1" ]; then
    FRONT_MODE='dev'
else
    ( cd "$FRONTEND_DIR" && node "$VITE_BIN" build >"$FRONT_BUILD_LOG" 2>&1 ) &
    FRONT_BUILD_PID=$!
    ok '前端生产包已在后台开始构建（和 basic-agent 加载同时进行，结果见后面「构建前端」一步）'
fi

# basic-agent 没起来、脚本要退出时，把还在跑的后台构建一起停掉：它不在 PID 文件里，stop 停不了，
# 紧接着重新启动的话两次构建会同时写一个输出目录。杀掉后 wait 回收一下，bash 就不会打出像报错的「Killed: 9」。
stop_front_build() {
    [ -n "$FRONT_BUILD_PID" ] || return 0
    kill_pid_tree "$FRONT_BUILD_PID"
    wait "$FRONT_BUILD_PID" 2>/dev/null || true
}

warn "首次启动要加载嵌入模型、建检索索引，约 1–5 分钟（慢的电脑更久），最长等待 $AGENT_TIMEOUT 秒；之后用缓存，几秒就好..."
wait_health "http://127.0.0.1:$AGENT_PORT/health" "$AGENT_TIMEOUT" "$AGENT_PID"
case $? in
    0) ok "已就绪 (PID $AGENT_PID)" ;;
    2)
        show_log_tail "$AGENT_ERR"
        stop_front_build
        rm -f "$RUN_DIR/agent.pid"
        die "basic-agent 启动后随即退出。完整日志：$AGENT_ERR"
        ;;
    *)
        show_log_tail "$AGENT_ERR"
        kill_pid_tree "$AGENT_PID"
        stop_front_build
        rm -f "$RUN_DIR/agent.pid"
        die "basic-agent 在 $AGENT_TIMEOUT 秒内未就绪。日志：$AGENT_ERR
       电脑较慢或模型下载慢的话可以加大超时：./scripts/start.sh --agent-timeout 1800"
        ;;
esac

# 「怎么跑.txt」让人手动开 /knowledge 看这一项，这里直接替他看了。
step '检查知识来源'
# 这个接口已经改成不阻塞（探活挪到后台，见 app/infra/background_probe.py），
# 不再需要为「OpenNotebook 连不上要等 15~20 秒」留 60 秒。
# 代价是刚启动时头一次读到的 notebook_reachable 可能还是 null（后台还没探完）。
KNOWLEDGE="$(curl -fsS -m 10 "http://127.0.0.1:$AGENT_PORT/knowledge" 2>/dev/null)"
if [ -n "$KNOWLEDGE" ]; then
    SOURCE="$(printf '%s' "$KNOWLEDGE" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    ok "source = ${SOURCE:-?}"
    REFS="$(printf '%s' "$KNOWLEDGE" | sed -n 's/.*"references"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')"
    [ -n "$REFS" ] && ok "本地知识库：教材 book1.md + 参考文献 ${REFS} 篇"
    if [ "$SOURCE" = 'local' ]; then
        warn '当前只用本地教材 book1.md。想接笔记本，请确认 OpenNotebook 已启动且 OPEN_NOTEBOOK_API_URL 指向 5055。'
    elif printf '%s' "$KNOWLEDGE" | grep -q '"notebook_reachable"[[:space:]]*:[[:space:]]*true'; then
        ok 'notebook_reachable = true'
    else
        warn 'notebook_reachable = false，笔记本连不上。'
        warn '答疑仍能作答，但内容只来自本地教材。8502 是页面端口，接口在 5055。'
    fi
else
    warn "读 /knowledge 失败。服务本身已经起来了，可稍后手动打开 http://localhost:$AGENT_PORT/knowledge 再看一次。"
fi

# ------------------------------------------------- 7. 启动前端
if [ "$LAN" = "1" ]; then VITE_HOST='0.0.0.0'; else VITE_HOST='127.0.0.1'; fi
FRONT_OUT="$LOG_DIR/tagentnote.out.log"
FRONT_ERR="$LOG_DIR/tagentnote.err.log"
cd "$FRONTEND_DIR" || die "无法进入 ${FRONTEND_DIR}。"

# 构建是在启动 basic-agent 时就放到后台开始的，这里等它收尾。
# 构建失败不致命：退回开发服务器，慢一些但能用，并把原因留在日志里。
if [ -n "$FRONT_BUILD_PID" ]; then
    step '构建前端（生产包）'
    if wait "$FRONT_BUILD_PID"; then
        ok '构建完成'
    else
        show_log_tail "$FRONT_BUILD_LOG"
        warn "构建失败，改用开发服务器启动（页面打开会慢一些）。构建日志：$FRONT_BUILD_LOG"
        FRONT_MODE='dev'
    fi
fi

step "启动 tagentnote (${VITE_HOST}:${FRONTEND_PORT}，${FRONT_MODE})"
# 直接用 node 跑 vite，不经 npm：npm 会再派生一个 node 子进程，
# PID 文件记到的是 npm 那一层，stop 时杀不掉真正监听端口的进程。
nohup node "$VITE_BIN" "$FRONT_MODE" --port "$FRONTEND_PORT" --strictPort --host "$VITE_HOST" \
    >"$FRONT_OUT" 2>"$FRONT_ERR" &
FRONT_PID=$!
disown %+ 2>/dev/null || disown 2>/dev/null || true
cd "$ROOT" || true
write_pid_file "$FRONT_PID" "$RUN_DIR/frontend.pid"

wait_health "http://127.0.0.1:$FRONTEND_PORT/" 120 "$FRONT_PID"
FRONT_RC=$?
if [ "$FRONT_RC" -ne 0 ]; then
    show_log_tail "$FRONT_ERR"
    # 一并停掉已起来的 basic-agent，别留下半停状态占着端口
    kill_pid_tree "$FRONT_PID"
    kill_pid_tree "$AGENT_PID"
    rm -f "$RUN_DIR/frontend.pid" "$RUN_DIR/agent.pid"
    if [ "$FRONT_RC" = "2" ]; then
        die "前端启动后随即退出（basic-agent 也已一并停止）。完整日志：$FRONT_ERR
       多半是 node_modules 装坏了，可以删掉重装：rm -rf tagentnote/node_modules && npm --prefix tagentnote install"
    fi
    die "前端在 120 秒内未就绪（basic-agent 也已一并停止）。日志：$FRONT_ERR"
fi
ok "已就绪 (PID $FRONT_PID)"

# ------------------------------------------------- 完成
printf '\n启动完成。\n'
printf '  浏览器访问:   http://localhost:%s\n' "$FRONTEND_PORT"
[ "$NOTEBOOK_UP" = "1" ] && printf '  笔记本页面:   http://localhost:8502\n'
[ "$LAN" = "1" ] && printf '  局域网访问:   http://%s:%s\n' "$(ipconfig getifaddr en0 2>/dev/null || echo '<本机IP>')" "$FRONTEND_PORT"
printf '  知识来源自检: http://localhost:%s/knowledge\n' "$AGENT_PORT"
printf '  运行日志:     %s\n' "$LOG_DIR"
printf '  停止服务:     ./stop.command  或  ./scripts/stop.sh\n\n'

# 登记提示只在**确实没登记**时才给。已经登记过还照着念一长串 curl，
# 既吓人又没必要——而且早就有网页版登记页了，不用再让人手敲命令。
MODELS="$(curl -fsS -m 10 "http://127.0.0.1:$AGENT_PORT/v1/models" 2>/dev/null)"
if printf '%s' "$MODELS" | grep -q '"id"'; then
    ok '已登记模型，可以直接用'
else
    printf '还没登记模型。请用自己的 DeepSeek Key 登记一个（不要用别人的 Key），\n'
    printf '否则前端顶栏会是「选择模型」，答疑和出题都会失败。\n\n'
    printf '  登记页面:     http://localhost:%s/models\n\n' "$FRONTEND_PORT"
    printf '（页面要填管理口令，它在 %s 里的 AGENT_ADMIN_TOKEN。）\n\n' "$ENV_FILE"
fi

if [ "$OPEN_BROWSER" = "1" ]; then
    if have open; then
        open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
    elif have xdg-open; then
        xdg-open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
    fi
fi

exit 0
