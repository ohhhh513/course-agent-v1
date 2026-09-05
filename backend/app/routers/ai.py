"""
AI 智能答疑接口：/ai/*

⚠️ Agent 开发部分后续由用户补充。
当前使用 seed 脚本预置的 mock 答案做兜底，返回与前端契约完全一致的数据结构。
后续可在此文件中替换为 LLM + RAG 实现：
    1. /ai/chat   → 大模型 + 课程资料检索（返回 citations）
    2. /ai/chat/stream → SSE 流式输出（需要 sse-starlette）
"""
import json, re, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..models.ai import ChatSession, ChatMessage
from ..models.intervention import TeacherClassDashboard
from ..middleware.auth import get_current_user
from ..schemas.common import ok
from ..utils import loads

router = APIRouter(prefix="/api/v1/ai", tags=["AI 智能答疑"])


class ChatReq(BaseModel):
    sessionId: Optional[str] = None
    question: str
    method: str = "guided"
    kpId: Optional[str] = None
    courseId: str = "C2026DS001"


class FeedbackReq(BaseModel):
    messageId: str
    feedback: int = 1   # 1=点赞 -1=点踩


# ===== 预置答案库（与前端 mock 一致，关键词命中 → 带 citations 的答案） =====
# 后续可替换为向量库 + LLM 检索增强生成
_ANSWER_BANK = [
    {
        "match": r"遍历|前序|中序|后序",
        "content": (
            "<p>三种遍历的差别只有<strong>一处</strong>：访问根结点的时机。</p>"
            "<ol>"
            "<li><strong>前序</strong>：<code>根 → 左 → 右</code>，先记录根，适合<strong>复制/序列化</strong>一棵树；</li>"
            "<li><strong>中序</strong>：<code>左 → 根 → 右</code>，在二叉排序树上会得到<strong>递增有序序列</strong>；</li>"
            "<li><strong>后序</strong>：<code>左 → 右 → 根</code>，根最后访问，适合<strong>释放内存、计算子树聚合值</strong>。</li>"
            "</ol>"
            "<p>本质区别在于：<strong>前序自上而下传递信息，后序自下而上汇总信息</strong>，中序则天然对应有序性。</p>"
            "<p>想不想我出 2 道即时小题检验一下？</p>"
        ),
        "citations": [
            {
                "source": "第4章 树与二叉树 课堂课件",
                "locator": "P31 · 遍历定义",
                "quote": "二叉树的遍历是指按某种规律访问树中每个结点且仅访问一次，三种次序的区别仅在于访问根结点的先后。",
                "kp": "二叉树的遍历",
            },
            {
                "source": "《数据结构（C语言版）》第6章",
                "locator": "P130 · 性质 6.4",
                "quote": "中序遍历二叉排序树可得到一个关键字递增有序的序列。",
                "kp": "二叉树的遍历",
            },
        ],
    },
    {
        "match": r"负权|Dijkstra|dijkstra|最短路",
        "content": (
            "<p>Dijkstra 的正确性建立在一个<strong>贪心假设</strong>上：每次取出 dist 最小的顶点 u 时，dist[u] 就已是最终答案。</p>"
            "<p>这个假设成立的前提是 <strong>所有边权非负</strong> —— 因为从 u 继续往后走只会让路径变长，不可能再变短。</p>"
            "<p>一旦出现负权边，继续走反而更短就成立了，提前锁定 u 就错了。此时应改用 <strong>Bellman-Ford</strong>（O(VE)，还能检测负权回路）。</p>"
            "<p>试着自己跑一遍这个反例：A→B 权 1，A→C 权 4，<strong>C→B 权 -3</strong>。</p>"
        ),
        "citations": [
            {
                "source": "第5章 图（下）课堂课件",
                "locator": "P28 · 算法正确性证明",
                "quote": "若图中所有边的权值均为非负值，则每次选取的当前最短路径顶点，其最短路径长度不会因后续松弛而减小。",
                "kp": "最短路径 Dijkstra",
            },
            {
                "source": "《算法导论》第24章",
                "locator": "P658 · 定理 24.6",
                "quote": "Dijkstra 算法要求所有边权非负。存在负权边时需改用 Bellman-Ford 算法。",
                "kp": "最短路径 Dijkstra",
            },
        ],
    },
    {
        "match": r"循环队列|判空|判满",
        "content": (
            "<p>先看矛盾：队空和队满时都会出现 <code>rear == front</code>，无法区分。解决办法有三种，课程采用第一种。</p>"
            "<ol>"
            "<li><strong>牺牲一个单元</strong>（本课程标准）：队空 <code>rear == front</code>，队满 <code>(rear+1) % MAXSIZE == front</code>，实际可存 MAXSIZE-1 个；</li>"
            "<li>增设 <code>size</code> 计数变量；</li>"
            "<li>增设 <code>tag</code> 标记最后一次操作是入队还是出队。</li>"
            "</ol>"
            "<p>你上次这题错在把判满写成了 <code>(front+1) % MAXSIZE == rear</code> —— 指针方向反了。记住：<strong>是 rear 追 front</strong>。</p>"
        ),
        "citations": [
            {
                "source": "循环队列判空判满专题",
                "locator": "04:12 · 三种解决方案对比",
                "quote": "为区分队空与队满，最常用的方法是少用一个元素空间，约定以队头指针在队尾指针的下一位置作为队满的标志。",
                "kp": "循环队列判空判满",
            },
        ],
    },
    {
        "match": r"哈夫曼|WPL|编码|压缩",
        "content": (
            "<p>哈夫曼编码保证前缀码性质的关键：<strong>所有字符都放在叶子结点上</strong>。</p>"
            "<p>因为任一叶子都不可能是另一叶子的祖先，所以任一编码都不可能是另一编码的前缀 —— 解码时不会产生歧义。</p>"
            "<p>WPL 计算有两种等价方式，用第二种更不容易错：</p>"
            "<ol>"
            "<li>Σ(叶子权值 × 该叶子路径长度)；</li>"
            "<li><strong>Σ(所有非叶结点的权值)</strong> —— 即每次合并产生的新结点权值之和。</li>"
            "</ol>"
        ),
        "citations": [
            {
                "source": "《数据结构（C语言版）》第6章",
                "locator": "P152 · 哈夫曼树的构造",
                "quote": "哈夫曼编码是一种前缀编码，因为所有字符均处于叶子结点，任一编码都不是另一编码的前缀。",
                "kp": "哈夫曼树与编码",
            },
        ],
    },
]


