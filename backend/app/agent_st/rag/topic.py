"""主题定位：把用户的一句话定位到本课程的「章 + 知识点」。

数据基础是主库规范（见 docs/主库数据规范.md）：
  - 章 `CH01..CH09`、知识点 `KP001..KP026`，来自 `graph_nodes`
  - 题号用 `questions.q_id`（字符串）

定位分两层，**两层都不含任何课程专属术语**（换课程自动生效）：

  1) 术语匹配（读主库 `graph_nodes`）
     本课程 26 个知识点名称本身就是这门课的真实术语表 ——
     「树形查找」「二叉树遍历」都是 KP 名，所以直接拿名称做匹配即可，
     不需要任何写死的关键词列表，也不需要教师额外配置。
     匹配时按名称长度降序，并把已命中的片段从待匹配文本里挖掉，
     所以「树形查找」命中 KP020 后不会再被「查找」抢一次；
     而「栈和队列」会同时命中两个 KP（多知识点场景）。

  2) RAG 投票兜底（读 `st/rag.db`）
     术语层没命中时（自然语言长描述、表里没有的说法），用检索命中的切片投票：
     每个切片按 `kp_ids` 等权累计其得分，取得分最高的 KP。
     **必须用 `kp_ids` 而非 `kp_id`** —— 切片只把主 KP 写进 `kp_id`，
     用它投票会漏掉「插入与交换排序」这类挂多 KP 的课件。

历史说明：更早的实现是代码里写死一张「关键词 → kp_id」表（含 KP010/KP020
这类课程专属编号），换课程即全部失效 —— 已随本次改造删除。

多 KP 语义与主库/题库管理侧保持一致：
`kp_id` = 主 KP（`kp_ids` 首个，供组卷/统计/掌握度），`kp_ids` = 完整列表。
"""
from __future__ import annotations

import re
from collections import defaultdict

from app.agent_st.rag import structure
from app.agent_st.rag.bank import get_question

# ---- RAG 投票参数 ----
VOTE_TOP_K = 20        # 参与投票的切片数
VOTE_MIN_SCORE = 2.0   # 最高票低于此值 → 判低置信，保持 uncertain（不硬指）
VOTE_TOP1_RATIO = 1.6  # Top1 得分不足 Top2 的该倍数 → 视为并列（双主题），两个都取
VOTE_MAX_KPS = 2       # 投票最多取几个 KP

# 显式 id 标记（学生可以直接说题号/知识点）。
# 题号要同时满足「已知前缀」+「至少含一个字母数字」，否则会把 Question 这类英文词误判成题号。
Q_ID_RE = re.compile(r"\b((?:KHD|AI|QD|Q)[0-9A-Za-z_]*\d[0-9A-Za-z_]*)\b", re.I)
KP_ID_RE = re.compile(r"\b(KP\d{1,4})\b", re.I)
CHAPTER_ID_RE = re.compile(r"\b(CH0?[1-9])\b", re.I)
CHAPTER_CN_RE = re.compile(r"第\s*([1-9])\s*章")


# ------------------------------------------------------------------
# 第一层：术语匹配（数据全部来自主库，代码零课程术语）
# ------------------------------------------------------------------
def course_terms(course_id: str) -> list[tuple[str, str]]:
    """本课程真实术语表 = `(知识点名称, kp_id)`，按名称长度降序。

    直接取自 `graph_nodes.name`。不同课程走的是**同一个函数**，
    拿到的自然是各自课程的知识点术语 —— 这正是「按课程取真实关键词表」。
    """
    terms = [(kp["name"], kp["id"]) for kp in structure.list_kps(course_id) if kp["name"]]
    return sorted(terms, key=lambda item: len(item[0]), reverse=True)


def match_terms(course_id: str, text: str) -> list[dict]:
    """术语匹配：返回命中的知识点信息列表（长名优先，可多个）。

    命中后把该片段从待匹配文本中挖掉，避免短名称重复命中同一处
    （否则「树形查找」会被「查找」再命中一次）。
    """
    rest = str(text or "").strip().lower()
    if not rest:
        return []
    hits: list[dict] = []
    seen: set[str] = set()
    for term, kp_id in course_terms(course_id):
        key = term.lower()
        if not key or key not in rest:
            continue
        info = structure.kp_info(course_id, kp_id)
        if not info or kp_id in seen:
            continue
        seen.add(kp_id)
        hits.append(info)
        rest = rest.replace(key, " ")
    return hits


