## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、教师端课程目录与资源界面刷新逻辑（2026-09-23）

- `assets/js/teacher/app.js`：修复教师端创建课程后仍显示上一门课程的问题；创建成功后先写入新课程 `activeCourseId`，等待课程下拉列表异步刷新完成后再重绘当前视图，确保请求携带新课程的 `X-Course-Id`。
- `assets/js/teacher/views/structure.js`：为「课程目录与资源」增加课程 ID 与渲染序号校验；旧课程请求晚返回时不再覆盖新课程页面，并在重新加载时清空上一门课程的章节选择。

## 二、章节知识点归属与资源上传标签分组（2026-09-23）

- `assets/js/teacher/views/structure.js`：将新增知识点界面明确标记为当前章节的主知识点归属；新增知识点前先校验当前课程内是否重名，重名时提示「已存在知识点」。
- `assets/js/teacher/views/structure.js`：删除上传资源窗口中的「新建 KP 标签名」输入和按钮；KP 选择区按当前目录动态分为「主知识点」与「涉及知识点」，并保证上传时主知识点 ID 排在涉及知识点之前。
- `backend/app/routers/teacher.py`：新增知识点和修改知识点名称时增加当前课程内同名校验，拒绝重复名称并返回「已存在知识点」；仅增加接口校验，不修改数据库结构或现有数据。

## 三、教师端切换课程后进入其他页面仍显示旧课程（2026-09-23）

- `assets/js/teacher/app.js`：切换课程后重置所有教师端路由的挂载状态并重绘当前页面；之后进入 AI 出题、知识图谱等页面时会重新挂载并按新课程加载，不再复用旧课程页面。
- `assets/js/teacher/views/question.js`：为 AI 出题、草稿箱和题库请求增加当前课程与渲染序号校验；切换课程后清空上一门课程的知识点选择、生成状态和题库页码，旧课程请求返回时不再覆盖新课程内容。
- `assets/js/teacher/views/graph-edit.js`：为知识图谱拓扑加载增加课程 ID 与加载序号校验，切换课程或重新加载后，旧课程的异步结果不再覆盖当前图谱。

## 四、题库管理修复无法搜索搜索，知识点与关键词高亮（2026-09-23）

- `backend/app/routers/teacher.py`：题库搜索增加当前课程知识点名称匹配，覆盖主知识点和多知识点标签，不再只搜索题干与题号。
- `assets/js/teacher/views/question.js`、`assets/css/app.css`：题号、题干和知识点列中的命中关键词使用绿色高亮显示。

## 五、知识图谱编排限制同一对知识点重复关系（2026-09-23）

- `assets/js/teacher/views/graph-edit.js`：两个知识点建立关系时按无向组合去重，无论从哪一端发起、选择哪一种关系，只允许两个知识点之间保留一条关系。
- `backend/app/routers/teacher.py`：知识图谱关系读取和保存均按两个知识点的无向组合去重，防止反向或不同类型的关系同时保存；不修改数据库结构或直接改动现有数据。

## 六、学情分析报告生成、错题知识点归因与刷新（2026-09-23）

- `assets/js/teacher/views/report.js`：修复报告生成请求参数和当前课程兜底，处理 `this.loadArchive` 回调对象错误；右侧历史归档最多显示 8 条并支持滚动，生成成功后等待列表刷新完成再打开详情，避免误弹生成失败提示。
- `backend/app/routers/intervention.py`：按整体掌握度、共性短板归因、个体预警、干预效果、目标达成度生成模板；无学生或无学习记录时仍可生成，并将错误类型为空或为「未分类」的错题按题目知识点归因；报告历史按课程严格筛选且不修改数据库结构。

## 七、学生端未加入课程时各页面空白（2026-09-23）

- `assets/js/common.js`：为路由增加统一空状态拦截，学生未加入课程时进入任意功能页面均显示课程提示，不再挂载需要课程数据的页面。
- `assets/js/student/app.js`：无课程时清除残留课程上下文并提供统一的「尚未加入课程」页面；加入课程后等待课程上下文更新完成再刷新当前页面。
- `assets/js/student/views/dashboard.js`：学习驾驶舱复用统一未加入课程页面，避免单独请求接口后显示空白。
- `assets/css/app.css`：补充未加入课程提示的居中布局样式。

## 八、学生端切换课程后其他页面及智能练习仍显示旧课程（2026-09-23）

