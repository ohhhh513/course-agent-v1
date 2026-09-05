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
    Base.metadata.create_all(bind=engine)
