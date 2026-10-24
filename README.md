# TAgent 交接包

面向「系统建模与仿真」课程的教学智能体：**课程答疑（RAG 流式问答）+ 论文辅助（分章写作、出题、交稿批改）+ 知识笔记本 + 智能测评（出卷判卷）**。

浏览器只访问前端 `5173`。交接包**不含任何 API Key**，模型要用自己的 Key 登记。

## 三个服务

| 服务 | 地址 | 怎么起 | 作用 |
|---|---|---|---|
| **OpenNotebook** | 页面 `8502` / 接口 `5055` | 启动脚本（Docker） | 笔记本：管理笔记与来源 |
| **basic-agent** | `127.0.0.1:5001` | 启动脚本 | 检索、答疑、出卷、判卷 |
| **tagentnote** | `127.0.0.1:5173` | 启动脚本 | 前端，浏览器开这个 |

启动脚本按系统选：**Windows 双击 `start.bat`，macOS 双击 `start.command`**
（Linux 跑 `TAgent重写版/scripts/start.sh`，与 macOS 是同一个脚本）。三个服务都由它一起拉起。
OpenNotebook 起不来时脚本会说明原因并继续启动另外两个 —— 此时答疑只用本地教材 `book1.md`。

> **8502 是页面，5055 才是接口。** basic-agent 打的是 `/api/*`，只有 5055 认。
> 填成 8502 不会报错，只会让笔记本里的内容一条都检索不到、答疑静悄悄退回本地教材。
> 填了浏览器地址也没关系，脚本会自动换算成 5055。

## 快速开始

### 1. 装好 Docker Desktop 并确认它能启动

OpenNotebook 跑在 Docker 里（`opennotebook/docker-compose.yml`）。<https://www.docker.com/products/docker-desktop/>

> **Docker Desktop 报「未检测到虚拟化支持」？** 多数情况 BIOS 是好的，缺的是 Windows 组件。
> 以**管理员**身份运行 `wsl --install --no-distribution`，然后**重启电脑**。
> 自查：`wsl --status`，若报 `WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED` 就是这个原因。

国内建议先配镜像加速（镜像有 GB 级）：Docker Desktop → Settings → Docker Engine，
在 JSON 里加一行 `registry-mirrors`，见 `opennotebook/readme.md` 第三步。

### 2. 双击 `start.bat`（macOS 双击 `start.command`）

首次运行会自动装 Python 与 Node 依赖、生成本机密钥，需要几分钟。脚本是**幂等**的，重复执行会跳过已完成的步骤。

它会依次完成：检查环境与端口 → **起 OpenNotebook 容器并等接口就绪** → `uv sync` → 准备 `.env.runtime` → **下载参考文献（只有第一次要下）** → 准备前端依赖与 `.env` → 起 basic-agent → **自动校验知识来源** → 起前端。

看到这一段就说明检索（RAG）的几路来源都接上了：

```text
==> 检查知识来源
    source = composite
    本地知识库：教材 book1.md + 参考文献 14 篇
    notebook_reachable = true（http://localhost:5055）
```

**参考文献**：出题、答疑、论文批改检索时，除了教材还会用到《系统仿真学报》上和课程最相关的 14 篇论文。
论文版权在期刊、仓库又是公开的，所以仓库里只有篇目清单，全文由启动脚本第一次运行时从期刊官网下到本机
（约 23MB、半分钟左右，之后跳过；网络不通时十秒内放弃，照常启动）。加论文、换论文见 [`TAgent重写版/basic-agent/references/README.md`](TAgent重写版/basic-agent/references/README.md)。

停止：双击 `stop.bat` / `stop.command`。

> **macOS 第一次跑要先给执行权限。** 从 Windows 打包的 zip 解压后 `.command` 常会丢掉可执行位，
> 表现是双击没反应。在交接包目录开一个「终端」，跑一次即可：
>
> ```bash
> chmod +x start.command stop.command
> ```
>
> 若弹「无法打开，因为它来自身份不明的开发者」：右键该文件 → 打开 → 打开。
> 也可以完全不用双击，直接在终端里跑 `./start.command` 或 `bash TAgent重写版/scripts/start.sh`。

**常用参数**（在 PowerShell / 终端里传，双击不需要）：

