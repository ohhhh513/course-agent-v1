# Agent 化改造 · 交接文档与阶段划分

> 面向：接手 Agent（智能体）后续开发的队友。
> 分支：`new_agent_v2.4.2/P2a`　最后更新：2026-10-06
> 相关文档：`AGENTS.md`（给 AI 助手的硬规矩）、`docs/智能体入门与AI协作手册.md`（不懂智能体先读这份）、`待修复清单.md`（已核实但未修的问题）、`docs/智能体工作流说明.md`（原有 Agent 流程）、`docs/后端对接指南.md`。

---

## 0. 一分钟看懂

### 这件事要做什么

把现在只会「讲解」的 AI 智能答疑，升级成真正能**做事**的智能体：

- **能查数据**：学情、预警、逐题正确率、薄弱点排序。学生只能看自己；教师能看全班。
- **能动手**：给出界面动作（跳页、进练习）；写操作（保存草稿、批改、导入题库）必须**用户确认后**才执行。
- **能被外部调用**：同一批工具挂成 MCP，给 Claude Desktop / Cursor 这类客户端用。

### 现在到哪了

（全部在本地 `new_agent_v2.4.2/P2a`，**尚未 push**）

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 运行层换成 OpenAI Agents SDK（`AGENT_RUNTIME` 可切换，事件契约不变） | 已完成 |
| P1 | 学情只读工具 + 界面动作建议（学生端一键跳靶向练习） | 已完成 |
| P2a | 角色/权限基建 + 教师端路由闸门（清单 P38） | 已完成（本轮提交 `5010734`） |
| P2b | 教师视角工具（看全班）+ 教师端答疑页 | 已完成 |
| P2c | 写操作审批闸门（pending → executed / rejected） | 已完成 |
| P3 | 前端体验：确认卡片、学生自助报告 | 已完成 |
| P4 | MCP 导出 + 服务器部署 | 已完成 |

### 立刻能上手的四条命令