- `assets/js/student/app.js`：切换或加入课程后重置所有学生端页面的挂载状态和页面缓存，重新加载当前页面，之后进入其他页面时也会按新课程重新请求数据。
- `assets/js/student/views/practice.js`：切换课程时清除练习题目、会话、错题筛选和知识点状态，并阻止旧课程延迟返回的请求覆盖新课程页面；当前课程没有题目时显示暂无可练习题目提示。
- `assets/js/student/views/chat.js`、`assets/js/student/views/graph.js`、`assets/js/student/views/resource.js`：切换课程时清除答疑会话、图谱选中项和资源筛选等旧课程页面状态。
- `backend/app/routers/practice.py`：练习模式题量、智能组卷、练习存档、作答统计和错题本均严格按当前课程筛选，避免刷新后仍读取其他课程题库；不修改数据库结构或现有数据。
- `backend/app/routers/ai.py`：AI 答疑历史会话和消息按当前学生及当前课程筛选，避免切换课程后继续显示原课程会话；不修改数据库结构或现有数据。

## 九、知识图谱编排：+ 号按钮太小、连线选中无高亮（2026-09-23）

- `assets/js/teacher/views/graph-edit.js`：`ge-plus` 圆半径从 `r=9` 放大到 `r=13`、文字从 13px 改为 18px bold、描边从 1.5px 加粗到 2px；偏移公式改为 `translate(0, -(r+plusR+gap))`（plusR=13，gap=3），使加号位于知识点 icon 的**正上方**，与节点保持约 3px 视觉间隙、不被节点本体遮挡；鼠标悬停时加号额外加 `drop-shadow` 光晕并微微放大。
- `assets/js/teacher/views/graph-edit.js`：`path.hit` 命中区保持 14px 透明描边不变（确保选中区域够大）；选中连线时**仅**关系标签加粗并染为品牌色、字号 10→11px，连线本体（`path.line`）粗细、箭头粗细均保持原状不变，不加 `drop-shadow` 等会让箭头周围出现割裂阴影的滤镜；所有过渡动画时长 0.14s；`_syncSel` 中不再手动写 `stroke-width`，完全交给 CSS（`.ge-edge.on`）控制。
- `assets/js/teacher/views/graph-edit.js`：在 SVG `<defs>` 中为每种关系多定义一个选中态箭头 marker（`ge-ar-${k}-on`），其 `markerWidth/markerHeight` 由 5.5 放大到 7.5，并给箭头 path 加 `stroke="#fff" stroke-width="2.2" stroke-linejoin="round" paint-order="stroke fill"`，让箭头选中时**变粗并自带一圈白边**（与文字 `paint-order:stroke` 的描白边风格一致）；`_syncSel` 在选中时把 `marker-end`（`parallel` 同时切换 `marker-start`）从默认 marker URL 切到 `-on` 版本，取消选中时切回，从而让箭头和文字一起高亮；箭头粗细通过 marker 切换实现，不使用 drop-shadow 滤镜，避免箭头周围出现割裂阴影。
- `assets/js/teacher/views/graph-edit.js`：让连线主体（`path.line`）也与箭头、文字风格统一高亮——`draw()` 中每个 edge 多渲染一条 `path.halo`（白底层 path，渲染在 hit 与 line 之间），`paintGeom()` 在更新每条边的几何 `d` 时同步刷新 halo；CSS 默认 `path.halo{stroke:transparent;stroke-width:5.5;stroke-linejoin:round}`，选中时 `.ge-edge.on path.halo{stroke:#fff}`，并把 `path.line` 的 `stroke-width` 由 1.5 加粗到 2.4，从而让主线选中时**变粗并被 5.5px 白色 halo 包夹一圈白条**（与箭头自带白条的视觉一致）；不使用 drop-shadow / filter，避免箭头周围出现割裂阴影。

## 十、学情分析报告：班级→课程、人数实数化、生成者命名、去除干预效果（2026-09-24）

