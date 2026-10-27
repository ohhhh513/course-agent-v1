"""联网 PDF 原页、扫描 OCR、切题边界与下载安全检查；不接触业务数据库。"""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DEBUG"] = "false"
from app.services.web_pdf_worker import process_pdf, download_pdf, PublicNetworkBackend, PdfFailure, _segments


def fixtures(work):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    # 测试素材显式生成，不冒充网络原题。
    font = Path("C:/Windows/Fonts/simhei.ttf")
    if not font.exists():
        raise RuntimeError("测试中文字体缺失，请配置可用的中文 TTF 字体。")
    pdfmetrics.registerFont(TTFont("FixtureChinese", str(font)))
    native = work / "queue-native.pdf"
    c = canvas.Canvas(str(native), pagesize=(600, 700)); c.setFont("FixtureChinese", 16)
    for y, text in [(660, "1. 如图所示，队列依次存入 A、B、C。"), (630, "删除一个元素后，队头元素是什么？"),
                    (460, "A. A       B. B       C. C       D. 队空"), (400, "答案：B。这一行不应出现在题目裁图。"),
                    (340, "2. 以下哪一种结构遵循先进先出原则？"), (305, "A. 栈          B. 队列")]:
        c.drawString(30, y, text)
    for i, letter in enumerate("ABC"):
        x = 90 + i * 110
        c.rect(x, 520, 100, 55); c.drawString(x + 40, 540, letter)
    c.line(45, 548, 80, 548); c.line(72, 555, 80, 548); c.line(72, 541, 80, 548)
    c.save()
    # 第二份只有一张栅格图，不能靠 PDF 文本层取巧。
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(native)
    try:
        page = doc[0]; bitmap = page.render(scale=2)
        image = bitmap.to_pil().copy(); bitmap.close(); page.close()
    finally:
        doc.close()
    scan = work / "queue-scanned.pdf"
    c = canvas.Canvas(str(scan), pagesize=(600, 700)); c.drawImage(ImageReader(image), 0, 0, 600, 700); c.save(); image.close()
    return native, scan


def main():
    work = ROOT / ".pytest-tmp-custom-skills" / "web-pdf"
    work.mkdir(parents=True, exist_ok=True)
    native, scan = fixtures(work)
    for path, method in ((native, "text"), (scan, "ocr")):
        result = process_pdf(path.read_bytes(), work / "cache", query="队列 如图", max_pages=1)
        page = result["pages"][0]
        assert page["method"] == method, page
        assert "队列" in page["content"] and page["segments"], page
        first = page["segments"][0]
        assert "删除" in first["text"] and "答案" not in first["text"] and "2." not in first["text"], first
        assert first["pageNumber"] == 1
        assert first["bounds"][3] < 300, first  # 答案在 y=300 开始，裁图不能越过该行。
        assert process_pdf(path.read_bytes(), work / "cache", query="队列 如图", max_pages=1) == result
        (work / (method + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] {method}: 原页/原始矢量图截图、真实文字/扫描OCR、答案边界、页码与缓存")
    # 对连接地址而不是只对字符串做检查，重定向同样经过此后端。
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
        try:
            PublicNetworkBackend().connect_tcp("public-looking.example", 443)
            raise AssertionError("private DNS accepted")
        except PdfFailure:
            pass
    for payload in (b"not a pdf", b"%PDF-damaged"):
        try:
            process_pdf(payload, work / "cache")
            raise AssertionError("broken PDF accepted")
        except PdfFailure:
            pass
    # 公开可直接打开但设有 owner password 的文件应正常读取；真正需密码的文件拒绝。
    from pypdf import PdfReader, PdfWriter
    for password in ("", "reader-password"):
        writer = PdfWriter(); writer.append(PdfReader(native)); writer.encrypt(password, owner_password="owner-password")
        buffer = BytesIO(); writer.write(buffer)
        try:
            result = process_pdf(buffer.getvalue(), work / "cache", max_pages=1)
            assert not password and result["pages"]
        except PdfFailure:
            assert password
    with patch("httpcore.ConnectionPool") as factory:
        response = factory.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
        response.status = 200; response.headers = []
        response.iter_stream.return_value = iter([b"%P", b"DF-1.7\nbody"])
        assert download_pdf("https://example.com/document.pdf", 100) == b"%PDF-1.7\nbody"
        response.iter_stream.return_value = iter([b"%PDF-1.7\n", b"a" * 100])
        try:
            download_pdf("https://example.com/document.pdf", 20)
            raise AssertionError("oversized file accepted")
        except PdfFailure:
            pass
        response.status = 302; response.headers = [(b"location", b"http://127.0.0.1/private.pdf")]
        try:
            download_pdf("https://example.com/document.pdf", 100)
            raise AssertionError("private redirect accepted")
        except PdfFailure:
            pass
    assert not _segments([dict(text="无法可靠识别的扫描页题面及图中文字", score=.3, left=0, right=200, top=0, bottom=20)], 600, 700)
    bracketed = [dict(text=text, score=1, left=20, right=400, top=20+i*80, bottom=40+i*80)
                 for i,text in enumerate(("（10）如图所示，删除队头元素后新的队头元素是什么？", "A. A B. B C. C D. 队空", "（11）另一道不应该混入前题截图的队列习题。"))]
    parts = _segments(bracketed,600,700)
    assert len(parts)==2 and "（11）" not in parts[0]["text"] and parts[0]["bounds"][3]<180
    from app.services.web_pdf import read_pdf
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 1)):
        try:
            read_pdf("https://example.com/document.pdf", timeout=1)
            raise AssertionError("worker timeout not stopped")
        except Exception as exc:
            assert "超过" in str(exc)
    print("[ok] 内网 DNS/跳转、坏文件、超限下载、弱 OCR、真正加密 PDF 与超时拒绝；空密码公开 PDF 可读")


if __name__ == "__main__":
    main()
