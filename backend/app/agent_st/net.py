"""OpenAI 兼容客户端的统一构造（chat / embedding / Agents SDK 共用）。

集中到一处的原因：模型、Embedding、Agent 运行层都要建 OpenAI 兼容客户端，
分散构造容易出现超时/重试不一致。这里只统一"怎么建客户端"：

  - 网络策略遵循 httpx / OpenAI SDK 的标准行为（HTTP_PROXY / HTTPS_PROXY /
    NO_PROXY 都由环境决定，代码不额外干预）；
  - 超时按"流式对话"设：连接 10s、**读 300s**（模型两次输出之间可能停顿较久，
    读超时给足），写 60s、连接池 10s。
"""
from __future__ import annotations


def _timeout():
    import httpx

    return httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


def sync_client(base_url: str, api_key: str):
    """同步 OpenAI 客户端（chat 补全、embedding 用）。"""
    import httpx
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url,
                  http_client=httpx.Client(timeout=_timeout()))


def async_client(base_url: str, api_key: str):
    """异步 OpenAI 客户端（Agents SDK 的 OpenAIChatCompletionsModel 用）。"""
    import httpx
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key, base_url=base_url,
                       http_client=httpx.AsyncClient(timeout=_timeout()))
