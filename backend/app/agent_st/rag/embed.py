from __future__ import annotations

import hashlib
import math
import random
import re
import time

from app.agent_st.agent.config import get_settings

DIM = 256
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")

# 远程 embedding 单次请求的最大条数。题库约 450 条切片，整本教材切分会更多，
# 一次性提交容易触发请求体过大或限流，因此按批切分。
EMBED_BATCH_SIZE = 32
EMBED_MAX_RETRIES = 3


def embedding_api_available() -> bool:
    settings = get_settings()
    return bool(settings.embedding_api_key)


def active_model_name() -> str:
    settings = get_settings()
    if embedding_api_available():
        return settings.embedding_model or "remote-embedding"
    return f"local-hash-{DIM}"


def _hash_index(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest, 16) % DIM


def local_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    tokens = TOKEN_RE.findall((text or "").lower())
    grams = list(tokens)
    joined = "".join(tokens)
    for i in range(len(joined) - 1):
        grams.append(joined[i : i + 2])
    if not grams:
        return vec
    for gram in grams:
        vec[_hash_index(gram)] += 1.0
    return _l2_normalize(vec)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def _remote_embed_batch(client, model: str, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=texts)
    ordered = sorted(resp.data, key=lambda row: row.index)
    vectors = [_l2_normalize(list(row.embedding)) for row in ordered]
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"embedding 返回条数不一致：期望 {len(texts)}，实际 {len(vectors)}"
        )
    return vectors


def _embed_with_retry(client, model: str, texts: list[str]) -> list[list[float]]:
    """对网络抖动 / 限流做有限重试，避免整批入库前功尽弃。"""
    last_error: Exception | None = None
    for attempt in range(EMBED_MAX_RETRIES):
        try:
            return _remote_embed_batch(client, model, texts)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < EMBED_MAX_RETRIES - 1:
                time.sleep(0.5 * (2**attempt) + random.random() * 0.3)
    raise RuntimeError(f"调用 embedding 接口失败：{last_error}") from last_error


def embed_texts(texts: list[str]) -> list[list[float]]:
    texts = list(texts or [])
    if not texts:
        return []
    if not embedding_api_available():
        return [local_embed(t) for t in texts]
    settings = get_settings()
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要安装 openai 才能调用远程 embedding") from exc
    base = settings.embedding_base_url or settings.llm_base_url
    client = OpenAI(api_key=settings.embedding_api_key, base_url=base)

    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(_embed_with_retry(client, settings.embedding_model, batch))
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"embedding 结果条数不一致：期望 {len(texts)}，实际 {len(vectors)}"
        )
    return vectors


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def dims_compatible(a: list[float] | None, b: list[float] | None) -> bool:
    """向量维度一致才能比较。换 embedding 模型后旧向量维度不同，需重新入库。"""
    return bool(a) and bool(b) and len(a) == len(b)
