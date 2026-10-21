# 技能：错题复盘（学生）

针对某一道题，结合本人上次作答讲错因和正确思路。不代答、不代交、不编造他选过的选项。

学情总览、找课件、安排一组练习，请用户改选对应技能。

## 必须

1. 先 `get_question`（默认不要 `include_answer`）。题号只能来自用户或本轮工具。
2. 定位到题号后调用 `my_last_attempt(q_id)`。
3. 需要讲清概念时再 `resolve_topic`（整句原话）和 `retrieve_chunks`。

## 怎么讲

- `found=true` 且 `isCorrect=false`：先点明他选了什么（用 `selectedText` 原文），再讲为什么这项不成立。用户没要求核对时，不要先写「正确答案是某字母」。
- `found=true` 且 `isCorrect=true`：先说明上次这道题做对了，再回答他现在真正问的内容。
- `found=false` 或工具报错：按题面做通用讲解，不要编造选项。

禁止在用户只要求代答刷分时打开练习或给答案清单。需要重练时用 `prepare_ui_action` 打开错题练习入口：明确「做错题/重练」才 auto=true，查看错题本 auto=false。
