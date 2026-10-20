"""供三端智能体调用的只读界面准备工具。"""
from ..context import ToolContext
from ..registry import tool
from ..ui_actions import prepare_action


@tool(name="prepare_ui_action",
      description="生成真正显示在回答下方的界面入口。用户在询问功能/资料/操作位置且目标明确时必须调用，不能仅写步骤；按语义和最近对话解析口语、代词和省略。跳转必须经用户本轮确认：询问/讲解/学情默认auto=false只给按钮，用户点击后才跳转；本轮明确要求打开/跳转到该界面才auto=true。资源追问使用已确定知识点的student.graph.resources或student.resource.search，不能只给资源首页。target从系统提示选择；values仅用入口字段，不接受代码/选择器。错题重练用student.practice.mode.wrong，错题本列表用student.practice.wrong；明确生成报告用当前角色report.create；教师明确出题且题量、题型、范围都已明确时用teacher.question.create直接生成，缺关键细节时先offer_choices，询问出题位置才用teacher.question.generate。禁止代答、提交答案和伪造进度。其他表单仅回填，保存/发送/加入/导入仍用户确认。附件可use_attachments=true。对象不明确先让用户选择；未成功准备入口不得声称有按钮。",
      parameters={"type": "object", "properties": {
          "target": {"type": "string"}, "values": {"type": "object"},
          "object_id": {"type": "string", "description": "指定对象的已核实编号，可省略改用 keyword"},
          "keyword": {"type": "string", "description": "对象名称，服务器仅查询本人权限内的数据"},
          "auto": {"type": "boolean", "description": "跳转须用户本轮确认：本轮明确要求打开/跳转到该界面或继续执行为true；询问位置、讲解、学情为false只给按钮。历史只确定对象，不继承上轮自动跳转"},
          "use_attachments": {"type": "boolean", "description": "携带本轮已上传的文件"}},
          "required": ["target"]}, flows=("explain", "admin_ops"))
def prepare_ui_action(ctx: ToolContext, target: str, values: dict = None, object_id: str = "", keyword: str = "", auto: bool = False, use_attachments: bool = False):
    return prepare_action(ctx, target, values, object_id, keyword, auto, use_attachments)
