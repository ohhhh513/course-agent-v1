"""
媒体文件元数据解析与封面生成
- 轻量解析 MP4/PDF/PPTX（不依赖 ffmpeg/LibreOffice）
- 为上传资源生成占位封面
"""
import os
import re
import struct
import zipfile
import shutil
import codecs
from pathlib import Path
from datetime import datetime
from typing import Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False


# 相对定位：本文件位于 backend/app/media_utils.py，向上两级为项目根（course-agent）
BASE_DIR = Path(__file__).resolve().parents[2]

# ===================== 课程资源路径的唯一定义（改动请只改这里）=====================
# 磁盘位置：项目根 resources/（内容与前端代码 assets/ 分离；体积大，不入 Git）
RESOURCES_DIR = BASE_DIR / "resources"
COVERS_DIR = RESOURCES_DIR / "covers"

# 对外访问前缀：与磁盘目录一一对应（/resources/a/b.mp4 → resources/a/b.mp4）
URL_PREFIX = "/resources"

# 统一资源路径规范：resources/{course_id}/{res_id}/{filename}
#   - 第一级按课程隔离 → 天然支持多课程，资源一律由教师上传添加，不再有“内置资源”通道
#   - 第二级每个资源独占一个目录 → 避免同名覆盖，删除时整目录清理，不会残留孤儿文件
# 历史教训（勿重蹈）：
#   1) 早期前缀是 /assets/resources 但磁盘在 resources/，二者不对应，删除时反推必失败
#      且异常被吞 → 文件删不掉、越积越多（孤儿文件）；
#   2) 早期还有 data-structures-1-9/（内置资源目录）与 uploads/ 两套并存，扫描目录自动
#      登记资源的机制已废弃 —— 多课程场景下资源应统一由教师上传。
DEFAULT_COURSE_ID = "C2026DS001"


def course_dir(course_id: str):
    """某课程的资源根目录：resources/{course_id}/"""
    return RESOURCES_DIR / str(course_id or DEFAULT_COURSE_ID)


def res_dir(course_id: str, res_id: str):
    """某资源的独占目录：resources/{course_id}/{res_id}/"""
    return course_dir(course_id) / str(res_id)


def resource_url(rel_path: str) -> str:
    """把 resources/ 下的相对路径转成对外访问 URL。"""
    return f"{URL_PREFIX}/{str(rel_path).lstrip('/')}"


def res_url(course_id: str, res_id: str, filename: str) -> str:
    """某资源的标准访问 URL：/resources/{course_id}/{res_id}/{filename}"""
    return resource_url(f"{course_id or DEFAULT_COURSE_ID}/{res_id}/{filename}")


def presentation_preview_url(url: str) -> str:
    """PPT 原件旁的派生 PDF；不占用数据库列，也不会覆盖同名 PDF 原件。"""
    return url + ".preview.pdf" if str(url or "").lower().endswith((".ppt", ".pptx")) else ""


def url_to_path(url: str):
    """把资源 URL 反解为磁盘路径。

    资源删除 / 存在性校验的**唯一**入口，禁止在别处手写 `BASE_DIR / url.lstrip('/')`
    之类的拼接 —— 历史孤儿文件的根因就是手写拼接与实际目录不对应。
    """
    u = str(url or "").strip()
    if not u.startswith(URL_PREFIX + "/"):
        return None
    return RESOURCES_DIR / u[len(URL_PREFIX) + 1:]


def safe_filename(name: str) -> str:
    """清洗上传文件名：剥离目录部分、去掉路径分隔符与首尾点号，防止路径穿越。"""
    base = Path(str(name or "upload.bin")).name          # 去掉任何目录成分
    base = base.replace("\\", "_").replace("/", "_").replace(":", "_")
    base = base.strip().strip(".") or "upload.bin"
    return base[:180]


def cleanup_empty_dirs(path, retries: int = 2, delay: float = 0.3):
    """自下而上清理空目录（到 resources/ 为止），用于资源删除后不留空壳目录。

    Windows 上文件刚 unlink 后目录句柄可能短暂未释放，rmdir 会报
    「目录被占用 / 非空」——因此带少量重试；仍失败则放弃（残留的只是
    一个无害空目录，不影响数据一致性）。
    """
    import time
    d = path.parent if path.is_file() else path
    while d != RESOURCES_DIR and RESOURCES_DIR in d.parents:
        try:
            if any(d.iterdir()):
                break
            removed = False
            for attempt in range(retries + 1):
                try:
                    d.rmdir()
                    removed = True
                    break
                except OSError:
                    if attempt < retries:
                        time.sleep(delay)
            if not removed:
                break           # 放弃本层，避免死循环
        except OSError:
            break
        d = d.parent