| Windows | macOS / Linux | 说明 |
|---|---|---|
| `-Lan` | `--lan` | 前端监听 `0.0.0.0`，供局域网访问。明文 HTTP，仅适合短期演示 |
| `-SkipInstall` | `--skip-install` | 跳过 `uv sync` 与 `npm install`，省几十秒 |
| `-SkipNotebook` | `--skip-notebook` | 不启动 OpenNotebook（自己用别的方式起好了） |
| `-WithTts` | `--with-tts` | 连 `aliyun-tts-bridge` 一起起（做播客用，需要阿里云 DashScope Key） |
| `-PypiMirror <URL>` | `--pypi-mirror <URL>` | 装 Python 依赖失败时改用哪个 PyPI 镜像重试，默认阿里云 |
| `-AgentTimeout <秒>` | `--agent-timeout <秒>` | 等 basic-agent 就绪的超时，默认 900（首次要建检索索引，慢的电脑要几分钟） |
| `-NotebookTimeout <秒>` | `--notebook-timeout <秒>` | 等 OpenNotebook 接口就绪的超时，默认 180 |
| — | `--no-open` | 启动完成后不自动打开浏览器（macOS/Linux 默认会开） |

`.command` 也认 PowerShell 那套写法（`-Lan`、`-SkipInstall`…），照着上面抄哪一列都行。

`stop.bat` / `stop.command` 会连 OpenNotebook 容器一起停（`docker compose stop`，笔记数据保留）。
只想停前后端、容器继续跑：`stop.bat -KeepNotebook` / `./stop.command --keep-notebook`。

### 3. 登记模型（必做）

**用自己的 DeepSeek Key，不要用别人的。** 没登记的话前端顶栏是「选择模型」，答疑和出题都会失败。

管理 token 在 `TAgent重写版/.env.runtime` 的 `AGENT_ADMIN_TOKEN`（启动脚本自动生成）。

**网页登记（推荐）**：打开 <http://localhost:5173/models>（或顶栏模型下拉 →「登记 / 管理模型」），
粘贴管理 token → 「连接」→「登记新模型」→ 点「DeepSeek」填好常用项 → 填自己的 Key → 「保存」→「试一下」。
同一页还能改、停用、删除、设默认。token 只留在页面里，不保存，刷新后要重新填。

**会先思考的模型**（DeepSeek 推理模式、通义千问 3、智谱、豆包的思考模式等）把思考也算进输出额度，
思考长了正文会被挤没（2026-10-07 Windows 测试：额度 256 时正文为空）。「试一下」看到
「token 都用在了思考上」，就在「附加参数」点对应的「关闭思考」再保存。附加参数会原样带进每次请求，
各家写法不同：DeepSeek / 智谱 / 豆包是 `{"thinking": {"type": "disabled"}}`，通义千问是 `{"enable_thinking": false}`。
命令行登记时在 JSON 里加一项 `"extra_body": {...}` 即可。

也可以用命令行，macOS / Linux（在交接包根目录跑）：

```bash
TOKEN=$(grep '^AGENT_ADMIN_TOKEN=' TAgent重写版/.env.runtime | cut -d= -f2-)
curl -X POST http://127.0.0.1:5001/admin/model-providers \
  -H "X-Agent-Admin-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"DeepSeek","served_model_id":"deepseek",
       "base_url":"https://api.deepseek.com","upstream_model":"deepseek-chat",
       "auth_mode":"bearer","api_key":"你自己的-sk-xxx","temperature":0.1}'
```

Windows：

```powershell
$token = (Get-Content 'TAgent重写版\.env.runtime' | Where-Object { $_ -match '^AGENT_ADMIN_TOKEN=' }) -replace '^AGENT_ADMIN_TOKEN=',''
$body = @{
  name = 'DeepSeek'; served_model_id = 'deepseek'
  base_url = 'https://api.deepseek.com'; upstream_model = 'deepseek-chat'
  auth_mode = 'bearer'; api_key = '你自己的-sk-xxx'; temperature = 0.1
} | ConvertTo-Json

Invoke-RestMethod -Uri 'http://127.0.0.1:5001/admin/model-providers' -Method Post `
  -Headers @{ 'X-Agent-Admin-Token' = $token } -ContentType 'application/json' -Body $body
