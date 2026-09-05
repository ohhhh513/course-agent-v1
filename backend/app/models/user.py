"""
用户相关模型
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True, index=True)  # S20260317 / T100286
    username = Column(String(64), unique=True, nullable=False, index=True)
    password = Column(String(256), nullable=False)  # bcrypt hash

    name = Column(String(64), nullable=False)
    role = Column(String(16), nullable=False)  # student / teacher
    avatar_char = Column(String(4), default="")
    avatar_color = Column(String(32), default="")

    # 学生字段
    student_no = Column(String(32), default="")
    class_name = Column(String(64), default="")

    # 教师字段
    title = Column(String(32), default="")       # 副教授
    dept = Column(String(128), default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 教师与班级的关联
    teacher_classes = relationship("TeacherClass", back_populates="teacher")


class ClassInfo(Base):
    """班级（学生端用于 className，教师端用于 classes）"""
    __tablename__ = "classes"

    class_id = Column(String(32), primary_key=True)  # CL2301
    name = Column(String(128), nullable=False)        # 计算机 2301 班
    student_count = Column(Integer, default=0)

    # 学生与班级的关联（简化用 JSON 字段也行，这里用关联表保持规范）


class TeacherClass(Base):
    """教师-班级关联"""
    __tablename__ = "teacher_classes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    class_id = Column(String(32), index=True)
    class_name = Column(String(128))
    student_count = Column(Integer, default=0)

    teacher = relationship("User", back_populates="teacher_classes")
