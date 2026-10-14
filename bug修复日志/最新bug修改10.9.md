## 记录规范（后续改动请遵守）

1. 按块追加：**后端**、**前端渲染**、**LLM/Agent 相关**、**启动脚本·文档**、**数据库·数据**、其他自行补块；
2. 每条格式：`- 文件/模块：改动内容（动机）`，一行一条；
3. 新改动追加到对应块的末尾，并注明日期；
4. 破坏性改动（删表、改接口签名、改数据结构）需单独加粗标注。

## 一、图片上传、预览与智能体识图（2026-10-09）

- `backend/app/agent_st/agent/file_text.py`：新增 JPEG / PNG / GIF / WebP 文件签名识别与扩展名 MIME 对应关系，拒绝扩展名和实际图片内容不一致的上传。
- `backend/app/services/attachments.py`：共享附件服务接受 JPEG / PNG / GIF / WebP；文档文本和图片字节只进入本轮模型输入，原始附件由 `chat_attachments.py` 保存到 `AGENT_DATA_DIR` 上传目录；历史 `tool_log` 仅保存附件引用与名称、MIME、大小，不保存文件正文或图像字节。
- `backend/app/services/chat_attachments.py`：使用随机附件 ID 将原始文件持久化到 `AGENT_DATA_DIR/uploads/chat_attachments`，显示名称只作元数据；通过会话消息中的 `tool_log` 引用校验附件归属，并在删除会话或账号时清理文件；上传目录已加入 `.gitignore`，不改变数据库结构。
- `backend/app/routers/ai.py` 与 `backend/app/routers/admin.py`：为师生端和管理员端增加登录态保护的历史附件读取接口，检查会话归属及消息引用后才返回文件；删除会话时清理附件，管理员删除账号时一并清理其会话附件。
- `backend/app/agent_st/agent/tools/admin_delete.py`：管理员通过智能体确认删除账号时，也清理该账号会话引用的附件文件。
- `assets/js/shared/agent-chat.js`：三端历史消息显示图片预览且隐藏图片文件名；点击“重新编辑”时把该条消息的文字和图片、文档等附件恢复到输入框待发区，不自动发送；对无法读取的附件提示重新选择。
- `assets/js/api.js`：为师生端和管理员端添加带登录凭证的二进制附件读取方法，供历史图片预览及重新编辑恢复文件使用。
- `assets/css/app.css`：调整无文件名的图片缩略图布局，增加图片放大预览样式和缩放指针。
- `backend/app/agent_st/agent/runtime.py`：将图片转换为 Chat Completions 多模态内容块传给当前模型；未配置支持视觉输入的模型时明确提示无法识图；附件字节不写入历史记录，事件契约保持不变。
- `backend/app/agent_st/agent/sdk_runner.py`：为 Agents SDK 当前用户输入加入 `input_image` 内容块，保持原有工具与流式事件映射。
- `backend/app/agent_st/agent/llm.py`：继续使用既有 Chat Completions 请求接口，由运行层按兼容格式提供文本和图片内容。

## 二、登录周期内的智能体会话恢复（2026-10-09）

- `assets/js/shared/agent-chat.js`：首次进入不再自动选中最近历史会话；按用户、登录时间、端侧及课程在浏览器本地状态中记录当前会话，新登录从空对话开始，同次登录重新进入或刷新页面时恢复上次打开的会话。
- `assets/js/student/views/chat.js`、`assets/js/teacher/views/chat.js`、`assets/js/admin/views/assistant.js`：重置端侧会话时同步保存“新对话”状态，避免课程切换或显式重置后恢复旧会话。

## 三、用户消息复制与重新编辑（2026-10-09）

- `assets/js/shared/agent-chat.js`：三端用户消息支持复制文字和重新编辑；编辑会回填原文及该问题的图片、文档等附件到待发区并聚焦输入框，不自动发送。

## 四、教师与管理员端猜你想问动态个性化（2026-10-09）

