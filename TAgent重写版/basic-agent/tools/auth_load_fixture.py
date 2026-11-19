"""本机 100/200 人账号压测夹具。只监听回环地址，账号库使用进程内 SurrealDB。"""

from __future__ import annotations

import os
import threading

from cryptography.fernet import Fernet
from surrealdb import Surreal
from waitress import serve

from app.auth.mail import MemoryMailer
from app.auth.personal import PersonalService
from app.auth.service import AuthService, _PASSWORD, now_ms
from app.factory import create_app
from tools.init_auth_db import SCHEMA


class LockedMemoryStore:
    """让 Waitress 线程共享一份内存库；串行查询是本夹具的容量限制。"""

    def __init__(self):
        self.db = Surreal("mem://")
        self.db.connect()
        self.db.use("tagent_load", "accounts")
        self.lock = threading.RLock()

    def query(self, statement, variables=None):
        with self.lock:
            return self.db.query(statement, variables or {})

    def first(self, statement, variables=None):
        result = self.query(statement, variables)
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def close(self):
        self.db.close()


def main():
    store = LockedMemoryStore()
    for statement in SCHEMA:
        store.query(statement)
    password_hash = _PASSWORD.hash("fixture-password-123")
    for index in range(1, 201):
        store.query("CREATE auth_accounts CONTENT $value", {"value": {
            "uid": f"load-{index:03d}", "email": f"load{index:03d}@example.test",
            "name": f"Load {index:03d}", "password_hash": password_hash,
            "role": "student", "active": True, "verified_at": now_ms(),
            "created_at": now_ms(),
        }})
    service = AuthService(store, MemoryMailer(), "http://127.0.0.1:4173", registration_open=False)
    personal = PersonalService(store, Fernet.generate_key().decode())
    app = create_app({
        "TESTING": True, "AUTH_ENABLED": True,
        "AUTH_PUBLIC_ORIGIN": "http://127.0.0.1:4173", "AUTH_COOKIE_SECURE": False,
        "AUTH_STORE": store, "AUTH_SERVICE": service, "PERSONAL_SERVICE": personal,
    })
    print(f"AUTH_LOAD_FIXTURE_READY pid={os.getpid()} port=5009 accounts=200", flush=True)
    try:
        serve(app, host="127.0.0.1", port=5009, threads=64, connection_limit=500)
    finally:
        store.close()


if __name__ == "__main__":
    main()
