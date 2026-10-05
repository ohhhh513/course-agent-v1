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
  - **范围条**：原单行 callout 改为「图标 + 分析范围 chip（课程名/章节/时间范围）+ 一句话说明」的卡片。课程名取自 `GET /course/my`（原来只会显示 `C8WBRZKV` 这类课程号）。⚠️ **该卡片已整体删除，且随之取消 `GET /course/my` 调用，见第三十一节（2026-09-29）**。
  - **概览指标**：新增 4 张 `.stat` 卡（高频错题道数 / 累计答错次数 / 涉及知识点数 / 待关注学生数），全部由 `/analysis/errors` 返回数据现算，每张卡的 hint 注明口径，无估算、无新增接口。
  - **错题排行**：`高频错题 Top 5` 每条改为「排名徽标 + 题干 + 知识点/难度/主要错项 meta + 右侧错误率数值与进度条 + 答错次数」，颜色按错误率 60% / 30% 两档分级；空态改用带图标与引导文案的 `R.empty`。
  - **双栏明细**：共性薄弱条目追加「出错人数/学习人数」徽标与占比进度条、右侧百分比；个性异常条目改为「头像 + 姓名 + 问题标签 + 描述 + 查看学情」行式卡片；两栏空态都写明判定线。
  - **数据口径脚注**：新增卡片，逐条说明高频错题排序与错误率算法、共性薄弱（≥2 人且占比 ≥30%）、个体异常（有效学习点 ≥3 且平均掌握率 <40% 或完成率 <30%）的判定线。⚠️ **该脚注已于 2026-09-29 按反馈移除**，见第三十一节。
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
- ⚠️ 需重启后端（新接口才存在；实测当前进程仍是旧代码：`/practice/kp-pool` → 404、`/practice/modes` → 401）。前端刷新即可。

## 三十一、教师端「归因与错题分析」两个列表：卡内滚动 + 两卡等高 + 移除口径脚注（2026-09-29）

- `assets/js/teacher/views/analysis.js`（前端）：新增 `syncListWindows(boxes, n)` —— 「共性薄弱（班级层面）」与「个性异常（个体层面）」两个列表卡**共用同一个窗口高度，只完整显示 5 条**，其余条目在卡内滚动查看。
- **高度不写死像素**：量取各列表「前 5 行的真实排版高度」（首行顶部 → 第 5 行底部，含行底分隔线），取两者的**较大值**作为统一窗口 H —— 描述文字换行、字号变化时窗口仍正好 5 条，且两侧恒等高（与 `monitor.js::_clampAlertList` 固定 4 张预警卡片同一套思路）。
- **两卡等高**：内容超出 H 的一侧 `max-height:H` + 卡内滚动；**不足 H 的一侧 `min-height:H` 撑齐**（而不是把卡片缩矮）。于是两卡的标题栏、列表底边、卡片底边逐像素对齐。两侧都不足 5 条时，取内容较高的一侧作统一高度，同样等高（内容高度按亚像素取整，避免 0.4px 级别的参差）。
- 样式：列表容器加 `an-list`，卡片加 `an-card`（`align-self:start` —— 卡片高度只由「标题栏 + 窗口」决定，两侧窗口同高故卡片恒等高）；滚动条沿用项目既有观感（`scrollbar-width:thin`、6px、thumb `--brand-300`、track `--surface-3`、`scrollbar-gutter:stable`），**只在真的溢出时才加 `an-list--scroll`**，未溢出不留白。`resize` 时重算（描述换行会改行高），容器离开文档后自行摘掉监听。
- **移除页面底部的「数据口径」脚注卡片**：按反馈删掉该介绍性字段（连同 `an-note` 相关 CSS）。列表空态里的"判定线"说明保留 —— 那是空态自解释，不是页面级介绍。
- 动机：截图显示该页「共性薄弱」命中 17 个知识点、「个性异常」5 名学生，两个列表把页面拉得很长；固定为 5 条后一屏可见，其余滚动。随后发现两卡高度不一（一侧滚动、一侧缩矮）影响观感，故改为共用窗口高度。
- 实测（无头 Chrome 1500×1180，数据库副本，**未触碰真实库 `course_agent.db`**）：
  - **两卡完全对齐**：`cardTop / cardBottom / cardHeight` 与列表 `boxTop / boxBottom / boxHeight` **全部相等** —— 卡片高均为 465px、列表高均为 411px（共性薄弱 17 条 → `max-height:411px` + 滚动；个性异常 5 条 → `min-height:411px` 撑齐）。
  - **共性薄弱**：17 条 → 可见 411px / 内容 1396px；**完整可见正好 5 条**，第 5 行底边 1342.4 与容器底边 1342.4 齐平、第 6 行完全不可见；滚到底部仍只完整显示 5 条且最后一行与容器底对齐。
  - **表头固定**：卡内 `scrollTop=300` 时 `card__head` 位置不变（878 → 878），滚动只发生在列表区。
  - **`resize` 后**两卡仍等高（465 = 465）、窗口仍等于 5 行真实高度（411 = 411 = clientHeight）。
  - **「数据口径」卡片已删除**：`#view-analysis .an-note` 计数 0，页面卡片标题只剩「高频错题 Top 5 / 共性薄弱 / 个性异常」，最后一张卡即「个性异常」。
- **同日续 ①：删除范围卡里的一行说明文字** —— 「按答题记录与学习路径实时统计（不做估算），用于定位共性薄弱知识点与需要关注的学生。」按反馈删除（连同已无用的 `#view-analysis .an-scope p` 样式）。当时范围卡只保留「分析范围 + 课程 / 章节 / 时间三个 chip」。实测 `.an-scope` 内 `p` 计数 **0**、chips 文本仍为 `["数据结构与算法","全部章节","全部时间"]`，两卡仍等高（465 = 465、列表 411 = 411）。
- **同日续 ②：整块「分析范围」卡片全部删除**（按反馈「全部删掉」）—— 卡片标记、7 条 `.an-scope*` 样式，以及**只为它服务**的数据依赖一并去掉，不留死代码、不留无用请求：
  - 模板：删掉 `<div class="card">…<b>分析范围</b>…三个 chip…</div>` 整块，页面第一个元素由「范围卡」变为「概览指标」四张 stat 卡；
  - 样式：`#view-analysis .an-scope{...}` / `.an-scope__ico` / `.an-scope__ico svg` / `.an-scope__head` / `.an-scope__head b` / `.an-scope__head .chip` / `.an-scope__head .chip svg` 共 7 条全部删除；
  - 数据依赖：`Promise.all([analysis.errors, course.my])` 收敛为 `API.analysis.errors({}).then(d => …)`，删除 `scope` / `cur` / `courseLabel` / `timeLabel` 四个变量（`cur` 是 `Array.isArray(courses).find(...)`，仅被 `courseLabel` 使用）。**副作用是少发一次 `GET /course/my`**；
  - 顶部文件注释同步改写：去掉「范围条」「课程名取自 GET /course/my」，并把本次删除登记为第 4 条变更。