- `assets/js/shared/agent-chat.js`：读取当前账号最近 3 个智能体会话中的用户提问，按关键词相关度与时间新近程度对推荐问题排序，并避免重复主题。
- `assets/js/teacher/views/chat.js`：根据当前课程预警人数、薄弱知识点、班级掌握率、活跃情况和驾驶舱待办生成问题，再结合教师近期答疑主题调整排序；驾驶舱不可用时按本人近期主题生成后续问题。
- `backend/app/routers/admin.py`、`assets/js/api.js` 与 `docs/接口文档.md`：新增并记录仅管理员可访问的 `GET /api/v1/admin/agent/recommendation-context` 只读汇总接口，返回账号、课程、题目、资源、知识点、预警计数及智能体模式，不返回账号明细、不写入数据。
- `assets/js/admin/views/assistant.js`：依据实时平台汇总生成治理问题，并按当前管理员自己的近期对话主题调整排序；首次使用没有历史时仍依据平台汇总推荐，接口或历史不可用时不退回静态问题清单。

## 五、三端智能体回答精炼（2026-10-09）

- `backend/app/agent_st/agent/loader.py`、`skills/explain.md` 与 `flows/explain.yaml`：移除旧的正文强制引用要求，回答优先直入主题；正文默认使用题目 / 知识点名称，不附题号和 KP 编号，引用仍由 citations 事件提供，用户询问或需区分对象时例外；排名类回答列完至多三项即止。
- `backend/app/agent_st/agent/runtime.py`：精简演示模式答疑文本，不再在正文输出题号 / KP 编号，只展示相关检索片段并说明当前未生成完整讲解。
- `backend/app/agent_st/agent/skills/explain.md` 与 `loader.py`：简单概念通常控制在 2～4 句话，定义加步骤时不重复结论；教师弱项默认只查询并列出前三项，列表后结束，不补充用户没问的知识、总结或继续查询邀请，也不输出工具调用前的进度旁白。
- `backend/app/agent_st/agent/skills/admin_ops.md`：管理员回答只列所问维度，账号数量问题不额外列账号名单、未分配课程数据或未请求建议；保留账号操作的待批准状态、必要后果及核对用户名。

## 六、教师端智能体名称调整（2026-10-09）

- `teacher.html`、`assets/js/teacher/views/chat.js`、`assets/js/shared/agent-chat.js`、`backend/app/agent_st/agent/skills/admin_ops.md` 与相关功能文档：教师端侧栏入口、页面标题和管理员助手提及教师端时统一使用「智能助手」；学生端名称不变。

## 七、三端智能体系统操作源码索引、精确定位与内容回填（2026-10-09）

- `backend/app/agent_st/agent/system_features.yaml`：按学生、教师、管理员整理当前真实页面、面板、页签、小按钮和弹窗步骤，覆盖课程选择与邀请码、章节/知识点/资源编辑、图谱悬停加号连线、热力图与预警复核、题库排序/编辑/草稿发布、报告范围/日期/导出、账号模板导入/密码重置/确认删除及三端聊天交互；注明演示入口、未实现功能和角色限制，保存对应代码锚点。
- `backend/app/agent_st/agent/system_code_index.py`、`system_guide.py` 与 `tools/analytics.py`：`get_system_guide` 默认根据完整问题检索当前角色实际加载的界面源码，返回页面、代码位置与片段，支持继续按按钮 ID / 函数名追踪绑定；新按钮不依赖人工登记功能编号；原手册核对代码锚点后作为补充，仍兼容旧功能查询；角色取服务端上下文，不读取业务数据、不自动编辑或保存。

