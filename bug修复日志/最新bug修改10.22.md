## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；同一问题继续修改时更新原记录，跨日期新增一项；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、三端默认头像显示名字（2026-10-22）

- `assets/js/auth.js`：统一默认头像文字生成规则，三字及以上姓名取最后两字，两字姓名去掉姓氏取最后一字；侧边栏、个人中心、管理员用户列表及图片加载失败后的默认头像同步使用该规则，避免旧资料中的姓氏头像覆盖新显示。

- `assets/js/shared/agent-chat.js`、`assets/js/teacher/message-push.js`、`assets/js/teacher/views/monitor.js` 与 `assets/js/teacher/views/analysis.js`：聊天消息、推送消息选人列表、学生学情列表及归因分析学生头像统一显示名字。

- `student.html`、`teacher.html` 与 `admin.html`：更新相关脚本缓存版本，让已有用户重新加载后使用新的默认头像规则。

- 验证：五份 JavaScript 的 `node --check` 及 `git diff --check` 通过；Node 临时会话检查通过三字姓名、两字姓名、四字姓名、单字、空姓名、罕见汉字、旧姓氏缓存、自定义头像、图片失败回退文字、恢复默认及侧边栏和聊天头像同步。Browser 插件连接因缺少运行脚本失败，尚未完成浏览器显示、点击及硬刷新验收。

## 二、学生与教师学情报告改用 AI 分析生成（2026-10-22）

- `backend/app/services/report_facts.py`：从当前课程的真实学习路径、资源进度、答题记录、已结算试卷、预警和已保存的 AI 互动摘要整理事实；教师按所选章节、知识点及北京时间日期筛选活动，学生限定本人当前课程；当前进度与期间活动分开说明，未知正确率不写成零，重复资源进度取优，错题区分重复答错与已经纠正；教师只读取群体汇总，不读取或展示原始问句。

- `backend/app/services/ai_learning_report.py`：使用系统现有模型生成正文，固定输出学习概况、学习进度与投入、知识掌握与薄弱点、练习测验与错题、AI 互动疑惑与预警、下一步行动计划六部分；约束篇幅及行动建议数量，校验结构、依据引用和正文数字是否出现在事实清单；校验失败最多反馈修正一次，仍失败或模型不可用时提示重试，不保存模板或不完整报告。

- `backend/app/services/student_report.py` 与 `backend/app/routers/intervention.py`：移除学生、教师报告的固定正文拼接，统一走 AI 分析后再归档，教师接口增加可选章节数组并兼容旧参数；继续使用现有 `reports.detail_json`，保留历史详情和归属校验，PDF、HTML、DOCX 导出均包含分析依据，不修改数据库表结构。

- `assets/js/student/views/report.js`、`assets/js/teacher/views/report.js` 与 `assets/css/app.css`：报告各部分增加可展开的「查看分析依据」，生成时显示转圈和「AI 分析中」；教师弹窗改为展示固定六部分内容，章节和日期仍可选择，旧报告继续正常显示。

- `assets/js/api.js`、`assets/js/shared/agent-ui.js` 与 `backend/app/agent_st/agent/system_features.yaml`：教师生成接口取消模拟报告替代，智能助手沿用新的生成入口，兼容历史操作卡的旧部分选择；同步系统指引中的报告内容、筛选方式和生成失败说明；三端 HTML 更新相关脚本及样式缓存版本。

- `dev_tools/check_ai_reports.py`：新增仅使用临时数据库副本的检查，覆盖同一学生跨课程隔离、章节与知识点组合、日期边界、错题纠正、资源进度去重、章节内试卷得分、摘要隐私、输出结构与数字校验、三种格式导出及 AI 失败不归档。

- 验证：Conda `py_compile`、相关脚本 `node --check`、YAML 解析、`git diff --check`、上述新增检查、角色与路由权限检查和 MCP 端到端检查通过；现有 `check_ui_report_api.py` 在库副本上真实调用模型，学生生成、教师生成、自定义标题、历史归档及越权检查通过，真实数据库 SHA256 未变；学生与教师智能助手真实问答通过，SDK 未安装时依现有配置回退 legacy。两端报告内存渲染检查覆盖六部分、依据展开标记、文本转义和旧归档；Browser 插件缺少运行文件，未完成浏览器点击与硬刷新验收。现有 `check_system_actions.js` 的管理员导航断言失败，已用原 `HEAD` 内容复现同一失败，未修改其预期或无关导航代码。

## 三、教师端不显示学生上传的头像（2026-10-22）

