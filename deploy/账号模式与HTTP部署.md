# 账号模式与 HTTP 入口（部署记录 2026-11-21）

本文件记录把 TAgent 切到账号模式、并按“先用 HTTP”要求开启的部署形态。服务器为
`116.56.143.182`（账号 `hmzhang`，无 sudo，全部用户态运行）。

## 一、当前拓扑（暂存/验收环境）

| 组件 | 地址 | 运行方式 |
|---|---|---|
| TAgent 前端 | `http://116.56.143.182:8088` | `vite preview`（127.0.0.1:5174，经 Caddy 反代） |
| TAgent 后端（账号模式） | 127.0.0.1:5002 | `.venv/bin/python main.py` |
| 笔记本 API（账号模式） | 127.0.0.1:5056 | `.venv/bin/python -m uvicorn api.main:app` |
| 笔记本 worker | — | `surreal-commands-worker --import-modules commands` |
| 笔记本 UI | `http://116.56.143.182:8089` | Next standalone（127.0.0.1:8503，经 Caddy） |
| SurrealDB | 127.0.0.1:8010 | 原生二进制，独立数据目录 |

旧的 HTTPS 入口 `8443/8444` 目前 301 跳转到上述 HTTP 入口。

## 二、TAgent 侧改动（本仓库）

`TAgent重写版/basic-agent/app/factory.py`

- 新增 `TAGENT_ALLOW_INSECURE_HTTP=1`：仅当显式设置时，允许
  `TAGENT_PUBLIC_ORIGIN` / `OPEN_NOTEBOOK_PUBLIC_ORIGIN` 使用 `http://`，并允许
  `TAGENT_AUTH_COOKIE_SECURE=0`。**默认关闭，行为与之前完全一致（强制 HTTPS）。**
- 新增 `TAGENT_SESSION_COOKIE_NAME`：显式指定会话 Cookie 名。HTTP 下必须用
  `tagent_session_dev`——`__Host-` 前缀的 Cookie 浏览器要求 Secure，HTTP 会被直接丢弃。

`TAgent重写版/basic-agent/app/rag/opennotebook_kb.py`

- 访问笔记本 API 时携带的 Cookie 名改为读 `TAGENT_SESSION_COOKIE_NAME`，默认仍是
  `__Host-tagent_session`。

## 三、OpenNotebook 侧改动（另一个仓库，仅记录）

属于 `Ronnie-Hu/open-notebook` 的 `feat/tagent-account-isolation-20261109` 分支，未在本仓库。
服务器上的补丁文件为 `0003-notebook-allow-insecure-http.patch`，要点：

```diff
--- a/api/account_auth.py
+++ b/api/account_auth.py
@@
-        parsed = urlsplit(public_origin)
+        parsed = urlsplit(public_origin)
+        allow_insecure = os.getenv("OPEN_NOTEBOOK_ALLOW_INSECURE_HTTP") == "1"
+        allowed_schemes = {"https", "http"} if allow_insecure else {"https"}
         if (
-            parsed.scheme != "https"
+            parsed.scheme not in allowed_schemes
@@
-        if cookie_name != "__Host-tagent_session":
+        allowed_cookies = {"__Host-tagent_session", "tagent_session_dev"} if allow_insecure else {"__Host-tagent_session"}
+        if cookie_name not in allowed_cookies:
```

```diff
--- a/api/main.py
+++ b/api/main.py
@@
-            cookie_name="__Host-tagent_session",
+            cookie_name=os.getenv("TAGENT_SESSION_COOKIE_NAME", "__Host-tagent_session"),
```

## 四、服务器环境变量（关键项）

TAgent（`TAgent重写版/.env.runtime`）：

```ini
TAGENT_PUBLIC_ORIGIN=http://116.56.143.182:8088
OPEN_NOTEBOOK_PUBLIC_ORIGIN=http://116.56.143.182:8089
TAGENT_AUTH_COOKIE_SECURE=0
TAGENT_ALLOW_INSECURE_HTTP=1
TAGENT_SESSION_COOKIE_NAME=tagent_session_dev
TAGENT_DB_URL=ws://127.0.0.1:8010/rpc
TAGENT_DB_NAMESPACE=tagent
TAGENT_DB_DATABASE=app
TAGENT_DATA_KEYS=<Fernet key>
TAGENT_NOTEBOOK_LIFECYCLE_URL=http://127.0.0.1:5056
TAGENT_NOTEBOOK_LIFECYCLE_KEY=<32+ 字节>
```

笔记本（`open-notebook/.env`）：

```ini
OPEN_NOTEBOOK_TAGENT_ACCOUNT_MODE=1
OPEN_NOTEBOOK_PUBLIC_ORIGIN=http://116.56.143.182:8089
OPEN_NOTEBOOK_ALLOW_INSECURE_HTTP=1
TAGENT_SESSION_COOKIE_NAME=tagent_session_dev
OPEN_NOTEBOOK_TAGENT_VERIFIER_URL=http://127.0.0.1:5002
OPEN_NOTEBOOK_LEGACY_ADMIN_ID=<管理员 UUID>
OPEN_NOTEBOOK_TAGENT_DB_SIGNING_KEY=<43–128 字符>
OPEN_NOTEBOOK_TAGENT_LIFECYCLE_KEY=<与 TAgent 相同>
```

## 五、安全影响（务必读）

HTTP 模式下**口令与会话 Cookie 明文传输**，Cookie 无 Secure 属性，同网段可嗅探；
CSRF 仍校验 Origin，但链路本身不可信。仅建议校内/短期演示使用。

放开前建议：
- 更换管理员初始口令（当前为弱口令，交付前必须更换）；
- 不要对该入口做公网映射；
- 恢复 HTTPS 时，删掉 `TAGENT_ALLOW_INSECURE_HTTP` / `OPEN_NOTEBOOK_ALLOW_INSECURE_HTTP`，
  把两个 `PUBLIC_ORIGIN` 改回 `https://`，`AUTH_COOKIE_SECURE` 改回 1 即可，无需回滚代码。

## 六、已验证（2026-11-21）

- 全新账号：注册 201 → 登录 → `/auth/me` 200 → 笔记本列表 200 → 新建笔记本 200 → 笔记本页 200。
- 隔离：学生 2 列表为空，直接访问学生 1 的笔记本返回 404；无 Cookie 访问笔记本 API 返回 401。
- 管理员（`admin@tagent.local`）登录与笔记本访问正常。
- 线上旧站 5173 未受影响。

## 七、校外访问结论

校区边界限制公网入站：校内访问正常，校外两个独立探测点访问 5173/8443 均超时。
服务器无 root，无法从本机放开。校外访问应走学校 SSLVPN / WebVPN；若要长期公网直连，
需网络中心放行入站端口（建议 443）或提供反向代理。
