# 数据模型与接口 data 字段说明

> 适用对象：后端开发者（实现接口返回结构）、前端维护者。
> 核心原则：**前端按本文档列出的字段结构渲染；后端接口返回的 `data` 必须与之一致，前端才能零改动消费。**
> 早期 `assets/js/mock/data.js` 已下线，本文档现描述**真实后端返回的 `data` 结构**（字段名、类型、含义），而非某份假数据。

---

## 1. 数据来源说明

- 所有接口的 `data` 由 **`backend/app/routers/*` 实时计算并组装**而来，数据来自关系表（`users` / `learning_paths` / `answer_records` / `questions` / `resources` / `graph_*` / `alerts` / `chat_*` 等）。
- 字段名统一 **camelCase**（与前端一致）；数据库列名是 snake_case（`kp_id` / `avg_mastery`），由后端在组装时转换。
- 列表类接口统一返回 `{ total, list: [...] }`（个别接口如 `/teacher/classes` 返回裸数组，详见 §3 强依赖路径中的标注）。

### 1.1 接口 → data 结构 对照

| 接口 | 关键 data 结构 |
| --- | --- |
| `GET /course/{courseId}` | `course`（课程基本信息） |
| `GET /auth/profile` | `user`（当前用户，含 `classes`） |
| `GET /student/dashboard` | `studentDashboard`（学习驾驶舱聚合） |
| `GET /graph?type=knowledge\|problem\|goal` | `graph`（三类图谱之一） |
| `GET /graph/kp/{kpId}` | `kpDetail`（知识点详情） |
| `GET /graph/path` | `learningPath`（推荐学习路径数组） |
| `GET /student/resources` | `{ total, list }`（资源中心列表） |
| `GET /student/mastery/matrix` | `masteryMatrix`（按章分组掌握矩阵） |
| `GET /student/ability/radar` | `abilityRadar`（能力雷达） |
| `GET /student/growth` | `growthTrack`（成长轨迹） |
| `GET /student/compare` | `classCompare`（班级对比） |
| `GET /student/alerts` | `{ total, list }`（我的预警） |
| `GET /student/messages` | `{ total, list }`（私信/通知） |
| `GET /practice/modes`、`/sessions/...`、`/answers`、`/wrong-book` | 练习与错题相关结构 |
| `GET /teacher/dashboard` | `teacherDashboard`（教学驾驶舱） |
| `GET /teacher/heatmap` | `heatmap`（掌握热力图） |
| `GET /teacher/students` | `{ total, list }`（学生列表） |
| `GET /teacher/students/{userId}/profile` | `studentProfile`（个体学情） |
| `GET /analysis/errors` | `errorAnalysis`（错题与归因） |
| `GET /question/gen/config`、`/gen`、`/bank` | 出题配置/生成/题库结构 |
| `GET /intervention/list`、`/effect`、`/templates` | 干预与策略结构 |
| `GET /report/list`、`/generate`、`/{id}` | 报告结构 |
| `POST /ai/chat` | `{ messageId, sessionId, content, citations[], method, outOfScope, sourceCount }` |

---

## 2. 核心实体字段定义

> 以下为前端强依赖的字段。完整字段以后端实际返回为准；后端可增字段，**不可缺下列字段**（或提供等价兜底）。

### 2.1 User（用户）
见 `鉴权与会话方案.md` §5。登录 / profile 返回。

### 2.2 Course（课程）
```js
{ courseId, name, code, term, teacher, credit,
  chapters, knowledgePoints, resources, questions }
```