- `backend/app/routers/intervention.py`：`generate_report` 从 `courses` 表读真实课程名写入 `meta.courseName`（兼容 `meta.className`），并把 `len(students)` 写入 `meta.studentCount`（人数即该课程学生人数）；报告 `title` 由 `· 学情分析报告 - YYYY-MM-DD` 改为 `· 学情分析报告 YYYY-MM-DD`（去除 "-" 符号）；同时将"生成者"作为正式字段写入 `meta.generator`、增加 `meta.generatedAt` 与 `meta.period`，供前端展示与 PDF 导出复用；`_write_pdf` 中的标题字段同步改为"课程：/人数：/时间区间：/生成者："四行，删除原"班级："。
- `backend/app/routers/intervention.py`：按需求去除"四、干预效果"section——`section_map` 中移除 `section_effect`、目标达成度编号从"五、"改为"四、"；`requested_sections` 过滤时对"干预效果"做 `discard` 兼容，老报告若仍携带该选项静默忽略，避免空指针或章节缺失。
- `assets/js/teacher/views/report.js`：`openDetail` 渲染 meta 行由 "班级：className / 人数：— / 生成：generatedAt / generator" 改为 "课程：courseName / 人数：studentCount / 生成者：generator / generatedAt"；模态框中"包含章节"chips 移除"干预效果"按钮；顶部说明文案由"基于班级 / 章节 / 时间段，整体掌握度、共性短板、个体预警、干预效果、目标达成度"改为"基于课程 / 章节 / 时间段，整体掌握度、共性短板、个体预警、目标达成度"。

## 十一、AI 出题与题库：草稿箱分类精简、题库按默认/知识点/正确率/难度排序+升序反转（2026-09-24）

- `assets/js/teacher/views/question.js`：草稿箱顶部 `draftSeg` 由「全部 / 待处理 / 校验未过 / 已发布」精简为「待处理 / 已发布」两段，删除「全部」和「校验未过」按钮；`draftFilter` 默认值由 `'all'` 改为 `'draft'`（首次进入直接呈现待处理草稿），`render()` 切换课程时也回到 `'draft'`，避免遗留旧课程的过滤器。
- `assets/js/teacher/views/question.js`：题库管理 `bankSeg` 由之前的「按正确率 / 按难度」2 段，扩展为「默认 / 知识点 / 正确率 / 难度」4 段排序按钮，并在序列右方追加一个反转按钮（`#bankDirBtn`，同款 `.seg` 风格，前缀箭头 `↘`/`↗` + 文案「升序/降序」），切换课程后回到默认 + 升序；新增 `bankSort`（默认 `'default'`）与 `bankDir`（`asc`|`desc`，默认 `asc`）两个状态，新增 `_renderBankDirBtn` 方法在排序按钮每次重渲染时同步方向按钮文案与 `is-desc` 视觉态；`loadBank()` 调用 `API.question.bank` 时同时传 `sort` + `dir`，`editQ` 中拉取题目详情的 fallback 调用也同步带上。
- `assets/js/teacher/views/question.js`（2026-09-24 24:00 修复）：反转按钮 `#bankDirBtn` 点击切换 `bankDir` 后只调用了 `loadBank()` 刷新表格，按钮本身不会被替换、导致箭头与文案不刷新（用户报告「点击升序按钮未变为向下的箭头及降序」）；改为先调用 `_renderBankDirBtn()` 同步方向按钮的箭头（`↘`/`↗`）与文案（`升序`/`降序`），再调 `loadBank()` 拉数据；同时给 `_renderBankDirBtn` 加一层 `document.getElementById` 兜底，防止传入的 `box` 已被卸载导致查不到节点。
- `backend/app/routers/teacher.py`：`/question/bank` 排序参数扩展为 `default` / `kp` / `correctRate` / `difficulty` × `dir` (`asc`/`desc`)；`default` = DB 原顺序、不做二次排序；`correctRate` 按真实 `answer_records` 聚合值、`difficulty` 按 1~5 星、`kp` 按主知识点 `kp_id` 字典序（同 KP 内按 `q_id` 兜底）；空值/未知键一律放到末尾，使用 `_nulls_last` 辅助函数分离空/非空，非空段独立控制升降序，从根本上避免 Python 元组排序在 `reverse=True` 时空值被前置；旧 `status` 字段保留以兼容其它可能的调用方，未改动。
- `assets/css/base.css`：为 `.seg` 内追加样式 `.seg button.seg__dir` 与 `.seg button.seg__dir.is-desc`，复用既有的 26px 高度、圆角与 hover/active 态，仅追加箭头+文案布局和「降序」态的品牌色高亮；不引入新的全局控件，整体美术与原 seg 完全一致。
- `assets/js/api.js`：`API.question.bank` mock fallback 简化为空列表兜底（实际项目无 mock 题库数据），注释更新为 `sort=correctRate|difficulty|kp|default, dir=asc|desc`；`API.question.drafts` 注释同步更新为 `status: draft|published`；移除旧 `q.status` / `q.keyword` 双过滤逻辑，避免误导。

---
