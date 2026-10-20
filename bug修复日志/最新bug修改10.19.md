## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；同一问题继续修改时更新原记录，跨日期新增一项；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、三端智能助手右侧历史与预览面板（2026-10-19）

- `assets/js/shared/agent-chat.js`：历史会话改为聊天卡片右侧滑入的停靠面板，与聊天内容连成一体；「历史对话」与强调色「新建对话」并排放在右上角；支持拖动分隔线或用左右方向键大幅调整宽度，扩展栏超过可用宽度的 80% 后切换为全屏，仍可从左边缘拖回；关闭后再打开重置为 360px；拖动按帧更新并缓存边界位置，避免每次指针移动都触发布局读取。

- `assets/js/shared/agent-ui.js`：教师端生成题目预览复用历史面板的停靠位置、宽度、全屏阈值和右上角收起按钮；两类面板互斥，切换时同步关闭状态并播放一致的滑入、收起动画；关闭预览时同步把扩展栏宽度复位到 360px。

- `assets/css/app.css`：统一历史与预览面板的边框、背景和滑动效果；桌面端形成无缝连续的双栏卡片，窄屏时改为覆盖聊天卡片的整栏显示；面板达到阈值后固定铺满视口，并保留可拖回的左边缘；分隔线采用系统浅色细线，并延后到面板滑入后显示；拖动期间关闭网格和面板过渡动画，使宽度实时跟随指针；右上角按钮组保持间距，历史按钮在展开时显示选中状态。

- `assets/js/common.js`、`student.html`、`teacher.html`、`admin.html`：增加扩展栏收起图标并更新三端资源缓存版本，确保显示新图标、样式和交互。

- 验证：`node --check assets/js/shared/agent-chat.js`、`node --check assets/js/shared/agent-ui.js` 与 `git diff --check` 通过；未完成浏览器实测。

## 二、教师智能助手刷新后恢复题目预览（2026-10-19）

- `assets/js/shared/agent-ui.js`：按登录用户、课程、对话和操作计划将已生成题目及草稿状态保存在当前标签页会话中；刷新历史会话时直接显示并绑定「预览题目」，不再执行生成操作；生成中途刷新时恢复已产出的题目并提示未完成数量；旧操作没有对应预览快照时阻止再次生成并提示查看草稿箱；同步保存编辑和发布后的状态；移除生成题目预览中的「组成试卷」入口及其组卷逻辑。

- `teacher.html`、`student.html`、`admin.html`：更新共享智能体脚本缓存版本，确保刷新后加载预览恢复逻辑。

- 数据库·数据：仅使用浏览器 `sessionStorage` 保存预览快照，不改后端接口、数据库表或字段；数据限当前浏览器标签页会话。

- 验证：`node --check assets/js/shared/agent-ui.js` 与 `git diff --check` 通过；未完成浏览器硬刷新及真实点击验收。

## 三、三端智能体生成中状态提示（2026-10-19）

- `assets/js/shared/agent-ui.js`：移除智能体对话出题卡片按目标题数估算的进度条，改为旋转加载图标和状态文字；只显示真实已生成题目数，预览面板复用同一提示。
- `assets/js/shared/agent-chat.js`、`assets/css/app.css`：工具执行中在思考与工具调用栏及展开后的工具行显示旋转加载图标；执行完成后恢复结果状态标记，供出题、文档生成等耗时操作显示处理中状态。
- `student.html`、`teacher.html`、`admin.html`：更新三端智能体脚本与样式缓存版本。
- 验证：未进行浏览器实测。

**## 四、AI 批量出题性能优化（2026-10-19）**

- `backend/app/routers/teacher.py`：实模型出题从逐题启动完整 Agent 流程改为一次运行整批；一次定位课程范围、检索资料和题库参考，演示模式仍保留原有逐题预览。
- `backend/app/agent_st/agent/tools/batch_draft.py`、`backend/app/agent_st/agent/flows/generate_items.yaml`、`backend/app/agent_st/agent/skills/generate_items.md`：新增整批草稿工具与出题规则；逐题校验构思、题型、课程知识点、题目结构及新颖度，错误时返回对应题目供模型修正。
- `backend/app/agent_st/agent/store.py`：通过现有草稿表在单个事务中保存整批题目；任一题校验失败时不写入部分草稿，不改数据库表结构。
- `backend/app/agent_st/agent/runtime.py`、`backend/app/agent_st/agent/sdk_runner.py`、`backend/app/agent_st/agent/registry.py`：兼容整批草稿写入并逐题发出原有 `draft` 事件，保持已有事件名称与字段。
- `backend/app/agent_st/agent/llm.py`：复用同步模型客户端连接，减少同一轮工具调用重复建立连接的开销。
- 验证：`py_compile`、`git diff --check`、角色权限自检、路由权限自检、MCP 端到端检查通过；库副本上的真模型与教师端 `/question/gen` 实测各生成 2 道题，收到 2 条原格式 `draft` 事件；错误批次实测未留下部分草稿。当前 Conda 环境未启用 Agents SDK，真模型实测走 legacy 运行层；未进行浏览器实测。

## 五、教师智能助手匿名提问统计（2026-10-19）

- 后端：`backend/app/agent_st/agent/tools/teacher_analytics.py`：教师主动询问提问热点时仅返回当前课程的知识点、章节及次数；移除问句样例，不向工具结果提供学生原始问句。
- LLM/Agent：`backend/app/agent_st/agent/flows/explain.yaml`、`backend/app/agent_st/agent/skills/explain.md`：明确教师按需查询，并且回答只列知识点、章节、提问次数和总数，不展示、引用或改写学生问句，也不推断学生身份。
- 数据库·数据：复用现有课程会话与工具日志，不新增接口或修改数据库结构。
- 验证：`py_compile`、YAML 解析、`git diff --check`、角色权限自检、路由权限自检及 MCP 端到端检查通过；教师端库副本实测提问热点工具被调用，回答仅含知识点、章节和提问次数。模型 SDK 不可用，实测由 legacy 运行层完成。
