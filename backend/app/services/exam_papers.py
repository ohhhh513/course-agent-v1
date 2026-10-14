"""教师试卷：使用现有 JSON 容器保存独立题目快照，分值以十分之一分计算。"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from app.models.graph import GraphNode
from app.models.question import Question
from app.services.blank_questions import pack_blank
from app.agent_st.rag.validate import validate_graph

DATA_TYPE = "exam_paper"
TYPES = {"single", "multi", "judge", "blank"}


def score_units(value, *, positive=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = Decimal(str(value))
        units = number * 10
        if not number.is_finite() or units != units.to_integral_value():
            raise ValueError()
        if number < (Decimal("0.1") if positive else 0) or number > 10000:
            raise ValueError()
        return int(units)
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError("分值须为最多一位小数的数字，总分和已发布题目分值必须大于零（最大 10000 分）")


def distribute_scores(total, count):
    """整分总分优先按整分分配；不足一整分/题或小数总分使用 0.1 分。"""
    units = score_units(total, positive=True)
    if not count:
        return []
    step = 10 if units % 10 == 0 and units >= count * 10 else 1
    base, remainder = divmod(units // step, count)
    return [(base + (i >= count - remainder)) * step / 10 for i in range(count)]


def normalize_paper(db, course_id, incoming, previous=None):
    previous = previous or {}
    title = str(incoming.get("title") or "").strip()
    if len(title) > 120:
        raise ValueError("试卷名称不能超过 120 字")
    total = score_units(incoming.get("totalScore", 100), positive=True)
    mode = incoming.get("scoreMode", "auto")
    if mode not in ("auto", "manual"):
        raise ValueError("分值分配方式不正确")
    raw_items = incoming.get("items") or []
    if not isinstance(raw_items, list) or len(raw_items) > 200:
        raise ValueError("每份试卷最多 200 道题")
    nodes = db.query(GraphNode).filter(GraphNode.course_id == course_id).all()
    chapter_ids = {n.id for n in nodes if n.graph_type == "chapter"}
    kp_ids = {n.id for n in nodes if n.graph_type == "knowledge"}
    old_items = {i["id"]: i for i in previous.get("items", [])}
    scores = distribute_scores(total / 10, len(raw_items)) if mode == "auto" else None
    items, issues, seen = [], [], set()
    if not title:
        issues.append("请填写试卷名称")
    if not raw_items:
        issues.append("请至少添加一道题目")
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError("题目格式不正确")
        item_id = str(raw.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item_id) or item_id in seen:
            raise ValueError("试卷题目标识为空或重复")
        seen.add(item_id)
        source = str(raw.get("sourceQId") or "")
        if len(source) > 32:
            raise ValueError("题库题号格式不正确")
        # 首次引用必须来自当前课程的已发布题；保存过的快照不依赖原题继续存在。
        if source and old_items.get(item_id, {}).get("sourceQId") != source:
            row = db.query(Question).filter(Question.course_id == course_id,
                                          Question.q_id == source,
                                          Question.status == "published").first()
            if row is None:
                raise ValueError(f"第 {index + 1} 题不属于当前课程的已发布题库")
        question, errors = normalize_question(raw.get("question"), chapter_ids, kp_ids)
        units = score_units(scores[index] if scores is not None else raw.get("score", 0))
        if units <= 0:
            errors.append("分值必须大于零")
        issues.extend(f"第 {index + 1} 题：{error}" for error in errors)
        source_origin = old_items.get(item_id, {}).get("sourceOrigin", "")
        if source_origin not in ("bank", "exam"):
            source_origin = ""
        items.append({"id": item_id, "sourceQId": source, "sourceOrigin": source_origin,
                      "score": units / 10, "question": question})
    assigned = sum(score_units(i["score"]) for i in items)
    if assigned != total:
        issues.append(f"已分配 {assigned / 10:g} 分，须与总分 {total / 10:g} 分一致")
    return {"title": title, "totalScore": total / 10, "scoreMode": mode, "items": items}, issues


def normalize_question(raw, chapters, kps):
    if not isinstance(raw, dict):
        raise ValueError("题目内容格式不正确")
    stem = str(raw.get("stem") or "").strip()
    analysis = str(raw.get("analysis") or "").strip()
    if len(stem) > 20000 or len(analysis) > 20000:
        raise ValueError("题干或解析超过 20000 字")
    kind = str(raw.get("type") or "single")
    if kind not in TYPES:
        raise ValueError("试卷支持单选、多选、判断和填空题")
    chapter = str(raw.get("chapterId") or "")
    tags = raw.get("kpIds") or raw.get("kp_ids") or []
    if not isinstance(tags, list) or len(tags) > 100 or any(not isinstance(k, str) for k in tags):
        raise ValueError("知识点格式不正确")
    tags = list(dict.fromkeys(tags))
    if (chapter and chapter not in chapters) or any(k not in kps for k in tags):
        raise ValueError("题目的章节或知识点不属于当前课程")
    errors = [] if stem else ["题干不能为空"]
    if not tags:
        errors.append("请至少选择一个考查知识点")
    difficulty = raw.get("difficulty", 3)
    if isinstance(difficulty, bool) or difficulty not in (1, 2, 3, 4, 5):
        raise ValueError("难度应为 1～5")
    answer = str(raw.get("answer") or "").strip()
    options = raw.get("options") or []
    if kind == "blank":
        try:
            packed = pack_blank(stem, answer, options)
            options, answer = packed["options"], packed["display"]
        except ValueError as exc:
            options = []
            errors.append(str(exc))
    else:
        if not isinstance(options, list) or len(options) > 8 or any(not isinstance(o, dict) for o in options):
            raise ValueError("选项格式不正确")
        options = [{"key": str(o.get("key") or ""), "text": str(o.get("text") or "").strip()} for o in options]
        letters = [o["key"] for o in options]
        if len(options) < 2 or len(set(letters)) != len(letters) or any(k not in "ABCDEFGH" or len(k) != 1 for k in letters):
            errors.append("需有 2～8 个不同字母的选项")
        if any(not o["text"] or len(o["text"]) > 20000 for o in options):
            errors.append("选项不能为空或过长")
        answer = re.sub(r"[,，、\s]", "", answer.upper())
        if not answer or len(set(answer)) != len(answer) or any(a not in letters for a in answer):
            errors.append("答案必须对应题目选项")
        if kind in ("single", "judge") and len(answer) != 1:
            errors.append("单选题或判断题须选择一个答案")
        if kind == "multi" and len(answer) < 2:
            errors.append("多选题须至少选择两个正确答案")
        if kind == "judge" and (letters != ["A", "B"] or [o["text"] for o in options] != ["正确", "错误"]):
            errors.append("判断题选项应为 A 正确、B 错误")
        for option in options:
            option["right"] = option["key"] in answer
    figure = raw.get("figureJson") or raw.get("figure_json") or None
    if figure:
        if not isinstance(figure, dict):
            raise ValueError("题图格式不正确")
        image_url = figure.get("imageUrl") or figure.get("image_url")
        if image_url:
            parsed = urlparse(str(image_url))
            local_image = re.fullmatch(r"/resources/question-figures/[A-Za-z0-9]+/[A-Za-z0-9]+\.(?:png|jpe?g|gif|webp)", str(image_url), re.I)
            if ".." in str(image_url) or "\\" in str(image_url) or parsed.username or parsed.password or not (
                    (parsed.scheme in ("http", "https") and parsed.netloc) or local_image):
                raise ValueError("题图地址不正确")
            figure = {"imageUrl": str(image_url), "has_image": True}
        else:
            graph = figure.get("graph")
            options_graph = figure.get("options_graph")
            if not graph and not options_graph:
                raise ValueError("题图缺少图片或结构图")
            cleaned = {"has_image": True}
            if graph:
                if not isinstance(graph, dict):
                    raise ValueError("题干结构图格式不正确")
                errors.extend(validate_graph(graph))
                cleaned["graph"] = graph
            if options_graph:
                if not isinstance(options_graph, dict) or any(k not in "ABCDEFGH" or len(k) != 1 for k in options_graph):
                    raise ValueError("选项结构图格式不正确")
                for key, option_graph in options_graph.items():
                    if not isinstance(option_graph, dict):
                        raise ValueError("选项结构图格式不正确")
                    errors.extend(validate_graph(option_graph, f"选项 {key}"))
                cleaned["options_graph"] = options_graph
            figure = cleaned
    result = {"stem": stem, "type": kind, "difficulty": difficulty, "chapterId": chapter,
              "kpIds": tags, "options": options, "answer": answer, "analysis": analysis, "figureJson": figure}
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False)) > 100000:
        raise ValueError("单题内容过大")
    return result, errors


def _json_value(raw, default=None):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _question_snapshot_matches(row, snapshot: dict) -> bool:
    """判断题库来源题是否仍与试卷快照一致，避免把试卷内编辑写回原题。"""
    if not row:
        return False
    options = _json_value(row.options, []) or []
    target_options = snapshot.get("options") or []
    if snapshot.get("type") == "blank":
        try:
            packed = pack_blank(snapshot.get("stem") or "", snapshot.get("answer") or "", target_options)
            target_options = packed["options"]
            target_answer = packed["stored_answer"]
        except ValueError:
            return False
        try:
            old_packed = pack_blank(row.stem or "", row.answer or "", options)
            options = old_packed["options"]
            old_answer = old_packed["stored_answer"]
        except ValueError:
            return False
    else:
        target_answer = str(snapshot.get("answer") or "")
        old_answer = str(row.answer or "")
        options = [{"key": str(o.get("key") or ""), "text": str(o.get("text") or "")}
                   for o in options if isinstance(o, dict)]
        target_options = [{"key": str(o.get("key") or ""), "text": str(o.get("text") or "")}
                          for o in target_options if isinstance(o, dict)]
    target_figure = snapshot.get("figureJson")
    old_figure = _json_value(row.figure_json, None)
    target_kps = list(dict.fromkeys(str(x) for x in (snapshot.get("kpIds") or []) if str(x)))
    old_kps = list(dict.fromkeys(str(x) for x in (_json_value(row.kp_ids, []) or []) if str(x)))
    if row.kp_id and row.kp_id not in old_kps:
        old_kps.insert(0, row.kp_id)
    return (
        (row.stem or "") == (snapshot.get("stem") or "")
        and (row.type or "single") == (snapshot.get("type") or "single")
        and int(row.difficulty or 3) == int(snapshot.get("difficulty") or 3)
        and (row.chapter_id or "") == (snapshot.get("chapterId") or "")
        and old_kps == target_kps
        and options == target_options
        and old_answer == target_answer
        and (row.analysis or "") == (snapshot.get("analysis") or "")
        and old_figure == target_figure
    )


def _new_question_id(db) -> str:
    import uuid

    for _ in range(20):
        candidate = "EX" + uuid.uuid4().hex[:30].upper()
        if not db.query(Question.q_id).filter(Question.q_id == candidate).first():
            return candidate
    raise ValueError("暂时无法分配试卷题号，请重试")


def publish_question_snapshots(db, course_id: str, paper: dict) -> None:
    """把发布卷中新建或已在卷内修改的题目写入正式题库；草稿保存不会调用此函数。

    已发布的题目快照保持不可变：内容发生变化时创建新题号，保留旧题号上的作答记录。
    未修改的题库选题继续使用原题号，不复制原题。
    """
    from app.models.graph import GraphNode
    from app.models.question import Question

    nodes = db.query(GraphNode).filter(GraphNode.course_id == course_id).all()
    chapter_names = {n.id: n.name for n in nodes if n.graph_type == "chapter"}
    kp_names = {n.id: n.name for n in nodes if n.graph_type == "knowledge"}
    for item in paper.get("items", []):
        snapshot = item.get("question") or {}
        source_qid = str(item.get("sourceQId") or "")
        source_origin = item.get("sourceOrigin") or ""
        row = db.query(Question).filter(
            Question.course_id == course_id,
            Question.q_id == source_qid,
        ).first() if source_qid else None
        if source_origin not in ("bank", "exam") and row:
            source_origin = "exam" if row.source_ref_file == "exam_paper" else "bank"
        if source_qid and row and _question_snapshot_matches(row, snapshot):
            item["sourceOrigin"] = source_origin or "bank"
            continue

        # 新题、已删除的题库快照、以及在试卷内编辑过的题目均创建正式题目记录。
        # 不修改被选中的原题，避免影响其它试卷和既有作答记录。
        qid = _new_question_id(db)
        kp_ids = list(dict.fromkeys(str(x) for x in (snapshot.get("kpIds") or []) if str(x)))
        kp_id = kp_ids[0] if kp_ids else ""
        q_type = str(snapshot.get("type") or "single")
        options = snapshot.get("options") or []
        answer = str(snapshot.get("answer") or "")
        if q_type == "blank":
            packed = pack_blank(snapshot.get("stem") or "", answer, options)
            options, answer = packed["options"], packed["stored_answer"]
        figure = snapshot.get("figureJson")
        chapter_id = str(snapshot.get("chapterId") or "")
        chapter = chapter_names.get(chapter_id, "")
        kp_path = ([chapter] if chapter else []) + [kp_names.get(kp, kp) for kp in kp_ids]
        db.add(Question(
            q_id=qid,
            course_id=course_id,
            chapter_id=chapter_id,
            chapter=chapter,
            kp_id=kp_id,
            kp_ids=json.dumps(kp_ids, ensure_ascii=False),
            type=q_type,
            difficulty=int(snapshot.get("difficulty") or 3),
            score=5,
            status="published",
            stem=str(snapshot.get("stem") or ""),
            options=json.dumps(options, ensure_ascii=False),
            answer=answer,
            analysis=str(snapshot.get("analysis") or ""),
            kp_path=json.dumps(kp_path, ensure_ascii=False),
            pre_kp="[]",
            post_kp="[]",
            is_key=0,
            source_ref_file="exam_paper",
            source_ref_locator=str(paper.get("paperId") or "")[:32],
            figure_json=json.dumps(figure, ensure_ascii=False) if figure else None,
            has_image=bool(figure),
        ))
        item["sourceQId"] = qid
        item["sourceOrigin"] = "exam"
