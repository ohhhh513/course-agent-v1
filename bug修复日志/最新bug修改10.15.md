## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、教师端待办查看学生高频知识点错题（2026-10-15）

**前端渲染**

- `assets/js/teacher/views/dash.js`：低正确率和错题集中预警待办的「去处理」改为「查看详情」，点击直接打开学生错题弹窗；顶部展示全部有错题的知识点，按累计错误次数排序，支持多选、全选和清空；下方分页展示所选知识点的完整题干、章节、选项、配图、学生错误作答、正确答案、解析及错误次数，多知识点命中同一题只展示一次；标注最近已答对或仍答错，保留原有忽略与发送私信功能；防止关闭弹窗、切换课程和快速切换筛选后过期请求覆盖内容，并提供加载失败重试。

- `assets/js/api.js`：接入教师学生错题只读接口，传递知识点多选与分页参数。

- `assets/js/teacher/views/monitor.js`、`assets/js/teacher/views/dash.js`：学情监测看板「个体学情详情」中的高频错题改为可点击按钮，使用同一课程隔离接口按累计答错次数降序展示前 5 个知识点；点击某知识点打开共用错题弹窗并默认选中该点，查看该知识点的完整错题，继续支持多选和分页，关闭错题弹窗后保留原学生详情；增加加载失败重试与切换课程后的过期请求校验。

- `assets/css/app.css`：沿用系统颜色、圆角和按钮样式，增加知识点多选卡片、题目详情及答案区域样式；知识点列表可独立滚动，长题干与答案自动换行。

- `teacher.html`：更新本次修改的样式、接口脚本、驾驶舱和学情监测脚本版本号，避免浏览器继续使用缓存中的旧入口。

**后端**

- `backend/app/routers/teacher.py`：为 `GET /teacher/dashboard` 的预警待办补充学生与知识点标识，并调整低正确率和错题集中待办的操作；新增 `GET /teacher/students/{user_id}/wrong-questions`，按当前课程成员、题目归属与答题记录课程三重过滤，汇总历史错题与全部相关知识点；支持知识点组合筛选、去重和分页，返回最近错误作答、最近作答状态、题目解析与配图，学生角色不可访问。

**数据库·数据**

- 使用既有题目、答题记录、课程成员和知识点数据，只读查询；不新增或修改数据库表、字段及索引。

**验证**

- `dev_tools/check_teacher_wrong_questions.py`：在临时数据库副本中构造超过 5 个知识点、重复答错后答对、多标签、填空和配图数据；验收完整详情、错误次数排序、知识点单选与多选并集去重、未标注知识点、空结果、分页边界、教师登录、未登录 401、学生 403、课程外学生 404 和跨课程隔离；确认查看详情不改动题目、答题与预警记录，真实数据库文件哈希未变化；提供 `--serve` 副本服务用于浏览器验收。

- 验证：Python 与 JavaScript 语法检查、`git diff --check`、工具角色检查、路由角色检查和 MCP 端到端检查均通过；学生与教师真实问答冒烟完成，当前 SDK 不可用，实际回退到 `legacy`。浏览器在副本服务中实际点击「教学驾驶舱 → 查看详情」，完成清空、多选两个知识点得到 5 道去重错题、全选 15 道题及第二页显示剩余 5 道题、关闭和重新打开、硬刷新后的入口及详情检查；弹窗显示 8 个知识点与完整题目，截图留存于临时目录。数据库相关验证全部使用副本。

- 补充验证：学情监测脚本语法检查与 `git diff --check` 通过；浏览器在包含 8 个错题知识点的数据库副本中实际点击「学情监测看板 → 学生 → 高频错题」，列表只显示错误次数降序前 5 项（4、4、2、2、2 次）；点击后正常查看对应知识点的完整错题，关闭后原学生详情与 5 项列表保留，硬刷新后仍显示 5 项。

## 二、学情监测学生列表滚动区域与预警卡片对齐（2026-10-15）

- `assets/js/teacher/views/monitor.js`、`assets/css/app.css`：移除学生列表在双栏布局下固定的最大高度，让列表填满卡片标题下方区域，并与右侧异常预警卡片底部对齐，避免卡片底部有空白却提前滚动；窄屏单栏布局保留列表自身的最大高度和滚动。

