import threading

import httpx
from langchain_openai import ChatOpenAI

from app.config import UPSTREAM_CONNECT_TIMEOUT
from app.infra.upstream_http import async_client, sync_client
from app.schema.provider import ModelProvider


def _remove_authorization(request: httpx.Request) -> None:
    if "Authorization" in request.headers:
        del request.headers["Authorization"]


async def _remove_authorization_async(request: httpx.Request) -> None:
    _remove_authorization(request)


class ModelClientFactory:
    def __init__(self, timeout_seconds: float = 180, max_retries: int = 1):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._lock = threading.RLock()
        self._clients: dict[tuple[str, str, float, int], ChatOpenAI] = {}
        self._http_clients: dict[tuple[str, str, float, int], httpx.Client] = {}

    def get(
        self,
        provider: ModelProvider,
        *,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> ChatOpenAI:
        request_timeout = timeout_seconds or self.timeout_seconds
        request_retries = self.max_retries if max_retries is None else max_retries
        key = (provider.served_model_id, provider.updated_at, request_timeout, request_retries)
        with self._lock:
            cached = self._clients.get(key)
            if cached is not None:
                return cached

            # 只换掉这个模型「配置已经改过」的旧客户端（登记信息的 updated_at 变了）。
            # 以前这里把这个模型的所有客户端都关掉。可缓存键里有超时和重试次数，答疑、出卷、
            # 判卷、闪卡各要各的，于是互相踢：谁新建一个，正在用别的客户端的请求就被关了连接。
            # 答疑是同步流式读的，连接一关就卡住不动、也不报错（2026-10-25 本地假上游复现：
            # 收到 4/10 个字后一直等）——有人出卷或交卷时，别的同学正在出的回答会卡死。
            self._drop_stale_unlocked(provider)
            no_auth = provider.auth_mode == "none"
            hooks = {"request": [_remove_authorization]} if no_auth else None
            async_hooks = {"request": [_remove_authorization_async]} if no_auth else None
            # 读超时照旧（生成慢是正常的）；握手单独 UPSTREAM_CONNECT_TIMEOUT 秒，
            # 断网丢包时不必等满整段读超时才发现连不上
            timeout = httpx.Timeout(
                request_timeout, connect=min(UPSTREAM_CONNECT_TIMEOUT, request_timeout)
            )
            # 同步、异步两个客户端都要自己建：出题判卷走的是 ainvoke，以前只给了同步的，
            # 异步那边由 SDK 自建、跟着环境变量走代理（见 app/infra/upstream_http.py）
            http_client = sync_client(provider.base_url, timeout=timeout, event_hooks=hooks)
            http_async_client = async_client(
                provider.base_url, timeout=timeout, event_hooks=async_hooks
            )
            client = ChatOpenAI(
                model=provider.upstream_model,
                base_url=provider.base_url,
                api_key=provider.api_key if provider.auth_mode == "bearer" else "local-no-auth",
                temperature=provider.temperature,
                timeout=timeout,
                max_retries=request_retries,
                http_client=http_client,
                # 异步客户端绑在第一次用它的事件循环上（llm_json 的常驻循环）。换模型时
                # 只丢引用、不在这里关：关它得回到那个循环里 await，换模型又很少见。
                http_async_client=http_async_client,
                # 登记时填的厂商参数（例如关闭思考），没填就不发
                extra_body=provider.extra_body or None,
            )
            self._http_clients[key] = http_client
            self._clients[key] = client
            return client

    def invalidate(self, served_model_id: str | None = None) -> None:
        with self._lock:
            if served_model_id is None:
                keys = list(self._clients)
                for model_id, _updated_at, _timeout, _retries in keys:
                    self._invalidate_unlocked(model_id)
            else:
                self._invalidate_unlocked(served_model_id)

    def close(self) -> None:
        self.invalidate(None)

    def _drop_stale_unlocked(self, provider: ModelProvider) -> None:
        stale = [
            key for key in self._clients
            if key[0] == provider.served_model_id and key[1] != provider.updated_at
        ]
        for key in stale:
            self._clients.pop(key, None)
            http_client = self._http_clients.pop(key, None)
            if http_client is not None:
                http_client.close()

    def _invalidate_unlocked(self, served_model_id: str) -> None:
        keys = [key for key in self._clients if key[0] == served_model_id]
        for key in keys:
            self._clients.pop(key, None)
            http_client = self._http_clients.pop(key, None)
            if http_client is not None:
                http_client.close()


# ====================== 每次请求的可调参数 ======================
#
# 客户端是按 (模型, 超时, 重试) 缓存的，每次请求的参数**不能**进缓存键——
# 那等于每换一次温度就新建一个带连接池的 client。正确做法是在缓存好的
# client 上 .bind()，langchain 会把它们并进这一次调用的请求体。

# 只认模型真正支持的这几项。前端面板上多出来的开关一律不接——
# 与其让学生调一个没效果的滑块，不如不给。
TUNABLE = ("temperature", "top_p", "max_tokens")


def tuning_bind_kwargs(provider, tuning: dict | None) -> dict:
    """把可调参数翻译成 .bind() 的入参。没有可调项时返回空 dict。

    max_tokens 要特别处理：langchain 的 ChatOpenAI 会把它改名成
    max_completion_tokens 发出去，而 DeepSeek 只认 max_tokens，改了名就等于没传。
    所以它必须塞进 extra_body 原样透传。

    而 extra_body 又是**合并**不是覆盖：登记模型时填的厂商参数（例如关闭思考）
    也在里面，直接 bind 一个新的会把它整个冲掉。
    """
    if not tuning:
        return {}

    kwargs: dict = {}
    for name in ("temperature", "top_p"):
        value = tuning.get(name)
        if value is not None:
            kwargs[name] = value

    max_tokens = tuning.get("max_tokens")
    if max_tokens is not None:
        merged = dict(provider.extra_body or {})
        merged["max_tokens"] = max_tokens
        kwargs["extra_body"] = merged

    return kwargs
