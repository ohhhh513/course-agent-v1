"""
课程内自由多标签（与知识点 KP 正交）
"""
from sqlalchemy import Column, String, Integer, ForeignKey, UniqueConstraint
from ..database import Base


class Tag(Base):
    __tablename__ = "tags"

    tag_id = Column(String(32), primary_key=True)   # T + hex8
    course_id = Column(String(32), ForeignKey("courses.course_id"), index=True, nullable=False)
    name = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("course_id", "name", name="uq_tag_course_name"),
    )


class ResourceTagLink(Base):
    __tablename__ = "resource_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    res_id = Column(String(32), ForeignKey("resources.res_id"), index=True, nullable=False)
    tag_id = Column(String(32), ForeignKey("tags.tag_id"), index=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("res_id", "tag_id", name="uq_resource_tag"),
    )


class QuestionTagLink(Base):
    __tablename__ = "question_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    q_id = Column(String(32), ForeignKey("questions.q_id"), index=True, nullable=False)
    tag_id = Column(String(32), ForeignKey("tags.tag_id"), index=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("q_id", "tag_id", name="uq_question_tag"),
    )
