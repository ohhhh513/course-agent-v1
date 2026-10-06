# Agent 化改造 · 交接文档与阶段划分

> 面向：接手 Agent（智能体）后续开发的队友。
> 分支：`new_agent-v2.4.1`　最后更新：2026-10-06
> 相关文档：`AGENTS.md`（给 AI 助手的硬规矩）、`docs/智能体入门与AI协作手册.md`（不懂智能体先读这份）、`待修复清单.md`（已核实但未修的问题）、`docs/智能体工作流说明.md`（原有 Agent 流程）、`docs/后端对接指南.md`。

---

## 0. 一分钟看懂

### 这件事要做什么

把现在只会「讲解」的 AI 智能答疑，升级成真正能**做事**的智能体：

- **能查数据**：学情、预警、逐题正确率、薄弱点排序。学生只能看自己；教师能看全班。
- **能动手**：给出界面动作（跳页、进练习）；写操作（保存草稿、批改、导入题库）必须**用户确认后**才执行。
- **能被外部调用**：同一批工具挂成 MCP，给 Claude Desktop / Cursor 这类客户端用。

### 现在到哪了

（全部在本地 `new_agent-v2.4.1`，**尚未 push**）

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 运行层换成 OpenAI Agents SDK（`AGENT_RUNTIME` 可切换，事件契约不变） | 已完成 |
| P1 | 学情只读工具 + 界面动作建议（学生端一键跳靶向练习） | 已完成 |
| P2a | 角色/权限基建 + 教师端路由闸门（清单 P38） | 已完成（本轮提交 `5010734`） |
| P2b | 教师视角工具（看全班） | **待做** |
| P2c | 写操作审批闸门（pending → approved → executed） | **待做** |
| P3 | 前端体验：确认卡片、学生自助报告 | 待做 |
| P4 | MCP 导出 + 服务器部署 | 待做 |

### 立刻能上手的三条命令

```bat
REM 1. 角色与工具权限（秒级，不需要模型/数据库）
backend\.venv\Scripts\python.exe dev_tools\check_agent_roles.py

REM 2. 教师端路由闸门（真实登录 + 库副本，教师/学生/管理员三档）
backend\.venv\Scripts\python.exe dev_tools\check_route_roles.py

REM 3. 智能答疑两条运行层对照（真调模型，默认在库副本上跑，不写真实库）
backend\.venv\Scripts\python.exe dev_tools\smoke_agent_sdk.py --runtime sdk    --user stu07 --question "我现在有哪些预警？"
backend\.venv\Scripts\python.exe dev_tools\smoke_agent_sdk.py --runtime legacy --user stu07 --question "我现在有哪些预警？"
```

---

## 0.5 队友和他的 AI 助手：先立规矩

**如果你（或你的队友）不熟悉智能体，先读 `docs/智能体入门与AI协作手册.md`。** 它用大白话讲了：智能体的四个零件、一次提问的完整旅程、为什么不能随口命令 AI 改这个项目、以及一套可以直接复制的提示词。

这里只放最要紧的三条协作约定（`AGENTS.md` 里是完整版，任何 AI 助手进仓库都会自动读到）：

**① 让 AI 每次都说清 5 件事**

```text
【在做什么】一句话说清这一步干什么
【为什么】为什么现在做它（对应哪个阶段 / 哪个 bug）
【影响面】前端 / 后端 / 数据库 —— 具体文件与接口
【怎么验证】跑哪条命令、看到什么才算通过
【下一步】这件事做完之后该做什么
```

开工前给一次（当计划，等确认），收工时再给一次（结果 + 证据 + 下一步）。**只说「已完成」不算完成**。

**② 黄金四步：先读 → 要计划 → 一次一件事 → 要证据**

| 步 | 你该做什么 | 不对劲的信号 |
| --- | --- | --- |
| 1 先读 | 让它读 `AGENTS.md`、本文档、`待修复清单.md`，复述任务边界 | 上来就改代码 |
| 2 要计划 | 要它说「改哪些文件、影响什么、怎么验证」，等你说开始 | 直接给一堆 diff |
| 3 一次一件事 | 一次只批一个阶段，做完验证再下一个 | 一次提交混了好几件事 |
| 4 要证据 | 命令输出 / 事件序列 / 点了几次看到什么 | 「应该没问题」 |