### 2.3 Graph / GraphNode / GraphLink（三大图谱）
```js
Graph = {
  graphType: 'knowledge'|'problem'|'goal',
  categories: [ { name, color } ],            // knowledge 固定 5 项：
                                              // 0 已掌握 #22c55e / 1 学习中 #6366f1 / 2 待加强 #f59e0b
                                              // 3 未开始 #64748b / 4 薄弱预警 #ef4444
  nodes: [ {
    id, name,
    chapter?,                                 // 章节（知识图谱有）
    category,                                 // categories 下标（= 学生对该知识点的真实学习状态）
    mastery,                                  // 0~100 掌握率（由 answer_records + resource_progress 实时计算）
    difficulty,                               // 1~5 难度
    isKey,                                    // 是否重难点
    hours                                     // 建议学时
  } ],
  links: [ { source, target, relation } ]    // relation: pre|advance|parallel|split|map|error|support
}
```

> **`nodes[].category`（知识图谱）由后端按真实学习记录计算，不再取 `graph_nodes.category` 的库值：**
>
> | category | 状态 | 判定（`_knowledge_state_category`） |
> | --- | --- | --- |
> | 0 | 已掌握 | 资源学习完成率 = 100%，或答题正确率 ≥ 80% |
> | 1 | 学习中 | 有答题且正确率 50~79%，或有资源进度但未达标 |
> | 2 | 待加强 | 有答题且正确率 40~49% |
> | 3 | 未开始 | 无任何答题与资源记录（未登录查看图谱时也统一按此展示） |
> | 4 | 薄弱预警 | 有答题且正确率 < 40%（与驾驶舱 weakPoints 的 danger 线一致） |
>
> problem / goal 图谱的 `category` 仍来自教师编排（`graph_nodes.category`）。

### 2.4 KpDetail（知识点详情）
```js
{ name, summary, completionRate, masteryRate, classAvgMastery,
  studyMinutes,                                          // 个人学习时长(分)，见口径说明
  courseAvgCompletion, courseAvgMastery, courseAvgMinutes,  // 课程平均三项
  courseStudentCount, courseStudiedCount,                // 平均分母 / 有记录人数
  resources: [ { type, title, duration?, pages?, progress } ],
  relatedProblems: [ { qId, title, errorRate, mastery } ] }
```

> - **`kp_details.summary` = 「知识点介绍」**（2026-09-18 启用）：由教师在「课程目录与资源 → 新增知识点 /
>   知识点详情」中录入，落库后学生端与教师端图谱详情面板均读取展示（`POST/PUT /teacher/structure/kps` 的
>   `summary` 字段）。此前该列一直为空、前端显示的「暂无解释文本」占位曾是写死文案，现已改为空态样式。
> - 学情口径集中在 `backend/app/services/kp_stats.py`：掌握度 = max(答题正确率[按题去重], 资源完成率)；
>   完成度取 `learning_paths`；**学习时长** = Σ`resource_progress.position`（video）+ Σ`answer_records.duration_seconds`。
>   课程平均的分母 = `user_courses` 中该课程全部学生（未学习者按 0 计入，同时返回 `courseStudiedCount`）。
> - ⚠️ 历史数据里 `kp_details` 行数可能少于知识点数；缺失时后端从 `GraphNode` 兜底（此时 `summary` 为空），
>   `PUT /teacher/structure/kps/{kpId}` 会自动补建 KpDetail 行，保证「知识点介绍」始终有落库位置。

### 2.5 LearningPath（推荐路径）
```js
[ { step, name, status:'done|doing|todo|warn', hours, resCount, mastery, progress, locked } ]
```
> - `resCount` 由 `GET /graph/path` **以 `resources` 表实时统计后返回**（主 `kp_id` + `kp_ids`
>   多标签都计入，同一资源对同一知识点只算一次），并顺手回写 `learning_paths.res_count`。
>   表里的 `res_count` 只是派生缓存，别再当作事实来源 —— 历史上它只在教师端
>   上传/删除资源时同步，学生端会一直显示建路径时的旧值（新建行甚至是 0）。
> - 前端章节行显示的「N 个资源」按**去重后的资源条数**统计（同一资源挂多个知识点只算一次），
>   所以章节合计 ≤ 该章各知识点 `resCount` 之和。
> - `mastery` / `progress` / `status` 在每次 `GET /graph/path` 时按真实答题与资源进度刷新。

