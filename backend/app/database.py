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


def init_db():
    """初始化数据库表"""
    from .models import user, course, graph, question, practice, ai, alert, intervention, checkin
    from .models import agent_st  # noqa: F401  智能出题草稿表
    Base.metadata.create_all(bind=engine)
    _migrate()


def _add_col(conn, table: str, col: str, ddl: str) -> None:
    """给已存在的表补列（SQLite 无 ADD COLUMN IF NOT EXISTS，用 PRAGMA 守卫，幂等）"""
    from sqlalchemy import text
    cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
    if col not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _migrate():
    """agent_st 集成的列迁移：兼容已有旧库（create_all 不会给旧表加列）"""
    with engine.connect() as conn:
        _add_col(conn, "chat_sessions", "flow_id", "VARCHAR(16) DEFAULT 'explain'")
        _add_col(conn, "chat_messages", "tool_log", "TEXT DEFAULT '[]'")
        _add_col(conn, "chat_messages", "draft_id", "VARCHAR(32) DEFAULT ''")
        _add_col(conn, "questions", "figure_json", "TEXT")
        _add_col(conn, "questions", "has_image", "BOOLEAN DEFAULT 0")
        conn.commit()