- **实测（无头 Chrome 1500×1180，数据库副本，未触碰真实库）**
  - 结构：`.an-scope` 计数 **0**、`.an-scope__ico` **0**、页面内文本不含「分析范围/数据结构与算法/全部章节/全部时间」、**样式表里 `an-scope` 规则也不存在**（`scopeCssRule:false`，确认不是只删 DOM）；
  - 卡片标题只剩 `["高频错题 Top 5","共性薄弱（班级层面）","个性异常（个体层面）"]`，第一个 `.grid` 的子元素为 `stat`；
  - 请求：一次完整加载（启动 + 归因页渲染）**只有 1 次 `/api/v1/course/my`**、1 次 `/analysis/errors`，`/analysis/causes` 与 `/analysis/weak-chain` 均为 0（已于本日下线）；
  - **发起者归因**（CDP `Network.requestWillBeSent` 取 initiator 调用栈）：那唯一一次 `/course/my` 的栈为 `api.js:72 ← api.js:813 ← app.js:52 ← app.js:83` —— **来自应用外壳的课程切换器，栈中没有 `analysis.js`**；即删除后归因页确实不再发起该请求（对比：手动调一次 `API.course.my()`，计数由 1 变 2，证明该口径能测出新增请求）；
  - 回归：两卡仍恒等高 —— 卡片 465 = 465、列表 411 = 411，`共性薄弱 17 条`设 `max-height:411px` 卡内滚动、`个性异常 5 条`设 `min-height:411px` 撑齐，两卡底边一致（1213.9 = 1213.9）；页面无未捕获异常。
- 纯前端改动，**刷新页面即可，无需重启后端**；未改接口、未改表结构与数据。

## 三十二、接口占位与伪数据清理（P10–P16 · 2026-09-29）

- 背景：`待修复清单.md` 第三节「三、接口占位与伪数据」（P10–P16）逐条复核后按用户确认的方案处置：
  **两个占位接口下线 + 反馈真落库；冗余端点/别名一律删净；退出登录改为真实吊销 token**。
- **先核对再动手**：出方案前先用只读 SQLite 连接实测当前库，得到硬证据（不改任何数据）：
  - `teacher_class_data`（`TeacherClassDashboard`）**0 行** → `/ai/suggest-questions` 恒返回 `[]`；
  - `intervention_templates` **0 行**、`interventions` **0 行** → `/intervention/{id}/effect` 的"对照组"没有任何真实来源；
  - `questions` 229 行 / `answer_records` 645 行，`error_type` **非空 0 条**（属 P8，本轮未动）。
- **后端**：
  1. `routers/teacher.py`：删除 `POST /question/materials`（假 `fileId`，不落盘不解析）、`POST /question/packs`（假 `packId` + `pushed:true`，不落库）、
     `POST /question/gen/stream`（`/gen` 的纯别名，全库零调用）、`GET /analysis/weak-chain`、`GET /analysis/causes`（实现真实但前端从未调用），
     以及只为它们存在的 `UploadMaterialReq` / `CreatePackReq`；`GET /question/gen/config` 不再返回恒空的 `materials` 字段（前端已无消费方）。
  2. `routers/intervention.py`：删除 `GET /intervention/{ivId}/effect`（对照组序列 `min(rate+8,100)` 系编造）；
     `GET /intervention/templates` 移除 `successRate`（原 `70+use_count*2`）与 `avgLift`（原 `5+use_count*0.5`）两个编造字段，
     只保留按 `interventions` 真实统计的 `useCount`；顺带删掉未被使用的 `done_ivs` 变量与 `date/timedelta` 导入。
  3. `routers/ai.py`：删除 `GET /ai/suggest-questions`（查恒空表）；`POST /ai/feedback` **由 TODO 空实现改为真实落库**；
     `GET /ai/sessions/{id}/messages` 每条消息补 `messageId`（`M{chat_messages.id}`），供反馈定位到具体回答。
  4. **新增数据表** `ai_feedback`（`models/ai.py::AiFeedback`）：`id / message_id / session_id / user_id / course_id / feedback / created_at`；
     由 `init_db()` 的 `create_all` 建出（**已获用户同意**）。
     `course_id` 来自 `get_current_course_id`（含成员校验），**不给默认值**，避免落进演示课；`feedback` 仅接受 `1 / -1`，其它取值返回 `code=400` 信封。
  5. **P14 退出登录吊销 token**（`middleware/auth.py` + `routers/auth.py`，用户选定「进程内黑名单 + jti」）：
     `create_jwt` 增加 `jti`；新增吊销表 `_REVOKED_JTI`（`jti → exp`，写入/校验时惰性清理过期项）与 `revoke_token()` / `is_revoked()`；
     `POST /auth/logout` 改为**依赖登录**并写入吊销；`get_current_user` / `get_current_user_optional` 命中吊销即 401（`登录状态已失效，请重新登录`）。
     ⚠️ **已知限制（已写入文档）**：吊销表在进程内 —— 进程重启后旧 token 会重新可用；多 worker / 多实例不共享。当前单进程 uvicorn 下「登出即失效」成立。
- **前端**：
  - `teacher/views/question.js`：删除「素材库」卡（含 `${cfg.materials.map(...)}` 渲染）、「模拟上传」弹窗与其点击绑定、生成结果区的「生成靶向补练包」按钮及绑定 —— 出题页不再有任何"点了会说成功、实际没产物"的入口。
  - `student/views/chat.js`：👍/👎 按钮带 `data-mid="${m.messageId}"`；点击改为提交 `{messageId, sessionId, feedback: 1|-1}`；
    `onMeta` 记录流式回答的 `messageId`，`finish()` 回填到消息对象；无标识时拒绝提交并提示，`catch` 后提示失败（新增两条错误 Toast 文案）。
  - `api.js`：删除 `question.upload`、`question.createPack`、`ai.suggestQuestions`、`ai.chat`、`analysis.weakChain`、`analysis.causes`、
    `intervention.effect` 定义，以及**只被 `ai.chat` 使用的 `mockAnswer` 整段死代码**（约 100 行）。
- **文档**：同步更新 `docs/接口文档.md`（注销状态改 ✅、删 6 个端点行、补 `/ai/feedback` 说明、`templates` 去伪说明）、
  `docs/页面与功能清单.md`、`docs/后端对接指南.md`、`docs/项目真实交互梳理.md`（ai.py 端点表、僵尸表、死接口、待决项逐条改写），
  `待修复清单.md`（P10–P16 速查表与正文全部标 `[x]` 并附处置说明）。