TYPE_BG = {
    "video": ("#0f172a", "#1e3a8a"),
    "doc":   ("#0f172a", "#166534"),
    "ppt":   ("#0f172a", "#9a3412"),
    "quiz":  ("#0f172a", "#7c3aed"),
}

RESOURCE_TYPE_EXTENSIONS = {
    "doc": {".pdf", ".doc", ".docx", ".txt"},
    "ppt": {".pdf", ".ppt", ".pptx"},
    "video": {".mp4", ".mov", ".webm", ".mkv"},
}


class ResourceValidationUnavailable(RuntimeError):
    """Raised when a required format validator is missing from the runtime."""


def _validate_ole_office(file_obj, resource_type: str) -> bool:
    try:
        import olefile
    except ImportError as exc:
        raise ResourceValidationUnavailable(
            "服务器缺少 olefile，暂时无法验证旧版 DOC/PPT 文件；请安装项目依赖后重试。"
        ) from exc

    with olefile.OleFileIO(file_obj) as ole:
        streams = {entry[-1].casefold() for entry in ole.listdir() if entry}
        if resource_type == "doc":
            return "worddocument" in streams and bool({"0table", "1table"} & streams)
        return "powerpoint document" in streams


def _validate_text_file(file_obj) -> bool:
    for encoding in ("utf-8-sig", "gb18030"):
        file_obj.seek(0)
        decoder = codecs.getincrementaldecoder(encoding)()
        has_content = False
        try:
            while True:
                chunk = file_obj.read(64 * 1024)
                if not chunk:
                    break
                decoded = decoder.decode(chunk)
                if any(ord(char) == 0 or (ord(char) < 32 and char not in "\r\n\t\f") for char in decoded):
                    raise UnicodeError("binary control character")
                has_content = has_content or bool(decoded.strip())
            tail = decoder.decode(b"", final=True)
            if any(ord(char) == 0 or (ord(char) < 32 and char not in "\r\n\t\f") for char in tail):
                raise UnicodeError("binary control character")
            return has_content or bool(tail.strip())
        except UnicodeError:
            continue
    return False


def _validate_iso_video(file_obj, ext: str) -> bool:
    file_obj.seek(0, 2)
    file_size = file_obj.tell()
    file_obj.seek(0)
    position = 0
    has_file_type = False
    has_quicktime_movie = False
    has_video_data = False
    box_count = 0
    while position + 8 <= file_size and box_count < 10000:
        file_obj.seek(position)
        header = file_obj.read(16)
        if len(header) < 8:
            return False
        box_size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_size = 8
        if box_size == 1:
            if len(header) < 16:
                return False
            box_size = int.from_bytes(header[8:16], "big")
            header_size = 16
        elif box_size == 0:
            box_size = file_size - position
        if box_size < header_size or position + box_size > file_size:
            return False
        has_file_type = has_file_type or box_type == b"ftyp"
        has_quicktime_movie = has_quicktime_movie or box_type == b"moov"
        has_video_data = has_video_data or box_type in (b"moov", b"mdat", b"moof")
        position += box_size
        box_count += 1
    has_container = has_file_type or (ext == ".mov" and has_quicktime_movie)
    return has_container and has_video_data and position == file_size


def _validate_ebml_video(file_obj, header: bytes) -> bool:
    file_obj.seek(0, 2)
    file_size = file_obj.tell()
    file_obj.seek(0)
    container_header = file_obj.read(min(file_size, 64 * 1024))
    return (
        len(header) >= 4
        and header.startswith(b"\x1a\x45\xdf\xa3")
        and file_size > 32
        and (b"matroska" in container_header[:4096] or b"webm" in container_header[:4096])
        and b"\x18\x53\x80\x67" in container_header
    )


