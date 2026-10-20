from __future__ import annotations

import base64
import json
import queue
import re
import threading
from collections.abc import Iterator

from app.agent_st.agent import llm
from app.agent_st.agent.config import get_settings
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.loader import bind_course_identity, build_system_prompt, load_flow, load_persona
from app.agent_st.agent.registry import execute, openai_tools, tool_ok
from app.agent_st.agent.store import AgentStore
from app.agent_st.rag.bank import get_question, next_ai_q_id, search_similar
from app.agent_st.rag.ingest import ensure_bank_indexed
from app.agent_st.rag.topic import looks_like_course_question

# 注册工具（import 即注册；逐个显式列出，避免依赖 tools/__init__ 的副作用）
from app.agent_st.agent.tools import (admin_delete, admin_import, admin_ops,  # noqa: F401
                                      analytics, bank, batch_draft, draft, plan, rag,
                                      teacher_analytics, topic, validate, ui_actions)

Event = dict  # run_turn 产出的事件统一为 dict：{"type": ...}


def _citations_from_turn(turn: dict) -> list[dict]:
    hits = turn.get("citations") or (turn.get("retrieval") or {}).get("hits") or []
    out = []
    for hit in hits:
        out.append(
            {
                "chunk_id": hit.get("chunk_id"),
                "chapter_id": hit.get("chapter_id"),
                "kp_id": hit.get("kp_id"),
                "source_type": hit.get("source_type"),
                "source_id": hit.get("source_id"),
                "q_id": hit.get("q_id"),
                "snippet": hit.get("text"),
                "score": hit.get("score"),
            }
        )
    return out


def _log_tool(ctx: ToolContext, name: str, args: dict, result) -> dict:
    """记一条工具调用日志；写操作被闸门拦下时标成「待批准」（P2c）。"""
    entry = {"kind": "tool", "name": name, "args": args, "ok": tool_ok(result)}
    if isinstance(result, dict) and result.get("pending"):
        entry["pending"] = True
    ctx.tool_log.append(entry)
    return entry


def collect_actions(ctx: ToolContext) -> list[dict]:
    """本轮要透出的界面动作：只读建议（suggest_action）+ 待批准写操作（P2c）。"""
    out: list[dict] = list(ctx.turn.get("actions") or [])
    for item in ctx.turn.get("pending_actions") or []:
        out.append({
            "kind": "confirm",
            "actionId": item.get("action_id"),
            "tool": item.get("tool"),
            "summary": item.get("summary"),
            "impact": item.get("impact") or "",
            "status": item.get("status") or "pending",
        })
    return out


def action_events(ctx: ToolContext) -> list[Event]:
    actions = collect_actions(ctx)
    return [{"type": "action", "actions": actions}] if actions else []


def persist_side_effects(store: AgentStore, session_id: str, ctx: ToolContext) -> None:
    """把本轮的工具日志 + 待批准动作（含完整参数）+ 越界标记落到最后一条 assistant 消息上。

    待批准动作必须落库：approve 接口要从这里读出**服务端的参数**再执行，
    不能信任前端回传的参数。

    越界标记（`kind=meta`）也必须落库：它由本轮的「话题是否确定 / 检索最高分」算出来，
    这两个输入都不落库、事后无法重算；不存的话刷新页面提示条就消失了
    （前端只能在实时那一轮从 `done` 事件拿到它）。
    """
    log = list(ctx.tool_log) + [dict(x) for x in (ctx.turn.get("pending_actions") or [])]
    if ctx.turn.get("out_of_scope"):
        log.append({"kind": "meta", "out_of_scope": True})
    if log:
        store.set_last_tool_log(session_id, log, draft_id=_first_draft_id(ctx))


def _run_tool(name: str, args: dict, ctx: ToolContext) -> tuple[list[Event], object]:
    events: list[Event] = [
        {"type": "tool_start", "name": name, "args": args},
    ]
    result = execute(name, args, ctx)
    _log_tool(ctx, name, args, result)
    events.append(
        {"type": "tool_end", "name": name, "ok": True,
         "preview": result if not isinstance(result, list) else result[:4]}
    )
    return events, result


def draft_events_for_tool(name: str, result, ctx: ToolContext) -> list[Event]:
    """把草稿工具结果映射为现有的逐题 draft 事件。"""
    if name == "save_question_draft":
        return [{"type": "draft", **result}] if isinstance(result, dict) and result.get("draft_id") else []
    if name != "save_question_batch" or not isinstance(result, dict) or not result.get("ok"):
        return []
    draft_ids = set(str(value) for value in (result.get("draft_ids") or []))
    return [
        {"type": "draft", **draft}
        for draft in (ctx.turn.get("drafts") or [])
        if isinstance(draft, dict) and str(draft.get("draft_id") or "") in draft_ids
    ]


def _demo_explain(message: str, ctx: ToolContext) -> str:
    retrieval = ctx.turn.get("retrieval") or {}
    hits = retrieval.get("hits") or []
    topic = ctx.turn.get("topic") or {}
    topic_name = topic.get("kp_name") or topic.get("chapter_name") or ""
    if retrieval.get("empty") or not hits:
        lines = ["【演示模式】当前只提供检索结果，未生成完整讲解。",
                 "未检索到匹配的课程资料；请补充具体知识点或题目内容后再试。"]
        return "\n".join(lines)
    lines = ["【演示模式】当前只提供检索结果，未生成完整讲解。"]
    if topic_name:
        lines.append(f"相关知识点：{topic_name}")
    lines.append("相关课程资料：")
    for hit in hits[:2]:
        excerpt = " ".join(str(hit.get("text") or "").split())[:220]
        if excerpt:
            lines.append(f"- {excerpt}")
    return "\n".join(lines)


