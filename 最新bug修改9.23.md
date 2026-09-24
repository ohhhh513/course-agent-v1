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

## 十二、教师端「教学干预与策略」暂时隐藏（2026-09-24）

- `teacher.html`：侧栏移除「教学干预与策略」导航项，第三组标签由「干预与产出」改为「学情产出」（该模块尚未完善，前端先不给入口，避免教师误入半成品）；`<section id="view-intervention">` 与脚本引用保留，便于日后一行恢复。
- `assets/js/teacher/app.js`：`ViewFns` 移除 `intervention` 映射，课程切换后的视图重绘不再引用该视图。
- `assets/js/teacher/views/intervention.js`：由「开发中」占位页改为**隐藏兜底路由** —— 保留同名路由，直接输 `#intervention` 或旧书签访问时提示「该模块暂未开放」并回到教学驾驶舱，不再落到空白/半成品页；文件头写明重新开放的步骤。
- `assets/js/teacher/views/monitor.js`：预警详情弹窗移除「生成干预」按钮及其 `Router.go('intervention')` 跳转，避免入口指向已隐藏模块（弹窗内的处置建议文案保留）。
- 未改动：后端 `/intervention/*`、`/report/*`（真实实现保留）与 `assets/js/api.js` 的 `intervention` 命名空间（当前无人调用，随模块一起留着）。

---

## 十三、教师端「归因与错题分析」下线两块半实现内容（2026-09-24）

- 核查结论（先查后删，确认两处都不是真实实现）：
  - **知识点关联薄弱链路**（`GET /analysis/errors` 的 `weakChain`，`teacher.py:1094-1111`）：取本课程学生 `learning_paths` 中 `mastery>0` 的知识点，按平均掌握率升序取前 3 名，依次塞进 `root / mid / leaf`，不足 3 个补 `name='—'`；**全程不读 `graph_links` 前置关系**，没有任何链路推导（本地该课程 `graph_links` 为 0 条，页面照样画出「栈 → — → —」）。真正按「错题最多的 KP + 该点最多 error_type」拼 root/mid/leaf 的 `/analysis/weak-chain` 端点存在，但前端从未调用。
  - **AI 归因建议**（`causes`，`teacher.py:1113-1149`）：`answer_records.error_type` 的 `GROUP BY` 计数 + 硬编码 `DESC_MAP` 文案表 + 固定建议模板，**没有任何 LLM/Agent 调用**（`teacher.py` 里 `run_turn` 只出现在 AI 出题链路）；标题里的「成因概率」实际只是占比。且 `error_type` 基本恒为空——`practice.submit_answer` 把**题目**的 `error_type` 抄进答题记录，而题库该字段普遍为空（本地 229 道题、2 条答题记录全为空），因此实际只会渲染出「未分类 100%」。
- `assets/js/teacher/views/analysis.js`：删除上述两块卡片，并移除对应的 `weakChain` / `causes` 变量解构；页面保留「高频错题 Top 5」「共性薄弱（班级层面）」「个性异常（个体层面）」三块。
- `assets/js/teacher/views/analysis.js`：顶部说明文案由「系统通过对错题记录聚类与 AI 归因，识别共性薄弱与个性异常」改为「系统按错题记录与学习路径的真实统计，识别共性薄弱与个性异常」，避免页面继续宣称 AI 归因。
- 未改动（有意保留）：后端 `GET /analysis/errors` 仍照常返回 `weakChain` / `causes` 两个字段，`GET /analysis/causes`、`GET /analysis/weak-chain` 端点仍在（前端均未调用）；`assets/css/app.css` 的 `.chain*` / `.cause*` 样式未删（现无使用者），便于日后恢复。

---

## 十四、教师端「归因与错题分析」版式重排（2026-09-24）

- 背景：删掉两块（十二/十三节）后页面只剩三块内容、大片留白，显得简略。本次在不改后端、不加接口的前提下重排版式。
- `assets/js/teacher/views/analysis.js`：页面结构改为「范围条 → 概览指标 → 错题排行 → 双栏明细 → 数据口径脚注」：
  - **范围条**：原单行 callout 改为「图标 + 分析范围 chip（课程名/章节/时间范围）+ 一句话说明」的卡片。课程名取自 `GET /course/my`（原来只会显示 `C8WBRZKV` 这类课程号）。
  - **概览指标**：新增 4 张 `.stat` 卡（高频错题道数 / 累计答错次数 / 涉及知识点数 / 待关注学生数），全部由 `/analysis/errors` 返回数据现算，每张卡的 hint 注明口径，无估算、无新增接口。
  - **错题排行**：`高频错题 Top 5` 每条改为「排名徽标 + 题干 + 知识点/难度/主要错项 meta + 右侧错误率数值与进度条 + 答错次数」，颜色按错误率 60% / 30% 两档分级；空态改用带图标与引导文案的 `R.empty`。
  - **双栏明细**：共性薄弱条目追加「出错人数/学习人数」徽标与占比进度条、右侧百分比；个性异常条目改为「头像 + 姓名 + 问题标签 + 描述 + 查看学情」行式卡片；两栏空态都写明判定线。
  - **数据口径脚注**：新增卡片，逐条说明高频错题排序与错误率算法、共性薄弱（≥2 人且占比 ≥30%）、个体异常（有效学习点 ≥3 且平均掌握率 <40% 或完成率 <30%）的判定线。
- 样式仅在本视图内新增一段 `<style>`（`assets/css/*.css` 未改动），复用既有设计令牌与 `.stat / .chip / .badge / .bar / .empty` 组件，全站风格一致。
- 未改动：接口、字段、判定阈值与 `主要错项`（仍是后端启发式给出的 B/C，如需调整另议）。
- **行为变更备注（本次唯一改变渲染语义的地方）**：「个性异常」条目的严重度配色由原来的 `issue.includes('未登录') || issue.includes('滞后')` 改为 `/滞后|极低/`。原判断里的「未登录」后端从不产出（属死条件），结果是「掌握率极低」显示黄色、「进度严重滞后」显示红色，严重度正好反了；现在两者都按红色呈现。该变更由本次改动负责，如需与改动前逐字一致，改回原判断即可（一行）。