- `backend/app/agent_st/agent/system_code_index.py` 与 `.gitignore`：每次操作查询校验已加载文件的 SHA256，仅对内容变化文件重新切片；修改、新增已加载文件、移除引用、删除文件及同大小保留时间戳的保存均在下次查询生效；索引缓存放入 `AGENT_DATA_DIR/system_code_index.json`，不上传 GitHub，损坏时重建，不依赖数据库；排除未加载旧文件、已下线页面、API 总文件、第三方脚本及其他角色源码。
- `backend/app/agent_st/agent/tools/analytics.py` 与 `assets/js/admin/views/assistant.js`：扩展原有 `suggest_action`，按角色校验真实页面入口，接通管理员「账号管理 / 智能助手」导航；学生不能跳到教师或管理员页面，教师和管理员不能生成学生练习动作；旧页面建议继续兼容，具体页签、弹窗、对象与内容准备由新增 `prepare_ui_action` 接通，最终提交仍由用户确认。
- `backend/app/agent_st/agent/loader.py`、`flows/explain.yaml`、`flows/admin_ops.yaml`、`personas/*.yaml` 与 `skills/system_guide.md`、`skills/explain.md`、`skills/admin_ops.md`：区分系统操作帮助、学情/平台查询和课程讲解；操作先查当前源码，询问时给精确入口按钮，明确指令自动打开目标并准备文字/附件；确认缺失对象、重名和角色限制，不编造「编辑课程」入口、不补造答案/收件人/密码；明确操作的成功准备回复通常只保留 1～2 句及最终确认按钮，课程讲解继续检索原文，已有后台写操作继续走审批。
- `backend/app/agent_st/agent/runtime.py`：本轮成功查询操作目录后，不将系统使用帮助误判为课程越界；SDK 与既有运行层共用提示词和该判断。
- `dev_tools/check_system_guide.py`、`dev_tools/check_system_actions.js`、`dev_tools/check_system_code_index.py` 与 `dev_tools/check_agent_roles.py`：保留原目录和权限检查，新增临时源码副本的内容更新、加载范围、删除、缓存损坏/伪造重建、并发、未登记按钮检索与回退验证；原有九个管理员业务工具及写操作审批权限保持严格校验，新增手册与导航仅为共享只读能力；前端逻辑检查使用 DOM 替身，不冒充浏览器实测。

- `dev_tools/system_index_rollback.py`：本地保存索引试用前文件及哈希，默认只预览，显式 `--apply` 恢复原手册方案；拒绝覆盖试用后新增编辑，临时工作区逐文件 SHA256 恢复验证通过；回退副本置于已忽略的 `backend/data/system-index-rollback-20261009/`，保留已有未提交修改，不改数据库或 `data.zip`。
- `docs/智能体系统操作指南.md`、`docs/接口文档.md`、`docs/页面与功能清单.md` 与 `README.md`：同步源码检索、精确定位、文字与附件回填、导入预览和维护边界；补充报告实际生成、自动点击边界及分步回退命令，保留更早索引回退。当前 31 文件 / 296 片段首次构建约 121 毫秒、复用查询中位数约 42 毫秒，不含模型回答耗时；数据库表、字段和事件契约不变。真实问答及权限检查使用数据库副本，当前 Conda 未安装原生 Agents SDK，问答走项目既有 legacy 自动回退；浏览器自动化未跑通，Node 逻辑验收不冒充浏览器实测，也不宣称所有自然语言回答完全稳定。

- `assets/agent-ui-actions.json`、`backend/app/agent_st/agent/ui_actions.py` 与 `tools/ui_actions.py`：三端共用 93 个实际入口的固定选择器、处理器和回填字段清单，涵盖侧栏页面、加入/新建/切换课程、邀请码、通知、练习模式/指定章节/知识点与错题、资源/图谱/学情面板、报告实际生成/配置/详情/导出位置、教师私信/学生详情/预警、题库/目录编辑与导入、管理员账号及聊天入口；服务端按角色、成员关系、对象和章节/知识点归属校验，重名要求选择，不接受任意代码/选择器，清单内容修改下次调用读取。报告生成使用独立入口，仅接受明确请求 auto=true，询问使用原入口/配置，不生成；管理员不能调用教学报告入口。
- `assets/js/shared/agent-ui.js`、`assets/js/teacher/views/graph-edit.js`、`student.html`、`teacher.html` 与 `admin.html`：新增共享界面执行器，调用真实 Router、页签、弹窗与对象处理器，等待异步加载后回填允许字段；文件通过 File/DataTransfer 恢复到上传控件；查询给按钮、明确指令自动打开，未保存表单及账号/课程/页面/会话变化时阻止或取消，图谱详情保存成功后清除未保存标记、关闭详情不会阻止后续操作，不自动点击发送、保存、加入、正式导入或删除。

- `assets/js/student/views/practice.js` 与 `assets/js/shared/agent-ui.js`：修复练习入口重复异步加载把已打开模式覆盖回首页的问题；重复点击已选页签不重绘，入口/存档/章节/组卷请求增加版本及上下文校验，收起或切换后旧回调不再执行。明确「我要做错题」打开实际题目，有未完成错题则继续原进度；查看错题本仍只打开列表。支持指定章节/知识点点击真实顺序练习入口，其他模式保留存档选择，空题及加载失败显示原因；不代选答案或自动提交。

