# dev_tools · 开发测试初始化脚本使用说明

用 **真实 HTTP API** 批量初始化一门课：章节 / 知识点 / 上传资源 /（可选）导入题库。  
**仅用于开发与验收**，不被系统启动（`main.py` / `uvicorn`）自动执行。

---

## 1. 与系统的隔离

| 约定 | 说明 |
| --- | --- |
| 不进启动链路 | 目录在项目根 `dev_tools/`，后端不会 import |
| 走 HTTP | 先启动后端，再对 `http://127.0.0.1:8000` 发请求 |
| 不灌演示数据 | 业务课由教师界面或本脚本产生 |

---

## 2. 启动后端

```bat
:: 项目根目录
start.bat
```

或：

```bat
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开：<http://127.0.0.1:8000>

首次空库启动应看到类似：

```text
[startup] 数据库表已就绪（空库可直接使用）
[admin] 已创建管理员账号 admin/admin
[startup] 演示数据已关闭。请用 admin/admin 登录后创建教师与课程…
```

> 若日志仍有大量 `[bootstrap] 图谱已扩展`，说明跑的是旧入口，请确认 `backend/app/main.py` 为新版，且未设置 `DEMO_SEED=1`。

---

## 3. 新建教师 / 学生账号（管理员）

新版系统**不提供**演示师生账号，需先开号。

1. 登录页选 **管理员** → `admin` / `admin` → 进入 `admin.html`
2. 点 **新建账号**
3. 填写：
   - 角色：教师 / 学生  
   - 用户名（登录用，如 `teacher999`）  
   - 姓名  
   - 密码（至少 6 位，测试可用 `123456`）  
   - 学生可填班级；教师可填部门  
4. 列表中可 **删除** 账号（需输入用户名确认；课程创建者不能直接删）

教师也可在教师端 **顶栏「+」新建课程**；批量脚本可再选课或新建。

---

## 4. 批量上传（交互 · 推荐）

```bat
python dev_tools\init_course.py
```

（默认读 `dev_tools\course_structure_ds.json`，可用 `--config` 换配置）

### 交互步骤（当前流程）

| 步骤 | 提示 | 操作 |
| --- | --- | --- |
| 1 资源路径 | 若配置为空：`当前为空，请完成初次配置` → 填三类目录<br>若已有：`当前配置默认值` → 回车沿用 / `y` 修改 | 回车或填路径；修改后会写回配置并提示「已将本次修改设置为默认路径」 |
| 2 章节 KP | 列出配置里的章与知识点 | `n` 直接用 / `e` 可改名、改 KP、增删章；可写回 `chapters` |
| 3 教师登录 | 尽量列出教师供选择，或手输用户名 | 再输入该教师密码 |
| 4 选择课程 | 先列已有课，可选 **新建课程（输入名称）** | 新建时回车默认名「数据结构与算法」，也可自定义 |
| 5 建目录+上传 | 按章建 KP，再按路径上传 | 结束打印 `courseId` / `inviteCode` / 成功失败数 |

### 三类资源路径含义

| 字段 | 放什么 |
| --- | --- |
| `textbooksRoot` | 教材 **PDF** 所在文件夹（文件在根下） |
| `videosRoot` | **MP4** 所在文件夹 |
| `slidesRoot` | **PPT/PPTX** 所在文件夹 |

配置中文件写成：

```json
"file": "{textbooksRoot}/DOC_Ch01_….pdf"
"file": "{videosRoot}/VID_Ch01_….mp4"
"file": "{slidesRoot}/PPT_Ch01_….pptx"
```

**注意：**

- 路径不要带英文引号；可用 `D:\...` 或 `D:/...`
- 根目录应**直接**指向放文件的文件夹，不要再拼一层 `textbooks/`
- 三类目录都为空则跳过上传

---

## 5. 结束后怎么用

1. 用打印的 **inviteCode** 给学生；学生端「加入课程」
2. 教师端顶栏选中该课 → 「课程目录与资源」应看到章与资源
3. 教师顶栏 **邀请码** 按钮可随时再看邀请码

---

## 6. 只导入题库

```bat
:: 交互：选教师 → 选课 → 可先 dry-run
python dev_tools\import_questions.py
```

依赖：该课已建章与 KP（题库里的 `kpNames` 按名称匹配）。

转换源题库（可选）：

```bat
python dev_tools\convert_after_class.py
```

---

## 7. 命令行参数（非交互）

```bat
python dev_tools\init_course.py ^
  --config dev_tools\course_structure_ds.json ^
  --base http://127.0.0.1:8000 ^
  --teacher teacher999 --password 123456 ^
  --course CXXXXXXX ^
  --textbooks-root "E:/素材/教材PDF" ^
  --videos-root "E:/素材/视频" ^
  --slides-root "E:/素材/PPT"
```

| 参数 | 说明 |
| --- | --- |
| `--course` | 已有课号；不传则按配置 `useCourseId` 或新建 |
| `--textbooks-root` 等 | 覆盖配置中的三类根目录 |
| `--skip-uploads` | 只建章/KP，不传文件 |
| `-i` / `--interactive` | 强制走交互问答 |

---

## 8. 配置文件字段速查

主配置：`course_structure_ds.json`

| 字段 | 说明 |
| --- | --- |
| `baseUrl` | 后端地址，默认 `http://127.0.0.1:8000` |
| `teacher` | 仅作默认值；交互时一般会另选教师 |
| `course.name` | 新建课默认名 |
| `course.useCourseId` | 写死课号则跳过建课 |
| `textbooksRoot` / `videosRoot` / `slidesRoot` | 三类资源目录（脚本可读可写） |
| `chapters[]` | `{ name, kps: ["知识点名", …] }` |
| `resources[]` | `{ file, chapter, kps, title }`；`chapter`/`kps` 必须与上面名称一致 |
| `graph.edges` | 可选；`source/target` 为 KP **名称** |
| `questionsFile` | 可选；题库 JSON 路径 |