- **回归脚本修正（附带发现）**：`backend/regression_test.py` 有两处**早就失效**的问题，本次一并修好：
  1. 用例表里的账号 `student/123456`、`teacher/123456` 在当前库中**不存在**（真实账号为 `stu01…stu10` / `wangjg`），按原脚本登录直接崩；
     现改为可配置（`STUDENT_USER` / `TEACHER_USER` / `PASSWORD`，默认取真实账号），并把 `login()` 对失败响应的处理改为容错；
  2. 硬编码的 `classId=CL2301`、`course_id="C001"` 均已过期（真值 `CL2601` / `CCHYJTKE`），改为**运行时动态发现**（`/course/my`、`/teacher/classes`、`/teacher/students`）；
  3. 新增断言：8 个已删端点必须 `404/405`；`/ai/feedback` 真落库（含缺 `messageId` → 422、非法值被拒、点踩落库）；`/auth/logout` 后旧 token → 401；
     并放宽 SSE 出题用例的入参（该端点要求至少一个知识点，原脚本必然拿 400）。
- **实测（独立 8010 实例 + `sqlite3.backup()` 数据库副本，全程未触碰用户 8000 与真实库）**：
  - `regression_test.py`（`BASE=http://127.0.0.1:8010`）：**`ALL PASS  total=44 passed=44`**，
    其中 `auth/logout (revoke token) -> logout=200 reuse_old_token=401`、`ai/feedback -> up=200 noMessageId=422 badValue=200/code=400 down=200`、
    8 条 `GONE -> 404/405` 全部通过。
  - `dev_tools/verify_p10_16.py`：**`ALL PASS passed=16 failed=0`**。关键证据：
    - 反馈真落库：请求前后 `ai_feedback` 行数 `6 → 7`，落库行 `('M-VERIFY-UP','CH-VERIFY','2026010101','CCHYJTKE',1)` 与请求完全一致；点踩存 `-1`；
    - 被拒请求（`feedback=0`）**不落库**；
    - `templates` 去伪：插入 1 个模板 + 2 条同场景干预后，`useCount=2`（真实统计），返回字段为
      `['desc','name','resources','scene','steps','tags','tplId','useCount']` —— **`successRate` / `avgLift` 已不存在**；
    - 吊销粒度：token A 登出后 A → 401，同一用户的 token B 仍 200（按 token 作废，不是清空该用户全部会话）；
    - 表结构：`ai_feedback` 由启动建表产生，7 列齐全，且记录带真实 `course_id`。
  - 无头 Chrome（真实 Chrome + CDP，1500×1100 @2x，3 组探针，页面无未捕获异常）：
    - 教师端 `#question`：`hasGenBtn=true`、知识点 chip **26** 个（页面本身正常），而 `hasMaterialUpload=false`、页面文本**不含「素材库」**、
      `hasPackBtn=false`、`window.API.question.upload` 为 `undefined`；`API.question` 键为
      `["genConfig","generate","genStream","ingestStats","drafts","draftUpdate","draftDelete","draftPublish","bank","update","review","remove","importBatch"]`（无 `upload` / `createPack`）；
    - 学生端 `#ai`：2 个反馈按钮**全部带 `data-mid`**（值 `M12`，来自接口下发）；
    - 点击点赞 → 网络探针抓到 `POST /ai/feedback`，body `{"messageId":"M12","sessionId":"CHD175B97EE4","feedback":1}`；
    - **闭环**：随后查副本库，`ai_feedback` 新增第 9 行 `('M12','CHD175B97EE4','2026010101','CCHYJTKE',1)` —— 界面一次点击 → 真实入库。
- 影响面与后续：
  - 前端为静态资源，**刷新页面即生效**；后端改动需重启（用户 8000 端口实例仍是旧代码）。
  - 素材上传请改用真实入口 `POST /teacher/resources/upload`；题目文件导入用 `POST /question/import/file`。
  - `/ai/chat`（非流式）**保留**：它是真实实现且被接口文档、智能体工作流说明引用，供无头/脚本调用。
  - 若要跨重启持久化吊销记录，需另建 `revoked_tokens` 表（属表结构变更，需先议）。
  - `teacher_class_data` 表已无任何读取方（唯一读者已删除），可随下次删库重建一并移除。
  - 本次未动的邻近问题：P7（`mainWrongOption` 仍是 `"B" if wc>t*0.6 else "C"` 启发式）、P8（题库无错误类型标注入口）、P17/P38（越权类）。

## 三十三、隔离与权限：角色校验 + 课程归属（P17 / P18 / P38 / P39 + 补做 P4 / P9 · 2026-09-30）

- 背景：处理 `待修复清单.md` 第四节「四、隔离与权限」。经用户确认本轮范围为**安全隔离四件套（P38 + P17 + P39 + P18）**；
  P40（打卡/资源时长表加 `course_id`）**本次跳过、保持登记**；越权一律返回 **403**；v1 实际缺失的 §一/§二 条目本轮**只补 P4 / P9**。
- **后端**：
  1. `middleware/auth.py`：新增 `require_teacher` 依赖 —— `role != "teacher"` 直接 `HTTPException(403, "仅教师可访问该接口")`。
  2. `routers/teacher.py`：`router` / `analysis_router` / `question_router` 三个 router 统一挂
     `dependencies=[Depends(require_teacher)]`（一处挂载即覆盖该前缀下全部端点，无需逐端点改）。
  3. `routers/intervention.py`：`intervention_router` / `report_router` 同样挂载。
  4. **P17 课程归属校验**：`teacher.py::update_question` / `remove_question` / `review_questions` 增加
     `q.course_id != course_id → fail("无权操作其它课程的题目", 403)`；`remove_question` 由「先删再判」改为
     「先查 → 判归属 → 再删」（避免已删除才报错）；`intervention.py::report_detail` / `export_report`
     按 `detail_json.meta.courseId` 判归属 → `fail("无权查看/导出其它课程的报告", 403)`。
  5. **P39 课程收敛**：`teacher.py` 的今日 `PracticeSession`、今日 `AnswerRecord`、学生最近活跃、个体画像答题明细、
     活跃趋势时长、预警趋势作答、归因答题集、薄弱链路、题库正确率聚合，以及 `teacher_dashboard` 的 `kpRanking` 聚合、
     热力图的「掌握率」分支，全部补 `course_id` 等值过滤；`_student_lp_stats` / `_student_answer_stats` 补 `course_id` 形参
     （4 个调用点同步）；`_generate_interventions_from_db` 补 `course_id` 形参与过滤 —— 并因此发现
     `intervention_list` 端点原先**没有** `course_id` 依赖（改签名后直接 500），本轮一并补上。
     ⚠️ 首轮用**单行扫描器**排查时漏掉了多行写法的查询（统计 helper、`kpRanking`、热力图掌握率分支、干预生成），
     后改用多行（括号配对）扫描全量复查才补齐 —— 教训：静态扫描要能处理换行。
  6. **P18**：删除 `models/{alert,course,graph,practice,question}.py` 中 **9 处** `default="C2026DS001"`
     （`Alert`/`Resource`/`GraphNode`/`GraphLink`/`KpDetail`/`LearningPath`/`PracticeSession`/`AnswerRecord`/`Question`）：
     此后 `course_id` 必须显式传入，漏传即报错，不再静默落到演示课。
  7. **补做 v1 缺失项**：P4 —— `analysis_errors` 的答题集与 `class_lps` 补 `course_id`；
     P9 —— `student.py::student_dashboard` 的 `ans_dates` / `cur_week_rows` / `last_week_rows` / `weakPoints[].errorCount` 补 `course_id`。