def _mock_answer(question: str, method: str) -> dict:
    for bank in _ANSWER_BANK:
        if re.search(bank["match"], question):
            return {
                "messageId": "MSG" + uuid.uuid4().hex[:12],
                "method": method,
                "content": bank["content"],
                "citations": bank["citations"],
                "outOfScope": False,
                "sourceCount": len(bank["citations"]),
            }
    # 未命中 → 严格溯源降级
    return {
        "messageId": "MSG" + uuid.uuid4().hex[:12],
        "method": method,
        "content": (
            "<p>我在本课程的教材、课件与教学视频中<strong>没有检索到能直接支撑该问题的原文</strong>。"
            "为避免给你不可靠的答案，我不做推测性回答。</p>"
            "<p>你可以：</p>"
            "<ol>"
            "<li>换一个更贴近课程知识点的问法（例如指定章节或知识点名称）；</li>"
            "<li>点击下方「转人工」，我会把这个问题连同你的学情一起提交给老师；</li>"
            "<li>或者从这些和你薄弱点相关的问题开始：<strong>Dijkstra 为什么不能处理负权边</strong>、"
            "<strong>循环队列为什么少用一个单元</strong>。</li>"
            "</ol>"
        ),
        "citations": [],
        "outOfScope": True,
        "sourceCount": 0,
    }


