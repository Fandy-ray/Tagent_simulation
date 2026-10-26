"""蓝图注册。等价于 Spring Boot 的组件扫描。"""

from __future__ import annotations

from app.api.admin import blueprint as admin_blueprint
from app.api.agent import blueprint as agent_blueprint
from app.api.exam import blueprint as exam_blueprint
from app.api.feedback import blueprint as feedback_blueprint
from app.api.health import blueprint as health_blueprint
from app.api.internal import blueprint as internal_blueprint
from app.api.knowledge import blueprint as knowledge_blueprint
from app.api.knowledge_admin import blueprint as knowledge_admin_blueprint
from app.api.learning_admin import blueprint as learning_admin_blueprint
from app.api.openai_compat import blueprint as openai_blueprint
from app.api.openai_passthrough import blueprint as openai_passthrough_blueprint


def register_blueprints(app) -> None:
    for blueprint in (
        health_blueprint,
        openai_blueprint,
        openai_passthrough_blueprint,
        agent_blueprint,
        exam_blueprint,
        admin_blueprint,
        internal_blueprint,
        knowledge_blueprint,
        knowledge_admin_blueprint,
        learning_admin_blueprint,
        feedback_blueprint,
    ):
        app.register_blueprint(blueprint)