def validate_resource_upload(file_obj, filename: str, selected_type: str) -> str:
    """Validate a teacher-selected resource category against its suffix and file content.

    Returns an error message when the upload must be rejected, otherwise an empty string.
    The stream is rewound so the caller can safely save it after validation.
    """
    ext = Path(filename).suffix.lower()
    if selected_type not in RESOURCE_TYPE_EXTENSIONS:
        return "请选择教材文献、课件或教学视频。"
    if ext not in RESOURCE_TYPE_EXTENSIONS[selected_type]:
        return "所选资源类型与文件扩展名不匹配，请检查分类和文件后缀。"

    try:
        file_obj.seek(0)
        head = file_obj.read(4096)
        file_obj.seek(0)
        if ext == ".pdf":
            if b"%PDF-" not in head[:1024]:
                valid = False
            else:
                from pypdf import PdfReader

                pdf = PdfReader(file_obj, strict=False)
                valid = pdf.is_encrypted or len(pdf.pages) > 0
        elif ext == ".txt":
            valid = _validate_text_file(file_obj)
        elif ext in (".docx", ".pptx"):
            required_file = "word/document.xml" if ext == ".docx" else "ppt/presentation.xml"
            expected_type = (b"wordprocessingml.document.main+xml" if ext == ".docx"
                             else b"presentationml.presentation.main+xml")
            with zipfile.ZipFile(file_obj) as package:
                names = set(package.namelist())
                if "[Content_Types].xml" not in names or required_file not in names:
                    valid = False
                else:
                    with package.open("[Content_Types].xml") as content_types:
                        type_xml = content_types.read(1024 * 1024 + 1)
                    valid = len(type_xml) <= 1024 * 1024 and expected_type in type_xml
        elif ext in (".doc", ".ppt"):
            valid = _validate_ole_office(file_obj, selected_type)
        elif ext in (".mp4", ".mov"):
            valid = _validate_iso_video(file_obj, ext)
        else:
            valid = _validate_ebml_video(file_obj, head)
    except ResourceValidationUnavailable:
        raise
    except Exception:
        valid = False
    finally:
        file_obj.seek(0)

    if not valid:
        return "文件内容与所选资源类型不符，或文件已损坏；请重新选择正确的 PDF、DOC/DOCX、PPT/PPTX 或视频文件。"
    return ""


