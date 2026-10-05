"""OpenAI 兼容客户端的统一构造（chat / embedding / Agents SDK 共用）。

为什么需要这一层
----------------
本机若挂着一个**不通的** VPN/代理（Windows 上常见：Clash/v2ray 退出后
环境变量还留着 `HTTPS_PROXY=http://127.0.0.1:7892`），httpx 默认会读取这些
环境变量并静默走代理，于是所有外呼都失败，报错长这样：

    APIConnectionError: [WinError 10061] 目标计算机积极拒绝，无法连接

而 DeepSeek / SiliconFlow 都是国内可直连的接口，本来不需要代理。
所以默认 `use_env_proxy=False`（httpx 的 `trust_env=False`），
需要走代理时把 `.env` 的 `LLM_USE_ENV_PROXY` 设成 1。
"""
from __future__ import annotations


def _httpx(use_env_proxy: bool, timeout: float, *, sync: bool):
    """按需构造 httpx client；use_env_proxy=True 时返回 None（交给 openai SDK 自己处理）。"""
    if use_env_proxy:
        return None
    import httpx

    cls = httpx.Client if sync else httpx.AsyncClient
    return cls(trust_env=False, timeout=timeout)


def sync_client(base_url: str, api_key: str, *, use_env_proxy: bool = False,
                timeout: float = 60.0):
    """同步 OpenAI 客户端（chat 补全、embedding 用）。"""
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url,
                  http_client=_httpx(use_env_proxy, timeout, sync=True))


def async_client(base_url: str, api_key: str, *, use_env_proxy: bool = False,
                 timeout: float = 60.0):
    """异步 OpenAI 客户端（Agents SDK 的 OpenAIChatCompletionsModel 用）。"""
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key, base_url=base_url,
                       http_client=_httpx(use_env_proxy, timeout, sync=False))
