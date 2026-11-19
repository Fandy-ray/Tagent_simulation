"""运维人员核验身份后，在服务器终端交互式重置学生密码。"""

from __future__ import annotations

import getpass
import os
import secrets

from app.auth.mail import DisabledMailer
from app.auth.service import AuthService
from app.auth.store import IdentityStore


def reset_student(store: IdentityStore, email: str, password: str) -> None:
    email = AuthService.email(email)
    password = AuthService.password(password)
    account = store.first("SELECT * FROM auth_accounts WHERE email = $email LIMIT 1",
                          {"email": email})
    if not account or account.get("role") != "student" or not account.get("active", True):
        raise ValueError("找不到可重置的学生账号")
    service = AuthService(store, DisabledMailer(), "")
    store.query("UPDATE auth_accounts SET password_hash = $hash, auth_nonce = $nonce WHERE uid = $uid",
                {"hash": service._hash(password), "nonce": secrets.token_urlsafe(16),
                 "uid": account["uid"]})
    service.revoke_all(account["uid"])


def main() -> None:
    store = IdentityStore(
        os.environ["TAGENT_DB_URL"], os.environ.get("TAGENT_DB_NAMESPACE", "tagent"),
        os.environ.get("TAGENT_DB_DATABASE", "app"),
        os.environ["TAGENT_DB_USER"], os.environ["TAGENT_DB_PASSWORD"],
    )
    try:
        email = AuthService.email(input("学生邮箱: "))
        password = AuthService.password(getpass.getpass("新密码（至少 12 字符）: "))
        if password != getpass.getpass("再次输入新密码: "):
            raise SystemExit("两次输入不一致，未重置。")
        reset_student(store, email, password)
        print("密码已重置，原有登录会话已全部退出。")
    finally:
        store.close()


if __name__ == "__main__":
    main()