def _demo_build_payload(message: str, ctx: ToolContext) -> dict | None:
    """演示模式：按同章原题骨架拼一道题（**只构造，不落库**）。返回 None = 找不到骨架。"""
    course_id = (ctx.extra or {}).get("courseId") or ""
    topic = ctx.turn.get("topic") or {}
    examples = [x for x in (ctx.turn.get("example_questions") or []) if isinstance(x, dict)]
    similar = ctx.turn.get("similar") or []
    src = examples[0] if examples else None
    if src is None:
        if not similar:
            similar = search_similar(
                course_id=course_id,
                chapter_id=topic.get("chapter_id"),
                kp_ids=[str(x) for x in (topic.get("kp_ids") or []) if str(x).strip()]
                or ([topic["kp_id"]] if topic.get("kp_id") else None),
                limit=1,
                include_answer=True,
            )
        if not similar:
            return None
        src = similar[0]
    full = src
    if src.get("q_id"):
        full = get_question(course_id, src["q_id"], include_answer=True) or src
    payload = {
        "q_id": next_ai_q_id(course_id, reserved=ctx.store.reserved_q_ids()),
        # 结构归属以「本轮定位到的知识点」为准（教师指定），而不是复制骨架题的；
        # 只有定位不到时才退回骨架题的归属
        "chapter_id": topic.get("chapter_id") or full.get("chapter_id") or "",
        "kp_id": topic.get("kp_id") or full.get("kp_id") or "",
        "kp_ids": [str(x) for x in (topic.get("kp_ids") or []) if str(x).strip()]
        or ([topic["kp_id"]] if topic.get("kp_id") else [])
        or ([full["kp_id"]] if full.get("kp_id") else []),
        "question": full.get("question") or src.get("question"),
        "options": full.get("options") or src.get("options") or {},
        "answer": full.get("answer") or "A",
        "analysis": "【演示模式】此草稿复制自原题骨架，仅更换了题号。配置 LLM_API_KEY 后将改写题面并重算答案。",
        "has_image": bool(full.get("has_image") or src.get("has_image")),
    }
    if full.get("graph") or src.get("graph"):
        payload["graph"] = full.get("graph") or src.get("graph")
    if full.get("options_graph") or src.get("options_graph"):
        payload["options_graph"] = full.get("options_graph") or src.get("options_graph")
    return payload


def _demo_plan_args(ctx: ToolContext, payload: dict) -> dict:
    """演示模式的构思占位：**真实调用** submit_item_plan，把「跳过构思」这件事写进解题过程。

    演示模式没有模型参与，不可能给出真实构思；但写操作闸门要求「先过前置校验」，
    所以这里如实说明「这是占位」，而不是伪造一份看起来像真构思的文本。
    """
    kp = str(payload.get("kp_id") or "本知识点")
    qid = str(payload.get("q_id") or "（系统分配）")
    stem = str(payload.get("question") or "").strip().replace("\n", " ")
    return {
        "asked_target": f"【演示模式】复用同章原题骨架改写，考查 {kp}（题号 {qid}）",
        "instance_sketch": f"【演示模式】沿用骨架题「{stem[:60]}」的实例与选项结构。",
        "solution_trace": (
            "【演示模式，未配置 LLM_API_KEY】这里不是真实的逐步解题，只作占位：演示模式直接复用"
            "同章原题的骨架与解析，没有走「构思 → 改写 → 较大变动校验」的新题生成工作流。"
            "配置 LLM_API_KEY 之后，这一步会由模型给出真实的逐步解题过程与重算答案。"
        ),
        "correct_answer_content": "【演示模式】沿用骨架题的正确答案。",
        "distractor_rationale": "【演示模式】沿用骨架题的干扰项，未重新设计易错点。",
        "change_note": "【演示模式】除题号由系统重新分配外，相对骨架题没有内容改动。",
        "kp_or_section": str(payload.get("kp_id") or ""),
    }


def _demo_generate_text(payload: dict, result) -> str:
    """演示模式出题的说明文本：如实区分「已排入待批准」与「未排入」。"""
    if isinstance(result, dict) and result.get("pending"):
        head = (
            "【演示模式，未配置 LLM_API_KEY】已生成 1 道题，并排入**待批准**"
            f"（actionId={result.get('actionId')}）。\n"
            f"待批准内容：{result.get('summary')}\n"
            "请在上方的确认卡片上点「确认执行」，我才会真正把它写进你的草稿箱 —— **现在还没有写入**。\n"
            "演示模式未走「较大变动」构思与 novelty 校验；点击确认后仍会做结构校验。\n\n"
        )
    else:
        head = ("【演示模式，未配置 LLM_API_KEY】草稿**没有**排入待批准：\n"
                f"{json.dumps(result, ensure_ascii=False)}\n\n")
    return head + json.dumps(payload, ensure_ascii=False, indent=2)


# 演示模式：上传账号表后表达「要录入」意图的关键词（命中才走导入工具链，
# 避免把「这份名单里都有谁」这类提问误当写操作）。
_IMPORT_INTENT = ("导入", "录入", "建号", "开户", "注册", "新增", "添加", "创建",
                  "加入", "入库", "进系统", "加到", "加进")

# 演示模式：删号意图关键词（删比录入更明确，判断顺序放在录入之前）。
_DELETE_INTENT = ("删除", "删掉", "删了", "删去", "移除", "清理", "清掉", "去掉", "清除")


_USERNAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,31}")


def _username_candidates(msg: str) -> list[str]:
    """从自然语言里挑出**看起来像用户名**的 token（字母开头，后接字母/数字/下划线）。"""
    return list(dict.fromkeys(_USERNAME_TOKEN.findall(msg or "")))