**③ 三条红线，踩了立刻喊停**

- 改后端**没先给影响分析** → 停。
- 动**数据库结构**（加表 / 加列 / 改类型）→ 停。
- 改**事件名或字段**（前端只认那一套）→ 停。

---

## 1. 三条铁律（动代码前先读）

1. **前端可以直接改**。页面、样式、交互随便动。
2. **改后端要先给影响分析**：说明改哪个接口、谁在调用、学生端/教师端各会看到什么变化、失败时怎么回退。确认后再动手。
3. **不要改数据库格式**（不加表、不加列、不改字段类型）。需要存新东西时**先看现有列够不够**：
   - `chat_messages.tool_log`（JSON 文本）—— 工具调用日志已经在这里，将来的「待审批动作」也放这里。
   - `reports.detail_json` —— 报告没有 `user_id/course_id` 列，归属信息写进这个 JSON（见清单 P45）。

补充约定（用户强调过）：**不写补丁式代码**。这个系统最终要部署到服务器，能走 SDK / 框架规范做法就走规范做法，别用「能跑就行」的临时代码。

---

## 2. 代码地图（谁负责什么）

### 2.1 后端 · Agent 内核 `backend/app/agent_st/agent/`

| 文件 | 作用 | 改它要注意 |
| --- | --- | --- |
| `registry.py` | **工具注册表**。`ToolSpec(name, description, parameters, flows, roles)`；`openai_tools()` 组装给模型的 JSON Schema；`execute()` 是唯一执行入口（含 flow 白名单 + 角色二次校验） | 新增工具只在这里注册；`roles` 决定谁能用 |
| `runtime.py` | **legacy 运行层**（手写「模型 ⇄ 工具」循环），对外唯一入口 `run_turn()`；顶部按 `AGENT_RUNTIME` 委派给 `sdk_runner` | 改它等于改所有对话行为，先跑冒烟 |
| `sdk_runner.py` | **SDK 运行层**（OpenAI Agents SDK：`Agent` + `Runner.run_streamed`），与 legacy 同事件契约 | 两层的校验必须保持同步（本轮就补过一次） |
| `store.py` | `AgentStore`：会话/消息/草稿/`tool_log` 落库（走 `chat_sessions`/`chat_messages`/`st_question_drafts`） | 不建表，只用现有列 |
| `persistence.py` | agent_st 访问正式模型的统一出口（避免循环依赖） | 新模型从这里导入 |
| `context.py` | `ToolContext(store, flow_id, extra, turn, user_id, tool_log)`；`extra` 里带 `courseId` 与 `role` | 工具从 `ctx.extra` 取上下文，**签名里不要出现 user_id/course_id**（服务端注入，防模型伪造） |
| `loader.py` | 加载 persona / flow / skill，拼系统提示 | 提示词改动写进 skill，不要写进代码 |
| `net.py` | 统一构造 OpenAI 兼容客户端（超时策略，遵循标准代理环境变量） | 出网问题先看这里 |
| `personas/course_tutor.yaml` | 人格与默认工具集 | — |
| `flows/explain.yaml` | 答疑任务流（`roles: [student, teacher, admin]`、工具白名单、`max_steps`） | 加工具要同时改这里的白名单 |
| `flows/generate_items.yaml` | 出题任务流（`roles: [teacher, admin]`，会写草稿） | — |
| `skills/explain.md` | **答疑行为规范**（口径表、工具路由、回答结构、必须自包含） | 回答质量问题优先改这里 |
| `skills/generate_items.md` | 出题行为规范 | — |

### 2.2 后端 · 工具实现 `backend/app/agent_st/agent/tools/`

| 文件 | 工具 | 谁能用 |
| --- | --- | --- |
| `rag.py` | `retrieve_chunks` | 全部 |
| `topic.py` | `resolve_topic` | 全部 |
| `bank.py` | `get_question` / `search_similar_questions`（防抄黑名单） | 前者全部，后者教师/管理员 |
| `plan.py` | `submit_item_plan` / `check_novelty` | 教师/管理员 |
| `validate.py` | `validate_question` | 教师/管理员 |
| `draft.py` | `save_question_draft`（写 `st_question_drafts`，不发正式题库） | 教师/管理员 |
| `analytics.py` | `explain_metric` / `my_alerts` / `breakdown` / `weak_ranking` / `suggest_action` | 全部（**只读当前登录用户自己的数据**） |

