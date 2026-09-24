# 课程智能体系统（Course Agent）

> 一套面向《数据结构》课程的「课堂教与学」智能辅助系统：学生端提供个性化学习路径、学情看板、练习与 AI 答疑；教师端提供班级学情分析、知识点掌握归因、题库与干预建议。
>
> **当前形态**：FastAPI 后端 + 原生 HTML/JS 前端。
>
> **实现状态**：所有非 AI 业务接口**真实可用**（数据从关系表实时计算）；**AI 答疑与 AI 出题已接入真实 LLM**（DeepSeek + RAG 检索增强，当前为 live 模式）——**不再是占位实现**。
>
> ⚠️ 各模块「真实实现 / 空转 / 占位」的逐项清单，请以 **`docs/项目真实交互梳理.md`** 为准（该文档记录了当前最真实的项目状态）。

---

## 1. 技术选型

### 后端

| 能力 | 技术 | 版本 | 说明 |
| --- | --- | --- | --- |
| Web 框架 | FastAPI | 0.115.0 | 异步、自带 OpenAPI 文档（`/docs`） |
| 服务器 | uvicorn | 0.30.6 | ASGI 服务 |
| ORM | SQLAlchemy | 2.0.35 | 2.0 风格（`Mapped` / `mapped_column`） |
| 数据库 | SQLite（默认） | — | 零配置、随项目启动；可改 PostgreSQL（见 `config.py`） |
| 校验 / 序列化 | Pydantic / pydantic-settings | 2.9.2 / 2.5.2 | 请求体校验 + 配置读取 |
| 鉴权 | python-jose + passlib[bcrypt] | 3.3.0 / 1.7.4 | JWT（HS256）+ 密码哈希 |
| 流式输出 | sse-starlette | 2.2.1 | AI 答疑 / 出题的 SSE 流式接口 |
| LLM / RAG | openai（兼容客户端）+ PyYAML + pypdf | 见 `requirements.txt` | 调用 DeepSeek；本地 RAG 向量库 |

> **为什么是 FastAPI + 原生前端？** 项目处于原型 / 对接阶段，目标是让前端用最少成本切换 mock→真实接口，并让后端聚焦在「数据真实可算」。原生 HTML/JS 无构建步骤，任何人打开即可联调；FastAPI 自带文档与异步能力，便于 LLM 流式问答。

### 前端

- **原生 HTML / CSS / JS**，无框架、无打包构建；
- **ECharts** 负责图表（学情看板、掌握率、归因图）；
- **Hash 路由**切换视图（`student.html` / `teacher.html` 内部多视图）；
- 统一数据层 `assets/js/api.js`：所有取数走 `API.*`，`config.mode = 'http'` **直连真实后端**，页面无需改动。

> **Mock 已下线**：早期的 `assets/js/mock/data.js` 与 `mode:'mock'` 已移除，前端只消费后端真实接口。注意 `api.js` 内部仍留有 mock 分支的**死代码**（`window.MOCK` 已不存在），切勿切回 `mock`。

---

## 2. 目录结构与文件说明