def _usernames_in_text(msg: str) -> list[str]:
    """候选 token ∩ 库内确实存在的用户名（演示模式点名删号用）。

    按「库里存在」过滤后，句中的普通英文词不会变成假候选；
    而候选里不存在的（如打错的用户名）交给工具如实回报「账号不存在」。
    """
    from app.agent_st import persistence

    cands = _username_candidates(msg)
    if not cands:
        return []
    db = persistence.SessionLocal()
    try:
        from app.models.user import User
        existing = {r[0] for r in db.query(User.username).filter(User.username.in_(cands)).all()}
    finally:
        db.close()
    return [c for c in cands if c in existing]


def _attachment_files(ctx: ToolContext) -> list:
    """本轮附件在服务端已完成的结构化解析结果（账号表），无则为空列表。"""
    return [f for f in (((ctx.extra or {}).get("account_import") or {}).get("files") or [])
            if isinstance(f, dict)]


def _demo_admin_turn(message: str, ctx: ToolContext) -> Iterator[Event]:
    """演示模式（未配置 LLM_API_KEY）下的平台治理回答。

    与课程流的演示不同：治理工具本身是**确定性查询**，不依赖模型 —— 直接按问题关键词
    选一个治理工具跑**真实查询**，把真实数字拼成回答。管理员在没有 key 的环境里
    也能拿到真实数据（而不是一段占位文本）。
    """
    msg = message or ""
    # ① 账号删除 / 录入（上传文件或点名）：两个写操作在演示模式下也跑真实工具链
    #    （确定性，不依赖模型），最终都进「待批准」闸门，与 live 模式同一套语义。
    #    删除判断放在录入之前：「删」比「录入」更明确，避免歧义句走错分支。
    imp_files = _attachment_files(ctx)
    if any(k in msg for k in _DELETE_INTENT) and (imp_files or _username_candidates(msg)):
        yield from _demo_admin_delete(msg, ctx)
        return
    if imp_files and any(k in msg for k in _IMPORT_INTENT):
        yield from _demo_admin_import(msg, ctx)
        return

    if any(k in msg for k in ("体检", "一致性", "有没有问题", "脏数据", "数据问题")):
        name, title = "data_check", "数据一致性体检"
    elif any(k in msg for k in ("知识库", "索引", "切片", "重建")):
        name, title = "kb_status", "知识库索引状态"
    elif any(k in msg for k in ("课程", "几门课", "哪门课")):
        name, title = "course_overview", "课程规模"
    elif any(k in msg for k in ("账号", "用户", "学生", "教师")):
        name, title = "account_overview", "账号治理"
    else:
        name, title = "system_overview", "平台总览"

    # 演示模式没有模型，无法对附件正文做语义分析；如实告知已收到，避免用户误以为读了文件
    atts = [a for a in ((ctx.extra or {}).get("attachments") or []) if isinstance(a, dict)]
    att_note = ""
    if atts:
        att_note = ("已收到附件：" + "、".join(str(a.get("name") or "文件") for a in atts)
                    + "（演示模式未配置 LLM_API_KEY，不对附件内容做语义分析；"
                    "学生/教师账号表请直接说「把名单里的账号录入系统」或「把名单里的账号删掉」）")

    events, result = _run_tool(name, {}, ctx)
    yield from events

    if not isinstance(result, dict) or result.get("error"):
        text = (att_note + "\n\n" if att_note else "") + f"【演示模式，未配置 LLM_API_KEY】{title}查询失败：{result}"
        for chunk in llm.chunk_text(text):
            yield {"type": "text", "delta": chunk}
        ctx.turn["final_text"] = text
        return

    lines = []
    if att_note:
        lines += [att_note, ""]
    lines += [f"【演示模式，未配置 LLM_API_KEY】{title}（以下为工具实时查询的真实数据）：", ""]
    lines += _demo_admin_lines(name, result)
    lines += ["", "配置 LLM_API_KEY 后，回答将由模型基于同样的工具结果组织成自然语言。"]
    text = "\n".join(lines)
    for chunk in llm.chunk_text(text):
        yield {"type": "text", "delta": chunk}
    yield {"type": "citations", "items": []}
    ctx.turn["final_text"] = text


def _demo_admin_import(message: str, ctx: ToolContext) -> Iterator[Event]:
    """演示模式下的账号录入：跑真实工具链（preview_account_import → import_accounts）。

    import_accounts 是写操作，会被审批闸门拦成「待批准」——动作与卡片由既有 P2c 链路透出，
    这里只负责把结果讲清楚（不做任何写库）。
    """
    events, preview = _run_tool("preview_account_import", {}, ctx)
    yield from events

    files = [f for f in ((preview or {}).get("files") or []) if isinstance(f, dict)] \
        if isinstance(preview, dict) else []
    if not files:
        err = (preview or {}).get("error") if isinstance(preview, dict) else None
        text = ("【演示模式】" + (err or "未能从附件中解析出账号数据行，"
                                 "请检查表头（用户名 / 姓名 / 密码 / 班级 / 学号 或 部门 / 职称）。"))
        for chunk in llm.chunk_text(text):
            yield {"type": "text", "delta": chunk}
        ctx.turn["final_text"] = text
        return

    f0 = files[0]
    role = str(f0.get("role") or "student")
    # 文件表头没暴露角色线索、但管理员话里说明了角色 → 以管理员说的为准
    if "教师" in message and "学生" not in message:
        role = "teacher"
    label = {"student": "学生", "teacher": "教师"}.get(role, role)
    counts = f0.get("counts") or {}
    valid = [a for a in (f0.get("validAccounts") or []) if isinstance(a, dict)]

    lines = [
        f"【演示模式，未配置 LLM_API_KEY】已解析附件「{f0.get('name')}」，识别为{label}账号表：",
        f"- 共 {counts.get('total', 0)} 行：有效 {counts.get('valid', 0)} / "
        f"重复 {counts.get('dup', 0)} / 错误 {counts.get('error', 0)}",
    ]
    for s in (f0.get("skippedRows") or [])[:5]:
        lines.append(f"- 跳过：{s.get('username') or '（无用户名）'}（{s.get('error') or s.get('status')}）")

    if not valid:
        lines += ["", "没有可录入的有效行，未生成录入动作；修正文件后重新上传即可。"]
    else:
        ev, result = _run_tool("import_accounts", {"role": role, "accounts": valid}, ctx)
        yield from ev
        if isinstance(result, dict) and result.get("pending"):
            lines += ["", f"已生成「待批准动作」：批量创建 {len(valid)} 个{label}账号。"
                          "**请点下方卡片里的「确认执行」**，确认后才会真正写入系统。"]
        else:
            why = ""
            if isinstance(result, dict):
                why = result.get("error") or "；".join(result.get("errors") or [])
            lines += ["", f"生成录入动作失败：{why or result}"]

    text = "\n".join(lines)
    for chunk in llm.chunk_text(text):
        yield {"type": "text", "delta": chunk}
    yield {"type": "citations", "items": []}
    ctx.turn["final_text"] = text


