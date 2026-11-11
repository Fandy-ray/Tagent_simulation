"""模型客户端：只认 OpenAI 兼容的 /chat/completions。

原版用 esperanto 抽象了 24 家供应商，可实际部署里模型全是 tagent 的 /v1/raw 转发过来的，
所以这里直接默认指向 tagent（http://127.0.0.1:5001/v1/raw），换别家也只要改 ON_LLM_BASE_URL。
"""

from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from app.errors.notebook import UpstreamFailure

log = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
# 上游偶发的网关错误、限流、连不上：重试（原版走 LangChain 的 OpenAI 客户端，默认也重试 2 次）。
# 实测 tagent 到 DeepSeek 的 TLS 连接时好时坏，问答的第四次调用经常碰上一次 502，重试一次就过。
RETRY_STATUS = {429, 500, 502, 503, 504}


def strip_thinking(text: str) -> str:
    return _THINK.sub("", text or "").strip()


class LLMClient:
    def __init__(self, base_url: str, *, api_key: str = "", model: str = "", timeout: float = 180.0,
                 retries: int = 2, backoff: float = 1.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._transport = transport  # 测试用
        host = (urlsplit(self.base_url).hostname or "").lower()
        # 本机地址别走系统代理（本机常年开着 17897 代理，localhost 走代理会被它拒掉）
        self._trust_env = host not in _LOOPBACK

    @property
    def display_name(self) -> str:
        return self.model or "tagent 默认模型"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _body(self, messages: list[dict], *, temperature: float, max_tokens: int | None) -> dict:
        body: dict = {"messages": messages, "temperature": temperature, "stream": False}
        if self.model:
            body["model"] = self.model
        if max_tokens:
            body["max_tokens"] = max_tokens
        return body

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, trust_env=self._trust_env, transport=self._transport)

    def _post(self, body: dict) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"
        for attempt in range(self.retries + 1):
            last = attempt == self.retries
            try:
                with self._client() as client:
                    response = client.post(url, headers=self._headers(), json=body)
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                if last:
                    log.warning("模型服务连不上：%s", exc)
                    raise UpstreamFailure(
                        f"模型服务连不上（{self.base_url}），请确认 tagent 后端在运行或检查 ON_LLM_BASE_URL。"
                    ) from exc
            except httpx.HTTPError as exc:  # 超时等：再等一轮多半也超时，不重试
                log.warning("模型服务调用失败：%s", exc)
                raise UpstreamFailure(f"模型服务调用失败（{type(exc).__name__}），请稍后重试。") from exc
            else:
                if response.status_code not in RETRY_STATUS or last:
                    return response
                log.info("模型服务返回 %s，%.0f 秒后重试", response.status_code, self.backoff * (attempt + 1))
            time.sleep(self.backoff * (attempt + 1))
        raise UpstreamFailure("模型服务调用失败")  # 走不到这里，给类型检查看

    def complete(self, messages: list[dict], *, temperature: float = 0.3, max_tokens: int | None = None) -> str:
        response = self._post(self._body(messages, temperature=temperature, max_tokens=max_tokens))
        if response.status_code >= 400:
            raise UpstreamFailure(f"模型服务返回 {response.status_code}：{_error_text(response)}")
        try:
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise UpstreamFailure("模型服务的返回格式不对（不是 OpenAI 兼容格式）。") from exc
        text = strip_thinking(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        if not text:
            raise UpstreamFailure("模型没有返回内容。")
        return text


class RegistryLLM(LLMClient):
    """直接用 tagent 已经登记的模型。默认地址是本机 5001，同进程再 HTTP 打回去会占死工作线程。"""

    def __init__(self, registry, client_factory, *, model: str = ""):
        super().__init__("http://127.0.0.1/v1")
        self._registry = registry
        self._factory = client_factory
        self.model = model

    def complete(self, messages, *, temperature: float = 0.3, max_tokens: int | None = None) -> str:
        try:
            provider = self._registry.get_enabled_provider(self.model or None)
        except KeyError as exc:
            raise UpstreamFailure("还没有登记模型。请先在 tagent 的模型页登记一个。") from exc
        client = self._factory.get(provider)
        kwargs: dict = {"temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        try:
            result = client.bind(**kwargs).invoke(_langchain_messages(messages))
        except Exception as exc:
            raise UpstreamFailure(f"模型调用失败：{exc}") from exc
        from app.util.text import content_text

        text = strip_thinking(content_text(getattr(result, "content", result)))
        if not text:
            raise UpstreamFailure("模型没有返回内容。")
        return text


def _langchain_messages(messages: list[dict]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    converted = []
    for item in messages:
        content = item.get("content") or ""
        role = item.get("role")
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return (response.text or "")[:200]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:200]
        if data.get("detail"):
            return str(data["detail"])[:200]
    return str(data)[:200]
