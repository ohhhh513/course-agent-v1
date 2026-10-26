# 部署与 MCP 接入

> 适用对象：要把本系统部署到服务器的人，要把 `registry` 的工具接进 Claude Desktop / Cursor 的人。
> MCP 部分对应《Agent化改造-交接与阶段划分.md》的 P4。

---

## 1. 部署 checklist

### 1.1 必做（不做会出问题）

| # | 项 | 怎么做 | 不做会怎样 |
| --- | --- | --- | --- |
| 1 | **固定 `JWT_SECRET`** | 在 `backend/app/.env` 写 `JWT_SECRET=<64 位随机十六进制>`（`python -c "import secrets;print(secrets.token_hex(32))"`） | `config.py` 在没设时会**每次启动随机生成**（fail-secure，不是用已知占位符）；但每次重启后**所有旧令牌立刻失效**，用户被踢下线。启动日志会出现 `[SECURITY WARNING] JWT_SECRET 未通过环境变量设置…` |
| 2 | **装齐依赖** | `pip install -r backend/requirements.txt`（版本已钉死，见 §1.2） | `starlette` / `pydantic` 被间接升版会让 FastAPI 直接起不来 |
| 3 | **关闭调试** | 保持 `DEBUG=False`（默认）；生产别设 `DEBUG=1` | 开着会打印 SQL 与报错栈 |
| 4 | **备份两个 SQLite 文件** | `backend/app/data/course_agent.db`（业务库）+ `backend/app/data/st/rag.db`（RAG 切片库） | 两者都被 `.gitignore` 排除，**仓库里没有**；丢了就是真丢 |
| 5 | **`NO_PROXY` 含 `127.0.0.1`** | 服务器上若有 `HTTP_PROXY`/`HTTPS_PROXY`，加 `NO_PROXY=127.0.0.1,localhost` | 本机回环请求被代理转发 → 502，现象像"服务没起来" |

### 1.2 依赖版本：为什么钉得这么死

`backend/requirements.txt` 里有几条**带注释的硬钉**，都是踩过的坑：

| 依赖 | 钉法 | 原因 |
| --- | --- | --- |
| `sse-starlette` | `==2.1.3` | 2.2.x 要求 `starlette>=0.41.3`，与 fastapi 0.115 冲突 |
| `starlette` | `==0.38.6` | fastapi 0.115 把 starlette 卡在 `<0.39` |
| `bcrypt` | `==4.0.1` | `passlib[bcrypt]` 的兼容版本 |
| `openai` | `>=1.55.3,<2` | 低于 1.55.3 与 `httpx>=0.28` 冲突（`proxies` TypeError） |
| **`mcp`** | **`==1.12.4`** | **见下** |

**MCP 版本是本项目依赖组合下最紧的一条约束（P4 实测）**：

- `mcp 1.13 ~ 1.30` 在 `python_version < "3.14"` 上要求 **`pydantic>=2.11.0`**，
  而本项目钉的是 `pydantic==2.9.2` → **装不上**（`mcp 1.30.0` 就是文档里写过"已装"的那个版本，实际与本项目冲突）。
- `mcp 2.x` 会把 `starlette` 升到 **1.x**，与 `fastapi 0.115`（要求 `starlette<0.39`）**直接冲突**。
- 结论：`mcp==1.12.4` 是**能装上的最高版本**（要求 `pydantic>=2.8`，与 `starlette 0.38.6` 兼容）。
  **想升 mcp 就得同时升 pydantic + fastapi + starlette**，那是单独的依赖升级决策，别顺手改。

### 1.3 目录与静态资源

- 前端就是仓库根目录的 `*.html` + `assets/`，后端用 `StaticFiles` 挂 `/assets` 与 `/`（`html=True`）。
  所以**部署时整个仓库都要在服务器上**，不能只拷 `backend/`。
- `FRONTEND_DIR` = 仓库根；`BACKEND` = 仓库 `backend/`；两个路径都由代码从文件位置推导（绝对路径），
  **与启动时的工作目录无关**。

### 1.4 启动 / 停止

```bat
start.bat            REM 优先用 backend\.venv，没有就探测本机 Python 3.11；端口 8000
stop.bat             REM 按端口找 PID 并 taskkill
```