---

## 十五、学生端「课程图谱导航」删除问题图谱 / 目标图谱页签（2026-09-24）

- 核查结论（先查后删，两图谱属「有代码、无数据、无入口」）：
  - 后端 `GET /graph?type=problem|goal` **确有实现**（`graph.py`：按 `graph_type` 查 `graph_nodes` / `graph_links`；problem 沿 `map/error/split` 边递归聚合真实错题数算 `errorRate` / `count`；goal 用 `GOAL_KP_MAP` 聚合知识点掌握率算 `achieve`），不是空壳；另有两个未被前端调用的端点形态（`/graph/kp/{id}` 的 `relatedProblems` 等）。
  - 但**没有任何数据入口**：教师端建章（chapter）、建知识点（knowledge）、图谱编排（保存坐标与 pre/advance/parallel 边）都只处理这两类，真实课程里 problem / goal 节点恒为 0 条（本地库实测均为 0）。
  - `GOAL_KP_MAP` 仍是 v1.0 的 `KP01 / KP11 / …` 编号，与现行 `KP001 / KP002 / …` 体系对不上 → 即便有 goal 节点，`achieve` 也会因查不到知识点而恒为 0。
  - 前端原本也未接接口：`graph.js` 的非 knowledge 分支直接渲染「🚧 正在开发」占位并 `return`，从不调用 `/graph`。seed 里确实带 problem/goal 演示节点（`seed/mock_data.py`），但只在 `DEMO_SEED=1` 时灌入已废弃的 `C2026DS001`。
- `assets/js/student/views/graph.js`：删除三图谱页签（`#graphSeg`，含 `data-t="problem"/"goal"` 两个按钮）与「开发中」占位分支，页面固定为知识图谱；工具栏改为「知识图谱徽标 + 图谱说明（超长省略号）+ 重置视图」。
- `assets/js/student/views/graph.js`：一并清理只为 problem/goal 服务的死代码 —— `GraphView.type` 字段与页签切换逻辑、重难点清单里的 problem/goal 分支、节点详情里 goal/problem 的轻量弹窗分支、重难点条目里永远不会出现的 `count / errorRate` 展示。
- 未改动：后端 `/graph`、`GOAL_KP_MAP`、seed 演示节点、`student.html` 侧栏名称「课程图谱导航」。
- 同批处理（同属老 MOCK 注入的宣传文案）：`index.html` / `forgot.html` / `home.html` 三个认证页左侧宣传行由「三大图谱驱动」改为「知识图谱驱动」，并删除「问题图谱 / 目标图谱」两枚徽标（保留真实的「知识图谱」）。
- 仍待确认（未动，同类残留）：
  - `assets/js/student/views/mastery.js` 能力雷达卡的「目标图谱驱动」徽标 —— 该卡数据链同样是断的：后端 `_GOAL_DIMENSIONS`（`student.py:906-913`）仍用 v1.0 的 `KP11/KP12/…` 编号做维度映射，与现行 `KP001…` 对不上，6 个维度恒为 0，图里只有硬编码的「目标基线」有值。**已登记为 `待修复清单.md` P1（未实现，先放着）**；
  - ~~`assets/js/student/views/practice.js` 练习报告「已回写目标图谱达成度」提示~~ → 已删除（见第十六节）；同卡标题「能力目标增益」的命名问题仍在，登记为 `待修复清单.md` P24；
  - `index.html` 左侧功能列表第 3 条「AI 自动归因与干预策略推荐」（归因刚下线、干预刚隐藏）；`home.html` 第 37 行「通过三大图谱自主导航学习」及其写死的演示课程徽标「《数据结构与算法》· 2026 春季学期」；`assets/js/charts.js:200` 注释「三大图谱（力导向关系图）」（仅注释，无功能影响）。

---

## 十六、删除练习报告的不实提示 + 新增《待修复清单.md》（2026-09-24）

- `assets/js/student/views/practice.js`：删除练习报告顶部「能力目标增益」卡片下方的提示「已回写目标图谱达成度」—— 该提示不实（没有目标图谱，也没有任何回写动作）；卡片本身保留，其数值 `scoreGain`（本次答对题目的分值合计）是真实的。同卡标题「能力目标增益」命名仍不准确，已登记在 `待修复清单.md` P24，本次未改。
- 新增根目录 `待修复清单.md`：登记本轮已核实、但按约定先不修的问题（P1–P29，按「图谱 / 归因口径 / 占位与伪数据 / 隔离权限 / 前端残留 / 仓库与文档」分组），第一条即「目标图谱驱动」徽标 + 能力雷达数据链断裂（未实现，先放着）。
- 两份文件的分工：`最新bug修改9.23.md` 记「已经改了什么」，`待修复清单.md` 记「还没改什么」，避免以后再出现只在聊天记录里的结论。
- 同日追加（**不涉及代码改动**）：`待修复清单.md` 新增第七组「资源进度与完成率」P30–P35 —— PPT/PDF 进度为学生自报页码且只增不减、`pdf_pages()` 解析可能不准、自报进度经 `mastery_by_kp` 喂给掌握率从而影响知识图谱与学习路径状态、PPT/PDF 阅读时长完全不计入学习时长、「累计阅读页数」实为页码求和、视频完成度可被拖动到结尾绕过。**该组明确标注「只登记、先放着」**：百分比 / `resource_progress` / 资源完成率 / 掌握率四者耦合，删除百分比或统计会让资源完成率失真，故保持现状。
- 补记：第十七节的资源卡进度条移除属**显示层**改动 —— `/student/resources` 的 `progress` 字段、`resource_progress` 表、资源完成率与掌握率计算**均未改动**（`backend/app/routers/student.py` 与 `assets/js/student/views/resource.js` 在 `git status` 中无改动），被删掉的只是卡片上那条 `U.bar(...)`，卡片右下角的「知识点名 + 百分比」保留。

---