- `teacher.html`：更新学情监测脚本和样式版本号，避免旧缓存保留原高度设置。

- 验证：JavaScript 语法检查与 `git diff --check` 通过；浏览器在数据库副本中检查 1920×1080 双栏布局，学生与预警卡片高度均为 747 像素、底部差值为 0，学生列表底部距卡片仅剩 1 像素边框；10 名学生全部正常显示，原固定高度造成的提前滚动与下方留白已消除；1000×900 单栏布局保留 468 像素列表高度和内部滚动；硬刷新后两侧仍对齐。

## 三、归因与错题分析统计移至高频错题标题栏（2026-10-15）

- `assets/js/teacher/views/analysis.js`：删除页首四张概览统计卡片，移除「高频错题」统计和重复的题数标记；保留「累计答错」「涉及知识点」「待关注学生」三项，以紧凑样式显示在「高频错题 Top 5」标题右侧；删除「按答错次数降序取前 5」等统计说明文字，沿用原统计口径与数值配色；窄屏时三项统计可换行显示。

- `teacher.html`：更新归因分析脚本版本号，避免缓存保留旧统计布局。

- 验证：JavaScript 语法检查与 `git diff --check` 通过；浏览器在数据库副本中确认页首旧统计卡片与说明均已移除，标题右侧仅显示累计答错 28 次、涉及知识点 5 个、待关注学生 5 人，点击高频错题仍可打开题目详情；680 像素窄屏下统计换行且未超出标题栏，硬刷新后新脚本与三项统计正常加载。

## 四、个体学情详情拆分学习时长与 AI 提问趋势（2026-10-15）

- `assets/js/teacher/views/monitor.js`：删除上方按时段展示的「学习时间表」柱状图；将原「学习活跃度趋势」中的学习时长与 AI 提问次数拆为两张独立折线图，学习时长在上、AI 提问次数在下，各自使用分钟和次数纵轴，沿用原日期数据与时长提示格式。

- `teacher.html`：更新学情监测脚本版本号，避免缓存继续显示旧图表。

- 验证：JavaScript 语法检查与 `git diff --check` 通过；浏览器在数据库副本中打开「郑亦航」的个体学情详情，确认原时段柱状图已移除，两张独立趋势图均正常绘制且学习时长位于 AI 提问次数上方；硬刷新后重新进入学生详情，两张新图表与脚本版本均正常加载。

## 五、三端编辑弹窗禁止点击外部关闭（2026-10-15）

- `assets/js/common.js`：普通弹窗与抽屉统一支持 `closeOnBackdrop: false`；编辑弹窗点击外部遮罩时静默保持打开，不触发关闭回调，也不增加提示信息；关闭、取消及保存后的程序关闭仍按原流程处理。

- `assets/js/teacher/app.js`、`assets/js/teacher/views/question.js`、`structure.js`、`resource.js`、`report.js`、`exams.js`、`dash.js`、`monitor.js`：为新建课程、题目与草稿编辑、章节与知识点编辑、资源编辑与上传、报告配置、试卷选题及未保存修改确认、私信和预警复核设置遮罩关闭保护。

- `assets/js/admin/views/users.js`、`assets/js/admin/views/courses.js`：为账号与课程新建/编辑/删除确认、账号导入各待提交步骤及课程学生绑定设置遮罩关闭保护。

- `assets/js/student/app.js`、`assets/js/shared/agent-ui.js`：保护学生加入课程的输入弹窗与智能体导入题目的预览编辑弹窗；普通只读详情弹窗保持原有关闭方式。

- `student.html`、`teacher.html`、`admin.html`：更新共享组件及相关页面脚本版本号，避免旧缓存沿用原遮罩关闭行为。

- 验证：JavaScript 语法检查与 `git diff --check` 通过；浏览器在数据库副本环境中分别验证教师新建课程、学生加入课程、管理员新建账号，输入内容后点击遮罩均保持弹窗和输入，提示数量为 0，未出现原生提示框；取消和右上角关闭按钮正常，普通邀请码详情仍可点击外部关闭；三端硬刷新后保护均生效，表单未提交。