# ========= 路由实现 =========
@router.get("/methods")
def ai_methods(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return ok([
        {"key": "lecture", "name": "讲授法", "desc": "系统讲解概念与原理，结构清晰", "icon": "book"},
        {"key": "guided", "name": "引导式", "desc": "不直接给答案，层层提问引导思考", "icon": "compass"},
        {"key": "case", "name": "案例式", "desc": "结合实际工程案例说明", "icon": "briefcase"},
        {"key": "heuristic", "name": "启发式", "desc": "从反例与矛盾中启发理解", "icon": "bulb"},
        {"key": "fun", "name": "趣味式", "desc": "类比与故事化表达，降低认知门槛", "icon": "smile"},
    ])


@router.get("/sessions")
def ai_sessions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.query(ChatSession).filter(ChatSession.user_id == user.user_id).order_by(ChatSession.updated_at.desc()).all()
    items = [
        {
            "sessionId": s.session_id, "title": s.title,
            "time": s.updated_at.strftime("%m-%d %H:%M") if s.updated_at else "",
            "rounds": s.rounds, "kp": s.kp_name,
        }
        for s in rows
    ]
    # 不再兜底返回他人的 chat_history —— 新用户无会话则返回空
    return ok({"total": len(items), "list": items})


@router.get("/sessions/{session_id}/messages")
def ai_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id.asc()).all()
    if not rows:
        # 不再兜底返回他人的 chat_messages —— 新会话无消息则返回空
        return ok([])
    items = [
        {
            "role": m.role, "method": m.method, "content": m.content,
            "time": m.time_str, "citations": loads(m.citations) or [],
        }
        for m in rows
    ]
    return ok(items)


@router.get("/suggest-questions")
def suggest_questions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """推荐提问方向 —— 不再硬编码，返回空列表让前端展示默认提示"""
    row = db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == "suggested_questions").first()
    if row:
        return ok(loads(row.data_json))
    return ok([])


@router.post("/chat")
def ai_chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    AI 智能答疑 —— **Agent 部分 TODO**
    当前使用关键词匹配返回预设答案（含 citations）。
    后续可在此处接入大模型 + RAG：
        from .services.chat_agent import answer
        result = answer(req.question, method=req.method, kp_id=req.kpId, user=user)
    """
    result = _mock_answer(req.question, req.method)

    # 保存消息到数据库
    # 前端传 'new' 表示要创建新会话；空/None 也生成新会话
    raw_sid = (req.sessionId or '').strip()
    if not raw_sid or raw_sid.lower() == 'new':
        session_id = "CH" + uuid.uuid4().hex[:12]
    else:
        session_id = raw_sid
    now_str = datetime.now().strftime("%H:%M")
    # 用户提问
    db.add(ChatMessage(
        session_id=session_id, role="me", content=req.question, time_str=now_str,
    ))
    # AI 回答
    db.add(ChatMessage(
        session_id=session_id, role="ai", method=req.method, content=result["content"],
        citations=json.dumps(result["citations"], ensure_ascii=False), time_str=now_str,
    ))
    # 更新/创建会话
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        session = ChatSession(
            session_id=session_id, user_id=user.user_id,
            title=req.question[:30], rounds=2, kp_name=req.kpId or "",
        )
        db.add(session)
    else:
        session.rounds = (session.rounds or 0) + 2
    db.commit()

    # 把 sessionId 返回，方便前端切换到真实会话
    result["sessionId"] = session_id
    return ok(result)


@router.post("/chat/stream")
async def ai_chat_stream(
    req: ChatReq,
    user=Depends(get_current_user),
):
    """
    SSE 流式答疑 —— **Agent 部分 TODO**
    当前仅返回一次性完整答案（使用 StreamingResponse + text/event-stream）。
    后续替换为大模型流式输出：
        from sse_starlette.sse import EventSourceResponse
        return EventSourceResponse(generate_stream(req))
    """
    from sse_starlette.sse import EventSourceResponse
    result = _mock_answer(req.question, req.method)

    async def gen():
        yield {"event": "meta", "data": json.dumps({
            "messageId": result["messageId"], "citations": result["citations"],
        }, ensure_ascii=False)}
        yield {"event": "content", "data": result["content"]}
        yield {"event": "done", "data": json.dumps({"outOfScope": result["outOfScope"]})}

    return EventSourceResponse(gen())


@router.post("/feedback")
def ai_feedback(
    req: FeedbackReq,
    user=Depends(get_current_user),
):
    """点赞/点踩反馈，用于知识库迭代 —— TODO"""
    return ok({"accepted": True})