## 十七、学生端学习资源中心：资源卡去掉进度条（2026-09-24）

- `assets/js/common.js`：`R.res()`（资源卡渲染器，全项目仅被 `assets/js/student/views/resource.js` 的 `items.map(R.res)` 使用）删除卡片底部那条基于 `r.progress` 的进度条 `U.bar(...)`。
- 同处保留：该行的「知识点名 + 进度百分比」文字；`.mt-a`（`margin-top:auto`）保留，使这行仍贴在卡片底部。
- 未改动：接口 `/student/resources` 的 `progress` 字段、点击卡片后的续看逻辑（`openResource` → `/student/resources/{id}/progress`）、播放器内部进度条与记录点标记 —— 只是卡片上不再画那条线。
- 待确认（未改）：卡片右下角仍显示「知识点名 + 6%」这一行；若要连百分比一起去掉，删掉 `.mt-a` 那一行即可（一行改动）。

---

## 十八、学生端「我的学情」三个端点补课程隔离（2026-09-24）

- 背景：`/student/mastery/matrix`、`/student/growth`、`/student/compare` 只按 `user_id` 过滤，`GraphNode` 甚至完全不过滤课程 —— 多课程学生的「我的学情」不论切到哪门课都显示同一份数据（本地实测：知识点矩阵恒为 32 行 = 两门课知识点相加）。
- `backend/app/routers/student.py`：
  - `GET /mastery/matrix`：新增 `course_id: str = Depends(get_current_course_id)`；`LearningPath`、`GraphNode` 与两处 `AnswerRecord` 聚合全部按 `course_id` 过滤。
  - `GET /growth`：新增同一依赖；8 周答题记录、分母 `total_kp`、`mastered_kps` 全部按课程过滤。
  - `GET /compare`：新增同一依赖；口径由「按 `users.class_name` 找同班」改为「**当前课程成员**（`user_courses`，与教师端 `_course_students` 同源）」—— 班级维已废弃，旧实现里 `class_name` 为空会命中所有空班级学生，把两门课的人混在一起；顺带删除该函数内未使用的 `class_id = _resolve_class_id(...)` 死变量。
- 实测（直接调用端点函数验证，不经 HTTP）：课程 `C8WBRZKV` → 矩阵 9 章 / 26 个知识点、成长轨迹完成率 11.5%（3/26）、对比人数 1；课程 `C7BY3C4K` → 矩阵 2 章 / 6 个知识点、完成率 0%（0/6）、对比人数 1。**修复前两门课都是 32 行。**
- 未改动：`/student/ability/radar`（能力目标达成度）按约定暂不动；三个端点的返回字段与结构完全不变（前端无需改动）；表结构与数据未改动。
- ⚠️ 需要**重启后端**才生效（当前 uvicorn 未开 `--reload`）。
- 待确认：`/compare` 口径已变为「课程内同学」，而前端卡片标题仍是「班级对比定位」，是否改文案另定（登记 `待修复清单.md` P36）。

---

## 十九、学生端 AI 答疑：点击「猜你想问」不再直接发送（2026-09-24）

- `assets/js/student/views/chat.js`：右侧「猜你想问」条目的点击事件由 `this.ask(...)`（**点一下就立刻提问**）改为 `this.fillInput(...)` —— 只把问题填进底部输入框并聚焦，是否发送由用户决定；与驾驶舱「AI 助教」、学情「问 AI」、图谱「AI 提问」三个入口的行为统一（那三处早已是"只填不发"）。
- `assets/js/student/views/chat.js`：新增 `fillInput(question, silent)` 方法作为唯一实现（填值 + 触发 `input` 事件以自适应高度 + 聚焦；`silent` 为真时不弹提示），原来的 `_applyPendingDraft()` 改为复用它（跨页带入的草稿不弹提示，避免同一动作两次反馈）。
- 交互细节：原地点击会弹一条轻提示「已填入输入框 · 确认或修改后发送」—— 因为输入框在页面下方，没有提示容易以为"点了没反应"；不想要这条提示删掉 `fillInput` 里的 `Toast.info` 一行即可。
- **不改会话**：原地点击只填字，不新建会话、不清空当前对话（若在某个历史会话里点，问题会追加进该会话）。跨页入口（驾驶舱/学情/图谱）保持原行为不变：仍会新建会话并填入草稿。
- 未改动：`/ai/chat/stream` 与发送逻辑（`send()` → `this.ask(v)`）、`Chat.draft()` 的对外语义、后端。

---

## 二十、学生端「预警与提醒」接通 + 预警相关接口补课程隔离（2026-09-24）

- 前端 `assets/js/student/views/alerts.js`：由「🚧 开发中」占位页（`load()` 为空、不调任何接口）改为真实页面：
  - 顶部 4 张统计卡（红色 / 黄色 / 待处理 / 已忽略）取自 `GET /student/alerts` 的 `stats` / `openStats`；
  - 「我的预警」列表：级别筛选（全部 / 红 / 黄）+ 预警卡片（等级徽标、标题、正确率描述、知识点、触发规则、「标记已读」）+ 建议里的「去练习」（带知识点跳练习页，复用 `Practice._pendingTarget` 自动按该知识点组卷）；
  - 右侧「提醒与通知」：`GET /student/messages` 列表 + 未读数 + 点击查看详情并自动标记已读（`PUT /student/messages/{id}/read`）；
  - 右侧「预警是怎么算的」口径卡：同题取最近一次作答、<50% 红 / 50%~60% 黄 / ≥60% 达标自动解除、至少 2 道不同题才判定；
  - 路由补 `update` / `reset`：重复进入该页或切换课程都会重新拉取（此前只有 `mount`）。