def _demo_admin_delete(message: str, ctx: ToolContext) -> Iterator[Event]:
    """演示模式下的账号删除：跑真实工具链（preview_account_delete → delete_accounts）。

    delete_accounts 是写操作，会被审批闸门拦成「待批准」——动作与卡片由既有 P2c 链路透出，
    这里只负责把结果讲清楚（不做任何写库）。
    """
    # 点名（如「把 stu11、stu12 删掉」）优先；没点名就用本轮附件名单。
    # 点了名但库里没有 → 也交给工具，好如实回报「账号不存在」，而不是默默什么都不做。
    named = _usernames_in_text(message)
    if named:
        args = {"usernames": named}
    elif not _attachment_files(ctx) and _username_candidates(message):
        args = {"usernames": _username_candidates(message)}
    else:
        args = {}
    source = "点名" if (named or args) else "本轮附件名单"
    events, preview = _run_tool("preview_account_delete", args, ctx)
    yield from events

    if not isinstance(preview, dict) or preview.get("error"):
        err = preview.get("error") if isinstance(preview, dict) else None
        text = "【演示模式】" + (err or "未能确定要删除的账号。")
        for chunk in llm.chunk_text(text):
            yield {"type": "text", "delta": chunk}
        ctx.turn["final_text"] = text
        return

    counts = preview.get("counts") or {}
    deletable = [a for a in (preview.get("deletableAccounts") or []) if isinstance(a, dict)]
    lines = [
        f"【演示模式，未配置 LLM_API_KEY】已核对要删除的账号（来源：{source}）：",
        f"- 共核对 {preview.get('checked', 0)} 个：可删除 {counts.get('deletable', 0)} / "
        f"不能删 {counts.get('skipped', 0)}",
    ]
    for s in (preview.get("skippedRows") or [])[:5]:
        lines.append(f"- 不能删：{s.get('username') or s.get('ident') or '（无用户名）'}"
                     f"（{s.get('reason')}）")

    if not deletable:
        lines += ["", "没有可删除的账号，未生成删除动作。"]
    else:
        head = "、".join(str(a.get("username") or "") for a in deletable[:3])
        if len(deletable) > 3:
            head += f" 等 {len(deletable)} 个"
        ev, result = _run_tool("delete_accounts", {"accounts": deletable}, ctx)
        yield from ev
        if isinstance(result, dict) and result.get("pending"):
            lines += ["",
                      f"已生成「待批准动作」：批量删除 {len(deletable)} 个账号（{head}）。",
                      "**请点下方卡片里的「确认执行」**，确认后才会真正删除。",
                      "注意：删除会级联清理这些账号的个人数据（练习/答题、进度、学习路径、"
                      "AI 会话、预警、草稿、成员关系等），**不可撤销**。"]
        else:
            why = ""
            if isinstance(result, dict):
                why = result.get("error") or "；".join(result.get("errors") or [])
            lines += ["", f"生成删除动作失败：{why or result}"]

    text = "\n".join(lines)
    for chunk in llm.chunk_text(text):
        yield {"type": "text", "delta": chunk}
    yield {"type": "citations", "items": []}
    ctx.turn["final_text"] = text


