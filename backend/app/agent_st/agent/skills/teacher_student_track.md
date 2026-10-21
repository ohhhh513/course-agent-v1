# 技能：个体追踪（教师）

点名某个学生，看其近期练习、学习路径和 AI 互动摘要。不展示、引用或改写学生原始问句，不推断真实身份以外的隐私。

全班排名、共性错题、出题请改选其它技能。

## 必须

1. `student_id` 只用工具返回的 studentId 或教师给出的学号。可先 `class_alerts` 核对该生是否在预警名单，但主体是 `student_profile`。
2. `student_profile` 默认 `days=7`，最多 30。结合 `recentLearning` 与 `aiInteractionAnalysis`。
3. 每个主题 `likelyDoubt` 非空时必须呈现归纳疑惑；`confidence` 只说明推断强弱，不得因此省略。
4. 说明摘要的 `throughDate` 和 `latestScanAt`。提问次数是疑惑线索，不等于答题薄弱；单次提问不断言薄弱。
5. 没有真实答题或问答记录就明确说无法判断，不得补造。

学生不在当前课程：如实转告，不要复述错误 id。跳转须本轮确认。
