"""角色权限自检（不需要模型、不需要数据库，秒级）。

用法（backend/.venv 的解释器）：

    python dev_tools/check_agent_roles.py

校验十件事：
1. 任务流的 roles 声明（explain 三端可用；generate_items 只允许教师/管理员）；
2. 组装给模型的工具清单按角色过滤（学生看不到教师专用工具）；
3. 管理员档：只进平台治理流 admin_ops（5 个只读治理查询 + 4 个账号治理工具，写操作挂审批闸门），
   不再进 explain / 出题流，也不再共享教师视角工具；
4. role 为空时不过滤（兼容显式无角色调用，见交接文档 P2a 的 fail-open 说明）；
5. registry.execute() 的第二层校验：即使模型硬调，学生也会被拒；
6. 教师视角工具（P2b）对学生同样不可见、调不动；
7. 写操作工具（带 approval，P2c）在学生可用的任何任务流里都拿不到；
8. 界面动作白名单后端与前端一致（P3 加页面漏改白名单的兜底）；
9. 越界判定的「查库即例外」集合覆盖全部教师视角工具（P2b 加工具漏算的兜底）。

「教师专用工具」从注册表动态推导（判据：roles 里不含 student），
因此 P2b 往 explain 流加教师工具后本脚本会自动纳入断言，不需要改脚本；
只有「新增教师工具」时才同步 known_teacher_tools 这份快照做交叉校验。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.agent_st.agent import registry                      # noqa: E402
from app.agent_st.agent.context import ToolContext           # noqa: E402
from app.agent_st.agent.chat_skills import SKILLS, files_for_skill, resolve_chat_skill  # noqa: E402
from app.agent_st.agent.loader import load_flow, load_skill  # noqa: E402
from app.agent_st.agent.tools import (admin_import, admin_ops, analytics,  # noqa: E402,F401
                                      bank, batch_draft, draft, plan, rag, teacher_analytics,
                                      topic, validate, ui_actions, web_search, web_questions)

FAILS: list[str] = []

# 当前已知的教师专用工具（按任务流）。新增教师工具时在这里补一条，
# 与注册表推导交叉校验，防止「漏写 roles」把工具悄悄放给学生。
KNOWN_TEACHER_TOOLS: dict[str, set[str]] = {
    "explain": {"class_overview", "class_alerts", "student_profile",
                "kp_heatmap", "hot_wrong_questions", "class_question_hotspots"},
    "generate_items": {"search_similar_questions", "submit_item_plan",
                       "check_novelty", "validate_question", "save_question_draft",
                       "save_question_batch"},
}


def check(cond: bool, label: str) -> None:
    print(("  [ok] " if cond else "  [FAIL] ") + label)
    if not cond:
        FAILS.append(label)


def names_of(flow_id: str, role: str) -> list[str]:
    specs = registry.openai_tools(flow_id, None, role=role)
    return sorted((s.get("function") or {}).get("name") or "" for s in specs)


def teacher_only(flow_id: str) -> set[str]:
    """该流里学生不能调的工具（教师专用），从注册表动态推导。"""
    return {spec.name for spec in registry.TOOLS.values()
            if flow_id in spec.flows and "student" not in spec.roles}


def main() -> int:
    print("1) 流级 roles 声明")
    explain_roles = load_flow("explain").get("roles") or []
    gen_roles = load_flow("generate_items").get("roles") or []
    admin_roles = load_flow("admin_ops").get("roles") or []
    # 2026-10-06 收紧：教学流不再对管理员开放，管理员唯一的流是 admin_ops
    check(set(explain_roles) == {"student", "teacher"}, f"explain.roles={explain_roles}")
    check(set(gen_roles) == {"teacher"}, f"generate_items.roles={gen_roles}")
    check(set(admin_roles) == {"admin"}, f"admin_ops.roles={admin_roles}")

    print("2) explain 流：学生看得到全部该看的，教师专用工具不外露")
    exp_student = names_of("explain", "student")
    exp_teacher = names_of("explain", "teacher")
    exp_only = teacher_only("explain")
    student_personal = {"my_last_attempt"}
    check({"explain_metric", "my_alerts", "breakdown", "weak_ranking", "my_last_attempt"} <= set(exp_student),
          f"explain 流含学情工具：{exp_student}")
    check(student_personal <= set(exp_student) and not (student_personal & set(exp_teacher)),
          "my_last_attempt 只给学生：读的是当前登录人的最近一次作答，教师清单里不出现")
    check(KNOWN_TEACHER_TOOLS["explain"] <= exp_only,
          f"explain 流的教师专用工具都声明了 roles 不含 student：{sorted(exp_only)}")
    check(not (exp_only & set(exp_student)),
          f"explain 流学生看不到教师专用工具 {sorted(exp_only)}：{exp_student}")
    check(exp_only <= set(exp_teacher),
          f"explain 流教师能看到全部教师专用工具：{exp_teacher}")
    check(set(exp_student) - student_personal <= set(exp_teacher),
          "explain 流教师清单覆盖学生共享工具（个人作答查询除外）")

    print("3) generate_items 流：教师专用工具对学生不可见")
    gen_student = names_of("generate_items", "student")
    gen_teacher = names_of("generate_items", "teacher")
    gen_only = teacher_only("generate_items")
    check(KNOWN_TEACHER_TOOLS["generate_items"] <= gen_only,
          f"出题流的教师专用工具都声明了 roles 不含 student：{sorted(gen_only)}")
    check(not (gen_only & set(gen_student)), f"学生看不到教师专用工具：{gen_student}")
    check(gen_only <= set(gen_teacher), f"教师能看到全部出题工具：{gen_teacher}")

    print("4) 管理员档：只进平台治理流（admin_ops），不进教学流")
    # 2026-10-06 收紧：管理员不再共享教师视角（班级学情），也不再进 explain / 出题流；
    # 管理员唯一的任务流是 admin_ops（5 个只读治理查询 + 6 个治理写入相关工具：
    # preview_account_import / import_accounts / preview_account_delete / delete_accounts /
    # preview_course_delete / delete_course，
    # 其中 import_accounts、delete_accounts 与 delete_course 是写操作、必须挂审批闸门）。
    # 旧行为（admin 与教师同权）的断言已随之废弃。
    check("admin" not in (load_flow("explain").get("roles") or []),
          "explain 流不再对管理员开放")
    check("admin" not in (load_flow("generate_items").get("roles") or []),
          "出题流不再对管理员开放")
    admin_tools = set(load_flow("admin_ops").get("tools") or [])
    # 业务治理权限保持原有九个工具；系统使用手册与导航是新增的共享只读能力。
    # 2026-10-22 新增课程删除（preview_course_delete 只读 + delete_course 写），故为十一个。
    shared_guidance = {"get_system_guide", "suggest_action", "prepare_ui_action", "offer_choices"}
    business_admin_tools = admin_tools - shared_guidance
    expected_admin_tools = {"system_overview", "account_overview", "course_overview", "kb_status", "data_check",
                            "preview_account_import", "import_accounts", "preview_account_delete", "delete_accounts",
                            "preview_course_delete", "delete_course"}
    check(business_admin_tools == expected_admin_tools and admin_tools <= set(registry.TOOLS),
          f"admin_ops 十一个业务治理工具保持完整：{sorted(business_admin_tools)}")
    check(shared_guidance <= admin_tools and all(registry.TOOLS[n].approval is None for n in shared_guidance),
          "新增系统手册与页面导航均无业务写权限")
    check(all(registry.TOOLS[n].roles == ("admin",) for n in business_admin_tools),
          "系统级工具全部 admin-only（教师/学生都拿不到）")
    check(not any("explain" in registry.TOOLS[n].flows for n in business_admin_tools),
          "系统级工具不出现在任何教学流里")
    # 账号治理（2026-10-08）：preview 只读、import / delete 是写操作必须挂审批闸门（与 P2c 同一约定）
    check(registry.TOOLS["preview_account_import"].approval is None,
          "preview_account_import 是只读工具（无审批闸门、不写库）")
    check(registry.TOOLS["import_accounts"].approval is not None,
          "import_accounts 是写操作（挂审批闸门，管理员确认后才落库）")
    check(registry.TOOLS["preview_account_delete"].approval is None,
          "preview_account_delete 是只读工具（无审批闸门、不写库）")
    check(registry.TOOLS["delete_accounts"].approval is not None,
          "delete_accounts 是写操作（挂审批闸门，管理员确认后才真删）")
    check(registry.TOOLS["preview_course_delete"].approval is None,
          "preview_course_delete 是只读工具（无审批闸门、不写库）")
    check(registry.TOOLS["delete_course"].approval is not None,
          "delete_course 是写操作（挂审批闸门，管理员确认后才真删课程）")
    # 课程删除工具必须只挂 admin_ops 流，且不得出现在任何教学流里
    check(all("admin_ops" in registry.TOOLS[n].flows and
              not any(f in registry.TOOLS[n].flows for f in ("explain", "generate_items"))
              for n in ("preview_course_delete", "delete_course")),
          "课程删除工具只挂 admin_ops 流、不进任何教学流")
    # 两个写工具都要有摘要 / 影响面文案（确认卡片靠它说明「在做什么」）
    for _n in ("import_accounts", "delete_accounts", "delete_course"):
        _spec = registry.TOOLS[_n].approval
        check(bool(_spec.summarize and _spec.impact.strip()),
              f"{_n} 的审批规格含 summarize 与 impact（确认卡片可读）")
    check(all("admin" not in registry.TOOLS[n].roles for n in KNOWN_TEACHER_TOOLS["explain"]),
          "教师视角工具已收紧为 teacher-only（管理员也不再可见）")

    print("5) role 为空时不过滤（兼容显式无角色调用）")
    check(KNOWN_TEACHER_TOOLS["explain"] <= set(names_of("explain", "")),
          "explain 流 role 为空时不过滤")
    check(KNOWN_TEACHER_TOOLS["generate_items"] <= set(names_of("generate_items", "")),
          "generate_items 流 role 为空时不过滤")

    print("6) execute() 第二层校验")
    class _Store:
        course_id = ""
        user_id = "U_TEST"

    student_ctx = ToolContext(store=_Store(), flow_id="generate_items",
                              extra={"role": "student"}, user_id="U_TEST")
    rejected = registry.execute("save_question_draft", {"question": "{}"}, student_ctx)
    check(isinstance(rejected, dict) and "无权" in str(rejected.get("error", "")),
          f"学生硬调 save_question_draft 被拒：{rejected}")

    admin_ctx = ToolContext(store=_Store(), flow_id="generate_items",
                            extra={"role": "admin"}, user_id="U_TEST")
    denied_admin = registry.execute("save_question_draft", {"question": "{}"}, admin_ctx)
    # 2026-10-06 收紧后：管理员连出题工具都调不到（不再"管理员 ⊇ 教师"）
    check(isinstance(denied_admin, dict) and "无权" in str(denied_admin.get("error", "")),
          f"管理员调出题工具被拒：{denied_admin}")

    wrong_flow_ctx = ToolContext(store=_Store(), flow_id="explain",
                                 extra={"role": "teacher"}, user_id="U_TEST")
    rejected2 = registry.execute("save_question_draft", {"question": "{}"}, wrong_flow_ctx)
    check(isinstance(rejected2, dict) and "不能调用" in str(rejected2.get("error", "")),
          f"explain 流调用出题工具被拒：{rejected2}")

    # 教师视角工具（P2b）：学生在 explain 流里硬调也必须被拒
    stu_explain_ctx = ToolContext(store=_Store(), flow_id="explain",
                                  extra={"role": "student"}, user_id="U_TEST")
    rejected3 = registry.execute("class_alerts", {}, stu_explain_ctx)
    check(isinstance(rejected3, dict) and "无权" in str(rejected3.get("error", "")),
          f"学生硬调 class_alerts 被拒：{rejected3}")
    teacher_explain_ctx = ToolContext(store=_Store(), flow_id="explain",
                                      extra={"role": "teacher"}, user_id="U_TEST")
    rejected_attempt = registry.execute("my_last_attempt", {"q_id": "Q1"}, teacher_explain_ctx)
    check(isinstance(rejected_attempt, dict) and "无权" in str(rejected_attempt.get("error", "")),
          f"教师硬调 my_last_attempt 被拒：{rejected_attempt}")

    print("7) 写操作（带审批）的工具：学生一律看不见、调不动")
    write_tools = sorted(name for name, spec in registry.TOOLS.items() if spec.approval)
    check(bool(write_tools), f"注册表里确实有写工具（当前：{write_tools}）")
    check(all("student" not in registry.TOOLS[name].roles for name in write_tools),
          f"写工具的 roles 都不含 student：{[(n, registry.TOOLS[n].roles) for n in write_tools]}")
    leaked = []
    for flow_file in sorted((REPO / "backend/app/agent_st/agent/flows").glob("*.yaml")):
        student_names = set(names_of(flow_file.stem, "student"))
        leaked += [f"{flow_file.stem}:{n}" for n in write_tools if n in student_names]
    check(not leaked, f"学生在其可用的每个任务流里都看不到写工具：{leaked}")
    for name in write_tools:
        flow_id = (registry.TOOLS[name].flows or ("explain",))[0]
        stu_ctx = ToolContext(store=_Store(), flow_id=flow_id,
                              extra={"role": "student"}, user_id="U_TEST")
        denied = registry.execute(name, {}, stu_ctx)
        check(isinstance(denied, dict) and "无权" in str(denied.get("error", "")),
              f"学生硬调写工具 {name} 被拒：{denied}")

    print("8) 界面动作白名单：后端 _VIEWS / _MODES 与前端 chat.js 一致")
    # 这一条是给「加了页面却忘了改白名单」兜底的 —— P3 加了「学情报告」页但漏了 report，
    # 模型给不出指向它的按钮、前端也会把按钮拒掉（点一下只弹"无法直接打开"）。
    chat_js = (REPO / "assets/js/student/views/chat.js").read_text(encoding="utf-8")

    def js_list(var: str) -> list[str]:
        m = re.search(rf"const {var} = \[(.*?)\]", chat_js, re.S)
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()] if m else []

    fe_views, fe_modes = js_list("VIEWS"), js_list("MODES")
    be_views, be_modes = list(analytics._VIEWS), list(analytics._MODES)
    check(set(fe_views) == set(be_views),
          f"view 白名单一致：后端 {sorted(be_views)} / 前端 {sorted(fe_views)}")
    check(set(fe_modes) == set(be_modes),
          f"mode 白名单一致：后端 {sorted(be_modes)} / 前端 {sorted(fe_modes)}")
    # 前端每个页面 key 都必须是真实注册过的视图（否则按钮点下去会被 Router 兜回首页）
    start_js = (REPO / "assets/js/student/start.js").read_text(encoding="utf-8")
    registered = set(re.findall(r"Router\.register\(['\"]([^'\"]+)['\"]", 
                                "\n".join((REPO / "assets/js/student/views" / f).read_text(encoding="utf-8")
                                          for f in sorted(p.name for p in (REPO / "assets/js/student/views").glob("*.js")))
                                + "\n" + start_js))
    missing = sorted(v for v in fe_views if v not in registered)
    check(not missing, f"白名单里的 view 都有真实注册的视图（缺：{missing}）")

    print("9) 越界判定的「查库即例外」集合覆盖全部教师视角工具")
    # 这条是给「加了教师工具却忘了算进越界例外」兜底的 —— P2b 加了 5 个教师视角工具，
    # 但那个例外集合是硬编码的 4 个学生工具，于是教师问「班上谁最需要关注」这种纯查库问题
    # 被打上「超出课程材料范围」（2026-10-06 修）。集合现已改为从注册表推导。
    from app.agent_st.agent.runtime import analytics_tool_names
    covered = analytics_tool_names()
    exp_only = teacher_only("explain")
    check(exp_only <= covered,
          f"explain 流的教师专用工具都在例外集合内：{sorted(exp_only)} ⊆ {sorted(covered)}")
    check({"my_alerts", "breakdown", "explain_metric", "weak_ranking", "my_last_attempt"} <= covered,
          "学生学情工具也在例外集合内")

    print("10) 对话技能：角色隔离、工具 ⊆ 任务流、提示词文件存在")
    for sid, spec in SKILLS.items():
        flow_tools = set(load_flow(spec["flow"]).get("tools") or [])
        skill_tools = set(spec["tools"])
        missing_file = [n for n in files_for_skill(spec) if not load_skill(n)]
        check(not missing_file, f"{sid} 技能文件可读：{missing_file}")
        check(skill_tools <= flow_tools,
              f"{sid} 工具都在 {spec['flow']} 白名单内：{sorted(skill_tools - flow_tools)}")
        leaked_teacher = skill_tools & teacher_only("explain") if spec["flow"] == "explain" else set()
        if "student" in spec["roles"]:
            check(not leaked_teacher, f"学生技能 {sid} 不含教师工具：{sorted(leaked_teacher)}")
            check("my_last_attempt" not in skill_tools or sid == "wrong_review",
                  f"仅错题复盘可含 my_last_attempt：{sid}")
        if "teacher" in spec["roles"]:
            check("my_last_attempt" not in skill_tools, f"教师技能 {sid} 不含 my_last_attempt")
        for role in spec["roles"]:
            ok_spec, err = resolve_chat_skill(spec["flow"], role, sid)
            check(ok_spec is not None and not err, f"{role} 可解析 {sid}：{err}")
        for other in ("student", "teacher", "admin"):
            if other in spec["roles"]:
                continue
            denied, err = resolve_chat_skill(spec["flow"], other, sid)
            check(denied is None and "不能使用" in err, f"{other} 不能使用 {sid}")
    none_spec, none_err = resolve_chat_skill("explain", "student", "")
    check(none_spec is None and none_err == "", "未选技能时保持通用助手")
    bogus, bogus_err = resolve_chat_skill("explain", "student", "class")
    check(bogus is None and "不能使用" in bogus_err, "学生不能选用教师技能 class")
    skill_ctx = ToolContext(store=_Store(), flow_id="explain",
                            extra={"role": "student", "skillTools": ["resolve_topic"]},
                            user_id="U_TEST")
    blocked = registry.execute("my_alerts", {}, skill_ctx)
    check(isinstance(blocked, dict) and "当前技能不能调用" in str(blocked.get("error", "")),
          f"技能白名单拦截未授权工具：{blocked}")

    def js_skill_ids(rel: str) -> list[str]:
        text = (REPO / rel).read_text(encoding="utf-8")
        return re.findall(r"id:\s*'([^']+)'", text)

    fe_student = js_skill_ids("assets/js/student/views/chat.js")
    fe_teacher = js_skill_ids("assets/js/teacher/views/chat.js")
    fe_admin = js_skill_ids("assets/js/admin/views/assistant.js")
    check(fe_student == [s for s, spec in SKILLS.items() if "student" in spec["roles"]],
          f"学生前端技能 id 与目录一致：{fe_student}")
    check(fe_teacher == [s for s, spec in SKILLS.items() if "teacher" in spec["roles"]],
          f"教师前端技能 id 与目录一致：{fe_teacher}")
    check(fe_admin == [s for s, spec in SKILLS.items() if "admin" in spec["roles"]],
          f"管理员前端技能 id 与目录一致：{fe_admin}")

    print()
    if FAILS:
        print(f"结果：{len(FAILS)} 项失败")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
