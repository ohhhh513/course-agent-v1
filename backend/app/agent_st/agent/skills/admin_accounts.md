# 技能：账号治理（管理员）

师生账号概况，以及导入/删除（必须经待批准卡片）。不做教学学情，不重建索引。

## 查询

账号数量与分布、未分配课程、从未练习的学生、教师带课数 → `account_overview`。数字必须来自工具。问数量就只报所问角色的数量，不额外列名单。

## 导入（写操作）

1. `preview_account_import`，用一两句报告解析结果（valid / dup / error）。
2. 有 valid 记录再 `import_accounts`，`accounts` 原样传 `validAccounts`，不要改密码。
3. 这是待批准动作：**不能说已经导入**，必须提示点确认卡片。

## 删除（写操作）

**删账号：**

1. `preview_account_delete`：附件名单或 `usernames`。报告可删与被拒原因。
2. `delete_accounts` 只传 `deletableAccounts`。
3. **不能说已经删除**；说明会级联清理且不可撤销。

**删课程：**

1. `preview_course_delete`：给 `courseId` 或 `courseName`（只知道课名时先精确匹配，匹配到多门要让管理员指明）。
2. `deletable=false` 时**不要**调 `delete_course`，说明课程里还剩多少成员，请管理员先到「成员」里移出。
3. `deletable=true` 时把 `courseId` **原样**传给 `delete_course`。
4. 同属待批准动作：**不能说已经删除**，并提醒不可撤销。删课会一并清理该课程的题库 / 资源 / 图谱 / 学习记录 / 会话 / 报告等关联数据；师生账号本身保留。

其它写入（改课程、重建索引）本技能做不到，指向对应管理页。询问入口 auto=false，明确打开才 auto=false。不能跳转师生教学页面。
