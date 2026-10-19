"""界面操作目录与服务端验证。只准备界面，不执行业务写入。"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import threading
import uuid

from app.config import settings
from app.agent_st import persistence as p
from .registry import role_of

_LOCK = threading.RLock()
_CACHE = (None, {})


def action_catalogue():
    global _CACHE
    raw = (Path(settings.FRONTEND_DIR) / "assets/agent-ui-actions.json").read_bytes()
    fingerprint = sha256(raw).hexdigest()
    with _LOCK:
        if _CACHE[0] != fingerprint:
            data = json.loads(raw)
            records = data["actions"]
            index = {item["id"]: item for item in records}
            if len(index) != len(records) or data["version"] != 1:
                raise ValueError("界面操作目录版本或编号错误")
            _CACHE = (fingerprint, index)
        return deepcopy(_CACHE[1])


def role_actions(role):
    return [dict(id=a["id"], title=a["title"], view=a["view"], entity=a["entity"],
                 execution="明确请求才生成内容" if a.get("execute") else "打开或回填界面",
                 fields={key: {k: v for k, v in field.items() if k != "selector"}
                         for key, field in a["fields"].items()})
            for a in action_catalogue().values() if a["role"] == role]


def action_index(role):
    records = role_actions(role)
    if not records:
        return ""
    return "实际界面操作入口（用 prepare_ui_action；内部编号不写进回答）：\n" + "\n".join(
        f"{a['id']} | {a['title']} | {a['execution']} | 对象:{a['entity'] or '无'} | 可填:" +
        (','.join(f"{key}:{field['type']}" + (f"={field['enum']}" if 'enum' in field else '')
                  for key, field in a['fields'].items()) or '无')
        for a in records)


def validate_values(spec, values):
    if not isinstance(values, dict) or set(values) - set(spec["fields"]):
        raise ValueError("含该界面未支持的回填字段")
    if len(json.dumps(values, ensure_ascii=False)) > 100000:
        raise ValueError("回填内容过长，请分批操作")
    cleaned = {}
    for key, value in values.items():
        field = spec["fields"][key]
        kind = field["type"]
        valid = ((kind == "string" and isinstance(value, str))
                 or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
                 or (kind == "boolean" and isinstance(value, bool))
                 or (kind == "array" and isinstance(value, list) and len(value) <= 100))
        if not valid:
            raise ValueError(f"字段 {key} 的类型或数量不正确")
        if "enum" in field and value not in field["enum"]:
            raise ValueError(f"字段 {key} 的选项不受支持")
        if isinstance(value, str) and not field.get("minLength", 0) <= len(value) <= field.get("maxLength", 20000):
            raise ValueError(f"字段 {key} 的长度不正确")
        if kind == "integer" and not field.get("minimum", -100000) <= value <= field.get("maximum", 100000):
            raise ValueError(f"字段 {key} 超出范围")
        if key in ("kpIds", "chapterIds", "sections") and not all(isinstance(v, str) for v in value):
            raise ValueError(f"字段 {key} 必须是文本数组")
        if key == "types":
            aliases = {
                "single": "single", "单选": "single", "单选题": "single",
                "multi": "multi", "多选": "multi", "多选题": "multi",
                "blank": "blank", "填空": "blank", "填空题": "blank",
                "judge": "judge", "判断": "judge", "判断题": "judge",
            }
            mapped = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("题型必须是文本数组")
                key_name = aliases.get(item.strip()) or aliases.get(item.strip().lower())
                if not key_name:
                    raise ValueError("题型只能是单选、多选、填空或判断")
                if key_name not in mapped:
                    mapped.append(key_name)
            if not mapped:
                raise ValueError("请至少指定一种题型")
            cleaned[key] = mapped
            continue
        cleaned[key] = value
    return cleaned


def resolve_object(db, ctx, entity, object_id="", keyword=""):
    role, course = role_of(ctx), str(ctx.extra.get("courseId") or "")
    if role != "admin" and course:
        member = db.query(p.UserCourse).filter(p.UserCourse.course_id == course, p.UserCourse.user_id == ctx.user_id).first()
        if not member:
            raise ValueError("你不属于当前课程，不能打开其中的对象")
    if not entity:
        return None
    if entity not in ("user", "course") and not course:
        raise ValueError("请先选择课程")
    if entity == "student":
        query = db.query(p.User).join(p.UserCourse, p.UserCourse.user_id == p.User.user_id).filter(
            p.UserCourse.course_id == course, p.User.role == "student")
        id_col, name_col = p.User.user_id, p.User.name
    elif entity == "user" and role == "admin":
        query, id_col, name_col = db.query(p.User), p.User.user_id, p.User.username
    elif entity == "course":
        query = db.query(p.Course).join(p.UserCourse, p.UserCourse.course_id == p.Course.course_id).filter(p.UserCourse.user_id == ctx.user_id)
        id_col, name_col = p.Course.course_id, p.Course.name
    elif entity in ("chapter", "kp"):
        query = db.query(p.GraphNode).filter(p.GraphNode.course_id == course, p.GraphNode.graph_type == ("chapter" if entity == "chapter" else "knowledge"))
        id_col, name_col = p.GraphNode.id, p.GraphNode.name
    elif entity == "question":
        query = db.query(p.Question).filter(p.Question.course_id == course)
        id_col, name_col = p.Question.q_id, p.Question.stem
        if role == "student":
            query = query.filter(p.Question.status == "published")
    elif entity == "resource":
        query = db.query(p.Resource).filter(p.Resource.course_id == course)
        id_col, name_col = p.Resource.res_id, p.Resource.title
    elif entity == "alert" and role == "teacher":
        query = db.query(p.Alert).filter(p.Alert.course_id == course)
        id_col, name_col = p.Alert.alert_id, p.Alert.title
    elif entity == "draft" and role == "teacher":
        query = db.query(p.STQuestionDraft).filter(p.STQuestionDraft.course_id == course, p.STQuestionDraft.user_id == ctx.user_id)
        id_col, name_col = p.STQuestionDraft.draft_id, p.STQuestionDraft.draft_id
    elif entity == "report":
        rows = db.query(p.Report).all()
        scoped = []
        for row in rows:
            try:
                detail = json.loads(row.detail_json or "{}")
            except ValueError:
                continue
            meta = detail.get("meta", {})
            if str(meta.get("courseId") or "") != course:
                continue
            if role == "student" and (meta.get("scope") != "self" or str(meta.get("userId") or "") != ctx.user_id):
                continue
            if role == "teacher" and meta.get("scope") == "self":
                continue
            if (object_id and row.report_id == object_id) or (keyword and keyword in row.title):
                scoped.append({"id": row.report_id, "name": row.title})
        return _unique(scoped)
    else:
        raise ValueError("当前角色不支持该对象")
    if object_id:
        rows = query.filter(id_col == object_id).limit(2).all()
    elif keyword.strip():
        rows = query.filter(name_col == keyword.strip()).limit(9).all()
        if not rows:
            rows = query.filter(name_col.contains(keyword.strip(), autoescape=True)).limit(9).all()
    else:
        raise ValueError("请提供要打开对象的名称或编号")
    return _unique([{"id": str(getattr(row, id_col.key)), "name": str(getattr(row, name_col.key) or "")} for row in rows])


def _unique(matches):
    if not matches:
        raise ValueError("当前权限范围内未找到该对象，请核对名称")
    if len(matches) != 1:
        return {"ambiguous": True, "choices": matches}
    return matches[0]


def prepare_action(ctx, target, values=None, object_id="", keyword="", auto=False, use_attachments=False):
    if not isinstance(target, str) or len(target) > 128:
        return {"error": "界面入口编号格式不正确"}
    spec = action_catalogue().get(target)
    role = role_of(ctx)
    if not spec or spec["role"] != role:
        return {"error": "当前角色不能执行这个界面入口"}
    try:
        if spec['view']:
            from .system_guide import allowed_views
            if spec['view'] not in allowed_views(role):
                raise ValueError("该页面已从当前角色的界面移除，请重新查询入口")
        if not isinstance(auto, bool) or not isinstance(use_attachments, bool):
            raise ValueError("执行方式必须是布尔值")
        if spec.get('execute') and not auto:
            raise ValueError("生成内容必须是明确请求；询问位置请选择对应配置或页面入口")
        if spec.get('execute') and not ctx.extra.get('courseId'):
            raise ValueError("请先选择课程再生成")
        if target == "teacher.question.create" and not ({} if values is None else values).get("kpIds"):
            raise ValueError("请先确定要出题的知识点")
        if not isinstance(object_id, str) or not isinstance(keyword, str) or len(keyword) > 20000 or len(object_id) > 64:
            raise ValueError("对象名称或编号格式不正确")
        fields = validate_values(spec, {} if values is None else values)
        if "options" in fields:
            opts = fields["options"]
            if not 2 <= len(opts) <= 8 or any(not isinstance(o, dict) or not isinstance(o.get("key"), str) or len(o["key"]) != 1 or o["key"] not in "ABCDEFGH" or not isinstance(o.get("text"), str) or not o["text"].strip() for o in opts) or len({o["key"] for o in opts}) != len(opts):
                raise ValueError("选项需为 2～8 个不同字母且内容非空")
        with p.SessionLocal() as db:
            obj = resolve_object(db, ctx, spec["entity"], object_id, keyword)
            if obj and obj.get("ambiguous"):
                return {"needsChoice": True, "choices": obj["choices"], "note": "有多个匹配对象，请让用户选择后再准备界面"}
            course = str(ctx.extra.get("courseId") or "")
            for field_name, graph_type in (("chapterId", "chapter"), ("kpIds", "knowledge"), ("chapterIds", "chapter")):
                ids = fields.get(field_name, [])
                ids = [ids] if isinstance(ids, str) and ids else ids
                if not ids:
                    continue
                actual = {r.id for r in db.query(p.GraphNode).filter(p.GraphNode.course_id == course, p.GraphNode.graph_type == graph_type, p.GraphNode.id.in_(ids))}
                if actual != set(ids):
                    raise ValueError("回填的章节或知识点不属于当前课程")
            if target == "teacher.question.import" and fields.get("questions"):
                from app.services.question_preview import preview_questions
                preview = preview_questions(db, course, questions=fields["questions"])
                if not preview["ready"]:
                    return {"error": "题目内容需要修正后再准备导入", "validation": preview["errors"]}
                fields["questions"] = preview["questions"]
        attachments = []
        if use_attachments:
            if not (spec["file_input"] or spec["handler"] in ("question-import", "account-import")):
                raise ValueError("该界面不接受附件")
            attachments = [{"attachmentId": a["attachment_id"], "name": a["name"], "mimeType": a.get("mime_type", "")}
                           for a in ctx.extra.get("attachments", []) if a.get("attachment_id")]
            if not attachments:
                raise ValueError("本轮没有可用附件，请上传后重试")
        plan = {"id": uuid.uuid4().hex, "target": target, "label": ("" if spec.get('execute') else "打开") + spec["title"], "role": role,
                "userId": ctx.user_id, "courseId": str(ctx.extra.get("courseId") or ""), "auto": bool(auto),
                "values": fields, "object": obj, "attachments": attachments}
        ctx.tool_log.append({"kind": "ui_action", "plan": plan})
        ctx.turn["system_guide"] = {"found": True}
        if spec.get("execute") == "teacher-question-create":
            note = "前端将在对话右侧预览生成题目草稿；尚未进入正式题库。不要声称已经发布，也不要让用户去出题页再点生成。"
        elif spec.get("execute"):
            note = "前端收到后将生成当前课程的学情报告并打开详情；工具本身未生成报告，不能声称已成功。"
        else:
            note = "前端收到后才会打开或回填；保存、发送、加入和正式导入仍需用户在目标界面确认。练习只打开题目，不选择或提交答案。"
        return {"ok": True, "ui_action": plan, "note": note}
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}