### 2.3 后端 · 路由与依赖

| 文件 | 作用 |
| --- | --- |
| `routers/ai.py` | `/api/v1/ai/*`：答疑 SSE、聚合接口、会话历史；构造 `context` 时**注入 `role`** |
| `routers/teacher.py` | 教师端 48 个接口 + `/analysis/*`（归因）+ `/question/*`（AI 出题，`/question/gen` 是出题流入口） |
| `routers/intervention.py` | `/intervention/*`（教学干预）+ `/report/*`（学情报告） |
| `dependencies.py` | `get_current_course_id`（课程上下文 + 成员校验）；`require_role / require_teacher / require_student / require_admin`（角色闸门） |
| `routers/st_agent.py` | `/agent/*`：运行模式、RAG 入库状态；里面另有一份 `_require_teacher`（返回信封 403，未合并） |

### 2.4 前端

| 文件 | 作用 |
| --- | --- |
| `assets/js/api.js` | 统一接口层；`ai.chatStream` 解析 SSE，含 `onAction` 回调（约 168–195 行） |
| `assets/js/student/views/chat.js` | 答疑页：渲染消息/工具/引用/建议按钮；`applyAgentAction()` 是**白名单桥**（约 296–322 行） |
| `assets/js/student/views/practice.js` | 智能练习；`Practice._pendingTarget` 支持从预警/答疑「去练习」直接进靶向练习（含 `mode`） |

---

## 3. 事件契约（前端与运行层之间唯一的耦合面）

运行层产出的事件（`runtime.run_turn` / `sdk_runner.run_turn_sdk` 完全一致）：

| 内核事件 | SSE 事件名 | 前端用途 |
| --- | --- | --- |
| `session` | `meta` | 会话 id、flowId、messageId |
| `text` | `content` | 逐 token 正文 |
| `think` | `think` | 模型推理，折叠面板展示 |
| `tool_start` / `tool_end` | 同名 | 工具调用过程（`preview` 为截断结果） |
| `draft` | `draft` | 出题流每保存一道草稿推一次 |
| `citations` | `citations` | 引用来源（题号 / 知识点 / 切片） |
| `action` | `action` | 建议的界面动作（`suggest_action` 工具产生） |
| `error` | `error` | 可读错误 |
| `done` | `done` | `outOfScope` / `demo` / `drafts` |

**规矩**：改运行层、换模型、接 SDK —— 事件名和字段不许变。前端只认这张表。

---

## 4. 已完成的部分（可以直接看代码）

### P0 · 运行层接入 OpenAI Agents SDK

- `net.py` 统一客户端；`sdk_runner.py` 用 `Agent` + `Runner.run_streamed` 跑同一批注册工具；同步工具丢线程池（`asyncio.to_thread`），避免 SSE 卡住。
- 切换方式：环境变量 `AGENT_RUNTIME=legacy|sdk`（默认 `legacy`）。**没装 `openai-agents` 或没配 key 时自动回退 legacy**，不会因为环境不齐就崩。
- `set_tracing_disabled(True)`：不需要 OpenAI key，走 DeepSeek 兼容端点（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）。
- 已知差异：SDK 会把同一轮的多个工具**并行**执行（事件序可能出现 `start, start, end, end`），legacy 是串行。前端按事件渲染，不受影响。

### P1 · 学情只读工具 + 界面动作建议

- `services/scoring.py` 抽出 `_weighted_records()` 唯一取数入口，新增 `kp_accuracy_detail()` 逐题拆解；**重构前后全学生逐点比对 0 差异**。
- `tools/analytics.py` 五个工具：
  - `explain_metric` —— 口径字典（正确率/掌握率/预警规则怎么算）。
  - `my_alerts` —— 当前用户 + 当前课程的预警。
  - `breakdown` —— 某知识点的逐题拆解（含关系 `pre/post`）。
  - `weak_ranking` —— 统一口径的「最该先补」排序（命中 ≥2 题且 <60%，按正确率升序 → 被依赖多的基础点优先 → 章节靠前，每条带 `reason`）。
  - `suggest_action` —— 给出界面动作（只入队，不执行）。
