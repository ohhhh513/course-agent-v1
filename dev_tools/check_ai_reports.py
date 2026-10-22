"""AI 报告课程/日期隔离、校验失败不归档及导出检查；仅写临时库副本。

不调用模型：模型真实生成另用 check_ui_report_api.py 验证。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    real = ROOT / "backend/app/data/course_agent.db"
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="ai-report-check-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        shutil.copy2(real, work / "copy.db")
        os.environ.update(DATABASE_URL="sqlite:///" + (work / "copy.db").as_posix(),
                          AGENT_DATA_DIR=str(work / "agent"), DEBUG="false")
        sys.path.insert(0, str(ROOT / "backend"))
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        from app.models.user import User
        from app.models.user_course import UserCourse
        from app.models.course import Course, Resource, ResourceProgress
        from app.models.graph import GraphNode
        from app.models.practice import AnswerRecord
        from app.models.question import Question
        from app.models.intervention import TeacherClassDashboard, Report
        from app.services.report_facts import collect_report_facts, make_scope, SHANGHAI
        from app.services.ai_learning_report import SECTION_TITLES, validate_analysis
        from app.routers.intervention import render_report_file

        with SessionLocal() as db:
            schema_before = db.connection().exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all()
            student = db.query(User).filter(User.username == "stu07").one()
            uid = student.user_id
            yesterday = datetime.now(SHANGHAI).date() - timedelta(days=1)
            early = datetime.combine(yesterday, datetime.min.time()).replace(hour=3)
            for course_id in ("REPORT_CHECK_A", "REPORT_CHECK_B"):
                db.add(Course(course_id=course_id, name=course_id))
                db.add(UserCourse(user_id=uid, course_id=course_id, role_in_course="student"))
                for number in (1, 2):
                    kp = f"{course_id}_K{number}"
                    db.add(GraphNode(id=kp, graph_type="knowledge", course_id=course_id,
                                     name=f"知识点{number}", chapter=f"第{number}章"))
                    db.add(Question(q_id=f"{course_id}_Q{number}", course_id=course_id,
                                    kp_id=kp, chapter=f"第{number}章", stem="仅临时库使用的范围检查题"))
                db.add(Resource(res_id=course_id + "_R", course_id=course_id, type="doc", title="范围检查资源",
                                chapter="第1章", kp_id=course_id + "_K1"))
            db.flush()
            for course_id, dates in (("REPORT_CHECK_A", [early, early + timedelta(hours=1), early + timedelta(hours=2)]),
                                     ("REPORT_CHECK_B", [early])):
                for index, when in enumerate(dates):
                    db.add(AnswerRecord(user_id=uid, course_id=course_id, q_id=course_id + "_Q1",
                                        kp_id=course_id + "_K1", is_correct=int(index == 2),
                                        created_at=when, duration_seconds=20))
            # 次日北京时间 01:00，应被昨日结束边界排除；另一章也必须排除。
            db.add(AnswerRecord(user_id=uid, course_id="REPORT_CHECK_A", q_id="REPORT_CHECK_A_Q1",
                                kp_id="REPORT_CHECK_A_K1", is_correct=0, created_at=early.replace(hour=17)))
            db.add(AnswerRecord(user_id=uid, course_id="REPORT_CHECK_A", q_id="REPORT_CHECK_A_Q2",
                                kp_id="REPORT_CHECK_A_K2", is_correct=0, created_at=early))
            db.add(ResourceProgress(user_id=uid, res_id="REPORT_CHECK_A_R", progress=90))
            db.add(ResourceProgress(user_id=uid, res_id="REPORT_CHECK_A_R", progress=5))
            for course_id, count in (("REPORT_CHECK_A", 5), ("REPORT_CHECK_B", 999)):
                db.add(TeacherClassDashboard(data_type="ai_daily_analysis", data_key=course_id,
                    data_json=json.dumps({"courseId": course_id, "studentId": uid, "daily": [{
                        "date": yesterday.isoformat(), "questionCount": count, "analyzedQuestionCount": 3,
                        "topicStatus": "course_terms", "topics": [{"kpId": course_id + "_K1", "questionCount": count,
                        "likelyDoubt": "对概念边界有疑惑"}],
                    }]}, ensure_ascii=False)))
            db.add(TeacherClassDashboard(data_type="exam_attempt", data_key="REPORT_CHECK_EXAM",
                data_json=json.dumps({"courseId": "REPORT_CHECK_A", "userId": uid, "paperId": "CHECK_PAPER",
                    "status": "finished", "finishedAt": early.replace(tzinfo=timezone.utc).isoformat(),
                    "result": {"score": 75, "totalScore": 100, "items": [
                        {"chapter": "第1章", "kpIds": ["REPORT_CHECK_A_K1"], "score": 50, "earnedScore": 50},
                        {"chapter": "第2章", "kpIds": ["REPORT_CHECK_A_K2"], "score": 50, "earnedScore": 25},
                    ]}})))
            db.commit()
            scope = make_scope("REPORT_CHECK_A", chapters=["第1章"], start_date=yesterday.isoformat(), end_date=yesterday.isoformat())
            data = collect_report_facts(db, student, scope, personal=True)
            facts = {f["id"]: f["text"] for f in data["facts"]}
            assert "实际提交 3 次" in facts["practice"] and "正确率 100.0%" in facts["practice"]
            assert "1 个组合答错至少两次" in facts["wrong"] and "1 个组合在期间最近作答已答对" in facts["wrong"]
            assert "90.0%" in facts["resources"]
            assert "提问 5 次" in facts["aiCoverage"] and "999" not in json.dumps(data, ensure_ascii=False)
            assert "得分 50/50" in facts["exam0"] and "75" not in facts["exam0"]
            assert len([k for k in facts if k.startswith("kp") and k[2:].isdigit()]) == 1
            combined = collect_report_facts(db, student, make_scope(
                "REPORT_CHECK_A", chapters=["第1章", "第2章"], kp_ids=["REPORT_CHECK_A_K1"],
                start_date=yesterday.isoformat(), end_date=yesterday.isoformat()), personal=True)
            assert "实际提交 3 次" in next(f["text"] for f in combined["facts"] if f["id"] == "practice")
            teacher = db.query(User).filter(User.username == "wangjg").one()
            aggregate = collect_report_facts(db, teacher, scope)
            assert "对概念边界有疑惑" not in json.dumps(aggregate, ensure_ascii=False)
            empty = collect_report_facts(db, student, make_scope("REPORT_CHECK_A", chapters=["第2章"], start_date=datetime.now(SHANGHAI).date().isoformat()), personal=True)
            assert "没有作答，正确率未知" in next(f["text"] for f in empty["facts"] if f["id"] == "practice")
            for options in ({"chapters": ["第99章"]}, {"kp_ids": ["REPORT_CHECK_B_K1"]}):
                try:
                    collect_report_facts(db, student, make_scope("REPORT_CHECK_A", **options), personal=True)
                    raise AssertionError("非法范围未拒绝")
                except HTTPException as exc:
                    assert exc.status_code == 400
            for options in ({"start_date": "not-a-date"}, {"start_date": "2026-02-02", "end_date": "2026-02-01"},
                            {"end_date": (datetime.now(SHANGHAI).date() + timedelta(days=1)).isoformat()}):
                try:
                    make_scope("REPORT_CHECK_A", **options)
                    raise AssertionError("非法日期未拒绝")
                except HTTPException as exc:
                    assert exc.status_code == 400
            assert db.connection().exec_driver_sql("SELECT sql FROM sqlite_master ORDER BY name").all() == schema_before
            print("PASS: 同一学生双课程隔离、多章节与知识点范围、北京时间边界、重复资源取优、错题纠正、章节试卷得分、无作答未知、教师摘要隐私；未改表")

            keys = ("scope", "snapshot", "mastery", "practice", "aiCoverage", "actions")
            response = {"sections": [{"key": key, "paragraphs": ["基于对应证据说明情况。"], "bullets": [], "evidenceIds": [ref]}
                                    for key, ref in zip(SECTION_TITLES, keys)]}
            sections = validate_analysis(json.dumps(response), data["facts"])
            for mode in ("missing", "duplicate", "unknown", "invented"):
                bad = deepcopy(response)
                if mode == "missing":
                    bad["sections"].pop()
                elif mode == "duplicate":
                    bad["sections"][-1] = bad["sections"][0]
                elif mode == "unknown":
                    bad["sections"][0]["evidenceIds"] = ["not-a-fact"]
                else:
                    bad["sections"][0]["paragraphs"] = ["正确率 987654.32%。"]
                try:
                    validate_analysis(json.dumps(bad), data["facts"])
                    raise AssertionError(mode)
                except ValueError:
                    pass
            print("PASS: 缺失部分、重复部分、不存在的依据、无依据数字均被拒绝")

            report = Report(report_id="CHECK_ONLY", title="检查报告", detail_json=json.dumps({"sections": sections, "meta": data["meta"]}, ensure_ascii=False))

            async def content(stream):
                return b"".join([chunk async for chunk in stream.body_iterator])

            html = asyncio.run(content(render_report_file(report, "html"))).decode("utf-8")
            assert "分析依据" in html and "当前快照" in html
            from docx import Document
            doc = Document(io.BytesIO(asyncio.run(content(render_report_file(report, "docx")))))
            assert "分析依据" in " ".join(p.text for p in doc.paragraphs)
            from pypdf import PdfReader
            pdf = PdfReader(io.BytesIO(asyncio.run(content(render_report_file(report, "pdf")))))
            assert "分析依据" in " ".join(p.extract_text() for p in pdf.pages)
            count = db.query(Report).count()
            print("PASS: HTML、DOCX、PDF 导出保留 AI 分析依据")

        with patch("app.services.daily_learning_analysis.start_scheduler", return_value=False), TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"username": "stu07", "password": "123456"}).json()["data"]
            headers = {"Authorization": "Bearer " + login["token"], "X-Course-Id": "REPORT_CHECK_A"}
            with patch("app.services.ai_learning_report._model_analysis", side_effect=HTTPException(502, "验证失败")):
                assert client.post("/api/v1/student/reports/generate", headers=headers).status_code == 502
            from types import SimpleNamespace
            with patch("app.services.ai_learning_report.get_settings", return_value=SimpleNamespace(llm_api_key="", llm_model="")):
                assert client.post("/api/v1/student/reports/generate", headers=headers).status_code == 503
            with SessionLocal() as db:
                assert db.query(Report).count() == count
        print("PASS: AI 失败、缺少模型配置不创建报告，不使用固定模板替代")
        engine.dispose()
    assert sha256(real.read_bytes()).hexdigest() == original
    print("PASS: 真实数据库 SHA256 未改变；所有测试数据仅在临时副本")


if __name__ == "__main__":
    main()
