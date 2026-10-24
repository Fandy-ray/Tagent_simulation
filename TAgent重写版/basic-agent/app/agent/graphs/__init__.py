"""每种能力一张图，用 app/agent/nodes.py 里的共用节点拼出来。

    answer.py    答疑：理解问题 → 检索 → 生成（流式检索完就出图，逐块生成在 ChatService）
    exam.py      整卷：取材 → 大题 ∥ 子图（规划 → 填空 ∥ 选择）→ 组卷
    flash.py     闪卡：取材切片 → 各片并发 → 删坏卡、去重、交错
    grade.py     判卷：给大题配材料 → 各批并发
    essay.py     小论文：取材 → 三维并发打分 → 被点名才下钻批注；另有出题
    annotate.py  逐句批注：切句编号 → 问一次 → 挂原文区间
    edit.py      文件编辑（铺路）：修改建议 → 挂原文区间；采纳后 apply_edits 改回原文
"""
