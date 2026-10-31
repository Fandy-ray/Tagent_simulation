from flask import Blueprint, Response, jsonify

from app.errors.api_errors import AgentAPIError
from app.api.deps import get_registry, invalidate_provider, select_provider
from app.api.security import require_admin_token
from app.api.validators import json_body
from app.infra import passthrough_client


blueprint = Blueprint("admin", __name__, url_prefix="/admin/model-providers")


@blueprint.get("")
def list_providers():
    require_admin_token()
    return jsonify(get_registry().public_registry())


@blueprint.post("")
def create_provider():
    require_admin_token()
    try:
        provider = get_registry().create_provider(json_body())
    except ValueError as exc:
        raise AgentAPIError(str(exc), 400, "validation_error") from exc
    invalidate_provider(provider["served_model_id"])
    return jsonify(provider), 201


@blueprint.put("/<string:served_model_id>")
def update_provider(served_model_id: str):
    require_admin_token()
    try:
        provider = get_registry().update_provider(served_model_id, json_body())
    except KeyError as exc:
        raise AgentAPIError("Model provider not found.", 404, "model_not_found") from exc
    except ValueError as exc:
        raise AgentAPIError(str(exc), 400, "validation_error") from exc
    invalidate_provider(served_model_id)
    return jsonify(provider)


@blueprint.delete("/<string:served_model_id>")
def delete_provider(served_model_id: str):
    require_admin_token()
    try:
        get_registry().delete_provider(served_model_id)
    except KeyError as exc:
        raise AgentAPIError("Model provider not found.", 404, "model_not_found") from exc
    invalidate_provider(served_model_id)
    return jsonify({"status": True, "default_model_id": get_registry().get_default_model_id()})


@blueprint.post("/default")
def set_default_provider():
    require_admin_token()
    data = json_body()
    served_model_id = data.get("served_model_id")
    if not isinstance(served_model_id, str) or not served_model_id:
        raise AgentAPIError("served_model_id is required.", 400, "validation_error")
    try:
        result = get_registry().set_default_model(served_model_id)
    except KeyError as exc:
        raise AgentAPIError("Model provider not found or disabled.", 404, "model_not_found") from exc
    return jsonify(result)


# 登记页的「测试连接」：真发一句很短的话，看 Key、地址、模型名是不是都对。
# 以前走 /v1/raw，那条通道现在不经前端端口开放了（见 openai_passthrough），所以搬到这里、
# 要管理口令。只发这一句固定的话，调用方塞什么字段都不转——这里不是通用转发。
PROBE_MESSAGES = [{"role": "user", "content": "只回复一个字：好"}]
# 能连上的思考模型，额度给少了会把正文挤没；64 个 token 足够回一个字
PROBE_MAX_TOKENS = 64
# 回一个字用不了这么久；前端那边 60 秒就放弃了
PROBE_TIMEOUT_SECONDS = 50.0
# 回的是上游的原话时带上这个头。上游也会回 403、404，错误码也可能叫 model_not_found，
# 前端靠这个头分清「上游拒了 Key」和「这边的管理口令不对 / 模型没登记」
UPSTREAM_RELAY_HEADER = "X-Tagent-Upstream"


@blueprint.post("/<string:served_model_id>/probe")
def probe_provider(served_model_id: str):
    """原样回上游的状态码和响应体（带 UPSTREAM_RELAY_HEADER），和 /v1/raw/chat/completions 一个样子。"""
    require_admin_token()
    provider = select_provider(served_model_id)
    # 带上出题批改用的那份参数：它写错了上游会拒，「试一下」这里就能看出来，不用等到学生出卷失败
    status, body, content_type = passthrough_client.complete(
        {
            "model": served_model_id,
            "messages": PROBE_MESSAGES,
            "max_tokens": PROBE_MAX_TOKENS,
            **provider.structured_extra_body,
        },
        provider,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    return Response(body, status=status, content_type=content_type, headers={UPSTREAM_RELAY_HEADER: "1"})