- 事件链打通：`runtime`/`sdk_runner` → `action` 事件 → `routers/ai.py` SSE → `api.js onAction` → `chat.js` 渲染按钮 → `applyAgentAction()` 白名单执行（`navigate` 限 7 个页面；`practice` 只复用「预警 → 去练习」那套待办，仍需用户自己点开始）。
- `skills/explain.md` 增加「学情类问题」章节：工具路由表、禁止估算、按钮只是补充、**最终回答必须自包含**（不能写「见上文」）。

### P2a · 角色/权限基建（本轮）

**目标**：Agent 能区分「谁在问」，教师工具、写操作、隐私数据都靠它兜底。

- 工具级：`ToolSpec.roles`；`openai_tools(flow_id, names, role=)` **非空角色才过滤**（模型看不到就调不到）；`execute()` 再校验一次（模型硬调也会被拒）。
- 任务流级：`flows/*.yaml` 里的 `roles`；`runtime` 与 `sdk_runner` 都在建会话前校验，角色不符直接 `error + done`。
- 角色来源：`routers/ai.py` 与 `teacher.py` 的出题入口把登录用户的 `role` 注入 `context`（**模型无法指定**）。
- 路由级：`dependencies.require_teacher` 挂到 5 个前缀 —— `/teacher/*`、`/analysis/*`、`/question/*`、`/intervention/*`、`/report/*`。学生 token 一律 403；未登录仍是 401。
  - 已核实学生端页面只调用 `/student`、`/practice`、`/graph`、`/ai`、`/course`，**不受影响**。
  - 管理员能过角色闸门，但若未加入该课程，课程级接口仍会因「尚未加入课程」403（原有成员校验，与本闸门无关）。

验收脚本（都已全绿）：

```bat
backend\.venv\Scripts\python.exe dev_tools\check_agent_roles.py     REM 工具清单过滤 + execute 二次校验
backend\.venv\Scripts\python.exe dev_tools\check_route_roles.py     REM 真实登录：学生 403 / 教师 200 / 管理员不被角色闸门拦
```

---

## 5. 待做阶段划分

依赖关系一句话：**P2b 与 P2c 都建立在 P2a 之上，互相独立，可并行；P3 依赖 P2c；P4 最后做。**

### P2b · 教师视角工具（建议第一优先）

**目标**：教师在答疑框里就能问「我班上谁最需要关注」「这个知识点全班错在哪」。

**交付物**

- 新增 `backend/app/agent_st/agent/tools/teacher_analytics.py`，注册 5 个工具（`roles=("teacher","admin")`，`flows=("explain",)`）：

| 工具 | 入参 | 返回 | 数据来源（建议复用，别新写统计） |
| --- | --- | --- | --- |
| `class_overview` | 无（课程由服务端注入） | 人数、活跃、平均正确率、红黄预警数 | `services/kp_stats.course_student_ids` + `services/scoring` |
| `class_alerts` | `level`, `limit` | 全班预警清单（按等级/知识点聚合，带学生姓名+学号） | `alerts` 表（已按 `course_id` 落库） |
| `student_profile` | `student_id` | 单个学生：正确率、预警、薄弱点、最近作答 | `services/scoring` + `alerts` |
| `kp_heatmap` | `dimension`, `limit` | 知识点 × 学生 掌握/正确率矩阵 | `kp_stats` / `scoring` |
| `hot_wrong_questions` | `kp_id`, `limit` | 全班错得最多的题（题号 + 错误率） | `answer_records` |

- `flows/explain.yaml` 的 `tools` 白名单加这 5 个名字（否则不会给模型）。
- `skills/explain.md` 增加「教师视角」小节：先给结论数字，再给名单；**回答里只引用需要的人，不要把全班名单无差别倒出来**。

**验收标准**