## 六、教师试卷选题知识点多选（2026-10-15）

- `assets/js/teacher/views/exams.js`：将试卷「从题库选题」中的知识点单选改为带向下箭头的勾选下拉框，可同时选择多个知识点，显示已选数量并支持一键清空；选中任一知识点的题目均可检索，同一道题不重复；继续支持章节、题型与关键词组合筛选，筛选变化后返回第一页；切换章节时移除不属于当前章节的选择，题目详情与添加到试卷沿用原流程。

- `backend/app/routers/teacher.py`、`assets/js/api.js`：题库接口增加可选 `knowledgeIds` 参数，复用现有主知识点与多标签并集过滤逻辑，在分页前完成筛选；兼容原 `knowledgeId` 单选参数及响应格式，不修改数据库结构。

- `assets/css/app.css`、`teacher.html`：沿用系统按钮、边框和配色，增加多选下拉框、选项滚动与窄屏布局；更新选题脚本、接口脚本及样式版本号，避免旧缓存继续显示单选。

- `dev_tools/check_teacher_exams.py`：在原数据库副本验收中补充多知识点并集、重复命中去重、章节/题型/关键词组合、分页与空结果检查，保留原单选兼容检查；教师账号登录及试卷草稿、发布回归均通过。

- 验证：Python 与 JavaScript 语法检查、`git diff --check`、工具角色检查、路由角色检查及 MCP 端到端检查通过；学生与教师真实问答冒烟完成，当前 SDK 不可用，实际使用 `legacy`。数据库相关验证全部使用临时副本。当前 Browser 无可用浏览器，尚未完成页面多选、清空、章节联动与硬刷新实测。

## 七、学生试卷列表横向布局与组合筛选（2026-10-15）

- `assets/js/student/views/exams.js`：知识点筛选改为可勾选多项的下拉框，显示已选数量并支持清空；试卷必须同时包含全部所选知识点才会显示；新增「全部状态」「已测验」「待测验」筛选，以是否存在已结算测验记录区分，首次测验进行中但未结算仍属于待测验；名称与知识点实时搜索、高亮及测验状态可组合使用，返回列表保留筛选，切换课程重置筛选。

- `assets/css/app.css`：试卷卡片明确使用横向布局并占满一行，信息放左侧、测验按钮放右侧，窄屏自动换行；修正筛选箭头与实际 SVG 元素的定位，避免掉到第二行；增加多选下拉框的显示空间，避免被筛选卡片裁切。

- `student.html`：更新试卷脚本与样式版本号，避免缓存继续使用旧布局和单选筛选；本次只修改前端，复用接口返回的完整试卷列表、知识点与测验记录，不改接口及数据库结构。

- 验证：JavaScript 语法检查与 `git diff --check` 通过；临时 Node DOM 替身运行真实试卷渲染器，完成多知识点同时包含、多选取消与清空、已测验/待测验、进行中与重新测验状态、关键词组合与高亮、空结果、重渲染保留和切课重置检查；数据库副本中的学生试卷验收、工具角色检查、路由角色检查与 MCP 检查通过，学生真实问答冒烟完成（SDK 不可用，实际使用 `legacy`）。当前 Browser 无可用浏览器，尚未完成横向显示、箭头位置、实际点击与硬刷新验收，逻辑检查不作为浏览器实测。

## 七、智能助手消息操作区：放大按钮、新增重新生成、点赞激活动画（2026-10-15）

**后端**

- `backend/app/routers/ai.py`：`/ai/feedback` 端点契约 `FeedbackReq(messageId, feedback:int)` 不变（仍是 TODO 占位，前端保证调用形状对齐）。
- 新增依赖：无。

**前端渲染**

