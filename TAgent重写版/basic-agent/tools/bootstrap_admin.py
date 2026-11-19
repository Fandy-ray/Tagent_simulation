"""交互式创建首位管理员。密码只从终端安全输入，不进入参数、环境或日志。"""

from __future__ import annotations

import getpass
import os
import uuid

from app.auth.service import AuthService, _PASSWORD, now_ms
from app.auth.store import IdentityStore


def main() -> None:
    store = IdentityStore(
        os.environ["TAGENT_DB_URL"], os.environ.get("TAGENT_DB_NAMESPACE", "tagent"),
        os.environ.get("TAGENT_DB_DATABASE", "app"),
        os.environ["TAGENT_DB_USER"], os.environ["TAGENT_DB_PASSWORD"],
    )
    try:
        email = AuthService.email(input("管理员邮箱: "))
        if store.first("SELECT * FROM auth_accounts WHERE email = $email LIMIT 1", {"email": email}):
            raise SystemExit("该邮箱已有账号，未作更改。")
        password = AuthService.password(getpass.getpass("新密码（至少 12 字符）: "))
        if password != getpass.getpass("再次输入新密码: "):
            raise SystemExit("两次输入不一致，未创建。")
        store.query("CREATE auth_accounts CONTENT $value", {"value": {
            "uid": str(uuid.uuid4()), "email": email, "name": "管理员",
            "password_hash": _PASSWORD.hash(password), "role": "admin",
            "active": True, "verified_at": now_ms(), "created_at": now_ms(),
        }})
        print("管理员账号已创建。")
    finally:
        store.close()


if __name__ == "__main__":
    main()