- **回归脚本**（`backend/regression_test.py`）：新增 `check_forbidden()`（同时接受 HTTP 403 与信封 `code=403`）；
  新增 6 条 P38 断言（学生 token 打教师接口 → 403）与 2 条 P17 断言（不存在的 `qId` → 404，验证新校验路径未引入 500 或静默成功）。
- **文档**：`docs/接口文档.md` 新增 §1.6「角色与课程隔离」（两种 403 的落点区别），并给 §7 教师端 / §8 归因（`course_id` 收敛）/
  §9 题库 / §12 干预与报告补 🔒 角色说明；§10.2 里"模型 `course_id` 默认值 `C2026DS001`"改为**历史说明 + 已删除**；
  `待修复清单.md` 第四节 P17/P18/P38/P39 标 `[x]` 并附处置与实测，另加「v1/v2.1 归属提醒」。
- **实测（独立 8010 实例 + `sqlite3.backup()` 数据库副本，全程未触碰用户 8000 与真实库）**：
  - `regression_test.py`：**`ALL PASS  total=52 passed=52`**（其中 `P38 student->teacher/*` 6 条全 403、
    `P17 question PUT/DELETE unknown -> 404` 2 条通过）。
  - `dev_tools/verify_p17_38_39.py`：**`ALL PASS  passed=20 failed=0`**。关键证据：
    - **P18**：反射 `Base.metadata.tables` 遍历所有表，`course_id` 列 `default` **全部为 `None`**（0 处残留）
      —— 用反射而非 grep，可覆盖 `**values` 动态赋值等 grep 看不到的写法；
    - **P17**：跨课程 改题 / 删题 / 审核 / 读报告 / 导出报告 **5 项全部 403**；反证别门课题目 `difficulty/status`
      未被改动（仍为 `(3, 'published')`）；对照组本课题目可正常修改（`code=0`）；
    - **P38**：学生 token 打 8 个教师端接口（`teacher/classes`、`teacher/dashboard`、`teacher/heatmap`、`teacher/students`、
      `analysis/errors`、`question/bank`、`report/list`、`intervention/list`）**全部 HTTP 403**；教师 token 对照组正常；
    - **两级噪声敏感性对照**（向第二门课注入数据后比对 11 个接口的响应 JSON）：
      **L1 合法噪声**（第二门课自己的 12 条今日错答 + 3 条练习会话 + 3 条学习路径，归属一致）→ **逐字不变**；
      并用"不过滤 vs 过滤"的原始 SQL 计数证明噪声足够强（该生：今日答题 不过滤 **20** → 过滤后 **0**；
      全部答题 **133 → 113**；学习路径 **31 → 26**；练习会话 **25 → 22**），即"不变"确实来自课程过滤，不是噪声太弱的假通过。
  - 无头 Chrome（真实 Chrome + CDP，1600×1150 @2x）：教师端 8 个入口（驾驶舱 / 学情监测 / 归因分析 / 题库 / 报告 /
    干预兜底路由 / 课程目录 / 知识图谱编排）全部正常渲染、课程上下文正确（`CCHYJTKE`）、渲染量与真实库一致、
    **页面未捕获异常：无** —— 证明加 `require_teacher` 后教师端自身不受影响。
- **已知残余（已登记，本轮按约定未改）**：
  - **P43**：L2 脏数据（行内 `course_id` 与 `kp_id/q_id` 归属不一致）下 `student/dashboard`、`student/mastery/matrix`、
    `student/alerts` 三个接口会变 —— 根因是 `services/scoring.quiz_accuracy_by_kp` 等按 `user_id` 取值、**无课程参数**。
    这正是清单 P43 所述「靠 KP id 全局唯一做课程隔离」风险在真实接口上的可复现证据。
  - **P40**：`study_checkins` / `resource_study_log` 缺 `course_id` 列（属表结构变更，需先议）。
  - **P5 / P6 / P7 / P8**：v1 仍未落地（章记录来自同源 v2.1 仓库），另开一轮。
- **影响面与后续**：
  - 前端为静态资源，**无需改动、刷新即生效**；后端改动需**重启**（用户 8000 端口实例仍是旧代码）。
  - **破坏性变更（有意为之）**：凡"允许教师跨课程操作任意题目 / 报告"的用法，现在一律 403。
    前端教师端本身只操作当前课程，实测无影响；第三方脚本若依赖旧行为需同步调整。


## 三十四、学情监测「共性薄弱识别」chip 内数字与名称基线错位（2026-09-30）

- 现象（用户截图）：`teacher.html#monitor` 底部「共性薄弱识别（班级平均学习完成率低于 80% 的知识点）」
  的 chip 里，百分比数字比知识点名称**高 2px**，肉眼看着上下错位。
- 先排除数据问题：按 `learning_paths`（`course_id=CCHYJTKE` 且 `status != 'todo'` 的 `mastery`）复算班级平均，
  与截图**逐项一致**（选择排序 55.8 / 广义表 59.9 / 栈 62.4 / 查找 63.2 / 最短路径与生成树 64.3）
  —— 数据没配错，是渲染问题（名称与数值的配对由 `heatmap` 同一 `j` 下标取 `kp_names[j] / kp_avg[j]`，无错位空间）。
- 根因：`base.css` 的 `.chip` 是 `display:inline-flex; align-items:center`，而 `teacher/views/monitor.js`
  模板写的是「图标 svg + **裸文本**知识点名 + `<b class="mono">数字</b>`」——名称（匿名 flex 项）与数字
  （`.mono` → `--font-num` = Bahnschrift）成了**两个独立的 flex 项**，被 `align-items:center` **各自按盒子居中**；
  两者字体的 ascent 不同（中文 13 / Bahnschrift 10），基线于是差了 2px。
  实测 `baselineDelta = -2px`（数字基线上移）、名称项居中 0、图标居中 0。
