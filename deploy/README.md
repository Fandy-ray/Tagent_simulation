# 部署：把 TAgent 装成常驻服务

交接包根目录的 `start.bat` / `start.command` 是**手动跑**：双击起来，关掉终端窗口
或者重启电脑就没了。这个目录解决的是另一件事 —— **开机自启、崩了自动拉回来**，
用于课程演示机、实验室服务器这类要长期挂着的场景。

三个系统各用各自的原生机制，不引入任何第三方守护工具：

| 系统 | 用什么 | 装在哪 | 需要管理员 |
|---|---|---|---|
| **Linux** | systemd unit | `/etc/systemd/system/` | 是（`sudo`） |
| **macOS** | launchd LaunchAgent | `~/Library/LaunchAgents/` | 否 |
| **Windows** | 任务计划程序 + 看门狗 | 任务库 `\TAgent\` | 一般不用，注册失败时用管理员 |

具体步骤看各自的说明：

- [linux/README.md](linux/README.md)
- [macos/README.md](macos/README.md)
- [windows/README.md](windows/README.md)

## 装之前

**先手动跑通一次。** 部署脚本不解决"这台机器能不能跑起来"的问题，它只负责把
已经能跑的东西挂成服务。先照根目录 `README.md` 双击一次 `start.bat` /
`start.command`，确认浏览器能打开 <http://localhost:5173>、模型也登记好了，再回来部署。

三个系统共同的前置：

- **uv**（装 Python 依赖，会自动带上 Python 3.12）
- **Node.js ≥ 18**（推荐 22 LTS）+ npm
- **Docker**（可选。只影响 OpenNotebook 笔记本；没有它答疑仍能用本地教材 `book1.md`）
- 首次约 2 GiB 可用空间

安装脚本都会先跑一次 `scripts/start.sh --prepare`（Windows 是 `start.ps1 -Prepare`）
把依赖装好、密钥生成好，再去注册服务。这一步是**幂等**的：已经装过就几秒返回，
`.env.runtime` 里已有的密钥永远不会被改写。

## 装完是什么样

| 服务 | 地址 | 说明 |
|---|---|---|
| basic-agent | `127.0.0.1:5001` | 检索、答疑、出卷判卷 |
| 前端 tagentnote | `127.0.0.1:5173` | **浏览器开这个** |
| OpenNotebook | 页面 `8502` / 接口 `5055` | 笔记本，跑在 Docker 里 |

数据与日志：

```text
TAgent重写版/.env.runtime               本机密钥（禁止外传）
TAgent重写版/basic-agent/config/        model_providers.json —— 明文 API Key
TAgent重写版/logs/runtime/              运行日志（macOS/Windows；Linux 走 journald）
opennotebook/notebook_data/             你的笔记实际存在这里
opennotebook/surreal_data/              数据库文件
```

卸载脚本只删服务定义，**上面这些一个都不动**。

## 端口为什么是 5001 不是 5000

两个原因：`tagentnote/vite.config.ts` 里 `/agent-api` 的代理写死了
`http://127.0.0.1:5001`；而 macOS 的「隔空播放接收器」常年占着 5000。
改端口要两边一起改，否则前端所有请求 502。

## 为什么前端跑的是 dev server（以及为什么该换）

这三套服务定义写的时候以为 `/agent-api → 127.0.0.1:5001` 这条反向代理只存在于 Vite dev server，
所以跑的都是 `vite dev`。其实 `vite preview` 默认沿用同一份代理（2026-10-02 实测：健康检查和
流式回答都能经它到 5001）。一键启动脚本已经改成「先 `vite build`、再 `vite preview`」——
答疑页首次打开从 159 个请求、2.5MB、1.3 秒降到 35 个请求、142KB、0.12 秒。

这里的 launchd / systemd / 计划任务还是 `vite dev`：改成生产包需要在服务启动前先构建一次
（systemd 用 `ExecStartPre`，launchd 和 Windows 计划任务要包一层脚本），而且要在三个系统上
各自实测，留到下一轮。真要装成常驻服务又在意打开速度，可以先手动 `npm run build`，再把服务里的
`dev` 换成 `preview`。

要上真正的生产静态托管，得自己在 Nginx / Caddy 里补一条 `/agent-api` 的反代规则
指向 5001，那是另一套部署，不在本目录范围内。
答疑（SSE）和闪卡（`/quiz/flash/stream`，一行一个 JSON）都是边写边发的，反代不能把响应攒齐了再转：
后端已带 `X-Accel-Buffering: no`，Nginx 会照做；别的反代要自己关掉响应缓冲。

## 安全

- 默认只监听 `127.0.0.1`。加 `--lan` / `-Lan` 才对外，那是**明文 HTTP**，
  答疑内容和管理 token 都不加密，只适合内网短期演示。对外提供服务请在前面
  加反向代理并配 HTTPS。
- `.env.runtime`（管理 token）和 `basic-agent/config/model_providers.json`
  （**明文 API Key**）要当密码文件对待，别连同项目目录打包外传。
- Linux 的安装脚本默认用**调用 sudo 的那个普通用户**跑服务，不是 root；
  macOS 装的是用户级 LaunchAgent；Windows 的任务以当前用户身份、不提权运行。