使用 Conda 时，环境中的 Python 必须是 **3.11**。可以在 Anaconda Prompt 中先 `conda activate <环境名>`，再运行 `start.bat`。双击启动需要在项目根目录新建 `.env.start.bat`：

```bat
@echo off
set "COURSE_AGENT_CONDA_ENV=course-agent-py311"
```

该本地配置已被 `.gitignore` 的 `.env.*` 规则忽略，不会影响协作者。启动时会先激活指定 Conda 环境；也可以改用 `set "COURSE_AGENT_PYTHON=D:\实际路径\python.exe"` 直接指定解释器（优先级高于环境名）。按环境名启动需要 `conda.bat` 在 PATH 中，否则从 Anaconda Prompt 运行，或使用完整解释器路径。

`start.bat --check` 只检查解释器并显示路径、版本，不安装依赖、不清理端口、不启动服务。显式指定的环境不符合要求时会直接报错，不会静默换到其他环境。

手动方式：

```bat
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 健康检查：`GET /health`。
- 首次启动会自动建表、确保 admin 账号存在；演示数据默认**不写**（要演示数据得显式 `DEMO_SEED=1`）。
- `.env` 位置是 `backend/app/.env`（**不是** `backend/.env`）。

### 1.5 出网与模型

- 所有对模型的请求都走 `backend/app/agent_st/net.py` 里统一构造的 httpx 客户端；
  代理**完全交给环境变量**（`HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`），代码不额外干预。
- `LLM_API_KEY` 留空 = 演示模式（真实检索、不访问外网）。**注意**：`chat_available()` 只看 key 是否非空，
  所以填了一个**失效的 key** 不会退回演示模式，而是每次请求都报 401 —— 这种情况把 key 清空即可。

### 1.6 升级与回滚

1. 先备份 §1.1 第 4 条的两个 `.db`；
2. 拉新代码 → 若 `requirements.txt` 变了，先 `pip install -r backend/requirements.txt`；
3. 重启服务（`stop.bat` → `start.bat`）；
4. 回滚：切回上一个提交 + 恢复两个库文件。

> 看板/UI 无缓存问题：静态资源已加 no-cache 响应头；万一浏览器仍拿旧 JS，硬刷新（Ctrl+F5）。

---

## 2. MCP 接入（给 Claude Desktop / Cursor 用）

### 2.1 它是什么

`backend/app/agent_st/mcp_server.py` 把 `registry` 里**同一批工具**挂成一个 MCP server（stdio），
外部 MCP 客户端就能直接调用它们——**工具实现零改动**，与 `/ai` 答疑用的是同一套代码与数据。

### 2.2 安全模型：本地进程信任 + 显式作用域

MCP 客户端**没有**本系统的 JWT，所以作用域在**启动参数**里固化，不在协议里协商：

```
--user <用户名或 user_id>    --course <课程 ID>    --flow explain|generate_items
```

- 启动时查库校验「用户存在」**且**「是本课程成员」——与 HTTP 层 `get_current_course_id`
  的成员校验同源；任一不成立就**退出码 2** 并打印可读原因（不会用默认值兜底）。
- 工具签名里**没有** `course_id` / `user_id`（课程由服务端注入），客户端与模型都改不了作用域。
- **不校验密码**：能把配置写进 MCP 客户端的人，本来就能读 `backend/app/.env` 与数据库文件。
  需要更严隔离就别用本机 stdio（本项目**没做** HTTP + 一次性令牌那条路）。
- **写工具不暴露**：带 `approval` 的工具（当前三个：`save_question_draft` / `import_accounts` / `delete_accounts`）
  不进 `list_tools` —— MCP 客户端没有确认卡片、也没有 `/agent/actions/{id}/approve` 入口，
  暴露出来只会排一条**永远批不了**的 pending。
- 工具可见性 = 「该 `--flow` 的白名单」∩「该角色可用的工具」，与 `/ai` 答疑同一套过滤；
  **暴露出来的**工具都标了 `readOnlyHint`（写工具已被上面那条过滤掉，所以 MCP 侧确实全是只读）。

| 作用域 | `--flow explain` | `--flow generate_items` | `--flow admin_ops` |
| --- | --- | --- | --- |
| 教师 | 13 个（含 5 个教师专用：`class_overview` / `class_alerts` / `student_profile` / `kp_heatmap` / `hot_wrong_questions`） | 7 个（含 `search_similar_questions` / `submit_item_plan` / `check_novelty` / `validate_question`；**不含**写工具） | 0 个（治理流只对管理员开放） |
| 学生 | 8 个（看不到任何教师专用工具） | 3 个（`get_question` / `resolve_topic` / `retrieve_chunks`） | 0 个 |
| 管理员 | 0 个（角色收紧后管理员不再进教学流，唯一的流是 admin_ops） | 0 个 | 7 个（5 个只读查询 + `preview_account_import` / `preview_account_delete`；两个写工具按上面的规则**不暴露**） |

### 2.3 先自检，再往客户端里配

```bat
REM 1) 看一眼作用域解析出来的工具清单（不开 MCP 会话，最省事的排错入口）
cd backend
.venv\Scripts\python.exe -m app.agent_st.mcp_server --user wangjg --course CCHYJTKE --list
.venv\Scripts\python.exe -m app.agent_st.mcp_server --user stu08 --course CCHYJTKE --flow generate_items --list