```
course-agent/
├── index.html         # 登录页（入口）
├── forgot.html        # 找回密码
├── home.html          # 产品介绍（可选）
├── student.html       # 学生端（7 个视图）
├── teacher.html       # 教师端（7 个视图）
├── start.bat          # 一键启动（Windows）
├── stop.bat           # 停止后端进程
├── assets/
│   ├── css/
│   │   ├── base.css    # 设计令牌、重置、通用原子类
│   │   └── app.css     # 业务组件样式
│   ├── js/
│   │   ├── api.js       # 统一数据层（API.*，http 模式）+ SSE 流式解析
│   │   ├── auth.js      # 登录态、JWT 存取、路由守卫
│   │   ├── charts.js    # ECharts 封装
│   │   ├── common.js    # 通用工具（toast、DOM、格式化、Router）
│   │   ├── st/          # 智能体前端组件（图题 SVG 渲染、章节映射）
│   │   ├── student/     # 学生端：app.js + start.js + views/(7)
│   │   ├── teacher/     # 教师端：app.js + start.js + views/(7)
│   │   └── vendor/      # 第三方库（echarts 等）
│   └── resources/      # 课程资源：{course_id}/{res_id}/文件名 + covers/（约 1.6GB，不入 Git，统一由教师上传添加）
├── backend/
│   ├── requirements.txt
│   ├── regression_test.py   # 后端接口回归脚本
│   ├── import_st_bank.py    # 题库导入（after_class.json → questions）
│   ├── run_st_ingest.py     # 离线构建 RAG 向量库（从 resources 表读取清单）
│   ├── migrate_resource_paths.py  # 一次性迁移：旧资源目录 → 统一路径规范（幂等）
│   ├── kp_section_mapping.json  # 王道章节 → 知识点 KP 映射（人工维护）
│   └── app/
│       ├── main.py          # FastAPI 入口：中间件、路由注册、/health、挂载前端静态
│       ├── config.py        # 配置（CORS、JWT、数据库、LLM/Embedding）
│       ├── database.py      # 引擎 / Session / init_db（含手写 _migrate 列迁移）
│       ├── models/          # ORM 模型（23 张表）
│       ├── schemas/         # Pydantic 模型（含 common.py 统一信封）
│       ├── routers/         # 路由层：auth, course, graph, student, teacher,
│       │                   #   practice, intervention, ai, st_agent
│       │                   #   （teacher/intervention 各自额外导出子路由）
│       ├── middleware/      # JWT 鉴权中间件
│       ├── services/        # 业务服务层：bootstrap / alert_detector /
│       │                   #   learning_path / resource_registry / scoring
│       ├── agent_st/        # ★ RAG + LLM 智能体运行时（独立子包）
│       │   ├── agent/       #   运行时、工具、flows/personas/skills
│       │   └── rag/         #   检索、切片、embedding、解析器
│       ├── seed/            # 种子数据（首次启动建表并填充演示数据）
│       ├── data/            # course_agent.db / st/rag.db / st_bank/（不入 Git）
│       ├── media_utils.py   # 视频/素材工具
│       └── utils.py         # 通用工具
└── docs/                # 详细文档（见 §8）
```

**路由与模块归属**

- `routers/teacher.py` 同时导出 `teacher_router`、`analysis_router`、`question_router`；
- `routers/intervention.py` 同时导出 `intervention_router`、`report_router`；
- `routers/ai.py` 承载 **AI 答疑**（真实 RAG Agent，`/ai/chat`、`/ai/chat/stream`）；
- `routers/st_agent.py` 承载**智能体状态与知识库维护**（`/agent/status`、`/agent/ingest/*`）；
- `routers/teacher.py` 的 `question_router` 承载 **AI 出题**（`/question/gen` SSE）与题库管理。

---

## 3. 快速开始

### 环境要求

- **Python 3.11**（`start.bat` 自动探测：依次尝试 `python3.11`、`py -3.11`、PATH 中的 `python`（需为 3.11.x），无需手动配置路径）
- 数据库：默认 SQLite，无需额外安装
- LLM（可选）：在 `backend/app/.env` 配置 `LLM_API_KEY` / `EMBEDDING_API_KEY`；**未配置时 AI 答疑与出题自动降级为演示模式**（仍真实检索，但不生成）

### 一键启动（Windows）

```bat
start.bat
```

脚本会：检查 Python → 清占用端口 → 安装依赖（仅首次）→ 启动后端（127.0.0.1:8000）→ 等待 `/health` → 自动打开浏览器。停止用 `stop.bat`。

### 手动启动