# ------------------------------------------------------------------
# 第二层：RAG 投票兜底
# ------------------------------------------------------------------
def _kps_of_hit(hit: dict) -> list[str]:
    """单条切片涉及的知识点：主 KP + kp_ids（去重保序）"""
    primary = str(hit.get("kp_id") or "").strip()
    raw = hit.get("kp_ids")
    extra = [str(x).strip() for x in raw] if isinstance(raw, list) else []
    out: list[str] = []
    for kp in ([primary] if primary else []) + extra:
        if kp and kp not in out:
            out.append(kp)
    return out


def vote_by_retrieval(course_id: str, query: str, top_k: int = VOTE_TOP_K) -> list[tuple[str, float]]:
    """按检索命中的切片对知识点投票，返回 `[(kp_id, score)]` 降序。

    只读 rag.db；`retrieve_chunks` 在 course_id 缺失时返回空集（fail-closed）。
    """
    from app.agent_st.rag.retrieve import retrieve_chunks

    hits = retrieve_chunks(query=query, course_id=course_id or None, top_k=top_k)
    votes: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for hit in hits:
        score = float(hit.get("score") or 0.0)
        for kp in _kps_of_hit(hit):
            votes[kp] += score
            counts[kp] += 1
    return sorted(votes.items(), key=lambda kv: (-kv[1], -counts[kv[0]]))


def vote_pick(course_id: str, query: str, top_k: int = VOTE_TOP_K) -> list[str]:
    """投票选出知识点 id 列表（可为空 = 低置信）。"""
    ranked = vote_by_retrieval(course_id, query, top_k=top_k)
    if not ranked or ranked[0][1] < VOTE_MIN_SCORE:
        return []
    picked = [ranked[0][0]]
    if len(ranked) > 1 and ranked[0][1] < ranked[1][1] * VOTE_TOP1_RATIO:
        picked.append(ranked[1][0])
    return [kp for kp in picked if structure.kp_info(course_id, kp)][:VOTE_MAX_KPS]


# ------------------------------------------------------------------
# 结果组装
# ------------------------------------------------------------------
def _blank(query: str) -> dict:
    return {
        "uncertain": True,
        "kp_id": None,
        "kp_ids": [],
        "kp_name": None,
        "kp_names": [],
        "chapter_id": None,
        "chapter_name": None,
        "q_id": None,
        "course_title": "",
        "matched_by": None,
        "query": query,
    }


def _fill_from_kps(result: dict, course_id: str, kp_ids: list[str], matched_by: str) -> bool:
    """填入知识点（可多个）。主 KP = 首个，章取主 KP 所在章 —— 与主库口径一致。"""
    infos: list[dict] = []
    for kp_id in kp_ids:
        info = structure.kp_info(course_id, str(kp_id).strip())
        if info and info["kp_id"] not in {i["kp_id"] for i in infos}:
            infos.append(info)
    if not infos:
        return False
    head = infos[0]
    result.update({
        "kp_id": head["kp_id"],
        "kp_ids": [i["kp_id"] for i in infos],
        "kp_name": head["kp_name"],
        "kp_names": [i["kp_name"] for i in infos],
        "chapter_id": head["chapter_id"],
        "chapter_name": head["chapter_name"],
        "uncertain": False,
        "matched_by": matched_by,
    })
    return True


def _fill_from_kp(result: dict, course_id: str, kp_id: str, matched_by: str) -> bool:
    return _fill_from_kps(result, course_id, [kp_id], matched_by)


def _fill_chapter(result: dict, course_id: str, chapter_id: str, matched_by: str) -> bool:
    ch_name = structure.chapter_name_by_id(course_id, chapter_id)
    if not ch_name:
        return False
    result.update({
        "chapter_id": chapter_id, "chapter_name": ch_name,
        "uncertain": False, "matched_by": matched_by,
    })
    return True


def _suggestions(course_id: str) -> list[str]:
    return [f"{kp['chapter']} / {kp['name']}" for kp in structure.list_kps(course_id)[:8]]