REM 2) 端到端验收（真实 MCP 客户端 ↔ 真实 server 子进程，含越权与真取数断言）
cd ..
.venv\Scripts\python.exe dev_tools\check_mcp_tools.py
```

`check_mcp_tools.py` 会自己把演示库复制到临时目录再跑，**不写真实库**；它需要**装了 `mcp` 的解释器**。

### 2.4 Claude Desktop 配置

编辑 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "course-agent-teacher": {
      "command": "C:\\path\\to\\course-agent\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.agent_st.mcp_server", "--user", "wangjg", "--course", "CCHYJTKE"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\course-agent\\backend",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

- **用 `PYTHONPATH` 而不是依赖客户端的工作目录**：`-m app.agent_st.mcp_server` 只要求 `backend/` 在
  模块搜索路径里；数据库路径与前端目录都是代码里按文件位置推导的绝对路径，**与 cwd 无关**（实测可行）。
- 想同时给教师和学生两个作用域，就在 `mcpServers` 里加**多条**（名字不同即可）。
- 想同时开出题工具，再加一条把 `args` 里的 `--flow` 换成 `generate_items`。
- 改完重启 Claude Desktop。

### 2.5 Cursor 配置

项目级 `.cursor/mcp.json`（或全局 `%USERPROFILE%\.cursor\mcp.json`），字段同上：

```json
{
  "mcpServers": {
    "course-agent-teacher": {
      "command": "C:\\path\\to\\course-agent\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.agent_st.mcp_server", "--user", "wangjg", "--course", "CCHYJTKE"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\course-agent\\backend",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### 2.6 排错

| 现象 | 原因 / 处理 |
| --- | --- |
| 客户端里看不到这个 server | 先单独跑 §2.3 的 `--list`。命令能跑通说明服务没问题，是客户端配置或路径写错（`command` 必须指向**装了依赖的解释器**，别写 `python`） |
| 工具列表为空 | 该 `--user` 的角色在这条 `--flow` 里没有可用工具（例：学生 + `generate_items` 只剩 3 个只读工具；若某种角色确实一个都没有，就是空的） |
| 启动即退出、客户端报 server 挂了 | 看 stderr：`[mcp] 启动失败：…` 会写出原因（用户不存在 / 不是课程成员 / 课程不存在）——这几条都是**有意拒绝**，不是 bug |
| 中文乱码 | 配 `PYTHONIOENCODING=utf-8`；Windows 下 stdio 默认编码可能与 UTF-8 不一致 |
| 客户端调用报「未知或不可用的工具」 | 该工具不在当前作用域（角色不够，或该 flow 白名单里没有）。这是**角色/流过滤**在起作用 |

---

## 3. 本轮（P4）没做的事

- **HTTP / SSE 型 MCP + 一次性令牌**：只做了 stdio（本地进程信任）。远程客户端接入需要另做一个
  签发令牌的端点并管理令牌生命周期。
- **容器化**：没有 Dockerfile / compose（本机是 Windows，容器那条路受本机安全策略限制）。
- **写工具的 MCP 化**：等 MCP 侧有了确认交互（或改成"生成待批准动作 + 由系统侧确认"的两段式）再放开。
