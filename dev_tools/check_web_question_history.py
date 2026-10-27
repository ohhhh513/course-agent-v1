"""近期联网题卡去重：真实库副本、旧 JSON 兼容、题意/题图差异与上下文隔离。"""
from contextlib import closing, ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
import gc
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="question-history-") as folder, ExitStack() as cleanup:
        cleanup.callback(gc.collect)
        work = Path(folder)
        copied = work / "copy.db"
        with closing(sqlite3.connect((ROOT / "backend/app/data/course_agent.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copied)) as target:
                source.backup(target)
                schema = target.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        shutil.copy2(ROOT / "backend/app/data/st/rag.db", work / "rag.db")
        os.environ.update(DEBUG="false", DATABASE_URL="sqlite:///" + copied.as_posix(),
                          AGENT_DATA_DIR=str(work / "st"), RAG_DB_PATH=str(work / "rag.db"), JWT_SECRET="history-copy-check")
        sys.path.insert(0, str(ROOT / "backend"))
        from app.config import settings
        from app.database import SessionLocal, engine
        cleanup.callback(engine.dispose)
        from app.models.ai import ChatSession, ChatMessage
        from app.models.course import Course
        from app.models.user import User
        from app.models.user_course import UserCourse
        from app.middleware.auth import hash_password
        from app.agent_st.agent.context import ToolContext
        from app.services import web_question_history as history
        from app.services.teacher_web_search import SearchFailure
        text = {"id": "OLD", "title": "旧标题", "stem": "（10）队列依次加入 a、b，再删除一个元素，队头是什么？", "sourceUrl": "https://example.com/queue",
                "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}], "images": []}
        variant = {**text, "id": "NEW", "title": "完全不同的标题", "stem": "队列依次加入a、b，再删除一个元素，队头是什么?",
                   "sourceUrl": "https://other.example.com/mirror", "options": [{"label": "A", "text": "b"}, {"label": "B", "text": "a"}]}
        assert history.same_question(text, variant)
        assert not history.same_question(text, {**variant, "stem": variant["stem"].replace("a、b", "a、b、c")})
        assert not history.same_question(text, {**variant, "options": [{"label": "A", "text": "c"}]})
        assert not history.same_question({**text, "options": [{"label": "A", "text": "(1)"}]}, {**text, "options": [{"label": "A", "text": "(2)"}]})
        assert not history.same_question({**text, "stem": "(1)+(2)的计算结果是什么？"}, {**text, "stem": "(2)+(2)的计算结果是什么？"})
        assert history.same_question(text, {**text, "options": [{"label": "A", "text": "A．a"}, {"label": "B", "text": "B．b"}]})
        assert history.normalized("rear_ptr") != history.normalized("rear__ptr")
        assert history.normalized("（1）元素个数是________。") == history.normalized("元素个数是____")
        short = {**text, "stem": "如图所示，出队后的队头元素是什么？", "requiresImage": True, "images": [{"url": "https://example.com/graph1.png"}]}
        assert not history.same_question(short, {**short, "images": [{"url": "https://example.com/graph2.png"}]})
        assert history.same_question(short, deepcopy(short))
        # 同一 PDF 换缓存目录仍是同一原图；修改图形或数字后不能仅凭原页坐标合并。
        from PIL import Image
        with patch.object(settings, "FRONTEND_DIR", work):
            urls = ["/resources/web-question-pdfs/" + c * 64 + "/question-28-1.png" for c in "abc"]
            for index, url in enumerate(urls):
                path = work / url.lstrip("/"); path.parent.mkdir(parents=True, exist_ok=True)
                image = Image.new("RGB", (80, 40), "white" if index < 2 else "red"); image.save(path); image.close()
            pdf = {**short, "stem": "图3-21所示队列，front=15、rear=32，元素个数是____。", "sourceUrl": "https://example.com/book.pdf",
                   "sourcePage": 28, "sourceRegion": [0, 100, 500, 300], "viewKind": "question_crop", "images": [{"url": urls[0]}]}
            assert history.same_question(pdf, {**pdf, "images": [{"url": urls[1]}]})
            different = {**pdf, "images": [{"url": urls[2]}]}
            assert not history.same_question(pdf, different)
            assert not history.same_question(pdf, {**different, "stem": pdf["stem"].replace("32", "33")})
        print("[ok] 标题/UUID/题号/空白/选项顺序无关，跨来源同题识别；不同条件、选项与题图保持不同")
        for message in ("再看上一道题", "再找上一道题", "再给我看一次上一题", "讲解上一题", "把刚才那道题的答案显示一下", "重新显示原题", "找同一道题"):
            assert history.repeat_requested(message), message
        for message in ("来个有图的队列的题", "再来一道题", "换一道同类型的题", "不要重复上一题", "上一题看过了，再找一道题"):
            assert not history.repeat_requested(message), message
        with SessionLocal() as db:
            for uid in ("WH_TEACHER_A", "WH_TEACHER_B"):
                db.add(User(user_id=uid, username=uid.lower(), name="去重教师样例", role="teacher", password=hash_password("copy-test")))
            for cid in ("WH_COURSE_A", "WH_COURSE_B"):
                db.add(Course(course_id=cid, name="去重课程样例"))
                db.add(UserCourse(user_id="WH_TEACHER_A", course_id=cid, role_in_course="teacher"))
            db.add(UserCourse(user_id="WH_TEACHER_B", course_id="WH_COURSE_A", role_in_course="teacher"))
            db.flush()
            for sid, uid, cid in (("WH_SESSION_A", "WH_TEACHER_A", "WH_COURSE_A"), ("WH_SESSION_B", "WH_TEACHER_A", "WH_COURSE_A"),
                                  ("WH_OTHER_COURSE", "WH_TEACHER_A", "WH_COURSE_B"), ("WH_OTHER_USER", "WH_TEACHER_B", "WH_COURSE_A")):
                db.add(ChatSession(session_id=sid, user_id=uid, course_id=cid))
            db.flush()
            for sid, qid, age in (("WH_SESSION_A", "OWN", 0), ("WH_SESSION_B", "OWN_NEW_CHAT", 0),
                                  ("WH_SESSION_A", "OLD_31_DAYS", 31), ("WH_OTHER_COURSE", "CROSS_COURSE", 0), ("WH_OTHER_USER", "OTHER_USER", 0)):
                db.add(ChatMessage(session_id=sid, role="ai", content="题卡已整理", created_at=datetime.utcnow()-timedelta(days=age),
                                   tool_log=json.dumps([{"kind": "web_question", "question": {**text, "id": qid}}], ensure_ascii=False)))
            for raw in ('[{"kind":"web_question",', '{"kind":"web_question"}', '[null,{"kind":"web_question","question":{"stem":4}}]'):
                db.add(ChatMessage(session_id="WH_SESSION_A", role="ai", tool_log=raw))
            db.commit()
        recent = history.load_recent_questions("WH_TEACHER_A", "WH_COURSE_A")
        assert {q["id"] for q in recent} == {"OWN", "OWN_NEW_CHAT"}, recent
        context = ToolContext(store=SimpleNamespace(course_id="WH_COURSE_A"), user_id="WH_TEACHER_A", flow_id="explain", extra={"message": "再来一道题"})
        loaded = history.current_history(context)
        assert loaded.duplicate(variant) and loaded.summaries()[0]["stem"]
        assert history.current_history(context) is loaded
        loaded.remember({**text, "stem": "一轮中的新题也不能发送两次。"})
        assert loaded.duplicate({**text, "stem": "一轮中的新题也不能发送两次。"})
        print("[ok] 同教师课程跨会话保留近期题卡、30天窗口、他人/课程隔离、坏JSON跳过及同轮记录")
        from app.agent_st.agent import registry
        from app.agent_st.agent.tools import web_questions, web_search
        from app.services import teacher_web_search as service
        def ctx(message="再来一道队列题", role="teacher"):
            return ToolContext(store=SimpleNamespace(course_id="WH_COURSE_A"), user_id="WH_TEACHER_A", flow_id="explain",
                               extra={"role": role, "courseId": "WH_COURSE_A", "message": message})
        url = text["sourceUrl"]
        evidence = text["stem"] + "\nA. a\nB. b"
        other = "队列依次加入 c、d，再删除一个元素，队头是什么？\nA. c\nB. d"
        data = {"source_url": url, "title": "换了标题的旧题", "stem": variant["stem"], "evidence": evidence, "options": variant["options"]}
        turn = ctx(); turn.turn["web_search_sources"] = {url: "测试原文"}
        with patch.object(service, "fetch_page", return_value={"title": "测试原文", "content": evidence + "\n\n" + other}):
            response = registry.execute("read_web_page", {"url": url}, turn)
        assert response["recentQuestions"] and not response["repeatRequested"]
        for _ in range(3):
            duplicate = registry.execute("prepare_web_question", data, turn)
            assert duplicate.get("duplicate") and duplicate["retryable"], duplicate
        assert not turn.turn.get("web_question_failures") and not turn.turn.get("web_question_count")
        new = {**data, "title": "另一道队列题", "stem": other.splitlines()[0], "evidence": other,
               "options": [{"label": "A", "text": "c"}, {"label": "B", "text": "d"}]}
        assert registry.execute("prepare_web_question", new, turn).get("ok")
        assert registry.execute("prepare_web_question", new, turn).get("duplicate")
        exhausted = ctx(); exhausted.turn["web_question_pages"] = deepcopy(turn.turn["web_question_pages"])
        for _ in range(4):
            duplicate = registry.execute("prepare_web_question", data, exhausted)
        assert duplicate["retryable"] is False and exhausted.turn["web_question_exhausted"]
        assert "尚未提供" in web_questions.question_fallback(exhausted.turn)
        repeat = ctx("再看上一道题"); repeat.turn["web_question_pages"] = deepcopy(turn.turn["web_question_pages"])
        assert registry.execute("prepare_web_question", data, repeat).get("ok")
        assert registry.execute("prepare_web_question", data, repeat).get("duplicate")
        with patch.object(service, "search", return_value={"ok": True, "results": [{"url": url, "title": "原来源"}]}) as remote:
            result = registry.execute("search_web", {"query": "队列 例题"}, ctx())
            assert result["recentQuestions"] and result["results"][0]["previouslyUsedQuestions"] == 2
            assert remote.call_args.args == ("队列 例题",) and not remote.call_args.kwargs
        pdf_url = "https://example.com/book.pdf"
        old_pdf = {**text, "sourceUrl": pdf_url, "sourcePage": 1, "requiresImage": True, "images": [{"url": urls[0]}]}
        old_segment = {"text": evidence, "imageUrl": urls[0], "pageNumber": 1, "bounds": [0, 0, 500, 200], "viewKind": "question_crop"}
        fresh_segment = {"text": other, "imageUrl": urls[2], "pageNumber": 1, "bounds": [0, 200, 500, 400], "viewKind": "question_crop"}
        page = {"pageNumber": 1, "method": "text", "previewUrl": urls[0], "segments": [old_segment, fresh_segment]}
        pdf = {"title": "同页多题", "sourceUrl": pdf_url, "documentType": "pdf", "pageCount": 1, "content": evidence+"\n"+other, "truncated": False, "pages": [page]}
        pdf_ctx = ctx(); pdf_ctx.turn.update(web_question_history=history.QuestionHistory([old_pdf]), web_question_pages={pdf_url: pdf}, web_search_sources={pdf_url: "同页多题"})
        filtered = registry.execute("read_web_page", {"url": pdf_url}, pdf_ctx)
        assert filtered["previouslyUsedCandidates"] == 1 and filtered["pages"][0]["segments"] == [fresh_segment]
        fresh_pdf = {**old_pdf, "stem": new["stem"], "options": new["options"], "images": [{"url": urls[2]}]}
        pdf_ctx.turn["web_question_history"].remember(fresh_pdf)
        cached = registry.execute("read_web_page", {"url": pdf_url}, pdf_ctx)
        assert cached["pages"] == [] and cached["previouslyUsedCandidates"] == 2
        pdf["pageCount"] = 4; pdf_ctx.turn.update(web_pdf_pages=4, web_page_calls=1)
        page2 = {**page, "pageNumber": 2, "segments": [{**fresh_segment, "text": "另一个文件页中的新队列题目。", "pageNumber": 2}]}
        with patch.object(service, "fetch_page", return_value={**pdf, "pages": [page2], "renderedPages": 1}) as fetch:
            extra = registry.execute("read_web_page", {"url": pdf_url+"#page=2"}, pdf_ctx)
            assert extra["pages"][0]["pageNumber"] == 2 and fetch.call_args.kwargs["max_pdf_pages"] == 1
            assert pdf_ctx.turn["web_pdf_pages"] == 5 and pdf_ctx.turn["web_page_calls"] == 1
            registry.execute("read_web_page", {"url": pdf_url+"#page=2"}, pdf_ctx)
            assert fetch.call_count == 1
            assert "error" in registry.execute("read_web_page", {"url": pdf_url+"#page=99"}, pdf_ctx)
        for role in ("student", "admin"):
            with patch.object(history, "load_recent_questions") as reader:
                assert "error" in registry.execute("prepare_web_question", data, ctx(role=role)) and not reader.called
        with patch.object(settings, "TEACHER_WEB_QUESTION_DEDUP_ENABLED", False), patch.object(history, "load_recent_questions") as reader:
            disabled = ctx(); disabled.turn["web_question_pages"] = deepcopy(turn.turn["web_question_pages"])
            assert registry.execute("prepare_web_question", data, disabled).get("ok") and not reader.called
        print("[ok] 实际工具：重复不计原文错误、继续选新题、同轮去重、显式重看、有界终止、PDF同页筛选及缓存刷新")
        print("[ok] 历史不拼入外发查询、学生/管理员无读取权限、配置关闭可回退")
        from concurrent.futures import ThreadPoolExecutor
        concurrent = ctx(); concurrent.turn["web_question_pages"] = deepcopy(turn.turn["web_question_pages"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: registry.execute("prepare_web_question", new, concurrent), range(2)))
        assert sum(bool(r.get("ok")) for r in responses) == 1 and sum(bool(r.get("duplicate")) for r in responses) == 1
        assert concurrent.turn["web_question_count"] == 1
        from app.agent_st.agent import sdk_runner, llm
        adapter = ctx(); adapter.turn["web_question_pages"] = deepcopy(turn.turn["web_question_pages"])
        events = []
        result = json.loads(asyncio.run(sdk_runner._make_invoker("prepare_web_question", adapter, events.append)(None, json.dumps(data))))
        assert result.get("duplicate") and [e["type"] for e in events] == ["tool_start", "tool_end"]
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"username": "wh_teacher_a", "password": "copy-test"})
            assert login.status_code == 200
            headers = {"Authorization": "Bearer " + login.json()["data"]["token"].removeprefix("Bearer "), "X-Course-Id": "WH_COURSE_A"}
            results = iter([("search_web", {"query": "队列 例题"}), ("read_web_page", {"url": url}),
                            ("prepare_web_question", data), ("prepare_web_question", new), (None, None)])
            observed = []
            def model(messages, tools, on_text_delta=None, **kwargs):
                if messages[-1]["role"] == "tool":
                    observed.append(json.loads(messages[-1]["content"]))
                name, arguments = next(results)
                if name:
                    return {"content": "", "tool_calls": [{"id": "tool_"+str(len(observed)), "name": name, "arguments": json.dumps(arguments)}]}
                content = "已整理另一道队列题。"
                if on_text_delta:
                    on_text_delta(content)
                return {"content": content, "tool_calls": []}
            with patch.object(llm, "chat_available", return_value=True), patch.object(llm, "complete_stream", side_effect=model), \
                    patch.object(service, "search", return_value={"ok": True, "results": [{"url": url, "title": "测试来源"}]}), \
                    patch.object(service, "fetch_page", return_value={"title": "测试来源", "content": evidence+"\n\n"+other}):
                response = client.post("/api/v1/ai/chat/stream", headers=headers, json={"question": "再来一道队列题", "skillId": "web_research"})
            assert response.status_code == 200 and "已整理另一道" in response.text and "event: done" in response.text
            assert any(r.get("duplicate") for r in observed) and observed[-1].get("ok")
        print("[ok] SDK适配、并发同轮只发一次、教师真实登录及SSE运行循环拦旧题后继续生成新题（模型/来源固定样例）")
        with patch.object(history, "SessionLocal", side_effect=history.SQLAlchemyError("private upstream detail")):
            try:
                history.load_recent_questions("WH_TEACHER_A", "WH_COURSE_A")
                raise AssertionError("query failure swallowed")
            except SearchFailure as exc:
                assert "尚未完成去重" in str(exc) and "private" not in str(exc)
        with SessionLocal() as db:
            for i in range(201):
                db.add(ChatMessage(session_id="WH_SESSION_B", role="ai", content="题卡已整理",
                                   tool_log=json.dumps([{"kind": "web_question", "question": {**text, "id": str(i)}}], ensure_ascii=False)))
            db.commit()
        recent = history.load_recent_questions("WH_TEACHER_A", "WH_COURSE_A")
        assert len(recent) == 200 and recent[0]["id"] == "200" and recent[-1]["id"] == "1"
        with closing(sqlite3.connect(copied)) as db:
            assert schema == db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        print("[ok] 最近200条边界、查询失败明确报错、库结构不变；仅使用临时副本")
        from app.services.web_pdf_worker import candidate_pages
        body = "队列的基本操作图1\n" + "队列 "*40 + "\n（1）初始化\n（2）入队\n（3）出队"
        exercise = "队列判断题\n（1）如图2，执行出队后队头是什么？\n（2）队列长度是____。"
        assert candidate_pages([body, exercise], "队列 习题", max_pages=1) == [1]
        assert candidate_pages([body, exercise], "队列 习题", page_hint=1, max_pages=1) == [0]
        print("[ok] 真正习题页优先于高频关键词正文页，指定文件页码优先")


if __name__ == "__main__":
    main()
