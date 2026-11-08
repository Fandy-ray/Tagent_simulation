"""已登录账号的个人数据、课程与管理员操作。"""

from __future__ import annotations

import uuid

from flask import Blueprint, current_app, g, jsonify, make_response, request

from app.api.deps import get_learning_store, get_registry
from app.auth.service import public_account
from app.errors.api_errors import AgentAPIError


blueprint = Blueprint("identity", __name__)


def _services():
    if not current_app.config.get("AUTH_ENABLED"):
        raise AgentAPIError("账号服务尚未启用。", 503, "auth_unavailable")
    return current_app.extensions["auth_service"], current_app.extensions["personal_service"]


def _admin():
    if getattr(g, "account", {}).get("role") != "admin":
        raise AgentAPIError("需要管理员账号。", 403, "admin_required")


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AgentAPIError("请求应为 JSON 对象。", 400, "invalid_json")
    return data


def _course(row: dict) -> dict:
    return {
        "id": row["uid"], "name": row["name"], "description": row.get("description", ""),
        "model_ids": row.get("model_ids", []), "notebook_ids": row.get("notebook_ids", []),
        "active": row.get("active", True),
    }


@blueprint.get("/me/courses")
def my_courses():
    service, _ = _services()
    return jsonify({"courses": [_course(row) for row in service.courses_for(g.account)]})


@blueprint.get("/me/data/<string:kind>")
def get_personal(kind: str):
    _, personal = _services()
    course_id = g.course["uid"] if g.course else None
    return jsonify(personal.get(g.account["uid"], kind, course_id))


@blueprint.put("/me/data/<string:kind>")
def put_personal(kind: str):
    _, personal = _services()
    body = _json()
    course_id = g.course["uid"] if g.course else None
    return jsonify(personal.put(g.account["uid"], kind, body.get("data"),
                                body.get("version"), course_id))


@blueprint.get("/me/export")
def export_personal():
    _, personal = _services()
    payload = {"account": public_account(g.account), **personal.export(g.account["uid"])}
    learning_store = get_learning_store()
    if learning_store is not None:
        payload["learning_records"] = learning_store.export_student(g.account["uid"])
    response = make_response(jsonify(payload))
    response.headers["Content-Disposition"] = 'attachment; filename="tagent-personal-data.json"'
    response.headers["Cache-Control"] = "no-store"
    return response


@blueprint.delete("/me/account")
def delete_account():
    service, personal = _services()
    service.delete_account(g.account, _json().get("password"), personal, get_learning_store())
    response = make_response(jsonify({"deleted": True}))
    response.delete_cookie(current_app.config["AUTH_COOKIE_NAME"], path="/")
    return response


@blueprint.get("/admin/accounts")
def list_accounts():
    _admin()
    service, _ = _services()
    rows = service.store.query(
        "SELECT uid, email, name, role, active, deletion_pending, verified_at, created_at "
        "FROM auth_accounts ORDER BY created_at DESC LIMIT 1000"
    ) or []
    return jsonify({"accounts": [public_account(row) for row in rows]})


@blueprint.patch("/admin/accounts/<string:uid>")
def set_account_state(uid: str):
    _admin()
    service, _ = _services()
    body = _json()
    if type(body.get("active")) is not bool:
        raise AgentAPIError("active 必须是布尔值。", 400, "validation_error")
    account = service.account(uid)
    if not account:
        raise AgentAPIError("账号不存在。", 404, "account_not_found")
    if account["role"] == "admin" and not body["active"]:
        raise AgentAPIError("不能通过网页停用管理员。", 403, "admin_protected")
    if account.get("deletion_pending"):
        raise AgentAPIError("待注销账号只能完成清理，不能重新启用。", 409, "deletion_pending")
    service.store.query(
        "UPDATE auth_accounts SET active = $active WHERE uid = $uid",
        {"active": body["active"], "uid": uid},
    )
    if not body["active"]:
        service.revoke_all(uid)
    return jsonify({"account": public_account(service.account(uid))})


@blueprint.post("/admin/accounts/<string:uid>/complete-deletion")
def complete_account_deletion(uid: str):
    _admin()
    service, personal = _services()
    service.complete_deletion(uid, personal, get_learning_store())
    return jsonify({"deleted": True})


@blueprint.route("/admin/registration", methods=["GET", "PUT"])
def registration_state():
    _admin()
    service, _ = _services()
    if request.method == "PUT":
        body = _json()
        if type(body.get("open")) is not bool:
            raise AgentAPIError("open 必须是布尔值。", 400, "validation_error")
        service.set_registration_open(body["open"])
    return jsonify({"open": service.registration_is_open()})


