# dev_tools · 开发测试初始化脚本

**用途**：用 **真实 HTTP API** 批量初始化一门课（章、知识点、资源、可选题目导入、知识图谱边）。  
**仅开发/演示验收使用**，不会被 `main.py` / `run_seed` / `bootstrap` 自动调用。

## 与系统的隔离约定

| 规则 | 说明 |
| --- | --- |
| 不进启动链路 | 不写在 `backend/app/`，不被 `uvicorn` 导入 |
| 走 HTTP 而非 TestClient | 必须先 `start.bat` 或手动起后端，再对 `127.0.0.1:8000` 请求 |
| 不写死演示课 | 目标课号由配置指定；建课后返回新 `courseId` |
| 配置与产物分离 | 示例配置可提交；上传清单/临时 JSON 可放 `dev_tools/out/`（可 gitignore） |

## 前置

1. 后端已启动：`cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（或 `start.bat`）
2. 教师账号存在（可用管理员 `admin/admin` 先建号）
3. 准备本地资源文件（mp4/pdf/ppt 等）

## 用法

```bat
:: 默认读同目录 sample_config.json
python dev_tools\init_course.py

:: 指定配置
python dev_tools\init_course.py --config dev_tools\my_course.json

:: 指定服务地址
python dev_tools\init_course.py --base http://127.0.0.1:8000

:: 只建课与目录，不上传文件
python dev_tools\init_course.py --skip-uploads
```

## 配置字段（`sample_config.json`）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `baseUrl` | 否 | 默认 `http://127.0.0.1:8000` |
| `teacher.username` / `password` | 是 | 教师登录 |
| `course.name` | 是 | 课程名 |
| `course.useCourseId` | 否 | 已有课号则跳过建课，直接用该课（须为该教师已加入的课） |
| `course.term` | 否 | 学期文案 |
| `chapters[]` | 是 | 目录；每章 `name`、`kps[]`（名称字符串） |
| `resources[]` | 否 | `file` 本地绝对/相对路径，`chapter` 章名，`kps` 该资源标签（KP 名） |
| `graph.edges[]` | 否 | `source`/`target` 为 **KP 名**，`relation`: `pre`\|`advance`\|`parallel` |
| `questionsFile` | 否 | JSON 数组路径，按题库导入契约（`stem`/`options`/…），写入当前课 |

## 执行结果

成功后打印：

- `courseId` / `inviteCode`
- 建章、建 KP、上传资源数量与错误列表

把 `inviteCode` 发给学生账号 `POST /course/join` 即可入课联调。

## 题库批量导入（独立脚本）

转换脚本（源 → 导入契约）：

```bat
python dev_tools\convert_after_class.py
```

导入到**指定课程**（需已建章/KP；课号用 `--course`）：

```bat
:: 先校验文件与 KP 匹配，不写入
python dev_tools\import_questions.py --course <courseId> --dry-run

:: 正式导入（分批 50）
python dev_tools\import_questions.py --course <courseId>

:: 自定义教师/题库路径
python dev_tools\import_questions.py --course <courseId> ^
  --teacher dev_teacher --password 123456 ^
  --file dev_tools/questions_after_class_import.json
```

也可在 `course_structure_ds.json` 里设 `questionsFile`，用 `init_course.py` 与资源一并初始化。
