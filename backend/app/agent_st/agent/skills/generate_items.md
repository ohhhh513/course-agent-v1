# 智能出题 Skill

## 何时使用

教师或页面按钮指定章节、源题 id、数量（默认 1，最多 3），要出同类单选题。

## 必须先做

1. `resolve_topic`；有源题则 `get_question`，复制其 `chapter`、是否有图、`graph.type`、结点规模。
2. `search_similar_questions` 取同章、同配图形态的 2–3 道，只作骨架，不要抄原选项原文。
3. `retrieve_chunks` 约束考点表述。
4. 只输出题目 JSON 对象（多题则逐个处理），字段闭集：
   `id, chapter, question, options{A,B,C,D}, answer, analysis, has_image`
   可选：`graph`, `options_graph`
5. `validate_question`；失败则按 `errors` 改，最多两轮。
6. 通过后 `save_question_draft`。没有校验通过就不要保存。

## JSON 硬约束（短清单）

- 仅单项选择 A/B/C/D；不要多选/填空/判断/编程
- `chapter` 必须是王道小节前缀（如 `6.4 图的应用`），不要写成「第7章 图」
- 数组题用 `3.4`，树用 `5.x`，图用 `6.x`，查找用 `7.x`，排序用 `8.x`
- `graph.type` 只能是：`tree` `adjacency_matrix` `undirected_graph` `directed_graph` `weighted_undirected_graph` `weighted_directed_graph` `aoe_network`
- 相似题保持同一 `type` 与是否加权/有向；改标签和权值后必须重算 `answer`，禁止沿用源题答案
- 画不出的图（B 树过程、线索虚线、内存地址表）：`has_image=true`，不要写 `graph`
- 新 `id` 用 90001 起；也可用 `"id": 0` 让工具分配
- 不要 Markdown 图、不要 SVG

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