- 前端 `assets/js/student/app.js`：侧栏「预警与提醒」角标由**写死 0 且隐藏**改为读真实数据（当前课程下 `status=open` 的红 + 黄预警数，切课后丢弃旧结果）；并把 `loadMsgBadge` 暴露为 `window.refreshMsgBadge`，供预警页读完私信后刷新顶栏消息角标。
- 后端课程隔离（预警族）——四处补 `Alert.course_id` 过滤：
  - `student.py` 的 `GET /student/alerts`（原先只按 `user_id`）；
  - `student.py` 驾驶舱内的 `active_alerts`（影响「需要关注」计数与待办）；
  - `teacher.py` 的 `GET /teacher/alerts`（**原先只按「课程学生」过滤**：学生同时在两门课时会把别课预警带出来）与 `GET /teacher/dashboard` 的 `active_alerts_all`；
  - `intervention.py` 的 `generate_report` 预警统计段。
- 实测（全部在**数据库副本**上做，不触碰真实库）：
  - 学生端：`course=C8WBRZKV → total=2（红 1 / 黄 1，openStats 红 1）`；`course=C7BY3C4K → total=1`；
  - 教师端（复刻过滤逻辑）：同一学生两门课各一条预警时，**加过滤前两门课都返回 2 条**，加 `Alert.course_id` 后各返回 1 条。
- ⚠️ 需要**重启后端**才生效（当前 uvicorn 未开 `--reload`）；前端刷新即可。
- 未修（已登记 `待修复清单.md` P37）：`PUT /teacher/alerts/{id}/review` 的越权校验仍用 `TeacherClass`（班级维）比对 `alert.class_id`，而 `teacher_classes` / `classes` 两表当前均为 0 行、`class_id` 恒为 `None` → 教师在预警列表点「确认 / 忽略」必然返回 403。

---

## 二十一、修复教师端「复核预警」必然 403（班级维残留 · 2026-09-24）

- 问题（`待修复清单.md` P37）：`PUT /teacher/alerts/{alert_id}/review` 用班级维做越权校验（在 `TeacherClass` 里找 `alert.class_id`），而 `teacher_classes` / `classes` 两表当前都是 0 行、`alert.class_id` 恒为 `None` → 教师点「确认 / 忽略」必然返回 403「无权复核非本班预警」，该功能完全不可用。
- `backend/app/routers/teacher.py` 的修法（谨慎版：只改鉴权，不改业务）：
  - 新增 `course_id: str = Depends(get_current_course_id)` —— 复核纳入课程上下文（非课程成员直接 403，由依赖统一处理）；
  - 越权校验替换为两条：① `alert.course_id != course_id` → 403「无权复核其它课程的预警」；② 调用者在 `user_courses` 中该课程的角色不是 `teacher` → 403「仅该课程的教师可复核预警」；
  - `alert.class_id` 不再参与鉴权（恒为 `None` 也不影响）；`confirm` / `ignore` 的业务逻辑（含「已忽略记录重新确认时按最新作答重新判级」）**一行未改**。
- 实测（数据库副本 + 直接调用端点函数，未触碰真实库）：教师 + 本课程 `confirm` → `code=0 / status=reviewed`；教师 + 其它课程 → `403`；学生（同为该课程成员）→ `403`；教师 `ignore` → `code=0 / status=ignored / level=green` 且备注落库；预警不存在 → `404`；非法 `action` → `400`。
- 影响面：仅此端点；请求体与响应字段不变（前端 `monitor.js` 复核弹窗无需改动，错误文案会更准确）；不改表结构、不改数据。
- ⚠️ 需要重启后端才生效。
- 附带发现（已登记 P38）：`/teacher/*`、`/analysis/*`、`/question/*`、`/intervention/*`、`/report/*` 这些教师端路由**没有任何角色校验**（只校验课程成员身份）→ 学生账号带着自己的 JWT 即可调用教师端接口。这是独立的越权面，建议单独评估（加 `require_teacher` 依赖；可与 §P38 一起排期）。

---

## 二十二、智能练习「存档续做」补课程隔离（2026-09-24）

- 定位：后端的练习接口本身**已经**按课程过滤（`/practice/*` 的 5 处 `PracticeSession` 查询都带 `course_id`）；**漏的是「学习驾驶舱」里的三处练习查询** —— 它们只按 `user_id` 过滤，于是切课后：
  - 「继续挑战」待办仍显示上一门课留下的未完成练习（点进去还对不上：练习页的 `/practice/sessions/current` 是按课程过滤的）；
  - 「今日累计学习时长」把别课的练习用时也算了进来；
  - 「最近学习动态」混入别课的练习记录。
- `backend/app/routers/student.py` 修复（3 处查询 + 1 个依赖）：
  - 驾驶舱「继续挑战（存档续做）」待办循环：+ `PracticeSession.course_id == course_id`；
  - `recentActivities` 的练习会话查询：+ 课程过滤；
  - `_today_study_seconds()`：新增 `course_id` 形参并按课程过滤练习会话；`GET /student/study-duration` 新增 `course_id` 依赖并传入。
- 实测（数据库副本 + 直接调用 `student_dashboard`，未触碰真实库；副本内额外造了一个「别课 C7BY3C4K 的未完成练习 + 2 道作答」）：
  - `course=C8WBRZKV` → 存档待办 `[]`、今日练习 **16 秒**、练习动态 5 条；
  - `course=C7BY3C4K` → 存档待办 `['TD_PS_TESTPS1']`、今日练习 **240 秒**、练习动态 9 条；
  - 修复前：两门课都会显示那条 `TD_PS_TESTPS1`，且都算 240 秒。
- 未改动：`/practice/*` 路由本身（原本已隔离）、表结构、前端（练习页 `resetCourseContext()` 切课时已清空本地状态，且没有 localStorage 持久化）。
- ⚠️ 需要重启后端才生效。
- 附带发现（已登记 `待修复清单.md`）：
  - P39：教师端多 `PracticeSession` / `AnswerRecord` 查询仍只按「课程学生」过滤、未按内容自身的 `course_id` 收敛（与 P37/P38 同族，面较大，建议单独排一轮）；
  - P40：`study_checkins`（打卡/连续学习天数）与 `resource_study_log`（资源学习时长）**表里没有课程维度** → 切课时无法按课程隔离（要隔离就得改表结构，属"不动数据库格式"的范畴，先登记）。

---

