# AGENTS.md · 在这个仓库里干活的 AI 助手必须遵守

> 这份文件是给**任何 AI 编码助手**看的：Codex / Claude Code / Cursor / Copilot / 网页版大模型都算。

> 本文件优先级高于你自己的默认习惯；和用户当面的指令冲突时，以用户当面指令为准。

---

## 1. 三条铁律（项目所有者定下，不可协商）

1. **前端可以直接改** —— 页面、样式、交互随便动。
2. **改后端之前必须先给影响分析** —— 改哪个接口 / 谁在调用 / 学生端与教师端分别会看到什么变化 / 出错怎么回退。**人类确认后才动手。**
3. **禁止直接修改数据库格式** —— 不加表、不加列、不改字段类型、不写迁移脚本。需要存新数据时先看现有列够不够用：
   - `chat_messages.tool_log`（JSON 文本）：工具调用日志；将来的「待审批动作」也放这里。
   - `reports.detail_json`：报告没有 `user_id/course_id` 列，归属信息写进这个 JSON。

补充：**不写补丁式代码**。系统最终要部署到服务器，能用 SDK / 框架的规范做法就用规范做法，不要「能跑就行」的临时代码。

---

## 3. 明确禁止的事

- ❌ 改**事件契约**（`session` / `text` / `think` / `tool_start` / `tool_end` / `draft` / `citations` / `action` / `error` / `done` 的名字与字段）。前端只认这一套。
- ❌ 在**真实数据库**上做验证。`backend/app/data/course_agent.db` 视为只读；用 `dev_tools/` 里自带库副本的脚本，或自己复制一份到临时目录。
- ❌ 删除、修改或提交 `backend/data.zip`（打包给别人用的产物，当前有意保持未跟踪）。
- ❌ 一次同时做多个阶段。**一次一件事**，做完验证再进入下一步。
- ❌ 顺手重构无关文件；为了「让检查通过」而修改检查脚本的预期值。
- ❌ 在没有跑过 `py_compile` 和冒烟脚本的情况下宣称「应该没问题」。
- ❌ 把学生写操作工具加进学生可用的流（学生端不允许有写权限）。

---

## 4. 收工前的标准动作

```bat
REM 1. 语法检查（把 <改过的.py> 换成实际文件）
backend\.venv\Scripts\python.exe -m py_compile <改过的.py>

REM 2. 工具与角色权限自检
backend\.venv\Scripts\python.exe dev_tools\check_agent_roles.py

REM 3. 路由角色闸门自检（教师端前缀 + /agent/ingest/*）
backend\.venv\Scripts\python.exe dev_tools\check_route_roles.py

REM 4. 智能答疑冒烟（真调模型，默认在库副本上跑）
backend\.venv\Scripts\python.exe dev_tools\smoke_agent_sdk.py --runtime sdk --user stu07 --question "我现在有哪些预警？"

REM 5. MCP 导出端到端（真实 MCP 客户端拉起 server 子进程；需要装了 mcp 的解释器）
backend\.venv\Scripts\python.exe dev_tools\check_mcp_tools.py
```

- 没有 `backend\.venv` 时，用系统 Python 3.11 装 `backend/requirements.txt` 也能跑通 1–3。
- 新克隆的仓库**没有** `backend/app/data/course_agent.db`（被 `.gitignore` 排除），
  跑 2/3/4 之前先放一份演示库进去（详见 `docs/Agent化改造-交接与阶段划分.md` 的 7.2）。

- 动了教师端接口：再用教师账号（`wangjg/123456`）跑一次。
- 动了前端：在浏览器里实测，并说明点了哪里、看到什么（含硬刷新，避免旧缓存误导）。
- 动了提示词 / 行为规范（`skills/*.md`）：至少在库副本上跑一次真实问答，把回答原文贴出来。

---

## 5. 提交规范

- 中文提交信息**不要用 ASCII 双引号**（PowerShell 会吃掉），用 `「」`。
- 一次提交只装一件事；提交信息写清「改了什么 / 为什么 / 怎么验证的」。
- 提交前跑 `git status`，确认没有把 `data.zip`、临时脚本、`__pycache__` 一起带进去。
- **不要替人类做 push 决定**：本地提交可以，推送前问一句。

---
