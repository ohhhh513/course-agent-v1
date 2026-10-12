---
feature: gap-fill-edit-tags
status: delivered
updated: 2026-09-14
branch: (direct main worktree; user handles all git)
commits: (user-managed; no AI git ops)
---

# 补全：资源改标签 · 题目改图结构 · 多对多标签

## Report

**What was built** — 课程级多标签（tags + 资源/题多对多挂载）；`PUT /teacher/resources/{id}` 可改 KP/标题/标签；`PUT /question/{id}` 可改 figure/has_image/标签；列表与上传/导入打通；教师前端 TagPicker + 资源编辑 + 题目改图预览。

**Verification** — `python backend/test_tag_gapfill.py` → ALL PASS（标签 CRUD、题图更新、资源改挂载、学生可见 tags、删标签）。

**Journey log** — 范围先勾 A+B+C 后收敛为 A+C（无文件夹）；按项目约定未做 git/工作区，直接主目录改动；新表靠 create_all，无需旧库迁移脚本。

## [S1] Problem

审计确认的可编辑缺口：

1. 教师资源上传后无法改挂载知识点 / 标签（无 `PUT /teacher/resources/{id}`）；结构页提示“资源管理→编辑”实际无入口。
2. 题目 `PUT /question/{id}` 不接受 `figure_json` / `has_image`，建题后无法改图像结构。
3. 资源/题只有单 `kp_id`，缺少课程内可复用的自由多标签（如“重点”“期中”“实验”）。

产品语义：**章/知识点目录结构维持不变**；在 KP 之外增加课程级多标签；不引入自由文件夹树；不做推送级实时。

## [S2] Design

### 数据模型（`models/tag.py`）

- `tags`：`tag_id` PK（`T`+hex8）、`course_id`（index）、`name`；同课同名唯一。
- `resource_tags`：`res_id` + `tag_id` 联合唯一。
- `question_tags`：`q_id` + `tag_id` 联合唯一。

`database.py:init_db` 增加 import；`create_all` 建新表（既有库可增量建表，不删旧数据）。

### 标签服务约定

统一辅助（放 `services/tag_service.py` 或 teacher 内私有函数）：

- `list_tags(db, course_id)`
- `ensure_tags(db, course_id, names_or_ids)`：按名创建或返回已有
- `set_resource_tags(db, res_id, tag_ids)` / `set_question_tags(db, q_id, tag_ids)`：覆盖式写入
- `get_resource_tags(db, res_id)` / `get_question_tags(...)`：返回 `[{tagId,name}]`
- 删除标签：删链接后删 `tags` 行

仅当前课程内标签可挂载；跨课 tagId 拒绝（400）。

### API 契约（均要求 JWT + 成员校验）

| 方法 | 路径 | 请求 | 响应要点 |
| --- | --- | --- | --- |
| GET | `/api/v1/teacher/tags` | — | `{list:[{tagId,name}]}` |
| POST | `/api/v1/teacher/tags` | `{name}` | 建/复用；`{tagId,name}` |
| DELETE | `/api/v1/teacher/tags/{tagId}` | — | `{tagId,removed:true}` |
| PUT | `/api/v1/teacher/resources/{resId}` | `{kpId?,kp?,title?,tagIds?}` | `{resId,updated:true}`；改 KP 后 `sync_res_count` |
| PUT | `/api/v1/question/{qId}` | 现有字段 + `figureJson`/`has_image`/`tagIds` | 兼容 camel/snake：`figure_json` 与 `figureJson` 均可；写回 `has_image` |
| GET | `/api/v1/teacher/resources` | — | 每项增加 `tags:[{tagId,name}]` |
| GET | `/api/v1/question/bank` | — | 每项增加 `tags` |
| POST | `/api/v1/teacher/resources/upload` | Form 增加可选 `tagIds`（JSON 数组） | 创建后挂标签 |
| POST | `/api/v1/question/import` | 每题可选 `tagIds` 或 `tags:[name]` | 导入后挂标签 |

`GET /student/resources` 同步返回 `tags`（只读展示）。

### 前端（教师）

1. **资源管理**：卡片增加「编辑」；弹窗可改标题、章节→知识点、标签 chips（多选 + 输入新建）。
2. **上传弹窗**：增加标签多选/新建。
3. **题库编辑弹窗**：
   - 可改 `kp`、选项、答案、解析；
   - 若 `has_image`：展示当前 `figure_json` 的 `DsFigure` 预览；允许按建题同款表单编辑图结构后写回；
   - 标签 chips 多选/新建。
4. **新建题目**：提交时带 `tagIds`。
5. **api.js**：`teacher.tags/createTag/deleteTag/updateResource`；`question.update` 传完整 body 含 figure/tags。

### 错误行为

- 资源/题不存在 → 404
- 标签属其他课程 → 400
- 空 `name` → 400
- 删除标签成功不级联改题干/资源 KP

### 测试边界

- 新表 create_all 可建
- 标签 CRUD + 资源/题挂载覆盖式替换
- `PUT /question` 更新 `figure_json` 且 `has_image` 同步
- 无注册/无文件夹/无 WebSocket（Out of Scope）

## [S3] Out of Scope

- 自由资源文件夹目录树
- WebSocket / 推送级学情同步
- 学生端对资源/题的标签筛选（仅只读展示 tags）
- 旧库增量迁移脚本（按项目约定：改模型；新表 create_all）
- 占位接口清理（materials/packs 等）

## Tasks

- [x] T1: 新增 Tag/ResourceTagLink/QuestionTagLink 模型并接入 init_db — acceptance: 启动后 `tags`/`resource_tags`/`question_tags` 三表存在 (covers: S2)
- [x] T2: 标签服务 + `/teacher/tags` CRUD — acceptance: 建/列/删标签可用，跨课 400 (covers: S2; depends: T1)
- [x] T3: `PUT /teacher/resources/{id}` 改 KP/title/标签 — acceptance: 改后列表与库一致，路径资源计数同步 (covers: S2; depends: T2)
- [x] T4: `PUT /question/{id}` 支持 figure/has_image/tagIds；列表与 import 带 tags — acceptance: 改图后 bank 返回新 figure 与 tags (covers: S2; depends: T2)
- [x] T5: 上传资源可选 tagIds；学生资源列表返回 tags — acceptance: 上传后资源带标签，学生 GET 可见 (covers: S2; depends: T2)
- [x] T6: 教师前端：资源编辑/上传标签、题库改图+标签、新建题标签、api.js — acceptance: 浏览器可完成编辑闭环 (covers: S2; depends: T3, T4, T5)
- [x] T7: 回归脚本/手测清单写入《相较v1.0的改动.md》 — acceptance: 改动记录完整 (covers: S2; depends: T6)