- 修法（**局部**，不动全局 `.chip`）：
  - `assets/js/teacher/views/monitor.js`：把名称与数字包进同一个基线组
    `<span class="chip__txt">${name} <b class="mono">${avg}%</b></span>`；
  - `assets/css/base.css`：新增 `.chip__txt { display:inline-flex; align-items:baseline; gap:5px }`
    与 `.chip__txt b { line-height:0 }`。
- 为什么不直接给 `.chip` 加 `align-items: baseline`：**注入式对照实验**实测，该改法虽能把基线差归零，
  但会把整组文字相对 chip **顶高 3px**（`textOffCenter = -3`），纯文字 chip 会被一起顶起来 —— 故改为局部包装。
- 数字为什么要 `line-height: 0`：Bahnschrift 默认行高约 18px > 中文行盒 16px，会把基线组撑高 2px，
  整组居中后名称反而上移 1px（第二组注入对照：`textOff` 0→-1）。让数字不参与行盒高度后，
  名称停在**原位**、只有数字落下来对齐。
- 实测（独立 8010 + `sqlite3.backup()` 副本，无头 Chrome 真实量测全部 5 个 chip）：
  `baselineDelta = 0`（5/5）、名称 `textOffCenter = 0`（与原位置逐像素相同）、数字下移 2px（`pctOffCenter` -0.5 → +1.5）、
  图标仍居中（0）、chip 高 **28px** / chip 间距 **6px** / 名称到数字间距 **5px** 全部不变；页面未捕获异常：无。
  教师端 8 个入口冒烟复跑仍全部正常。
- 未改（同源但差异 < 1px，未获指示）：`practice.js` 章节 chip 的 `.chip__count`（同族字体、10.5px，基线差约 0.8px）。
- 影响面：纯前端静态资源，**Ctrl+F5 强刷即生效**，无需重启后端。

## 三十五、隔离与权限（第二轮）：统计口径补课程参数 + 预警生命周期（P41 / P43 / P44 / P47 / P48 · 2026-09-30）

本轮按确认的范围处理清单第四大节剩余条目：**P43 / P44 / P47 / P48 全部落地，P41 两处都修**；
P40（打卡/资源时长表加列）与 P45（题库按主 KP、图谱按主∪标签的两套口径）按决定**跳过、保持登记**。

### P43 · 统计口径函数补 `course_id`

- 改动：`services/scoring.quiz_accuracy_by_kp(db, user_id, secondary_weight, course_id=None)` 与
  `services/kp_stats.mastery_by_kp(db, user_id, course_id=None)` 新增**可选** `course_id`（默认 `None` = 保持历史口径）；
  作答记录 / 资源表按 `course_id` 过滤。
- 消费方全部收敛：`routers/graph.py::_mastery_for_user / _quiz_mastery_for_user / _mastery_from_records`（共 6 个调用点）、
  `routers/student.py`（驾驶舱 / 资源进度同步 / 学情矩阵）、`routers/practice.py::_random_scope_kp_ids`、
  `routers/teacher.py::review_alert`（用 `alert.course_id`）、`services/alert_detector.py`（改为**按课程分组**检测：
  每个学生遍历「有作答记录的课程 ∪ 现有预警所在的课程」）。
- 为什么平时看不到 bug：`graph_nodes` 主键是 `(id, graph_type)`（不含 `course_id`），同一 graph_type 下 KP 号
  在 DB 层本就唯一（`teacher._next_graph_id` 全表取 max+1）。本条是把「靠唯一性间接隔离」换成显式按课程收敛。
- 实测（8010 + 库副本 + 注入第二门课 `CVERIFY2`）：旧口径（`course_id=None`）混入别课知识点 `VFY2KP01/02/03`
  （键集合 25 → 28），新口径完全不含；学生端 3 个接口 × 10 名学生 + 教师端 6 个接口共 **36 个响应逐字不变**
  （比对时忽略信封 `traceId`）。

### P44 · 预警生命周期兜底

- `services/alert_detector.py::detect_alerts` 主循环改为「现有预警 ∪ 本次证据」**并集遍历**：
  证据不足（不在正确率表里，或不同题数低于门槛）的旧预警删除，`ignored`（教师判定过的历史记录）保留；
  评估范围覆盖「有作答记录的课程 ∪ 现有预警所在的课程」，所以**答题记录被清空**时也会走到该课程把预警清掉。
- 实测：清除学生 `2026010104` 在 `KP015` 上的 3 条答题记录后再跑检测 → 该 `open` 红警被删除
  （`deleted=1`，复查剩余 0）；反证：清除后该知识点已离开 `quiz_accuracy_by_kp` 的返回 —— 旧逻辑的循环根本不会到达它。

### P47 · 薄弱点清单让有预警的知识点优先占位

- 新增 `services/scoring.weak_kp_ids(db, user_id, course_id, candidates, limit)` 作为「薄弱点判定 + 排序 + 截断」的
  唯一入口，排序键 = **「有未处理红/黄预警优先 → 加权正确率升序」**；
  `/student/dashboard` 的 `weakPoints` 与 `/practice/modes` 的 `weak` 题量共用它，两边口径不再各写一份。
- 实测（构造性）：学生 `2026010106` 的 `KP010`（是薄弱点、当前无预警、排不进前 5）插入一条预警 → 立刻挤进前 5
  （`[…, KP015]` → `[…, KP010]`）；移除该预警 → 顺序**逐字还原**。

### P48 · 纯标签点预警门槛提到 ≥3 道

- `services/alert_detector.py` 按知识点区分门槛：本课程里**没有一道题以它为主 KP**（纯标签点）
  → `ENGAGE_MIN + 1 = 3` 道不同题；有主命中题的点保持 `ENGAGE_MIN = 2`。
- 实测：本课程纯标签点 = `KP005 / KP010 / KP012 / KP018 / KP022`；6 个「该点上 `hits=2` 且正确率 <60%」的组合
  （`2026010105/KP005`、`2026010106/KP010`、`2026010107/KP010`、`2026010108/KP010`、`2026010109/KP005`、`2026010109/KP010`）
  在旧门槛下会建预警、现已全部挡掉；主命中点的同条件组合仍正常挂预警（0 例漏挂）。

### P41 · 练习模式文案与实现对齐

- 顺序练习卡片文案：「按章节与知识点前后置顺序逐题推进」→「选定章节或知识点后逐题推进，做错过的题优先」
  （后端从未按 `graph_links(relation='pre')` 排序，本课关系边 0 条、`kp_details.pre_kp` 全空）；
  前端 `assets/js/student/views/practice.js` 的「按前后置关系排序」同步改为「做错过的题优先」。