```

只要支持标准 Chat Completions 协议（通义千问、OpenAI、vLLM、LM Studio…），都按同样方式登记，不用改代码。

> ⚠️ **Key 是明文存在 `basic-agent/config/model_providers.json` 里的。** 接口返回时会掩码（`****xxxx`），但磁盘上没有加密——当前 basic-agent 代码里没有任何加解密逻辑（`AGENT_PROVIDER_ENCRYPTION_KEY` 是 open-webui 时期留下的，现在没人读）。这个文件已在 `.gitignore` 中，**不要提交、不要连同项目目录打包外传**。

登记完刷新 <http://localhost:5173> 即可。

### 4. 让 OpenNotebook 复用同一个 Key（可选，推荐）

登记过一次之后，OpenNotebook 不用再单独填 DeepSeek Key —— 让它走 basic-agent 的**透传通道**即可。

在 <http://localhost:8502> 里 **Models → Add Configuration → OpenAI Compatible**，填：

| 字段 | 值 |
|---|---|
| Base URL | `http://host.docker.internal:5001/v1/raw` |
| Model | `deepseek`（你注册时的 `served_model_id`） |
| API Key | 随便填，比如 `local`（这条通道不校验，真 Key 在 basic-agent 那边） |

然后 **Sync Models**，把 `deepseek` 指派为 Chat Model。

> **一定要填 `/v1/raw`，不能填 `/v1`。**
> `/v1/chat/completions` 是 TAgent 自己的 RAG 答疑通道，每次调用都会把 `book1.md`
> 和笔记本内容注入 prompt。OpenNotebook 拿它做摘要、来源转换、播客脚本时，
> 会被塞进一堆无关的系统仿真教材，输出直接跑偏。
> `/v1/raw/chat/completions` 什么都不加，原样转发给上游。
>
> `/v1/raw` 只给本机直连的程序用（OpenNotebook 就是直连 5001），**经前端端口（5173 / 4173）访问会被拒绝（403）**：
> 开了 `--lan` 时前端端口对整个局域网开着，这条通道原样转发、什么都能发，不能让谁都拿你的 Key 用。
> 模型登记页的「测试连接」走的是要管理口令的 `/admin/model-providers/<id>/probe`。

#### Embedding（可选，装了检索更准）

basic-agent 没有 `/v1/embeddings`，DeepSeek 官方也不提供 embeddings API，
所以这块没法走上面的透传通道，只能在 OpenNotebook 里单独配。

**但不配也能跑。** TAgent 检索时先试向量检索，失败就退回全文检索：

```python
try:    body["type"] = "vector"   # 没配 embedding 时 OpenNotebook 返回 400
except: body["type"] = "text"     # 自动退回，仍能检索到内容
```

实测确认过这条兜底有效（`vector` → HTTP 400，`text` → HTTP 200）。所以：

| | 不配 embedding | 配了 embedding |
|---|---|---|
| 能不能用 | 能 | 能 |
| 检索方式 | 关键词匹配 | 语义相似 |
| 代价 | 0 | 装 Ollama，约 1.5 GB + 模型 670 MB |

想配的话，两条路选一条：

**A. Ollama（本地、免费、离线）** —— OpenNotebook readme 推荐的做法。
先去 <https://ollama.com/download> 装好（装完它会自己在后台跑服务，不用手动 `ollama serve`），
再新开一个终端拉模型：

```bash
ollama pull mxbai-embed-large
```

然后在 OpenNotebook 里 Models → Add Configuration → Ollama，
Base URL 填 `http://host.docker.internal:11434`
（**不是** `localhost:11434` —— 容器里的 localhost 是容器自己）。

**B. 阿里云百炼（不用装东西）** —— 它的 `text-embedding-v3` 走 OpenAI 兼容接口。
在 OpenNotebook 里选 OpenAI Compatible，Base URL 填
`https://dashscope.aliyuncs.com/compatible-mode/v1`，Model 填 `text-embedding-v3`，
API Key 填你的 DashScope Key。如果你本来就要配播客 TTS，这条更省事。


## 功能