## 二十三、智能练习组卷：抽题池限定到目标知识点 + 池内排序（2026-09-24）

- 背景（用户确认口径）：「抽题本来就应该是在该点上的随机题目」；池内排序若可行就做。原实现与之一致性不足：
  - `_expand_kp_ids()` 会把指定知识点**按章节扩散**成「同章所有知识点」再抽题 → 点 `KP001` 实际抽第1章 13 题（含 KP002）、点 `KP015` 实际抽第6章 49 题；
  - 「薄弱点强化」池子 62 题里只有 24 题真正属于薄弱点 → 抽 10 题平均只有约 4 题有针对性；
  - 匹配只认主 `kp_id`；抽题用纯 `random.sample`，**不看正确率**（"优先低正确率"只体现在选点上）。
- `backend/app/routers/practice.py`：
  - 删除 `_expand_kp_ids()`（章节扩散）。`POST /practice/sessions` 带 `kpIds` 时只保留「属于当前课程的目标知识点」，题池 = `Question.kp_id IN (目标知识点)`，**不扩散**。
  - 新增 `_order_pool()`：**最薄弱知识点优先（按传入顺序 = 正确率升序）→ 该生最近一次做错的题优先 → 难度升序 → 同档随机打散**，取代纯随机；未指定知识点的模式（随机 / 错题重练）保持随机。
  - 传了 `kpIds` 但都不属于当前课程（切课后的残留状态）：**显式返回空池**（total=0）并打日志，不再静默回退成「整门课随机」。
- `assets/js/student/views/practice.js`：组卷为空时区分两种提示 —— 带知识点筛选 → 「该知识点暂无可用题目（可改用顺序/随机练习）」；未筛选 → 「当前课程暂无可练习题目」。
- 实测（数据库副本 + 直接调用 `create_session`，未触碰真实库）：
  - 薄弱点强化 3 点（KP001 0% / KP015 0% / KP002 10%，count=10）→ 共 10 题，分布 **KP001 3 题 + KP015 7 题**（全部来自这 3 个薄弱点，且更薄弱的排在前）；前 6 题顺序 = KP001 的题（做错过的优先、难度 2→3）→ KP015 的题（做错过的优先）；
  - 单点 `KP001`（count=10）→ **3 题**（改前 13 题）；单点 `KP015` → 10 题（池 11 题）；
  - 无效 `kpIds` → total=0 且落日志；随机练习（无 kpIds）→ 仍覆盖 9 个知识点。
- 未改动：`status='published'` 过滤、`count = min(请求题量, 池大小)`、其它模式、表结构。
- ⚠️ 需要重启后端才生效。**行为变化需知**：题池变小 → 组卷题量可能少于卡片上写的「10 题」（组卷完成的提示会显示实际题量）。
- 待定（已登记 `待修复清单.md`）：P41 练习模式文案与实际不符；P42 归因分权重设计（用户提出，待定权重与范围）。

---

## 二十四、正确率口径统一为「主 KP 1.0 + 其它标签 0.3」加权（2026-09-24）

- 背景（用户决策）：题目可能挂多个知识点（`questions.kp_id` 是主 KP、`questions.kp_ids` 是完整标签）。**做错一道题应当对所有挂载的知识点负责**，因此正确率改为加权，且**全站统一**（不区分薄弱点/预警）：
  - 主 KP 权重 **1.0**、其它标签权重 **0.3**（`services/scoring.SECONDARY_KP_WEIGHT`）；
  - `正确率(KP) = Σ(权重 × 该题最近一次是否答对) / Σ(权重)`；
  - 「做过几道题」**含次要命中**（一道题只要挂了这个点就算 1 道）→ 子知识点同样能进入预警判定，避免出现「薄弱点看得见、预警判不到」的口径分裂；
  - 预警门槛（`ENGAGE_MIN=2`）与阈值（红 <50 / 黄 <60）**不变**，仍是原设计。
- `backend/app/services/scoring.py`：重写 `quiz_accuracy_by_kp()`（唯一入口，4 个消费方自动跟随）：按 `q_id` 去重取最近一次作答 → join `questions` 取主 KP + 标签 → 加权累加；题目已删除时退回答题记录里的 `kp_id`。新增常量 `SECONDARY_KP_WEIGHT = 0.3` 与 `_kp_tags()`；参数 `secondary_weight` 传 `0.0` 可把**正确率**退回旧口径（便于对账/回退，注意「不同题数」与权重无关、始终含次要命中）。
- 影响面：学生端「薄弱点」、**预警等级与文案**、掌握率（知识图谱节点状态 / 学习路径 / 学情矩阵 / 教师端热力图 / 报告）、教师复核时的重新判级 —— **结构字段不变，只有数值变**。
- 实测（数据库副本，未触碰真实库）：
  - 后向兼容核对：`secondary_weight=0` 的正确率与旧实现逐点一致（KP001 33.3% / KP002 20.0% / KP006 100% / KP015 0.0%）；「不同题数」因含次要命中，KP002 由 10 → **11**（本次口径变化，符合"子知识点也要负责"）；
  - 新口径：KP002 20.0% → **19.4%**（11 题），KP001/KP006/KP015 不变；本数据下没有新增知识点进入预警（仍为 KP001/KP002/KP015 三条红）；
  - 实跑 `detect_alerts`：`{'created': 0, 'updated': 3, 'deleted': 0}`，三条预警的说明文字已同步为加权后的数值（KP002 显示 19%），与学情页同源。
- `assets/js/student/views/alerts.js`：预警页「预警是怎么算的」补充该口径（主知识点 1.0 / 其它标签 0.3）。
- ⚠️ 需要重启后端才生效。备注：预警文案按整数显示（19%），学情页保留一位小数（19.4%），属既有取整差异。

---

## 二十五、靶向练习（薄弱点）与预警统一门槛「≥2 道不同题」（2026-09-24）