def _find_font(size: int):
    """找系统中文字体，失败返回 None（PIL 会退用默认）"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return None


def mp4_duration(path: Path) -> str:
    """轻量解析 MP4 moov/mvhd，返回 MM:SS / HH:MM:SS"""
    try:
        with open(path, "rb") as f:
            data = f.read()

        def read_box(b: bytes, offset: int):
            if offset + 8 > len(b):
                return None
            size = struct.unpack(">I", b[offset:offset + 4])[0]
            typ = b[offset + 4:offset + 8].decode("latin-1", errors="ignore")
            if size == 0:
                size = len(b) - offset
            elif size == 1:
                if offset + 16 > len(b):
                    return None
                size = struct.unpack(">Q", b[offset + 8:offset + 16])[0]
                return typ, offset + 16, size - 16
            return typ, offset + 8, size - 8

        def iter_top_boxes(b: bytes):
            pos = 0
            while pos + 8 <= len(b):
                box = read_box(b, pos)
                if not box:
                    break
                typ, body_start, body_size = box
                box_end = body_start + body_size
                yield typ, body_start, body_size, box_end
                pos = box_end

        def find_box(b: bytes, target: str, start: int, end: int):
            pos = start
            while pos + 8 <= end:
                box = read_box(b, pos)
                if not box:
                    break
                typ, body_start, body_size = box
                box_end = body_start + body_size
                if typ == target:
                    return body_start, body_size, box_end
                pos = box_end
            return None

        moov = None
        for typ, body_start, body_size, box_end in iter_top_boxes(data):
            if typ == "moov":
                moov = (body_start, body_size, box_end)
                break
        if not moov:
            return ""
        mvhd = find_box(data, "mvhd", moov[0], moov[2])
        if not mvhd:
            return ""
        start = mvhd[0]
        version = data[start]
        if version == 0:
            timescale = struct.unpack(">I", data[start + 12:start + 16])[0]
            duration = struct.unpack(">I", data[start + 16:start + 20])[0]
        else:
            timescale = struct.unpack(">I", data[start + 20:start + 24])[0]
            duration = struct.unpack(">Q", data[start + 24:start + 32])[0]
        if timescale == 0:
            return ""
        secs = int(duration / timescale)
        if secs >= 3600:
            return f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
        return f"{secs // 60}:{secs % 60:02d}"
    except Exception:
        return ""


def pdf_pages(path: Path) -> int:
    """PDF 总页数：取头部/尾部的 /Count 最大值"""
    try:
        with open(path, "rb") as f:
            head = f.read(32768)
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - 32768))
            tail = f.read()
        counts = [int(x) for x in re.findall(br"/Count\s+(\d+)", head + tail)]
        return max(counts) if counts else 0
    except Exception:
        return 0


def pptx_pages(path: Path) -> int:
    """PPTX 幻灯片数量"""
    try:
        with zipfile.ZipFile(path) as z:
            return sum(1 for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
    except Exception:
        return 0


def guess_type(filename: str) -> Tuple[str, str]:
    """(资源类型, 扩展名)"""
    ext = Path(filename).suffix.lower()
    for resource_type, extensions in RESOURCE_TYPE_EXTENSIONS.items():
        if ext in extensions:
            return resource_type, ext
    return "", ext


def chapter_number_of(name: str) -> int | None:
    """从文件名提取章序号：`PPT_Ch06_二叉树遍历.pptx` → 6。

    旧的 `parse_chapter()` 直接返回硬编码的章名字符串（且只覆盖前 5 章，
    第 4/5 章的名字还是旧体系），与主库 `graph_nodes` 的章名对不上。
    这里只负责取序号，章 id/章名一律由调用方查主库得到（见
    `agent_st/rag/structure.py`），媒体工具不依赖数据库。
    """
    m = re.search(r"Ch(\d{1,2})", str(name or ""), re.I)
    if not m:
        return None
    num = int(m.group(1))
    return num if 1 <= num <= 99 else None


def chapter_id_of(name: str) -> str:
    """文件名 → 章 id，如 `DOC_Ch06_...pdf` → `CH06`；取不到返回空串。"""
    num = chapter_number_of(name)
    return f"CH{num:02d}" if num else ""


def parse_title(filename: str) -> str:
    """从文件名生成可读标题"""
    name = Path(filename).stem
    name = re.sub(r"^[A-Z]+_Ch\d+_", "", name)
    return name.replace("_", " ").replace("-", " ")


def save_upload_file(file_obj, filename: str, res_id: str, course_id: str = DEFAULT_COURSE_ID) -> Path:
    """保存上传文件到统一路径 resources/{course_id}/{res_id}/，返回磁盘路径（文件名已清洗）"""
    target_dir = res_dir(course_id, res_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / safe_filename(filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return dest


def generate_cover(res_id: str, title: str, rtype: str) -> str:
    """为资源生成占位封面（480x270 JPG），返回相对路径 /resources/covers/{res_id}.jpg"""
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    out = COVERS_DIR / f"{res_id}.jpg"
    if not HAS_PIL:
        return resource_url("covers/default.jpg")

    try:
        W, H = 480, 270
        c1, c2 = TYPE_BG.get(rtype, TYPE_BG["quiz"])
        img = Image.new("RGB", (W, H), c1)
        draw = ImageDraw.Draw(img)
        # 渐变
        for y in range(H):
            ratio = y / H
            r = int(int(c1[1:3], 16) * (1 - ratio) + int(c2[1:3], 16) * ratio)
            g = int(int(c1[3:5], 16) * (1 - ratio) + int(c2[3:5], 16) * ratio)
            b = int(int(c1[5:7], 16) * (1 - ratio) + int(c2[5:7], 16) * ratio)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        font_title = _find_font(26) or ImageFont.load_default()

        # 标题（居中，自动截断）
        max_w = W - 40
        display = title
        while draw.textlength(display, font=font_title) > max_w and len(display) > 1:
            display = display[:-2] + "…"
        tw = draw.textlength(display, font=font_title)
        draw.text(((W - tw) / 2, H / 2 - 16), display, fill="#ffffff", font=font_title)

        img.save(out, "JPEG", quality=88)
        return resource_url(f"covers/{res_id}.jpg")
    except Exception:
        return resource_url(f"covers/{res_id}.jpg")