1. `check_agent_roles.py` 扩展后全绿：学生 token 的 explain 流工具清单里**不含**这 5 个；教师含。
2. 学生 `execute("class_alerts", ...)` 被拒。
3. 教师提问「我班上谁最需要关注」时，回答里出现具体学生 + 具体知识点 + 正确率，且 `context['courseId']` 之外的课程数据不出现。
4. 传一个不属于本课程的 `student_id`（例如其他课程的学生）→ 工具返回明确错误，不泄露该生任何数据。

**风险与注意**

- 这是**隐私边界**新开口子：工具内部必须先校验「该学生在当前课程内」（用 `kp_stats.course_student_ids`），再查数据；错误信息里不要回显该生姓名。
- 人数多时 `kp_heatmap` 结果可能巨大 —— 强制 `limit`，并在工具里截断，别指望模型自己克制。
- 不要动数据库：现有表足够。

### P2c · 写操作审批闸门

**目标**：Agent 能提出「要做什么」，但**必须用户点确认**才真正落库（Claude 那种「待批准动作」）。

**必须先知道的技术事实**

- 当前 SDK 版本 `openai-agents 0.3.3`：**普通 `FunctionTool` 没有 `needs_approval`**，也没有可持久化的 `RunState`；只有 MCP 工具支持 `MCPToolApprovalFunction`。
- 所以跨请求的审批**要自己落地**，但不能建表 —— 正好用现有列 `chat_messages.tool_log`（JSON 文本，已存在）。

**建议方案（不改数据库）**

1. `registry.ToolSpec` 增加 `writes: bool`（或 `approval: str`），写操作工具打标。
2. `execute()` 遇到写工具时**不执行**，改为往 `ctx.turn["pending_actions"]` 推一条：`{action_id, tool, args, summary, status: "pending", created_by, course_id}`。
3. 运行层透出 `action`（`kind=confirm`）事件；`store.set_last_tool_log()` 把 pending 动作一起写进该条 assistant 消息的 `tool_log`。
4. 新增 `POST /api/v1/agent/actions/{action_id}/approve` 与 `/reject`：服务端从 `tool_log` 读出**落库的参数**（不信任前端传来的参数），校验「属于当前用户 + 当前课程」，然后执行工具、把状态改成 `executed`（拒绝改 `rejected`）。
5. 前端：`chat.js` 渲染确认卡片（做什么 + 关键参数摘要 + 确认/拒绝），复用现有 `action` 事件渲染路径。

**验收标准**

1. 未确认时：`st_question_drafts` 里**没有**新草稿；`tool_log` 里能看到 `status=pending`。
2. 点确认 → 工具真正执行、状态变 `executed`；点拒绝 → 状态 `rejected` 且无副作用。
3. 换一个用户（或换课程）去 approve 别人的 `action_id` → 403。
4. 重复 approve 同一条 → 幂等（第二次返回已执行，不重复写）。

**风险与注意**

- 写工具会让 Agent 具备真实副作用，**先只把「低风险、可回滚」的动作纳入**（保存草稿、批改草稿）；「发消息给学生」「发布题目」这类要等审批 UI 稳定后再放开。
- 学生端**不要**开放任何写工具。
- 每个写工具都要自己再做一次权限校验（服务端注入的角色 + 课程），不能只依赖闸门。

### P3 · 前端体验与报告

- **确认卡片 UI**（P2c 的前端部分）：卡片要能显示「工具名 / 关键参数 / 影响面」，并区分「只读建议」与「待批准写操作」。
- **学生自助报告**：用户要求保留「生成报告」。`reports` 表只有 `class_id`，没有 `user_id/course_id` —— 把归属写进 `detail_json`，列表按内容过滤（清单 P45 已登记这个口径问题）。若将来要真正按学生隔离，需要动表结构，**必须先跟用户确认**。
- 学生端操作范围天然受限（不能让 AI 帮学生做题）；教师端更自由（批改、出题、导入题库）。

### P4 · MCP 导出与部署

- 把 `registry` 里同一批工具挂成 MCP server（`mcp 1.30.0` 已装），给 Claude Desktop / Cursor 用。注意：MCP 客户端没有本系统的 JWT，需要**一次性令牌 / 本地进程信任**模型，并明确作用域（哪个用户、哪门课）。
- 部署注意：`backend\.venv` 依赖（`openai`、`openai-agents`、`mcp`、`uvicorn`、`sse-starlette==2.1.3`、`starlette==0.38.6`）；生产必须固定 `JWT_SECRET`；代理环境变量会影响出网，先看 `net.py`。

