"""从上传的附件中抽取纯文本，供智能助手「附到当前问题」语义使用。

支持格式与依赖：
    .txt / .md / .csv / .json  —— 原生解码（utf-8-sig / gbk 回退）
    .xlsx                      —— openpyxl（已装）
    .docx                      —— python-docx（已装）
    .pdf                       —— pypdf（已装）

设计约定：
    - 所有第三方库惰性导入，缺失时明确报错而不是静默崩溃。
    - 单文件抽取上限 MAX_CHARS，避免超长上下文把模型喂爆。
    - 不落库、不建索引：抽取出的文本只在「当前这一轮」注入 prompt，
      历史消息里只保留文件名（见 run_turn 的 attachments 处理），符合
      「不擅自改数据库表结构」约束。
"""
from typing import List

MAX_CHARS = 60_000  # 单文件抽取上限

ALLOWED = {".txt", ".md", ".csv", ".json", ".xlsx", ".docx", ".pdf"}


def _ext(filename: str) -> str:
    """返回带点的小写后缀（如 '.xlsx'）；无后缀返回 ''。"""
    name = filename or ""
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def extract_file_text(filename: str, data: bytes) -> str:
    """抽取上传文件的纯文本。失败抛 ValueError / RuntimeError（调用方负责转成用户可读错误）。"""
    ext = _ext(filename)
    if ext not in ALLOWED:
        raise ValueError(
            f"不支持的文件类型：{ext or '(无后缀)'}。"
            f"支持 .txt / .md / .csv / .json / .xlsx / .docx / .pdf"
        )
    if not data:
        raise ValueError("文件内容为空")

    try:
        if ext in (".txt", ".md", ".csv", ".json"):
            text = _read_text(data, ext)
        elif ext == ".xlsx":
            text = _read_xlsx(data)
        elif ext == ".docx":
            text = _read_docx(data)
        else:  # .pdf
            text = _read_pdf(data)
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:  # noqa: BLE001 —— 第三方解析器抛错五花八门，统一转成用户可读文案
        raise ValueError(f"文件已损坏或格式不正确（{exc}）")

    text = (text or "").strip()
    if not text:
        raise ValueError("文件中未抽取到可识别的文本（可能是扫描件 / 图片型 PDF）")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n…（内容过长已截断，仅保留前 {MAX_CHARS} 字）"
    return text


def _read_text(data: bytes, ext: str) -> str:
    # 优先 utf-8-sig（去掉 BOM），失败回退 gbk（中文 Windows 常见）
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="ignore")


def _read_xlsx(data: bytes) -> str:
    from io import BytesIO
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(data), data_only=True, read_only=True)
    parts: List[str] = []
    for ws in wb.worksheets:
        parts.append(f"### 工作表：{ws.title}")
        for r in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in r]
            if all(x == "" for x in cells):
                continue
            parts.append("\t".join(cells))
    wb.close()
    return "\n".join(parts)


def _read_docx(data: bytes) -> str:
    from io import BytesIO
    from docx import Document

    doc = Document(BytesIO(data))
    parts: List[str] = []
    for p in doc.paragraphs:
        if p.text and p.text.strip():
            parts.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_pdf(data: bytes) -> str:
    from io import BytesIO

    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("解析 PDF 需要安装 pypdf（pip install pypdf）")
    reader = PdfReader(BytesIO(data))
    parts: List[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return "\n".join(parts)