- 需求（用户）：靶向练习的入选机制应与预警一致 —— 同一知识点**至少作答 2 道不同题**才算证据。
- `backend/app/routers/student.py`：驾驶舱 `weakPoints` 判定加门槛 —— 由 `if q and q[0] < 60` 改为 `if q and q[1] >= ENGAGE_MIN and q[0] < 60`；`ENGAGE_MIN` **直接复用 `services/alert_detector` 的常量**（当前 = 2，单一来源，改一处两边同步）。薄弱点同时是「薄弱点强化」的 `kpIds` 与「靶向强化建议」列表的数据源，因此三处一并生效。
- `backend/app/routers/practice.py`：`mode='weak'` 且既无 `kpIds` 也无 `qIds` 时**显式返回空池**并打日志 —— 避免"没有达标薄弱点"时静默退化成整门课随机抽。
- `assets/js/student/views/practice.js`：
  - 横幅与「靶向强化建议」补空态（无达标薄弱点时说明"每个知识点至少作答 2 道不同题（与预警同一门槛）后才会计入；可先用顺序/随机练习"），不再出现"已定位 0 个"或空白卡片；
  - 「薄弱点强化」入口在无达标薄弱点时不再发起组卷，改为提示；
  - 组卷为空时的提示区分三种情形：无可定位薄弱点 / 该知识点暂无题目 / 当前课程暂无题目。
- 实测（数据库副本，未触碰真实库）：该生原本 9 个「<60%」的知识点里，**6 个只做过 1 道题、被门槛排除**；统一后薄弱点 = **3 个**：`KP015 树的应用 0%（2 题）`、`KP002 算法与算法评价 19%（11 题）`、`KP001 数据结构概述 33%（3 题）` —— 与预警（KP001 / KP002 / KP015 三条红）**完全一致**。`weak` 模式不带 kpIds → `total=0`；带达标薄弱点 → 组卷 10 题且全部来自这些点。
- ⚠️ 需要重启后端才生效。
- 待你定（行为观察）：当前池内排序是**严格按薄弱度优先**，所以最弱那个知识点题量够时（如实测 KP015 有 11 题、count=10）一轮会被它"吃满"，其余薄弱点本轮不出题。若希望**一轮覆盖全部薄弱点**，可改为按薄弱点轮转取题（最薄弱者先取、题多者多取）。

---

## 二十六、教师端「预警详情」改为「按天累计的历史正确率」曲线（2026-09-24）

- 背景（用户）：原「预警详情」里的图是"最近 5 次作答的对错（0/100 点）"，只是单次对错、看不出趋势，没什么用。改为**该学生该知识点的历史正确率，按天算**：每天的值 = **截至当天（含）为止的累计正确率**；当天没做题就沿用前一天的值（"昨天 40%，今天没做还是 40%"）。
- `backend/app/routers/teacher.py`：新增 `daily_accuracy_series(db, user_id, course_id, kp_id, days=14)`，口径与 `services/scoring.quiz_accuracy_by_kp` **完全一致**（按题去重取最近一次作答；主 KP 权重 1.0、其它标签 0.3），只是把"截至时刻"改为"按天"：
  - 逐日推进：把当天的作答并入"每题最近一次"的快照，再算加权正确率；
  - 当天无作答 → 分子分母不变 → 自动沿用前一天；
  - 第一次作答之前的日期返回 `None`（图上留空，不画成 0）；
  - 日期按**中国时区自然日**切分（库里 `created_at` 是 UTC naive，用 `china_day_bounds_utc` 换算）。
  `alert_to_dict` 用它替换原 `trendData`，并新增 `trendXAxis`（MM-DD）与 `trendDays`（14）。
- `assets/js/teacher/views/monitor.js`：预警详情弹窗改为「当前累计正确率」徽标 + 口径说明 + 折线图（`累计正确率` 主曲线 + `达标线 60%` 灰色虚线），替换原来那条 `4步前…当前` 的假趋势。
- 实测（数据库副本，未触碰真实库）：`KP015 树的应用` → 09-23 起为 `0.0`（09-23、09-24 两天沿用）；`KP001 数据结构概述` → 09-24 首次出现 `33.3`；`KP002 算法与算法评价` → 09-24 `19.4`。**曲线终点与预警文案/学情页同源**（文案取整显示 19%、学情保留一位小数 19.4%）。
- 接口契约同步：`docs/接口文档.md`（Alert 实体行）与 `docs/数据模型与字段说明.md`（§2.8 Alert）已补 `trendXAxis` / `trendDays` 与新口径说明（`docs/数据模型与Mock说明.md` 为 mock 时代遗留文档，未动）。
- ⚠️ 需要重启后端才生效。

---

## 二十七、预警详情图表重排：让"今天"一眼看清（2026-09-24）

- 问题（用户反馈）：上一版把最新值放在最右侧，**右端日期标签被裁、今天的数值也看不清**。
- `assets/js/charts.js`：`Charts.line` 增加两个可选能力（默认行为不变，避免影响其它调用方）：
  - `opts.left / opts.right / opts.top` 可覆盖 grid 内边距 —— 原实现最后一个类目标签贴边被裁掉；
  - 每个 series 支持 `markPoint`（把取值直接标在图上）。
- `assets/js/teacher/views/monitor.js`：预警详情弹窗重排：
  - 顶部改为**大号「当前累计正确率」**（配「今日为止（近 14 天累计）」说明）+「较上一天 ±x.xpp / 与上一天持平」徽标 —— 不需要看右端小点也能读到今天的值；
  - 折线图右侧留 46px 内边距，今天的日期标签完整显示；
  - 在**最新数据点**上打标记并在图上直接写出「今天 19.4%」（取值 ≥80% 时标签自动落到点下方，避免压住图例），保留 60% 达标虚线；
  - 口径说明改成"台阶式推进"的措辞（当天没做题沿用前一天的值）。
- 实测：`charts.js` / `monitor.js` 语法检查通过、HTTP 200；`markPoint` 与 `right` 覆盖均已生效。
- 说明：本次只改前端（刷新即可，无需重启后端）。

---

## 二十八、随机练习重定义：只在「学过且做错过」的知识点里抽题（2026-09-24）

