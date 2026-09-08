"""agent_st 集成测试：章节映射 / 出题校验 / RAG / demo 运行时（hermetic，不发外网、不碰正式库）"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


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

    # 2) 重建 agent_st 配置桥
    from app.agent_st import settings_bridge

    s = settings_bridge._bridge.refresh()

    # 3) 正式数据库替换为临时 SQLite（先导入全部模型注册表结构，再建表）
    from app.models import user, course, graph, question, practice, ai, alert, intervention, checkin  # noqa: F401
    from app.models import agent_st  # noqa: F401
    tmp_engine = create_engine(
        f"sqlite:///{tmp_path / 'main.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=tmp_engine)
    from app.agent_st import persistence

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=tmp_engine)
    monkeypatch.setattr(persistence, "SessionLocal", TestSession)

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

    info = ensure_bank_indexed()
    assert info.get("ok") or info.get("chunks", 0) >= 0
    hits = retrieve_chunks(query="KMP next 数组", course_chapter=4, source_types=["question_stem", "question_analysis"])
    assert hits, "第4章检索应有命中"
    assert all(h["course_chapter"] == 4 for h in hits)


# ---------------- 运行时（demo 模式，不发外网请求、不碰正式库） ----------------
def test_runtime_demo_explain(st_env):
    from app.agent_st.agent import runtime

    events = list(runtime.run_turn("题63 讲解", user_id="U_TEST"))
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

    events = list(runtime.run_turn("第4章 出一道相似题", flow_id="generate_items", user_id="U_TEST2"))
    types = [e["type"] for e in events]
    draft_events = [e for e in events if e["type"] == "draft"]
    assert draft_events, "demo 出题流应产出 draft 事件"
    d = draft_events[0]
    assert d["draft_id"].startswith("QD")
    assert d["payload"]["id"] >= 90001
    text = "".join(e.get("delta") or "" for e in events if e["type"] == "text")
    assert "较大变动" in text
    # 草稿落库且归属生成用户（查询必须走被替换的临时库 session）
    db = persistence.SessionLocal()
    row = db.query(STQuestionDraft).filter(STQuestionDraft.draft_id == d["draft_id"]).first()
    assert row is not None and row.user_id == "U_TEST2"
    db.close()


def test_session_isolation_between_users(st_env):
    from app.agent_st.agent import runtime

    ev1 = list(runtime.run_turn("题63 讲解", user_id="U_A"))
    ev2 = list(runtime.run_turn("题63 讲解", user_id="U_B"))
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
