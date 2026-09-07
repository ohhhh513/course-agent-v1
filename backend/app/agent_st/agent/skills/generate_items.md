# 智能出题 Skill

## 何时使用

教师指定任意个知识点（可为 0）与 0～3 道例题，两者数量之和必须大于 0，要出单选题。

## 输入三种模式

- 仅知识点：根据知识点与教材/解析 **从零出题**。`search_similar_questions` 只作防抄黑名单，禁止当可微调骨架。
- 仅例题：`get_question` 读齐例题（可带答案以便避开原解题路径），按「较大变动」出新题，考点由例题章节推断。
- 两者都有：考指定知识点；例题只作启发，新题必须相对例题足够不同。

## 必须按顺序做

1. `resolve_topic`。上下文若有 `example_question_ids`，对每道例题 `get_question(include_answer=true)`。
2. `retrieve_chunks` 约束考点表述。
3. `search_similar_questions`：只用来避免抄题库，不要照抄题干/选项/权值。
4. `submit_item_plan`：先交构思。必须包含提问目标、实例草图、**逐步解题与正确结论**、干扰项对应的易错点、相对对照题怎么变。没有 plan 不得出 JSON。
5. 根据解题过程设计 3 个错误选项，再输出闭集 JSON：
   `id, chapter, question, options{A,B,C,D}, answer, analysis, has_image`
   可选：`graph`, `options_graph`
6. `validate_question`；失败则按 `errors` 改，最多两轮。
7. `check_novelty`；失败必须加大变动后重做 plan 或改 JSON，禁止只改一个数字再提交。
8. 两项都通过后 `save_question_draft`。

## 「较大变动」

不是必须改图的拓扑或树的形状。禁止的是近乎原题的微扰，例如把「从 1,3,6 中选最大」改成「从 1,2,6 中选最大」，或只改一两根边的权值且解题路径不变。

可以通过的例子：换提问目标（第一条边 vs 总权值）；或同一考点但实例实质不同（多条边权非平移式改动，或边集合明显不同）。改完必须 **重算答案**，禁止沿用源题答案。

## JSON 硬约束（短清单）

- 仅单项选择 A/B/C/D；不要多选/填空/判断/编程
- `chapter` 必须是王道小节前缀（如 `6.4 图的应用`），不要写成「第7章 图」
- 数组题用 `3.4`，树用 `5.x`，图用 `6.x`，查找用 `7.x`，排序用 `8.x`
- `graph.type` 只能是：`tree` `adjacency_matrix` `undirected_graph` `directed_graph` `weighted_undirected_graph` `weighted_directed_graph` `aoe_network`
- 画不出的图（B 树过程、线索虚线、内存地址表）：`has_image=true`，不要写 `graph`
- 新 `id` 用 90001 起；也可用 `"id": 0` 让工具分配
- 不要 Markdown 图、不要 SVG
- `analysis` 必须写出与 plan 一致的解题要点

最小示例（结构参考，不要原样照抄考点）：

```json
{
  "id": 90001,
  "chapter": "6.4 图的应用",
  "question": "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。",
  "options": {"A": "(a,b)", "B": "(b,c)", "C": "(a,c)", "D": "(c,d)"},
  "answer": "B",
  "analysis": "各边权值最小为 (b,c)=1，且不构成环。",
  "has_image": true,
  "graph": {
    "type": "weighted_undirected_graph",
    "nodes": ["a", "b", "c", "d"],
    "edges": [
      {"from": "a", "to": "b", "weight": 4},
      {"from": "b", "to": "c", "weight": 1},
      {"from": "a", "to": "c", "weight": 5},
      {"from": "c", "to": "d", "weight": 2}
    ]
  }
}
```

## 禁止

- 说「已加入题库」或已写入 `after_class.json`
- 发明新字段名（如 `analyse`、`has_picture`）
- 把二叉树改成一般图，或把 AOE 改成无向图
- 把检索到的题当骨架做标签/权值微扰
- 无对照题时直接复述 `retrieve_chunks` 里的题干