- `assets/js/student/views/report.js`、`assets/js/teacher/views/report.js` 与 `assets/js/shared/agent-ui.js`：师生明确生成学情报告时，配置回填后沿用页面原生成动作，完成后刷新归档并打开详情；按钮生成期间防重入，生成计划在 sessionStorage 记录执行状态，同一计划重复点击或刷新不再生成。请求返回后若已换登录/课程/页面，不显示旧报告；未改变既有统计口径、接口、数据库表与字段，教师日期/章节仍仅记录元信息。

- `backend/app/agent_st/agent/loader.py`、`skills/system_guide.md` 与 `skills/explain.md`：移除明确生成报告仍只给导航的旧规则，区分做错题/查看错题本、实际生成/仅打开配置；精确动作不能降级成页面跳转。禁止代答、自动提交和伪造学习进度；仅提出代答刷分时简短拒绝，不擅自打开替代页面。实际模型负面用例首次会拒绝后打开练习，收紧规则复测无操作计划。

- `assets/js/shared/agent-chat.js` 与 `backend/app/agent_st/agent/runtime.py`：沿用 `tool_end.preview` 接收界面计划，计划保存现有 `tool_log` 并在历史回答重建按钮；实时完成后执行最后一个明确目标，停止生成不执行，刷新不会自动重放；附件从原有受保护读取接口恢复，缺失时提示重新上传，旧导航与审批卡片保持兼容。
- `backend/app/services/question_preview.py`、`backend/app/routers/teacher.py`、`assets/js/api.js` 与 `assets/js/teacher/views/question.js`：教师题库新增「导入题目」和只读 `POST /api/v1/question/import/preview`，支持 TXT/MD/JSON/CSV/XLSX/DOCX/文本 PDF，单文件≤10MB、每批1～100题；结构化单选/多选与文本先校验和展示，可修改并选择统一章节/知识点，修改后重新校验，通过后用户点击「确认导入题库」才沿用原导入接口写为待审核；图片需视觉模型先整理内容，没有新增扫描 PDF OCR，复杂题图不会静默丢弃后导入。
- `backend/app/routers/admin.py` 与 `assets/js/admin/views/users.js`：账号导入向导补齐既有共享解析器的 CSV/TXT 支持，和 XLSX/DOCX 使用相同校验与确认提交；智能体可携带文件或将用户提供的文字名单整理为带表头 CSV 打开预览，不自动建号；删除入口仅打开原确认弹窗，不填写确认用户名或代点删除。
- `backend/app/agent_st/agent/tools/__init__.py`、`sdk_runner.py`、`backend/app/agent_st/mcp_server.py` 与权限检查脚本：补齐界面准备工具的注册，在既有 SDK/legacy/MCP 入口保持一致；工具仅准备界面与读取对象，没有后台业务写权限，不改变学生写工具禁令。
- `dev_tools/check_ui_actions.py`、`check_ui_actions.js`、`check_ui_clicks.js`、`check_ui_report_api.py` 与 `smoke_ui_actions.py`：校验 93 个入口、三端权限、原 SSE 字段、文件预览与持久化；实际页面代码回归通过错题展开/续练、旧请求取消、空题、指定章节/知识点、报告详情/防重复及过期登录拦截。数据库副本中师生各生成一份报告、错题组卷 12 题，答题记录和 schema 不变，真实库 SHA256 不变；真实模型验证错题模式/列表、两端实际生成、询问生成入口、仅打开配置和代答拒绝。py_compile、Node 语法、角色/路由/MCP、学生答疑冒烟与源码索引主体检查通过；浏览器工具导入失败，DOM 替身不算浏览器实测。原索引检查脚本绑定旧快照的回退检查会拒绝后续编辑，不能标成整条检查全通过。

- `backend/app/agent_st/agent/system_guide.py`、`tools/analytics.py`、`tools/ui_actions.py` 与 `loader.py`：修正操作查询结果中仍要求旧 suggest_action 的冲突提示；按完整语义和最近对话承接「它/他/这个」等省略对象的追问，已实现且目标明确的操作询问须成功准备真实入口，不能只描述按钮。历史只用于确定对象，是否自动跳转只看本轮意图，避免上一轮「我要编辑」导致本轮「那在哪改」误跳转；接口、工具参数结构、事件契约和数据库格式不变（2026-10-09）。

