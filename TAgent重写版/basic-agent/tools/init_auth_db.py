"""一次性初始化 TAgent 独立身份库。使用管理员数据库凭据运行，不在 Web 进程内建表。

示例：uv run python tools/init_auth_db.py；连接配置从 TAGENT_DB_* 环境变量读取。
建表前先在 SurrealDB 创建专用 namespace/database 和数据库级运行账号。
"""

from __future__ import annotations

import os

from surrealdb import Surreal


SCHEMA = (
    "DEFINE TABLE IF NOT EXISTS auth_accounts SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS account_email ON auth_accounts FIELDS email UNIQUE",
    "DEFINE INDEX IF NOT EXISTS account_username ON auth_accounts FIELDS username UNIQUE",
    "DEFINE INDEX IF NOT EXISTS account_uid ON auth_accounts FIELDS uid UNIQUE",
    "DEFINE TABLE IF NOT EXISTS auth_sessions SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS session_digest ON auth_sessions FIELDS digest UNIQUE",
    "DEFINE INDEX IF NOT EXISTS session_account ON auth_sessions FIELDS account_id",
    "DEFINE TABLE IF NOT EXISTS auth_tokens SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS token_digest ON auth_tokens FIELDS digest UNIQUE",
    "DEFINE TABLE IF NOT EXISTS auth_courses SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS course_uid ON auth_courses FIELDS uid UNIQUE",
    "DEFINE TABLE IF NOT EXISTS auth_memberships SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS membership_pair ON auth_memberships FIELDS account_id, course_id UNIQUE",
    "DEFINE TABLE IF NOT EXISTS auth_personal SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS personal_key ON auth_personal FIELDS account_id, context_id, kind UNIQUE",
    "DEFINE TABLE IF NOT EXISTS auth_events SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS event_limit ON auth_events FIELDS kind, subject, at",
    "DEFINE INDEX IF NOT EXISTS event_age ON auth_events FIELDS at",
    "DEFINE TABLE IF NOT EXISTS auth_config SCHEMALESS",
    "DEFINE INDEX IF NOT EXISTS config_key ON auth_config FIELDS key UNIQUE",
)


def main() -> None:
    url = os.environ["TAGENT_DB_URL"]
    namespace = os.environ.get("TAGENT_DB_NAMESPACE", "tagent")
    database = os.environ.get("TAGENT_DB_DATABASE", "app")
    with Surreal(url) as db:
        db.signin({
            "username": os.environ["TAGENT_DB_ADMIN_USER"],
            "password": os.environ["TAGENT_DB_ADMIN_PASSWORD"],
        })
        db.use(namespace, database)
        for statement in SCHEMA:
            db.query(statement)
    print(f"TAgent identity schema ready in {namespace}/{database}")


if __name__ == "__main__":
    main()