- `assets/css/app.css`：`.msg__acts button` 由 `24×24` 放大到 `48×48`、内嵌 svg 由 `13×13` 放大到 `26×26`（统一覆盖学生/教师/管理员三端 AI 消息底部栏与用户气泡底部栏，因为三端都走同一份 `agent-chat.js` 模板）；`gap: 2px` 改为 `4px` 防止相邻按钮挨太近。新增 `.msg__acts button[data-fb="up"].is-on / [data-fb="down"].is-on` 状态：背景填充（up 用 `--brand-500` 绿、down 用 `#ef4444` 红）+ 0.42s `thumb-pop` 弹性放大动画（scale 1→1.28→0.94→1）；其余按钮不加动画。
- `assets/js/shared/agent-chat.js` 的 `tpl()`（AI 消息分支）：在 `复制回答` 之后新增 `重新生成` 按钮，icon 用 `refresh`，属性 `data-regen="1"`，title 提示"重新生成回答并回滚已执行动作"。AI 消息顶层 `<div class="msg msg--ai">` 上增加 `data-tool-log` 属性，承载 `m.toolLog` 的 JSON（U.esc 转义），供"重新生成"按 `save_question_draft` 调用回滚。
- `assets/js/shared/agent-chat.js` 的 `bindCites()`：
  - `data-fb` 点击：互斥切换 `is-on`（up 与 down 二选一，可再次点同一按钮回到默认），仍调用 `API.ai.feedback({ messageId, feedback: ±1 })` 以保持与后端契约对齐（端点是占位 TODO，失败也不打扰用户）。
  - 新增 `data-regen` 点击：① 从 `data-tool-log` 提取所有 `kind=tool && name=save_question_draft && ok=true` 条目里的 `draft_id`，逐个 `API.question.draftDelete()` 回滚（删除失败不阻塞重新生成）；② 移除当前 AI 消息 DOM；③ 调用 `this.ask(question)` 复用原问题重发，question 文本从前一条 `.msg--me .msg__user-text` 取。
- `assets/js/api.js`：`API.ai.feedback` 注释更新为"`messageId: str, feedback: 1|-1`"，调用形状已对齐。

**LLM/Agent 相关**

- 智能体回复流（`/ai/chat/stream` → `onDone`）的事件契约**不动**。
- AI 出题工具 `save_question_draft` 的副作用现可被前端"重新生成"按 `draft_id` 精确回滚（其它类型的动作卡——`confirm cards` 里的 `submit_item_plan` 等——本次不实现回滚，由教师在消息里手动决策拒绝/批准，避免引入"动作回滚"通用端点）。

**启动脚本·文档**

- 本次未修改 `start.bat` / `docs/**`。

**数据库·数据**

- 无任何表结构、字段、索引改动；不写迁移脚本。

**破坏性改动**

- 无接口签名 / 表结构破坏。仅前端样式与按钮行为变更；老用户刷新即生效。

**测试**

- `backend/tests/test_regen_rollback.py`：新增端到端测试，覆盖「写入一份 st_question_drafts → DELETE /question/drafts/{id} → 验证 DB 真删」与「POST /ai/feedback 字段对齐（messageId+feedback）」，使用 tmp 副本库 + FastAPI TestClient + JWT，可在隔离环境反复运行。
- 验证：复制库后跑 `python tests/test_regen_rollback.py` 全绿；`py_compile ai.py` 通过；`node -c` 五份 JS（agent-chat.js + 三端 chat.js + api.js）全过；`dev_tools/check_route_roles.py` 全部通过。

## 八、三端侧边栏改为手动拉出 + 半圆按钮 + 涟漪背景动画（2026-10-15）

**前端渲染**

- `assets/css/app.css` 末尾新增「侧边栏拉出」样式块：
  - `.sidebar` 由常驻 `position: sticky` 改为 `position: fixed; left: 0; top: 0`，默认 `transform: translateX(-100%)` 收起（不再占布局宽度），加 `.is-open` 后 `transform: translateX(0)` 并配 8px 阴影滑入；
  - `.main` 默认 `margin-left: 0`，`.app.sidebar-open .main` 时让出 `var(--sidebar-w, 260px)` 配合侧边栏宽度；
  - 新增 `.sidebar__handle` 半圆拉出按钮：固定屏幕最左、垂直居中，48×48 圆，渐变品牌色背景，常驻 2.6s `handle-breathe` 光晕呼吸动画 + 拉出时 1.2s `handle-pulse` 弹性放大 + 旋转 180° 移至侧边栏外侧；
  - 新增 `.app::before` 左下角径向渐变涟漪背景层，`opacity: 0`，仅在 `.app.sidebar-open` 时触发 1.2s `corner-ripple` 一次性缩放动画（3 层紫/蓝/青径向）；
  - 窄屏 `@media (max-width: 900px)` 回退：侧边栏恢复 sticky 常驻、隐藏拉出按钮。
