from __future__ import annotations

from collections.abc import Iterator

from app.agent_st.agent.config import get_settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


def chat_available() -> bool:
    settings = get_settings()
    return bool(settings.llm_api_key) and OpenAI is not None


def _client():
    settings = get_settings()
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


def complete(messages: list[dict], tools: list[dict] | None) -> dict:
    """非流式调用（保留给 demo / 测试 / 无需流式的场景）"""
    settings = get_settings()
    client = _client()
    kwargs = {"model": settings.llm_model, "messages": messages, "temperature": 0.2}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            )
    return {"content": msg.content or "", "tool_calls": tool_calls}


def complete_stream(
    messages: list[dict],
    tools: list[dict] | None,
    on_text_delta=None,
    on_reasoning_delta=None,
) -> dict:
    """真实 token 流式调用。

    边流式产出文本（经 on_text_delta 回调），边聚合 tool_calls 片段。
    若模型返回 reasoning_content（如 deepseek 系思考模型的内部推理），
    经 on_reasoning_delta 实时回调，供前端"思考"面板展示。
    返回值形状与 complete() 一致：{"content", "tool_calls"}。
    """
    settings = get_settings()
    client = _client()
    kwargs = {"model": settings.llm_model, "messages": messages, "temperature": 0.2}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    content_parts: list[str] = []
    calls: dict[int, dict] = {}

    stream = client.chat.completions.create(**kwargs, stream=True)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        # 思考模型的内部推理（deepseek: reasoning_content）——实时转发
        reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
        if reasoning and on_reasoning_delta:
            on_reasoning_delta(reasoning)
        if delta.content:
            content_parts.append(delta.content)
            if on_text_delta:
                on_text_delta(delta.content)
        if delta.tool_calls:
            for frag in delta.tool_calls:
                slot = calls.setdefault(
                    frag.index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if frag.id:
                    slot["id"] = frag.id
                if frag.function:
                    if frag.function.name:
                        slot["name"] += frag.function.name
                    if frag.function.arguments:
                        slot["arguments"] += frag.function.arguments

    tool_calls = [calls[i] for i in sorted(calls)]
    return {"content": "".join(content_parts), "tool_calls": tool_calls}


def chunk_text(text: str, size: int = 24) -> Iterator[str]:
    """演示模式的假流式切片"""
    for i in range(0, len(text), size):
        yield text[i : i + size]