### 2.6 Dashboard（驾驶舱）
学生 `studentDashboard`：
```js
{ overview: { courseProgress, currentNode:{kpId,name}, streakDays, streakHistory:[0~4...],
              currentStreak, maxStreak, totalDays,
              todayStudyMinutes, todayStudySeconds, todayPracticeSeconds, todayResourceSeconds,
              status:'ok|warn|danger' },
  coreMetrics: { completionRate, masteryRate, goalAchieveRate, updatedAt },
  todos: [ { id, type, level, title, desc, action, target, kpId?, kpName?, sessionId?, mode? } ],
  weakPoints: [ { kpId, name, masteryRate, chapter, errorCount, trend, level } ],
  suggestedQuestions: [ string ],
  recentActivities: [ { id, type:'practice|resource', title, meta, time, level } ] }
```
> `todayStudySeconds`（当天练习用时 + 当天视频观看秒数，本地日历日）用于驾驶舱
> 「今日累计学习时长」徽标，并由 `GET /student/study-duration` 轮询刷新；
> `todos[].target` 取值必须是前端路由名（`resource` / `practice` / `graph` / `alerts`），
> 否则 `Router.go()` 会静默失败导致按钮点了没反应。

教师 `teacherDashboard`：
```js
{ classOverview:{...}, liveFeed:[...], todos:[...], kpRanking:[...] }
```

### 2.6.1 ResourceProgress（资源学习进度 / 视频记录点）

```js
resource_progress = { user_id, res_id, progress:0~100, position, updated_at }
// 视频 position = 秒（下次进入的续播记录点）；文档/PPT position = 页码
```
> - 写入：`POST /student/resources/{resId}/progress`，`progress`/`position` **取最大值不回退**；
>   视频另带 `watchedDelta`（本次真实播放秒数）用于累计当日观看时长。
> - ⚠️ 该表**没有 (user_id, res_id) 唯一约束**，历史并发上报会留下重复行
>   （同一资源两行：一行 0/0、一行真实进度）。所以读写必须走 `services/resource_progress.py`：
>   读 `progress_map()` 取最优行，写 `consolidate()` 合并成一行。
>   **要彻底根治需补唯一约束（表结构变更，需先确认）。**
> - 前端卡片/路径/掌握率、后端驾驶舱动态与 `resource-stats` 都已改用统一口径，重复行不会再让进度显示成 0%。

### 2.7 StudentOverview / Heatmap
```js
Heatmap = {
  kpAxis: [ { kpId, name } ],
  studentAxis: [ { userId, name } ],
  data: [ [ kpIndex, studentIndex, masteryRate ] ],   // 三元组
  weakest: [ { kpId, name, avgMastery } ] }
```

### 2.8 Alert（预警）
```js
{ alertId, level:'red|yellow|green', student, kp, type,
  trigger, trendData:[...], status:'open|reviewed|ignored' }
```

### 2.9 StudentProfile（个体学情）
```js
{ user:{...}, portrait:{...}, schedule:[...], activity:[...],
  answerDetail:[...], freqWrong:[...] }
```

### 2.10 Question（习题 / 生成题）
```js
GeneratedQuestion = {
  qId, type, difficulty, status:'pending|approved|published|archived',
  stem, options:[...], analysis,
  kpPath:[...], preKp:[...], postKp:[...],          // 知识点定位树 / 前后置
  isKey, sourceRef:{ fileId, locator }, estimatedCorrectRate }
```

### 2.11 Intervention（干预）
```js
{ ivId, status:'pending|running|done', level, scope:'common|individual',
  title, target, reason, steps:[...], expectEffect, execution? }
```

### 2.12 ReportSection（报告章节）
```js
{ title, paragraphs:[...], bullets:[...] }
```
报告整体：`{ reportId, status, detail:{ title, sections:[ ReportSection ] } }`

---

## 3. 前端强依赖的关键字段路径（后端务必提供）

