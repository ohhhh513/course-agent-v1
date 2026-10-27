"""受限公开 PDF 下载和离线处理。入口由父进程施加整项超时，无数据库访问。"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import shutil
import tempfile
import uuid
from urllib.parse import quote, urljoin, urlsplit

import httpcore


class PdfFailure(Exception):
    rendered_pages = 0


class PublicNetworkBackend(httpcore.SyncBackend):
    """在实际 TCP 连接处校验全部 DNS 结果并连接固定 IP，TLS 仍验证原主机。"""
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        except OSError:
            raise PdfFailure("PDF 来源域名无法解析，请继续换来源。") from None
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise PdfFailure("PDF 来源解析到非公网地址，不能读取。")
        for index, address in enumerate(addresses):
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout):
                if index == len(addresses) - 1:
                    raise


def _public_url(url):
    # 独立进程不导入应用配置/数据库。下载仅允许标准公开 HTTP(S) 及无凭据 URL。
    try:
        value = urlsplit(url)
        host = (value.hostname or "").lower().rstrip(".")
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return (len(url) <= 2048 and not re.search(r'[\s<>"\x27\\\x00-\x1f]', url)
                and value.scheme in ("http", "https") and host
                and not value.username and not value.password and value.port in (None, 80, 443)
                and host != "localhost" and not host.endswith((".local", ".internal", ".localhost")))
    except ValueError:
        return False


def download_pdf(url: str, max_bytes: int) -> bytes:
    with httpcore.ConnectionPool(network_backend=PublicNetworkBackend(), max_connections=1, retries=0) as pool:
        for _ in range(4):
            if not _public_url(url):
                raise PdfFailure("PDF 来源或跳转目标不是可读取的公开地址。")
            with pool.stream("GET", quote(url, safe=":/?&=%#@+;,[]"), headers={"User-Agent": "CourseAgent-PDFReader/1.0", "Accept": "application/pdf",
                                                 "Accept-Encoding": "identity"},
                             extensions={"timeout": {"connect": 8, "read": 12, "write": 8, "pool": 8}}) as response:
                headers = {key.lower(): val for key, val in response.headers}
                if response.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, headers.get(b"location", b"").decode("latin-1"))
                    continue
                if response.status != 200:
                    raise PdfFailure(f"PDF 来源返回 HTTP {response.status}，请继续换来源。")
                if headers.get(b"content-encoding", b"identity").lower() not in (b"identity", b""):
                    raise PdfFailure("PDF 来源使用了不支持的压缩传输，已跳过。")
                length = headers.get(b"content-length", b"0")
                if length.isdigit() and int(length) > max_bytes:
                    raise PdfFailure("PDF 文件超过读取体积上限，已跳过。")
                chunks, size, prefix = [], 0, bytearray()
                for chunk in response.iter_stream():
                    size += len(chunk)
                    if size > max_bytes:
                        raise PdfFailure("PDF 文件超过读取体积上限，已停止下载。")
                    chunks.append(chunk)
                    prefix.extend(chunk[:max(0, 1024 - len(prefix))])
                    if len(prefix.lstrip()) >= 5 and not prefix.lstrip().startswith(b"%PDF-"):
                        raise PdfFailure("该来源不是可下载的 PDF 原文，请继续换来源。")
                data = b"".join(chunks)
                if not data[:1024].lstrip().startswith(b"%PDF-"):
                    raise PdfFailure("未取得有效 PDF 原文。")
                return data
    raise PdfFailure("PDF 来源跳转过多，已停止读取。")


def _native_lines(page):
    """按 PDF 原始字符坐标组行；保留定位坐标以截取矢量图。"""
    textpage = page.get_textpage()
    from pypdfium2.raw import FPDFText_GetCharAngle
    rows, chars = [], []
    try:
        height = page.get_height()
        for i in range(textpage.count_chars()):
            char = textpage.get_text_range(i, 1)
            if char in ("\r", "\n"):
                if chars:
                    rows.append(chars); chars = []
                continue
            # 斜向水印不参与文字与边界定位；渲染后的原页仍完整保留水印。
            if abs(math.sin(FPDFText_GetCharAngle(textpage.raw, i))) > .15:
                continue
            left, bottom, right, top = textpage.get_charbox(i)
            if not char or (not char.isspace() and (right <= left or top <= bottom)):
                continue
            chars.append((left, height - top, right, height - bottom, char))
        if chars:
            rows.append(chars)
    finally:
        textpage.close()
    result = []
    for chars in sorted(rows, key=lambda r: min(c[1] for c in r)):
        result.append({"text": "".join(c[4] for c in chars), "left": min(c[0] for c in chars),
                       "top": min(c[1] for c in chars), "right": max(c[2] for c in chars),
                       "bottom": max(c[3] for c in chars), "score": 1.0})
    return result


_START = re.compile(r"^\s*(?:[（(]\s*\d{1,3}\s*[）)]|\d{1,3}\s*[.、．)）](?!\d)|[【\[]?例(?:题)?\s*\d+|(?:题目|习题)\s*[:：])")
_ANSWER = re.compile(r"(?:^\s*(?:参考|正确)?(?:答案|解析|解答|分析|解|答)\s*[:：]|[【\[](?:答案|解析)|^\s*(?:Answer|Solution)\s*[:：]|正确答案)", re.I)


def _segments(lines, width, height):
    """只对纵向边界可确认的单栏题目生成裁图；不把答案一起截入题图。"""
    # 多栏长文本的纵向裁图会混入另一题，无法可靠切分时不生成题卡候选。
    long_lines = [line for line in lines if len(line["text"]) > 12]
    if any(line["left"] < width * .2 for line in long_lines) and sum(line["left"] > width * .5 for line in long_lines) >= 3:
        return []
    starts = [i for i, line in enumerate(lines) if _START.search(line["text"])]
    if not starts:
        starts = [0] if lines else []
    result = []
    for at, first in enumerate(starts):
        last = starts[at + 1] if at + 1 < len(starts) else len(lines)
        answers = [i for i in range(first, last) if _ANSWER.search(lines[i]["text"])]
        end = min(answers) if answers else last
        selected = lines[first:end]
        text = "\n".join(line["text"] for line in selected)
        # 常见已填答案的题面无法安全去答案，宁可换题；不能只隐藏独立答案字段。
        if re.search(r"_{2,}[^\n]{0,24}[（(]\s*[A-D\d][^）)\n]{0,12}[）)]|[（(]\s*[A-D]\s*[）)]", text):
            continue
        if len(text.strip()) < 16 or not selected:
            continue
        if min(line["score"] for line in selected) < .55 or sum(line["score"] for line in selected) / len(selected) < .85:
            continue
        top = max(0, selected[0]["top"] - 4) if first else 0
        bottom = max(top, lines[end]["top"] - 4) if end < len(lines) else height
        # 明显横跨多个题号/分栏或题号同行混排时无法可靠切题，保留页预览但不采用。
        if any(len(re.findall(r"(?:^|\s)\d{1,3}[.、．)）](?!\d)", line["text"])) > 1 for line in selected) or bottom <= max(line["bottom"] for line in selected):
            continue
        result.append({"text": text, "bounds": [0, top, width, bottom],
                       "viewKind": "question_crop" if starts != [0] or answers else "page_preview"})
    return result


def candidate_pages(texts, query, page_hint=0, max_pages=8):
    terms = list(dict.fromkeys(re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", query)))
    terms += [word for word in ("队列", "queue", "线性表", "栈", "树", "如图", "图示") if word in query.lower()]
    def page_rank(i):
        text = texts[i]
        relevant = sum(text.lower().count(t.lower()) for t in terms)
        numbered = len(re.findall(r"(?m)^\s*(?:[（(]\s*\d{1,3}\s*[）)]|\d{1,3}\s*[.、．])", text))
        figures = bool(re.search(r"如图|图\s*\d|figure", text, re.I))
        category = bool(re.search(r"选择题|判断题|问答题|(?:习题|练习题)(?!\s*答案)|exercises|problems", text, re.I))
        question_form = bool(re.search(r"_{2,}|？|(?<!\w)(?:\(\s*\)|（\s*）)", text))
        # 编号也可能只是基本操作列表；不能只标 True 后按关键词频率选介绍页。
        exercise = 0
        if relevant and figures:
            if category:
                exercise = 4
            elif numbered >= 2 and question_form:
                exercise = 3
            elif numbered >= 2 and "如图" in text:
                exercise = 2
            elif numbered >= 2:
                exercise = 1
        return i + 1 == page_hint, exercise, relevant
    return sorted(sorted(range(len(texts)), key=page_rank, reverse=True)[:max_pages])


def process_pdf(data: bytes, cache: Path, *, query="", page_hint=0, max_pages=8):
    try:
        import pypdfium2 as pdfium
        from pypdf import PdfReader
        from io import BytesIO
    except ImportError:
        raise PdfFailure("PDF 渲染依赖未安装，请更新 backend/requirements.txt。") from None
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        # is_encrypted 在空密码成功打开后仍为 True；公开可直接阅读的 PDF 不能因此被误拒。
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfFailure("PDF 已加密，无法直接读取，请继续换来源。")
        count = len(reader.pages)
        if page_hint > count:
            raise PdfFailure("指定文件页码超过该 PDF 的总页数。")
        # 防止大文档整本展开；先索引文字用于选页，再渲染候选页。
        if count > 300:
            raise PdfFailure("PDF 超过 300 页索引上限，请选择更具体的题目来源。")
        texts = [(p.extract_text() or "")[:16000] for p in reader.pages]
    except PdfFailure:
        raise
    except Exception:
        raise PdfFailure("PDF 损坏或格式无法解析，请继续换来源。") from None
    chosen = candidate_pages(texts, query, page_hint, max_pages)
    digest = hashlib.sha256(data + json.dumps([chosen, 5]).encode()).hexdigest()
    destination = cache / digest
    manifest = destination / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8"))
    cache.mkdir(parents=True, exist_ok=True)
    pages, ocr, rendered = [], None, 0
    doc = pdfium.PdfDocument(data)
    try:
        with tempfile.TemporaryDirectory(prefix=".build-", dir=cache) as temporary:
            temporary = Path(temporary)
            for index in chosen:
                page = doc[index]
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0 or width * height > 12_000_000:
                        continue
                    scale = min(2.0, 2600 / max(width, height))
                    rendered += 1
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                    lines = _native_lines(page) if page.get_rotation() == 0 else []
                    method = "text"
                    if sum(len(line["text"]) for line in lines) < 30:
                        try:
                            import numpy as np
                            import rapidocr
                            from rapidocr import RapidOCR
                            if ocr is None:
                                model_dir = Path(rapidocr.__file__).parent / "models"
                                required = ("ch_PP-OCRv4_det_infer.onnx", "ch_ppocr_mobile_v2.0_cls_infer.onnx", "ch_PP-OCRv4_rec_infer.onnx", "FZYTK.TTF")
                                if any(not (model_dir / name).exists() for name in required):
                                    raise PdfFailure("本地 OCR 模型/字体尚未准备，请运行 dev_tools/prepare_web_pdf.py 后重试。")
                                ocr = RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": 2,
                                                       "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                                                       "Global.log_level": "error"})
                            output = ocr(np.asarray(image))
                            lines = [{"text": text, "score": float(score), "left": float(min(p[0] for p in box)) / scale,
                                      "right": float(max(p[0] for p in box)) / scale, "top": float(min(p[1] for p in box)) / scale,
                                      "bottom": float(max(p[1] for p in box)) / scale}
                                     for text, score, box in zip(output.txts or (), output.scores or (), output.boxes if output.boxes is not None else ())]
                            lines.sort(key=lambda line: (line["top"], line["left"]))
                            method = "ocr"
                        except PdfFailure:
                            raise
                        except ImportError:
                            raise PdfFailure("扫描页 OCR 依赖未安装，请更新 backend/requirements.txt。") from None
                        except Exception:
                            raise PdfFailure("扫描页 OCR 未能完成，请检查本地 OCR 模型，或继续换来源。") from None
                    if not lines:
                        continue
                    page_name = f"page-{index + 1}.png"
                    image.save(temporary / page_name)
                    segments = []
                    candidates = _segments(lines, width, height)
                    candidates.sort(key=lambda s: (bool(re.search(r"如图|下图|图\s*\d|figure", s["text"], re.I)), len(s["text"]) > 60), reverse=True)
                    candidates = sorted(candidates[:12], key=lambda s: s["bounds"][1])
                    for number, segment in enumerate(candidates, 1):
                        if len(segment["text"]) > 6000:
                            continue
                        name = f"question-{index + 1}-{number}.png"
                        image.crop(tuple(round(v * scale) for v in segment["bounds"])).save(temporary / name)
                        segments.append({**segment, "imageUrl": f"/resources/web-question-pdfs/{digest}/{name}", "pageNumber": index + 1})
                    pages.append({"pageNumber": index + 1, "method": method, "content": "\n".join(line["text"] for line in lines),
                                  "previewUrl": f"/resources/web-question-pdfs/{digest}/{page_name}", "segments": segments})
                    image.close()
                finally:
                    page.close()
            if not pages:
                raise PdfFailure("PDF 中未识别到可核对的题目文字，请继续换来源。")
            result = {"title": "PDF 原文", "documentType": "pdf", "pageCount": count, "pages": pages,
                      "renderedPages": len(chosen), "truncated": len(chosen) < count,
                      "content": "\n\n".join(f"第 {p['pageNumber']} 页（{p['method']}）\n" + p["content"] for p in pages)}
            destination.mkdir(parents=True, exist_ok=True)
            for path in temporary.glob("*.png"):
                # 临时目录在 Windows 使用私有 ACL。重新创建发布文件以继承资源目录权限，
                # 不能把私有临时文件直接 rename 给独立的静态服务进程。
                published = destination / ("." + uuid.uuid4().hex + ".png")
                shutil.copyfile(path, published)
                published.replace(destination / path.name)
            temp_manifest = destination / ("." + uuid.uuid4().hex + ".json")
            temp_manifest.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temp_manifest.replace(manifest)
            return result
    except PdfFailure as exc:
        exc.rendered_pages = rendered
        raise
    finally:
        doc.close()


def main():
    parser = argparse.ArgumentParser()
    for name in ("url", "result", "cache", "query"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--page-hint", type=int, default=0)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--max-bytes", type=int, default=15 * 1024 * 1024)
    args = parser.parse_args()
    try:
        result = process_pdf(download_pdf(args.url, args.max_bytes), Path(args.cache), query=args.query,
                             page_hint=args.page_hint, max_pages=args.max_pages)
    except PdfFailure as exc:
        result = {"error": str(exc), "renderedPages": exc.rendered_pages}
    except (httpcore.NetworkError, httpcore.TimeoutException):
        result = {"error": "PDF 下载连接失败或超时，请继续换来源。"}
    except Exception:
        result = {"error": "PDF 读取失败，请检查依赖或继续换来源。", "renderedPages": args.max_pages}
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
