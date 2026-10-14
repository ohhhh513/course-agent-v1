## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、三端智能体新对话与聊天界面布局（2026-10-12）

- `assets/js/shared/agent-chat.js`：新对话改为中央欢迎区、大输入框及输入框下方的「猜你想问」，右侧保留独立滚动的历史会话；发送问题或打开历史后切换为消息区与底部输入框，点击「新建会话」恢复欢迎布局；推荐仍按原有动态数据生成，点击只回填、不自动发送。

- `assets/css/app.css`：沿用系统青绿色、字体、圆角及按钮样式，调整中央输入框、欢迎图标、推荐卡片、聊天内容宽度与右侧历史栏；窄屏时历史栏放到下方，避免挤压输入和消息；欢迎区内容超出高度可滚动，不遮挡推荐或附件。

- `assets/js/student/views/chat.js`、`assets/js/teacher/views/chat.js` 与 `assets/js/admin/views/assistant.js`：分别设置学生、教师和管理员的新对话欢迎标题与说明；沿用既有推荐来源、附件上传、图片放大、复制、重新编辑、溯源、审批及界面操作能力。

- `assets/js/shared/agent-chat.js`：为推荐与历史消息异步加载增加当前容器校验，避免旧页面请求覆盖重新挂载后的内容；历史为空或读取失败时给出明确提示；生成中禁用新建会话并拦截历史切换，防止当前回答混入其他会话。

- 验证：三端实际配置与共享渲染器在临时 Node DOM 替身中完成推荐回填、附件预览、发送后布局切换、生成中会话保护、重新编辑恢复图片、历史与新对话切换、同次登录恢复、新登录重置及过期历史请求检查；现有 `dev_tools/check_system_actions.js` 检查通过。当前 Browser 连接返回无可用浏览器，尚未完成浏览器显示、真实点击和硬刷新验收，以上逻辑检查不作为浏览器实测。

## 二、三端智能体入口置顶并作为默认首页（2026-10-12）

- `student.html`、`teacher.html` 与 `admin.html`：将各端智能体导航入口移到侧栏首位，并同步初始页面标题；为本轮修改的 CSS、共享聊天脚本、各端配置及启动脚本更新缓存版本。

- `assets/js/student/start.js`、`assets/js/teacher/start.js` 与 `assets/js/admin/app.js`：学生、教师、管理员登录后默认进入各自智能体；师生端继续等待课程上下文就绪再挂载，保留明确页面锚点跳转、同次登录的当前会话恢复以及新登录的新对话行为。

- 修改范围：本次只调整前端与文档，未修改后端接口、模型提示词、流式事件契约或数据库格式；后端相关验证使用独立数据库副本。

- 验证：三端 HTML 首个导航入口和师生端课程上下文就绪后的默认路由检查通过；修改脚本的 Node 语法检查、`git diff --check`、角色权限、路由权限与 MCP 检查通过；库副本上真实问答返回预警与导航动作，SDK 不可用时按当前配置自动回退 legacy。

## 三、移除「猜你想问」与学生端驾驶舱「AI 助教」卡（2026-10-12）

**前端渲染**
- `assets/js/shared/agent-chat.js`：删除欢迎区「猜你想问」整块 DOM（`.chat__recommend` + `#askBox`）以及加载推荐 / 错误兜底逻辑；删除共享配置 `recommended` / `emptyRecommend` / `recommendFail` 默认值，删除工具函数 `recentUserQuestions` / `rankRecommendationCandidates` 及其对外导出。`fillInput` / `Chat.draft`（跨页带入问题）保留。
- `assets/js/student/views/chat.js`、`assets/js/teacher/views/chat.js`：将 `recommended` 置空（`() => Promise.resolve([])`），欢迎区只显示图标 + 标题 + 欢迎语；教师端原推荐生成逻辑（约 80 行：基于驾驶舱统计、薄弱知识点、待办、近期提问排序）整段删除。管理端 `assistant.js` 未提及，**保持现状**。
- `assets/js/student/views/dashboard.js`：删除「AI 助教」卡（含「一键发起提问」与「猜你想问」推荐条目）、删除 `[data-ask]` 事件绑定；将下方网格由 `g-3` 改为 `g-2`，使「薄弱点提示」与「最近学习动态」两卡占满整行。
- `assets/css/app.css`：删除 `.chat__recommend` / `.chat__questions` 及响应式里的相关规则；调整 `.chat__intro` 的 flex/margin 让欢迎区在没有推荐块时仍能在工作区垂直居中。

**后端**
- `backend/app/routers/ai.py`：**删除 `GET /ai/suggest-questions` 端点**（前端已无任何调用方）。`TeacherClassDashboard` 的 import 保留，留给其他路由继续使用。
- `backend/app/routers/student.py`：`/student/dashboard` 返回体中的 `suggestedQuestions` 字段**保留**（不动接口契约、不删字段、避免破坏其他潜在消费者），仅前端不再渲染。
- `assets/js/api.js`：删除 `API.ai.suggestQuestions` 包装方法（已无调用方），改为占位注释说明「猜你想问」已下线。

**启动脚本·文档**
- 本次未修改 `start.bat` / 任何 `docs/**`。
- 后端无迁移、无新表/新列；前端不写补丁代码，全部为规范做法。

**数据库·数据**
- 无任何表结构、字段、索引改动；不写迁移脚本。

**破坏性改动**
- **`GET /ai/suggest-questions` 端点被删除**（前端 0 引用，库副本与冒烟脚本均无调用）。若外部仍期望该接口，需另行通知恢复。
- `AgentChatView.recentUserQuestions` / `AgentChatView.rankRecommendationCandidates` 对外导出移除（仅三端 chat.js 使用，已同步删除）。
