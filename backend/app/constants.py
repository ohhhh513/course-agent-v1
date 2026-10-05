"""全站共享的业务常量。

这里的值是「唯一真源」——同一个业务阈值不允许在多个模块里各写一份，
否则改一处漏一处就会口径打架（本项目历史上多次踩过这个坑）。

`MASTERY_THRESHOLD` 的引用方（全站统一，改这一个数就全站生效）：
- 学生端 `routers/student.py`：
  · `coreMetrics.masteredKpCount` = 达标知识点个数；
  · `coreMetrics.masteryThreshold` 下发，前端「达标线 X%」文案由此渲染（前端不写死）；
  · 成长轨迹「达标知识点占比」。
- 教师端 `routers/teacher.py`：目标达成度、未达标人数、待关注学生、干预目标分档。
- 干预 `routers/intervention.py`：达标知识点统计与结论文案。

注意：预警分级用的 `RED_BELOW` / `YELLOW_BELOW`（`services/alert_detector.py`）
是「预警线」，与「达标线」是两个不同概念，因此不放在这里、也不跟随本常量变动。
"""

# 掌握率达标线（百分比）：单知识点综合掌握率 ≥ 该值即视为「达标」。
MASTERY_THRESHOLD = 80
