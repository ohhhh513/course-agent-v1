"""三端操作目录：静态界面事实，不访问业务数据库、不执行界面操作。"""
from __future__ import annotations

from functools import lru_cache
import logging
import os
import re
import unicodedata

import yaml

from app.agent_st.agent.config import AGENT_DIR

LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def catalogue() -> dict:
    data = yaml.safe_load((AGENT_DIR / "system_features.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data.get("roles", {})) != {"student", "teacher", "admin"}:
        raise ValueError("系统操作目录必须包含三种角色")
    for role in data["roles"]:
        records = features_for_role(role, data)
        ids = [record["id"] for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{role} 操作目录含重复 id")
        for record in records:
            if not record["title"] or not record["steps"] or not record["anchors"]:
                raise ValueError(f"操作目录缺少标题、步骤或代码锚点：{record['id']}")
    return data


def _manual_allowed_views(role: str) -> tuple[str, ...]:
    return tuple(catalogue()["roles"].get(role, {}).get("pages", {}))


def allowed_views(role: str) -> tuple[str, ...]:
    original = _manual_allowed_views(role)
    if not original or os.getenv("SYSTEM_GUIDE_MODE", "code") == "manual":
        return original
    try:
        from .system_code_index import get_code_index
        index = get_code_index()
        index.refresh()
        # 新路由需同时接通前端导航权限；移除的入口立即失效。
        return tuple(view for view in original if view in index.pages.get(role, {}))
    except (OSError, ValueError, KeyError, TypeError):
        LOG.warning("无法核对当前导航，使用原页面白名单", exc_info=True)
        return original


def features_for_role(role: str, data: dict | None = None) -> list[dict]:
    data = data if data is not None else catalogue()
    spec = data["roles"].get(role)
    if spec is None:
        return []
    records = []
    for view, page in spec["pages"].items():
        for feature in page.get("features", []):
            records.append({**feature, "view": view, "page": page["title"],
                            "source": feature.get("source", page["source"]), "location": feature.get("location", page["title"]),
                            "prerequisites": feature.get("prerequisites", page.get("prerequisites", [])),
                            "navigation": feature.get("navigation", True)})
    chat_view = spec["chat_view"]
    for feature in data.get("shared", []):
        records.append({**feature, "view": chat_view, "page": spec["pages"][chat_view]["title"],
                        "source": feature.get("source", "assets/js/shared/agent-chat.js"), "prerequisites": [],
                        "navigation": feature.get("navigation", True)})
    return records


def _manual_feature_index(role: str) -> str:
    """给模型完整、紧凑的目录，具体步骤仍通过工具查询。"""
    records = features_for_role(role)
    if not records:
        return ""
    lines = ["当前登录角色可用的系统操作目录（内部 id 仅供 get_system_guide 调用，不写进回答）："]
    for item in records:
        aliases = "、".join(item.get("aliases", []))
        lines.append(f"{item['id']} | {item['page']} | {item['title']}" + (f"（{aliases}）" if aliases else ""))
    return "\n".join(lines)


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).lower())


def _grams(value: str) -> set[str]:
    value = _normalize(value)
    return {value[i:i + 2] for i in range(max(0, len(value) - 1))}


def _lookup_manual_guide(role: str, query: str = "", feature_id: str = "", view: str = "", limit: int = 4) -> dict:
    if role not in catalogue()["roles"]:
        return {"error": "无法确认登录角色，不能提供操作入口"}
    if view and view not in _manual_allowed_views(role):
        return {"error": "该页面不属于当前角色，不能跳转或提供操作权限"}
    records = features_for_role(role)
    if feature_id:
        matches = [item for item in records if item["id"] == feature_id and (not view or item["view"] == view)]
        if not matches:
            return {"error": "当前角色没有这个操作入口，请按当前角色的目录选择功能"}
    else:
        if not query.strip() and not view:
            return {"error": "请提供问题、功能 id 或页面 view"}
        records = [item for item in records if not view or item["view"] == view]
        needle, grams = _normalize(query), _grams(query)
        def score(item):
            terms = [item["title"], *item.get("aliases", [])]
            exact = max((len(_normalize(term)) for term in terms
                         if _normalize(term) and _normalize(term) in needle), default=0)
            text = " ".join([item["page"], item["location"], *terms, *item["steps"]])
            return exact * 3 + len(grams & _grams(text)) / max(1, len(grams))
        matches = sorted(records, key=score, reverse=True) if needle else records
        matches = [item for item in matches if not needle or score(item) >= .2]
        matches = matches[:max(1, min(int(limit), 12))]
    if not matches:
        return {"found": False, "features": [], "note": "目录未找到已实现入口；不要凭空编造按钮或步骤，可请用户说明目标"}
    return {"found": True, "role": role, "features": [
        {key: item.get(key, []) if key in ("notes", "prerequisites") else item[key]
         for key in ("id", "title", "page", "view", "location", "steps", "prerequisites", "notes", "navigation")}
        for item in matches],
        "note": "本工具只查询位置，不会生成按钮。目标明确且有可执行入口时，最终回答前必须调用 prepare_ui_action：询问auto=false给按钮，明确打开auto=true。指代从最近对话确定；不能仅写步骤或在未成功准备入口时声称有按钮。"}


def feature_index(role: str) -> str:
    if role not in catalogue()["roles"]:
        return ""
    if os.getenv("SYSTEM_GUIDE_MODE", "code") == "manual":
        return _manual_feature_index(role)
    try:
        from .system_code_index import get_code_index
        return get_code_index().page_index(role)
    except (OSError, ValueError, KeyError, TypeError):
        LOG.warning("界面源码索引不可用，提示词使用原操作目录", exc_info=True)
        return _manual_feature_index(role)


def lookup_guide(role: str, query: str = "", feature_id: str = "", view: str = "", limit: int = 4) -> dict:
    manual = _lookup_manual_guide(role, query, feature_id, view, limit)
    if "error" in manual or os.getenv("SYSTEM_GUIDE_MODE", "code") == "manual":
        return manual
    try:
        from .system_code_index import get_code_index
        index = get_code_index()
        # 原 feature_id 仍兼容；新按钮直接按问题/中文名称/绑定 id 查源码，无需手工登记。
        search_query = query or (manual.get("features", [{}])[0].get("title", "") if feature_id else "")
        result = index.search(role, search_query, view, limit)
        records = {r["id"]: r for r in features_for_role(role)}
        supplements = []
        for item in manual.get("features", []):
            record = records[item["id"]]
            source = index.files.get(record["source"], {}).get("text", "")
            # 补充资料有时引用路由中的固定文案；只校验仓库自带手册的源码锚点。
            # 模型不能传路径，不把这些额外文件当成当前角色的可检索源码。
            if not source:
                path = (index.root / record["source"]).resolve()
                if (path.is_relative_to(index.root) and path.suffix in (".js", ".py", ".html")
                        and path.is_file() and path.stat().st_size <= 2_000_000):
                    source = path.read_text(encoding="utf-8")
            if item["view"] in index.pages.get(role, {}) and source and all(a in source for a in record["anchors"]):
                supplements.append(item)
        return {**result, "role": role, "features": supplements,
                "found": bool(result.get("found") or supplements), "mode": "code",
                "note": "sources 是当前源码证据，优先于 features 旧手册补充。追踪实际渲染入口、事件绑定和调用，"
                        "不足时继续用 query=按钮id/函数名、view=所属页面 查询关联片段。"
                        "未调用函数、演示模板或已移除入口不能当作可用功能。"
                        "本工具只查询位置，不会生成按钮。操作目标明确且ui_actions中有入口时，最终回答前必须另调prepare_ui_action："
                        "询问auto=false给真实按钮，明确打开auto=true；按最近对话解析指代，具体入口优先于普通导航。"
                        "只写必要中文位置和步骤，不输出代码；没有成功准备入口，不许声称有按钮。"}
    except (OSError, ValueError, KeyError, TypeError):
        LOG.warning("界面源码查询失败，使用原操作手册", exc_info=True)
        return {**manual, "mode": "manual_fallback",
                "warning": "实时源码不可用，以下为原手册；可能未反映新改动，不应声称已核实当前按钮"}
