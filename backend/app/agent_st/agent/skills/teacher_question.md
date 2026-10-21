# 技能：备课出题（教师）

在对话里按教师指定范围生成习题草稿。不写入正式题库。不要调用 `kp_heatmap` 做逐点分析，不要打开出题配置页代替生成，不要把完整试卷写进聊天。

## 流程

1. 范围、题量或题型有缺：先 `offer_choices` 让教师点选，禁止默认题量后出题。每轮只问一件关键事，此轮不要同时 `prepare_ui_action`。
2. 细节齐全后 `resolve_topic`（整词、多章分别定位）收集 `kp_id`，不要编 id。
3. `prepare_ui_action(target="teacher.question.create", values={kpIds, count, types, difficulty}, auto=true)`。
4. 题型只能是 `single` / `multi` / `blank` / `judge`。未说难度才用 3。
5. 正文 1～2 句说明正在按哪些范围出几道什么题。不要催「点预览题目」（前端生成完成后才出现）。

询问「出题在哪 / 打开配置，先别生成」才用 `teacher.question.generate`。未进正式题库前不得说已经发布。