---

## 9. 常见问题

| 现象 | 处理 |
| --- | --- |
| 教师登录失败 | 用管理员先建号；密码为该教师密码 |
| 无法选课 / 未加入课程 | 该教师尚未建课或未加入；选「新建课程」 |
| 上传 FAIL 文件不存在 | 检查三类目录是否指向**含该文件的文件夹**；路径不要带引号 |
| 资源挂不上知识点 | 配置 `resources[].kps` 名称须与 `chapters[].kps` 完全一致 |
| 题库导入大量未匹配 KP | 先完成章/KP 初始化，再 `import_questions.py` |
| 端口占用 | `stop.bat` 后再 `start.bat` |
| 想换课但不想新建 | 交互时选已有 `courseId`，或 `--course` |

---

## 10. 目录内文件

| 文件 | 作用 |
| --- | --- |
| `init_course.py` | 主入口：路径 / 章 KP / 建课 / 上传 |
| `import_questions.py` | 仅题库导入 |
| `convert_after_class.py` | 旧 after_class.json → 导入契约 |
| `cli_common.py` | 交互与 HTTP 公共库 |
| `course_structure_ds.json` | 数据结构课示例配置 |
| `questions_after_class_import.json` | 转换后的题库示例 |
| `upload.bat` | 一键：初始化 → 可选导题 |
| `sample_config.json` | 最小配置样例 |

---

**一句话：** 启动后端 → 管理员建教师 → 运行 `init_course.py` 按提示填三类资源目录、选教师与课程 → 得到 `courseId` / `inviteCode` → 学生凭码入课。

---

## 11. 生成一份「演示库」（1 教师 + 10 学生，带学情）

目标：一条可复现的流水线，产出一个**内容 + 学情都真实**的演示数据库
（默认就是 `backend/app/data/course_agent.db`，`start.bat` 直接用它）。

分工原则：**课程内容一律走上面的官方导入器**，`seed_demo_db.py` 只补「账号 + 学情」。

| 步骤 | 命令 | 说明 |
| --- | --- | --- |
| ① 生成导入配置 | `python dev_tools\seed_demo_db.py config` | 由 `course_structure_ds.json` 派生 `demo_config.json`，把课名与三类资源根改成仓库内素材（`resources/data-structures-1-9/`，65 个文件） |
| ② 建库 + 账号 | `python dev_tools\seed_demo_db.py init-db [--force]` | 建表 + 1 管理员 / 1 教师（wangjg）/ 10 名学生（stu01…stu10）/ 班级 |
| ③ 起后端 | `start.bat`（或 `python -m uvicorn app.main:app --port 8000`） | 后端必须指向同一份库 |
| ④ 教师建课 | 教师端顶栏「+」建课，或 `POST /api/v1/teacher/courses` | `init_course.py` 的非交互模式要先有课号 |
| ⑤ 章/KP/资源 | `python dev_tools\init_course.py --config dev_tools\demo_config.json --course <课号> --teacher wangjg --password 123456` | 9 章 / 26 KP / 65 个资源，全部走上传接口 |
| ⑥ 题库 | `python dev_tools\import_questions.py --course <课号> --teacher wangjg --password 123456` | 228 题，按 KP 名称挂载 |
| ⑦ 知识点关系与介绍 | `python dev_tools\seed_demo_db.py content --course <课号>` | 27 条前置链 + 6 条并列关系 + 26 条知识点介绍；同时给画布布好坐标（需服务在跑） |
| ⑧ 学情 | 停后端 → `python dev_tools\seed_demo_db.py activity --course <课号>` | 10 名学生的答题/练习/资源进度/打卡/消息/答疑，再由后端自身逻辑推导学习路径与预警 |
| ⑨ 直接演示 | 重新 `start.bat` | 账号见输出，或随时 `python dev_tools\seed_demo_db.py accounts` |

要点：

- `activity` 可重复执行：它会先清掉这 10 名学生在该课程里上次生成的数据，再重算，**不动课程内容**。
- 学生的掌握率/正确率/预警**不是写死的**：脚本只生成 `answer_records` 等原始记录，
  学习路径用 `services/learning_path.sync_user`、预警用 `services.alert_detector.detect_alerts` 推导，
  所以页面之间口径一致（换随机种子 `--seed` 可重来一套）。
- 10 名学生的画像（学霸→落后）定义在 `seed_demo_db.py` 顶部的 `PROFILES`，改完重跑 `activity` 即可。
- 知识点关系与介绍写在 `seed_demo_db.py` 顶部的 `KP_PRE` / `KP_PARALLEL` / `KP_SUMMARY`（用**知识点名称**书写，脚本再解析成 id），
  推送时走教师端官方接口：`PUT /teacher/graph/kp-topology`（坐标 + 并列）与
  `PUT /teacher/structure/kps/{id}/relations`（前置，含环检测、并双写 `kp_details.pre_kp/post_kp`）；
  介绍走 `PUT /teacher/structure/kps/{id}` 落 `kp_details.summary`。
  ⚠️ 顺序不能反：拓扑接口是**覆盖式**重写 pre/advance/parallel，所以先推拓扑、再推前置关系。