**根因**：头像字段实际存在 `TeacherClassDashboard` 表 `data_type='account_profile'` 的 JSON 中（`avatarId` 指向 `data/avatars/<uuid>.png`），管理端在 `routers/admin.py` 调用 `profile_metadata()` 读出 `avatarUrl`，前端 `Auth.avatarHtml()` 据此渲染图片；学生端走 `auth.py` 自己的 `user_profile_dict()`，同样拿到 `avatarUrl`。教师端 `routers/teacher.py` 的 `/students` 只返回了 `avatar_char`（首字），没调 `profile_metadata()`；前端 `teacher/views/monitor.js`、`teacher/message-push.js`、`teacher/views/analysis.js` 三处又硬编码 `Auth.defaultAvatarText(name)`，于是教师端永远渲染默认文字头像。

### 后端

- `backend/app/routers/teacher.py`：引入 `profile_metadata`，`/students` 构造返回项时调一次 `profile_metadata(db, student_ids)` 并把 `avatarUrl` / `signature` 注入每个学生对象；`/analysis/errors` 的 `individual[]` 同样注入 `avatarUrl`。现有 `avatar` / `avatarColor` 字段保留不变，向后兼容。

### 前端渲染

- `assets/js/teacher/views/monitor.js`、`assets/js/teacher/message-push.js`、`assets/js/teacher/views/analysis.js`：把硬编码的 `Auth.defaultAvatarText(name)` 替换为 `Auth.avatarHtml(...)`；`analysis.js` 的归因项只带 `name + avatarUrl`，按需构造最小对象传入。
- `assets/css/app.css`：`.teacher-message-push__avatar` 与 `.an-avatar` 是 grid 圆形头像容器，原来只渲染文字，新增与 `.avatar img` 同等的 `img` 撑满规则，让 `<img>` 也能铺满并按 `object-fit: cover` 裁剪。

### 启动脚本·文档

- `teacher.html`、`student.html`、`admin.html`：`app.css` 与教师端三份 JS 的 `?v=` 缓存版本统一升到 `20261022-teacher-avatar`，避免硬刷新前被旧脚本拦截。

### 数据库·数据

- 复用现有 `TeacherClassDashboard` JSON 字段，**不新建表、不加列、不改字段类型**；图片文件位置 `backend/app/data/avatars/<uuid>.png` 也维持不变。真实库 SHA256 验收前后一致。

### 验证

- 静态检查：`py_compile`（`teacher.py` + `check_teacher_avatars.py`）、`node --check`（三份前端 JS）、`git diff --check` 全部通过。
- 角色与路由权限：`check_agent_roles.py`、`check_route_roles.py` 通过。
- 既有头像验收：`check_user_profiles.py` 四段 PASS，真实库 SHA256 未变。
- 新增 `dev_tools/check_teacher_avatars.py`：临时库副本 + TestClient，覆盖（1）教师端 `/students` 返回 `avatarUrl` / `signature` 字段、（2）学生 PUT 上传后教师端立刻拿到同一 `avatarUrl`、图片 GET 200 且与管理端一致、（3）恢复默认后教师端同步清空、（4）`/analysis/errors` 的 `individual[]` 每项带 `avatarUrl`、（5）数据库结构与真实库 SHA256 不变。运行结果全部通过。
- 浏览器验收：当前环境缺 Browser 插件运行文件，未完成硬刷新与点击验收，请在浏览器里用 `wangjg/123456` 进教师端「学情 / 消息推送 / 归因」三处对照已上传头像的学生图片是否显示。

## 四、管理端智能助手支持删除课程；顶部导航栏滑动时对齐顶部（2026-10-22）

### 背景

管理端智能助手此前只能做只读查询与账号导入 / 删除，无法删除课程，而管理员在「课程管理」页本来就有删除课程的权限，助手侧却缺这个入口；同时三端顶部导航栏在窄屏滑动时无法吸附到顶部。

### 后端

- `backend/app/agent_st/agent/tools/admin_delete.py`：新增 `preview_course_delete`（只读）与 `delete_course`（写）两个工具，补上「删除课程」这一类治理能力。`preview_course_delete` 支持按 `courseId` 或 `courseName` 定位（只给课名时先精确匹配、多条命中时返回候选让管理员指明、匹配不到再按包含匹配），返回课程基本信息、成员数，以及 `deletable` 与 `blockers`（尚存多少题目 / 章节 / 资源 / 试卷）；`delete_course` 挂 `ApprovalSpec` 审批闸门，摘要、影响面、前置校验齐备。执行时**重新核对一遍**（不信任入参、也不信任审批前的那份状态），期间若课程被新增教学内容会被拒绝并如实回报，不会误删。

