# 最新 bug 修改 · 2026-10-26

## 课程删除口径重构 + 负责人状态修正（管理端课程管理）

### 一、需求与变更

| # | 需求 | 实现 |
|---|---|---|
| 1 | 删除取消二次确认（不再输入课程名），点删除直接删 | `assets/js/admin/views/courses.js` |
| 2 | 删除约束改为「课程内无任何成员即可删」，并清理全部关联数据；提示改为「有成员，请先移出」 | `services/course_admin.py`、`routers/admin_courses.py` |
| 3 | 课程无成员（学生与教师都为 0）时，负责人列显示「无负责人」，去掉黄色「待指派负责人」 | 后端清空 `owner_id` + 前端渲染 |
| 4 | 编辑界面同样显示「无负责人」，并支持指派/更换负责人；指派后教师端能看到该课 | `update_course` 已支持从无到有 + 前端下拉 |

### 二、后端改动（按铁律 2 已先给影响分析并经确认）

#### 1. `backend/app/services/course_admin.py`

**删除语义反转**（这是本次最核心的变更）：

- 旧：`content_blockers()` 统计资源/题目/图谱/学习记录等，**有教学内容就拒绝删除**，成员关系反而自动清掉。
- 新：`content_blockers()` 只统计**成员**，有成员即拒绝；成员为 0 则删除并**级联清理全部关联数据**。
  - 函数名与返回形状 `[(说明, 数量)]` 保留不变，因此智能助手 `preview_course_delete` 的契约无需改。
- 新增 `member_count(db, course_id)`。
- 新增 `_purge_course_rows(db, course_id)`：按「先子后父」顺序删除，因 `database.py:20` 已开启
  `PRAGMA foreign_keys = ON`，顺序错误会直接触发外键失败。清理范围：

  | 层级 | 表 | 删除依据 |
  |---|---|---|
  | 二级（先删） | `resource_progress` `resource_tags` `question_tags` `chat_messages` | 依赖一级表主键 |
  | 一级 | `answer_records` `learning_paths` `practice_sessions` `chat_sessions` `st_question_drafts` `alerts` `resources` `questions` `graph_links` `graph_nodes` `kp_details` `tags` | `course_id` |
  | JSON 隐性依赖 | `teacher_class_data`（`data_json.$.courseId`）、`reports`（`detail_json.$.meta.courseId`） | `json_extract` |

  - 二级表 ID 集合按 500 一批，避免 SQLite 绑定变量上限。
  - `tags` 额外做了**反向清理**：其它课程的资源/题目若挂本课程的标签，先摘链接，否则标签删不掉。

- 新增 `course_resource_urls()` / `purge_course_assets()`：删库**之后**清磁盘资源文件
  （`media_utils.url_to_path` + `cleanup_empty_dirs`）与向量库切片（`ChunkStore.delete_course`）。
  - 顺序刻意如此：DB 事务不碰文件系统，回滚时不会出现「数据还在、文件没了」。
  - 磁盘/向量库清理失败只留孤儿文件，不影响已提交的删除，错误记入返回值 `assets.errors`。

**负责人状态**（需求 3/4）：

- `_unbind()` 增加逻辑：退绑后若课程成员数归零，则把 `courses.owner_id` 与 `courses.teacher` 一并置空，
  返回新增 `ownerCleared` / `memberCount`。
- 这取代了旧的「软退绑」语义（保留 `owner_id`、显示「待指派负责人」）。
- `update_course()` 的负责人分支补充注释：`owner_id` 为空时即为「添加」，有值换人即为「更换」，
  两种情况都保证新负责人写入 `user_courses`，教师端才有权限看到该课。

#### 2. `backend/app/routers/admin_courses.py`

`admin_delete_course` 改为三段式：取资源 URL → 删库并 commit → 清磁盘与向量库，
响应 data 增加 `purged`（各表清理条数）与 `assets`（文件/切片清理结果）。

#### 3. `backend/app/agent_st/agent/tools/admin_delete.py`

- `preview_course_delete` 的 `deletable` / `basis` / `hint` 文案改为「按成员判定」。
- `delete_course` 工具同步执行「先取 URL → 删库 → 清资产」，返回值补 `purged` / `assets`。
- `ApprovalSpec.impact` 更新为完整级联范围（审批卡片上管理员看到的影响描述）。

#### 4. 技能提示词同步（`skills/admin_ops.md`、`skills/admin_courses.md`、`skills/admin_accounts.md`）

旧文案让模型在 `deletable=false` 时"把还剩多少题目/章节讲清楚，请先到教师端处理"——
这在新口径下是**错误引导**，已改为「说明还剩多少成员，请先移出成员」。

### 三、前端改动

