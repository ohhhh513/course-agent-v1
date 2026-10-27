"""在内存对话存储上执行教师草稿试用，不创建正式会话和学习记录。"""
from copy import deepcopy
import uuid

from fastapi import HTTPException

from app.agent_st.agent.store import AgentStore


class TrialStore(AgentStore):
    def __init__(self, user_id, course_id, history):
        self.user_id, self.course_id = user_id, course_id
        self.messages = deepcopy(history)
        self.tool_log = []
        self.session_id = "TR" + uuid.uuid4().hex

    def ensure_session(self, session_id, flow_id):
        return self.session_id

    def add_message(self, session_id, role, content, tool_log=None):
        self.messages.append({"role": role, "content": content})

    def history(self, session_id, limit=12):
        return deepcopy(self.messages[-limit:])

    def set_last_tool_log(self, session_id, tool_log, draft_id=""):
        self.tool_log = deepcopy(tool_log)


def run_trial(spec, user_id, course_id, question, history):
    from app.agent_st.agent import llm, runtime, sdk_runner
    from app.agent_st.agent.config import get_settings
    if not llm.chat_available():
        raise HTTPException(503, "尚未配置可用模型，无法进行真实技能试用")
    context = {"role": "teacher", "courseId": course_id, "skillId": spec["id"],
               "_skillTrial": True, "_skillTrialRevision": spec["customRevision"],
               "_customSkillSnapshot": deepcopy(spec)}
    text, errors = [], []
    for event in runtime.run_turn(message=question, flow_id="explain", context=context,
                                  user_id=user_id, course_id=course_id,
                                  store=TrialStore(user_id, course_id, history)):
        if event.get("type") == "text":
            text.append(event.get("delta") or "")
        elif event.get("type") == "error":
            errors.append(event.get("message") or "试用失败")
    if errors or not "".join(text).strip():
        raise HTTPException(502, errors[0] if errors else "模型未返回试用回答，请稍后重试")
    actual_runtime = "sdk" if get_settings().agent_runtime == "sdk" and sdk_runner.available() else "legacy"
    return {"text": "".join(text), "revision": spec["customRevision"], "runtime": actual_runtime}
