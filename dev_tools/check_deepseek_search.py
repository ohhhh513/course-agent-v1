"""DeepSeek 搜索供应商单测：MockTransport 验证网络边界，不访问真实数据库或外网。"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.update(DEBUG="false", DATABASE_URL="sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from app.config import settings
from app.services import teacher_web_search as service


def main():
    real_client = httpx.Client
    with patch.multiple(settings, LLM_BASE_URL="https://api.deepseek.com", LLM_API_KEY="fixture-key",
                        TAVILY_API_KEY="fixture-tavily", TEACHER_WEB_SEARCH_PROVIDER="auto",
                        TEACHER_WEB_SEARCH_ENABLED=True, TEACHER_WEB_SEARCH_MAX_RESULTS=5,
                        TEACHER_WEB_SEARCH_TIMEOUT=15):
        assert service.selected_provider() == "deepseek"
        with patch.object(settings, "LLM_BASE_URL", "https://api.deepseek.com/v1/"):
            assert service.selected_provider() == "deepseek"
        for url in ("https://proxy.example.com", "http://api.deepseek.com", "https://api.deepseek.com.evil.com",
                    "https://api.deepseek.com@evil.com", "https://api.deepseek.com:123", "https://api.deepseek.com/?secret=x"):
            with patch.object(settings, "LLM_BASE_URL", url):
                assert service.selected_provider() == "tavily"
                with patch.object(settings, "TEACHER_WEB_SEARCH_PROVIDER", "deepseek"):
                    try:
                        service.search("公开教学资料")
                        raise AssertionError("不应复用非官方模型配置")
                    except service.SearchFailure as exc:
                        assert "官方地址" in str(exc)
        with patch.object(settings, "TEACHER_WEB_SEARCH_PROVIDER", "tavily"), \
                patch.object(service, "_sdk_search", return_value={"results": []}) as tavily:
            assert service.search("公开教学资料")["empty"] and tavily.called
        try:
            service.validate_query("a" * 129, "", "")
            raise AssertionError("超长查询应在读取数据库或联网前拒绝")
        except service.SearchFailure as exc:
            assert "128" in str(exc)

        calls = []
        fixture = {"results": [
            {"title": "官方文档", "url": "https://docs.python.org/3/library/collections.html", "summary": "长摘要",
             "snippet": "短摘要", "content": "不读取全文", "date": "2026-10-01T00:00:00+00:00"},
            {"title": "另一条", "url": "https://www.python.org/doc/", "snippet": "摘要回退", "date": None},
            {"title": "不安全来源", "url": "http://127.0.0.1/private", "summary": "不展示"}, None,
        ]}
        def success(request):
            calls.append(request)
            assert str(request.url) == "https://api.deepseek.com/v1/tools/search"
            assert request.headers["Authorization"] == "Bearer fixture-key"
            body = json.loads(request.content)
            assert body == {"query": "Python 官方教学文档", "count": 5, "need_content": False}
            return httpx.Response(200, json=fixture)
        def make_client(**kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["timeout"].read == 15
            return real_client(transport=httpx.MockTransport(success), **kwargs)
        with patch.object(httpx, "Client", side_effect=make_client), patch.object(service, "_sdk_search") as tavily:
            result = service.search("Python 官方教学文档")
            assert len(calls) == 1 and not tavily.called
            assert len(result["results"]) == 2
            assert result["results"][0]["snippet"] == "长摘要"
            assert result["results"][1]["snippet"] == "摘要回退" and result["results"][1]["publishedDate"] == ""
            assert result["results"][0]["publishedDate"].startswith("2026-10-01")
        for status, text in ((401, "鉴权"), (402, "余额不足"), (403, "鉴权"), (404, "暂不可用"),
                             (405, "暂不可用"), (429, "过于频繁"), (500, "失败或超时"), (302, "失败或超时")):
            def error(request):
                return httpx.Response(status, json={"error": {"message": "fixture-key must never appear"}},
                                      headers={"Location": "https://evil.example/"})
            with patch.object(httpx, "Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(error), **kwargs)), \
                    patch.object(service, "_sdk_search") as tavily:
                try:
                    service.search("公开教学资料")
                    raise AssertionError(status)
                except service.SearchFailure as exc:
                    assert text in str(exc) and "fixture-key" not in str(exc) and not tavily.called
        for reply in (httpx.Response(200, text="invalid json"), httpx.Response(200, json={"results": "bad"})):
            with patch.object(httpx, "Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: reply), **kwargs)):
                try:
                    service.search("公开教学资料")
                    raise AssertionError("响应格式应校验")
                except service.SearchFailure as exc:
                    assert "格式异常" in str(exc)
        with patch.object(settings, "LLM_API_KEY", ""), patch.object(settings, "TEACHER_WEB_SEARCH_PROVIDER", "deepseek"):
            try:
                service.search("公开教学资料")
                raise AssertionError("密钥缺失应报错")
            except service.SearchFailure as exc:
                assert "尚未配置" in str(exc)
    print("[ok] 自动复用官方配置、非官方地址拒绝、显式选择 Tavily、查询长度限制")
    print("[ok] 固定官方请求地址和字段、禁重定向、结果适配、来源过滤、错误脱敏且不自动切供应商")


if __name__ == "__main__":
    main()
