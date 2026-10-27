"""网络原题与题图证据链验证；仅临时库，网页内容使用明确的固定样例。"""
from contextlib import closing, ExitStack
import gc
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="web-question-") as folder, ExitStack() as cleanup:
        cleanup.callback(gc.collect)
        copied = Path(folder) / "copy.db"
        with closing(sqlite3.connect((ROOT / "backend/app/data/course_agent.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copied)) as target:
                source.backup(target)
        os.environ.update(DEBUG="false", DATABASE_URL="sqlite:///" + copied.as_posix())
        sys.path.insert(0, str(ROOT / "backend"))
        from app.database import SessionLocal, engine
        cleanup.callback(engine.dispose)
        from app.models.user import User
        from app.agent_st.agent import runtime, registry
        from app.agent_st.agent.context import ToolContext
        from app.agent_st.agent.tools import web_questions as questions
        from app.services import teacher_web_search as service
        from app.agent_st.agent.ui_actions import prepare_action
        with SessionLocal() as db:
            teacher = db.query(User).filter(User.username == "wangjg").one().user_id
        def context(role="teacher"):
            return ToolContext(store=SimpleNamespace(course_id="CCHYJTKE"), flow_id="explain", user_id=teacher,
                               extra={"role": role, "courseId": "CCHYJTKE", "message": "找一道完整题，不需要答案"})
        ctx = context()
        url = "https://example.com/course/queue"
        evidence = "如图所示，删除一个队头元素后 front 是多少？\n![循环队列](../queue.png)\nA. 0\nB. 1"
        plain = "队列依次加入 a、b，再删除一个元素，队头是什么？\nA. a\nB. b"
        page = "# 队列练习\n" + evidence + "\n\n" + plain
        invoke = lambda name, data, c=ctx: registry.execute(name, data, c)
        assert "error" in invoke("read_web_page", {"url": url})
        with patch.object(service, "search", return_value={"ok": True, "results": [{"url": url, "title": "队列练习"}]}), \
                patch.object(service, "fetch_page", return_value={"title": "队列练习", "content": page, "truncated": False}) as fetch:
            assert invoke("search_web", {"query": "队列 教学例题"})["ok"]
            assert "error" in invoke("read_web_page", {"url": "http://127.0.0.1/private"})
            assert "error" in invoke("read_web_page", {"url": "https://other.example.com/not-searched"})
            result = invoke("read_web_page", {"url": url})
            assert result["imageUrls"] == ["https://example.com/queue.png"]
            assert invoke("read_web_page", {"url": url}) == result and fetch.call_count == 1
        base = {"source_url": url, "title": "循环队列", "stem": "如图所示，删除一个队头元素后 front 是多少？", "evidence": evidence,
                "options": [{"label": "A", "text": "0"}, {"label": "B", "text": "1"}], "requires_image": True}
        def rejected(data):
            isolated = context(); isolated.turn = deepcopy(ctx.turn)
            return invoke("prepare_web_question", data, isolated)
        assert "error" in rejected(base)
        assert "error" in rejected({**base, "images": [{"url": "https://example.com/wrong.png"}]})
        assert "error" in rejected({**base, "stem": "编造题面和数据"})
        assert "error" in rejected({**base, "evidence": "无此原文"})
        image = invoke("prepare_web_question", {**base, "images": [{"url": "../queue.png", "alt": "循环队列示意图"}]})
        assert image["ok"] and image["question"]["images"][0]["url"] == "https://example.com/queue.png"
        simple = {"source_url": url, "title": "先进先出", "stem": plain.splitlines()[0], "evidence": plain,
                  "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}]}
        assert invoke("prepare_web_question", simple)["ok"]
        assert len([x for x in ctx.tool_log if x.get("kind") == "web_question"]) == 2
        # 用户实际故障：全角、Markdown 转义、空白和换行不同应仍匹配真实原文。
        original = "（ 2）在 n 个结点的顺序表中，算法的时间复杂度是 O\\(1\\) 的操作是（） 。\nA ．访问第 i 个结点（ 1≤ i≤ n）\nB ．删除第 i 个结点（ 1≤ i≤ n）"
        clean = "（2）在n个结点的顺序表中，算法的时间复杂度是O(1)的操作是（）。\nA.访问第i个结点（1<=i<=n）\nB.删除第i个结点（1<=i<=n）"
        local = context(); local.turn["web_question_pages"] = {url: {"title": "线性表", "content": original}}
        case = {"source_url": url, "title": "线性表", "stem": "在 n 个结点的顺序表中，算法的时间复杂度是 O(1) 的操作是（）。", "evidence": clean,
                "options": [{"label": "A", "text": "访问第i个结点（1<=i<=n）"}, {"label": "B", "text": "删除第i个结点（1<=i<=n）"}], "answer": "A"}
        result = invoke("prepare_web_question", case, local)
        assert result.get("ok") and result["question"]["answer"] == "", result
        invalid = context(); invalid.turn["web_question_pages"] = deepcopy(local.turn["web_question_pages"])
        for _ in range(3):
            result = invoke("prepare_web_question", {**case, "stem": case["stem"].replace("O(1)", "O(2)")}, invalid)
            assert "error" in result
        assert invalid.turn["web_question_exhausted"] and result["retryable"] is False
        assert "停止" in invoke("prepare_web_question", case, invalid)["error"]
        assert "未能核对" in questions.question_fallback(invalid.turn)
        assert "已整理" in questions.question_fallback(local.turn)
        from app.services.web_question_text import source_excerpt
        assert source_excerpt(original, clean.replace("O(1)", "O(2)")) is None
        assert questions._plain("a*b") != questions._plain("ab")
        print("[ok] 真实故障的转义/全角/空白等价匹配，未要求的答案隐藏，数据变更拒绝，三次失败停止")
        for role in ("student", "admin", ""):
            for name, data in (("read_web_page", {"url": url}), ("prepare_web_question", simple)):
                assert "error" in invoke(name, data, context(role))
        for flag in ("_skillTrial", "_customSkillSnapshot"):
            blocked = context();blocked.extra[flag] = True
            assert "error" in invoke("read_web_page", {"url": url}, blocked)
        # 图片列表来自原题片段，HTML 图片与相对路径可以识别，内网或执行协议排除。
        assert questions.images_in('<img src="./q.webp"><img src="javascript:bad()">', url) == ["https://example.com/course/q.webp"]
        print("[ok] 本轮来源限定、原文缓存、图文证据、缺图/伪造题图/改写拒绝、纯文字题及日志恢复")
        # 两次读取失败不能耗尽整个回合；第三个来源仍能成功，重复失败来源走缓存。
        switched = context()
        sources = [f"https://example.com/source-{i}" for i in range(6)]
        switched.turn["web_search_sources"] = dict.fromkeys(sources, "公开来源")
        with patch.object(service, "fetch_page", side_effect=[service.SearchFailure("读取失败"), service.SearchFailure("读取失败"),
                                                            {"title": "成功来源", "content": plain}]) as fetch:
            for source in sources[:2]:
                assert invoke("read_web_page", {"url": source}, switched)["retryable"]
                assert invoke("read_web_page", {"url": source}, switched)["retryable"]
            assert invoke("read_web_page", {"url": sources[2]}, switched)["content"] == plain
            assert fetch.call_count == 3
        # PDF 候选必须来自真实工作进程的分段；自动附该段截图和页码，不接受另一页图。
        from check_web_pdf import fixtures
        from app.services.web_pdf_worker import process_pdf
        native, _ = fixtures(Path(folder))
        pdf = process_pdf(native.read_bytes(), Path(folder) / "pdf-cache", max_pages=1)
        segment = pdf["pages"][0]["segments"][0]
        pdfctx = context(); pdfctx.turn["web_question_pages"] = {url: pdf}
        data = {"source_url": url, "title": "PDF队列题", "stem": "删除一个元素后，队头元素是什么？", "evidence": segment["text"]}
        result = invoke("prepare_web_question", data, pdfctx)
        assert result.get("ok") and result["question"]["sourcePage"] == 1, result
        assert result["question"]["images"][0]["url"] == segment["imageUrl"]
        invalid_pdf = context(); invalid_pdf.turn = deepcopy(pdfctx.turn)
        assert "error" in invoke("prepare_web_question", {**data, "images": [{"url": pdf["pages"][0]["previewUrl"]}]}, invalid_pdf)
        print("[ok] 失败来源在本轮继续切换、失败缓存，以及真实 PDF 分段的截图/页码关联和伪造图片拒绝")
        print("[ok] 学生/管理员/空角色/定制技能试用不能读取或整理网络原题")
        for role, target in (("teacher", "teacher.page.dashboard"), ("student", "student.page.dashboard"), ("admin", "admin.page.users")):
            scoped = context(role)
            result = prepare_action(scoped, target, auto=True)
            assert result.get("ok") and result["ui_action"]["auto"] is False, result
            assert "确认" in result["note"]
        print("[ok] 三端旧 auto=true 请求只产生待确认计划，不授权导航")


if __name__ == "__main__":
    main()