- `skills/system_guide.md`、`skills/explain.md`、`skills/admin_ops.md`、`flows/explain.yaml` 与 `flows/admin_ops.yaml`：同步三端连续追问与入口必备规则，截图中的「那他的资源在哪里」优先给上文知识点的「关联资源」按钮，明确「带我去」才自动打开。多个对象先澄清，纯知识讲解不强制导航，未查实际资源不承诺已有课件；保留报告生成、导入确认及禁止代答边界（2026-10-09）。

- `dev_tools/check_ui_followups.py`、`smoke_ui_followups.py` 与操作指南/接口/页面文档：新增源码/手册/故障回退提示一致性、三端对象定位、原 SSE 与工具日志持久化检查；数据库副本真实问答覆盖截图原话、口语课件、明确打开、教师编辑位置、管理员密码、知识讲解和指代不明，两轮均真实调用模型的连续追问也返回真实入口。教师首次误继承旧意图，收紧后复测只给按钮；错题打开、报告生成与代答拒绝回归通过。py_compile、角色/路由/MCP、目录检查和学生真实答疑冒烟通过；当前未安装原生 Agents SDK，沿用 legacy 真实模型。未改前端，Node 逻辑检查不冒充浏览器实测；业务数据及真实库 SHA256 不变（2026-10-09）。

- `backend/data/ui-followups-rollback-20261009/`（本地忽略目录）：保存追问入口完善前的文件原文与 SHA256，默认预览、显式 --apply 恢复，仅撤销本轮修改，保留此前自动点击、报告和附件功能；临时工作区验证逐文件恢复、幂等与拒绝覆盖后续编辑，不恢复真实工作区、数据库或 data.zip。完整回退顺序为追问入口→自动点击→界面执行→源码索引（2026-10-09）。

- `backend/data/ui-clicks-rollback-20261009/`（本地忽略目录）：保存本次自动点击修改前的文件原文和 SHA256，支持单独回退到此前执行器版本，保留源码索引和图片/附件功能；默认预览、显式 --apply 恢复，拒绝覆盖后续编辑，不改业务数据库或 data.zip。先退追问入口，再退本次点击完善→此前界面执行→源码索引。
- `backend/data/ui-actions-rollback-20261009/`（本地忽略目录）：保留执行功能试用前原文、基线与试用 SHA256，`restore_ui.py` 默认预览、显式 `--apply` 恢复，拒绝覆盖后续编辑；临时工作区逐文件恢复、幂等和新增编辑保护通过。需要退回更早手册方案时先退本次执行功能再退索引，不涉及业务数据库、资源文件或 `backend/data.zip`。

## 八、教师课程资源类型选择、文件校验与封面清理（2026-10-09）