```bash
cd backend
pip install -r requirements.txt
pip install bcrypt==4.0.1            # passlib 兼容需要，建议锁版本
cp app/.env.example app/.env         # 按需填写 LLM / Embedding 密钥
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 验证

- 前端入口：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health> → `{"status":"ok",...}`
- 智能体状态：<http://127.0.0.1:8000/api/v1/agent/status> → 看 `mode` 是 `live` 还是 `demo`

### 演示账号

| 用户名 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `student` | `123456` | 学生 | 陈思远 · 计算机 2301 班 |
| `teacher` | `123456` | 教师 | 李文博 · 可看 CL2301 / CL2302 / 软件 2301 |

> 后端种子写入 12 名学生 + 1 名教师（见 `backend/app/seed/mock_data.py` 的 `DEFAULT_ACCOUNTS`）。首次启动会执行 `run_seed()` 建表并填充演示数据，随后 `bootstrap()` 把演示库补全为真实库（9 章图谱 + 真实资源 + 228 道正式题）；如需重置，删除 `backend/app/data/course_agent.db` 后重启即可。

---

## 4. 核心架构约定（务必遵守）

1. **统一响应信封**：所有接口返回 `{ code, message, data, traceId }`，成功 `code=0`，前端只读 `data`；异常由全局处理器包成 `code≠0`（HTTP 仍 200）。
2. **接口前缀**：业务接口统一挂在 `/api/v1` 下。
3. **鉴权**：`Authorization: Bearer <JWT>`；登录 `/api/v1/auth/login`，当前用户 `/api/v1/auth/profile`。
4. **http 直连**：前端 `assets/js/api.js` 的 `config.mode` 已固定为 `'http'`，页面零改动消费真实后端；**请勿改回 `mock`**（mock 数据文件已移除，改回会全线崩溃）。
5. **不受管接口必须走 `API.*`**：直接 `fetch` 会绕过统一注入的 JWT（`question.js:558` 已因此产生 401 bug）。
6. **AI 能力已落地**：答疑在 `routers/ai.py`，出题在 `routers/teacher.py` 的 `question_router`，底层统一调用 `app/agent_st/` 的 `run_turn()`（live / demo 双模式）；事件契约见 `docs/智能体工作流说明.md`。
7. **无框架前端**：视图切换用 Hash 路由；第三方库放 `assets/js/vendor/`；**不要在原型阶段引入构建工具**。

---

## 5. 开发规范

### 命名

- 文件/变量：`snake_case`；前端模块：`assets/js/<role>/*.js`；路由：`<domain>.py`。
- 接口路径：`/api/v1/<domain>/<action>`，动词尽量贴合 REST（或直接用动作名）。
- 数据库表名/`model` 类：`PascalCase`，表名默认小写复数由 SQLAlchemy 约定。

### 接口

- 新增/修改接口 **必须同步更新 `docs/接口文档.md` 的契约**。
- 响应必须套用 `schemas/common.py` 的 `ok()/fail()`，不得裸返回 dict。
- 复杂计算（掌握率、归因、干预）必须基于关系表**真实计算**，不得退回硬编码 mock。

### Git / 协作

- 主干保护：禁止直接 push `main`，一律走 feature 分支 + PR Review。
- Commit 语义化：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`。
- 依赖变更：改 `backend/requirements.txt` 并自测 `pip install -r requirements.txt` 通过。
- 详细协作流程、文件级所有权、红线与常见坑 → 见 `docs/团队协作开发手册.md`。

### 红线（务必）

- ⚠️ **JWT_SECRET 必须团队一致**：通过环境变量或 `.env` 固定强随机密钥；否则一人登录、他人无法验签，且重启后旧令牌失效（`main.py` 启动时会告警）。
- 不要把 `backend/app/data/*.db`、`.env`、密钥提交进仓库（见 `.gitignore`）。
- 不得为「前端能跑」而在后端返回假数据掩盖计算缺失。

---

## 6. 模块现状一览

> 详细逐端点判定见 `docs/项目真实交互梳理.md`。这里只给"接手必须知道"的结论。

| 模块 | 状态 |
| --- | --- |
| 鉴权、图谱、题库、资源、练习判分、干预、报告 | ✅ 真实实现 |
| AI 答疑、AI 出题 | ✅ 真实 LLM（live 模式，需 `.env` 配 Key） |
| 掌握率 / 雷达 / 预警 / 归因 | ⚠️ **算法真实，但数据为空**（`learning_paths` 全 `todo`、`answer_records` 仅 2 条）→ 显示为 0，**不是 bug** |
| 素材上传解析 `/question/materials`、靶向补练包 `/question/packs`、答疑反馈 `/ai/feedback`、猜你想问 `/ai/suggest-questions` | 🚧 占位 |
| 教师端「文件方式批量导入题目」 | 🔴 **有功能 bug**：前端 token 取错导致 401（见 `项目真实交互梳理.md` §六） |

---

## 7. 数据库与 RAG 同步

> **正式题库存在 SQLite 数据库中，该文件不随 git 传播**。git 上只走"原料与配方"（题库源 JSON、知识点映射、导入脚本）+ **基准快照**。本地数据库停留在旧状态时，题库会与最新代码对不上——按下述步骤恢复。

### 7.1 哪些随 git 走

| 文件 | 说明 |
| --- | --- |
| `backend/app/data/course_agent.db.bak.baseline` | **基准数据库快照**（2026-09-08：228 题细粒度 KP + AI 生成样例题） |
| `backend/app/data/st/st_bank/after_class.json` | 课后题库源（导入原料，228 题） |
| `backend/kp_section_mapping.json` | 王道小节 → 知识点 KP 映射（人工维护） |
| `backend/app/data/st/rag.db` | RAG 向量库（1480 切片，重建命令见下） |
| `backend/import_st_bank.py` / `run_st_ingest.py` | 题库导入 / RAG 构建脚本 |

**不入仓库**：`course_agent.db` 本体（本地日常数据）、`st/drafts/`（教师个人出题草稿）、历史 db 备份。

### 7.2 同事首次同步 / 题库对不上时

```bash
git pull
cd backend
# 推荐：用基准快照恢复，与团队开发状态完全一致
python -c "import shutil; shutil.copy('app/data/course_agent.db.bak.baseline', 'app/data/course_agent.db')"
# 或：保留本地练习/答疑数据，仅重建题库归属（幂等，不会删除历史残留的占位种子题）
python import_st_bank.py
```

恢复后的基准题库：**228 道 KHD 课后题，覆盖 22 个细粒度知识点**，另有 AI 生成样例题 AI001。

### 7.3 RAG 向量库

`rag.db` 随 git 走，正常 `git pull` 即可拿到最新版。仅当课程资源（PDF/PPT/题库）发生变更时才需要重建：

```bash
python run_st_ingest.py     # 重跑后 git 会出现 rag.db 的变更，提交即可
```

> ⚠️ 注意：rag.db 的向量维数取决于**建库时**使用的 embedding 模型。若建库用了远程 bge-m3（1024 维）而运行时未配 Key（退化为 256 维本地哈希），**检索会静默退化为纯关键词匹配**。详见 `项目真实交互梳理.md` §2.3。

### 7.4 更新基准快照（阶段性变更需要同步全队时）

```bash
cd backend
python import_st_bank.py    # 先确认题库状态可由脚本复现
cp app/data/course_agent.db app/data/course_agent.db.bak.baseline
git add app/data/course_agent.db.bak.baseline
git commit -m "更新基准数据库：注明本次变更内容"
```

---

## 8. 相关文档

| 文档 | 内容 |
| --- | --- |
| **`docs/项目真实交互梳理.md`** | ★ **各模块真实实现 / 空转 / 占位逐项清单 + 现存 bug 与隐患**（接手第一份该读的） |
| `docs/README.md` | 文档导航 |
| `docs/接口文档.md` | 全部 API 契约（Path / 请求 / 响应 / 占位标注） |
| `docs/数据模型与字段说明.md` | 各接口 `data` 结构与前端强依赖字段路径 |
| `docs/前端架构与运行.md` | 前端技术栈、目录、模块职责、本地运行 |
| `docs/鉴权与会话方案.md` | 登录 / JWT / 路由守卫 / 找回密码 |
| `docs/智能体工作流说明.md` | 智能答疑与智能出题的工作流、工具链、SSE 事件 |
| `docs/页面与功能清单.md` | 每个页面需要哪些数据（页面 ↔ 接口映射） |
| `docs/团队协作开发手册.md` | 数据口径、数据模型、协作流程、红线与技术债、数据库同步 |
| `相较v1.0的改动.md` | 相对 v1.0 的全部改动记录（**强制维护**） |

---

*最后更新：2026-09-11 · 已按真实实现状态校对（AI 已接入真实 LLM、删除过时分工与占位表述）。*