- 薄弱点强化卡片题量：由「全课题数」改为按**真实薄弱点题池**（前 5 个薄弱知识点下的已发布题数）统计。
- 实测：某学生 `weak.count = 2` = 真实题池 2（全课 229 题），证明不再用全课口径。

### 验证与影响面

- `regression_test.py` → **ALL PASS total=52 passed=52**（无回归）。
- `dev_tools/verify_p41_43_44_47_48.py` → **ALL PASS passed=25 failed=0**。
- 无头 Chrome（学生端 `stu07`）：驾驶舱 / 智能练习 / 我的学情 / 预警与提醒 四个入口正常渲染，
  **页面未捕获异常：无**。
- 全程使用 8010 独立实例 + `sqlite3.backup()` 生成的库副本，真实库仅 `mode=ro` 只读查询，未改动。
- 同步文档：`待修复清单.md`（P41/P43/P44/P47/P48 标 `[x]` + 速查表 + 表头）、
  `docs/接口文档.md`（§1.6 补统计口径隔离与薄弱点口径统一；`/practice/modes` 表格行补口径）。

## 三十六、前端残留（第五大节）：mock 分支彻底删除 + 断链/死文件/失效文案清理（P19–P26 / P36 · 2026-09-30）

本轮按确认的范围把清单第五大节 8 条**一起做完**（P19 / P20 / P22 / P23 / P24 / P25 / P26 / P36），
并把复核后确认**早已自愈**的 P21 一并结案。决策口径：
**P20 → 改跳已有视图**；**P23 → 删掉示例账号字样**；**P22 → 彻底删除 mock 分支**；
其余按「只做既有文案替换/更正，不新增任何可见文案」执行。

### P22 · `assets/js/api.js` 彻底删除 mock 分支（本轮最大改动）

- 复核结论：比清单写的更严重 —— `window.MOCK` **全仓已无定义**，mock 分支不是"显示假数据"而是**一跑就抛错**。
- 删除：`config.mode` / `config.latency` / `delay()` / `ok()` / `const M = () => window.MOCK;` /
  本地账号表（`ACCOUNTS_KEY` / `getAccounts` / `saveAccounts` / `toUser`）/ 无人调用的 `ai.agentStatus`
  （`analysis.weakChain` / `causes` / `student.abilityRadar` 已于 2026-09-29 随 P1、P8 删除）。
- `request` / `download` 摘掉 `if (config.mode === 'http') { … }` 包装，函数体归一缩进（去掉一层嵌套）。
- **59 处 mock resolver 实参**（每个方法的第 4 个参数）全部删除 —— 23 处内联兜底 `() => ({…})`、
  33 处 `M().xxx`、以及 `intervention.list` 的多行 resolver。
  用「括号配对 + 字符串感知」的扫描器按顶层逗号切分参数，`len(args) == 4` 才删第 4 个，避免误伤。
- 保留：`config.activeCourseId`（被大量使用）与 `auth.logout()` 的本地清 token 行为（不扩大范围）。
- 结果：文件 **710 → 575 行**；`mock` / `M()` / `window.MOCK` 字样仅剩文件头「已于 2026-09-30 彻底移除」的说明。

### P19 · 删除教师端死文件 `teacher/views/resource.js`

- 复核更正：不是"被 `structure.js` 覆盖"，而是 `teacher.html` **从未加载**该文件；
  且 `Router.register('resource', …)` 定义在 `structure.js:615`、渲染目标却是 `#view-structure`，
  所以直接访问 `#resource` 会是**白屏**（清单未登记的连带隐患）。
- 处置：删除整文件（16KB）+ 清三处配套死链 —— `teacher.html` 的 `<section id="view-resource">`、
  `structure.js:615` 的 `Router.register('resource', {…})`（保留 `'structure'`）、
  `assets/js/teacher/app.js` 的 `ViewFns.resource`。
- ⚠️ 保留 `assets/css/app.css:1269/1274` 的 `#view-resource …` 规则 —— 经核实**是学生端在用**
  （`student/views/resource.js:41/55/70`），不能删。

### P20 · 驾驶舱待办断链改跳已有视图

- 根因：`Router.go(key)` 对未注册 key **静默 return**（`if (!this.views[key]) return;`），
  而后端 `todos[].target` 给的是语义标识 `alerts` / `students`，从来不是视图名 —— **两条待办都断链**。
- 处置：`assets/js/teacher/views/dash.js` 增加 `TODO_TARGET` 映射表 + `gotoTodoTarget()`，
  把 `target` 映射到「已注册视图 + 目标卡片锚点」再平滑滚动：
  `alerts → monitor#alList`（学情监测看板 · 异常预警列表）、`students → monitor#stuList`（学情监测看板 · 学生学情列表）。
  两处点击处理器统一改走 `gotoTodoTarget()`。**未新增任何可见文案。**

### P23 / P24 / P25 / P26 / P36 · 失效文案与注释

| 条目 | 位置 | 改动 |
| --- | --- | --- |
| P23 | `index.html` `DEMO_HINT`、`start.bat` 横幅 | 三角色提示统一为「账号由管理员在管理端创建」（admin 保留真实存在的 `admin` 说明）；`start.bat` 按**字节**精确删除两行 `student / 123456`、`teacher / 123456` |
| P24 | `assets/js/student/views/practice.js` 报告卡 | 「能力目标增益」→「**答对得分**」（数值实为本次答对题的分值合计，与目标图谱无关） |
| P25 | `index.html` 功能列表、`home.html` | 「AI 自动归因与干预策略推荐」→「错题自动归因分析」；`home.html` 四处对齐现状（含清单**漏登记的 3 处**：徽标「三图谱导航」、教师端「AI 自动归因并推荐干预策略」/「教学干预」），并把**写错的学期**更正为库中真实值「2026-2027 学年 第一学期」 |
| P26 | `assets/js/charts.js` 分节注释 | 「1. 三大图谱（力导向关系图）」→「1. **知识图谱**（力导向关系图）」；依据：本课程 `graph_nodes` 只有 `chapter`(9) + `knowledge`(26)，**problem / goal 恒为 0** |
| P36 | `assets/js/student/views/mastery.js` | 5 处统一为课程内口径：卡片标题「课程内对比定位」、徽标「课程内第 N / M 名」、图表系列「课程内平均」/「课程内最高」、表头「课程内平均」 |

### P21 · 复核确认已不存在（结案，非本轮改动）

- `assets/js/student/views/dashboard.js:177` 早已改用真实值 `m.totalKpCount`，8010 实测渲染 **「共 26 个」**
  （＝本课程知识节点真实数）。清单原写的「实际 32 个」也已过时（旧课程/旧编号的数字），属早期迭代自然修复。

### 验证与影响面