---

## 6. 已知问题（与 `待修复清单.md` 的对应）

| 编号 | 说明 | 与 Agent 改造的关系 |
| --- | --- | --- |
| P38 | 教师端路由没有角色校验 | ✅ 本轮已修（学生 403） |
| P44 | 预警生命周期没有兜底：证据消失后预警消不掉 | ⚠️ 直接影响教师工具 `class_alerts` 的可信度，建议在 P2b 前或同期处理 |
| P45 | 题目归属两套视角（题库按主 KP、学情按主∪标签） | 影响 `hot_wrong_questions` 的口径说明，回答里要写清口径 |
| P46 | 薄弱点强化会排进「已做对」的题 | 已被用户明确决策：**不改** |
| P47 | 薄弱点清单只取前 5，会漏掉有预警的子知识点 | 影响「预警 → 练习」按钮的完整性 |
| P48 | 纯标签命中的子知识点预警门槛过松 | 影响预警数量与教师端噪声 |

完整清单与「归属 / 界面 / 影响」三段说明见 `待修复清单.md`。

---

## 7. 验证、调试与协作资产

### 7.1 三个脚本

| 脚本 | 用途 | 是否需要模型 | 会不会写库 |
| --- | --- | --- | --- |
| `dev_tools/check_agent_roles.py` | 工具/任务流角色校验自检 | 否 | 否 |
| `dev_tools/check_route_roles.py` | 教师端路由闸门（真实登录 + TestClient） | 否 | 只在库副本 |
| `dev_tools/smoke_agent_sdk.py` | 两条运行层对照冒烟（`--runtime`、`--user`、`--flow`、`--role`、`--max-events`） | 是 | 默认库副本，`--db` 才指真实库 |

### 7.2 铁律：验证一律在**库副本**上做

```bat
REM 演示库（真实数据，别直接改）
backend\app\data\course_agent.db
REM 演示账号：管理员 admin/admin；教师 wangjg/123456；学生 stu01…stu10/123456
REM 课程：CCHYJTKE
```

`smoke_agent_sdk.py` 与 `check_route_roles.py` 默认自己复制一份到临时目录再跑，不用手动处理。

### 7.3 启动

```bat
start.bat            REM 一键：优先 backend\.venv，端口 8000
REM 或手动：
cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 7.4 已知坑

- **前端页面可能是旧版**：静态资源已加 no-cache，但浏览器仍可能缓存，症状是「后端明明产出了按钮/新逻辑，页面没反应」——先硬刷新。
- **PowerShell 提交中文**：`git commit -m` 里含中文引号（`"`）会被解析吃掉，用 `「」` 或去掉引号。
- **写文件用 apply_patch**，中文里避免出现 ASCII 双引号。
- `backend/data.zip` 是打包给别人用的产物，**不要删、也不要误提交**（当前未跟踪）。

---

## 8. 开工检查清单

- [ ] **如果不懂智能体**：先读 `docs/智能体入门与AI协作手册.md`（大白话版），知道「工具 / 任务流 / 技能 / 事件契约」分别是什么。
- [ ] 把 `AGENTS.md` 交给你的 AI 助手（或让它自己读），确认它按「5 行汇报 + 先给计划」的方式跟你说话。
- [ ] 读 `待修复清单.md` 的「怎么读这份清单」，知道每条都有「归属 / 界面 / 影响」。
- [ ] 跑通 `check_agent_roles.py` 与 `check_route_roles.py`（应全绿）。
- [ ] 跑一次 `smoke_agent_sdk.py`（sdk 与 legacy 各一次），看到工具调用、引用、建议动作、完整回答。
- [ ] 确认 `AGENT_RUNTIME` 的含义（默认 legacy，sdk 需装包 + 配 key）。
- [ ] 确认三条铁律（前端可改 / 后端先给影响分析 / 不改数据库格式）。
- [ ] 认领一个阶段（建议 P2b），按「验收标准」逐条自测，再提交。

有任何一条对不上，先在群里问，不要凭猜改后端。
