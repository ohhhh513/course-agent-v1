## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；同一问题继续修改时更新原记录，跨日期新增一项；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、教师智能助手出题支持真正暂停（2026-10-20）

- 后端：`backend/app/routers/teacher.py`：出题请求增加可选任务标识，并新增教师专用 `/question/gen/stop` 接口；只接受当前教师、当前课程的活动任务，普通题库出题未携带标识时行为不变。
- LLM/Agent：`backend/app/agent_st/agent/cancel.py`、`runtime.py`、`llm.py` 与 `sdk_runner.py`：暂停信号关联出题任务，立即关闭可中断的模型流；模型返回后、执行工具前再次检查停止状态，避免暂停后继续思考或调用工具。
- LLM/Agent：`backend/app/agent_st/agent/tools/batch_draft.py`：批量保存前检查任务状态，并将最终写入与停止请求同步；暂停先生效时不保存未提交批次，已经完成写入的草稿保留。
- 前端渲染：`assets/js/shared/agent-chat.js`、`agent-ui.js` 与 `assets/js/api.js`：智能助手发送按钮在出题生成期间保持停止状态；点击后重试确认后端任务已登记并停止，再关闭出题 SSE；预览中的生成状态也提供停止按钮，保存的草稿继续展示。
- 前端渲染：`assets/js/shared/agent-ui.js`：停止生成完成后只刷新已经打开的预览，不再自动弹出右侧预览；正常生成完成仍按原行为打开预览。
- 前端渲染：`assets/css/app.css`、`student.html`、`teacher.html` 与 `admin.html`：调整停止按钮布局并更新三端脚本缓存版本。
- 数据库·数据：仅使用内存任务状态与现有草稿保存逻辑，不新增或修改数据库表、列及字段；检查均使用临时数据库副本。
- 验证：Conda `py_compile`、三份前端脚本 `node --check`、`git diff --check`、角色权限检查、路由权限检查、MCP 端到端检查及教师智能体冒烟均通过；教师出题停止接口临时库集成检查确认上游流已关闭、SSE正常结束且草稿数不变；停止发生在批量校验期间的检查确认不会写入草稿。当前环境未安装 `openai-agents`，SDK 冒烟按配置回退 legacy；浏览器连接因 Browser 插件缺少运行脚本未能建立，尚未完成真实界面点击与硬刷新验收。

## 二、教师智能助手增加学生学情分析并每五分钟增量更新（2026-10-20）

- 后端：`backend/app/services/daily_learning_analysis.py` 与 `backend/app/main.py`：学情任务改为每 5 分钟按北京时间扫描；按课程成员读取新增问答，通过消息 ID 游标只增量分析新内容并更新当天摘要，每轮最多分析 40 条新问答；应用启动后仍补算最近 7 天的真实历史记录。
- 后端：`backend/app/agent_st/agent/tools/teacher_analytics.py` 与 `backend/app/services/scoring.py`：学生画像支持最近 1～30 天的课程内答题统计、学习路径进度及 AI 互动摘要；答题正确率和最近答题记录按当前课程过滤，避免同一学生跨课程数据混入。
- LLM/Agent：`backend/app/services/daily_learning_analysis.py`：使用现有模型概括新增问答涉及的知识点、章节和可能疑惑；只保存结构化摘要，不保存或向教师返回原始问句；模型不可用时按本课程知识点词表生成有限度的规则摘要，并标记依据范围；没有新增问答时不重复调用模型，不创建模拟学生或问答数据。
- LLM/Agent：`backend/app/agent_st/agent/flows/explain.yaml`、`skills/explain.md` 与 `tools/teacher_analytics.py`：教师询问某个学生近期情况时调用 `student_profile`；结合近期学习、答题及增量更新的 AI 互动摘要回答，标明摘要覆盖日期和最近扫描时间，区分实际答错与提问线索，不把单次提问断言为薄弱。
- 数据库·数据：复用 `teacher_class_data.data_json` 保存按课程、学生汇总的近 30 日摘要、消息 ID 游标与运行时间；不新增或修改数据库表、列及字段。问句只在分析时交给系统现有模型处理，摘要不含原始问句。
- 启动脚本·文档：`backend/requirements.txt` 使用 `APScheduler==3.10.4`，用于每五分钟增量任务及启动时的历史摘要补算。
- 验证：Conda `stucourse` 下 `py_compile`、解释流 YAML 解析、`git diff --check`、角色权限、路由权限（临时库副本）和 MCP 端到端检查通过；APScheduler 间隔为 300 秒。在临时库副本上仅分析现有真实问答 1 条，重复扫描新增数为 0 且未改写摘要；教师真实模型问答成功调用 `student_profile` 并返回该真实摘要。全程未插入模拟学生、会话或问答记录，真实数据库未用于验证。
