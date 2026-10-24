# TAgentNote · 系统建模与仿真智能教学平台

面向《系统建模与仿真》课程的智能教学前端，支持 RAG 增强答疑、知识笔记本与智能测评。面向「AI for 高校教学智能体创新大赛 · 未来课堂」方向。

## 功能概览

| 模块       | 路由            | 说明                                                                                                                    |
| ---------- | --------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 欢迎页     | `/welcome`      | 平台入口与品牌展示                                                                                                      |
| 智能体选择 | `/agent-select` | 选择模型与智能体类型                                                                                                    |
| 答疑智能体 | `/qa`           | 课程答疑（检索增强问答）；论文辅助模式：任务卡分步写作、让助手出题、交稿批改（三维打分 + 逐句批注，结果以试卷样式呈现） |
| 笔记本     | `/notebook`     | 嵌入 OpenNoteBook 知识工作空间                                                                                          |
| 测评智能体 | `/exam`         | 闪卡模式（本地判定）与整卷模式（交卷后模型判分，大题可点开逐句批注）                                                    |

## 技术栈

- [SvelteKit](https://svelte.dev/docs/kit) + Svelte 5
- TypeScript
- Vite 8
- Tailwind CSS 4

## 快速开始

### 环境要求

- Node.js 18+（建议使用当前 LTS）

### 安装与运行

在仓库根目录（能看到 `package.json` 的目录）执行：

```bash
npm install --registry=https://registry.npmmirror.com --no-audit
npm run dev
```

国内访问官方 npm 源时，`npm install` 可能在 audit 阶段长时间停住。也可用：

```bash
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认一般为 `http://localhost:5173`）。根路径 `/` 会自动跳转到 `/welcome`。

需要同时启动三套服务：

1. 本仓库前端：`npm run dev`（默认 `5173`）
2. OpenNoteBook：按 https://gitee.com/kevin-zhengscuter/fixed_open_notebook 启动（默认 `8502`）
3. basic-agent：`5001`（Vite 代理写死了这个端口），负责答疑检索、出题判卷与论文批改

不启动 OpenNoteBook 时，笔记本页会提示服务未连接。不启动 basic-agent 时，答疑和测评会失败。

### 常用脚本

| 命令              | 说明                   |
| ----------------- | ---------------------- |
| `npm run dev`     | 启动开发服务器         |
| `npm run build`   | 生产构建               |
| `npm run preview` | 预览生产构建           |
| `npm run check`   | 类型与 Svelte 检查     |
| `npm run lint`    | ESLint + Prettier 检查 |
| `npm run format`  | Prettier 格式化        |

## 环境变量

在项目根目录创建或编辑 `.env`：

```env
# OpenNoteBook 嵌入地址（笔记本页 iframe）
PUBLIC_OPENNOTEBOOK_URL=http://localhost:8502/notebooks
```

未配置时，笔记本页默认使用 `http://localhost:8502/notebooks`。

OpenNoteBook本地配置教程详见：https://gitee.com/kevin-zhengscuter/fixed_open_notebook

## 项目结构

```
src/
├── lib/
│   ├── apis/agent.ts          # 模型列表与 Mock RAG 接口
│   └── components/
│       ├── chat/              # 答疑页聊天 UI
│       └── quiz/              # 测评面板
└── routes/
    ├── welcome/               # 欢迎页
    ├── agent-select/          # 智能体选择
    ├── qa/                    # 答疑
    ├── notebook/              # OpenNoteBook 嵌入
    └── exam/                  # 测评
```

## 说明

- 答疑走 `POST /v1/chat/completions`（论文模式带 `mode: "paper"` 与 `retrieval_query`），测评走 `/quiz/exam/generate`、`/quiz/flash/stream`（闪卡边写边给，一行一个 JSON）、`/quiz/exam/review`、`/quiz/exam/annotate`，论文辅助的出题与批改走 `/essay/topic`、`/essay/review`，均由 Vite 代理到 basic-agent。
- 笔记本依赖外部 OpenNoteBook 服务；需先在本地或目标环境启动对应服务，并配置 `PUBLIC_OPENNOTEBOOK_URL`。
- 播客功能本周在教学前端隐藏。若 OpenNoteBook 内仍露出播客入口，需 tagent 组在对端 UI 关闭。

## License

Private（见 `package.json`）。
