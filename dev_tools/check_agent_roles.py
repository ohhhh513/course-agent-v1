"""角色权限自检（不需要模型、不需要数据库，秒级）。

用法（backend/.venv 的解释器）：

    python dev_tools/check_agent_roles.py

校验三件事：
1. 任务流的 roles 声明（explain 三端可用；generate_items 只允许教师/管理员）；
2. 组装给模型的工具清单按角色过滤（学生看不到教师专用工具）；
3. registry.execute() 的第二层校验：即使模型硬调，学生也会被拒。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.agent_st.agent import registry                      # noqa: E402
from app.agent_st.agent.context import ToolContext           # noqa: E402
from app.agent_st.agent.loader import load_flow              # noqa: E402
from app.agent_st.agent.tools import bank, draft, plan, rag, topic, validate  # noqa: E402,F401

FAILS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  [ok] " if cond else "  [FAIL] ") + label)
    if not cond:
        FAILS.append(label)


def names_of(flow_id: str, role: str) -> list[str]:
    specs = registry.openai_tools(flow_id, None, role=role)
    return sorted((s.get("function") or {}).get("name") or "" for s in specs)


def main() -> int:
    print("1) 流级 roles 声明")
    explain_roles = load_flow("explain").get("roles") or []
    gen_roles = load_flow("generate_items").get("roles") or []
    check(set(explain_roles) == {"student", "teacher", "admin"}, f"explain.roles={explain_roles}")
    check(set(gen_roles) == {"teacher", "admin"}, f"generate_items.roles={gen_roles}")

    teacher_tools = {"search_similar_questions", "submit_item_plan",
                     "check_novelty", "validate_question", "save_question_draft"}

    print("2) 工具清单按角色过滤")
    exp_student, exp_teacher = names_of("explain", "student"), names_of("explain", "teacher")
    check(exp_student == exp_teacher, "explain 流学生/教师工具清单一致（该流无教师专用工具）")
    check({"explain_metric", "my_alerts", "breakdown", "weak_ranking"} <= set(exp_student),
          f"explain 流含学情工具：{exp_student}")

    gen_student = names_of("generate_items", "student")
    gen_teacher = names_of("generate_items", "teacher")
    check(not (teacher_tools & set(gen_student)), f"学生看不到教师专用工具：{gen_student}")
    check(teacher_tools <= set(gen_teacher), f"教师能看到全部出题工具：{gen_teacher}")

    unfiltered = names_of("generate_items", "")
    check(teacher_tools <= set(unfiltered), "role 为空时不过滤（兼容显式无角色调用）")

    print("3) execute() 第二层校验")
    class _Store:
        course_id = ""
        user_id = "U_TEST"

    student_ctx = ToolContext(store=_Store(), flow_id="generate_items",
                              extra={"role": "student"}, user_id="U_TEST")
    rejected = registry.execute("save_question_draft", {"question": "{}"}, student_ctx)
    check(isinstance(rejected, dict) and "无权" in str(rejected.get("error", "")),
          f"学生硬调 save_question_draft 被拒：{rejected}")

    wrong_flow_ctx = ToolContext(store=_Store(), flow_id="explain",
                                 extra={"role": "teacher"}, user_id="U_TEST")
    rejected2 = registry.execute("save_question_draft", {"question": "{}"}, wrong_flow_ctx)
    check(isinstance(rejected2, dict) and "不能调用" in str(rejected2.get("error", "")),
          f"explain 流调用出题工具被拒：{rejected2}")

    print()
    if FAILS:
        print(f"结果：{len(FAILS)} 项失败")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