- `backend/app/agent_st/agent/tools/admin_delete.py`：课程侧的定位、保护规则与删除动作全部复用 `services/course_admin`（`_get_course` / `content_blockers` / `delete_course`），与「课程管理 → 删除」按钮同一条实现，本文件不另写第二套判断；模块 docstring 同步补充课程删除的职责说明。**未新增 / 修改任何 HTTP 路由**，未改数据库结构。

- `backend/app/agent_st/agent/skills/admin_accounts.md` 与 `admin_courses.md`：补齐删除课程的调用顺序与口径 —— `deletable=false` 时不得调用 `delete_course`、须把剩余教学内容讲清楚；可删时 `courseId` 原样传递；两者均属待批准动作，不能声称已删除。

- **`backend/app/agent_st/agent/flows/admin_ops.yaml`（首版遗漏，人工验收后才补上，关键修复）**：`tools` 白名单加上 `preview_course_delete` 与 `delete_course`，`steps` 增加删课程步骤。**工具只注册进 `TOOLS` 是不够的** —— 模型能看见的工具由本文件的流白名单决定，且技能白名单必须 ⊆ 流白名单。未加这里时，模型在真实对话里根本调不到新工具（见下方「首版失败原因」）。`max_steps` 保持 5。

- `backend/app/agent_st/agent/chat_skills.py`：`accounts` 与 `courses` 两个技能的工具白名单都补上 `preview_course_delete` / `delete_course`。管理员选「课程核查」技能或「账号治理」技能时都能删课。

- `backend/app/agent_st/agent/skills/admin_ops.md`：硬规则里「写操作只有两个（账号录入与账号删除）」改为三个（含课程删除），工具路由表补两行，并新增「课程删除工作流（写操作 · 需确认）」一节（预览 → 看 `deletable` → 传 `courseId` → 等确认卡片）。

- `backend/app/agent_st/agent/loader.py`：`admin_ops` 的 grounding 与任务流标题文案同步为「账号录入 / 账号删除 / 课程删除是写操作、必须经确认卡片」，避免与 skills 里的新说法矛盾。

**权限边界（破坏性改动前已确认）**：两个新工具声明 `roles=("admin",)`、只挂 `admin_ops` 流。学生 / 教师既看不到工具清单，绕过清单硬调也会被 `execute()` 的第二层角色校验拦下；不改动事件契约与数据库结构。

### 前端渲染

- `assets/css/refresh.css`：修复窄屏（`max-width: 760px`）下顶部导航栏滑动时无法对齐顶部 —— 该断点内 `.topbar` 原被写死为 `position: static`，滚动时直接随内容滚走。现恢复 `position: sticky`，并新增 `:root --sidebar-stack-h: 103px` 表达窄屏下同样 sticky 的侧栏高度（品牌行 54px + 导航行 38px + 内边距与边框），顶栏 `top` 取该值让开侧栏，避免两块 sticky 叠在一起；`z-index: 35` 仍低于侧栏的 40。

### 启动脚本·文档

- 本次未改动三端 HTML 的脚本引用与缓存版本（CSS 改动不涉及 `?v=`）。

### 数据库·数据

- **无数据库结构变更**：不加表、不加列、不改字段类型。删除课程仅沿用既有 `courses` 行删除与 `user_courses` 成员关系移除，语义与页面上的删除按钮完全一致。

### 首版失败原因（2026-10-22 人工验收发现并修正）

首版只做了两件事：注册 `@tool` + 改 `skills/*.md` 提示词。人工验收时助手仍回答「当前助手只支持账号录入与删除这两种写入」，功能完全没生效。原因是**工具注册与工具可见性是两套机制**：

1. `@tool` 只把函数登记进 `registry.TOOLS`，决定「有没有这个工具」；
2. 模型实际能看见的清单来自 `flows/admin_ops.yaml` 的 `tools` 白名单（未选技能时用流白名单，选了技能则用技能白名单，且技能白名单必须 ⊆ 流白名单）；
3. 提示词 `skills/*.md` 只负责教模型怎么用，管不了可见性。

首版三处全漏了第 2 层（`chat_skills.py` 的技能白名单、`flows/admin_ops.yaml` 的流白名单、`loader.py` 的文案），于是工具存在但模型看不见，表现为「助手说没有这个功能」。教训：新增工具必须同时改「注册 + 流白名单 + 技能白名单 + 提示词」四处。

### 验证