- `regression_test.py` → **ALL PASS total=52 passed=52**（无回归）。
- 无头 Chrome（真实点击 / 真实取数）：
  - 登录页 + 首页：三种角色提示无假账号、`123456` 零残留；旧字样（三大图谱/三图谱/AI 自动归因/教学干预）4 项残留检查全 false；学期徽标＝真实学期。
  - 学生端：环形图「共 26 个」；我的学情卡片/徽标/表头全为「课程内」口径，「班级」零残留。
  - P24 真实练习：跑 3 题（1 对 2 错）→ 报告卡 `['正确率','答对 / 总题数','总用时','答对得分']` = `['33.3%','1/3','12"','+5']`。
  - 教师端：点「去处理」→ `#monitor` + `#alList` 可见；`gotoTodoTarget('students')` → `#monitor` + `#stuList` 可见；
    `#view-resource` 已不存在、`resource.js` 加载数 0、`location.hash='#resource'` 回落 `view-dashboard` 无白屏；8 个入口全渲染。
  - 以上各页 **未捕获异常均为：无**；7 个改动 JS 全过 `node --check`。
- **前端渲染层**（`assets/js/**`、`*.html`）旧文案扫描：`三大图谱` / `三图谱` / `student / 123456` /
  `teacher / 123456` / `能力目标增益` / `班级对比定位` / `班级第` → **0 处**。
- ⚠️ 例外（**不在本轮范围、未动**）：后端 `models/graph.py` / `routers/graph.py` 的模块 docstring 仍写「三大图谱」——
  这两处**描述是准确的**（v1 的 `graph_nodes.graph_type` 与 `CATEGORY_COLORS` 确实同时支持 `knowledge` / `problem` / `goal`，
  problem / goal 的下线属清单 §一 的 P2 / P3，已约定另开一轮）；另有 4 份 `docs/*.md`
  （`数据模型与Mock说明.md`、`数据模型与字段说明.md`、`课程结构与图谱编辑-设计方案.md`、`项目真实交互梳理.md`）
  含「三大图谱 / 三图谱」，属清单 **P29（文档口径过时）**，本轮未动。
- 全程使用 8010 独立实例 + `sqlite3.backup()` 生成的库副本，真实库仅只读、用户 8000 实例未触碰。
- 同步文档：`待修复清单.md`（第五大节 8 条标 `[x]` + P21 结案注 + 速查表 9 行 + 表头）、`docs/README.md`、
  根 `README.md`、`docs/前端架构与运行.md`、`docs/后端对接指南.md`、`docs/接口文档.md`、
  `docs/团队交接与开发指南.md`、`docs/鉴权与会话方案.md`、`docs/页面与功能清单.md`、`docs/项目真实交互梳理.md`
  （9 个文档同步 mock 移除 / 三图谱纠正 / 视图名与目录树更新，全部保留 CRLF）。

## 三十七、仓库卫生与文档（第六大节）：脱管大文件 + 清垃圾文件 + 文档口径更正（P27 / P28 / P29 · 2026-09-30）

本轮按确认的范围处理清单第六大节三条。决策口径：**P27 → B 档（脱管 + 删 pytest 残留）**；
**P29 → 清单登记的 3 个文件 + 漏登记的 3 个文件**；本轮只改文件，**不执行 git commit**。

### P27 · Git 脱管大文件与临时库

- 复核更正：清单写「`rag.db` 28MB、6 个 `course_agent.db.bak.*`、`resource_registry_snapshot.json`」——实测
  `rag.db` 只有 **2.14 MB**，6 个 bak 与快照**早已不在仓库**。真正的元凶是 `backend/data/.pytest-tmp-*`：
  **27 个文件 / 15.56 MB**（2026-09-06 的 pytest 残留，占当时被跟踪总体积的 **74%**）。
- 处置：`git rm -r --cached backend/app/data/st/rag.db backend/data` —— **只清索引，磁盘文件原样保留**
  （`rag.db` 是 RAG 库，代码运行时要读）；`backend/data/.pytest-tmp-*` 三个目录**移入隔离区**而非直接删除。
- 结果：被跟踪文件 **206 → 175 个**，总体积 **21.10 MB → 3.40 MB**；
  `git ls-files | grep -E "\.db($|-)|pytest-tmp|_snapshot\.json"` → **无输出**。
- ⚠️ `.git` 历史里的 35.84 MiB 大对象（`rag.db` 曾 11 个版本、原始 129.89 MB；`main.db` 12 个版本）**未处理** ——
  彻底瘦身要 `git filter-repo` + **force push**（改写已推送哈希、协作者需重新 clone），属 C 档，未执行。

### P28 · 垃圾文件

- `assets/js/teacher/views/111.txt`、`backend/app/111.txt`（内容 `Ciallo～(∠・ω<)⌒☆`，sha1 相同）、根目录空文件 `1.55.3`（0 字节）。
- 全仓**无任何代码引用**（`1.55.3` 只作为 `requirements.txt` 里 `openai>=1.55.3` 的版本号出现，与文件无关）。
- 处置：各留副本到 `<workspace>/verify_20260930_p6_repo/backup/` 后 `git rm`。

### P29 · 文档口径更正（18 + 14 处）

| 文件 | 更正内容 |
| --- | --- |
| 根 `README.md` | ① 演示账号表（`student` / `teacher` + 陈思远 / 李文博）→ 改为「账号来自数据库：`admin` / `admin` + 由管理员创建」；② "种子写入 12 名学生 + 1 名教师…首次启动会执行 `run_seed()` 填演示数据" → **事实错误**，实际由 `DEMO_SEED=1` 门控、默认关闭；③ §6 模块现状表三条（"数据为空 / `answer_records` 仅 2 条"、"雷达"、"占位清单"、"批量导入 401 bug"）全部重写为真实状态 |
| `docs/README.md` | `config.mode = 'http'`（P22 已删该配置）→ `config.baseURL`；端点数 **130 → 101**；数据规模 408 全 `todo` / 仅 2 条 → **645 / 260 / 51**；两端视图明细 |
| `docs/项目真实交互梳理.md` | `POST /logout` 写"占位" → 已真实吊销；`student.py`「输出恒 0/空」→ 数据已非空；§三 实测行数表整表（`users` 13→12、`courses` `C2026DS001`→`CCHYJTKE`、`graph_nodes` 67(34/19/14)→35(26+9)、`graph_links` 79→34、`answer_records` 2→645、`alerts` 0→51、`messages` 0→18、`resource_progress` 0→401、`study_checkins` 1→125、`practice_sessions` 40→163、`reports` 1→4 等）；§3.3 结构性缺口重写；§四 耦合点 #1/#2/#3/#4/#5 改写、#10 标已解除；§五 `chunks 1480 → 458`；附录两条验证项 |
| `docs/团队协作开发手册.md` | 更新日期 2026-09-11 → 2026-09-30；"当前仅 2 条，是首要补齐目标" → 实测 645；§3.4 数据规模表整表重写；§3.3 上方"两者都空转"改为"输入数据为空时"；故障表里 `C88QUSR4`（**同源 v2.1** 的课程号）→ 改为不依赖具体课程号的表述 |
| `docs/后端对接指南.md` | "用演示账号 student/123456 进学生端；teacher/123456 进教师端" → 账号来自数据库 |
| `docs/团队交接与开发指南.md` | 交接清单的登录校验项去掉不存在账号；"已知两大缺口（AI 未接、题库/学情不足）" → 实际缺口改为"空库无教师/学生账号" |

