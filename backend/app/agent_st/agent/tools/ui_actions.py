"""供三端智能体调用的只读界面准备工具。"""
from ..context import ToolContext
from ..registry import tool
from ..ui_actions import prepare_action


@tool(name="prepare_ui_action",
      description="准备真实的界面操作确认卡，不执行跳转。所有端的页面、弹窗、练习、资源、报告和出题入口都必须先询问用户，点击确认才执行，即使本轮已经说打开也不能自动跳。auto保留兼容，一律传false。目标和对象来自实际目录，缺对象先澄清；不能只写步骤或伪造入口。错题重练用student.practice.mode.wrong，报告生成用对应report.create；教师出题需先补齐范围、题量、题型再准备teacher.question.create确认卡。只说内容已准备、请确认，禁止声称正在打开或已经生成。保存、发送、加入、正式导入及删除仍走原有确认。",
      parameters={"type": "object", "properties": {
          "target": {"type": "string"}, "values": {"type": "object"},
          "object_id": {"type": "string", "description": "指定对象的已核实编号，可省略改用 keyword"},
          "keyword": {"type": "string", "description": "对象名称，服务器仅查询本人权限内的数据"},
          "auto": {"type": "boolean", "description": "兼容旧请求，一律传false。即使用户本轮说打开也先显示确认卡，不自动跳转"},
          "use_attachments": {"type": "boolean", "description": "携带本轮已上传的文件"}},
          "required": ["target"]}, flows=("explain", "admin_ops"))
def prepare_ui_action(ctx: ToolContext, target: str, values: dict = None, object_id: str = "", keyword: str = "", auto: bool = False, use_attachments: bool = False):
    return prepare_action(ctx, target, values, object_id, keyword, auto, use_attachments)
