# TAgent 完整版 OpenNotebook 账号模式上线核对

本清单适用于 TAgent `feat/auth-full-notebook-20261116` 与 OpenNotebook
`feat/tagent-account-isolation-20261109` 配套部署。旧的 `deploy/linux/install.sh`
仍按单用户轻量笔记本部署，不能直接作为本模式的安装脚本。

## 启用前

1. 为 TAgent 前端和完整版 OpenNotebook 前端提供同一主机名的可信 HTTPS 入口；可使用受信任的 IP 证书。浏览器必须能验证证书。TAgent 后端、OpenNotebook API、worker 与 SurrealDB 只允许内网或本机访问，不向公网开放。
2. 记录正在运行的版本、进程、端口与数据目录；备份并试恢复 TAgent 学习记录库、身份库、OpenNotebook SurrealDB、上传文件、播客文件和 SQLite 聊天检查点。保留旧版本的回滚路径。
3. 创建独立 TAgent 身份 namespace/database 和数据库运行账号。用管理员数据库凭据运行 `TAgent重写版/basic-agent/tools/init_auth_db.py`，再用 `bootstrap_admin.py` 在终端交互创建首个管理员。核对管理员 UUID；OpenNotebook 迁移 27 会把旧共享内容归给它。
4. 分别配置两个仓库的 `.env.auth.example` 所列变量，密钥只放服务器的受保护配置中。TAgent 与 OpenNotebook 的生命周期密钥须一致；OpenNotebook API 和 worker 的数据库签名密钥须一致。`TAGENT_MAIL_MODE=disabled` 表示邮箱仅作唯一登录标识，不验证邮箱归属，忘记密码由管理员核验后在服务器终端重置。
5. 排空旧 OpenNotebook 后台队列，再启动数据库、TAgent 单个后端进程、OpenNotebook API 与 worker，最后启动两个前端和 HTTPS 入口。账号模式首次启动会运行迁移；不要在迁移后的数据库上直接切回匿名模式，应使用迁移前备份回滚。学生提供的模型地址还需由服务器出站网络策略限制为外部 HTTPS 目的地。

## 上线验收

- 用两个独立浏览器注册不同学生账号，在各自设备再次登录；检查 TAgent 答疑历史、个人设置和完整版 OpenNotebook 笔记、资料、聊天、模型密钥与设置随账号读取。
- 交叉访问对方的笔记 ID、资料下载地址和后台任务结果，应被拒绝；旧共享内容只能由管理员看到。
- 验证退出登录、换账号、改密码后旧会话失效；检查导出 ZIP 含本人数据和上传文件，注销后本人会话失效而其他账号数据仍在。
- 让 OpenNotebook worker 实际处理上传、检索和播客任务，检查任务完成后仍只属于发起账号。记录浏览器、API、worker 和数据库证据。
- 复核 HTTPS 证书、Cookie 的 `Secure`/`HttpOnly`、浏览器来源限制、后端私有监听、备份可恢复性和异常时回滚流程。

任何一项失败都不要开放注册。当前本地 HTTP 夹具与自动测试不能替代以上服务器验收；在可信 HTTPS 入口就绪前保持 `TAGENT_AUTH_ENABLED=0` 和 `OPEN_NOTEBOOK_TAGENT_ACCOUNT_MODE=0`。