- 需求（用户）：**随机练习 = 只抽「学过且做错过」的知识点**；若已学的全是正确、或压根没做过题，则**弹提示、不进入练习**（不再随机抽整门课）。
  - 由选做 → 明确排除：`_random_scope_kp_ids` 里 `rate < 100` 即"有错"，`rate == 100`（全对）与无作答记录（没做过）都不入范围。
- `backend/app/routers/practice.py`：
  - 新增 `_random_scope_kp_ids(db, user_id, course_id)` —— 复用 `services/scoring.quiz_accuracy_by_kp`（与薄弱点/预警同一口径），取加权正确率 `< 100%` 的知识点；**再按"本课程的知识点"过滤一遍**。
    - ⚠️ 措辞更正（2026-09-24 二次核实）：**正确率的数值口径没有跨课程**，它就是「某学生 × 某课程 × 某知识点」——KP id 全局唯一（`teacher._next_graph_id` 全表取 max+1），一道题只属一门课，库副本实测「只取该课程作答记录重算」与全量口径**逐点完全一致**（见下方"口径澄清"）。
    - 过滤的真正理由：`quiz_accuracy_by_kp` **没有 course 参数**，它返回的是该生**所有课程**的 KP 表（键集合跨课程）。不过滤的话，切到 `C7BY3C4K` 时会拿 9 个属于 `C8WBRZKV` 的 KP 当抽题范围（实测），那些点在本课根本没题 —— 问题出在**范围选错**，不是数值算错。
  - `/practice/modes`：随机卡片文案改为「只在「学过且做错过」的知识点里随机抽题」；题量按**该范围**统计（`min(15, 范围内已发布题数)`），不再写"全课题数"。
  - `POST /practice/sessions` 新增 `elif req.mode == "random":` 分支：范围内无题时返回 `{"total": 0, "questions": [], "emptyReason": "random_scope_empty"}` 并打日志，**不再静默退化成整门课随机**。
- `assets/js/student/views/practice.js`（三处收口）：
  - `renderSelect()` 记录 `this._randomCount`（来自 `/practice/modes`）；
  - `_startMode('random')` 在 `_randomCount === 0` 时不发起组卷，直接 `Toast.warn('随机练习暂无可抽题范围', '随机练习只抽「学过且做错过」的知识点；你学过的都答对了、或还没做过题，可先用顺序练习')`；
  - `start()` 的空池分支新增第三种情形 `emptyReason === 'random_scope_empty'` → 标题「随机练习无可抽题范围」，措辞与上面一致（此前只有"无可定位薄弱点 / 该知识点暂无题目 / 当前课程无题"三种）。
- 实测（数据库副本，未触碰真实库；真实库 `course_agent.db` 校验：大小 909312、`mtime` 仍为 11:08:02，未被本次验证写入）：
  - `Ss` @ `C8WBRZKV`：范围 = `KP001 KP002 KP009 KP010 KP015 KP016 KP017 KP018 KP020`（9 个，含次要命中；KP010/KP018 本课无题，贡献 0 道）→ 随机卡片 **15 题**、组卷 **15 题**，命中 KP `KP001/KP002/KP015/KP016/KP017/KP020`，**全部落在范围内**；连抽两次题号不同（确认是范围内随机，不是固定顺序）。
  - `Ss` @ `C7BY3C4K`（该课 6 个 KP 全是 `KP027…KP032`、无已发布题）→ 范围 `[]` → 卡片 **0 题**、组卷 `total=0, emptyReason=random_scope_empty`（前端弹提示）。
  - 无作答记录的用户 → 同样 `emptyReason=random_scope_empty`。
  - 回归：`/practice/modes` 四张卡片为 `weak 10 / order 20 / random 15 / wrong 12`；`weak + kpIds=['KP001']` 仍出 3 题（未被本次改动影响）。
- ⚠️ **需要重启后端**才生效（前端刷新即可）。
- 接口契约同步：`docs/接口文档.md`（§5 智能练习）补「组卷响应 / 各模式取题范围」说明（含 `emptyReason`、`random` 的"学过且有错"口径、`weak` 不再扩散到同章）。

### 口径澄清：「正确率」到底是不是跨课程聚合的（2026-09-24 二次核实）

- 起因（用户质疑）：上一轮记录里写"正确率是跨课程聚合的"，说法**错误且危险** —— 正确率的定义是「**某学生 × 某课程 × 某知识点**」，不该是跨课程混算。
- 核实结论：**用户是对的，我原来的措辞要更正。**
  1. `services/scoring.quiz_accuracy_by_kp(db, user_id)` **没有 course 参数**，只按 `user_id` 过滤 `answer_records`（连记录自带的 `course_id` 都不用）→ 它返回的是该生**所有课程**的 KP 正确率表，即**键集合跨课程**。
  2. 但**每个 KP 的数值不跨课**：一个 KP 只属于一门课，聚合时按 KP 分桶 → 该点的分子/分母只会来自那门课的题。
  3. 支撑这一点的三条结构性前提（库副本实测）：
     - `graph_nodes` 的 KP id **全局唯一**：生成器 `teacher._next_graph_id()` 扫描**全表**取 `max+1`，注释写明"id 为全局主键，跨课程唯一"；实测 32 个 knowledge 节点 / 32 个 distinct id / 撞号 0。
     - 题目标签不跨课：全部题的 `kp_id` 与 `kp_ids` 逐条比对，指向其它课程 KP 的 **0 条**；指向不存在 KP 的 **0 条**。
     - 作答记录不脏：`answer_records.course_id` 与所属题目的课程不一致的 **0 条**（且 `submit_answer` 强制 `Question.course_id == 当前课程`）。
  4. 决定性实测：对 `Ss`，「照抄 `quiz_accuracy_by_kp` 口径但只取该课程作答记录」重算一遍，与全量口径**逐点完全一致**（`C8WBRZKV` 的 13 个 KP 全部相等；`C7BY3C4K` 两边都是空集）。
