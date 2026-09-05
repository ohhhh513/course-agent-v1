"""
种子数据脚本 —— 入口
将 mock_data.py 的数据完整写入数据库，保证前后端结构一致。

灌库顺序:
  1. 公共数据（无 user_id）: 账号、班级、课程、图谱、资源、题库、模板、报告
  2. Transaction（有 user_id 归属）: 每学生独立 LearningPath、AnswerRecord、
     PracticeSession、Alert、Intervention、ChatSession、ChatMessage
  3. 班级级 Dashboard 聚合数据

运行: 应用启动时自动执行  或  python -m app.seed.seed_data
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.database import SessionLocal, engine, Base
from app.middleware.auth import hash_password
from app.models.user import User, ClassInfo, TeacherClass
from app.models.course import Course, Resource
from app.models.graph import GraphNode, GraphLink, KpDetail, LearningPath
from app.models.question import Question
from app.models.practice import PracticeSession, AnswerRecord
from app.models.ai import ChatSession, ChatMessage
from app.models.alert import Alert
from app.models.intervention import (
    Intervention, InterventionTemplate, Report, TeacherClassDashboard,
)
from .mock_data import (
    DEFAULT_ACCOUNTS,
    MOCK_GRAPH_NODES, MOCK_GRAPH_LINKS, MOCK_KP_DETAIL,
    MOCK_RESOURCES, MOCK_QUESTIONS,
    MOCK_LEARNING_PATHS,
    MOCK_ANSWER_RECORDS,
    MOCK_PRACTICE_SESSIONS,
    MOCK_CHAT_SESSIONS, MOCK_CHAT_MESSAGES,
    MOCK_ALERTS, MOCK_INTERVENTIONS,
    MOCK_TEMPLATES, MOCK_REPORTS,
    DASHBOARD_DATA,
)


def run_seed():
    db = SessionLocal()
    try:
        if db.query(User).first():
            print("[seed] 数据库已有数据，跳过")
            return

        print("[seed] 开始写入种子数据...")

        # =========================================================
        # 1. 账号（12 学生 + 1 老师）
        # =========================================================
        for acct in DEFAULT_ACCOUNTS:
            db.add(User(
                user_id=acct["user_id"], username=acct["username"],
                password=hash_password(acct["password"]),
                name=acct["name"], role=acct["role"], avatar_char=acct["name"][0],
                student_no=acct.get("student_no", ""),
                class_name=acct.get("class_name", ""),
                title=acct.get("title", ""), dept=acct.get("dept", ""),
            ))
        print(f"  -> {len(DEFAULT_ACCOUNTS)} 账号")

        # 班级
        db.add_all([
            ClassInfo(class_id="CL2301", name="计算机 2301 班", student_count=12),
            ClassInfo(class_id="CL2302", name="计算机 2302 班", student_count=45),
            ClassInfo(class_id="CL2303", name="软件工程 2301 班", student_count=38),
        ])
        db.add_all([
            TeacherClass(teacher_user_id="T100286", class_id="CL2301",
                         class_name="计算机 2301 班", student_count=12),
            TeacherClass(teacher_user_id="T100286", class_id="CL2302",
                         class_name="计算机 2302 班", student_count=45),
            TeacherClass(teacher_user_id="T100286", class_id="CL2303",
                         class_name="软件工程 2301 班", student_count=38),
        ])

        # 课程
        db.add(Course(
            course_id="C2026DS001", name="数据结构与算法", code="CS20301",
            term="2026 春季学期", teacher="李文博", credit=4,
            chapters=8, knowledge_points=25, resources=132, questions=860,
        ))

        # =========================================================
        # 2. 图谱公共数据
        # =========================================================
        for n in MOCK_GRAPH_NODES:
            db.add(GraphNode(**n))
        for l in MOCK_GRAPH_LINKS:
            db.add(GraphLink(**l))
        db.add(KpDetail(**MOCK_KP_DETAIL))
        print(f"  -> graph: {len(MOCK_GRAPH_NODES)} nodes, "
              f"{len(MOCK_GRAPH_LINKS)} links")

        # =========================================================
        # 3. 资源 & 题库
        # =========================================================
        for r in MOCK_RESOURCES:
            db.add(Resource(**r))
        for q in MOCK_QUESTIONS:
            db.add(Question(**q))
        print(f"  -> resources: {len(MOCK_RESOURCES)}, "
              f"questions: {len(MOCK_QUESTIONS)}")

        # =========================================================
        # 4. Transaction 数据（按 user_id 归属）
        # =========================================================

        # 4.1 每学生独立 LearningPath（25 × 12 = 300 条）
        for lp in MOCK_LEARNING_PATHS:
            db.add(LearningPath(**lp))
        print(f"  -> learning_paths: {len(MOCK_LEARNING_PATHS)}")

        # 4.2 答题记录（12 学生 × 15-25 条 ≈ 195 条）
        for ar in MOCK_ANSWER_RECORDS:
            db.add(AnswerRecord(**ar))
        print(f"  -> answer_records: {len(MOCK_ANSWER_RECORDS)}")

        # 4.3 练习会话（12 学生 × 2-4 条 ≈ 38 条）
        for ps in MOCK_PRACTICE_SESSIONS:
            db.add(PracticeSession(**ps))
        print(f"  -> practice_sessions: {len(MOCK_PRACTICE_SESSIONS)}")

        # 4.4 预警（全部带 user_id 归属）
        for a in MOCK_ALERTS:
            db.add(Alert(**a))
        print(f"  -> alerts: {len(MOCK_ALERTS)}")

        # 4.5 干预
        for iv in MOCK_INTERVENTIONS:
            db.add(Intervention(**iv))
        print(f"  -> interventions: {len(MOCK_INTERVENTIONS)}")

        # 4.6 AI 对话会话 & 消息
        for cs in MOCK_CHAT_SESSIONS:
            db.add(ChatSession(**cs))
        for cm in MOCK_CHAT_MESSAGES:
            db.add(ChatMessage(**cm))
        print(f"  -> chat_sessions: {len(MOCK_CHAT_SESSIONS)}, "
              f"chat_messages: {len(MOCK_CHAT_MESSAGES)}")

        # =========================================================
        # 5. 模板 & 报告（班级级）
        # =========================================================
        for tpl in MOCK_TEMPLATES:
            db.add(InterventionTemplate(**tpl))
        for r in MOCK_REPORTS:
            db.add(Report(**r))

        # =========================================================
        # 6. Dashboard 班级级聚合数据（JSON）
        # =========================================================
        for dt, cid, dkey, jdata in DASHBOARD_DATA:
            db.add(TeacherClassDashboard(
                class_id=cid, data_type=dt, data_key=dkey,
                data_json=json.dumps(jdata, ensure_ascii=False),
            ))
        print(f"  -> dashboards: {len(DASHBOARD_DATA)}")

        db.commit()
        print("[seed] ✅ 种子数据写入完成")
    except Exception as e:
        db.rollback()
        print(f"[seed] ❌ 写入失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    run_seed()