下列路径在前端渲染中被直接读取，缺失会导致页面异常：

| 页面 / 视图 | 必填字段路径 |
| --- | --- |
| 学生驾驶舱 | `overview.coreMetrics.*`、`todos[]`、`weakPoints[]`、`streakHistory` |
| 三图谱 | `categories[]`、`nodes[].{id,name,mastery,category,isKey}`、`links[].{source,target,relation}` |
| 资源中心 | `list[].{resId,title,type,kp,views,progress,duration?\|pages?\|count?}` |
| AI 答疑 | `content`（HTML 串）、`citations[]`、`outOfScope`、`messageId` |
| 智能练习 | `questions[].{qId,type,stem,options,answer,analysis}`、`practiceReport` |
| 我的学情 | `masteryMatrix`、`abilityRadar`、`growthTrack`、`classCompare` |
| 预警中心 | `studentAlerts[].{alertId,level,student,kp,type,status}` |
| 教学驾驶舱 | `teacherDashboard.classOverview`、`liveFeed`、`todos`、`kpRanking` |
| 学情监测看板 | `heatmap.{kpAxis,studentAxis,data,weakeSt}`、`students[]`、`studentProfile` |
| 归因分析 | `errorAnalysis.{errorTypes?,highFreq,weakChain,causes}` |
| AI 出题 | `genConfig`、`generatedQuestions[]`、`questionBank[]` |
| 教学干预 | `interventions[]`、`interventionEffect`、`strategyTemplates[]` |
| 学情报告 | `reportList[]`、`reportDetail.sections[]` |
| **教师班级下拉** | `GET /teacher/classes` 返回**裸数组** `[{classId,name}]`，不是 `{list:[...]}`（前端已兼容，新增接口请勿混用两种形态） |

---

## 4. 枚举与格式约定

| 类别 | 取值 |
| --- | --- |
| `role` | `student` / `teacher` |
| 图谱 `graphType` | `knowledge` / `problem` / `goal` |
| 图谱 `relation` | `pre`(前置) / `advance`(进阶) / `parallel`(并行) / `split`(拆分) / `map`(映射) / `error`(易错) / `support`(支撑) |
| 预警 `level` | `red`(紧急) / `yellow`(关注) / `green`(正常) |
| 预警 `status` | `open` / `reviewed` / `ignored` |
| 干预 `status` | `pending` / `running` / `done` |
| 干预 `scope` | `common`(共性) / `individual`(个性) |
| 习题 `status` | `pending` / `approved` / `published` / `archived` |
| 资源 `type` | `video` / `ppt` / `doc` / `quiz` |
| 时间 | ISO 或 `'YYYY-MM-DD HH:mm'` 字符串 |
| 百分比 | 数值 0~100（非字符串 `"62%"`） |
| 颜色 | CSS 颜色字符串（`#22c55e` 或 `linear-gradient(...)`） |

---

## 5. 联调提示

1. **字段对齐优先于接口数量**：后端不必一次实现全部 60+ 接口，但已实现的接口返回结构必须与本文档一致。
2. **数组字段**：列表类接口统一返回 `{ total, list:[...] }` 结构（见 `接口文档.md` 各列表接口）。
3. **AI 答疑**：`/ai/chat` 当前由 `routers/ai.py` 的关键词答案库（`_ANSWER_BANK`）兜底，命中返回带 `citations` 的答案，未命中返回 `outOfScope:true` 降级。真实环境由后端大模型 + 检索生成（见 `后端对接指南.md` §5）。
4. **AI 出题**：`/question/gen` 当前从现有题库随机抽题兜底，真实环境由后端调用大模型按素材/知识点生成，并回填 `kpPath/preKp/postKp/sourceRef` 等溯源字段。
5. **题库与学情样本**：当前种子题库仅十余道、答题记录很少，导致「知识掌握率」多为 0——这是已知数据缺口，补齐后方可验证掌握率/归因的准确性。
