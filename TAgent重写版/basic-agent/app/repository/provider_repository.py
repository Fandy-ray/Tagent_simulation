"""provider 注册表的持久化：JSON 文件的原子读写、迁移与校验。

repository 层：只管落盘与读取，不认识 Flask、不发上游请求。
校验字段用的是 schema 层的规则，不反向依赖 service。
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.config import DEFAULT_MODEL_PROVIDERS_PATH as DEFAULT_CONFIG_PATH
from app.errors.registry_errors import RegistryLoadError
from app.schema.provider import (
    AUTH_MODES,
    PROVIDER_ID_PATTERN,
    ModelProvider,
    mask_api_key,
    normalize_base_url,
    normalize_extra_body,
    normalize_temperature,
    parse_timestamp,
)
from app.util.timeutil import utc_now


PROVIDER_SCHEMA_VERSION = 2
# 多久看一次文件变没变：每次都 stat 的话，几十个请求同时来时每个都要为这次系统调用放开、再抢回 GIL，
# 实测 50 路连发时 /v1/models 的 P95 有 60 多毫秒。手改了文件最多过这么久生效；自己写的立刻生效
FILE_CHECK_INTERVAL_S = 1.0


class ModelProviderRegistry:
    def __init__(
        self,
        path: str | Path | None = None,
        on_change: Callable[[str | None], None] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        # 路径由 app/container.py 注入（AgentConfig 已解析 MODEL_PROVIDERS_PATH）；
        # 仓储层不自己读环境变量。
        self.path = Path(path or DEFAULT_CONFIG_PATH)
        self._lock = threading.RLock()
        self._on_change = on_change
        # 解析、校验好的文件内容，按（inode, 修改时间, 大小）认：每个答疑请求都要查一次模型，
        # 以前每次都重新打开、解析、逐条校验这个文件，还是在一把全局锁里，50 路并发时排成一队
        self._cached: tuple[tuple[int, int, int], dict[str, Any]] | None = None
        self._clock = clock
        self._checked_at = 0.0

    def list_providers(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._public_provider(item) for item in self._snapshot_unlocked()["providers"]]

    def public_registry(self) -> dict[str, Any]:
        with self._lock:
            return self._public_registry(self._snapshot_unlocked(), include_secrets=False)

    def enabled_providers(self) -> list[ModelProvider]:
        with self._lock:
            data = self._snapshot_unlocked()
            providers = [item for item in data["providers"] if item["enabled"]]
            default_id = data["default_model_id"]
            providers.sort(key=lambda item: item["served_model_id"] != default_id)
            return [self._provider_from_dict(item) for item in providers]

    def get_enabled_provider(self, served_model_id: str | None = None) -> ModelProvider:
        with self._lock:
            data = self._snapshot_unlocked()
            provider_id = served_model_id or data["default_model_id"]
            for provider in data["providers"]:
                if provider["served_model_id"] == provider_id and provider["enabled"]:
                    return self._provider_from_dict(provider)
            raise KeyError(provider_id or "default")

    def get_default_model_id(self) -> str:
        with self._lock:
            return self._snapshot_unlocked()["default_model_id"]

    def create_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            provider = self._normalize_provider(payload, existing=None, from_disk=False)
            if any(item["served_model_id"] == provider["served_model_id"] for item in data["providers"]):
                raise ValueError(f"Model provider already exists: {provider['served_model_id']}")

            data["providers"].append(provider)
            self._repair_default(data)
            self._write_unlocked(data)
            self._notify(provider["served_model_id"])
            return self._public_provider(provider)

    def update_provider(self, served_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            for index, existing in enumerate(data["providers"]):
                if existing["served_model_id"] != served_model_id:
                    continue
                merged = {**existing, **payload, "served_model_id": served_model_id}
                provider = self._normalize_provider(merged, existing=existing, from_disk=False)
                provider["created_at"] = existing["created_at"]
                data["providers"][index] = provider
                self._repair_default(data)
                self._write_unlocked(data)
                self._notify(served_model_id)
                return self._public_provider(provider)
            raise KeyError(served_model_id)

    def delete_provider(self, served_model_id: str) -> None:
        with self._lock:
            data = self._read_unlocked()
            providers = [item for item in data["providers"] if item["served_model_id"] != served_model_id]
            if len(providers) == len(data["providers"]):
                raise KeyError(served_model_id)
            data["providers"] = providers
            self._repair_default(data)
            self._write_unlocked(data)
            self._notify(served_model_id)

    def set_default_model(self, served_model_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            if not any(
                item["served_model_id"] == served_model_id and item["enabled"]
                for item in data["providers"]
            ):
                raise KeyError(served_model_id)
            data["default_model_id"] = served_model_id
            self._write_unlocked(data)
            self._notify(None)
            return self._public_registry(data, include_secrets=False)

    def _read_unlocked(self) -> dict[str, Any]:
        """给要改内容的（增删改、设默认）：一份可以随便改的拷贝。"""
        return copy.deepcopy(self._snapshot_unlocked())

    def _snapshot_unlocked(self) -> dict[str, Any]:
        """当前内容，**只读**：文件没变就是上次解析好的那一份，调用方不许改它。

        手改了文件、或者别的进程写了，修改时间或大小会变，最多 FILE_CHECK_INTERVAL_S 之后重新读；
        自己写的在 _write_unlocked 里直接作废。签名取在读文件之前，读的过程中文件又变了，下一次签名对不上照样会重读。
        """
        now = self._clock()
        if self._cached is not None and now - self._checked_at < FILE_CHECK_INTERVAL_S:
            return self._cached[1]
        self._checked_at = now
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            self._cached = None
            return {"version": PROVIDER_SCHEMA_VERSION, "default_model_id": "", "providers": []}
        signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if self._cached is not None and self._cached[0] == signature:
            return self._cached[1]
        try:
            data = self._load_unlocked()
        except Exception:
            # 文件坏了：不拿上次的好内容顶着（那样一会儿报错一会儿不报），每次都照实报错，和以前一样
            self._cached = None
            raise
        self._cached = (signature, data)
        return data

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": PROVIDER_SCHEMA_VERSION, "default_model_id": "", "providers": []}

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle, parse_constant=_reject_json_constant)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise RegistryLoadError(
                "Model provider configuration is damaged. Restore or remove the local JSON file and restart."
            ) from exc

        if not isinstance(data, dict):
            raise RegistryLoadError("Model provider configuration must be a JSON object.")
        version = data.get("version")
        if version == 1:
            migrated = self._validate_document(self._migrate_v1(data), from_disk=True)
            self._write_unlocked(migrated)
            return migrated
        if version != PROVIDER_SCHEMA_VERSION:
            raise RegistryLoadError(f"Unsupported model provider schema version: {version!r}.")
        return self._validate_document(data, from_disk=True)

    def _validate_document(self, data: dict[str, Any], from_disk: bool) -> dict[str, Any]:
        providers = data.get("providers")
        if not isinstance(providers, list):
            raise RegistryLoadError("Model provider configuration field 'providers' must be a list.")

        normalized = []
        identifiers = set()
        try:
            for item in providers:
                if not isinstance(item, dict):
                    raise ValueError("each provider must be an object")
                provider = self._normalize_provider(item, existing=None, from_disk=from_disk)
                identifier = provider["served_model_id"]
                if identifier in identifiers:
                    raise ValueError(f"duplicate served_model_id: {identifier}")
                identifiers.add(identifier)
                normalized.append(provider)
        except ValueError as exc:
            raise RegistryLoadError(f"Invalid model provider configuration: {exc}") from exc

        default_id = data.get("default_model_id") or ""
        if not isinstance(default_id, str):
            raise RegistryLoadError("default_model_id must be a string.")
        enabled_ids = {
            item["served_model_id"] for item in normalized if item["enabled"]
        }
        if enabled_ids and default_id not in enabled_ids:
            raise RegistryLoadError("default_model_id must reference an enabled provider.")
        if not enabled_ids and default_id:
            raise RegistryLoadError("default_model_id must be empty when no provider is enabled.")

        return {
            "version": PROVIDER_SCHEMA_VERSION,
            "default_model_id": default_id,
            "providers": normalized,
        }

    def _migrate_v1(self, data: dict[str, Any]) -> dict[str, Any]:
        providers = data.get("providers")
        if not isinstance(providers, list):
            raise RegistryLoadError("Cannot migrate schema v1: providers must be a list.")
        migrated = []
        for item in providers:
            if not isinstance(item, dict):
                raise RegistryLoadError("Cannot migrate schema v1: each provider must be an object.")
            migrated.append({**item, "auth_mode": "bearer"})
        result = {
            "version": PROVIDER_SCHEMA_VERSION,
            "default_model_id": data.get("default_model_id") or "",
            "providers": migrated,
        }
        self._repair_default(result)
        return result

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        validated = self._validate_document(data, from_disk=True)
        payload = self._public_registry(validated, include_secrets=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self._cached = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def _normalize_provider(
        self,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
        from_disk: bool,
    ) -> dict[str, Any]:
        now = utc_now()
        name = str(payload.get("name") or "").strip()
        served_model_id = str(payload.get("served_model_id") or "").strip()
        base_url = normalize_base_url(payload.get("base_url"))
        upstream_model = str(payload.get("upstream_model") or payload.get("model") or "").strip()
        auth_mode = str(payload.get("auth_mode") or "bearer").strip().lower()
        temperature = normalize_temperature(payload.get("temperature", 0.1))
        extra_body = normalize_extra_body(payload.get("extra_body"))
        enabled = payload.get("enabled", True)

        if not name:
            raise ValueError("name is required")
        if not PROVIDER_ID_PATTERN.fullmatch(served_model_id):
            raise ValueError("served_model_id contains unsupported characters or has invalid length")
        if not upstream_model:
            raise ValueError("upstream_model is required")
        if auth_mode not in AUTH_MODES:
            raise ValueError("auth_mode must be 'bearer' or 'none'")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")

        submitted_key = payload.get("api_key")
        if auth_mode == "none":
            api_key = ""
        elif submitted_key is None or str(submitted_key) == "":
            if existing and existing.get("auth_mode") == "bearer" and existing.get("api_key"):
                api_key = str(existing["api_key"])
            else:
                raise ValueError("api_key is required when auth_mode is bearer")
        else:
            api_key = str(submitted_key)

        created_at = str(payload.get("created_at") or now)
        updated_at = str(payload.get("updated_at") or now) if from_disk else now
        parse_timestamp(created_at, "created_at")
        parse_timestamp(updated_at, "updated_at")

        return {
            "name": name,
            "served_model_id": served_model_id,
            "base_url": base_url,
            "upstream_model": upstream_model,
            "auth_mode": auth_mode,
            "api_key": api_key,
            "temperature": temperature,
            "enabled": enabled,
            "created_at": created_at,
            "updated_at": updated_at,
            "extra_body": extra_body,
        }

    @staticmethod
    def _repair_default(data: dict[str, Any]) -> None:
        current = data.get("default_model_id") or ""
        enabled = [item["served_model_id"] for item in data.get("providers", []) if item.get("enabled", True)]
        data["default_model_id"] = current if current in enabled else (enabled[0] if enabled else "")

    @staticmethod
    def _provider_from_dict(provider: dict[str, Any]) -> ModelProvider:
        # 附加参数是可变的字典，和缓存里的那份分开，用的人改了也不会带坏缓存
        return ModelProvider(**{**provider, "extra_body": copy.deepcopy(provider.get("extra_body") or {})})

    @staticmethod
    def _public_provider(provider: dict[str, Any], include_secrets: bool = False) -> dict[str, Any]:
        public = {
            key: provider[key]
            for key in (
                "name",
                "served_model_id",
                "base_url",
                "upstream_model",
                "auth_mode",
                "temperature",
                "enabled",
                "created_at",
                "updated_at",
            )
        }
        # 不是密钥，照常给出去，登记页要能看见、改它
        public["extra_body"] = provider.get("extra_body") or {}
        if include_secrets:
            public["api_key"] = provider.get("api_key", "")
        else:
            public["api_key_masked"] = mask_api_key(provider.get("api_key", ""))
            public["has_api_key"] = bool(provider.get("api_key"))
        return public

    def _public_registry(self, data: dict[str, Any], include_secrets: bool) -> dict[str, Any]:
        return {
            "version": PROVIDER_SCHEMA_VERSION,
            "default_model_id": data.get("default_model_id", ""),
            "providers": [
                self._public_provider(provider, include_secrets=include_secrets)
                for provider in data.get("providers", [])
            ],
        }

    def _notify(self, served_model_id: str | None) -> None:
        if self._on_change:
            self._on_change(served_model_id)

def _reject_json_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")

def load_model_registry(
    path: str | Path | None = None,
    on_change: Callable[[str | None], None] | None = None,
) -> ModelProviderRegistry:
    registry = ModelProviderRegistry(path, on_change=on_change)
    if registry.path.exists():
        registry.public_registry()
    return registry
