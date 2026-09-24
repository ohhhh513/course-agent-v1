"""
种子数据脚本 —— 入口
将 mock_data.py 的数据完整写入数据库，保证前后端结构一致。

灌库顺序:
  1. 公共数据（无 user_id）: 账号、班级、课程、图谱、资源、题库、模板、报告
  2. Transaction（有 user_id 归属）: PracticeSession、Intervention、
     ChatSession、ChatMessage
  3. 班级级 Dashboard 聚合数据

不含 LearningPath：学习路径由图谱派生，且必须在图谱扩展为 9 章之后生成，
所以交给启动引导 bootstrap.ensure_learning_paths()（见 services/learning_path.py）。

运行: 应用启动时自动执行  或  python -m app.seed.seed_data
"""
import json
import sys
from pathlib import Path

import secrets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.database import SessionLocal, engine, Base
from app.middleware.auth import hash_password
from app.models.user import User, ClassInfo, TeacherClass
from app.models.course import Course
from app.models.graph import GraphNode, GraphLink, KpDetail
from app.models.question import Question  # noqa: F401  （题库由 bootstrap.import_questions 导入，seed 不灌）
from app.models.user_course import UserCourse
from app.models.intervention import InterventionTemplate
from .mock_data import (
    DEFAULT_ACCOUNTS,
    MOCK_GRAPH_NODES, MOCK_GRAPH_LINKS, MOCK_KP_DETAIL,
    MOCK_TEMPLATES,
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
            # 成员归属：所有种子账号加入默认课程（成员校验的数据来源，多课程地基）
            db.add(UserCourse(
                user_id=acct["user_id"], course_id="C2026DS001",
                role_in_course=acct["role"],
            ))
        print(f"  -> {len(DEFAULT_ACCOUNTS)} 账号（含默认课程归属）")

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

        # 课程（空课起点：章节/知识点/资源计数随真实使用增长；邀请码供学生凭码加入）
        _INV = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        _invite = "".join(secrets.choice(_INV) for _ in range(8))
        db.add(Course(
            course_id="C2026DS001", name="数据结构与算法", code="CS20301",
            term="2026 春季学期", teacher="李文博", credit=4,
            chapters=0, knowledge_points=0, resources=0, questions=0,
            invite_code=_invite, owner_id="T100286",
        ))
        print(f"  -> course: C2026DS001（邀请码 {_invite}）")
        # 先落库父表（用户/班级/课程），避免后续 FK 子表先于父表插入导致外键失败
        db.flush()

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
        # ---------------------------------------------------------
        # 资源：**不再灌入任何种子资源**（含历史占位资源）——资源一律由
        # 教师通过「资源管理 → 上传」添加，这是既定的真实流程约定。
        # 题库：由 bootstrap.import_questions() 从 after_class.json 导入
        # （KHD 前缀 228 题），不在 seed 内。
        # =========================================================

        # =========================================================
        # 4. Transaction 数据 —— 全部不再灌入（seed 降级 · Step 7）
        # ---------------------------------------------------------
        # 以下演示/人设数据已全部移除，系统数据只来自真实使用：
        #   - 假练习会话（MOCK_PRACTICE_SESSIONS）
        #   - 假 AI 答疑会话与消息（MOCK_CHAT_*）
        #   - 假干预记录（MOCK_INTERVENTIONS）
        # 学习路径仍由 bootstrap.ensure_learning_paths() 按图谱派生；
        # 预警/错题本/掌握率等指标由真实答题与资源进度驱动（初始为 0 属正常）。
        # =========================================================

        # =========================================================
        # 5. 干预建议模板（功能配置，非演示数据）
        # =========================================================
        for tpl in MOCK_TEMPLATES:
            db.add(InterventionTemplate(**tpl))
        print(f"  -> intervention_templates: {len(MOCK_TEMPLATES)}")

        db.commit()
        print("[seed] 种子数据写入完成（已降级：仅账号/归属/课程/班级/图谱/模板）")
    except Exception as e:
        db.rollback()
        print(f"[seed] 写入失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    run_seed()
