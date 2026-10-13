## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、题库管理：导入题目与新建题目改为先入草稿箱（2026-10-13）

**后端**

- `backend/app/routers/teacher.py` 的 `POST /question/import`：从写入 `Question` 表改为写入 `st_question_drafts`（草稿箱），**状态写为 `draft`（与 AI 出题草稿一致）**，由教师在草稿箱中点击「发布」后才进入正式题库；不再分配 `q_id`（发布时由 `next_ai_q_id` 统一分配）；响应增加 `draftIds[]` 数组便于前端定位本次导入的草稿；来源标记 `source: "import"` 写入 payload 以便发布时回填。**`payload` 字段对齐 `rag.validate.validate_question` 契约**：`options` 由 `[{key,text}]` 列表改为 `{"A":text,"B":text,...}` 字典；题干字段名由 `stem` 改为 `question`；`has_image` 由 `0/1` 改为 `bool`；多选答案主答案用占位（`A`）写 `answer`（发布时不依赖单选校验）；blank（填空）题以 `is_blank=True` 走独立分支，保留原始 options/answer 由 `draft_publish` 重新 `pack_blank`。
- `backend/app/routers/teacher.py` 的 `POST /question/import/file`：同上，文件解析后直接写 `st_question_drafts`，payload 同样对齐 validate 契约，`source` 标记为 `"file_import"`；blank 题不调用 validate，固定 `draft`。
- 上述两个端点**均**在写入前调用 `validate_question` 决定 `status`：`draft`（校验通过）/`invalid`（校验未通过），与 `store.save_draft` 行为对齐（2026-10-13 修复：之前一版错写 `pending`，导致草稿箱前端 `draftFilter=draft` 过滤不到、且发布按钮判断 `d.status==='draft'` 不显示）。
- `backend/app/routers/teacher.py` 的 `POST /question/import/preview`：**不动**，它只是只读解析和校验。
- `backend/app/routers/teacher.py` 的 `PUT /question/{q_id}`：**不动**，编辑既有题目的逻辑不受影响。
- `backend/app/routers/teacher.py` 的 `POST /question/drafts/{id}/publish`：**不动**，发布链路已带 `ingest_question_bank` 触发 RAG 索引，发布时自动建索引。

**前端渲染**

- `assets/js/teacher/views/question.js` 的 `openNewQuestionModal` 提交逻辑：删除 `status: "published"` 硬编码字段（后端统一写 `draft` 状态）；Toast 文案从「题目已保存进题库」改为「题目已加入草稿箱，请到「草稿箱」发布后学生方可练习」。
- `assets/js/shared/agent-ui.js` 的导入弹窗提交回调：Toast/状态文案改为 `已加入草稿箱，待审核`，提示教师到草稿箱发布；`Question.loadBank()` 刷新题库仍保留（导入成功后在草稿箱可见）。

**LLM/Agent 相关**

- AI 出题流程（`tools/draft.py` → `POST /question/drafts/{id}` → `POST /question/drafts/{id}/publish`）：**不动**，已完整走草稿箱发布链路。

**启动脚本·文档**

- 本次未修改 `start.bat` / `docs/**`。

**数据库·数据**

- 无任何表结构、字段、索引改动；不写迁移脚本。草稿箱使用现有 `st_question_drafts` 表，无新增列。

**破坏性改动**

- **`POST /question/import` 的写入目标从 `questions` 表改为 `st_question_drafts` 表**；调用方（前端导入弹窗、新建题目弹窗）行为同步更新，教师感知到的变化仅为「导入后题库列表不再立即出现，而是出现在草稿箱」。历史已导入的题目不受影响。

**测试**

- `backend/tests/test_import_to_draftbox.py`：新增端到端测试，覆盖「教师 → `/question/import` → 草稿箱列表能看到 → 发布 → 题库 DB 存在该 q_id」全链路，使用 tmp 副本库 + FastAPI TestClient + JWT，可在隔离环境反复运行。
- 验证：复制库后跑 `python tests/test_import_to_draftbox.py` 全绿；`py_compile teacher.py` 通过；`dev_tools/check_route_roles.py` 通过。