- `assets/js/common.js` 末尾新增 `Sidebar` 模块：
  - 自启动：DOM 就绪后扫所有 `.app` 容器调用 `Sidebar.init`（teacher / student / admin 三端 HTML 零改动）；
  - 动态注入 `<button class="sidebar__handle">`，含向右 chevron svg；
  - 点击按钮切换 `.sidebar-open` / `.is-open`，并通过 `requestAnimationFrame` 强制重放 CSS 涟漪动画；
  - 监听 `.app` 上 click 事件：若点击发生在 `.sidebar` 或 handle 内部 `e.stopPropagation()`；否则收起；
  - 全局 `keydown` 监听 Esc 收起。

**启动脚本·文档**

- 本次未修改 `start.bat` / `docs/**`。

**数据库·数据**

- 无任何表结构、字段、索引改动。

**破坏性改动**

- 三端侧边栏默认不再常驻，首次进入需点击屏幕最左侧的紫色半圆按钮拉出（仅宽屏 ≥ 901px；窄屏仍常驻显示，避免移动端找不到导航）。Esc 键可收起。

**测试**

- 验证：`node --check assets/js/common.js` 通过；CSS 结构无 linter 报错；浏览器在数据库副本中实测三端默认收起、点击拉出按钮侧边栏滑入、点主区自动收起、Esc 收起、拉出时左下角涟漪背景动画播放、窄屏回退常驻。

## 九、侧边栏拉出 v2：取消居中留白、衔接紧密、白色脉动、取消涟漪（2026-10-15）

**问题**（来自浏览器实测截图）：

1. 拉出/收起切换硬切：sidebar 没有 visibility 延迟隐藏，元素瞬间消失；
2. 收起时主区虽从 0px 开始，但 `.content { max-width: 1560px; margin: 0 auto }` 让 content 居中在屏幕中央，左右两侧留白 ≈ 180px，视觉上"主区没填到左"；
3. 拉出时主区 margin-left 与 sidebar 宽一致，但 content 仍是 max-width 居中，导致 main 容器和 content 容器边缘不齐，出现"中间缝"；
4. 拉出按钮为紫色径向渐变，与浅色背景对比突兀；左下角 `.app::before` 径向涟漪动画视觉效果不佳，已被产品要求取消。

**前端渲染**

- `assets/css/app.css` 末尾「侧边栏拉出 v2」样式块（替换 v1）：
  - sidebar 拉出/收起统一 `transform var(--sidebar-dur)` 过渡，visibility 延迟 0s linear var(--sidebar-dur) 在 transform 走完后才隐藏，确保**不会有瞬间消失**；
  - 主区 `.main` 默认 `margin-left: 0; width: 100%`，拉出时 `margin-left: var(--sidebar-w, 232px)`，过渡同步；
  - 关键修复：`.content { max-width: none; margin: 0; width: 100% }` —— 无论收起/拉出，content 都贴齐主区左边缘，不再出现左右留白和"中间缝"；
  - 拉出按钮 `.sidebar__handle` 改为白底 + 品牌色内嵌描边 + `handle-breathe` 2.6s 呼吸光圈动画（白底/品牌色描边/淡蓝光圈三段 box-shadow），与主题色呼应，hover 加深描边；
  - 取消 `.app::before` 径向渐变涟漪背景与 `corner-ripple` 动画；
  - 窄屏 `@media (max-width: 900px)` 段保持 sidebar 常驻 sticky 可见、按钮隐藏，恢复 content 居中样式。
