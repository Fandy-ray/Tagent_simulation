"""注册全部蓝图。"""

from __future__ import annotations

from app.api.notebook import chat, insights, meta, notebooks, notes, search, source_chat, sources


def register_blueprints(app, *, include_root: bool = False) -> None:
    if include_root:
        app.register_blueprint(meta.root_blueprint)
    for module in (meta, notebooks, notes, sources, insights, search, chat, source_chat):
        app.register_blueprint(module.blueprint)
