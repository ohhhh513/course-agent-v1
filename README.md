# 课程智能体系统（Course Agent）

> 一套面向《数据结构》课程的「课堂教与学」智能辅助系统：学生端提供个性化学习路径、学情看板、练习与 AI 答疑；教师端提供班级学情分析、知识点掌握归因、题库与干预建议。
>
> 当前形态：**FastAPI 后端 + 原生 HTML/JS 前端原型**。**所有非 AI 业务接口已真实可用**——数据从关系表实时计算；**AI 答疑 / AI 出题当前为关键词 / 题库兜底的占位实现**，已预留 LLM 接入位（`/ai/chat`、`/ai/chat/stream`、`/question/gen`）。

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
| 流式输出 | sse-starlette | 2.2.1 | AI 对话 SSE 流式接口预留 |

> **为什么是 FastAPI + 原生前端？** 项目处于原型 / 对接阶段，目标是让前端用最少成本切换 mock→真实接口，并让后端聚焦在「数据真实可算」。原生 HTML/JS 无构建步骤，任何人打开即可联调；FastAPI 自带文档与异步能力，便于后续接入 LLM 流式问答。

### 前端

- **原生 HTML / CSS / JS**，无框架、无打包构建；
- **ECharts** 负责图表（学情看板、掌握率、归因图）；
- **Hash 路由**切换视图（`student.html` / `teacher.html` 内部多视图）；
- 统一数据层 `assets/js/api.js`：所有取数走 `API.*`，当前默认 `config.mode = 'http'` **直连真实后端**，页面无需改动。