- `assets/js/common.js`：`Sidebar.setOpen()` 简化为纯 toggle（去掉先 remove 再 raf add 的涟漪重放逻辑，CSS 已无涟漪）。

**测试**

- 验证：`node --check assets/js/common.js` 通过；jsdom + 三份 CSS（base/refresh/app）真实计算样式验证收起时 sidebar transform: translateX(-100%) + visibility: hidden、main width: 100% + margin-left: 0、content max-width: none + margin: 0；拉出时 sidebar transform: translateX(0) + visibility: visible、main margin-left: 232px、content 紧贴 sidebar 右边 0 间隙。建议浏览器硬刷新三端页面实际查看。

## 十二、智能助手标识 hover 切换 wink 表情（2026-10-15）

**问题**：上一版用 SVG 内嵌 `<style>` 的 `:hover` 切换两套 `<g>`，**完全不生效**。

**根因**：HTML 里通过 `<img src="assets/img/course-assistant.svg">` 引用 SVG。
浏览器把 `<img>` 加载的 SVG 视为**静态图片**，**禁用**内部 CSS hover、JS 动画、
外链资源。所以无论内嵌 `<style>` 写得多完整，hover 时 SVG 都不会重新计算样式。

**修复**（按用户原话"画两份 SVG + 悬浮时切换"）：

- `assets/img/course-assistant.svg` —— 还原成纯默认版（两个圆角矩形眼），去掉内嵌 `<style>` 和 `<g class=...>` 分组；
- 新增 `assets/img/course-assistant-wink.svg` —— 默认眼左眼眯成上扬弧线 `M208 198 Q220 192 232 198`，右眼保持圆角矩形；
- `assets/js/common.js`：
  - `ASSISTANT_MARK_SRC` / 新增 `ASSISTANT_MARK_WINK_SRC` 常量；
  - `assistantMark()` 返回的 `<img>` 模板带 `data-default-src` / `data-wink-src` 两个 data 属性，标记可切换；
  - 新增 `bindAssistantMarkHover()` 函数：
    1. 启动时扫描 `document.querySelectorAll('img')`，给所有 `src` 等于默认 mark 的 img 补上 data 属性（覆盖 HTML 静态 brand 区域、动态 nav-item 注入、聊天面板 AI 头像三种来源）；
    2. 用 document 级事件委托监听 `mouseover` / `mouseout`（capture 阶段），命中 `data-wink-src` 的 `<img>` 切换 `img.src`；
    3. `MutationObserver` 监听 `documentElement` 子树新增节点，对后续动态注入的 mark 补 data 属性（兜底）。
  - `boot()` 末尾调用 `bindAssistantMarkHover()`。

**HTML 加载版本号**：teacher / student / admin 三个 HTML 里 `common.js?v=` 全部更新为
`20261015-mark-wink`（浏览器必须硬刷新才能拿到新 JS）。

**测试**

- `node --check assets/js/common.js` 通过；
- jsdom + `runScripts: 'dangerously'` 实测：静态 `<img>` boot 后自动补 `data-wink-src`，
  mouseover 触发 `src` 切换为 `course-assistant-wink.svg`，mouseout 还原；动态注入的
  `<img>` 被 MutationObserver 捕获，hover 切换同样成功。

## 十一、侧边栏拉出 v4：修复 HTML 加载顺序 + sidebar 真实宽度 (2026-10-15)

**问题根因**（v2/v3 修了多次仍不生效的真正原因）：

> HTML 加载顺序是 `base.css → app.css → refresh.css`。**`refresh.css` 最后加载**，它的
> `.sidebar { --sidebar-w: 244px; position: relative }` 与 `.content { max-width: 1640px; margin: 0 auto }`
> 全部覆盖了 app.css v2/v3 块。所以之前的所有修改都没真正生效。
> 另一个细节：即使我代码里写 `var(--sidebar-w, 232px)`，refresh.css 已把 `--sidebar-w` 设为 244px，
> 所以侧边栏真实宽度 244px，而我代码 fallback 232px → **margin-left 232px ≠ sidebar 244px**，
> 这就是拉出后中间出现约 12px 空缝的来源。

**修复**：