def _demo_admin_lines(name: str, r: dict) -> list[str]:
    """把治理工具的返回压成几行可读文本（只挑关键字段，JSON 全文交给工具面板）。"""
    if name == "system_overview":
        roles = "、".join(f"{k} {v}" for k, v in r["accounts"]["byRole"].items())
        return [
            f"- 账号：{r['accounts']['total']} 个（{roles}）",
            f"- 课程：{r['memberships']['courses']} 门，课程成员关系 {r['memberships']['total']} 条",
            f"- 内容：题目 {r['content']['questions']} / 资源 {r['content']['resources']} / "
            f"知识点 {r['content']['knowledgePoints']} / 章节 {r['content']['chapters']}",
            f"- 学习数据：答题记录 {r['learning']['answerRecords']} 条，预警 {r['learning']['alerts']} 条",
            f"- 智能体：会话 {r['agent']['sessions']} 个 / 消息 {r['agent']['messages']} 条 / "
            f"报告 {r['agent']['reports']} 份 / 草稿 {r['agent']['drafts']} 份",
            f"- 运行模式：{r['runtime']['mode']}（模型 {r['runtime']['model']}，"
            f"embedding {r['runtime']['embeddingModel']}）",
            f"- 知识库索引：{r['rag']['totalChunks']} 条切片",
        ]
    if name == "account_overview":
        roles = "、".join(f"{k} {v}" for k, v in r["byRole"].items())
        out = [f"- 账号总数（不含管理员）：{r['total']}；按角色：{roles}",
               f"- 未加入任何课程的账号：{r['noCourseCount']} 个；从未练习过的学生：{r['noAnswerStudentCount']} 名"]
        for t in r["teachers"]:
            out.append(f"- 教师 {t['name']}（{t['username']}）带 {t['courseCount']} 门课")
        return out
    if name == "course_overview":
        out = []
        for c in r["courses"]:
            out.append(
                f"- {c['name']}（{c['courseId']}）：教师 {c['members']['teachers']} / "
                f"学生 {c['members']['students']}，题目 {c['content']['questions']}、"
                f"资源 {c['content']['resources']}、知识点 {c['content']['knowledgePoints']}，"
                f"答题 {c['learning']['answerRecords']} 条，最近作答 {c['learning']['lastAnswerAt'] or '（无）'}"
            )
        return out
    if name == "kb_status":
        out = [f"- 生效 embedding 模型：{r['activeEmbeddingModel']}；切片总数 {r['totalChunks']}"]
        for cid, n in r["byCourse"].items():
            out.append(f"- {cid or '（未归属）'}：{n} 条")
        if "staleChunkCount" in r:
            out.append(f"- 旧模型切片：{r['staleChunkCount']} 条"
                       + ("，建议重建索引" if r.get("needRebuildCourses") else "，无需重建"))
        return out
    if name == "data_check":
        out = [f"- 共 {r['checked']} 项检查，{r['issueCount']} 项需要处理"]
        for c in r["checks"]:
            mark = "✅" if c["ok"] else "⚠️"
            detail = "" if c["ok"] else "：" + json.dumps(c["items"], ensure_ascii=False)[:160]
            out.append(f"- {mark} {c['name']}{detail}")
        return out
    return [json.dumps(r, ensure_ascii=False)[:600]]


def _demo_turn(flow_id: str, message: str, ctx: ToolContext) -> Iterator[Event]:
    if flow_id == "admin_ops":
        # 平台治理流（管理员）：演示模式也跑真实工具查询；课程流的演示逻辑不适用
        yield from _demo_admin_turn(message, ctx)
        return
    extra = ctx.extra or {}
    events, topic = _run_tool(
        "resolve_topic",
        {"text": message, "kp_id": extra.get("kpId"), "q_id": extra.get("q_id")},
        ctx,
    )
    yield from events
    example_ids = extra.get("example_question_ids") or []
    topic_q = (topic or {}).get("q_id") if isinstance(topic, dict) else None
    if topic_q and str(topic_q) not in [str(x) for x in example_ids]:
        ev, _ = _run_tool("get_question", {"q_id": str(topic_q)}, ctx)
        yield from ev
    if flow_id == "generate_items":
        for qid in example_ids:
            ev, _ = _run_tool(
                "get_question",
                {"q_id": str(qid), "include_answer": True},
                ctx,
            )
            yield from ev

    query = message
    if isinstance(topic, dict) and topic.get("kp_name"):
        query = f"{topic['kp_name']} {message}"
    ev, retrieval = _run_tool("retrieve_chunks", {"query": query}, ctx)
    yield from ev

    if flow_id == "generate_items":
        args = {
            "chapter_id": (topic or {}).get("chapter_id") if isinstance(topic, dict) else None,
            "kp_id": (topic or {}).get("kp_id") if isinstance(topic, dict) else None,
        }
        ev, _ = _run_tool("search_similar_questions", args, ctx)
        yield from ev
        payload = _demo_build_payload(message, ctx)
        if payload is None:
            text = "未找到可复用的同章题目骨架。请指定章节、知识点或源题号。"
        else:
            # 先补齐构思 / 查重，再保存草稿。出题页带 autoApproveDraft 时直接落库并出预览；
            # 答疑里的同名工具仍排成待批准。
            ev, _ = _run_tool("submit_item_plan", _demo_plan_args(ctx, payload), ctx)
            yield from ev
            from app.agent_st.rag.novelty import question_fingerprint

            ctx.turn["last_novelty"] = {
                "ok": True, "errors": [], "fingerprint": question_fingerprint(payload),
                "note": "演示模式：未真实执行「较大变动」校验（骨架改写必然近似）",
            }
            ev, result = _run_tool("save_question_draft", {"question": payload}, ctx)
            yield from ev
            text = _demo_generate_text(payload, result)
    else:
        text = _demo_explain(message, ctx)

    for chunk in llm.chunk_text(text):
        yield {"type": "text", "delta": chunk}
    yield {"type": "citations", "items": _citations_from_turn(ctx.turn)}
    ctx.turn["final_text"] = text


def _retrieval_empty(ctx: ToolContext) -> bool:
    retrieval = ctx.turn.get("retrieval") or {}
    hits = retrieval.get("hits") or []
    return bool(retrieval.get("empty") or not hits)


# 学生学情类工具：问自己的预警 / 某个百分比怎么算 / 逐题拆解 —— 不依赖教材检索，数据来自库
_STUDENT_ANALYTICS_TOOLS = {
    "my_alerts", "breakdown", "explain_metric", "weak_ranking", "my_last_attempt",
}