- 因此本次 `_random_scope_kp_ids` 的课程过滤**该做**，但理由要改成：**选"这门课有哪些知识点"**（范围），而不是"修数值"。前一轮的实测现象（不过滤时 `C7BY3C4K` 也拿到 9 个 `C8WBRZKV` 的 KP）正是范围错，不是数值错。
- ⚠️ 由此暴露一条架构前提：`quiz_accuracy_by_kp` / `mastery_by_kp` 这类「按 user 算、按 KP 取用」的字典，**全靠 KP id 全局唯一来做课程隔离**。消费方都是「课程内的知识点列表 × `.get(kp_id)`」（如驾驶舱 `weakPoints` 走 `learning_paths(course_id)`），所以当前是正确的；但若有第二条路径能产生撞号的 KP id，这套口径会**静默混课**。已登记为 P43。

---

## 二十九、学生端「我的学情」删除两张卡并合并末行（2026-09-24）

- 需求（用户）：删除「**能力目标达成度**」（目标图谱不存在，雷达 6 维恒 0）与「**薄弱点清单**」（同一批薄弱点已在练习页、预警页呈现，这里是第三处重复入口），并把剩下的「成长轨迹（周）」「班级对比定位」**放进同一行**。
- `assets/js/student/views/mastery.js`（只改前端）：
  - 删掉「能力目标达成度」卡片（含 `#radarChart` 容器、`card__head--col` + `目标图谱驱动` 徽标）与「薄弱点清单」卡片（含 `#weakList`、`一键靶向练习` 按钮）；
  - 原来两个 `grid g-2`（2×2 四张卡）合并为**一个 `grid g-2`**：左「成长轨迹（周）」、右「班级对比定位」，即一行两张；
  - 移除随之失效的 JS：`API.student.abilityRadar().then(...)` 雷达绘制、`#weakList` 列表渲染、以及只服务于该卡的 `[data-goto]` / `[data-ask2]`（问 AI）监听器；两处均留注释说明删除原因与日期。
  - 保留：顶部三指标、资源学习进度、知识点学习完成矩阵、成长轨迹、班级对比定位 —— 页面其余部分未动。
- 死代码处置：`assets/js/api.js:362` 的 `student.abilityRadar()` 定义保留（现无调用方），已并入 `待修复清单.md` P22 的死接口清单；后端 `/student/ability/radar` 与 `_GOAL_DIMENSIONS` 未动（P1）。
- ⚠️ 另有**两处同名指标仍在用**，数值真实、但与目标图谱无关，本次**未动**（等用户定）：`dashboard.js:178` 首页环形图、`mastery.js:61` 学情页顶部指标，值 = `goalAchieveRate = 达标知识点数(≥60%) / 总知识点数`，但标签写「能力目标达成度」、提示写死「目标基线 80%」。已记入 P1 待议（改名 or 删）。
- 校验：`node --check` 通过；`GET /assets/js/student/views/mastery.js` → 200 且已无 `radarChart` / `weakList`；全前端 grep 仅剩 `api.js` 的定义与注释。**本次只改前端，刷新即可，无需重启后端。**

---

## 三十、顺序练习选章节：没有题的知识点不显示（2026-09-24）

- 需求（用户）：顺序练习的章节/知识点列表里，**如果该知识点没有对应题目，就不要显示**（截图：第9章 排序 →「排序算法概述」实际 0 题，但仍列出来，点进去组不出卷）。
- 现状：`_renderChapterPick` 只读 `/graph?type=knowledge`（不含题量），所以无法判断有没有题 → 全部列出。
- 后端：**新增一个只读接口**（不改任何现有接口的响应、不动数据库）——
  - `GET /api/v1/practice/kp-pool` → `{ "counts": { "KP023": 5, ... }, "total": 229 }`
  - 口径与组卷一致：只统计**主 KP**（`questions.kp_id`），不按 `kp_ids` 多标签扩散 —— `create_session` 带 `kpIds` 时就是按主 KP 抽题，按多标签统计会出现「显示有题、进去抽不到」；
  - 只统计当前课程 + `status='published'`；一次 `GROUP BY kp_id` 聚合查询。
  - 影响面：**纯新增**，不改 `/graph`、不改 `create_session`、不改表结构；现有页面与接口行为完全不变。需重启后端生效。
- 前端 `assets/js/student/views/practice.js`（`_renderChapterPick`）：
  - 并行取「知识图谱节点」+「题量表」，**题量为 0 的知识点直接不列出**；整章都没有题时，连章节标题和「整章练习」一起不显示，改显示「暂无可练习的知识点」提示；
  - 每个知识点按钮后面补了「N 题」，章头文案改为「N 个可练习知识点」，卡片右上注明「只列出有题目的知识点」；
  - **降级策略**：题量接口失败时（`pool=null`）退回旧行为、全部列出、不显示题数 —— 不能因为一次请求失败就让学生以为"这门课没题"。
  - `assets/js/api.js` 新增 `practice.kpPool()`。
- 实测（数据库副本，未触碰真实库；真实库 `course_agent.db` 本次未被脚本写入）：
  - `/practice/kp-pool` 与 SQL 直查逐键一致（`C8WBRZKV`：20 个有题知识点 / 229 题）。
  - 前端过滤后：26 个知识点中隐藏 6 个 —— `KP004 顺序表`、`KP005 链表`、`KP010 串的模式匹配`、`KP012 广义表`、`KP018 拓扑与关键路径`、`KP022 排序算法概述`；无「整章全空」的章节。
  - 对照截图的「第9章 排序」：**KP022 排序算法概述（0 题）已隐藏**，保留 KP023 交换排序 5 题 / KP024 插入排序 8 题 / KP025 选择排序 10 题 / KP026 归并排序 4 题。
  - **关键断言**：把显示出来的 20 个知识点逐个拿去组卷，**没有一个返回空池**；被隐藏的 6 个逐个组卷全部 `total=0`。
- ⚠️ 需重启后端（新接口才存在；实测当前进程仍是旧代码：`/practice/kp-pool` → 404，`/practice/modes` → 401）。前端刷新即可。