- 静态检查：`python -m py_compile`（`admin_delete.py` / `chat_skills.py` / `loader.py`）、YAML 解析、`git diff --check` 通过。
- 角色与权限：`dev_tools/check_agent_roles.py` 全项通过 —— `admin_ops` 流白名单已含 `delete_course`（第 4 项断言由「九个」更新为「十一个」业务治理工具）；新增断言 `preview_course_delete` 无审批闸门、`delete_course` 有闸门且摘要/影响面齐备、两者只挂 `admin_ops` 流不进教学流；`delete_course` 已被第 7 项纳入写工具监管，学生硬调被 `execute()` 拒绝。
- 路由闸门：`dev_tools/check_route_roles.py` 全项通过。
- **真实模型问答（库副本，临时脚本已清理）**：
    - 问「平台上现在有哪些课程？分别有多少成员？」→ 调 `course_overview`，正确答出 2 门课（数据结构与算法 11 人、近代史纲要 16 人）。
    - 问「把课程 CCHYJTKE 删掉」→ 调 `preview_course_delete`，返回 `deletable=false` 与 12 类阻碍（题目 236 / 资源 131 / 答题记录 645 / 学习路径 260 / 练习 171 / 图谱 35+34 / 知识点 26 / 答疑会话 18 / 草稿 4 / 预警 51 / 试卷 1），模型逐项列表说明需先由教师端清理，**没有**擅自调用 `delete_course`。
    - 问「帮我删除课程 CZYNGCLC」→ 调 `preview_course_delete`，识别出唯一阻碍是「答疑会话 1 条」，同样未擅自调用写工具。
    - 三次均未产生待批准动作，符合预期：两门课都因残留内容被正确拦截。
- **未完成**：顶栏窄屏吸附仍未做浏览器实测（验证环境浏览器标签页崩溃）；两门课都有残留内容，`delete_course` 真正生成待批准卡片的那条路径尚未用真实模型跑通，需要一门空课程才能验。

## 五、管理端课程删除死锁修复 + 成员批量移出（2026-10-22）

### 背景

管理员反馈：在智能助手里问「删除课程」接口能响应，但删不掉 —— 教师自己建的课（课程里只有他一个成员、没有学生也没有教材）永远删不掉。追查发现是**前后端双向的死锁**，与第四节记录的智能助手 `delete_course` 无关（助手侧逻辑是对的，它正确地调用了管理端同一条实现）。

### 根因

死锁由「负责人不可移出」与「负责人不可置空」两条规则互相锁死构成：

1. `services/course_admin.py` 的 `unbind_member()` 里有一条硬拒绝：`if user.user_id == course.owner_id: raise CourseAdminError("不能移出课程负责人…")`；
2. `update_course()` 只能**换成另一位教师**（`teacher_user_id` 必须是一个真实存在的教师账号），**无法设为「无负责人」**；
3. 于是教师自建的课（`owner_id` 就是发起人本人）→ 既不能移出他、又不能换成别人、更不能置空 → 管理端永远删不掉。前端还额外加了一层：成员表里负责人行渲染为「不可移出」，按钮都不给。

三者叠加，形成闭环死锁。

### 后端

- **（破坏性行为变更）** `backend/app/services/course_admin.py`：`unbind_member()` 删除「负责人不可移出」的硬拒绝，改为**允许退绑负责人**；`_unbind()` 同步放开（原先对 `course.owner_id` 做 `continue` 跳过，并把命中数报成 `keptOwner`，现改为照常删除并回报 `ownerUnbound`）。这是本次唯一改变既有契约的地方：以前对负责人调用该接口必定 400，现在返回成功。

- `backend/app/services/course_admin.py`：新增 `unbind_members(db, course_id, user_ids)` —— 批量退绑，去重、空列表拒绝（400「请先勾选要移出的成员」）、上限 `MAX_ROSTER_ROWS`、账号不存在时整体拒绝并回报是哪几个（不静默跳过、也不部分写入）。逐个删 `user_courses` 行，**不动任何学习记录**。

- `backend/app/services/course_admin.py`：`list_members()` 增加 `ownerId` / `ownerName` / `ownerBound` 三个字段。`ownerBound` 单独存在的意义：软退绑之后 `courses.owner_id` 仍有值、但该人已不在成员表里，前端据此显示「待指派负责人」。

- **软退绑语义（本次选型）**：退绑负责人只删 `user_courses` 这一行，**`courses.owner_id` 保留原值**。课程因此进入「待指派负责人」状态 —— 管理员之后既可在编辑里改派负责人，也可直接删课（`delete_course()` 本就会清空剩余成员关系，此处未改）。选择保留而非清空 `owner_id`，是为了不破坏依赖该列判断归属的地方，也让课程列表仍能显示「原负责人是谁、待重新指派」。