> **当前默认即 http 模式**：早期的 `mock` 模式与 `assets/js/mock/data.js` 已移除，前端直接消费后端真实接口（见 `docs/前端架构与运行.md`）。

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
│   │   ├── api.js       # 统一数据层（API.*，默认 http 模式）
│   │   ├── auth.js      # 登录态、JWT 存取、路由守卫
│   │   ├── charts.js    # ECharts 封装
│   │   ├── common.js    # 通用工具（toast、DOM、格式化、Router）
│   │   ├── student/      # 学生端：app.js + start.js + views/(7)
│   │   ├── teacher/      # 教师端：app.js + start.js + views/(7)
│   │   └── vendor/       # 第三方库（echarts 等）
│   └── resources/      # 课程视频/素材（体积较大，按需分发）
├── backend/
│   ├── requirements.txt
│   ├── regression_test.py   # 后端接口回归脚本
│   └── app/
│       ├── main.py          # FastAPI 入口：中间件、路由注册、/health、挂载前端静态
│       ├── config.py        # 配置（CORS、JWT_SECRET、FRONTEND_DIR、数据库）
│       ├── database.py      # 引擎 / Session / init_db
│       ├── models/          # ORM 模型：user, course, graph, question, practice,
│       │                   #   intervention, alert, checkin, ai
│       ├── schemas/         # Pydantic 模型（含 common.py 统一信封）
│       ├── routers/         # 路由层：auth, course, graph, student, teacher,
│       │                   #   practice, intervention, ai（teacher 同时导出
│       │                   #   analysis_router / question_router；intervention
│       │                   #   同时导出 report_router）
│       ├── middleware/      # JWT 鉴权中间件
│       ├── services/        # 业务服务层（AI/算法接入位，当前为空）
│       ├── seed/            # 种子数据（首次启动建表并填充）
│       ├── media_utils.py   # 视频/素材工具
│       └── utils.py         # 通用工具
└── docs/                # 详细文档（接口文档、前端文档导航等）
```

**路由与模块归属**

- `routers/teacher.py` 同时导出 `analysis_router`、`question_router`；
- `routers/intervention.py` 同时导出 `intervention_router`、`report_router`；
- `routers/ai.py` 为 AI 能力预留（当前返回关键词 / 题库兜底答案）。

---

## 3. 快速开始

### 环境要求

- **Python 3.12**（一键脚本默认读取 `C:\Users\CQYDDD\.local\bin\python3.12.exe`，其他机器请编辑 `start.bat` 顶部 `PYTHON` 变量）
- 数据库：默认 SQLite，无需额外安装

### 一键启动（Windows）

```bat
start.bat
```

脚本会：检查 Python → 清占用端口 → 安装依赖（仅首次）→ 启动后端（127.0.0.1:8000）→ 等待 `/health` → 自动打开浏览器。停止用 `stop.bat`。

> 若你的 Python 路径不同，编辑 `start.bat` 顶部的 `set "PYTHON=..."`。脚本首次安装依赖使用 `--break-system-packages`（适配无 venv 的环境）。

### 手动启动

```bash
cd backend
pip install -r requirements.txt
pip install bcrypt==4.0.1            # passlib 兼容需要，建议锁版本
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另开一个终端用任意静态服务器托管前端，或直接用后端挂载的根路径
```

### 验证

- 前端入口：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health> → `{"status":"ok",...}`

### 演示账号

| 用户名 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `student` | `123456` | 学生 | 陈思远 · 计算机 2301 班 |
| `teacher` | `123456` | 教师 | 李文博 · 可看 CL2301 / CL2302 / 软件 2301 |

> 后端种子写入 12 名学生 + 1 名教师（见 `backend/app/seed/mock_data.py` 的 `DEFAULT_ACCOUNTS`）。首次启动会执行 `run_seed()` 建表并填充演示数据；如需重置，删除 `backend/app/data/course_agent.db` 后重启即可。

---

## 4. 核心架构约定（务必遵守）

1. **统一响应信封**：所有接口返回 `{ code, message, data, traceId }`，成功 `code=0`，前端只读 `data`；异常由全局处理器包成 `code≠0`（HTTP 仍 200）。
2. **接口前缀**：业务接口统一挂在 `/api/v1` 下。
3. **鉴权**：`Authorization: Bearer <JWT>`；登录 `/api/v1/auth/login`，当前用户 `/api/v1/auth/profile`。
4. **http 直连**：前端 `assets/js/api.js` 的 `config.mode` 已固定为 `'http'`，页面零改动消费真实后端；**请勿改回 `mock`**（mock 数据文件已移除）。
5. **AI 预留位**：`/ai/chat`、`/ai/chat/stream`（SSE）、`/question/gen` 已在 `routers/ai.py` 预留，当前返回关键词 / 题库兜底答案，待接入 LLM + RAG。
6. **无框架前端**：视图切换用 Hash 路由；第三方库放 `assets/js/vendor/`；**不要在原型阶段引入构建工具**。

---

## 5. 开发规范

### 命名

- 文件/变量：`snake_case`；前端模块：`assets/js/<role>/*.js`；路由：`<domain>.py`。
- 接口路径：`/api/v1/<domain>/<action>`，动词尽量贴合 REST（或直接用动作名）。
- 数据库表名/`model` 类：`PascalCase`，表名默认小写复数由 SQLAlchemy 约定。

### 接口

- 新增/修改接口 **必须同步更新 `docs/接口文档.md` 的契约注释**，保持「接口文档 = 唯一真相源」。
- 响应必须套用 `schemas/common.py` 的 `success/fail`，不得裸返回 dict。
- 复杂计算（掌握率、归因、干预）必须基于关系表**真实计算**，不得退回硬编码 mock。

### Git / 协作

- 主干保护：禁止直接 push `main`，一律走 feature 分支 + PR，由技术负责人 Review。
- Commit 语义化：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`。
- 依赖变更：改 `backend/requirements.txt` 并自测 `pip install -r requirements.txt` 通过。

### 红线（务必）

- ⚠️ **JWT_SECRET 必须团队一致**：通过环境变量或 `.env` 固定强随机密钥；否则一人登录、他人无法验签，且重启后旧令牌失效（`main.py` 启动时会告警）。
- 不要把 `backend/app/data/*.db`、`.env`、密钥提交进仓库（见 `.gitignore`）。
- 不得为「前端能跑」而在后端返回假数据掩盖计算缺失。
- 不得把 `assets/js/api.js` 的 `config.mode` 改回 `mock`（mock 数据已下线）。

---

## 6. 团队分工（共 5 人）

| 角色 | 成员 | 主要职责 |
| --- | --- | --- |
| 技术负责人 | 架构/主干守护 | 基建与主干、统一 `JWT_SECRET`/`.env.example`/`.gitignore`/分支保护、所有 PR Review、维护接口文档「唯一真相源」 |
| 成员 A · Agent | 指定 | 接入 LLM+RAG：替换 `routers/ai.py` 的 `_mock_answer`，落地 `/ai/chat`、`/ai/chat/stream`（SSE）、`/question/gen`；新建 `services/` 与向量库 |
| 成员 B · 后端数据 | 未定 | 真实掌握率/归因/干预算法；扩充题库（当前十余道 vs 34 知识点）、生成学情数据 |
| 成员 C · 前端 | 未定 | 学生端 7 视图 + 教师端 7 视图维护完善；SSE 流式接入；播放器与响应式适配 |
| 成员 D · 测试/数据/DevOps | 未定 | 端到端联调迁仓、回归补用例、CI、题库规范与 `resources/` 资源分发 |

> **交接前必须让全员知道的两个关键缺口**：① AI 能力尚未接入（仅关键词/题库兜底）；② 题库与学情样本严重不足，需先补齐数据再谈算法准确度。

---

## 7. 相关文档

- `docs/README.md` —— 前端文档导航（接口文档、对接指南、数据模型、页面清单等）
- `docs/接口文档.md` —— 全部 API 契约（与 `api.js` 一一对应）
- `docs/数据模型与Mock说明.md` —— 各接口 `data` 结构与强依赖字段路径（Mock 已下线，现为后端真实返回）
- `docs/前端架构与运行.md` —— 前端技术栈、目录、本地运行
- `docs/鉴权与会话方案.md` —— 登录/JWT/路由守卫/找回密码
- `docs/后端对接指南.md` —— 接口优先级、约定、联调 checklist
- `docs/团队交接与开发指南.md` / `docs/团队协作开发手册.md` —— 更细的项目背景、分工与排期

---

*最后更新：2026-09-04 · 已根据当前代码（模块化前端 + 真实后端）重写。*