- `assets/js/teacher/resource-upload.js`、`assets/js/teacher/views/resource.js`、`assets/js/teacher/views/structure.js` 与 `teacher.html`：两个教师上传入口都先选「教材文献 / 课件 / 教学视频」；教材文献接受 PDF/DOC/DOCX/TXT，课件接受 PDF/PPT/PPTX，教学视频接受 MP4/MOV/WEBM/MKV。选择器按类别筛选，提交前检查分类与后缀；类型未选或不匹配时不会发送上传请求。
- `backend/app/routers/teacher.py` 与 `backend/app/media_utils.py`：共享上传接口按教师所选类别校验扩展名与实际内容；PDF/DOCX/PPTX 检查文件签名及包内结构，旧版 DOC/PPT 检查 OLE 流，文本检查编码/控制字符，MP4/MOV 检查 ISO BMFF 盒结构，WEBM/MKV 检查 EBML 容器。PDF 可归入教材或课件，服务端保存教师所选类别；错误文件在保存和新增资源记录前被拒绝。PDF 无论类别均可在线阅读；PPT/PPTX 通过服务器 LibreOffice 自动生成 PDF 预览并保留原件，Word 文件仍下载查看。保留数据库已有的 `doc/ppt/video` 类型值、不改表结构；自动生成的封面移除左上角类型文字。
- `backend/requirements.txt` 与 `dev_tools/init_course.py`：新增 `olefile==0.47` 以区分旧版 Word/PowerPoint OLE 流，初始化脚本给共享上传接口传分类；Conda 安装命令：`conda install -n stucourse -c conda-forge olefile=0.47 -y`。
- `assets/js/common.js`、`assets/js/student/views/mastery.js`、`assets/js/student/views/resource.js`、`docs/接口文档.md`：学生最近学习记录与教师目录/资源列表统一显示「教材文献 / 课件 / 教学视频」，不再把内部 `doc/ppt/video` 代码直接展示。`dev_tools/init_course.py` 支持资源配置项用 `resourceType` 指定 PDF 归入教材还是课件。
- `backend/data/resource-upload-rollback-20261009/`（本地忽略目录）：保存本轮修改前各文件和 SHA256；默认预览、显式 `--apply` 恢复，只覆盖本轮文件，保护后续编辑，不涉及数据库、课程资源文件或 `data.zip`。
- 2026-10-10 补充：课件分类支持 PDF/PPT/PPTX。`backend/app/services/presentation_preview.py` 接入 LibreOffice 独立进程转换，`backend/app/config.py` 提供转换器路径与超时设置；PPT 原件旁保存 `.preview.pdf`，转换完成后才发布文件与资源记录，失败明确提示。删除资源同时清理两份文件，`resource_registry.py` 避免将派生 PDF 当孤儿删除，RAG 使用 PDF 入库。仅后端机器需要安装软件，数据库表结构不变。

- 两个教师上传入口同步提示自动转换及等待状态；部署说明见 `docs/课件在线预览部署.md`。

- 验证：临时数据库和资源目录使用真实 PPTX 加转换进程测试替身，验证原件保留、PDF 页数、预览 HEAD/Range、失败不新增记录/文件、直接 PDF 跳过转换与删除清理。`py_compile`、Node 语法、角色/路由自检、MCP 与模型问答冒烟通过（SDK 不可用时按原配置回退 legacy）。当前未安装 LibreOffice，真实课件转换尚待安装后验收；?



- `backend/data/resource-courseware-rollback-20261010/`（本地忽略目录）：保存本次扩展 PDF 课件前的 11 个相关文件及 SHA256；默认预览、显式 `--apply` 恢复，拒绝覆盖后续编辑，不涉及数据库或 `data.zip`。


## 九、学生端 PDF 阅读器全屏与页码跳转（2026-10-10）

- `assets/js/student/views/resource.js` 与 `student.html`：学生端 PDF 页码输入框固定从第 1 页开始；根据 PDF 总页数限制输入值，超上限时立即回到最大页码，失焦、变更或按 Enter 也会校正页码。点击「跳转」后更新页码片段和请求参数，重新加载 PDF 并显示定位页；保留按上次阅读位置打开和保存进度的行为。更新资源视图脚本缓存版本到 `reader3`。

- 验证：Node.js 语法检查和 `git diff --check` 通过；DOM 模拟确认默认值为 1、输入超过 5 页时回到 5、跳转地址更新、状态显示和进度保存正确。Edge WebView2 验收脚本未能连接：浏览器进程没有生成 `DevToolsActivePort`，因此 PDF 内置阅读器的实际翻页效果尚未完成浏览器实测。本次只改学生端前端及文档，未改后端或数据库。

- `assets/js/student/views/resource.js`、`assets/js/common.js`、`assets/css/app.css` 与 `student.html`：默认阅读窗口扩大，增加「全屏阅读 / 退出全屏」和「下载原文件」。针对学生端弹窗看不到全屏按钮的反馈，将按钮从底部移到标题栏右上角、关闭按钮旁；标题过长时省略，按钮保持可见。学生入口为相关 JS/CSS 添加版本标记，避免沿用旧资源。不支持浏览器全屏时铺满页面，Esc 可退出；关闭时清理监听并保存进度。旧 PPT 没有预览时提示下载或重新上传。

- 2026-10-10 按钮显示修正验证：Node 语法及 `git diff --check` 通过；模拟 DOM 冒烟确认共享弹窗将全屏按钮渲染在标题栏，检查全屏/退出、降级铺满、Esc、页码跳转、关闭清理及入口版本标记。浏览器自动化仍未能建立连接，此项不冒充真实浏览器验收；本次仅修改前端与文档。

