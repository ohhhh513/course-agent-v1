"""
教学干预 / 报告模型（教师端）
"""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class Intervention(Base):
    """教学干预建议"""
    __tablename__ = "interventions"

    iv_id = Column(String(32), primary_key=True)
    class_id = Column(String(32), ForeignKey("classes.class_id"), index=True)
    level = Column(String(16), default="normal")               # normal/high
    scope = Column(String(16), default="common")               # common/individual

    title = Column(String(256), default="")
    target = Column(String(256), default="")
    reason = Column(Text, default="")
    steps_json = Column(Text, default="[]")                     # JSON
    expect_effect = Column(Text, default="")
    status = Column(String(16), default="pending")             # pending/running/done/rejected
    execution_json = Column(Text, default="{}")                 # JSON 执行情况

    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class InterventionTemplate(Base):
    """干预策略模板（教师沉淀）"""
    __tablename__ = "intervention_templates"

    tpl_id = Column(String(32), primary_key=True)
    scene = Column(String(64), default="")
    name = Column(String(256), default="")
    steps_json = Column(Text, default="[]")
    resources_json = Column(Text, default="[]")
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    """学情分析报告"""
    __tablename__ = "reports"

    report_id = Column(String(32), primary_key=True)
    class_id = Column(String(32), ForeignKey("classes.class_id"), index=True)
    title = Column(String(256), default="")
    status = Column(String(16), default="ready")               # generating/ready/exported
    detail_json = Column(Text, default="{}")                    # JSON 报告详情
    created_at = Column(DateTime, default=datetime.utcnow)


class TeacherClassDashboard(Base):
    """教师端学生列表/画像/驾驶舱等聚合数据（简化存 JSON）"""
    __tablename__ = "teacher_class_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(String(32), ForeignKey("classes.class_id"), index=True)
    data_type = Column(String(32), index=True)                  # dashboard/heatmap/students/profile
    data_key = Column(String(64), default="")                   # userId 等
    data_json = Column(Text, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