- **答疑** `/qa` — 顶栏切换「课程答疑 / 论文辅助」两种模式，两种模式的会话分开存。
  - **课程答疑**：流式输出，可中途停止与重新生成；右上角选笔记本，**选哪一本就只检索哪一本**，不选则本地教材与全部笔记一起检索；回答可一键「加入笔记本」写回 OpenNotebook。
    回答下面的「引用」列出这次回答依据的材料：教材写到第几章第几页（书上印的页码），论文写题目和期刊卷期、点开是期刊官网的文章页，笔记本来源点开回到笔记本。
  - **论文辅助**：任务卡按 7 个章节（选题与大纲 → … → 完整性检查）分步写，每节填几项信息、点对应按钮，模型按这一节的要求写成对话回答。
    另有两样和章节无关：**「让助手出题」**按笔记本材料出一道小论文题，一键设为本次题目；
    **「交稿批改」**把输入框里的整篇正文交给后端，三个维度（切题与内容 / 论证与结构 / 语言与规范）打分，
    挑出最值得改和最值得夸的几句用朱笔画线加旁批，结果以一张批改过的卷子出现在对话里，刷新后仍在。
- **笔记本** `/notebook` — iframe 嵌入 OpenNotebook，带连接检测与失败提示。
- **测评** `/exam` — 进来先选模式，两种都按选中的笔记本/来源出题：
  - **闪卡模式**：填空 + 选择两类混着来，6~12 张（分片并发生成，撞题的会去重掉）。
    填空可翻面自评也可打字作答，选择点一下就判——**判定全在浏览器本地比对，
    不往返模型，所以是即时的**。答错的卡回队尾重练，随时可以停。
  - **整卷模式**：填空 + 选择 + 大题，总分 100（原来的行为，没变）。要一次做完再提交，
    提交后大题由出卷的同一个模型批改，**还要再等一轮模型**。交卷后点开某道大题可以「逐句批注」，
    点哪道才批哪道，不点不花调用。

  两者出卷耗时取决于你接的模型，这里不写死秒数（在 DeepSeek 上两者都是十秒上下）。
  真正的区别是上面加粗的那两点：闪卡判定不花时间，整卷判卷要再等一轮。

会话历史存在浏览器本地（localStorage），换浏览器或清缓存就没了——后端还没有会话存储接口。

### 合并说明（2026-09-25）