def resolve_topic(
    course_id: str,
    text: str = "",
    kp_id: str | None = None,
    chapter_id: str | None = None,
    q_id: str | None = None,
) -> dict:
    """定位主题。

    优先级：显式题号 > 显式知识点 > 显式章 > 文本中的 id > 「第N章」 >
            术语匹配（本课知识点名称）> RAG 投票兜底。
    """
    query = str(text or "").strip()
    result = _blank(query)
    if not course_id:
        return result
    result["course_title"] = structure.course_name(course_id)

    # 1) 题号（显式传入，或文本里出现 KHD001 / AI3F8A21 这类 token）
    target_q = str(q_id or "").strip()
    if not target_q:
        m = Q_ID_RE.search(query)
        if m:
            target_q = m.group(1).upper()
    if target_q:
        item = get_question(course_id, target_q, include_answer=False)
        if item:
            kp_ids = [str(x) for x in (item.get("kp_ids") or []) if str(x).strip()]
            if item.get("kp_id") and item["kp_id"] not in kp_ids:
                kp_ids.insert(0, item["kp_id"])
            result.update({
                "q_id": item["q_id"],
                "kp_id": item.get("kp_id") or None,
                "kp_ids": kp_ids,
                "kp_name": item.get("kp_name") or None,
                "kp_names": [item["kp_name"]] if item.get("kp_name") else [],
                "chapter_id": item.get("chapter_id") or None,
                "chapter_name": item.get("chapter") or None,
                "uncertain": False,
                "matched_by": "q_id",
            })
            return result

    # 2) 显式知识点（可能是多个）
    ctx_kps = kp_id if isinstance(kp_id, (list, tuple)) else [kp_id] if kp_id else []
    if ctx_kps and _fill_from_kps(result, course_id, [str(x) for x in ctx_kps], "context_kp"):
        return result

    # 3) 显式章
    if chapter_id and _fill_chapter(result, course_id, str(chapter_id).strip(), "context_chapter"):
        return result

    # 4) 文本中的 KP id
    m = KP_ID_RE.search(query)
    if m and _fill_from_kp(result, course_id, m.group(1).upper(), "text_kp"):
        return result

    # 5) 文本中的 CH id
    m = CHAPTER_ID_RE.search(query)
    if m:
        cid = m.group(1).upper()
        cid = cid if len(cid) == 4 else f"CH0{cid[-1]}"
        if _fill_chapter(result, course_id, cid, "text_chapter"):
            return result

    # 6) 「第N章」→ 先定章，再尝试在**该章内**定到知识点
    #    （否则「第6章 二叉树遍历」只会得到章、丢掉更精确的知识点归属）
    m = CHAPTER_CN_RE.search(query)
    if m:
        num = int(m.group(1))
        for ch in structure.list_chapters(course_id):
            if ch["name"].startswith(f"第{num}章"):
                result.update({
                    "chapter_id": ch["id"], "chapter_name": ch["name"],
                    "uncertain": False, "matched_by": "chapter_cn",
                })
                for info in match_terms(course_id, query):
                    if info["chapter_id"] == ch["id"]:
                        result.update({
                            "kp_id": info["kp_id"], "kp_ids": [info["kp_id"]],
                            "kp_name": info["kp_name"], "kp_names": [info["kp_name"]],
                            "matched_by": f"chapter_cn+term:{info['kp_name']}",
                        })
                        break
                return result

    # 7) 术语匹配（本课知识点名称，长名优先，可多个）
    infos = match_terms(course_id, query)
    if infos and _fill_from_kps(result, course_id, [i["kp_id"] for i in infos],
                                "term:" + ",".join(i["kp_name"] for i in infos)):
        return result

    # 8) RAG 投票兜底（自然语言长描述 / 术语表没有的说法）
    picked = vote_pick(course_id, query)
    if picked:
        ranked = dict(vote_by_retrieval(course_id, query))
        if _fill_from_kps(result, course_id, picked,
                          "rag_vote:" + ",".join(f"{k}={ranked.get(k, 0):.2f}" for k in picked)):
            return result

    # 未命中：给出可选项，便于模型/前端提示
    result["suggestions"] = _suggestions(course_id)
    return result


_COURSE_HINTS = (
    "定义", "实现", "算法", "复杂度", "遍历", "结点", "节点", "指针", "递归",
    "数据结构", "课件", "教材", "ppt",
)


def looks_like_course_question(text: str, course_id: str = "") -> bool:
    """粗判是否像本课问题：有 id 标记/章节，或命中本课知识点名称/课程通用词。

    传入 course_id 时会做知识点名称匹配（数据驱动）；不传则只做通用判断。
    """
    query = str(text or "").strip()
    if not query:
        return False
    if Q_ID_RE.search(query) or KP_ID_RE.search(query) or CHAPTER_ID_RE.search(query) \
            or CHAPTER_CN_RE.search(query):
        return True
    if course_id and match_terms(course_id, query):
        return True
    return any(hint in query for hint in _COURSE_HINTS)
