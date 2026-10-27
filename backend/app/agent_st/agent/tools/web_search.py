"""教师只读联网备课工具；与本地学情、学生定制技能隔离。"""
from app.agent_st.agent.registry import role_of, tool
from app.config import settings
from app.services import teacher_web_search as service
from app.services.web_question_history import current_history, source_url


@tool(
    name="search_web",
    description=("教师联网搜索公开教学资料、案例和技术文档。明确要求联网、查最新资料或外部备课资源时使用；"
                 "本课普通知识优先查课程资料。只传简短公开主题，不得包含学生姓名、学号、学情、完整对话或附件。"
                 "返回标题、摘要和真实来源链接，不读取个人学情，也不发布资源或修改课程。"),
    parameters={"type": "object", "properties": {"query": {"type": "string", "minLength": 2, "maxLength": 128,
                 "description": "不含任何学生标识或私有数据的公开教学主题"}}, "required": ["query"], "additionalProperties": False},
    flows=("explain",), roles=("teacher",),
)
def search_web(ctx, query: str):
    if role_of(ctx) != "teacher" or ctx.extra.get("_skillTrial") or ctx.extra.get("_customSkillSnapshot"):
        return {"error": "联网备课仅对教师正式教学对话开放，定制技能试用不能使用。"}
    course_id = str(ctx.store.course_id or "")
    if not course_id or (ctx.extra.get("courseId") and ctx.extra["courseId"] != course_id):
        return {"error": "课程上下文无效，请重新选择任教课程。"}
    try:
        query = service.validate_query(query, ctx.user_id, course_id)
        history = current_history(ctx)
        calls = ctx.turn.get("web_search_calls", 0)
        limit = max(1, min(3, settings.TEACHER_WEB_SEARCH_MAX_CALLS))
        if calls >= limit:
            return {"error": f"本轮联网搜索已达 {limit} 次上限，请基于已有结果回答，或下一轮补充搜索。"}
        ctx.turn["web_search_calls"] = calls + 1
        ctx.turn["web_search_query"] = query
        result = service.search(query)
        sources = ctx.turn.setdefault("web_search_sources", {})
        for item in result["results"]:
            sources[item["url"].split("#", 1)[0]] = item["title"]
            item["previouslyUsedQuestions"] = sum(source_url(q.get("sourceUrl", "")) == source_url(item["url"]) for q in history.questions)
        result["recentQuestions"] = history.summaries()
        result["repeatRequested"] = history.allow_repeat
        result["selectionNotice"] = "默认找未提供过的新题，避开 recentQuestions 中的题干；同来源仍可能有其他新题，不排除整本 PDF。只有明确重看/讲解原题时才可复用。不要把这些本地历史加入对外搜索关键词。"
        if result["results"]:
            ctx.turn["web_search_succeeded"] = True
        return result
    except service.SearchFailure as exc:
        return {"error": str(exc)}
