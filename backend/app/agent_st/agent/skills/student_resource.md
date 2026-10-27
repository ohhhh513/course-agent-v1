# 技能：资源导航（学生）

按章或知识点找本课程已挂载的课件、文档等，并说明在哪打开。未查到真实资源时不能承诺「已有视频/课件」。

## 步骤

1. 从本轮或最近对话确定对象；多个对象先澄清。
2. `resolve_topic` 传用户原话整词，得到知识点或章节。
3. 先查 `get_system_guide`，再 `prepare_ui_action`：
   - 知识点明确时优先 `student.graph.resources`，keyword=完整知识点名称；
   - 需要资源中心时用 `student.resource.search`，values.keyword 填该名称。
4. 询问位置 auto=false 给按钮；明确「带我去 / 打开」才 auto=false。

入口不证明已经挂载资源。只需说明可以去查看，没有资源由页面提示。纯概念「为什么快」不属于本技能，请用户改选课程答疑。
