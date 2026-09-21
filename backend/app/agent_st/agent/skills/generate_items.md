# 智能出题 Skill

## 何时使用

教师指定任意个知识点（可为 0）与 0～3 道例题，两者数量之和必须大于 0，要出单选题。

## 输入三种模式

- 仅知识点：根据知识点与教材/解析 **从零出题**。`search_similar_questions` 只作防抄黑名单，禁止当可微调骨架。
- 仅例题：`get_question` 读齐例题（可带答案以便避开原解题路径），按「较大变动」出新题，结构归属沿用例题的章/知识点。
- 两者都有：考指定知识点；例题只作启发，新题必须相对例题足够不同。

## 必须按顺序做

1. `resolve_topic`。上下文若有 `example_question_ids`，对每道例题 `get_question(include_answer=true)`。
2. `retrieve_chunks` 约束考点表述。
3. `search_similar_questions`：只用来避免抄题库，不要照抄题干/选项/权值。
4. `submit_item_plan`：先交构思。必须包含提问目标、实例草图、**逐步解题与正确结论**、干扰项对应的易错点、相对对照题怎么变。没有 plan 不得出 JSON。
5. 根据解题过程设计 3 个错误选项，再输出闭集 JSON：
   `chapter_id, kp_ids, question, options{A,B,C,D}, answer, analysis, has_image`
   可选：`graph`, `options_graph`
   **不要输出 `q_id` 字段**（见下方「题号」）。
6. `validate_question`；失败则按 `errors` 改，最多两轮。
7. `check_novelty`；失败必须加大变动后重做 plan 或改 JSON，禁止只改一个数字再提交。
8. 两项都通过后 `save_question_draft`。保存成功后，工具返回的 `q_id` 就是本题正式题号。

## 定位约定：整词交给 resolve_topic，不要自己拆词

`resolve_topic` 的 `text` 传**教师原话或其中的完整名词短语**，不要拆词、不要自己判断知识点。
`resolve_topic` 先按**本课程知识点名称**匹配（名称清单见 system prompt），匹配不到才做检索投票兜底。

| 说法 | 正确调用 | 定位结果 |
|---|---|---|
| 「树形查找」 | `text="树形查找"` | `树形查找`（与「查找」是两个不同知识点） |
| 「二叉树遍历」 | `text="二叉树遍历"` | `二叉树遍历`（不是「树与二叉树」） |
| 「图的遍历」 | `text="图的遍历"` | `图的存储与遍历` |
| 「栈和队列」 | `text="栈和队列"` | 命中**多个**知识点（`kp_ids` 多项） |

教师端本来就会显式传 `kp_ids`（前端勾选的知识点），此时**以它为准**，不要用关键词覆盖它。
校验失败后回改时，也不要改 `kp_ids` —— 改的是题面/选项/答案。

## 题号：由系统分配，你不要编号

题号是主库 `questions.q_id`，是**系统生成的字符串**，前后端都把它当不透明标识使用：

| 生成方式 | 形态 | 示例 |
|---|---|---|
| 教师手动新增 / 导入题库 | `Q` + 8 位十六进制 | `QD44D2820` |
| AI 草稿发布进正式题库 | `AI` + 8 位十六进制 | `AI3F8A21E7` |

因此：

- **JSON 里不要写 `q_id` 字段**。保存时由系统按上表分配；即使你写了，系统也会覆盖它。
- 不要写 `AI001`、`AI###`、`id`、`#1` 这类自己编的号 —— 一律不要出现在你的输出里。
- 引用例题或对照题时，用工具返回的 `q_id` **原样照抄**（如 `QD44D2820`），不要改写、不要补零、不要缩短。
- 学生侧是按题号检索的，编造题号会导致引用失败。

## 「较大变动」

不是必须改图的拓扑或树的形状。禁止的是近乎原题的微扰，例如把「从 1,3,6 中选最大」改成「从 1,2,6 中选最大」，或只改一两根边的权值且解题路径不变。

可以通过的例子：换提问目标（第一条边 vs 总权值）；或同一考点但实例实质不同（多条边权非平移式改动，或边集合明显不同）。改完必须 **重算答案**，禁止沿用源题答案。

## JSON 硬约束（短清单）

- 仅单项选择 A/B/C/D；不要多选/填空/判断/编程
- **`chapter_id` 与 `kp_ids` 必须取自本课程图谱**：`chapter_id` 形如 `CH06`，`kp_ids` 是知识点 id 数组，如 `["KP017"]`。
  只能使用 `resolve_topic` 或上下文给出的值，**不要自己编 id，也不要写章名或知识点名称**
- **`kp_ids` 是数组**：这道题只考一个知识点就写一项；确实同时考多个考点才写多项（最多 3 项），
  第一项是主考点。不要为了凑数堆知识点
- 主考点（`kp_ids` 第一项）必须与 `chapter_id` 自洽（该知识点确实挂在该章下）
- 不要输出 `kp_id` 字段（单值）；系统会按 `kp_ids` 的首项自动填主知识点
- `graph.type` 只能是：`tree` `adjacency_matrix` `undirected_graph` `directed_graph` `weighted_undirected_graph` `weighted_directed_graph` `aoe_network`
- 画不出的图（B 树过程、线索虚线、内存地址表）：`has_image=true`，不要写 `graph`
- `q_id` **不要出现在你的输出里**，保存时系统分配
- 不要 Markdown 图、不要 SVG
- `analysis` 必须写出与 plan 一致的解题要点

最小示例（结构参考，不要原样照抄考点；`chapter_id` / `kp_ids` 以实际 `resolve_topic` 结果为准）：

```json
{
  "chapter_id": "CH07",
  "kp_ids": ["KP017"],
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

- 说「已加入题库」或已写入正式题库
- 输出 `q_id`，或自己编题号（`AI001`、`AI###`、`#1`、整数 id 都不行）
- 发明新字段名（如 `analyse`、`has_picture`、`chapter`、`id`）
- 把二叉树改成一般图，或把 AOE 改成无向图
- 把检索到的题当骨架做标签/权值微扰
- 无对照题时直接复述 `retrieve_chunks` 里的题干