def analytics_tool_names() -> set[str]:
    """「查库即不算越界」的工具集合。

    = 学生学情类 + **教师视角类**。教师视角工具（`class_overview` / `class_alerts` /
    `student_profile` / `kp_heatmap` / `hot_wrong_questions`）同样只查库、不检索教材，
    问「班上谁最需要关注」必须算相关。

    这里**从注册表推导**而不是再列一遍名字：之前就是硬编码漏掉了教师工具，
    导致教师问班级学情被误判成「超出课程材料范围」（2026-10-06 修）。
    推导放在函数里（不是模块级常量）—— 注册表是按 import 逐个填充的，
    模块导入时机太早会数不到工具。
    """
    names = set(_STUDENT_ANALYTICS_TOOLS)
    try:
        from app.agent_st.agent import registry

        for spec in registry.TOOLS.values():
            # 教育解释流里的「教师专用工具」= 查全班/某生数据的只读工具
            # （出题流的写工具不在 explain 白名单里，天然不会被算进来）
            if "explain" in spec.flows and "student" not in spec.roles:
                names.add(spec.name)
    except Exception:  # noqa: BLE001 - 推导失败时退回学生集合，不能因此让整轮判定崩掉
        pass
    return names


# 教学工作流工具：出题、给选项、打开界面。这些本来就不检索教材，
# 本轮调用过就不能再打「超出课程材料范围」——否则会出现一边给选项一边拒绝的矛盾。
_WORKFLOW_TOOLS = {"prepare_ui_action", "offer_choices", "suggest_action"}


def _explain_out_of_scope(ctx: ToolContext, message: str) -> bool:
    """越界判定：主题不确定 + 不像本课教学/学习问题 + 检索证据分低于越界阈值。

    越界只用于与课程学习明显无关的闲聊（天气、菜谱、写诗等）。
    出题、组卷、练习、学情、界面操作等教学任务即使还没检索到课文，也不是越界。

    注意检索混合了向量分，生活类问题（如菜谱）也可能捞到几个低分切片，
    因此不能用「有命中就算相关」，必须看最高分是否达到课程问题的水平。

    例外：
    - 本轮成功查到操作目录（界面帮助不依赖教材）
    - 查库类学情工具，见 `analytics_tool_names()`
    - 教学工作流工具（出题预览、选项询问、界面入口）
    """
    # 界面帮助以当前角色操作目录为依据，不需要课程教材检索。
    # 只认工具本轮成功查到的目录，失败调用不能豁免越界判断。
    if (ctx.turn.get("system_guide") or {}).get("found"):
        return False
    used = {e.get("name") for e in (ctx.tool_log or []) if isinstance(e, dict)}
    if used & analytics_tool_names():
        return False
    if used & _WORKFLOW_TOOLS:
        return False

    topic = ctx.turn.get("topic") or {}
    if not topic.get("uncertain", True):
        return False
    if looks_like_course_question(message, course_id=(ctx.extra or {}).get("courseId") or ""):
        return False
    retrieval = ctx.turn.get("retrieval") or {}
    max_score = float(retrieval.get("max_score") or 0.0)
    return max_score < get_settings().off_topic_score


def attachment_ground_text(attachments: list) -> str:
    """把文档附件抽取出的文本拼成「追加到本轮用户消息」的补充材料。

    只在内存里拼，不写库；历史会话仅保留附件引用与展示元数据（见 attachment_log_entries）。
    """
    parts = []
    for a in attachments or []:
        if isinstance(a, dict) and a.get("text"):
            parts.append(f"【用户上传文件：{a.get('name') or 'file'}】\n{a['text']}")
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def attachment_image_parts(attachments: list, *, sdk_input: bool = False) -> list[dict]:
    """将本轮图片转换为当前模型适配器所需的多模态内容块。"""
    parts = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        image_bytes = attachment.get("image_bytes")
        image_mime = attachment.get("image_mime")
        if not isinstance(image_bytes, bytes) or not image_bytes or not image_mime:
            continue
        data_url = f"data:{image_mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        name = str(attachment.get("name") or "图片")
        if sdk_input:
            parts.extend((
                {"type": "input_text", "text": f"【用户上传图片：{name}】"},
                {"type": "input_image", "image_url": data_url, "detail": "auto"},
            ))
        else:
            parts.extend((
                {"type": "text", "text": f"【用户上传图片：{name}】"},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}},
            ))
    return parts


def attachment_log_entries(attachments: list) -> list | None:
    """构造写入 chat_messages.tool_log 的附件引用与展示元数据，不包含文件字节。"""
    files = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict) or not attachment.get("name"):
            continue
        item = {
            "name": str(attachment.get("name") or "文件"),
            "chars": int(attachment.get("chars") or 0),
        }
        if attachment.get("attachment_id"):
            item["attachmentId"] = str(attachment["attachment_id"])
            item["mimeType"] = str(attachment.get("mime_type") or "application/octet-stream")
            item["size"] = int(attachment.get("size") or 0)
        files.append(item)
    return [{"kind": "attach", "files": files}] if files else None