- `backend/app/routers/admin_courses.py`：新增 `POST /api/v1/admin/courses/{courseId}/unbind-members`（`UserIdsBody{userIds:[]}`），与既有单删接口同样的 try/rollback/fail 写法。`DELETE .../members/{userId}` 顺带补上兜底 `except`（原先只有 `CourseAdminError` 分支）。**未改动 `delete_course`，未改事件契约。**

### 前端渲染

- `assets/js/admin/views/courses.js` —— 成员表多选：每行加复选框，表头行加「全选 / 取消全选」按钮、「已选 N 人」计数与「移出勾选的成员」按钮；新增 `POST` 对应的 `API.admin.unbindMembers()`。负责人行不再显示「不可移出」，与普通成员一样可勾选、可单独移出。

- `assets/js/admin/views/courses.js` —— 勾选变化**只更新按钮可用态与计数，不整块重渲染**：重渲染会重建 DOM、把焦点从复选框上抢走，连续勾选手感会很差。全选/取消全选才走 `render()`。`reload()` 后会剔除已不在成员表里的陈旧 `userId`，避免下次提交时把退课的人带上。

- `assets/js/admin/views/courses.js` —— 文案：`data-act="members"` 按钮「学生」→「成员」，弹窗标题「课程学生 · X」→「课程成员 · X」；编辑课程里负责人字段的说明补充「更换负责人只是新增一位授课教师，不会把原教师移出课程；要把原教师移出，请到『成员』里勾选后移出」（原文案在死锁存在时是误导）。

- `assets/js/admin/views/courses.js` —— 课程列表：`ownerId` 存在但 `teacherCount` 为 0 时（即负责人已退绑）显示 `badge--warn`「待指派负责人」；成员弹窗顶部 meta 同步追加提示，告知此时可直接删除课程。

- `assets/js/api.js`：新增 `unbindMembers()`；`unbindMember()` 的注释从「不能移出负责人」改为说明负责人可移出及其后果。

### 启动脚本·文档

- 本次未改动三端 HTML 的脚本引用与缓存版本（无新增文件、无 CSS 改动）。

### 数据库·数据

- **无数据库结构变更**：不加表、不加列、不改字段类型、不写迁移脚本。新增的 `ownerId/ownerName/ownerBound` 只是 `list_members` 的响应字段，不落库。成员关系仍只写 `user_courses` 一行，学习记录全部保留。真实数据库全程只读（冒烟脚本跑在 `tempfile` 拷贝上）。

### 验证

- 静态检查：`python -m py_compile`（`course_admin.py` / `admin_courses.py` / `check_course_unbind.py`）、`node --check`（`courses.js` / `api.js`）、`git diff --check`、IDE lints 全部通过。

- `dev_tools/check_agent_roles.py`、`dev_tools/check_route_roles.py` 全项通过（无回归）。

- 新增 `dev_tools/check_course_unbind.py`（临时库副本 + `TestClient`），按你描述的真实场景逐段验证，全部通过：
  - 造一门「只有老师、没有学生和教材」的空课 → 成员数=1、`ownerBound=True`；
  - 退绑负责人 → `code=0`（修复前必定 400）、`removed=1`；
  - 退绑后成员为空、`ownerBound=False`、**`ownerId` 仍保留**（证明是软退绑、未动 `courses.owner_id`）；
  - 退绑后删除课程 → `code=0`（**死锁解开**）；
  - 另建一门课绑入 3 名真实学生（成员数=4），一次批量退绑 3 人（含负责人）→ `removed=3`、剩余 1 人、勾选者全部移出；空列表 → 400；不存在的账号 → 400。
- **未完成**：浏览器实测未做（验证环境缺 Browser 插件运行文件）。请在浏览器里硬刷新（Ctrl+F5）后，用管理员进「课程管理」确认：① 列表「学生」按钮已变「成员」；② 打开「当前成员」页签，每行可勾选，全选/计数/批量移出可用；③ 把某课唯一那位教师勾选移出，确认出现「待指派负责人」徽标且此时「删除」能删掉这门课；④ 在智能助手里问「删除课程」再验一次。
- **已知未做**：「向教师发出退绑通知」本次未实现（见 `docs/10.23课程智能体优化方向.md`）。当前退绑是管理员单方面动作，被退绑的教师端不会收到任何提示，他若此时操作该课会被权限校验拒绝（`teacher.py` 按 `user_courses.role_in_course == "teacher"` 判定）—— 这是「退绑生效」的预期表现，但对该教师来说是无预告的。
