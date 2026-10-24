"""分层架构守卫（tools/check_architecture.py）随测试一起跑。

它以前只能手动跑，没人想起来跑：新加的 app/agent 层一直没有规则，测试文件里的
未用 import 也一直没人发现。放进测试里，违规时测试直接红。
"""

from tools.check_architecture import check


def test_architecture_rules_hold():
    problems, checked = check()
    assert checked > 100, "检查器没找到文件，多半是路径算错了"
    assert problems == [], "\n".join(problems)
