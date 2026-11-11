# OpenNotebook 新版（拆分精简版）

把原来当黑盒用的 OpenNotebook 1.15.0（Next.js + FastAPI + SurrealDB + 后台 worker）手工拆开，
**只留 tagent 真正用到的部分**：笔记本、来源（文本 / 文件 / 网址）、笔记、检索（文本 + 向量）、
问答、笔记本聊天、来源聊天、洞察。播客、模型与凭据管理、变换管理、设置页、高级页都砍掉了。

- 后端 `backend/`：按 tagent（`TAgent重写版/basic-agent`）的分层手工重写，Flask + waitress + SQLite，
  接口路径、字段、编号格式、错误体都和原版一致，tagent 现有的 `opennotebook_kb.py` 和前端白名单不用改。
- 前端 `frontend/`：原版 Next.js 前端源码，只删了砍掉功能的页面和入口，其余组件、样式、字体、
  14 种界面语言原样保留，**保留下来的页面外观和原版一致**。

为什么这样拆、每块对应 tagent 的哪一层、以后怎么并进 tagent，见 [docs/架构分析与拆分方案.md](docs/架构分析与拆分方案.md)。

后端已经并进 `TAgent重写版/basic-agent`（同一个进程，接口仍是 `5055`，检索不再 HTTP 打一圈）。
这个目录留下前端 `frontend/` 和当初的拆分说明。`opennotebook/` 里的 Docker Compose 不再是启动路径。

## 跑起来

平时用交接包的启动脚本即可（`start.command` / `start.sh`）。它拉起 basic-agent（答疑 `5001`，笔记本接口 `5055`）和这个目录里的前端（`8502`）。

笔记本后端源码在 `TAgent重写版/basic-agent/app/` 的各层 `notebook/` 子包，不再单独起一个 Python 进程。

只想看页面时：

需要：Python 3.12 + [uv](https://docs.astral.sh/uv/)、Node.js 20+。

```bash
# 后端在 basic-agent 里（5001 和 5055）
cd TAgent重写版/basic-agent
uv sync
uv run python main.py
```

```bash
# 前端（默认 8502，和原版同端口；/api/* 转给后端）
cd opennotebook新版/frontend
npm ci
npm run build      # 构建时决定后端地址，默认 http://localhost:5055，换地址就在构建前设 INTERNAL_API_URL
npm start
```

浏览器打开 http://localhost:8502 。tagent 的 `/notebook` 页面 iframe 嵌的也是这个地址。

> 原版 OpenNotebook 的 Docker 容器如果还开着，会占着 5055 / 8502，先停掉它，或者新版换端口。

**前端连后端的两条路**（沿用原版的设计，容易踩坑）：

- 普通接口：浏览器**直接**连后端。地址由前端的 `/config` 决定——没设 `API_URL` 时自动拼成
  「当前页面的主机名 + `:5055`」。所以后端不在 5055 时，启动前端要设 `API_URL`，例如
  `API_URL=http://localhost:5056 npm start`（运行时生效，不用重新构建）。后端默认允许跨域。
- 流式接口（问答、来源聊天）和 `/api/*` 改写：由 Next 服务端转发到 `INTERNAL_API_URL`
  （默认 `http://localhost:5055`）。改写规则在**构建时**写死，换后端地址要带着 `INTERNAL_API_URL` 重新 `npm run build`；
  流式转发运行时读这个变量。

换端口的完整例子（后端 5056、前端 8503）：

```bash
ON_PORT=5056 uv run python main.py                      # backend/ 下
INTERNAL_API_URL=http://127.0.0.1:5056 npm run build    # frontend/ 下
PORT=8503 API_URL=http://localhost:5056 INTERNAL_API_URL=http://127.0.0.1:5056 npm start
```

### 前端为什么用 webpack 构建

Next 16 默认的 Turbopack 在**路径里有中文**时处理 Google 字体会报
`next/font/google queries have exactly one entry`（同一份代码放到英文路径下就能构建，已验证）。
仓库路径带「参赛代码」「opennotebook新版」，所以 `dev` / `build` 脚本都加了 `--webpack`，产物和外观不受影响。
构建要下载原版用的三种 Google 字体，下载不了时加代理：`HTTPS_PROXY=http://127.0.0.1:17897 npm run build`。

## 配置（后端环境变量，全部可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ON_HOST` / `ON_PORT` | `127.0.0.1` / `5055` | 监听地址；Docker 里要设 `0.0.0.0` |
| `ON_DATA_DIR` | macOS `~/Library/Application Support/OpenNotebookLite` | SQLite 库 `notebook.sqlite3` 和上传文件 `uploads/` 放这里 |
| `ON_PASSWORD`（或原版的 `OPEN_NOTEBOOK_PASSWORD`） | 空 = 不鉴权 | 设了就要 `Authorization: Bearer <口令>`（也认 `X-Password`） |
| `ON_LLM_BASE_URL` | `http://127.0.0.1:5001/v1/raw` | OpenAI 兼容接口；默认就是 tagent 的原样转发通道 |
| `ON_LLM_MODEL` / `ON_LLM_API_KEY` | 空 | 模型名（空 = tagent 默认模型）、密钥（tagent 本机通道不需要） |
| `ON_LLM_TIMEOUT` | `180` | 单次模型调用超时（秒） |
| `ON_EMBEDDING` | `local` | `off` 关掉向量检索，只用全文检索 |
| `ON_EMBEDDING_MODEL` | `shibing624/text2vec-base-chinese` | 和 tagent 本地知识库同一个，先读本机缓存 |
| `ON_MAX_UPLOAD_MB` | `100` | 上传大小上限 |
| `ON_ALLOW_PRIVATE_URLS` | `false` | 网址来源默认不许访问本机/内网（防 SSRF） |
| `ON_CORS_ORIGINS` | `*` | 逗号分隔 |
| `ON_JOB_WORKERS` / `ON_THREADS` | `2` / `8` | 后台处理线程数 / HTTP 线程数 |

## 和原版的差别

| 方面 | 原版 | 新版 |
|---|---|---|
| 进程 | Next.js + FastAPI + SurrealDB + worker（supervisord） | Next.js + Flask 两个进程 |
| 存储 | SurrealDB | SQLite（WAL），一个文件 |
| 全文检索 | BM25，英文分词，**中文搜不到句中的词** | FTS5 + 中文单字/两字切词，中文可用 |
| 向量检索 | 要在界面上配嵌入模型（现网没配，一直 400） | 默认本地 text2vec，开箱即用 |
| 模型 | 24 家供应商、界面上配凭据 | 只认 OpenAI 兼容接口，环境变量配置，默认走 tagent |
| 来源抽取 | content-core：网页、Office、PDF、音视频、YouTube | 文本、txt/md/csv/json/xml/html、PDF、docx、普通网页 |
| 变换 | 可增删改的提示词模板 | 内置 6 个（中文提示词），只读 |
| 界面 | 11 个页面 | 6 个页面（登录、笔记本列表/详情、来源列表/详情、检索与问答），外观不变 |

## 检查

```bash
cd TAgent重写版/basic-agent && uv run pytest tests/notebook -q && uv run python tools/check_architecture.py
```

```bash
cd opennotebook新版/frontend && npx tsc --noEmit && npm run lint && npm test && npm run build
```

## 许可

前端 `frontend/` 和后端里照搬的接口设计来自 [open-notebook](https://github.com/lfnovo/open-notebook)（MIT 许可，
Copyright (c) 2024 Luis Novo），原版许可证见 [LICENSE.open-notebook](LICENSE.open-notebook)。