def run_turn(
    message: str,
    flow_id: str | None = None,
    session_id: str | None = None,
    context: dict | None = None,
    store: AgentStore | None = None,
    user_id: str = "",
    course_id: str = "",
    stream: bool = True,
) -> Iterator[Event]:
    """执行一轮对话，产出事件 dict 流。

    事件类型：session / text / tool_start / tool_end / draft / citations / error / done。
    live 模式下文本 delta 来自 LLM 的真实 token 流（stream=True，两段式：
    工具编排轮的过渡文本照常转发，最终回答轮逐 token 转发）；
    demo 模式回退为 chunk_text 假流式。

    course_id 是本轮的数据隔离边界：写入侧进 chat_sessions/草稿，
    读取侧经 context['courseId'] 传给 RAG 检索工具。缺失时检索一律返回空。

    运行层可切换：`AGENT_RUNTIME=sdk` 时交给 sdk_runner（OpenAI Agents SDK），
    事件契约完全一致，前端与路由不用改；默认仍是下方这套手写工具循环。
    """
    from . import sdk_runner

    if (get_settings().agent_runtime or "legacy").strip().lower() == "sdk" and sdk_runner.available():
        yield from sdk_runner.run_turn_sdk(
            message=message, flow_id=flow_id, session_id=session_id, context=context,
            store=store, user_id=user_id, course_id=course_id,
        )
        return

    ensure_bank_indexed(course_id=course_id or (context or {}).get("courseId") or None)
    persona = load_persona()
    flow_id = flow_id or persona.get("default_flow", "explain")
    if flow_id in {"qa", "tutoring"}:
        flow_id = "explain"
    try:
        flow = load_flow(flow_id)
    except FileNotFoundError:
        yield {"type": "error", "message": f"未知任务流 {flow_id}"}
        yield {"type": "done"}
        return

    # 任务流级角色校验：flow 里声明的 roles 是"谁能用这条流"（服务端按登录用户角色判断，
    # 模型无法指定）。出题流会写草稿，只允许教师/管理员。
    role = str((context or {}).get("role") or "").strip()
    allowed_roles = flow.get("roles") or persona.get("roles") or []
    if role and allowed_roles and role not in allowed_roles:
        yield {"type": "error",
               "message": f"当前角色（{role}）不能使用「{flow.get('name') or flow_id}」"}
        yield {"type": "done"}
        return

    store = store or AgentStore(user_id=user_id, course_id=course_id)
    if user_id and not store.user_id:
        store.user_id = user_id
    if course_id and not store.course_id:
        store.course_id = course_id
    session_id = store.ensure_session(session_id, flow_id)
    yield {"type": "session", "session_id": session_id, "flow_id": flow_id}

    # 「停止生成」= 协作式取消：开新一轮前清掉上一轮可能残留的停止标记
    from . import cancel as _cancel

    cancel_key = str((context or {}).get("cancelKey") or session_id)
    if cancel_key == session_id:
        _cancel.clear(session_id)

    extra = dict(context or {})
    extra["message"] = message
    # 检索工具统一从 extra['courseId'] 取课程，这里保证它一定被填上
    if store.course_id:
        extra.setdefault("courseId", store.course_id)
    # 上传附件（附到当前问题）：文档文本和图片只进入本轮模型输入，
    # 消息本身只落附件引用与展示元数据，不落正文或图片字节。
    attachments = [a for a in (extra.get("attachments") or []) if isinstance(a, dict)]
    store.add_message(session_id, "user", message, tool_log=attachment_log_entries(attachments))
    ctx = ToolContext(store=store, flow_id=flow_id, extra=extra, user_id=user_id or store.user_id)

    live_model_available = llm.chat_available()
    if any(a.get("image_bytes") for a in attachments) and not live_model_available:
        yield {"type": "error", "message": "当前处于演示模式，图片识别需要配置支持视觉输入的模型和 API Key"}
        yield {"type": "done"}
        return

    if not live_model_available:
        final = ""
        stopped = False
        for event in _demo_turn(flow_id, message, ctx):
            # 停止生成：演示模式的假流式也在每个切片之间检查一次
            if _cancel.is_requested(cancel_key):
                stopped = True
                break
            if event.get("type") == "text":
                final += event.get("delta") or ""
            yield event
        out_of_scope = _explain_out_of_scope(ctx, message) if flow_id == "explain" else False
        ctx.turn["out_of_scope"] = out_of_scope   # 落库前写入，persist_side_effects 从 ctx.turn 取
        # 停止时只落「已经流出的部分」（ctx.turn['final_text'] 可能是完整文本，不能直接用）；
        # 一个字都没流出就不落空消息。
        demo_text = final if stopped else (ctx.turn.get("final_text") or final)
        if not (stopped and not demo_text.strip()):
            store.add_message(session_id, "assistant", demo_text)
        # 演示模式也会产生待批准动作（出题流），同样要落 tool_log 并透出确认事件
        persist_side_effects(store, session_id, ctx)
        for ev in action_events(ctx):
            yield ev
        yield {
            "type": "done",
            "demo": True,
            "stopped": stopped,
            "drafts": ctx.turn.get("drafts") or [],
            "out_of_scope": out_of_scope,
        }
        return

    history = store.history(session_id, limit=12)
    # 术语清单来自主库（换课程自动换），提示词里不写死任何课程知识点名称
    from app.agent_st.rag import structure as _structure

    catalog = _structure.kp_catalog_text(store.course_id) if store.course_id else ""
    # 提示词里的「页面上下文」不含附件正文与账号解析结果：正文只拼进用户消息，
    # 账号表数据由 preview_account_import 工具按需读取 —— 两处都不进 system，
    # 避免同一份内容重复喂（既费 token，也可能让模型把材料当指令；密码更不该进提示词）。
    prompt_extra = bind_course_identity(
        {k: v for k, v in extra.items() if k not in ("attachments", "account_import")},
        store.course_id,
    )
    messages = [{
        "role": "system",
        "content": build_system_prompt(persona, flow, prompt_extra, course_catalog=catalog),
    }]
    messages.extend(history)
    # 附件正文注入「本轮用户消息」：只改内存里的 LLM 消息，不写库、不影响历史其它轮
    _ground = attachment_ground_text(attachments)
    _image_parts = attachment_image_parts(attachments)
    if _ground or _image_parts:
        for _m in reversed(messages):
            if _m.get("role") == "user":
                current_content = _m.get("content") or ""
                if not isinstance(current_content, str):
                    current_content = str(current_content)
                if _image_parts:
                    text_content = current_content + _ground
                    _m["content"] = ([{"type": "text", "text": text_content}]
                                     if text_content else []) + _image_parts
                else:
                    _m["content"] = current_content + _ground
                break
    whitelist = flow.get("tools") or persona.get("tools") or []
    tools = openai_tools(flow_id, whitelist, role=role)
    settings = get_settings()
    max_steps = int(flow.get("max_steps") or persona.get("max_steps") or settings.max_steps)
    final_text = ""

    for _ in range(max_steps):
        # 真实 token 流式：complete_stream 在工作线程中生成，delta 经队列实时
        # 转发给 SSE 生成器——token 到一个发一个，不再等整轮生成完毕（修复
        # "一瞬间给出大段回复"的体验问题）。
        q: "queue.Queue[tuple[str, object]]" = queue.Queue()
        holder: dict = {}

        def _worker(msgs=messages, _tools=tools, _q=q, _holder=holder, _key=cancel_key):
            def _forward(kind: str, text: str) -> None:
                # 停止生成：一旦置了标记就从回调里抛出去 —— 展开生成器、关闭上游 HTTP 流，
                # 不再继续消耗 token（而不是只在消费侧丢弃）。
                if _cancel.is_requested(_key):
                    raise _cancel.Stopped()
                _q.put((kind, text))

            try:
                _holder["reply"] = llm.complete_stream(
                    msgs, _tools,
                    on_text_delta=lambda t: _forward("delta", t),
                    on_reasoning_delta=lambda t: _forward("think", t),
                    cancel_key=_key,
                )
                _q.put(("done", None))
            except _cancel.Stopped:
                _q.put(("stopped", None))
            except Exception as exc:  # noqa: BLE001
                _q.put(("stopped", None) if _cancel.is_requested(_key) else ("error", exc))

        threading.Thread(target=_worker, daemon=True).start()
        reply: dict | None = None
        round_text_parts: list[str] = []
        round_think_parts: list[str] = []
        stopped = False
        while True:
            # 兜底轮询：模型长时间没有 delta（例如纯思考阶段）时，也在下个检查点停下
            if _cancel.is_requested(cancel_key):
                stopped = True
                break
            try:
                kind, payload = q.get(timeout=0.1)
            except queue.Empty:
                continue
            if kind == "delta":
                round_text_parts.append(payload)
                yield {"type": "text", "delta": payload}
            elif kind == "think":
                round_think_parts.append(payload)
                yield {"type": "think", "delta": payload}
            elif kind == "stopped":
                stopped = True
                break
            elif kind == "error":
                yield {"type": "error", "message": f"模型调用失败：{payload}"}
                yield {"type": "done"}
                return
            else:
                reply = holder.get("reply")
                break
        if stopped:
            break
        assert reply is not None

        def _log_think(text: str) -> None:
            text = (text or "").strip()
            if text:
                ctx.tool_log.append({"kind": "think", "text": text})

        if reply["tool_calls"]:
            # 编排轮：思考内容与本轮过渡文本归入"思考"日志（前端在 tool_start 时
            # 将过渡文本收进折叠面板），随后执行工具
            _log_think("".join(round_think_parts))
            _log_think("".join(round_text_parts))
            messages.append(
                {
                    "role": "assistant",
                    "content": reply["content"] or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in reply["tool_calls"]
                    ],
                }
            )
            for tc in reply["tool_calls"]:
                if _cancel.is_requested(cancel_key):
                    stopped = True
                    break
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_start", "name": tc["name"], "args": args}
                result = execute(tc["name"], args, ctx)
                saved_batch = (
                    tc["name"] == "save_question_batch"
                    and isinstance(result, dict)
                    and result.get("ok") is True
                )
                if _cancel.is_requested(cancel_key) and not saved_batch:
                    stopped = True
                    break
                _log_tool(ctx, tc["name"], args, result)
                preview = result if not isinstance(result, list) else result[:4]
                yield {"type": "tool_end", "name": tc["name"], "ok": True, "preview": preview}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                # 每保存一道题即推送 draft 事件（教师端流式预览的关键）
                yield from draft_events_for_tool(tc["name"], result, ctx)
                if _cancel.is_requested(cancel_key):
                    stopped = True
                    break
            if stopped:
                break
            continue

        # 最终回答轮：delta 已实时转发，无需重发；思考内容也入日志
        _log_think("".join(round_think_parts))
        final_text = reply["content"] or ""
        break

    if stopped:
        # 用户中途停止：只把「已经流出来的部分」作为本轮回答落库（刷新后看到的也是这一段）
        _partial = "".join(round_text_parts).strip()
        if not _partial:
            yield {"type": "citations", "items": []}
            yield {"type": "done", "stopped": True,
                   "drafts": ctx.turn.get("drafts") or [], "out_of_scope": False}
            return
        final_text = _partial

    if not final_text:
        final_text = "（模型没有返回文本）"
        yield {"type": "text", "delta": final_text}

    yield {"type": "citations", "items": _citations_from_turn(ctx.turn)}
    out_of_scope = _explain_out_of_scope(ctx, message) if flow_id == "explain" else False
    ctx.turn["out_of_scope"] = out_of_scope       # 落库前写入，persist_side_effects 从 ctx.turn 取
    store.add_message(session_id, "assistant", final_text)
    persist_side_effects(store, session_id, ctx)
    # 界面动作：工具建议的界面动作（suggest_action）+ 写操作的待批准卡片（P2c），
    # 都只透出建议/待批准，用户点击才生效。
    for ev in action_events(ctx):
        yield ev
    yield {
        "type": "done",
        "stopped": stopped,
        "drafts": ctx.turn.get("drafts") or [],
        "out_of_scope": out_of_scope,
    }


def _first_draft_id(ctx: ToolContext) -> str:
    drafts = ctx.turn.get("drafts") or []
    if drafts and isinstance(drafts[0], dict):
        return drafts[0].get("draft_id") or ""
    return ""