- `backend/data/resource-fullscreen-fix-20261010/`（本地忽略目录）：保存本次按钮位置与缓存版本修正前的 6 个文件及 SHA256，可单独回退，保留上一轮 PPT 转换代码；默认预览，显式 `--apply` 恢复，拒绝覆盖后续编辑。

- `backend/data/resource-preview-rollback-20261010/`（本地忽略目录）：保存本轮转换与全屏修改前的文件及 SHA256，支持预览回退和显式 `--apply` 恢复，不涉及数据库、资源文件或 `data.zip`。

## 十、教师端资源上传下拉选项提示（2026-10-10）

- `assets/js/teacher/views/structure.js` 与 `assets/css/refresh.css`：在教师端实际使用的资源上传弹窗中，为“目录（章）”和“资源类型”两个选择框增加清晰的向下箭头，并给箭头预留右侧空间；箭头样式限定在这两个选择框，不改变其他下拉框。

- 验证：`node --check assets/js/teacher/views/structure.js` 与 `git diff --check` 通过；确认 `teacher.html` 加载 `structure.js`，下拉样式在 `refresh.css` 覆盖基础样式后仍显示。浏览器交互实测尚未进行。

- Chrome/Edge 自动化启动后退出，未建立调试连接，尚未完成真实浏览器全屏和硬刷新验收。

## 十一、Windows 启动脚本识别 Conda 环境失败（2026-10-10）

- `start.bat`：将解释器探测调整为自定义 `COURSE_AGENT_PYTHON`、项目虚拟环境、已激活 Conda、`stucourse` 常见路径、PATH 与 `py` 启动器依次检查；自动选择 Python 3.11，其他设备可通过环境变量指定自己的 `python.exe`。修正错误提示在 CMD 括号块中的解析问题，并统一批处理文件换行；依赖安装改为对已选解释器使用普通 pip，不再传入 Windows/Conda 不适用的 `--break-system-packages`。
- 验证：使用 `cmd.exe` 的临时诊断分支实际运行启动脚本，输出选择 `E:\anaconda\envs\stucourse\python.exe`、Python `3.11.16` 和 `Environment OK.`；该检查未清理 8000 端口、启动服务或安装依赖。相同解释器的 FastAPI、SQLAlchemy、Uvicorn、JWT、Passlib 与 OpenAI 导入检查通过；数据库未访问或修改。

## 十二、后端启动日志标注当前 Python 环境（2026-10-10）

- `backend/app/main.py`：FastAPI 启动时打印当前环境名与 Python 版本，例如 `environment=stucourse Python=3.11.16`。Conda 环境根据实际解释器前缀识别，venv 显示其目录名，普通系统 Python 显示 `system`；不输出解释器完整路径，不改变接口、数据库或业务行为。
- 验证：`E:\anaconda\envs\stucourse\python.exe -m py_compile app\main.py` 通过；使用同一解释器调用应用启动钩子，`DATABASE_URL=sqlite:///:memory:`，日志输出 `[runtime] environment=stucourse Python=3.11.16`。验证数据库仅为内存库，未读写真实数据库。

## 十三、练习支持填空题（2026-10-11）

- `backend/app/services/blank_questions.py`：填空题的空位、多种可接受答案和判分放在现有 `questions.options` JSON 中，`questions.answer` 只存不超过 64 字的摘要；不新增表或列。
- `backend/app/routers/practice.py`：学生组卷不返回填空标准答案；提交时按空判分，选择题仍是整串相等。响应里多一个 `blankResults` 字段，只在填空题出现。
- `backend/app/services/question_preview.py`、`backend/app/routers/teacher.py`：导入和教师保存接受填空题。题干用 `____` 标空，多个空用 `；` 分段，同一空多种写法用 `|`。
- `assets/js/student/views/practice.js`、`assets/js/teacher/views/question.js`：学生练习在空位输入；教师新建、编辑题目可以选择填空题。
- 验证：`py_compile` 通过；`tests/test_blank_questions.py` 五项（双空判对、错序判错、学生端不泄露答案、导入预览）通过。未改数据库，未做浏览器点击验收。
