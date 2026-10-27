"""公开 PDF 读取入口；下载/渲染/OCR 在可超时终止的独立进程运行。"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from app.config import settings
from app.services.teacher_web_search import SearchFailure, public_url

IMAGE_PATTERN = r"/resources/web-question-pdfs/[a-f0-9]{64}/(?:page-\d+|question-\d+-\d+)\.png"


def local_image(value: str) -> str:
    return value if isinstance(value, str) and re.fullmatch(IMAGE_PATTERN, value) else ""


def read_pdf(url: str, *, query="", page_hint=0, timeout=90, max_pages=None) -> dict:
    if not settings.TEACHER_WEB_PDF_ENABLED:
        raise SearchFailure("PDF/扫描页读取已停用，请继续换一个网页来源。")
    if not public_url(url):
        raise SearchFailure("PDF 来源不是有效的公开地址。")
    cache = settings.FRONTEND_DIR / "resources" / "web-question-pdfs"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="web-pdf-") as folder:
        result = Path(folder) / "result.json"
        command = [sys.executable, "-m", "app.services.web_pdf_worker", "--url", url,
                   "--result", str(result), "--cache", str(cache), "--query", query[:128],
                   "--page-hint", str(max(0, page_hint)),
                   "--max-pages", str(max(1, min(8, max_pages or settings.TEACHER_WEB_PDF_MAX_PAGES))),
                   "--max-bytes", str(max(1, min(30, settings.TEACHER_WEB_PDF_MAX_MB)) * 1024 * 1024)]
        try:
            process = subprocess.run(command, cwd=settings.PROJECT_ROOT, capture_output=True,
                                     timeout=max(1, timeout), check=False)
        except subprocess.TimeoutExpired:
            raise SearchFailure("PDF 下载、截图或识别超过本轮剩余时间，已停止该来源。",
                                rendered_pages=max_pages or settings.TEACHER_WEB_PDF_MAX_PAGES) from None
        if not result.exists():
            raise SearchFailure("PDF 读取进程未完成，请检查 PDF/OCR 依赖，或继续换来源。")
        try:
            payload = json.loads(result.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise SearchFailure("PDF 读取结果无效，已跳过该来源。") from None
        if process.returncode or payload.get("error"):
            raise SearchFailure(payload.get("error") or "PDF 读取失败，已跳过该来源。", rendered_pages=payload.get("renderedPages", 0))
        return payload
