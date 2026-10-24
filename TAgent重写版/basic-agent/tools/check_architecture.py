"""分层架构守卫。纯标准库，无需额外依赖。

用法（工作目录 basic-agent/）：

    python -m tools.check_architecture

tests/test_architecture.py 也会跑它：违规时测试直接红，不用等谁想起来手动跑。

检查项：
  1. 未定义的名字——引用了但既没定义、没 import、也不是内置
     （抽取式重构最容易漏的就是"函数搬走了、它依赖的 import 没跟着搬"，
       这种问题只在跑到那一行时才炸，测试未必覆盖得到）
  2. 未使用的 import（1、2 两项也查测试文件）
  3. 分层依赖方向（见 docs/basic-agent-layering-plan.md §9）
  4. 配置收口：os.getenv 只允许出现在 app/config.py
  5. Flask 只允许出现在 app/api/ 与 app/factory.py
  6. controller（app/api 里定义了 blueprint 的模块）之间不得互相 import
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys


BASE = pathlib.Path(__file__).resolve().parents[1]  # basic-agent/
APP = BASE / "app"

# 层 -> 禁止 import 的层。app.agent（流程图与共用节点）在 service 之下、
# infra / rag / schema / prompts 之上：service 调它，它不能反过来碰 service、api、repository。
FORBIDDEN = {
    "app.repository": ("app.service", "app.api", "app.infra", "app.agent"),
    "app.schema": ("app.service", "app.api", "app.repository", "app.infra", "app.agent"),
    "app.util": ("app.service", "app.api", "app.repository", "app.infra", "app.schema", "app.agent"),
    "app.errors": ("app.service", "app.api", "app.repository", "app.infra", "app.schema", "app.agent"),
    "app.infra": ("app.service", "app.api", "app.repository", "app.agent"),
    "app.prompts": ("app.service", "app.api", "app.repository", "app.infra", "app.agent"),
    "app.agent": ("app.service", "app.api", "app.repository"),
    "app.service": ("app.api",),
    "app.rag": ("app.service", "app.api", "app.repository", "app.agent"),
    "app.api": ("app.repository",),
}


def is_controller(path: pathlib.Path, text: str) -> bool:
    """定义了 blueprint 的 api 模块就是 controller。以前是手写名单，新加的几个都漏了。"""
    return path.parent.name == "api" and "blueprint = Blueprint(" in text


def test_files() -> list[pathlib.Path]:
    """测试文件：tests/ 下的，加上根目录的 test_*.py 和 conftest.py。"""
    found = [p for p in (BASE / "tests").rglob("*.py") if "__pycache__" not in p.parts]
    found += list(BASE.glob("test_*.py")) + list(BASE.glob("conftest.py"))
    return sorted(found)


def module_name(path: pathlib.Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def layer_of(mod: str) -> str | None:
    parts = mod.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else None


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.append((n.module, n.lineno))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((a.name, n.lineno))
    return out


def bound_names(tree: ast.AST) -> set[str]:
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                bound.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
    return bound


def used_names(tree: ast.AST) -> set[str]:
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            root = n
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used.add(root.id)
    return used


def import_bindings(tree: ast.AST) -> list[tuple[str, int]]:
    """(本模块可见的名字, 行号)，用于未使用检测。"""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.append(((a.asname or a.name).split(".")[0], n.lineno))
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name == "*":
                    continue
                out.append((a.asname or a.name, n.lineno))
    return out


def name_problems(tree: ast.AST, path: pathlib.Path, rel: str) -> list[str]:
    """第 1、2 项：未定义的名字、未使用的 import。"""
    problems: list[str] = []

    # 1. 未定义的名字
    missing = used_names(tree) - bound_names(tree) - set(dir(builtins)) - {
        "__name__", "__file__", "__doc__",
    }
    for name in sorted(missing):
        problems.append(f"{rel}: 未定义的名字 `{name}`")

    # 2. 未使用的 import（__init__.py 的重导出除外）
    if path.name != "__init__.py":
        # 字符串形式的类型注解也算使用（如 dataclass 里的 "ExamCache"）
        annotated = {
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        text_names = used_names(tree) | annotated
        for name, lineno in import_bindings(tree):
            if name == "annotations":
                continue
            if name not in text_names:
                problems.append(f"{rel}:{lineno}: 未使用的 import `{name}`")
    return problems


def check() -> tuple[list[str], int]:
    """(问题清单, 查过的文件数)。"""
    problems: list[str] = []
    files = sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)

    for path in files:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        rel = path.relative_to(BASE).as_posix()
        mod = module_name(path.relative_to(BASE))
        layer = layer_of(mod)
        problems += name_problems(tree, path, rel)

        # 3. 分层方向
        for imported, lineno in imported_modules(tree):
            for bad in FORBIDDEN.get(layer, ()):
                if imported == bad or imported.startswith(bad + "."):
                    problems.append(
                        f"{rel}:{lineno}: {layer} 不得依赖 {bad}（import {imported}）"
                    )

        # 4. 配置收口
        if rel != "app/config.py" and ("os.getenv" in text or "os.environ" in text):
            problems.append(f"{rel}: os.getenv/os.environ 只允许出现在 app/config.py")

        # 5. Flask 边界
        if not (rel.startswith("app/api/") or rel == "app/factory.py"):
            for imported, lineno in imported_modules(tree):
                if imported == "flask" or imported.startswith("flask."):
                    problems.append(f"{rel}:{lineno}: 只有 api 层与启动类可以 import flask")

        # 6. controller 互调
        if is_controller(path, text):
            for imported, lineno in imported_modules(tree):
                if imported.startswith("app.api."):
                    target = APP / "api" / f"{imported.rsplit('.', 1)[-1]}.py"
                    if target.exists() and is_controller(target, target.read_text(encoding="utf-8")):
                        problems.append(
                            f"{rel}:{lineno}: controller 不得 import 兄弟 controller（{imported}）"
                        )

    tests = test_files()
    for path in tests:
        rel = path.relative_to(BASE).as_posix()
        problems += name_problems(ast.parse(path.read_text(encoding="utf-8")), path, rel)

    return problems, len(files) + len(tests)


def main() -> int:
    problems, count = check()
    if problems:
        print(f"架构检查未通过，共 {len(problems)} 项：\n")
        for p in problems:
            print("  " + p)
        return 1

    print(f"架构检查通过：{count} 个文件，6 项规则全部满足。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
