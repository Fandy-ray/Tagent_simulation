"""把请求原样转发给上游 OpenAI 兼容接口。

与 openai_view 的分工：

    /v1/chat/completions      TAgent 自己的 RAG 答疑，会把检索到的课程内容注入 prompt
    /v1/raw/chat/completions  本模块，什么都不加，原样转发

OpenNotebook 做摘要、来源转换、播客脚本时要的正是后者 —— 它自己已经把待处理的
文本放进 prompt 了，再被塞一份系统仿真教材进去只会让输出跑偏。有了这条通道，
DeepSeek 的 Key 只需要在 basic-agent 登记一次，OpenNotebook 指过来即可。

直接用 httpx 而不复用 ModelClientFactory：那边返回的是 LangChain 的 ChatOpenAI，
只认它自己那套参数；透传要能带上 tools、response_format 这类任意字段，
并把上游的 SSE 字节原封不动传回去。
"""

from __future__ import annotations

import httpx

from app.errors.api_errors import AgentAPIError
from app.infra.upstream_http import sync_client
from app.schema.provider import ModelProvider


DEFAULT_TIMEOUT_SECONDS = 180.0

# TAgent 自己的扩展字段，上游 OpenAI 接口不认识，转发前必须摘掉
TAGENT_ONLY_FIELDS = ("notebook_ids",)


def build_headers(provider: ModelProvider) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider.auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {provider.api_key}"
    return headers


def build_payload(data: dict, provider: ModelProvider) -> dict:
    """客户端报的是 served_model_id（deepseek），上游认的是 upstream_model（deepseek-chat）。"""
    payload = {key: value for key, value in data.items() if key not in TAGENT_ONLY_FIELDS}
    payload["model"] = provider.upstream_model
    # 登记时填的厂商参数（例如关闭思考）也带上；调用方自己写了同名字段的，听调用方的
    for key, value in provider.extra_body.items():
        payload.setdefault(key, value)
    return payload


def translate_transport_error(error: Exception) -> AgentAPIError:
    """只翻译"没连上"这类传输层故障。

    上游真的答复了（哪怕是 401/429），一律原样透传状态码和响应体 ——
    透传通道谎报上游的错误只会让 OpenNotebook 那头更难排查。
    """
    if isinstance(error, httpx.TimeoutException):
        return AgentAPIError("The selected provider timed out.", 504, "upstream_timeout")
    if isinstance(error, httpx.ConnectError):
        detail = str(error).upper()
        if "CERTIFICATE" in detail or "SSL" in detail:
            return AgentAPIError(
                "无法校验上游的 HTTPS 证书，网络可能被拦截或需要代理。",
                502,
                "upstream_unavailable",
            )
        return AgentAPIError("The selected provider is unavailable.", 502, "upstream_unavailable")
    return AgentAPIError("The selected provider request failed.", 502, "upstream_error")


def _open_client(provider: ModelProvider, timeout: float) -> httpx.Client:
    # 和 ModelClientFactory 同一套：本机直连；配了代理时先直连、连不上再走代理
    return sync_client(provider.base_url, timeout=timeout)


def _endpoint(provider: ModelProvider) -> str:
    return f"{provider.base_url}/chat/completions"


def complete(
    data: dict,
    provider: ModelProvider,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, bytes, str]:
    """非流式转发。返回 (状态码, 原始响应体, content-type)。"""
    payload = build_payload(data, provider)
    try:
        with _open_client(provider, timeout) as client:
            response = client.post(
                _endpoint(provider),
                json=payload,
                headers=build_headers(provider),
            )
    except httpx.HTTPError as exc:
        raise translate_transport_error(exc) from exc

    content_type = response.headers.get("content-type", "application/json")
    return response.status_code, response.content, content_type


def stream(
    data: dict,
    provider: ModelProvider,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
):
    """流式转发，逐块 yield 上游的原始字节。

    生成器在被消费时才真正发起请求，所以 httpx 的 Client 与 stream 都放在
    生成器内部用 with 管理：调用方提前 close（浏览器断连）时一并释放。
    """
    payload = build_payload(data, provider)
    payload["stream"] = True

    def generate():
        try:
            with _open_client(provider, timeout) as client:
                with client.stream(
                    "POST",
                    _endpoint(provider),
                    json=payload,
                    headers=build_headers(provider),
                ) as response:
                    if response.status_code >= 400:
                        # 上游在开流前就拒了。此时响应头还没发给客户端，
                        # 读完错误体抛出去，由 error_handler 转成正常的 JSON 错误。
                        response.read()
                        raise AgentAPIError(
                            _upstream_message(response),
                            response.status_code,
                            "upstream_error",
                        )
                    # HTTPX decodes Content-Encoding here; SSE clients do not receive
                    # the upstream gzip header, so forwarding compressed bytes breaks them.
                    # https://www.python-httpx.org/quickstart/#streaming-responses
                    for chunk in response.iter_bytes():
                        if chunk:
                            yield chunk
        except AgentAPIError:
            raise
        except httpx.HTTPError as exc:
            raise translate_transport_error(exc) from exc

    return generate()


def _upstream_message(response: httpx.Response) -> str:
    """尽量把上游的错误描述透出来，取不到就退回一句通用的。"""
    try:
        body = response.json()
    except ValueError:
        return "The selected provider rejected the request."
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(body.get("message"), str):
            return body["message"]
    return "The selected provider rejected the request."