```bat
REM 1. 角色与工具权限（秒级，不需要模型/数据库）
backend\.venv\Scripts\python.exe dev_tools\check_agent_roles.py

REM 2. 教师端路由闸门（真实登录 + 库副本，教师/学生/管理员三档）
backend\.venv\Scripts\python.exe dev_tools\check_route_roles.py

REM 3. 智能答疑两条运行层对照（真调模型，默认在库副本上跑，不写真实库）
backend\.venv\Scripts\python.exe dev_tools\smoke_agent_sdk.py --runtime sdk    --user stu07 --question "我现在有哪些预警？"

REM 4. MCP 导出（真实 MCP 客户端 ↔ 真实 server 子进程，含越权与真取数断言）
backend\.venv\Scripts\python.exe dev_tools\check_mcp_tools.py
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
| `registry.py` | **工具注册表**。`ToolSpec(name, description, parameters, flows, roles, approval)`；`openai_tools()` 组装给模型的 JSON Schema；`execute()` 是唯一执行入口（flow 白名单 + 角色二次校验 + **写操作闸门**） | 新增工具只在这里注册；`roles` 决定谁能用；`approval=ApprovalSpec(...)` = 该工具必须先经用户确认才能执行 |
| `runtime.py` | **legacy 运行层**（手写「模型 ⇄ 工具」循环），对外唯一入口 `run_turn()`；顶部按 `AGENT_RUNTIME` 委派给 `sdk_runner` | 改它等于改所有对话行为，先跑冒烟 |
| `sdk_runner.py` | **SDK 运行层**（OpenAI Agents SDK：`Agent` + `Runner.run_streamed`），与 legacy 同事件契约 | 两层的校验必须保持同步（本轮就补过一次） |
| `store.py` | `AgentStore`：会话/消息/草稿/`tool_log` 落库（走 `chat_sessions`/`chat_messages`/`st_question_drafts`）；`find_action` / `set_action_status` 支撑审批闸门（P2c） | 不建表，只用现有列 |
| `persistence.py` | agent_st 访问正式模型的统一出口（避免循环依赖） | 新模型从这里导入 |
| `context.py` | `ToolContext(store, flow_id, extra, turn, user_id, tool_log)`；`extra` 里带 `courseId` 与 `role` | 工具从 `ctx.extra` 取上下文，**签名里不要出现 user_id/course_id**（服务端注入，防模型伪造） |
| `loader.py` | 加载 persona / flow / skill，拼系统提示 | 提示词改动写进 skill，不要写进代码 |
| `net.py` | 统一构造 OpenAI 兼容客户端（超时策略，遵循标准代理环境变量） | 出网问题先看这里 |
| `personas/course_tutor.yaml` | 人格与默认工具集 | — |
| `flows/explain.yaml` | 答疑任务流（`roles: [student, teacher]`、工具白名单、`max_steps`） | 加工具要同时改这里的白名单 |
| `flows/generate_items.yaml` | 出题任务流（`roles: [teacher]`，会写草稿） | — |
| `flows/admin_ops.yaml` | 平台治理任务流（`roles: [admin]`；5 个只读查询 + 4 个账号治理工具） | 管理端智能体唯一入口（接口见 `docs/接口文档.md` 第 15 节） |
| `skills/explain.md` | **答疑行为规范**（口径表、工具路由、回答结构、必须自包含） | 回答质量问题优先改这里 |
| `skills/generate_items.md` | 出题行为规范 | — |

### 2.2 后端 · 工具实现 `backend/app/agent_st/agent/tools/`

| 文件 | 工具 | 谁能用 |
| --- | --- | --- |
| `rag.py` | `retrieve_chunks` | 全部 |
| `topic.py` | `resolve_topic` | 全部 |
| `bank.py` | `get_question` / `search_similar_questions`（防抄黑名单） | 前者全部，后者教师 |
| `plan.py` | `submit_item_plan` / `check_novelty` | 教师 |
| `validate.py` | `validate_question` | 教师 |
| `draft.py` | `save_question_draft`（写 `st_question_drafts`，不发正式题库；**挂审批闸门**） | 教师 |
| `analytics.py` | `explain_metric` / `my_alerts` / `breakdown` / `weak_ranking` / `suggest_action` | 全部（**只读当前登录用户自己的数据**） |
| `teacher_analytics.py` | `class_overview` / `class_alerts` / `student_profile` / `kp_heatmap` / `hot_wrong_questions` | 教师（**只读全班**，非本课程学生一律拒绝且不回显姓名） |
| `admin_ops.py` | `system_overview` / `account_overview` / `course_overview` / `kb_status` / `data_check` | 仅管理员（平台级**只读查询**，不吃 `courseId`） |
| `admin_import.py` | `preview_account_import`（只读）/ `import_accounts`（写，**挂审批闸门**） | 仅管理员 |
| `admin_delete.py` | `preview_account_delete`（只读）/ `delete_accounts`（写，**挂审批闸门**） | 仅管理员 |

> 角色口径以注册表为准：教师工具已收紧为 **teacher-only**（管理员不再共享教师视角工具、
> 也不再进 explain / 出题流）；管理员唯一的任务流是 `admin_ops`。

### 2.3 后端 · 路由与依赖

| 文件 | 作用 |
| --- | --- |
| `routers/ai.py` | `/api/v1/ai/*`：答疑 SSE、聚合接口、会话历史；构造 `context` 时**注入 `role`** |
| `routers/teacher.py` | 教师端 48 个接口 + `/analysis/*`（归因）+ `/question/*`（AI 出题，`/question/gen` 是出题流入口） |
| `routers/intervention.py` | `/intervention/*`（教学干预）+ `/report/*`（学情报告，教师闸门）+ **`/student/reports/*`**（学生自助报告，仅登录；导出与学生侧共用 `render_report_file()`） |
| `dependencies.py` | `get_current_course_id`（课程上下文 + 成员校验）；`require_role / require_teacher / require_student / require_admin`（角色闸门） |
| `routers/st_agent.py` | `/agent/*`：运行模式、RAG 入库状态、**写操作审批**（`/agent/actions/{id}/approve|reject`，P2c）；入库端点与审批端点都挂 `require_role("teacher","admin")`（与教师端前缀同一套闸门），`/agent/status` 对全部登录用户开放 |
| `routers/admin.py` | `/admin/*`：账号管理（列表 / 新建 / 编辑 / 删除 / 批量删除 / 批量导入）+ 平台治理智能体（`/admin/agent/*`，含 `actions/{id}/approve|reject`）；全部挂依赖注入的 `require_admin`（此前是本地手写的一份 `_require_admin`，已合并） |
| `agent_st/mcp_server.py` | **MCP 导出**（P4）：stdio server，把 `registry` 的工具按 `--flow` + 角色过滤后挂出去；作用域由 `--user/--course` 固化并在启动时校验成员关系；**不暴露写工具** |
| `services/student_report.py` | **学生个人报告统计**（`build_student_report`）：全部按登录学生本人的真实表计算，复用 `kp_stats.mastery_by_kp` / `scoring.overall_accuracy` 口径；不写库、不调模型（P3） |

### 2.4 前端

| 文件 | 作用 |
| --- | --- |
| `assets/js/api.js` | 统一接口层；`ai.chatStream` 解析 SSE，含 `onAction` 回调（约 168–195 行） |
| `assets/js/shared/agent-chat.js` | **答疑视图工厂**：`AgentChatView.create(config)`，学生端与教师端共用同一套渲染 / 流式 / 会话逻辑（差异全部由 config 提供） |
| `assets/js/student/views/chat.js` | 学生端答疑**配置**：欢迎语、推荐问题（驾驶舱同源）、`Chat.draft()` 供驾驶舱/图谱跨页带入、界面动作白名单 `applyAction`（与后端 `analytics._VIEWS` **必须一致**，由 `check_agent_roles.py` 第 8 组断言交叉校验） |
| `assets/js/teacher/views/chat.js` | 教师端「智能答疑」**配置**：教师向推荐问题、教师端页面白名单；教师视角工具由后端按角色下发 |
| `assets/js/student/views/practice.js` | 智能练习；`Practice._pendingTarget` 支持从预警/答疑「去练习」直接进靶向练习（含 `mode`） |
| `assets/js/student/views/report.js` | 学生端「学情报告」：生成 / 历史归档 / 详情弹窗 / 导出（PDF·HTML），走 `/student/reports/*` |

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
| `action` | `action` | 界面动作。`kind=navigate/practice` = 只读建议（`suggest_action`，`navigate` 的 `view` 走白名单，含学生端「学情报告」页）；**`kind=confirm` = 待批准写操作（P2c）**，前端渲染成确认卡片 |
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
- 事件链打通：`runtime`/`sdk_runner` → `action` 事件 → `routers/ai.py` SSE → `api.js onAction` → `chat.js` 渲染按钮 → `applyAgentAction()` 白名单执行（`navigate` 限 8 个页面，含 P3 的「学情报告」；`practice` 只复用「预警 → 去练习」那套待办，仍需用户自己点开始）。
- `skills/explain.md` 增加「学情类问题」章节：工具路由表、禁止估算、按钮只是补充、**最终回答必须自包含**（不能写「见上文」）。

### P2a · 角色/权限基建（本轮）

**目标**：Agent 能区分「谁在问」，教师工具、写操作、隐私数据都靠它兜底。

- 工具级：`ToolSpec.roles`；`openai_tools(flow_id, names, role=)` **非空角色才过滤**（模型看不到就调不到）；`execute()` 再校验一次（模型硬调也会被拒）。
- 任务流级：`flows/*.yaml` 里的 `roles`；`runtime` 与 `sdk_runner` 都在建会话前校验，角色不符直接 `error + done`。
- 角色来源：`routers/ai.py` 与 `teacher.py` 的出题入口把登录用户的 `role` 注入 `context`（**模型无法指定**）。
- 路由级：`dependencies.require_teacher` 挂到 5 个前缀 —— `/teacher/*`、`/analysis/*`、`/question/*`、`/intervention/*`、`/report/*`。学生 token 一律 403；未登录仍是 401。
  - 已核实学生端页面只调用 `/student`、`/practice`、`/graph`、`/ai`、`/course`，**不受影响**。
  - 管理员能过角色闸门，但若未加入该课程，课程级接口仍会因「尚未加入课程」403（原有成员校验，与本闸门无关）。
- 路由级（本轮收口）：把散在外面的两份**手写**校验并回 `dependencies` 的同一套 `require_role`：
  - `routers/st_agent.py` 的 `_require_teacher`（只认 `teacher`）→ `/agent/ingest/{stats,bank,file}` 改为 `Depends(require_role("teacher","admin"))`。旧行为下**管理员即使已加入课程也会被拒**（信封 403），与教师端前缀的 teacher+admin 口径相反；现在两处一致。
  - `routers/admin.py` 的本地 `_require_admin` → 4 个端点改为 `Depends(require_admin)`（语义不变，仍是 admin-only + HTTP 403，只是去掉重复实现）。
  - 入库端点**逐个挂依赖**而不是挂整个 `/agent` 前缀 —— `/agent/status` 是学生端也要读的，不能锁。
  - 越权响应从「HTTP 200 + 信封 `code=403`」变成「**HTTP 403 + `detail`**」，与五个前缀一致。前端 `api.js` 两个分支都会抛错，功能无影响。

**已知取舍：角色缺失 = 放行（fail-open）**

工具清单过滤、`execute()` 二次校验、flow 级 `roles` 三处都是「角色非空才校验」。
现有真实入口（`routers/ai.py` 的答疑、`teacher.py` 的出题）都会注入角色，所以**当前不构成可利用缺口**；
但它是最后一道防线 —— 将来新增调用路径（MCP 导出、脚本直调、新的路由）时**必须显式传 `role`**，
否则学生也能调教师专用工具。若要改成「缺角色一律拒绝」，需同时改
`registry.openai_tools` / `registry.execute` / `runtime`·`sdk_runner` 的 flow 校验，
并同步 `dev_tools/check_agent_roles.py` 的「role 为空时不过滤」断言与 `smoke_agent_sdk.py --role` 留空的用法。

验收脚本（都已全绿；没有 `backend\.venv` 时用系统 Python 3.11 + `backend/requirements.txt` 亦可）：

```bat
backend\.venv\Scripts\python.exe dev_tools\check_agent_roles.py     REM 流/工具/管理员/execute 四层角色校验
backend\.venv\Scripts\python.exe dev_tools\check_route_roles.py     REM 真实登录：教师端前缀 + /agent/ingest/* 三档 + 学生端与 /agent/status 不受影响
```

`check_agent_roles.py` 的「教师专用工具」集合是从注册表**动态推导**的（判据：`roles` 不含 `student`），
所以 P2b 往 explain 流加教师工具后该脚本会自动纳入断言，不需要改脚本；只有新增教师工具时才同步
`KNOWN_TEACHER_TOOLS` 这份快照做交叉校验。

### P2b · 教师视角工具 + 教师端答疑页（本轮）

**目标**：教师在答疑框里就能问「我班上谁最需要关注」「这个知识点全班错在哪」。

**交付物**

- 新增 `backend/app/agent_st/agent/tools/teacher_analytics.py`，5 个只读工具（`roles=("teacher","admin")`、`flows=("explain",)`）
  ——（当时的角色口径；这批工具**后在收紧批次改为 teacher-only**，管理员不再可见，下同）：

| 工具 | 入参 | 数据来源（复用现有口径，未新写统计） |
| --- | --- | --- |
| `class_overview` | 无（课程由服务端注入） | `kp_stats.course_student_ids` + `scoring` + `alerts` |
| `class_alerts` | `level`, `limit` | `alerts`（按 `course_id` 落库；排除 `ignored`） |
| `student_profile` | `student_id`, `limit` | `scoring.quiz_accuracy_by_kp` + `alerts` + `answer_records` |
| `kp_heatmap` | `dimension`, `limit` | `scoring.quiz_accuracy_by_kp` / `kp_stats.mastery_by_kp` |
| `hot_wrong_questions` | `kp_id`, `limit` | `answer_records` 按题聚合 |

- `flows/explain.yaml` 的工具白名单 +5；`skills/explain.md` 增加「教师视角」小节
  （先数字后名单、只引用需要的人、口径要交代、教师端不要用 `suggest_action`）。
  > 后续调整（2026-10-08）：答疑回答**不再附「口径说明」**（改为默认不写、仅被问起时用一句话说明），
  > 也不再固定追加「一句话建议 / 补充说明」这类收尾段 —— 以 `skills/explain.md` 现行文本为准。
- 前端：新增 `assets/js/shared/agent-chat.js`（答疑视图工厂，两端共用）+ `assets/js/teacher/views/chat.js`；
  `teacher.html` 新增导航「智能答疑」（`data-view="chat"` → `#view-chat`）；学生端 `chat.js` 收缩成配置薄壳，行为不变。
- 注册与验收：`runtime.py` / `sdk_runner.py` / `check_agent_roles.py` 的显式 import 加 `teacher_analytics`；
  `check_agent_roles.py` 的 `KNOWN_TEACHER_TOOLS` 改成**按任务流**声明（explain / generate_items 各一份），
  并增加「学生硬调 `class_alerts` 被拒」断言。

**隐私边界（本轮新开的口子）**

- 课程由服务端注入（`ctx.extra['courseId']`），工具签名里**没有** course_id / user_id；
- `student_profile` 先校验该生在 `kp_stats.course_student_ids` 内，否则返回「该学生不在当前课程中」——
  **错误信息不回显该生姓名 / 学号**；`student_id` 也接受学号；
- 五个工具全部只读；结果一律在**工具内**强制截断（`class_alerts` ≤50 条、`kp_heatmap` ≤20 行 × ≤80 人、
  `hot_wrong_questions` ≤30 条、`student_profile` 薄弱点 ≤10 条）。

**已知口径差异（回答时必须交代）**：`class_overview.avgQuizAccuracy` 走 `services/scoring`
（按题去重取最近一次；主 KP 权重 1.0 / 标签命中 0.3），而教师端「教学驾驶舱」页面的 `kpRanking` 是
`answer_records` 简单计数 + 对参与学生非加权平均 —— **两套算法、数字可能不同**。
工具返回里带 `accuracyBasis` / `basis` 原文，`skills/explain.md` 要求报数字时顺带说明口径。

**验收结果（2026-10-06 实测）**

- `check_agent_roles.py`：17 项全过 —— 学生 explain 流清单**不含**这 5 个工具，教师/管理员含 13 个。
  （当时的输出；后续收紧批次改为 teacher-only —— 管理员 explain 流工具数现为 0、教师仍 13 个。）
- 工具直调探针（教师 `ToolContext`，库副本）：`class_overview` 学生数 10 / 平均正确率 66.6% /
  红 25 黄 25 / 涉及 8 人（与 SQL 交叉验证逐项一致）；`class_alerts` 返回姓名 + 学号 + 知识点 + 当前正确率；
  跨课程学生（另一门课的 id）→ `该学生不在当前课程中，无法查看其学情`（不回显姓名）。
- `check_route_roles.py` 21 项全过；`pytest tests` 43 passed。
- 前端（无头 Chrome + 无头实例 8011，**库副本**）：教师端导航「智能答疑」可达、4 个教师向推荐问题、
  发送后正文 661 字符 / 气泡 616px、工具面板与「原文溯源」「超出课程材料范围」均正常；
  学生端答疑页渲染与 `Chat.draft()` 跨页带入（驾驶舱/图谱依赖的入口）无回归。

**遗留（未在 P2b 处理）**：① 答疑页会**自动加载最近一次历史会话**，而会话跨 flow 共用，
教师的历史会话可能是出题会话 —— 在答疑页里展示略突兀（既有行为，学生端同样）；② SSE 先 `error` 后 `done`
时前端会先 `fail()` 再 `finish()`，多出一条**空的 AI 气泡**（既有行为，两端都有）。

---

### P2c · 写操作审批闸门（本轮）

**目标**：Agent 能提出「要做什么」，但**必须用户点确认**才真正落库。

**技术前提（已核实）**：`openai-agents 0.3.3` 的普通 `FunctionTool` 没有 `needs_approval`，
也没有可持久化的 `RunState` → 跨请求审批自己落地；**不建表**，用现有列 `chat_messages.tool_log`（JSON 文本）。

**交付物**

- `registry.py`：`ApprovalSpec(summarize, precheck, impact)` + `ToolSpec.approval`；
  `execute()` 对带 `approval` 的工具**不执行**，改为「先跑前置校验 → 通过则推入 `ctx.turn['pending_actions']`
  → 返回 pending 结果给模型（并明确告诉它『不要说已完成』）」；新增 `tool_ok()` 统一「算不算成功执行」。
  服务端回放（approve 时才真正执行）靠 `ctx.turn['approval_replay']` 标记。
- `draft.py`：给 `save_question_draft` 挂 `ApprovalSpec`（摘要 = 章节 · 知识点 · 题号 · 题面；
  `precheck` = 原有 `_plan_ready + _novelty_ready`；`impact` = 写哪个表、能不能回退）。
- `store.py`：`find_action(user_id, course_id, action_id)` 与 `set_action_status(...)`。
- 运行层：`runtime` / `sdk_runner` 把 `pending_actions` 转成 `kind=confirm` 的 `action` 事件，
  并把**含完整参数**的动作条目并入该条 assistant 消息的 `tool_log`（approve 以它为准，不信前端）。
- 接口：`POST /api/v1/agent/actions/{action_id}/approve` 与 `/reject`（挂 teacher/admin 闸门）。
- 前端：`shared/agent-chat.js` 导出 `confirmCardHtml` / `bindConfirms`（答疑页与出题页共用一套渲染与交互）；
  教师端出题页接上 `onAction` 渲染卡片；`teacher.py` 的 `/question/gen` SSE **补转发 `action` 事件**
  （此前只转 draft / text / tool_start / tool_end / citations）。
- 演示模式（无 LLM key）的出题分支同样过闸门：先真实调 `submit_item_plan` 占位、再走 `save_question_draft`，
  由闸门排成待批准 —— 演示模式**不再直接写草稿**（行为变更，已同步 `tests/test_st_agent.py`）。

**关键设计：前置校验放在「拦截那一刻」**

`save_question_draft` 的构思 / 查重校验依赖**同轮内存**（`ctx.turn`），而审批发生在新请求里、那时已经为空。
所以闸门在拦截时先跑 `precheck`：不通过就**不排队**（把 blockers 直接交回模型修正），通过才排；
approve 回放时只做结构校验与写入，不重跑构思 / 查重。

**验收结果（2026-10-06 实测，全程库副本）**

| 验收标准 | 结果 |
| --- | --- |
| 1. 未确认时不写草稿、`tool_log` 有 `status=pending` | ✅ 出题流跑完草稿数不变；`tool_log` 内为 `{kind: action, status: pending}`（含完整参数） |
| 2. 确认 → 真正执行；拒绝 → 无副作用 | ✅ 确认后草稿 3→4，卡片显示的 `draft_id` 与库里最新草稿**完全一致**；拒绝后草稿数不变、状态 `rejected` |
| 3. 换用户 / 换课程 approve 别人的 action → 403 | ✅ 另一个教师 403、同一教师换课程 403、学生 403（角色闸门） |
| 4. 重复 approve 幂等 | ✅ 第二次 `idempotent: true` 且草稿数不变；已拒绝的再 approve → **409** |
| 工具层 | ✅ 前置未过不排队；排队阶段不写库；只有 `approval_replay` 才写库 |
| UI（无头 Chrome） | ✅ 出题页出现「待批准」卡片（摘要 / 影响面 / 工具名 / 确认·拒绝）→ 点确认变「已执行」并显示草稿号；答疑页历史消息能从 `tool_log` 恢复卡片 |
| 回归 | ✅ `check_agent_roles.py` 全绿、`check_route_roles.py` 全绿、`pytest tests` **44 passed** |

**为什么本轮只纳入一个工具**：全系统只有 `save_question_draft` 真的写库
（`submit_item_plan` / `check_novelty` / `validate_question` 只写内存）。按文档要求「先只把低风险、
可回滚的动作纳入」，「发消息给学生」「发布题目」等要等审批 UI 稳定后再放开 —— 放开方式就是给它挂 `ApprovalSpec`。

**已知取舍**：① 班级统计口径差异同 P2b（见上）；② 审批的幂等靠「读-改-写 tool_log」，
**多 worker 部署时并发确认同一动作存在竞态**（当前 uvicorn 单 worker，未处理）。

---

### P3 · 前端体验与学生自助报告（本轮）

**目标**：① 答疑/出题里的两种「可点的东西」一眼能分清；② 学生能自助生成并导出自己的学情报告。

**交付物**

- **只读建议 vs 待批准写操作的双重区分**：`shared/agent-chat.js` 给只读建议区加了
  `只读建议 · 点击跳转，不会修改任何数据` 的标识（`.msg__acts-tag`，带 `eye` 图标、独占一行）；
  待批准写操作仍是独立的 `.confirm-card` 卡片（盾牌图标 + 状态标签 + 摘要 + 影响面 + 工具名）。
  两者在**文案、图标、容器样式**三处都不同，不会再被当成同一类按钮。
- **学生自助报告**（新）：后端 `services/student_report.py`（统计）+ `/api/v1/student/reports/*`
  （生成 / 列表 / 详情 / 导出）；前端学生端新视图 `assets/js/student/views/report.js` + 侧栏「学情报告」。
- **教师端报告归档与学生个人报告隔离**：`/report/list` 跳过 `meta.scope == "self"` 的报告。
- **验收脚本补一条**：`check_agent_roles.py` 断言「任何带 `approval`（写操作）的工具，`roles` 都不含
  `student`，且在学生可用的任何任务流里都不出现」。

**报告归属怎么落地（本轮的关键取舍）**

`reports` 表只有 `class_id`，而真实库里 4 条报告的 `class_id` **全是 NULL** —— 归属一直是靠
`detail_json.meta` 里的 `courseId` 过滤出来的。本轮**不动表结构**（本仓库没有 Alembic，建表靠
`Base.metadata.create_all`，加列不会自动迁移到已有库），沿用同一套：学生报告把
`meta.scope = "self"` + `meta.userId` + `meta.courseId` 写进 `detail_json`，读写两侧都按内容过滤。

- 学生侧：`/student/reports/{id}` 与 `/export` 都先校验 `scope=="self" and userId==当前用户`，
  否则 **403**（不是 404 —— 报告确实存在，只是不属于你）。
- 教师侧：归档列表显式排除 `scope=="self"`。
- **代价（必须知道）**：这不是数据库级隔离，靠代码过滤。报告一多就会全表扫描 + 逐条 `json.loads`
  （当前 6 条，无影响）。真要库级隔离得给 `reports` 加 `user_id` 列并写迁移，**属于动表结构，
  按约定须先经用户同意**（清单 **P17**「题库/报告接口无课程归属校验」已登记；学生侧本次已加校验，教师侧 `GET /report/{reportId}` 仍未关闭）。

**报告内容与口径**

全部数字从真实业务表按**当前登录学生本人**统计，复用既有口径、不新写一套：
掌握率走 `services/kp_stats.mastery_by_kp`（= max(答题正确率, 资源完成率)），
正确率走 `services/scoring.overall_accuracy`（按题去重、每题取最近一次），
学习时长走 `best_position_sum`（视频最佳观看位置）+ `answer_records.duration_seconds`，
预警与教师端 `class_alerts` 同一口径（`status != "ignored"` 且 `level in (red, yellow)`）。
时长统一按全站约定输出 `分'秒"`（后端新加 `utils.fmt_dur`，与前端 `U.dur()` 同格式）。

**刻意不做筛选**：教师端报告页的「章节 / 日期」选择器只写进 meta、**并不参与计算**
（既有行为，见 `routers/intervention.py::generate_report`，本次未改动它）。为了避免复制这套会误导人的参数，
学生报告页**没有**任何筛选，直接给「截至当前」的课程全量快照。

**验收结果（2026-10-06 实测，全程库副本）**

| 验收标准 | 结果 |
| --- | --- |
| 数字真实（与 SQL 交叉验证） | ✅ 完成率 88.5%（23/26）、作答 103 题 96 对 → 93.2%、时长 27636+7295=34931s → `9:42'11"`、预警 0 条，逐项与 SQL 一致 |
| 学生只看得到自己的报告 | ✅ stu01 / stu02 各生成一份，各自 `total=1` 且只含自己的 reportId |
| 越权 | ✅ stu02 读/导出 stu01 的报告 → **403 无权访问该报告**（详情与导出两条路径都拦） |
| 教师归档不被污染 | ✅ 教师 `/report/list` 仍为 4 条班级报告，不含两份学生报告 |
| 学生仍进不去教师报告接口 | ✅ `/report/list` 对学生 **403 角色闸门** |
| 导出 | ✅ 学生导出自己的报告：PDF 30 KB / HTML 1.7 KB 正常下载；UI 点「导出网页」弹出「网页已下载」 |
| 隔离结构 | ✅ 落库 `class_id=NULL`、`detail_json.meta.scope="self"`（与教师班组报告同表区分） |
| 只读建议与写操作区分 | ✅ 答疑页只读建议行显示「只读建议 · 点击跳转，不会修改任何数据」；写操作仍是盾牌确认卡片 |
| 回归 | ✅ `check_agent_roles.py` 21 项全过、`check_route_roles.py` 21 项全过、`pytest tests` **44 passed** |
| UI（无头 Chrome） | ✅ 侧栏新增「学情报告」可达（8 个导航）、点「生成报告」→ 详情弹窗 5 个章节、归档列表刷新；我的学情/驾驶舱无回归、无未捕获异常 |

**点一次只写一份（防止重复写入的取证方式）**：带写操作的 UI plan 必须用**库计数夹住** ——
跑前 `select count(*) ... where meta.scope='self'` → 点一次 → 跑后再数，本次实测 **2 → 3（+1）**。
（这次一度以为"点一次生成两份"，实际是执行 plan 的那条命令被重复执行了两遍，靠计数才分清。）

---

### P4 · MCP 导出与部署（本轮）

**目标**：把 `registry` 里同一批工具挂成 MCP server 给 Claude Desktop / Cursor 用，并给部署收口。

**交付物**

- `backend/app/agent_st/mcp_server.py`（新）：stdio MCP server，**工具实现零改动**（直接调 `registry.execute`）。
- `dev_tools/check_mcp_tools.py`（新）：**真实 MCP 客户端** ↔ 真实 server 子进程的端到端验收（24 项）。
- `backend/requirements.txt`：新增 `mcp==1.12.4`（版本为什么钉死见下）。
- `docs/部署与MCP.md`（新）：生产 checklist + 客户端配置示例 + 排错表。

**作用域模型：本地进程信任 + 显式作用域**

MCP 客户端没有本系统的 JWT，所以作用域在启动参数里固化：

```
--user <用户名或 user_id>    --course <课程 ID>    --flow explain|generate_items
```

- 启动时查库校验「用户存在」**且**「是本课程成员」——与 HTTP 层 `get_current_course_id` 同源；
  不成立就 **退出码 2** + 可读报错，**不用默认值兜底**。
- 工具签名里没有 `course_id` / `user_id`，客户端与模型都改不了作用域。
- **不校验密码**（本地进程信任）：能把配置写进 MCP 客户端的人本来就能读 `.env` 与数据库文件。
- **写工具（带 `approval`）不进 `list_tools`**：MCP 侧没有确认卡片、也没有 approve 入口，
  暴露出来只会排一条永远批不了的 pending。

**工具可见性** = 「该 `--flow` 的白名单」∩「该角色可用的工具」，与 `/ai` 答疑同一套过滤：

| 作用域 | `--flow explain` | `--flow generate_items` | `--flow admin_ops` |
| --- | --- | --- | --- |
| 教师 | 13 个（含 5 个教师专用） | 7 个（**不含**写工具 `save_question_draft`） | 0 个 |
| 学生 | 8 个（看不到任何教师专用工具） | 3 个（`get_question` / `resolve_topic` / `retrieve_chunks`） | 0 个 |
| 管理员 | 0 个（角色收紧后不再进教学流） | 0 个 | 7 个（5 个只读查询 + 2 个 `preview_*`；两个写工具不暴露） |

**一个必须知道的依赖坑（本轮实测）**

文档原先写「`mcp 1.30.0` 已装」，但实测**与本项目的钉版冲突**，装不上：

| 版本 | 冲突点 |
| --- | --- |
| `mcp 1.13 ~ 1.30` | 在 `python<3.14` 上要求 `pydantic>=2.11.0`，本项目钉的是 `pydantic==2.9.2` |
| `mcp 2.x` | 会把 `starlette` 升到 `1.x`，与 `fastapi 0.115`（要求 `starlette<0.39`）冲突 |

→ 取**能装上的最高版本 `mcp==1.12.4`**（要求 `pydantic>=2.8`，与 `starlette 0.38.6` 兼容）。
升级 mcp 必须先一起升 pydantic + fastapi + starlette，属单独的依赖升级决策。

**实现上踩的两个坑（都已落进代码注释）**

1. **低层 `Server` 的 `call_tool` 不能返回 `CallToolResult`**：SDK 会把返回对象当可迭代对象拆成
   `(字段名, 值)` 元组，报 20 条 pydantic 校验错误。成功要返回**内容块列表**（或 `(列表, 结构化 dict)`），
   失败要**抛异常**（SDK 自己包成 `isError=True` 并把异常文本透给客户端）。
2. **`app.*` 必须惰性导入**：`app.config.settings` 在导入时就固化 `DATABASE_URL`，
   而 `--db`（验收指向库副本）得在那之前生效 → 模块顶层不放任何 `app.*` 导入。

**验收结果（2026-10-06 实测，全程库副本）**

| 验收标准 | 结果 |
| --- | --- |
| 工具清单 = 注册表推导（4 种作用域） | ✅ 教师 explain 13 / 学生 explain 8 / 教师出题 7 / 学生出题 3，与 `registry.TOOLS` 推导**逐项相等** |
| 写工具不暴露 | ✅ `save_question_draft` 在两条 flow、两种角色下都**不在** `list_tools` 里 |
| 角色隔离 | ✅ 学生清单与教师专用集合交集为空；学生硬调 `class_alerts` → `isError` 且原因可读 |
| 真取数（与 SQL 交叉验证） | ✅ `class_overview`：学生数 10、红/黄 25/25；`my_alerts`（stu08）11 条且带真实 `alertId` |
| 结构化输出 | ✅ 带 `structuredContent`，客户端可直接读对象 |
| 只读标注 | ✅ 所有工具 `readOnlyHint=True` |
| 作用域校验 | ✅ 用户不存在 / 不是课程成员 / 课程不存在 → 退出码 2 + 可读中文报错 |
| 换目录可启动 | ✅ 只用 `PYTHONPATH`（不依赖 cwd）也能起 server（MCP 客户端常用这种配法） |

**本轮没做**：HTTP/SSE 型 MCP + 一次性令牌（只做了 stdio）；容器化；写工具的 MCP 化。

---

### 收尾修复：答疑页「报告按钮」（2026-10-06 晚）

用户在真实使用里连报两次，追出**三个缺陷**（都不是新功能，是前面阶段的收口没做干净）：

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| A | 问「帮我生成学习报告」，AI 给不出指向「学情报告」页的按钮；手工造一个 `view=report` 的按钮点下去被拒，弹「这个建议暂时无法直接打开」 | **白名单前后端两份、都不含 `report`** —— P3 加了页面却没同步白名单（后端 `analytics._VIEWS`、前端 `chat.js::applyAction`） | 两处各加 `report`；`skills/explain.md` 补一张 `view` ↔ 页面 ↔ 能力对照表，并明确「生成/导出报告」类问题应指向该页 |
| B | 刷新页面 / 重开会话后，只读建议按钮**消失**（正文里那两条「• 「…」」变成纯文本、点不动） | `GET /ai/sessions/{id}/messages` **不返回 `actions`**（字段只有 citations/content/method/role/time/toolLog）；而 `suggest_action` 的参数其实**在 `toolLog` 里**，只读建议却没像 P2c 的确认卡片那样从 toolLog 重建 | `shared/agent-chat.js` 新增 `suggestCardsOf(m)`：优先用实时的 `m.actions`，否则从 `toolLog` 里 `name=="suggest_action"` 且 `ok!=false` 的条目重建（`kp_id` → `kpId`） |
| C | 正文写「下面按钮只是入口，需要你自己点击才会跳转」，但**一个按钮都没有**（这次模型压根没调 `suggest_action`） | 提示词只写了「按钮只是建议、不得声称已经替用户做了」，**没写"没调用就不许提按钮"**；也没约束 `label` 必须与 `view` 指向同一页面（曾出现 label 写「去我的学情看完整报告」而 `view=dashboard`） | `skills/explain.md` 补两条规则：① 没真的调用 `suggest_action` 不许在正文里提按钮；② `label` 必须与 `view` 指向同一页面 |

**新增常驻断言（防复发）**：`check_agent_roles.py` 第 8 组 ——
后端 `analytics._VIEWS / _MODES` 与前端 `chat.js` 的白名单**逐项相等**，且白名单里的每个 view
都有真实注册的视图（`Router.register`）。自测：故意从前端摘掉 `report` → 脚本 **退出码 1**，还原后全绿。

**实测（2026-10-06 晚，无头 Chrome + 库副本）**：

| 项 | 结果 |
| --- | --- |
| B 历史重建 | ✅ 16:28 那条历史消息此前一个按钮都没有，现在渲染出「只读建议」标识 +「去练 KP003 线性表靶向练习」；点 `dashboard`/`mastery` 两个历史按钮分别落到 `#dashboard` / `#mastery` |
| A 报告可达 | ✅ 点 `view=report` 的按钮 → `#report`「学情报告」，**无拒绝 Toast** |
| C 真模型 | ✅ 真问「帮我生成学习报告」→ 模型给出 `{view:"report", label:"去「学情报告」生成完整报告"}`，正文写「点下面的「…」按钮过去生成即可」，页面同时出现「只读建议」标识 |
| 回归 | ✅ `check_agent_roles` 24 项（21+3）、`check_route_roles` 21 项、`check_mcp_tools` 24 项全过；`pytest` 见下方 |

> ⚠️ 这一轮只介绍了**提示词 + 白名单 + 前端渲染**；A 的后端白名单改动**需要重启后端**才生效。

---

### 收尾修复（二）：「超出课程材料范围」提示条与「转人工」按钮（2026-10-06 晚）

用户在真实使用里又报了两件事，追出三个缺陷：

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| A | **教师**问「哪个知识点全班掌握最差」，回答是正确的班级查库结果，却被打上「超出课程材料范围」 | 越界判定的「查库即例外」集合是**硬编码的 4 个学生工具**（`my_alerts/breakdown/explain_metric/weak_ranking`），P2b 加的 5 个教师视角工具**没算进去** —— 教师问班级学情的回答不检索教材，必然落进"检索分为 0"的判定 | 集合改为 `runtime.analytics_tool_names()`：学生 4 个 + **从注册表动态推导**的教师视角工具（`explain` 流里 `roles` 不含 `student`）；以后加教师工具自动生效 |
| B | 提示条里的「可点击下方转人工」指向一个**点了没反应的按钮** | 该按钮只有 `<button>` 标签：**没有 `id`、没有 `data-*`**，也不在 `bindCites()` 的绑定集合里；后端**没有任何转人工接口**（`messages` 表只有教师→学生的单向私信 `POST /teacher/messages`）；唯一的"会提交给李老师"承诺写在 `api.js` 的**离线兜底 mock** 里 | 按钮删掉；提示条文案改为「…建议换一个更贴近课程知识点的问法」；`api.js` mock 里那条承诺同步删除。**不实现转人工**（要真做需先定"转给谁、老师在哪看、要不要提醒"，属独立需求） |
| C | 刷新页面后提示条**消失** | `outOfScope` 只在 SSE `done` 事件里透出，**不落库**；而历史消息接口只回 `[role,method,content,time,citations,toolLog]`。且它由「话题是否确定 + 检索最高分」算出，这两个输入也不落库 → **事后无法重算** | 结果本身随消息落库：`persist_side_effects` 在该条回答的 `tool_log` 末尾追加 `{kind:'meta', out_of_scope:true}`（**只在为真时追加**）；前端新增 `outOfScopeOf(m)`：实时读 `m.outOfScope`，历史从 `toolLog` 恢复；`toolsPanelHtml` 过滤掉 `meta` 条目（否则它会显示成一条"工具 undefined 完成 {}"，面板计数也会多 1） |

**新增常驻断言**：`check_agent_roles.py` 第 9 组 —— `explain` 流的**全部教师专用工具**都必须在越界例外集合内。
灵敏度自测：故意把动态推导去掉（退回硬编码 4 个）→ 脚本**退出码 1** 并打印缺哪些工具；还原后全绿。

**实测（2026-10-06 晚，库副本 + 无头 Chrome）**

| 项 | 结果 |
| --- | --- |
| 判定探针 | 教师 `kp_heatmap` / `class_alerts` / `student_profile` / `class_overview` 四种场景 → 全部 `False`（修前全 `True`）；学生「红烧肉怎么做」仍 `True`、`my_alerts` 仍 `False`（行为未变） |
| 落库 | 越界问句 → `done.outOfScope=true` + 该条消息 `toolLog` 里 `{'kind':'meta','out_of_scope':True}`；非越界问句 → **无 meta**（对照） |
| UI（真实提问 + 演示模式） | 提示条文案已更新、**无「转人工」按钮**（右下只剩点赞/点踩/复制）、工具面板计数 2 且 `meta` 不外露、无未捕获异常 |
| UI（重新加载页面） | 同一会话自动加载后**提示条仍在**（从 `toolLog` 恢复）—— 修前会消失 |
| 回归 | `check_agent_roles` 26 项（24+2）、`check_route_roles` 21 项全过；`pytest tests` **44 passed** |

> ⚠️ A 与 C 的服务端改动**需要重启后端**才生效（前端是热生效的）。

---

## 5. 待做阶段划分

依赖关系一句话：**P2b / P2c / P3 / P4 全部完成**；后续是第 6 节的已知问题与第 4 节各小节的「本轮没做」。

### P2b · 教师视角工具 + 教师端答疑页 —— 已完成（2026-10-06）

交付物、隐私边界、口径差异与验收结果见前面 **第 4 节「P2b」** 小节，此处不再重复。

### P2c · 写操作审批闸门 —— 已完成（2026-10-06）

交付物、关键设计与验收结果见前面 **第 4 节「P2c」** 小节，此处不再重复。

### P3 · 前端体验与学生自助报告 —— 已完成（2026-10-06）

交付物、报告归属口径与验收结果见前面 **第 4 节「P3」** 小节，此处不再重复。

### P4 · MCP 导出与部署 —— 已完成（2026-10-06）

交付物、作用域模型、依赖版本坑与验收结果见前面 **第 4 节「P4」** 小节，此处不再重复。

**四个阶段（P2b / P2c / P3 / P4）全部完成。** 后续方向见第 4 节各小节的「本轮没做」与第 6 节已知问题。

---

## 6. 已知问题（与 `待修复清单.md` 的对应）

| 编号 | 说明 | 与 Agent 改造的关系 |
| --- | --- | --- |
| P38 | 教师端路由没有角色校验 | ✅ 本轮已修（学生 403） |
| P44 | 预警生命周期没有兜底：证据消失后预警消不掉 | ⚠️ P2b 的 `class_alerts` 直接读 `alerts` 表，**受本问题影响**（陈旧预警会被当成有效预警列给教师）；建议尽早处理 |
| P45 | 题目归属两套视角（题库按主 KP、学情按主∪标签） | 影响 `hot_wrong_questions` 的口径说明，回答里要写清口径 |
| P46 | 薄弱点强化会排进「已做对」的题 | 已被用户明确决策：**不改** |
| P47 | 薄弱点清单只取前 5，会漏掉有预警的子知识点 | 影响「预警 → 练习」按钮的完整性 |
| P48 | 纯标签命中的子知识点预警门槛过松 | 影响预警数量与教师端噪声 |

完整清单与「归属 / 界面 / 影响」三段说明见 `待修复清单.md`。

---

## 7. 验证、调试与协作资产

### 7.1 四个脚本

| 脚本 | 用途 | 是否需要模型 | 会不会写库 |
| --- | --- | --- | --- |
| `dev_tools/check_agent_roles.py` | 工具/任务流角色校验自检 + **界面动作白名单前后端一致性** | 否 | 否 |
| `dev_tools/check_route_roles.py` | 教师端前缀 + `/agent/ingest/*` 的角色闸门（真实登录 + TestClient） | 否 | 只在库副本 |
| `dev_tools/smoke_agent_sdk.py` | 两条运行层对照冒烟（`--runtime`、`--user`、`--flow`、`--role`、`--max-events`） | 是 | 默认库副本，`--db` 才指真实库 |
| `dev_tools/check_mcp_tools.py` | MCP 导出端到端（真实 MCP 客户端拉起 server 子进程；作用域/越权/真取数/拒绝启动） | 否 | 只在库副本；**需要装了 `mcp` 的解释器** |

### 7.2 铁律：验证一律在**库副本**上做

```bat
REM 演示库（真实数据，别直接改）
backend\app\data\course_agent.db
REM 演示账号：管理员 admin/admin；教师 wangjg/123456；学生 stu01…stu10/123456
REM 课程：CCHYJTKE
```

`smoke_agent_sdk.py` 与 `check_route_roles.py` 默认自己复制一份到临时目录再跑，不用手动处理。

**演示库不在版本库里**：`backend/app/data/*.db` 被 `.gitignore` 排除，新克隆的仓库里**没有**
`course_agent.db` —— `check_route_roles.py` / `smoke_agent_sdk.py` 会直接报「找不到数据库」。
首次验收前先放一份到 `backend/app/data/course_agent.db`（从队友那里要一份现成的，或按
`待修复清单.md` 的口径用 `dev_tools/` 下的初始化脚本生成）；文件本身不会被提交。

**解释器**：本文命令统一写 `backend\.venv\Scripts\python.exe`。若本地还没有这个 venv，
用系统 Python 3.11 装 `backend/requirements.txt` 也可以跑通（三个 `check_*` 脚本只依赖
fastapi / sqlalchemy / httpx / mcp 等常规依赖）。跑 `pytest` 需额外安装 `pytest`，
并按 `backend/pytest.ini` 的提示传一个全新的 `--basetemp` 目录。

⚠️ `check_mcp_tools.py` **必须用装了 `mcp` 的解释器**运行（`requirements.txt` 里已含 `mcp==1.12.4`）；
它自己会用 `sys.executable` 拉起 MCP server 子进程，也可以用 `--python` 指定别的解释器。

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
- **演示模式下 AI 出题也不再直接落草稿**（P2c）：写操作一律先排成「待批准」卡片，要在卡片上点「确认执行」才写入 `st_question_drafts`；`draft` 事件也只在那之后才推。
- **回答里直接冒出 `401 Authentication fails` / `api key ... is invalid`**：说明 `backend/app/.env` 里的
  `LLM_API_KEY` 还在但已失效 —— 此时**不会**退回演示模式（`chat_available()` 只判断 key 非空），
  而是真的去调模型然后失败。本地想看演示模式：起实例时显式 `LLM_API_KEY=""`。

---

## 8. 开工检查清单

- [ ] **如果不懂智能体**：先读 `docs/智能体入门与AI协作手册.md`（大白话版），知道「工具 / 任务流 / 技能 / 事件契约」分别是什么。
- [ ] 把 `AGENTS.md` 交给你的 AI 助手（或让它自己读），确认它按「5 行汇报 + 先给计划」的方式跟你说话。
- [ ] 读 `待修复清单.md` 的「怎么读这份清单」，知道每条都有「归属 / 界面 / 影响」。
- [ ] 跑通 `check_agent_roles.py` 与 `check_route_roles.py`（应全绿）。
- [ ] 跑一次 `smoke_agent_sdk.py`（sdk 与 legacy 各一次），看到工具调用、引用、建议动作、完整回答。
- [ ] 确认 `AGENT_RUNTIME` 的含义（默认 legacy，sdk 需装包 + 配 key）。
- [ ] 确认三条铁律（前端可改 / 后端先给影响分析 / 不改数据库格式）。
- [ ] 四个阶段都已完成；接手请看第 6 节已知问题与第 4 节各小节的「本轮没做」。

有任何一条对不上，先在群里问，不要凭猜改后端。
