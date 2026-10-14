"""
数据库连接与会话
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event
from .config import settings

# SQLite 连接（check_same_thread=False 是 SQLite 在多线程下必须的）
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
)

# 开启外键约束：SQLite 默认关闭，必须每个连接单独设置，否则外键不生效
@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns(engine):
    """仅 ADD COLUMN 的幂等补列（不改已有列/不删数据）。

    项目约定旧完整迁移已退役；此处只为「章目录 + 多 KP」「课程隔离」等
    新增列在已有库上可运行。删库重建仍是最干净路径。
    """
    from sqlalchemy import text

    # 表 → {列名: 列定义}。新增列只在这里登记，勿在别处散落 ALTER。
    want = {
        "resources": {
            "chapter_id": "VARCHAR(64) DEFAULT ''",
            "chapter": "VARCHAR(64) DEFAULT ''",
            "kp_ids": "TEXT DEFAULT '[]'",
        },
        "questions": {
            "chapter_id": "VARCHAR(64) DEFAULT ''",
            "chapter": "VARCHAR(64) DEFAULT ''",
            "kp_ids": "TEXT DEFAULT '[]'",
        },
        "graph_nodes": {
            "pos_x": "FLOAT",
            "pos_y": "FLOAT",
        },
        # 课程隔离：出题草稿补课程维度（存量行保持 NULL，由运维显式归属）
        "st_question_drafts": {
            "course_id": "VARCHAR(32)",
        },
        # 课程隔离：会话表补课程维度（存量 28 行曾回填默认课程，新行为 NULL）
        "chat_sessions": {
            "course_id": "VARCHAR(32)",
        },
    }
    with engine.connect() as conn:
        for table, cols in want.items():
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {r[1] for r in rows}
            if not existing:
                continue
            for col, ddl in cols.items():
                if col in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        conn.commit()


def init_db():
    """初始化数据库表。

    数据库结构的唯一事实来源是 models/ 的模型定义（面向删库重建）：
    create_all 会按当前模型建出完整结构。
    """
    from .models import user, course, graph, question, practice, ai, alert, intervention, checkin
    from .models import agent_st  # noqa: F401  智能出题草稿表
    from .models import user_course  # noqa: F401  用户-课程关联（多课程数据地基）
    from .models import tag  # noqa: F401  课程多标签（历史保留；产品语义已并入 KP）
    Base.metadata.create_all(bind=engine)
    _add_missing_columns(engine)