- `teacher.html` / `student.html` / `admin.html` 三个 HTML 文件的 CSS 加载顺序统一调整为
  **`base.css → refresh.css → app.css`**（refresh 提前到 app 之前），query string 改为
  `app.css?v=20261015-sidebar-v4`。这样 app.css 最后加载，v2/v3 块真正生效；
- `assets/css/app.css` 末尾 v2 块整体替换为 v4 块：
  - 注释头标注根因（三端 HTML 加载顺序错误 + sidebar 真实宽度 244px）；
  - `var(--sidebar-w, 244px)`：所有用 sidebar 宽度的 fallback 改为 **244px**（refresh.css 设定值），消除 12px 错位；
  - `.app.sidebar-open .main { margin-left: var(--sidebar-w, 244px) }`：拉出时主区**精确**让出侧边栏宽度，0 间隙；
  - 拉出时 topbar/content 内左 padding 由 24px 减到 **14px**（v3 是 16px），进一步压缩视觉缝；
  - 窄屏 `@media (max-width: 900px)` 保留常驻 sticky + 按钮隐藏 + content 居中。

**测试**

- 验证：jsdom + 三份 CSS（**真实加载顺序 base→refresh→app**）+ 1280px 视口，实测收起/拉出时
  main width=100%、margin-left=0/244px、content max-width=none、topbar/content padding-left=24px/14px 全部正确；
- 浏览器**必须硬刷新**（Ctrl+F5 或 Cmd+Shift+R）以加载新 HTML（link 顺序变了） + 新 CSS；
- 如果硬刷新后仍异常，**请截图**显示 DevTools Elements 面板的 `<aside class="sidebar">` 和
  `<main class="main">` 的 Computed 样式，方便定位是哪条规则还在覆盖。

## 十、侧边栏拉出 v3：底层策略改为"主区默认填满、拉出后让出" + 只按钮/Esc 切换（2026-10-15）

**问题**（来自浏览器实测截图 v3）：

1. 拉出时主区 main 容器已 0 间隙紧贴 sidebar，但 topbar 内 padding-left 24px（refresh.css 覆盖 base 22px）+ content 内 padding-left 24px 合计 48px 让"主区首屏内容"看起来仍离 sidebar 右边一截；
2. 点击主区任意位置会自动收起侧边栏，与"只有按钮触发"的产品意图不符。

**修复策略**（v2 → v3）：

- 底层策略：sidebar 始终 `position: fixed; left: 0; top: 0; bottom: 0`，`transform: translateX` 控制显示/隐藏（不再 toggle visibility 硬切）；主区 `.main` 收起时 `margin-left: 0; width: 100%`（**默认填满全屏**），拉出时 `margin-left: var(--sidebar-w, 232px)` 让主区**往右挤**为侧边栏腾出空间。这是 v2 已落地的底层架构，v3 不再改动。
- 拉出时减小 topbar/content 内部左 padding（24px → 16px），消除"main 容器 0 间隙但 topbar 内部 padding 看起来还有缝"的视觉错觉；
- 删除 `appRoot` 上的 click 监听：现在只有**拉出按钮**和**Esc 键**能切换侧边栏状态，**点击其他区域不再收起**。

**前端渲染**

- `assets/css/app.css` 末尾追加：
  ```css
  .app.sidebar-open .topbar   { padding-left: 16px; }
  .app.sidebar-open .content  { padding-left: 16px; }
  ```
- `assets/js/common.js` `Sidebar.init()` 内部：
  - 移除 `appRoot.addEventListener('click', ...)` 整段（点击其他区域不再收起）；
  - 保留 `handle.addEventListener('click', ...)`（按钮切换）、`sidebar.addEventListener('click', e => e.stopPropagation())`（避免冒泡）、`document.addEventListener('keydown', Esc)`（Esc 收起）。

**测试**

- 验证：`node --check assets/js/common.js` 通过；jsdom 在 1280px 视口下计算样式确认收起/拉出时 main width、margin-left、topbar/content padding-left 全部正确；浏览器需**硬刷新（Ctrl+F5）**三端页面以加载最新 `assets/css/app.css`（query string 未变）。