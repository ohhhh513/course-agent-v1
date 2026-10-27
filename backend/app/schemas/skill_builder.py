"""教师编辑器元数据；只负责恢复界面，不能配置工具或角色权限。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TEMPLATE_BASES = {"guided": "course_qa", "concept": "course_qa", "example": "course_qa",
                  "wrong": "wrong_review", "mastery": "mastery", "practice": "practice", "resource": "resource"}


class BuilderValues(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    audience: str = Field(default="正在学习本课程的学生", max_length=40)
    topic: str = Field(default="", max_length=80)
    goal: str = Field(default="", max_length=140)
    extra: str = Field(default="", max_length=600)
    exampleQuestion: str = Field(default="", max_length=240)
    exampleAnswer: str = Field(default="", max_length=1200)
    teachingStyle: Literal["questions", "explain", "examples"] = "questions"
    pace: Literal["one", "short_steps", "complete"] = "one"
    answerPolicy: Literal["after_attempt", "hints", "concept"] = "after_attempt"
    depth: Literal["basic", "standard", "advanced"] = "standard"
    evidence: Literal["course_first", "course_only", "marked_extra"] = "course_first"
    check: Literal["question", "retell", "compare"] = "question"
    layout: Literal["steps", "dialogue", "bullets"] = "steps"
    tone: Literal["patient", "concise", "encourage"] = "patient"
    length: Literal["short", "normal", "detailed"] = "normal"
    missingInfo: Literal["ask", "limited"] = "ask"


class SkillBuilder(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1] = 1
    mode: Literal["guided", "free"]
    templateId: Literal["guided", "concept", "example", "wrong", "mastery", "practice", "resource"]
    values: BuilderValues

    @model_validator(mode="after")
    def goal_required_in_guided_mode(self):
        if self.mode == "guided" and not self.values.goal:
            raise ValueError("引导式配置需要填写学习目标")
        return self