- `assets/js/admin/views/courses.js`
  - `confirmDelete()`：删除「输入课程名称」输入框与比对校验，点击直接删除；
    提示文案改为按成员数判断（有成员=警告色并说明先移出；无成员=危险色并说明会清空哪些数据）。
  - 课程列表「负责人」列：`teacherCount` 为 0 时渲染「无负责人」，不再渲染黄色「待指派负责人」徽标。
  - 编辑弹窗：无负责人时下拉首项为「无负责人（请选择教师以指派）」，说明文案同步；
    校验放宽为「仅新建课程必须选负责人」，编辑时允许留空。
  - 成员弹窗：meta 文案、批量移出提示、`Toast` 文案全部改为「无负责人」口径。
- `assets/js/api.js`：`deleteCourse` / `unbindMember` 的注释更新为新语义。

### 四、存量数据订正

旧软退绑留下的「已无成员但 `owner_id` 仍有值」的课程，需要置空才算真正一致。
在库副本上检查后发现**真实库中存在 1 门**这样的课：

```
CZYNGCLC  近代史纲要  owner_id='T2026001' teacher='王建国'   （成员 0 人）
```

正是截图里的那门课。前端已按 `teacherCount` 兜底显示「无负责人」，
但库里的残留值还会让 `account_import.py:300` 的「该教师是某课 owner」校验误判。

订正方式（已用临时脚本 dry-run 核对，脚本按任务要求删除）：把这两门课的
`courses.owner_id` 与 `courses.teacher` 置空即可，只需一条 SQL：

```sql
UPDATE courses SET owner_id='', teacher=''
WHERE TRIM(IFNULL(owner_id,'')) <> ''
  AND course_id NOT IN (SELECT DISTINCT course_id FROM user_courses);
```

**这一步尚未对真实库执行**，需你确认后再跑（属数据订正，不改表结构）。

### 四之二、`data_check` 口径同步

`admin_ops.py` 的「课程创建者有效」检查原本会把「`owner_id` 为空」一律报为问题。
新口径下**无成员的课本来就该是无负责人状态**，否则每次自检都会误报。
已改为：无成员的课跳过；只有「有成员却无负责人」或「负责人不是成员」才报，
检查项名称同步改为「课程负责人有效」。已验证在库副本上返回 `ok: true`。

### 五、验证

新增 `dev_tools/check_course_delete.py`（库副本，绝不碰真库），全部通过：

```
需求1：删除弹窗无输入框、无课程名比对           [ok]
需求2：有成员时拒绝（提示「还有 1 名成员…请先移出」）[ok]
       无成员时删除成功                          [ok]
       级联清理 14 类数据，库内 0 残留            [ok]
需求3：退绑到 0 人 → ownerCleared=true，ownerId/teacher 均空   [ok]
需求4：指派负责人成功 → 自动成为成员 → 教师端 /course/my 能看到该课 [ok]
安全网：删不存在的课程被拒绝                     [ok]
```

清理明细实测（一次删课）：

```
{'资源学习进度': 1, '资源标签': 1, '题目标签': 1, '会话消息': 1, '答疑会话': 1,
 '出题草稿': 1, '预警': 1, '资源': 1, '题目': 1, '图谱连线': 1, '图谱节点': 1,
 '知识点详情': 1, '标签': 1, '教师端记录': 1}
```

同时通过的标准自检：

- `py_compile`：`course_admin.py` / `admin_courses.py` / `admin_delete.py` 均通过
- `node --check`：`courses.js` / `api.js` 通过
- `dev_tools/check_agent_roles.py`：全部通过（`delete_course` 仍是带审批的 admin-only 写工具）
- `dev_tools/check_route_roles.py`：全部通过

### 六、风险与回退

- **不可逆**：删除现在是真删全部数据。这是需求明确要求的语义（已确认）。
- 回退方式：`git revert` 对应提交即可；存量数据订正脚本本身是幂等的，且只动 `courses` 两列。
- 未改表结构、未加列、未写迁移脚本 —— 符合铁律 3。
- 已知未覆盖：浏览器端未做真人点击实测（本机无 Browser 插件运行文件），
  建议硬刷新（Ctrl+F5）后按「截图里那门近代史纲要」验一遍三点：
  ① 负责人列显示「无负责人」且无黄色徽标；② 点删除直接弹确认、无需输入课名；
  ③ 编辑弹窗负责人下拉显示「无负责人（请选择教师以指派）」。

### 七、临时脚本清理

按任务要求**已删除**本次验证用的两个脚本：

- `dev_tools/check_course_delete.py`（删除口径 + 级联清理验收，库副本）
- `dev_tools/fix_orphan_course_owner.py`（存量 owner_id 订正，dry-run 版）

如需把它们保留为长期回归用例，可以从本次提交历史里取回。