@blueprint.get("/admin/courses")
def list_courses():
    _admin()
    service, _ = _services()
    rows = service.store.query("SELECT * FROM auth_courses ORDER BY name") or []
    return jsonify({"courses": [_course(row) for row in rows]})


def _course_payload(data: dict) -> dict:
    name = data.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise AgentAPIError("课程名称长度应为 1～120 字符。", 400, "validation_error")
    result = {"name": name.strip(), "description": str(data.get("description", ""))[:500]}
    for field in ("model_ids", "notebook_ids"):
        value = data.get(field, [])
        if not isinstance(value, list) or len(value) > 100 or any(
            not isinstance(item, str) or not 1 <= len(item) <= 200 for item in value
        ):
            raise AgentAPIError(f"{field} 无效。", 400, "validation_error")
        result[field] = list(dict.fromkeys(value))
    available = {provider.served_model_id for provider in get_registry().enabled_providers()}
    if not set(result["model_ids"]).issubset(available):
        raise AgentAPIError("课程包含未启用的模型。", 400, "invalid_model")
    return result


@blueprint.post("/admin/courses")
def create_course():
    _admin()
    service, _ = _services()
    data = _course_payload(_json())
    data.update({"uid": str(uuid.uuid4()), "active": True})
    service.store.query("CREATE auth_courses CONTENT $value", {"value": data})
    return jsonify({"course": _course(data)}), 201


@blueprint.put("/admin/courses/<string:uid>")
def update_course(uid: str):
    _admin()
    service, _ = _services()
    if not service.course(uid):
        raise AgentAPIError("课程不存在。", 404, "course_not_found")
    data = _course_payload(_json())
    service.store.query(
        "UPDATE auth_courses MERGE $value WHERE uid = $uid",
        {"value": data, "uid": uid},
    )
    return jsonify({"course": _course(service.course(uid))})


@blueprint.patch("/admin/courses/<string:uid>/state")
def set_course_state(uid: str):
    _admin()
    service, _ = _services()
    body = _json()
    if type(body.get("active")) is not bool:
        raise AgentAPIError("active 必须是布尔值。", 400, "validation_error")
    row = service.store.first("SELECT * FROM auth_courses WHERE uid = $uid LIMIT 1", {"uid": uid})
    if not row:
        raise AgentAPIError("课程不存在。", 404, "course_not_found")
    service.store.query("UPDATE auth_courses SET active = $active WHERE uid = $uid",
                        {"active": body["active"], "uid": uid})
    updated = service.store.first("SELECT * FROM auth_courses WHERE uid = $uid LIMIT 1", {"uid": uid})
    return jsonify({"course": _course(updated)})


@blueprint.get("/admin/courses/<string:uid>/members")
def list_members(uid: str):
    _admin()
    service, _ = _services()
    if not service.course(uid):
        raise AgentAPIError("课程不存在。", 404, "course_not_found")
    rows = service.store.query(
        "SELECT account_id FROM auth_memberships WHERE course_id = $uid", {"uid": uid}
    ) or []
    members = [public_account(row) for item in rows
               if (row := service.account(item["account_id"])) is not None]
    return jsonify({"members": members})


@blueprint.get("/admin/courses/<string:uid>/summary")
def course_summary(uid: str):
    _admin()
    service, _ = _services()
    if not service.course(uid):
        raise AgentAPIError("课程不存在。", 404, "course_not_found")
    store = get_learning_store()
    if store is None:
        raise AgentAPIError("学习记录库暂不可用。", 503, "learning_store_unavailable")
    members = service.store.query(
        "SELECT account_id FROM auth_memberships WHERE course_id = $uid", {"uid": uid}
    ) or []
    return jsonify(store.course_summary(uid, [row["account_id"] for row in members]))


@blueprint.post("/admin/courses/<string:uid>/members")
def add_member(uid: str):
    _admin()
    service, _ = _services()
    if not service.course(uid):
        raise AgentAPIError("课程不存在。", 404, "course_not_found")
    email = service.email(_json().get("email"))
    account = service._account_for_email(email)
    if not account or account.get("role") != "student" or not account.get("verified_at"):
        raise AgentAPIError("找不到已验证的账号。", 404, "account_not_found")
    if not service.is_member(account["uid"], uid):
        service.store.query(
            "CREATE auth_memberships CONTENT $value",
            {"value": {"account_id": account["uid"], "course_id": uid}},
        )
    return jsonify({"member": public_account(account)})


@blueprint.delete("/admin/courses/<string:uid>/members/<string:account_id>")
def remove_member(uid: str, account_id: str):
    _admin()
    service, _ = _services()
    service.store.query(
        "DELETE auth_memberships WHERE course_id = $course AND account_id = $account",
        {"course": uid, "account": account_id},
    )
    return jsonify({"removed": True})
