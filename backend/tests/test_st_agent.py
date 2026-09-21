"""agent_st 集成测试。

覆盖：课程结构查询 / 出题校验 / 题库访问 / RAG 课程隔离 / demo 运行时
（hermetic，不发外网、不碰正式库）

结构规范：章 CH01-09 + 知识点 KP001-026（见 docs/主库数据规范.md）。
「王道小节」相关的旧测试已随该体系一并删除。
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

COURSE_A = "C_TEST_A"
COURSE_B = "C_TEST_B"

CHAPTER_A = "CH01"
CHAPTER_B = "CH02"
KP_A1, KP_A2 = "KP001", "KP002"
KP_B1 = "KP021"
CHAPTER_A_NAME = "第1章 测试绪论"
CHAPTER_B_NAME = "第2章 测试线性表"


@pytest.fixture()
def st_env(tmp_path, monkeypatch):
    """hermetic 环境：临时 rag.db / 草稿目录 / 正式库；embedding 走本地哈希；强制 demo 模式"""
    from app import config as app_config
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(app_config.settings, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(app_config.settings, "LLM_API_KEY", "")
    monkeypatch.setattr(app_config.settings, "AGENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(app_config.settings, "RAG_DB_PATH", tmp_path / "rag.db")

    from app.agent_st import settings_bridge

    s = settings_bridge._bridge.refresh()

    from app.models import user, course, graph, question, practice, ai, alert, intervention, checkin  # noqa: F401
    from app.models import agent_st  # noqa: F401
    from app.models.course import Course
    from app.models.graph import GraphNode
    from app.models.question import Question

    tmp_engine = create_engine(
        f"sqlite:///{tmp_path / 'main.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=tmp_engine)
    from app.agent_st import persistence

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=tmp_engine)
    monkeypatch.setattr(persistence, "SessionLocal", TestSession)

    db = TestSession()
    db.add(Course(course_id=COURSE_A, name="测试课程A"))
    db.add(Course(course_id=COURSE_B, name="测试课程B"))
    # 课程结构：章 + 知识点（knowledge.chapter 存的是章名）
    graph_seed = [
        (CHAPTER_A, "chapter", CHAPTER_A_NAME, "", COURSE_A),
        (KP_A1, "knowledge", "测试知识点一", CHAPTER_A_NAME, COURSE_A),
        (KP_A2, "knowledge", "测试知识点二", CHAPTER_A_NAME, COURSE_A),
        (CHAPTER_B, "chapter", CHAPTER_B_NAME, "", COURSE_B),
        (KP_B1, "knowledge", "B课程知识点", CHAPTER_B_NAME, COURSE_B),
    ]
    for gid, gtype, name, chapter, cid in graph_seed:
        db.add(GraphNode(id=gid, graph_type=gtype, name=name, chapter=chapter, course_id=cid))

    def _opts(right_key, texts):
        return json.dumps(
            [{"key": k, "text": t, "right": k == right_key} for k, t in texts],
            ensure_ascii=False,
        )

    db.add(Question(
        q_id="QTEST_A1", course_id=COURSE_A, chapter_id=CHAPTER_A, chapter=CHAPTER_A_NAME,
        kp_id=KP_A1, type="single", status="published",
        stem="测试题干A：KMP 算法 next 数组怎么求",
        options=_opts("A", [("A", "选项甲"), ("B", "选项乙"), ("C", "选项丙"), ("D", "选项丁")]),
        answer="A", analysis="测试解析A：KMP 的核心是 next 数组", difficulty=3,
    ))
    db.add(Question(
        q_id="QTEST_B1", course_id=COURSE_B, chapter_id=CHAPTER_B, chapter=CHAPTER_B_NAME,
        kp_id=KP_B1, type="single", status="published", stem="测试题干B：线性表",
        options=_opts("B", [("A", "甲"), ("B", "乙"), ("C", "丙"), ("D", "丁")]),
        answer="B", analysis="测试解析B", difficulty=3,
    ))
    db.commit()
    db.close()

    from app.agent_st.agent import llm

    monkeypatch.setattr(llm, "chat_available", lambda: False)

    yield s

    settings_bridge._bridge.refresh()


def _valid_payload(q_id="AI001", kp_id=KP_A1, chapter_id=CHAPTER_A):
    return {
        "q_id": q_id,
        "chapter_id": chapter_id,
        "kp_id": kp_id,
        "question": "测试题干",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "answer": "B",
        "analysis": "测试解析",
        "has_image": True,
        "graph": {
            "type": "weighted_undirected_graph",
            "nodes": ["A", "B", "C"],
            "edges": [{"from": "A", "to": "B", "weight": 1}, {"from": "B", "to": "C", "weight": 2}],
        },
    }


VALID = _valid_payload()


# ---------------- 图规格 ----------------
def test_figure_mode_priority():
    from app.agent_st.rag.figures import figure_mode

    assert figure_mode({"options_graph": {"A": {"type": "tree", "nodes": ["1"], "edges": []}}}) == "option-figures"
    assert figure_mode({"graph": {"type": "adjacency_matrix", "nodes": ["A"], "matrix": [[0]]}}) == "matrix"
    assert figure_mode({"graph": {"type": "tree", "nodes": ["1"], "edges": []}}) == "stem-figure"
    assert figure_mode({"has_image": True}) == "text"


# ---------------- 课程结构（主库规范） ----------------
def test_structure_reads_graph_nodes(st_env):
    from app.agent_st.rag import structure

    chapters = structure.list_chapters(COURSE_A)
    assert [c["id"] for c in chapters] == [CHAPTER_A]
    assert chapters[0]["name"] == CHAPTER_A_NAME

    assert {k["id"] for k in structure.list_kps(COURSE_A)} == {KP_A1, KP_A2}

    info = structure.kp_info(COURSE_A, KP_A1)
    assert info["kp_name"] == "测试知识点一"
    # 知识点靠「章名字符串」关联到章 id
    assert info["chapter_id"] == CHAPTER_A
    assert info["chapter_name"] == CHAPTER_A_NAME

    assert structure.valid_kp_ids(COURSE_A) == {KP_A1, KP_A2}
    assert structure.valid_kp_ids(COURSE_B) == {KP_B1}
    # 跨课程不可见
    assert structure.kp_info(COURSE_B, KP_A1) is None


# ---------------- 出题 JSON 校验 ----------------
def test_validate_ok_graph(st_env):
    from app.agent_st.rag.validate import validate_question

    result = validate_question(dict(VALID), course_id=COURSE_A)
    assert result["ok"], result["errors"]


def test_validate_rejects_bad_type_and_chapter(st_env):
    from app.agent_st.rag.validate import validate_question

    bad = _valid_payload()
    bad["chapter_id"] = "CH99"
    bad["graph"] = {"type": "mindmap", "nodes": ["A"], "edges": []}
    result = validate_question(bad, course_id=COURSE_A)
    assert not result["ok"]
    assert any("type" in e for e in result["errors"])
    assert any("chapter_id" in e for e in result["errors"])


def test_validate_rejects_foreign_kp(st_env):
    from app.agent_st.rag.validate import validate_question

    result = validate_question(_valid_payload(kp_id="KP999"), course_id=COURSE_A)
    assert not result["ok"]
    assert any("kp_id" in e for e in result["errors"])


def test_validate_rejects_kp_chapter_mismatch(st_env):
    from app.agent_st.rag.validate import validate_question

    # KP001 属于 CH01，却声称在 CH02
    result = validate_question(_valid_payload(chapter_id="CH02"), course_id=COURSE_A)
    assert not result["ok"]
    assert any("不一致" in e for e in result["errors"])


def test_validate_rejects_aoe_cycle(st_env):
    from app.agent_st.rag.validate import validate_question

    bad = _valid_payload()
    bad["graph"] = {
        "type": "aoe_network",
        "nodes": ["A", "B", "C"],
        "edges": [
            {"from": "A", "to": "B", "weight": 1, "activity": "a1"},
            {"from": "B", "to": "C", "weight": 1, "activity": "a2"},
            {"from": "C", "to": "A", "weight": 1, "activity": "a3"},
        ],
    }
    result = validate_question(bad, course_id=COURSE_A)
    assert not result["ok"]
    assert any("DAG" in e for e in result["errors"])


def test_validate_detects_duplicate_q_id(st_env):
    from app.agent_st.rag.validate import validate_question

    result = validate_question(_valid_payload(q_id="QTEST_A1"), course_id=COURSE_A)
    assert not result["ok"]
    assert any("冲突" in e for e in result["errors"])


# ---------------- 题库（改读主库 questions 表） ----------------
def test_bank_reads_questions_table(st_env):
    from app.agent_st.rag.bank import existing_q_ids, get_question, next_ai_q_id, search_similar

    item = get_question(COURSE_A, "QTEST_A1")
    assert item is not None
    assert item["kp_id"] == KP_A1 and item["chapter_id"] == CHAPTER_A
    assert item["options"]["A"] == "选项甲"
    # 课程隔离：别的课程读不到
    assert get_question(COURSE_B, "QTEST_A1") is None

    assert existing_q_ids(COURSE_A) == {"QTEST_A1"}
    assert [h["q_id"] for h in search_similar(course_id=COURSE_A, kp_id=KP_A1)] == ["QTEST_A1"]
    assert search_similar(course_id=COURSE_A, kp_id=KP_B1) == []
    # AI 题号：与导入题库不同前缀 + 随机 hex，且不与正式题库撞号
    from app.agent_st.rag.bank import AI_QID_RE

    qid = next_ai_q_id(COURSE_A)
    assert AI_QID_RE.match(qid), qid
    assert qid not in existing_q_ids(COURSE_A)


def test_bank_get_question_hides_answer(st_env):
    from app.agent_st.rag.bank import get_question

    item = get_question(COURSE_A, "QTEST_A1", include_answer=False)
    assert "answer" not in item and "analysis" not in item


# ---------------- RAG ----------------
def test_embed_local_and_dims_guard():
    from app.agent_st.rag.embed import local_embed, cosine, dims_compatible

    v1 = local_embed("KMP 算法 next 数组")
    v2 = local_embed("KMP 算法 next 数组")
    v3 = local_embed("完全不同的内容 content")
    assert dims_compatible(v1, v2) and cosine(v1, v2) > 0.9
    assert dims_compatible(v1, [0.0] * 3) is False
    assert cosine(v1, v3) < cosine(v1, v2)


def test_question_bank_ingest_carries_structure(st_env):
    """题库切片来自主库 questions 表，且自带规范结构"""
    from app.agent_st.rag.ingest import ingest_question_bank
    from app.agent_st.rag.store import ChunkStore

    result = ingest_question_bank(COURSE_A)
    assert result["ok"] and result["questions"] == 1
    assert result["chunks"] == 2  # 题干 + 解析

    store = ChunkStore()
    assert store.count(COURSE_A) == 2
    assert store.count(COURSE_B) == 0
    assert store.kp_coverage(COURSE_A) == {KP_A1: 2}
    with store._conn() as conn:
        row = conn.execute(
            "SELECT chapter_id, kp_id, kp_ids, q_id, source_id FROM chunks LIMIT 1"
        ).fetchone()
    assert row["chapter_id"] == CHAPTER_A
    assert row["kp_id"] == KP_A1
    assert json.loads(row["kp_ids"]) == [KP_A1]
    assert row["q_id"] == "QTEST_A1"
    assert row["source_id"] == "__questions__"


def test_local_retrieve_by_chapter_and_kp(st_env):
    from app.agent_st.rag.ingest import ingest_question_bank
    from app.agent_st.rag.retrieve import retrieve_chunks

    ingest_question_bank(COURSE_A)
    hits = retrieve_chunks(query="KMP next 数组", course_id=COURSE_A, chapter_id=CHAPTER_A)
    assert hits, "本课程本章应有命中"
    assert all(h["course_id"] == COURSE_A for h in hits)
    assert all(h["chapter_id"] == CHAPTER_A for h in hits)
    assert all(str(h["chunk_id"]).startswith(f"{COURSE_A}:") for h in hits)

    assert retrieve_chunks(query="KMP", course_id=COURSE_A, kp_id=KP_A1)
    assert retrieve_chunks(query="KMP", course_id=COURSE_A, kp_id=KP_B1) == []


def test_ingest_resource_inherits_structure(st_env, tmp_path):
    """资源切片的结构归属继承 resources 表传进来的 chapter_id / kp_ids"""
    from app.agent_st.rag.ingest import ingest_path
    from app.agent_st.rag.retrieve import retrieve_chunks
    from app.agent_st.rag.store import ChunkStore

    doc = tmp_path / "DOC_Ch01_测试教材.txt"
    doc.write_text("KMP 算法的 next 数组用于模式串回溯。\n" * 6, encoding="utf-8")
    r = ingest_path(
        doc, course_id=COURSE_A, source_key="R001/DOC_Ch01_测试教材.txt",
        chapter_id=CHAPTER_A, kp_ids=[KP_A1, KP_A2],
    )
    assert r["ok"] and r["chunks"] > 0

    store = ChunkStore()
    assert store.count(COURSE_A) == r["chunks"]
    assert store.source_counts(COURSE_A) == {"R001/DOC_Ch01_测试教材.txt": r["chunks"]}
    # 多 KP 资源：两个 KP 都能命中
    assert retrieve_chunks(query="KMP next", course_id=COURSE_A, kp_id=KP_A1)
    assert retrieve_chunks(query="KMP next", course_id=COURSE_A, kp_id=KP_A2)

    # 按资源前缀删除只清自己
    assert store.delete_source_prefix("R001/", COURSE_A) == r["chunks"]
    assert store.count(COURSE_A) == 0


def test_retrieve_without_course_returns_empty(st_env):
    """fail-closed：没有课程上下文不得退化成全库混搜"""
    from app.agent_st.rag.ingest import ingest_question_bank
    from app.agent_st.rag.retrieve import retrieve_chunks

    ingest_question_bank(COURSE_A)
    assert retrieve_chunks(query="KMP next 数组", course_id=None) == []
    assert retrieve_chunks(query="KMP next 数组", course_id="") == []


def test_rag_isolation_between_courses(st_env):
    """两门课各自入库：切片互不可见、chunk_id 不撞车"""
    from app.agent_st.rag.ingest import ingest_question_bank
    from app.agent_st.rag.retrieve import retrieve_chunks
    from app.agent_st.rag.store import ChunkStore

    ingest_question_bank(COURSE_A)
    ingest_question_bank(COURSE_B)
    store = ChunkStore()
    assert store.count(COURSE_A) == 2 and store.count(COURSE_B) == 2
    rows = store.load_filtered(course_id=COURSE_A)
    assert all(r.chunk_id.startswith(f"{COURSE_A}:") for r in rows)
    assert all(r.course_id == COURSE_A for r in rows)

    for cid in (COURSE_A, COURSE_B):
        hits = retrieve_chunks(query="测试", course_id=cid)
        assert hits and all(h["course_id"] == cid for h in hits)


def test_delete_source_types_scoped_by_course(st_env):
    """按来源类型清理题库切片时，绝不能波及其它课程"""
    from app.agent_st.rag.ingest import ingest_question_bank
    from app.agent_st.rag.store import ChunkStore

    ingest_question_bank(COURSE_A)
    ingest_question_bank(COURSE_B)
    store = ChunkStore()
    before_b = store.count(COURSE_B)
    assert store.count(COURSE_A) > 0 and before_b > 0

    removed = store.delete_source_types(["question_stem", "question_analysis"], course_id=COURSE_A)
    assert removed > 0
    assert store.count(COURSE_A) == 0
    assert store.count(COURSE_B) == before_b, "课程 B 的题库切片被误删"


def test_store_rejects_chunk_without_course(st_env):
    from app.agent_st.rag.schema import ChunkRecord
    from app.agent_st.rag.store import ChunkStore

    bad = ChunkRecord(
        chunk_id="x-1", text="t", source_type="textbook", source_id="s",
        course_id="", chapter_id=CHAPTER_A,
    )
    with pytest.raises(ValueError):
        ChunkStore().upsert_many([bad])


def test_store_columns_have_no_course_default(st_env):
    """rag.db 的 course_id 列不得带默认值（历史 DEFAULT 'C2026DS001' 是串数据根因）"""
    import sqlite3
    from app.agent_st.rag.store import ChunkStore

    store = ChunkStore()
    with sqlite3.connect(store.path) as conn:
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    assert {"course_id", "chapter_id", "kp_id", "kp_ids", "q_id"} <= set(cols)
    assert cols["course_id"][3] == 1, "course_id 必须是 NOT NULL"
    assert cols["course_id"][4] is None, f"course_id 不应有默认值，实际={cols['course_id'][4]!r}"


# ---------------- 会话与草稿 ----------------
def test_session_and_draft_carry_course_id(st_env):
    from app.agent_st.agent.store import AgentStore
    from app.agent_st import persistence
    from app.models.ai import ChatSession

    store = AgentStore(user_id="U_ISO", course_id=COURSE_A)
    sid = store.ensure_session(None, "explain")
    saved = store.save_draft(_valid_payload())

    db = persistence.SessionLocal()
    try:
        sess = db.query(ChatSession).filter(ChatSession.session_id == sid).first()
        assert sess is not None and sess.course_id == COURSE_A
    finally:
        db.close()

    rows = store.list_drafts(user_id="U_ISO", course_id=COURSE_A)
    assert any(r["draft_id"] == saved["draft_id"] for r in rows)
    assert store.list_drafts(user_id="U_ISO", course_id=COURSE_B) == []


def test_session_cannot_be_reused_across_courses(st_env):
    from app.agent_st.agent.store import AgentStore

    sid = AgentStore(user_id="U_X", course_id=COURSE_A).ensure_session(None, "explain")
    sid2 = AgentStore(user_id="U_X", course_id=COURSE_B).ensure_session(sid, "explain")
    assert sid2 != sid


def test_reserved_q_ids_covers_bank_and_drafts(st_env):
    from app.agent_st.agent.store import AgentStore

    store = AgentStore(user_id="U_R", course_id=COURSE_A)
    assert store.reserved_q_ids() == {"QTEST_A1"}
    store.save_draft(_valid_payload(q_id="AI001"))
    store.save_draft(_valid_payload(q_id="AI002"))
    assert store.reserved_q_ids() == {"QTEST_A1", "AI001", "AI002"}


# ---------------- 主题定位（读库术语 + RAG 投票兜底） ----------------
def _add_kps(course_id, pairs, chapter=CHAPTER_A_NAME):
    from app.agent_st import persistence
    from app.models.graph import GraphNode

    db = persistence.SessionLocal()
    for kid, name in pairs:
        db.add(GraphNode(id=kid, graph_type="knowledge", name=name,
                         chapter=chapter, course_id=course_id))
    db.commit()
    db.close()


def test_resolve_topic_by_explicit_ids(st_env):
    from app.agent_st.rag.topic import resolve_topic

    r = resolve_topic(COURSE_A, kp_id=KP_A1)
    assert r["uncertain"] is False and r["matched_by"] == "context_kp"
    assert r["kp_ids"] == [KP_A1] and r["chapter_id"] == CHAPTER_A

    r = resolve_topic(COURSE_A, chapter_id=CHAPTER_A)
    assert r["chapter_id"] == CHAPTER_A and r["matched_by"] == "context_chapter"

    r = resolve_topic(COURSE_A, text="看看 CH01 的内容")
    assert r["chapter_id"] == CHAPTER_A and r["matched_by"] == "text_chapter"

    r = resolve_topic(COURSE_A, q_id="QTEST_A1")
    assert r["q_id"] == "QTEST_A1" and r["kp_id"] == KP_A1 and r["matched_by"] == "q_id"
    assert r["kp_ids"] == [KP_A1]


def test_resolve_topic_matches_course_kp_names(st_env):
    """术语来自数据库：知识点名称本身就是本课关键词，代码里不写死任何术语。

    回归：早期关键词表按书写顺序扫描，通用词「查找」会在「树形查找」里先命中。
    """
    from app.agent_st.rag.topic import course_terms, match_terms, resolve_topic

    _add_kps(COURSE_A, [("KP019", "查找"), ("KP020", "树形查找"),
                        ("KP006", "栈"), ("KP007", "队列")])

    names = dict(course_terms(COURSE_A))      # {知识点名称: kp_id}
    assert names.get("树形查找") == "KP020" and names.get("查找") == "KP019"

    # 长名优先：命中「树形查找」后不再被「查找」抢一次
    r = resolve_topic(COURSE_A, text="树形查找是怎么回事？")
    assert r["kp_id"] == "KP020" and r["kp_ids"] == ["KP020"]
    assert str(r["matched_by"]).startswith("term:")

    r = resolve_topic(COURSE_A, text="查找是什么？")
    assert r["kp_id"] == "KP019" and r["kp_ids"] == ["KP019"]

    # 双主题 → 命中多个知识点（kp_id 是主 KP，kp_ids 是完整列表）
    r = resolve_topic(COURSE_A, text="栈和队列有什么区别")
    assert set(r["kp_ids"]) == {"KP006", "KP007"}
    assert r["kp_id"] in {"KP006", "KP007"} and len(r["kp_names"]) == 2

    assert match_terms(COURSE_A, "今天天气如何") == []


def test_resolve_topic_falls_back_to_rag_vote(st_env):
    """术语层没命中时走 RAG 投票；切片库为空时应保持 uncertain（fail-closed）。"""
    from app.agent_st.rag.topic import resolve_topic, vote_pick

    assert vote_pick(COURSE_A, "这个算法的时间复杂度怎么算") == []
    r = resolve_topic(COURSE_A, text="这个算法的时间复杂度怎么算")
    assert r["uncertain"] is True and r["suggestions"]


def test_course_terms_are_per_course(st_env):
    """同一个函数取不同课程的术语表：A 课看不到 B 课的知识点名称。"""
    from app.agent_st.rag.topic import course_terms

    a_names = {t[0] for t in course_terms(COURSE_A)}
    b_names = {t[0] for t in course_terms(COURSE_B)}
    assert "测试知识点一" in a_names and "B课程知识点" not in a_names
    assert "B课程知识点" in b_names and "测试知识点一" not in b_names


# ---------------- 运行时（demo 模式） ----------------
def test_runtime_demo_explain(st_env):
    from app.agent_st.agent import runtime

    events = list(runtime.run_turn("KMP next 数组", user_id="U_TEST", course_id=COURSE_A))
    types = [e["type"] for e in events]
    assert "session" in types and "text" in types and "citations" in types
    assert types[-1] == "done"
    done = events[-1]
    assert done["demo"] is True
    assert done.get("out_of_scope") is False


def test_runtime_demo_generate_writes_draft(st_env):
    from app.agent_st.agent import runtime
    from app.agent_st import persistence
    from app.models.agent_st import STQuestionDraft

    events = list(runtime.run_turn(
        "出一道相似题", flow_id="generate_items",
        user_id="U_TEST2", course_id=COURSE_A,
        context={"courseId": COURSE_A, "kp_ids": [KP_A1], "example_question_ids": ["QTEST_A1"]},
    ))
    draft_events = [e for e in events if e["type"] == "draft"]
    assert draft_events, "demo 出题流应产出 draft 事件"
    d = draft_events[0]
    assert d["draft_id"].startswith("QD")
    assert str(d["payload"]["q_id"]).startswith("AI")

    db = persistence.SessionLocal()
    row = db.query(STQuestionDraft).filter(STQuestionDraft.draft_id == d["draft_id"]).first()
    assert row is not None and row.user_id == "U_TEST2" and row.course_id == COURSE_A
    db.close()


def test_session_isolation_between_users(st_env):
    from app.agent_st.agent import runtime

    ev1 = list(runtime.run_turn("KMP", user_id="U_A", course_id=COURSE_A))
    ev2 = list(runtime.run_turn("KMP", user_id="U_B", course_id=COURSE_A))
    sid1 = next(e["session_id"] for e in ev1 if e["type"] == "session")
    sid2 = next(e["session_id"] for e in ev2 if e["type"] == "session")
    assert sid1 != sid2


# ---------------- 较大变动 / 讲解补充 ----------------
def test_novelty_rejects_numeric_micro_edit():
    from app.agent_st.rag.novelty import check_novelty

    src = {"q_id": "Q1", "question": "从 1，3，6 中选一个最大数", "graph": None}
    cand = {"q_id": "AI001", "question": "从 1，2，6 中选一个最大数", "graph": None}
    result = check_novelty(cand, [src])
    assert not result["ok"]
    assert any("微扰" in e or "变动不足" in e for e in result["errors"])


def test_novelty_accepts_changed_asked_target():
    from app.agent_st.rag.novelty import check_novelty

    graph = {
        "type": "weighted_undirected_graph",
        "nodes": ["a", "b", "c", "d"],
        "edges": [
            {"from": "a", "to": "b", "weight": 4},
            {"from": "b", "to": "c", "weight": 1},
            {"from": "a", "to": "c", "weight": 5},
            {"from": "c", "to": "d", "weight": 2},
        ],
    }
    src = {"q_id": "Q8", "question": "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。", "graph": graph}
    cand = {
        "q_id": "AI001",
        "question": "对下图使用 Kruskal 算法，最小生成树的总权值是(  )。",
        "graph": graph,
    }
    result = check_novelty(cand, [src])
    assert result["ok"], result["errors"]


def test_novelty_rejects_tiny_weight_tweak():
    from app.agent_st.rag.novelty import check_novelty

    src_graph = {
        "type": "weighted_undirected_graph",
        "nodes": ["a", "b", "c", "d"],
        "edges": [
            {"from": "a", "to": "b", "weight": 4},
            {"from": "b", "to": "c", "weight": 1},
            {"from": "a", "to": "c", "weight": 5},
            {"from": "c", "to": "d", "weight": 2},
        ],
    }
    cand_graph = json.loads(json.dumps(src_graph))
    cand_graph["edges"][2]["weight"] = 6
    stem = "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。"
    result = check_novelty(
        {"q_id": "AI001", "question": stem, "graph": cand_graph},
        [{"q_id": "Q8", "question": stem, "graph": src_graph}],
    )
    assert not result["ok"]


def test_demo_explain_empty_uses_supplement(st_env):
    from app.agent_st.agent import runtime
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore

    ctx = ToolContext(store=AgentStore(user_id="U_SUP"), flow_id="explain", extra={}, user_id="U_SUP")
    ctx.turn["retrieval"] = {"empty": True, "hits": []}
    ctx.turn["topic"] = {"uncertain": True, "course_title": "", "chapter_name": "", "kp_name": ""}
    text = runtime._demo_explain("今天天气如何", ctx)
    assert "【补充】" in text
    assert runtime._explain_out_of_scope(ctx, "今天天气如何") is True
    assert runtime._explain_out_of_scope(ctx, "请解释 KMP 的定义") is False


def test_save_draft_requires_plan_and_novelty(st_env):
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore
    from app.agent_st.agent.tools.draft import save_question_draft

    ctx = ToolContext(
        store=AgentStore(user_id="U_SAVE", course_id=COURSE_A), flow_id="generate_items",
        extra={"courseId": COURSE_A}, user_id="U_SAVE",
    )
    result = save_question_draft(ctx, _valid_payload())
    assert result.get("ok") is False
    assert any("submit_item_plan" in e for e in result.get("errors") or [])


def test_prompt_grounding_splits_by_flow():
    from app.agent_st.agent.loader import build_system_prompt, load_flow, load_persona

    persona = load_persona()
    explain = build_system_prompt(persona, load_flow("explain"))
    generate = build_system_prompt(persona, load_flow("generate_items"))
    assert "【补充】" in explain
    assert "check_novelty" in generate
    assert "微扰动" in generate


# ---------------- 回归：定位「整词优先」 ----------------
def test_resolve_topic_chapter_cn_keeps_kp(st_env):
    """「第N章 + 知识点」应同时给出章与知识点，而不是只给章。"""
    from app.agent_st.rag.topic import resolve_topic

    _add_kps(COURSE_A, [("KP014", "二叉树遍历")])
    r = resolve_topic(COURSE_A, text=f"{CHAPTER_A_NAME} 二叉树遍历讲一下")
    assert r["chapter_id"] == CHAPTER_A
    assert r["kp_id"] == "KP014", r
    assert r["kp_ids"] == ["KP014"]


# ---------------- 回归：q_id 由系统分配 ----------------
def test_validate_q_id_optional_but_format_checked(st_env):
    """q_id 不是模型的输出字段：缺失不算错，但给了值就必须是规范形态。"""
    from app.agent_st.rag.validate import validate_question

    no_qid = {k: v for k, v in _valid_payload().items() if k != "q_id"}
    assert validate_question(no_qid, course_id=COURSE_A, used_q_ids=set())["ok"] is True

    bad = validate_question(_valid_payload(q_id="AI###"), course_id=COURSE_A, used_q_ids=set())
    assert bad["ok"] is False
    assert any("格式不合法" in e for e in bad["errors"])


def test_validate_accepts_real_bank_q_id_forms(st_env):
    """回归：主库真实题号形态必须被接受。

    `Q` + 8 位十六进制（如 `QD44D2820`）前缀后含字母，早期写成 `^[A-Za-z]{1,4}\\d{1,6}$`
    会把主库全部 228 条题号判为「格式不合法」。
    """
    from app.agent_st.rag.validate import validate_question

    for qid in ("QD44D2820", "Q8FE3AE1", "KHD001", "AI001", "AI002"):
        r = validate_question(_valid_payload(q_id=qid), course_id=COURSE_A, used_q_ids=set())
        assert r["ok"] is True, f"{qid} 被误判：{r['errors']}"


def test_two_drafts_get_distinct_q_ids(st_env):
    """回归：一次出 2 道题时两道草稿必须拿到不同题号。

    历史上 next_ai_q_id 只扫正式题库（不含草稿），同批次每道题都算出同一个
    AI001，于是第 2 道被 validate 判「题号与现有题库冲突」→ status=invalid。
    """
    from app.agent_st.agent.store import AgentStore
    from app.agent_st.rag.bank import AI_QID_RE, next_ai_q_id

    store = AgentStore(user_id="U_TWO", course_id=COURSE_A)
    first = next_ai_q_id(COURSE_A, reserved=store.reserved_q_ids())
    saved1 = store.save_draft({**_valid_payload(q_id=first), "question": "第一题"}, batch_id="BT1")
    second = next_ai_q_id(COURSE_A, reserved=store.reserved_q_ids())

    assert AI_QID_RE.match(first) and AI_QID_RE.match(second), (first, second)
    assert second != first, f"第二题复用了第一题的题号 {second}"
    saved2 = store.save_draft({**_valid_payload(q_id=second), "question": "第二题"}, batch_id="BT1")
    assert saved1["status"] == "draft" and saved1["errors"] == []
    assert saved2["status"] == "draft", saved2["errors"]


def test_ai_q_id_format_is_hex_and_collision_checked(st_env):
    """AI 题号 = `AI` + 8 位十六进制；不再自增，且必须让开已占用的号。

    随机 hex 单独不保证不撞（16^8 ≈ 4.3e9），所以分配时要检查唯一性 ——
    这里用一个已占用的号池验证它确实会绕开。
    """
    from app.agent_st.rag.bank import AI_QID_RE, next_ai_q_id

    assert AI_QID_RE.match("AI3F8A21E7")
    assert not AI_QID_RE.match("AI###")     # 模型示例串不是合法题号
    assert not AI_QID_RE.match("AI1")       # 太短

    # 连续分配应互不相同，且都与导入题库的 `Q`+hex 前缀不同
    got = {next_ai_q_id(COURSE_A) for _ in range(30)}
    assert len(got) == 30
    assert all(q.startswith("AI") for q in got)


# ---------------- 多 KP（与主库口径一致） ----------------
def test_validate_accepts_multi_kp(st_env):
    """kp_id 是主 KP，kp_ids 是完整列表；主 KP 必须与章自洽，其余只要求属本课。"""
    from app.agent_st.rag.validate import validate_question

    payload = {**_valid_payload(), "kp_ids": [KP_A1, KP_A2]}
    r = validate_question(payload, course_id=COURSE_A, used_q_ids=set())
    assert r["ok"] is True, r["errors"]
    assert r["kp_id"] == KP_A1 and r["kp_ids"] == [KP_A1, KP_A2]

    # 只给 kp_ids 时主 KP 取首个
    p2 = {k: v for k, v in _valid_payload().items() if k != "kp_id"}
    p2["kp_ids"] = [KP_A2, KP_A1]
    r2 = validate_question(p2, course_id=COURSE_A, used_q_ids=set())
    assert r2["ok"] is True, r2["errors"]
    assert r2["kp_id"] == KP_A2 and r2["kp_ids"] == [KP_A2, KP_A1]

    # 混入别课程的 KP → 拒绝
    bad = {**_valid_payload(), "kp_ids": [KP_A1, KP_B1]}
    rb = validate_question(bad, course_id=COURSE_A, used_q_ids=set())
    assert rb["ok"] is False
    assert any(KP_B1 in e for e in rb["errors"]), rb["errors"]


def test_search_similar_matches_any_kp(st_env):
    """挂多 KP 的题在任一 KP 下都应被检索到（否则防抄名单会出现缺口）。"""
    from app.agent_st import persistence
    from app.agent_st.rag.bank import search_similar
    from app.models.question import Question

    db = persistence.SessionLocal()
    db.add(Question(q_id="QMULTI01", course_id=COURSE_A, chapter_id=CHAPTER_A,
                    chapter=CHAPTER_A_NAME, kp_id=KP_A1,
                    kp_ids=json.dumps([KP_A1, KP_A2]), status="published",
                    stem="多 KP 题", options="[]", answer="A", analysis=""))
    db.commit()
    db.close()

    assert "QMULTI01" in [h["q_id"] for h in search_similar(course_id=COURSE_A, kp_ids=[KP_A2])]
    assert "QMULTI01" in [h["q_id"] for h in search_similar(course_id=COURSE_A, kp_id=KP_A1)]
    one = search_similar(course_id=COURSE_A, kp_id=KP_A1)[0]
    assert one["kp_ids"] == [KP_A1, KP_A2]
    assert one["kp_names"] == ["测试知识点一", "测试知识点二"]


def test_draft_tool_overrides_bogus_q_id(st_env):
    """模型把提示词示例串 `AI###` 当题号写进 JSON 时，必须被系统覆盖成规范号。"""
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore
    from app.agent_st.agent.tools.draft import save_question_draft
    from app.agent_st.rag.novelty import question_fingerprint
    from app.agent_st.rag.validate import Q_ID_RE

    ctx = ToolContext(
        store=AgentStore(user_id="U_BOGUS", course_id=COURSE_A), flow_id="generate_items",
        extra={"courseId": COURSE_A}, user_id="U_BOGUS",
    )
    ctx.turn["item_plan"] = {"ok": True, "plan": {"solution_trace": "x" * 60}}
    payload = _valid_payload(q_id="AI###")
    ctx.turn["last_novelty"] = {
        "ok": True, "fingerprint": question_fingerprint(payload),
    }

    result = save_question_draft(ctx, payload)
    assert result.get("ok") is True, result
    assert result["q_id"] != "AI###"
    assert Q_ID_RE.match(result["q_id"]), result["q_id"]