前端采用 [Fandy-ray/Tagent_FrontEnd](https://github.com/Fandy-ray/Tagent_FrontEnd) 的
`paper-assistant-workflow` 分支（`ed2d5d3`，xiewenna985 / FDD 维护的 Open WebUI 风格对话外壳、
论文辅助模式、工作空间与 OpenNoteBook 检索），后端沿用本仓库的 basic-agent。在她的前端上做了三件事：

1. 把本仓库的测评栈移植回去（她的 `/exam` 还是旧的单模式页面）：闪卡/整卷两种模式、公式渲染、整卷大题逐句批注。
2. 在论文辅助模式里接上出题（`POST /essay/topic`）与交稿批改（`POST /essay/review`）。
3. 后端的 `/v1/chat/completions` 开始识别她一直在发的 `mode: "paper"`（换论文写作助教的 system prompt），
   并接受 `retrieval_query`（论文模式用「题目 + 关键词」检索，不再拿几千字的任务 prompt 去检索）。

原来独立的 `/essay` 批改页已经去掉，功能并进了论文辅助模式。合并前的旧前端留在提交 `104242d`，需要时可以取回。
已知：同一篇作文重批，分数可能差一条评分要点（实测 66 与 60，差在「语言与规范」），是模型判分的波动。


## 环境要求

- Python 3.12（`uv` 会自动装，无需预装）
- Node.js ≥ 18（推荐 22 LTS）、npm
- uv：Windows `python -m pip install uv`；macOS `brew install uv`
  （没有 Homebrew 就 `curl -LsSf https://astral.sh/uv/install.sh | sh`，装完新开一个终端）
- Docker Desktop（macOS 上 Apple 芯片选 Apple Silicon 版；OrbStack / colima 也行）
- 首次初始化约 2 GiB 可用空间

依赖由 `basic-agent/uv.lock` 与 `tagentnote/package-lock.json` 固定。**不要复制别人电脑的 `.venv` 或 `node_modules`**，新机器必须按锁文件重装。

### 国内网络：PyPI 镜像有个坑

`uv.lock` 里每个包都写死了 `https://files.pythonhosted.org/...` 的下载地址，而
**`uv sync --frozen` 只认这些地址，镜像设置一概不生效**（`UV_DEFAULT_INDEX`、
`UV_INDEX_URL`、`-i` 全被忽略，见 [astral-sh/uv#19625](https://github.com/astral-sh/uv/issues/19625)）。
所以"先 export 镜像再 `uv sync --frozen`"是没用的，表现就是卡两分钟后
`operation timed out`。

管用的办法是**去掉 `--frozen`** 让 uv 照镜像重新解析一次——包版本仍由
`pyproject.toml` 里的 `==` 钉死，变的只是 `uv.lock` 里记录的下载地址：

```bash
cd TAgent重写版/basic-agent
UV_DEFAULT_INDEX="https://mirrors.aliyun.com/pypi/simple/" uv sync
```

**两边的启动脚本都已经自动处理**（`start.sh` 与 `start.ps1` 同一套逻辑）：
官方源失败时自动改用镜像重解析，并把原 `uv.lock` 备份成 `uv.lock.bak`；
若你已经设了 `UV_DEFAULT_INDEX` / `UV_INDEX_URL`，它会直接走镜像，不再白等官方源。
换镜像：`--pypi-mirror <URL>`（macOS/Linux）、`-PypiMirror <URL>`（Windows）。

npm 那边两个脚本默认都走 npmmirror，失败再退回官方源；手动装的话：

```bash
npm config set registry https://registry.npmmirror.com
```

## 目录结构

```text
TAgent交接版/
  start.bat / stop.bat      Windows 双击入口（放在本层或 TAgent重写版 里都能用）
  start.command / stop.command  macOS 双击入口（同上；首次可能要 chmod +x）
  怎么跑.txt                最简启动备忘
  README.md                 本文件
  TAgent重写版/             后端
    basic-agent/            Flask 服务：RAG、模型注册表、出卷判卷
      app/rag/              knowledge_base(本地教材) / opennotebook_kb / composite_kb
      app/api/openai_compat.py       /v1  答疑通道（走 RAG）
      app/api/openai_passthrough.py  /v1/raw  透传通道（不走 RAG，给 OpenNotebook 用）
      config/               model_providers.json（含 Key，禁止提交）
    scripts/                start.ps1 / stop.ps1（Windows），start.sh / stop.sh（macOS/Linux）
    docs/ 文档/             重构报告、代码手册、项目汇报
    .env.runtime            本机密钥，自动生成，禁止提交
  deploy/                   装成开机自启服务（见 deploy/README.md）
    linux/                  systemd 单元 + install.sh / uninstall.sh
    macos/                  launchd plist + install.sh / uninstall.sh
    windows/                任务计划程序 install.ps1 / uninstall.ps1 / watchdog.ps1
  opennotebook/             OpenNotebook 的 Docker Compose 部署（见 VENDOR.md）
    docker-compose.yml      surrealdb + open_notebook(+ 可选 tts bridge)
    notebook_data/          **你的笔记实际存在这里**，首次启动时创建
    surreal_data/           数据库文件，同上
  tagentnote/               前端（SvelteKit + Vite）
    src/lib/apis/           agent.ts(打 basic-agent) / opennotebook.ts(打 5055)
    .env                    从 .env.example 自动生成
```

## 手动启动

不想用脚本时（对应「怎么跑.txt」）：

```bash
# 后端
cd TAgent重写版/basic-agent
uv sync
uv run python main.py          # 读上一级的 .env.runtime

# 前端（另开一个终端）
cd tagentnote
npm install
npm run build && npm run preview -- --port 5173 --strictPort   # 演示 / 日常用：生产包
# npm run dev                                                   # 改前端代码时用：热更新，但打开慢约 10 倍
```

演示请用生产包（`build` + `preview`），一键启动脚本默认也是这样：开发服务器把几百个源文件逐个现编现发，
答疑页首次打开实测 159 个请求、2.5MB、1.3 秒，生产包是 35 个请求、142KB、0.12 秒；开发服务器第一次遇到新依赖
还会整页刷新一次。`/agent-api` 代理两种模式都有——`vite preview` 默认沿用 `vite.config.ts` 里 `server.proxy` 那份。
只有直接把 `build` 出来的文件扔给别的静态服务器（nginx 等）时才没有这个代理，那就要在那边自己配。

后端端口必须是 **5001**——`tagentnote/vite.config.ts` 的代理写死了 `http://127.0.0.1:5001`。改一边就得改另一边。

## 部署成常驻服务（开机自启）

上面那套是**手动跑**：关掉窗口或重启电脑就没了。要长期挂着（课程演示机、
实验室服务器），用 `deploy/` 下的安装脚本装成系统服务，开机自启、崩了自动拉回来：

| 系统 | 一条命令 | 用的机制 |
|---|---|---|
| Linux | `sudo deploy/linux/install.sh` | systemd |
| macOS | `deploy/macos/install.sh` | launchd LaunchAgent |
| Windows | `deploy\windows\install.ps1` | 任务计划程序 + 看门狗 |

装之前**先手动跑通一次**。各系统的详细步骤、运维命令和排查表见
[deploy/README.md](deploy/README.md)。卸载脚本只删服务定义，代码、依赖、密钥、
笔记数据一概不动。

## 验证

```bash
cd TAgent重写版/basic-agent
uv run pytest -q                    # 2026-10-10：554 passed
```

要在 `basic-agent` 目录直接跑，别只跑 `tests/`：根目录下还有路由、模型客户端、并发这几组（`pytest tests` 只有四百多条）。

```bash
cd tagentnote
npm run check                       # 0 errors、0 warnings
npm run lint                        # 格式（prettier）+ eslint，都要通过
npm test                            # 前端单测：整卷存档（含逐句批注）、整本选笔记本时跳过下载失败的来源
npm run build
```

服务起来后的自检：

- <http://localhost:5001/health> — basic-agent 活着
- <http://localhost:5001/knowledge> — 看 `source` 和 `notebook_reachable`
- <http://localhost:5001/v1/models> — 看模型登记成功没有

## 排查

| 现象 | 原因 |
|---|---|
| 前端顶栏是「选择模型」 | 还没登记模型，见上面第 3 步 |
| 出题、批改报「模型的输出被截断了」，或「试一下」说 token 都用在了思考上 | 模型先思考再回答，思考占满了输出额度。在 `/models` 给它加「关闭思考」的附加参数，见第 3 步 |
| Windows 上每次启动都是开发服务器、页面打开很慢 | 旧版 `start.ps1` 把构建成功误判成失败（没取进程句柄，退出码读成空值），已修。仍然这样就看 `logs\runtime\tagentnote.build*.log` |
| Windows 上 `logs\runtime\basic-agent.*.log` 里中文是乱码 | 旧版没让 Python 用 UTF-8 写重定向的日志，中文 Windows 默认写成 GBK。现在启动脚本启动后端时设 `PYTHONUTF8=1`；旧日志用 GBK 打开，在 PowerShell 里看新日志用 `Get-Content -Encoding UTF8` |
| Windows 上 `npm run lint` 报两百多个文件格式不对 | 旧版本检出时把前端文件转成了 CRLF，prettier 要 LF。现在 `tagentnote/.gitattributes` 规定按 LF 检出，新克隆的不会有；已有的检出拉代码后在 `tagentnote` 目录下先跑 `npx prettier --write .`，再跑 `git add --renormalize .`（只刷新 Git 记下的文件信息，不改内容；不跑的话 `git status` 会显示两百多个文件「已修改」）。有没提交的改动先提交 |
| Windows 上 Docker Desktop 起不来：报错里有 1920，或 `dockerInference` / Inference manager 的运行目录、本地 socket 访问不了 | Docker Desktop 自己的问题，不是本项目的（2026-10-06、10-10、10-11 三次 Windows 测试都遇到过，相关公开问题见 [docker/desktop-feedback#460](https://github.com/docker/desktop-feedback/issues/460)）。恢复办法：完全退出 Docker Desktop（托盘图标里选 Quit），把 `%LOCALAPPDATA%\Docker\run` 和 `%LOCALAPPDATA%\docker-secrets-engine` 两个目录改名备份（例如末尾加 `.bak`），再建两个同名的空目录，重新启动 Docker Desktop。不需要恢复出厂、清理镜像或删数据，容器和笔记数据都在。普通重启后可能复发，复发就再做一遍 |
| 很多人同时用时提问半天不出字，或交稿提示「请稍后再试」 | 后端同时处理的请求数（`WAITRESS_THREADS`，默认 100）和同时批改 / 出卷的份数（`EXAM_MAX_CONCURRENT_LLM`，默认 5，每份同时调 3 次模型）都有上限，超出的排队；批改、出卷最多 8 人排队、最多排 30 秒，排不上或等不到就提示稍后再试。人更多就在 `TAgent重写版/.env.runtime` 里调大，重启后端生效。压测数据见 `TAgent重写版/文档/升级轮次/round-07.md`「压测」 |
| 页面请求全 502 | basic-agent 没起来，或端口不是 5001 |
| 答疑能答但笔记本内容检索不到 | `notebook_reachable` 是 false。8502 是页面，接口在 5055 |
| 笔记本明明起着，`notebook_reachable` 还是 false | 多半有个旧的 basic-agent 残留进程在占着 5001。`stop.bat` 后确认 5001 已释放再重启。另：开着 Clash 等系统代理的 Mac 上，旧版本会把 `localhost:5055` 也送进代理（代理回 502），现在本机和局域网地址一律直连 |
| 「参考文献」那一步提示有几篇没准备好 | 提示会逐篇点名、写明原因（如「官网返回 404」「下载超时」）。期刊官网要直连（走代理会 403），偶尔也会临时出错。不影响启动，答疑和出题先用教材和其余论文，标了「下次启动会再试」的会自动补；也可以在 `basic-agent` 目录跑 `uv run python tools/fetch_references.py` |
| `/admin/model-providers` 返回 503 | `AGENT_ADMIN_TOKEN` 是空的。跑一次 `start.bat` 会自动补 |
| 提示端口被占 | 先 `stop.bat`；脚本不会去结束不认识的进程 |
| Docker 引擎不可用 | Docker Desktop 没启动，或 WSL2 组件没装（见上面第 1 步）|
| Docker Desktop 一直卡在 `Starting the Docker Engine...` | 先别管界面，开个终端跑 `docker ps`。能通就说明引擎其实是好的，只是面板没刷新，`start.bat` 照样能用 |
| 拉镜像超时 | 配 Docker 镜像加速，见 `opennotebook/readme.md` 第三步 |
| OpenNotebook 的摘要里混进了系统仿真教材 | Base URL 填成 `/v1` 了，要填 `/v1/raw`，见上面第 4 步 |
| OpenNotebook 建不了向量索引 | 没配 embedding。不影响使用（会退回全文检索），想要语义检索见第 4 步 |
| 证书相关报错 | 网络拦截了 `https://api.deepseek.com`，需要代理 |
| macOS 双击 `.command` 没反应 | 丢了可执行权限。`chmod +x start.command stop.command`；提示「身份不明的开发者」就右键 → 打开 |
| macOS 提示端口 `5001` 被 `ControlCenter` 占用 | 那是「隔空播放接收器」（它占 5000/7000，偶尔波及邻近端口）。系统设置 → 通用 → 隔空播放与接力，关掉它 |
| macOS 上 `zsh: command not found: uv` | uv 装在 `~/.local/bin` 但没进 PATH。新开一个终端，或 `export PATH="$HOME/.local/bin:$PATH"` |
| `uv sync` 报 `operation timed out` / `Failed to download` | `--frozen` 无视镜像，见上面「国内网络」一节。启动脚本会自动改走镜像重试，还不行就 `-PypiMirror` / `--pypi-mirror` 换一个 |
| 拉 Docker 镜像 `context deadline exceeded` | 配镜像加速（`opennotebook/readme.md` 第三步）。注意 `docker-compose.yml` 里 `pull_policy: always` 会每次重拉，实在拉不动就把那两行注释掉 |

运行日志在 `TAgent重写版/logs/runtime/`。

## 安全

以下内容**禁止提交**（已在 `.gitignore` 中）：

- `TAgent重写版/.env.runtime` — 管理 token、内部 token
- `TAgent重写版/basic-agent/config/model_providers.json` — **明文 API Key**
- `.venv`、`node_modules`、`.run/`、`logs/`

管理通道与内部通道用不同 token，都以 `hmac.compare_digest` 定长比较；token 未配置时返回 `503` 而不是放行。日志对 `api_key`、`token`、`secret`、`password` 递归脱敏。

API Key 在磁盘上**没有加密**（见上），所以 `model_providers.json` 要当成密码文件对待。

## 已知缺口

- 会话历史不落盘。
- API Key 明文落盘，没有加密（见「安全」一节）。
- `文档/` 与 `docs/` 里部分内容仍描述 open-webui 时期的架构。

## 许可证

见 `TAgent重写版/LICENSE`。
