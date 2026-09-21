"""agent_st 集成测试：章节映射 / 出题校验 / RAG / demo 运行时（hermetic，不发外网、不碰正式库）"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 测试用课程 ID（真实字符串，满足外键）
COURSE_A = "C_TEST_A"
COURSE_B = "C_TEST_B"


@pytest.fixture()
def st_env(tmp_path, monkeypatch):
    """hermetic 环境：临时 rag.db / 草稿目录 / 正式库；embedding 走本地哈希；强制 demo 模式"""
    from app import config as app_config
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 1) 正式 Settings 的 agent_st 字段指向临时目录，且不配任何 KEY
    monkeypatch.setattr(app_config.settings, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(app_config.settings, "LLM_API_KEY", "")
    monkeypatch.setattr(app_config.settings, "AGENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(app_config.settings, "RAG_DB_PATH", tmp_path / "rag.db")
    monkeypatch.setattr(app_config.settings, "ST_DRAFTS_DIR", tmp_path / "drafts")
    # 题库归属课程 = 课程 A（多课程下题库不再跨课程灌入）
    monkeypatch.setattr(app_config.settings, "ST_BANK_COURSE_ID", COURSE_A)

    # 2) 重建 agent_st 配置桥
    from app.agent_st import settings_bridge

    s = settings_bridge._bridge.refresh()

    # 3) 正式数据库替换为临时 SQLite（先导入全部模型注册表结构，再建表）
    from app.models import user, course, graph, question, practice, ai, alert, intervention, checkin  # noqa: F401
    from app.models import agent_st  # noqa: F401
    from app.models.course import Course
    tmp_engine = create_engine(
        f"sqlite:///{tmp_path / 'main.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=tmp_engine)
    from app.agent_st import persistence

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=tmp_engine)
    monkeypatch.setattr(persistence, "SessionLocal", TestSession)

    # 3b) 建两门课，满足 chat_sessions / st_question_drafts 的外键
    db = TestSession()
    for cid in (COURSE_A, COURSE_B):
        db.add(Course(course_id=cid, name=f"测试课程 {cid}"))
    db.commit()
    db.close()

    # 4) 强制 demo 模式（不走真实 LLM）
    from app.agent_st.agent import llm

    monkeypatch.setattr(llm, "chat_available", lambda: False)

    yield s

    settings_bridge._bridge.refresh()


# ---------------- 章节映射 ----------------
def test_chapter_map_wandao_prefixes():
    from app.agent_st.rag.chapter_map import map_section

    assert map_section("1.1 数据结构的基本概念")["id"] == 1
    assert map_section("3.1 栈")["id"] == 3
    assert map_section("3.4 数组、特殊矩阵和广义表")["id"] == 5   # 王道 3.4 → 课程第5章
    assert map_section("5.3 二叉树的遍历")["id"] == 6            # 王道 5.x → 课程第6章
    assert map_section("6.4 图的应用")["id"] == 7                # 王道 6.x → 课程第7章
    assert map_section("7.2 折半查找")["id"] == 8
    assert map_section("8.3 快速排序")["id"] == 9
    assert map_section("第7章 图")["id"] == 0                    # 不允许"第N章"作为王道前缀
    assert map_section("完全无关内容")["id"] == 0


def test_figure_mode_priority():
    from app.agent_st.rag.chapter_map import figure_mode

    assert figure_mode({"options_graph": {"A": {"type": "tree", "nodes": ["1"], "edges": []}}}) == "option-figures"
    assert figure_mode({"graph": {"type": "adjacency_matrix", "nodes": ["A"], "matrix": [[0]]}}) == "matrix"
    assert figure_mode({"graph": {"type": "tree", "nodes": ["1"], "edges": []}}) == "stem-figure"
    assert figure_mode({"has_image": True}) == "text"


# ---------------- 出题 JSON 校验 ----------------
VALID = {
    "id": 90001,
    "chapter": "6.1 图的基本概念",
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


def test_validate_ok_graph():
    from app.agent_st.rag.validate import validate_question

    result = validate_question(dict(VALID), used_ids=set())
    assert result["ok"], result["errors"]


def test_validate_rejects_bad_type_and_chapter():
    from app.agent_st.rag.validate import validate_question

    bad = dict(VALID)
    bad["chapter"] = "第7章 图"
    bad["graph"] = {"type": "mindmap", "nodes": ["A"], "edges": []}
    result = validate_question(bad, used_ids=set())
    assert not result["ok"]
    assert any("type" in e for e in result["errors"])
    assert any("chapter" in e for e in result["errors"])


def test_validate_rejects_aoe_cycle():
    from app.agent_st.rag.validate import validate_question

    bad = dict(VALID)
    bad["graph"] = {
        "type": "aoe_network",
        "nodes": ["A", "B", "C"],
        "edges": [
            {"from": "A", "to": "B", "weight": 1, "activity": "a1"},
            {"from": "B", "to": "C", "weight": 1, "activity": "a2"},
            {"from": "C", "to": "A", "weight": 1, "activity": "a3"},
        ],
    }
    result = validate_question(bad, used_ids=set())
    assert not result["ok"]
    assert any("DAG" in e for e in result["errors"])


# ---------------- RAG ----------------
def test_embed_local_and_dims_guard():
    from app.agent_st.rag.embed import local_embed, cosine, dims_compatible

    v1 = local_embed("KMP 算法 next 数组")
    v2 = local_embed("KMP 算法 next 数组")
    v3 = local_embed("完全不同的内容 content")
    assert dims_compatible(v1, v2) and cosine(v1, v2) > 0.9
    assert dims_compatible(v1, [0.0] * 3) is False  # 维度不同 → 检索退化为纯关键词
    assert cosine(v1, v3) < cosine(v1, v2)


def test_bank_missing_file_returns_empty(tmp_path):
    from app.agent_st.rag import bank

    bank.load_questions.cache_clear()
    try:
        assert bank.load_questions(str(tmp_path / "missing.json")) == []
    finally:
        bank.load_questions.cache_clear()


def test_local_retrieve_hits_chapter(st_env):
    from app.agent_st.rag.ingest import ensure_bank_indexed
    from app.agent_st.rag.retrieve import retrieve_chunks

    info = ensure_bank_indexed(course_id=COURSE_A)
    assert info.get("ok") or info.get("chunks", 0) >= 0
    hits = retrieve_chunks(
        query="KMP next 数组", course_id=COURSE_A, course_chapter=4,
        source_types=["question_stem", "question_analysis"],
    )
    assert hits, "第4章检索应有命中"
    assert all(h["course_chapter"] == 4 for h in hits)
    assert all(h["course_id"] == COURSE_A for h in hits)


# ---------------- 课程隔离（P0/P1 修复后的回归） ----------------
def test_retrieve_without_course_returns_empty(st_env):
    """fail-closed：没有课程上下文不得退化成全库混搜"""
    from app.agent_st.rag.ingest import ensure_bank_indexed
    from app.agent_st.rag.retrieve import retrieve_chunks

    ensure_bank_indexed(course_id=COURSE_A)          # 库里有数据
    assert retrieve_chunks(query="KMP next 数组", course_id=None) == []
    assert retrieve_chunks(query="KMP next 数组", course_id="") == []


def test_rag_isolation_between_courses(st_env):
    """两门课各自入库同一份题库：切片必须互不可见、chunk_id 不得撞车"""
    from app.agent_st.rag.ingest import ingest_bank
    from app.agent_st.rag.retrieve import retrieve_chunks
    from app.agent_st.rag.store import ChunkStore

    r_a = ingest_bank(COURSE_A)
    r_b = ingest_bank(COURSE_B)
    assert r_a.get("ok") and r_b.get("ok")

    store = ChunkStore()
    n_a, n_b = store.count(COURSE_A), store.count(COURSE_B)
    assert n_a > 0 and n_b > 0
    # 关键：两门课的切片数应各自完整，不能被对方 INSERT OR REPLACE 吃掉
    assert n_a == n_b, f"两课程切片数应一致，实际 A={n_a} B={n_b}"

    for cid in (COURSE_A, COURSE_B):
        hits = retrieve_chunks(query="KMP next 数组", course_id=cid, course_chapter=4)
        assert hits, f"{cid} 应有命中"
        assert all(h["course_id"] == cid for h in hits)
        assert all(str(h["chunk_id"]).startswith(f"{cid}:") for h in hits)


def test_delete_source_types_scoped_by_course(st_env):
    """按来源类型清理题库切片时，绝不能波及其它课程（旧实现跨课程误删）"""
    from app.agent_st.rag.ingest import ingest_bank
    from app.agent_st.rag.store import ChunkStore

    ingest_bank(COURSE_A)
    ingest_bank(COURSE_B)
    store = ChunkStore()
    before_b = store.count(COURSE_B)
    assert store.count(COURSE_A) > 0 and before_b > 0

    removed = store.delete_source_types(["question_stem", "question_analysis"], course_id=COURSE_A)
    assert removed > 0
    assert store.count(COURSE_A) == 0
    assert store.count(COURSE_B) == before_b, "课程 B 的题库切片被误删"


def test_store_rejects_chunk_without_course(st_env):
    """写入侧硬约束：没有 course_id 的切片必须拒绝入库，不能落到默认课程"""
    import pytest as _pytest
    from app.agent_st.rag.schema import ChunkRecord
    from app.agent_st.rag.store import ChunkStore

    bad = ChunkRecord(
        chunk_id="x-1", text="t", source_type="textbook", source_id="s",
        course_chapter=1, section="1.1", course_id="",
    )
    with _pytest.raises(ValueError):
        ChunkStore().upsert_many([bad])


def test_store_columns_have_no_course_default(st_env):
    """rag.db 的 course_id 列不得再带默认值（历史 DEFAULT 'C2026DS001' 是串数据根因）"""
    import sqlite3
    from app.agent_st.rag.store import ChunkStore

    store = ChunkStore()
    with sqlite3.connect(store.path) as conn:
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    assert "course_id" in cols
    assert cols["course_id"][3] == 1, "course_id 必须是 NOT NULL"
    assert cols["course_id"][4] is None, f"course_id 不应有默认值，实际={cols['course_id'][4]!r}"


def test_session_and_draft_carry_course_id(st_env):
    """会话与出题草稿都必须落到当前课程（否则列表按课程过滤时查不到）"""
    from app.agent_st.agent.store import AgentStore
    from app.agent_st import persistence
    from app.models.ai import ChatSession

    store = AgentStore(user_id="U_ISO", course_id=COURSE_A)
    sid = store.ensure_session(None, "explain")
    saved = store.save_draft(dict(VALID))

    db = persistence.SessionLocal()
    try:
        sess = db.query(ChatSession).filter(ChatSession.session_id == sid).first()
        assert sess is not None and sess.course_id == COURSE_A
    finally:
        db.close()

    rows = store.list_drafts(user_id="U_ISO", course_id=COURSE_A)
    assert any(r["draft_id"] == saved["draft_id"] for r in rows)
    # 另一门课看不到这份草稿
    assert store.list_drafts(user_id="U_ISO", course_id=COURSE_B) == []


def test_session_cannot_be_reused_across_courses(st_env):
    """同一 session_id 不能跨课程复用（否则把两门课的对话串在一起）"""
    from app.agent_st.agent.store import AgentStore

    sid = AgentStore(user_id="U_X", course_id=COURSE_A).ensure_session(None, "explain")
    sid2 = AgentStore(user_id="U_X", course_id=COURSE_B).ensure_session(sid, "explain")
    assert sid2 != sid


# ---------------- 运行时（demo 模式，不发外网请求、不碰正式库） ----------------
def test_runtime_demo_explain(st_env):
    from app.agent_st.agent import runtime

    events = list(runtime.run_turn("题63 讲解", user_id="U_TEST", course_id=COURSE_A))
    types = [e["type"] for e in events]
    assert "session" in types
    assert "text" in types
    assert "citations" in types
    assert types[-1] == "done"
    done = events[-1]
    assert done["demo"] is True
    assert done.get("out_of_scope") is False
    text = "".join(e.get("delta") or "" for e in events if e["type"] == "text")
    assert "我不会用记忆补定义" not in text


def test_runtime_demo_generate_writes_draft(st_env):
    from app.agent_st.agent import runtime
    from app.agent_st import persistence
    from app.models.agent_st import STQuestionDraft

    events = list(runtime.run_turn(
        "第4章 出一道相似题", flow_id="generate_items",
        user_id="U_TEST2", course_id=COURSE_A,
    ))
    types = [e["type"] for e in events]
    draft_events = [e for e in events if e["type"] == "draft"]
    assert draft_events, "demo 出题流应产出 draft 事件"
    d = draft_events[0]
    assert d["draft_id"].startswith("QD")
    assert d["payload"]["id"] >= 90001
    text = "".join(e.get("delta") or "" for e in events if e["type"] == "text")
    assert "较大变动" in text
    # 草稿落库且归属生成用户 + 当前课程（查询必须走被替换的临时库 session）
    db = persistence.SessionLocal()
    row = db.query(STQuestionDraft).filter(STQuestionDraft.draft_id == d["draft_id"]).first()
    assert row is not None and row.user_id == "U_TEST2"
    assert row.course_id == COURSE_A, "草稿未落到当前课程"
    db.close()


def test_session_isolation_between_users(st_env):
    from app.agent_st.agent import runtime

    ev1 = list(runtime.run_turn("题63 讲解", user_id="U_A", course_id=COURSE_A))
    ev2 = list(runtime.run_turn("题63 讲解", user_id="U_B", course_id=COURSE_A))
    sid1 = next(e["session_id"] for e in ev1 if e["type"] == "session")
    sid2 = next(e["session_id"] for e in ev2 if e["type"] == "session")
    assert sid1 != sid2


# ---------------- 较大变动 / 讲解补充 ----------------
def test_parse_example_question_ids():
    from app.agent_st.rag.kp_map import parse_example_question_id, parse_example_question_ids, sections_for_kp_ids

    assert parse_example_question_id(12) == 12
    assert parse_example_question_id("KHD012") == 12
    assert parse_example_question_id("KHD12") == 12
    assert parse_example_question_ids(["KHD001", 1, "2", 2]) == [1, 2]
    assert "6.4" in sections_for_kp_ids(["KP51"])


def test_novelty_rejects_numeric_micro_edit():
    from app.agent_st.rag.novelty import check_novelty

    src = {"id": 1, "question": "从 1，3，6 中选一个最大数", "graph": None}
    cand = {"id": 90001, "question": "从 1，2，6 中选一个最大数", "graph": None}
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
    src = {"id": 8, "question": "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。", "graph": graph}
    cand = {
        "id": 90001,
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
    cand_graph = {
        "type": "weighted_undirected_graph",
        "nodes": ["a", "b", "c", "d"],
        "edges": [
            {"from": "a", "to": "b", "weight": 4},
            {"from": "b", "to": "c", "weight": 1},
            {"from": "a", "to": "c", "weight": 6},
            {"from": "c", "to": "d", "weight": 2},
        ],
    }
    stem = "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。"
    result = check_novelty(
        {"id": 90001, "question": stem, "graph": cand_graph},
        [{"id": 8, "question": stem, "graph": src_graph}],
    )
    assert not result["ok"]


def test_novelty_accepts_multiple_weight_changes():
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
    cand_graph = {
        "type": "weighted_undirected_graph",
        "nodes": ["a", "b", "c", "d"],
        "edges": [
            {"from": "a", "to": "b", "weight": 8},
            {"from": "b", "to": "c", "weight": 3},
            {"from": "a", "to": "c", "weight": 1},
            {"from": "c", "to": "d", "weight": 9},
        ],
    }
    stem = "对下图使用 Kruskal 算法，加入生成树的第一条边是(  )。"
    result = check_novelty(
        {"id": 90001, "question": stem, "graph": cand_graph},
        [{"id": 8, "question": stem, "graph": src_graph}],
    )
    assert result["ok"], result["errors"]


def test_demo_explain_empty_uses_supplement(st_env):
    from app.agent_st.agent import runtime
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore

    ctx = ToolContext(store=AgentStore(user_id="U_SUP"), flow_id="explain", extra={}, user_id="U_SUP")
    ctx.turn["retrieval"] = {"empty": True, "hits": []}
    ctx.turn["topic"] = {"uncertain": True, "course_title": "", "section": ""}
    text = runtime._demo_explain("今天天气如何", ctx)
    assert "【补充】" in text
    assert "我不会用记忆补定义" not in text
    assert runtime._explain_out_of_scope(ctx, "今天天气如何") is True
    assert runtime._explain_out_of_scope(ctx, "请解释 KMP 的定义") is False


def test_save_draft_requires_plan_and_novelty(st_env):
    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore
    from app.agent_st.agent.tools.draft import save_question_draft

    ctx = ToolContext(store=AgentStore(user_id="U_SAVE"), flow_id="generate_items", extra={}, user_id="U_SAVE")
    result = save_question_draft(ctx, dict(VALID))
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