**只做事实替换，未新增任何说明性文案。**

### 补充更正（同日）

- `.gitignore` 末尾那段「已跟踪文件脱管清单」是**给本次任务留的待办指令**，随 P27 完成改为已执行记录；
  其中「请保留 `st_bank/after_class.json` / `ai_samples.json`」**已失效** —— 两文件已不在仓库与磁盘上，
  题库切片的唯一通道是 `ingest_question_bank()`（切主库 `questions` 表），原先读该文件的路径已废除
  （`agent_st/rag/ingest.py` 与 `rag/bank.py` 均有注明）。
- `backend/run_st_ingest.py` 的 docstring 第 1 步同步更正（仍写"课后题库 after_class.json"，实际走
  `ingest_question_bank()`）；该脚本正是 `.gitignore` 尾注推荐的重建命令，口径必须一致。
- 以上均为注释 / docstring，**零行为改动**。

### 验证与影响面

- `git ls-files` 三项校验：无 `*.db` / 无 `pytest-tmp` / 无 `_snapshot.json` / 无 `111.txt` / 无 `1.55.3`。
  被跟踪 **206 → 175 个**、**21.10 → 3.40 MB**。
- `backend/app/data/st/rag.db` 仍在磁盘（2240512 字节）—— 脱管 ≠ 删除。
- 六个文档全部保留 **CRLF**（脚本逐文件断言 `CRLF == LF`）。
- 过时标记复扫：`student/123456`、`teacher/123456`、`config.mode`、`12 名学生`、`约 130 个端点`、
  `408`、`全部 todo`、`仅 2 条` 在文档层已无残留（历史快照类文档中的 `C2026DS001` 有意保留）。
- 本轮**未改任何代码**，`run_seed` / `bootstrap` 的 `DEMO_SEED=1` 门控是既有实现，仅据实写进文档。
- ⚠️ 本轮**未执行 `git commit`**（按约定由用户在交互终端自行提交）。

### 未做（保持登记）

- **C 档历史瘦身**：`.git` 内 35.84 MiB 大对象需 `git filter-repo` + force push，未做。
- **同类过时口径 3 处**（本轮确认范围外）：
  `docs/数据模型与字段说明.md:104`（"`learning_paths` 共 408 行，全部为 `todo`"）、
  `docs/数据模型与字段说明.md:277`（"答题记录仅 2 条、学习路径全为 `todo`"）、
  `docs/接口文档.md:85`（`/course/{courseId}` 的"默认 `C2026DS001`、返回统计是种子演示常数" ——
  实测该端点已无默认值，`chapters` / `knowledgePoints` / `resources` / `questions` 均由 `func.count` 实时聚合）。

## 三十八、资源页码禁止越界：PDF「跳转页码」与 PPT「已读到第 N 页」钳制（2026-09-30）

用户截图实测：PDF「共 17 页」的跳转页码能输 **946**、PPT「页数 4 页」的「已读到第」能填 **208** ——
输入框虽有 `min/max` 属性，但 `type=number` 的属性**不拦手输**，跳转/保存逻辑也没有钳制，
越界值直接入库（配合「进度不回退」逻辑会**永久保留**）。

### 处置

**前端 `assets/js/student/views/resource.js`（`_openDoc` 两个分支共用一个钳制函数）**
- `_openDoc` 顶部新增 `clampPage(v, min)`：总页数已知（`res.pages > 0`）时钳到 `[min, 总页数]`；
  页数未知时只约束下限（PDF ≥1 / PPT ≥0），不再受原模板里 `max=999` 假上限影响。
- **PDF 分支**：① 弹窗打开时的初始页码与 `#page=` 定位也走钳制（历史越界的 `savedPage` 被拉回）；
  ② 「跳转」点击：钳制 → 把输入框值改回 → `Toast.warn('页码超出范围', '共 N 页，已调整为 p')` → 跳转并保存；
  ③ 关闭/点遮罩的兜底保存同样钳制。
- **PPT/doc 分支**：① 初始值钳制；② 「保存进度」点击：钳制 + 输入框回写 + Toast 提示。

**后端 `backend/app/routers/student.py::save_resource_progress`（前端之外的兜底，直接调接口也无法越界）**
- `r.type in ("ppt","doc") and r.pages` 时：`position = min(position, r.pages)`（`progress` 原有 `0~100` 钳制不变）。
- **历史越界值收敛**：落库前的 `prev_position` 同步钳到总页数 —— 修复「进度不回退」会把
  越界旧值（如 946）**永久保留**的问题；合法区间内「只增不减」语义不变。
- 视频分支不受影响（`position` 是秒数，不按页码钳制）。

### 验证（8010 + 库副本；真实库只读）

- **接口层（以库中值断言）**：R001（doc,17 页）传 946 → 库 `(17,100)`；R002（ppt,43 页）传 208 → 库 `(43,100)`；
  R001 传合法值 5 → 库仍 17（**不回退**）；R003（ppt,4 页）预置脏行 208 → 传 2 → 库收敛 **4**；
  R006（doc,26 页）预置 500 → 收敛 **26**；R004（video）传秒 100 → 100（不误伤视频）；
  GET progress 返回钳后值（前端续看读到的就是它）。**10/10 通过**。
- **UI 层（无头 Chrome，真实点击）**：PDF 弹窗输 946 → 点「跳转」→ 输入框**钳回 17**、toast 出现、
  抓到的请求体 `{"progress":100,"position":17}`（946 没有发出去）；PPT 弹窗输 208 → 保存 → **钳回 4**、
  请求体 `position:4`；**页面未捕获异常：无**。截图 `verify_20260930_pclamp/`。
- `regression_test.py` → **ALL PASS total=52 passed=52**；`node --check` / `py_compile` 均通过。
- ⚠️ 本轮改了后端 `student.py`，**需重启 8000 端口实例**后接口兜底才生效（前端钳制刷新页面即生效）。
- 清单 P30（自报进度模型）**保持登记**：本条只做"输入不越界"，未改"页码自报、进度只增不减"的模型本身。
