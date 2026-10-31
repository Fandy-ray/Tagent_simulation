"""模型 provider 的数据结构与字段校验规则。

schema 层：只描述"一个合法的 provider 长什么样"，不做持久化、不发请求。
repository 与 service 都依赖本模块；本模块不依赖任何其他层。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


PROVIDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
AUTH_MODES = {"bearer", "none"}


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    api_key: str
    base_url: str
    model: str
    served_model_id: str
    temperature: float
    auth_mode: str = "bearer"

@dataclass(frozen=True)
class ModelProvider:
    name: str
    served_model_id: str
    base_url: str
    upstream_model: str
    auth_mode: str
    api_key: str
    temperature: float = 0.1
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    # 原样并进每次请求体的厂商参数，见 normalize_extra_body。dict 不可哈希，不参与 hash
    extra_body: dict = field(default_factory=dict, hash=False)
    # 只有出题、批改这类要结构化 JSON 的调用才加的厂商参数，答疑不带，见 structured_bind_kwargs
    structured_extra_body: dict = field(default_factory=dict, hash=False)

    @property
    def as_openai_config(self) -> OpenAICompatibleConfig:
        return OpenAICompatibleConfig(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.upstream_model,
            served_model_id=self.served_model_id,
            temperature=self.temperature,
            auth_mode=self.auth_mode,
        )

def parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed

def normalize_base_url(value: Any) -> str:
    base_url = str(value or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not contain credentials")
    return base_url

def normalize_temperature(value: Any) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature must be a number") from exc
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("temperature must be a finite number between 0 and 2")
    return temperature

# 这些由 TAgent 自己定，不许被附加参数改掉
EXTRA_BODY_RESERVED = frozenset(
    {
        "model",
        "messages",
        "stream",
        "stream_options",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "n",
        "tools",
        "tool_choice",
        "response_format",
    }
)
EXTRA_BODY_MAX_CHARS = 2000


def normalize_extra_body(value: Any, name: str = "extra_body") -> dict:
    """登记模型时可选的「附加参数」：原样并进每次请求体。

    主要用来关闭思考。会先思考的模型把思考也算进输出额度，思考长了正文就被挤没
    （2026-10-07 Windows 测试报告：额度 256 时正文为空）。各家关闭的写法不一样，
    例如 DeepSeek / 智谱 / 豆包是 {"thinking": {"type": "disabled"}}，
    通义千问是 {"enable_thinking": false}，所以不做成开关，照厂商文档填。
    name 是报错里写的字段名：structured_extra_body 走的是同一套规则。
    """
    if value is None or value == "":
        return {}
    if isinstance(value, str):  # 表单和命令行传上来的可能是 JSON 文本
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    reserved = sorted(EXTRA_BODY_RESERVED & set(value))
    if reserved:
        raise ValueError(f"{name} must not set {', '.join(reserved)}")
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain plain JSON values only") from exc
    if len(text) > EXTRA_BODY_MAX_CHARS:
        raise ValueError(f"{name} must be at most {EXTRA_BODY_MAX_CHARS} characters of JSON")
    return json.loads(text)  # 深拷贝：之后谁改了传进来的对象都影响不到这里


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "****"
    return f"****{api_key[-4:]}"
