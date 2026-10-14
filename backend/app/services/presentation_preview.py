"""使用 LibreOffice 独立进程生成课件 PDF，不依赖桌面 Office 或 COM。"""
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading

from pypdf import PdfReader

from ..config import settings

logger = logging.getLogger(__name__)
_conversion_slots = threading.BoundedSemaphore(2)


class PresentationConversionError(Exception):
    def __init__(self, message: str, code: int = 422):
        super().__init__(message)
        self.code = code


def libreoffice_executable() -> str:
    configured = settings.LIBREOFFICE_PATH.strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        raise PresentationConversionError("服务器的 LibreOffice 路径无效，请联系管理员。", 503)
    names = ("soffice.com", "soffice", "libreoffice") if os.name == "nt" else ("soffice", "libreoffice")
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    candidates = [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")]
    if os.name == "nt":
        candidates = [Path(os.environ.get(key, default)) / "LibreOffice/program/soffice.com"
                      for key, default in (("ProgramFiles", "C:/Program Files"),
                                           ("ProgramFiles(x86)", "C:/Program Files (x86)"))]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise PresentationConversionError(
        "服务器尚未安装 LibreOffice，暂不能转换 PPT；请联系管理员安装，或先将课件导出为 PDF 后重新上传。", 503)


def _run_conversion(command: list[str]) -> None:
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    try:
        stdout, stderr = process.communicate(timeout=max(1, settings.PRESENTATION_CONVERT_TIMEOUT))
    except subprocess.TimeoutExpired:
        # 回收本次独立转换进程及子进程，防止锁住临时目录或影响下一次上传。
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired):
            logger.exception("Could not terminate conversion process tree")
        finally:
            process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.stdout.close()
                process.stderr.close()
        raise PresentationConversionError("课件转 PDF 超时，请缩小文件后重新上传，或自行导出 PDF。", 504)
    if process.returncode:
        logger.warning("LibreOffice conversion failed: %r %r", stdout[-2000:], stderr[-2000:])
        raise PresentationConversionError("课件无法转为 PDF，请检查文件是否损坏或加密，或自行导出 PDF 后上传。")


def convert_presentation_upload(file_obj, filename: str):
    """返回 (可读 PDF 临时流, 页数)，调用者负责关闭流。成功前不发布任何资源文件。"""
    executable = libreoffice_executable()
    if not _conversion_slots.acquire(timeout=10):
        raise PresentationConversionError("课件转换繁忙，请稍后重新上传。", 503)
    output = None
    try:
        with tempfile.TemporaryDirectory(prefix="course-presentation-") as temp:
            work = Path(temp)
            source = work / ("source" + Path(filename).suffix.lower())
            file_obj.seek(0)
            with source.open("wb") as target:
                shutil.copyfileobj(file_obj, target)
            profile = work / "profile"
            profile.mkdir()
            # 每个请求独享 profile，避免与用户桌面 LibreOffice 或其它上传相互抢占。
            _run_conversion([executable, "-env:UserInstallation=" + profile.as_uri(),
                             "--headless", "--nologo", "--nodefault", "--norestore",
                             "--convert-to", "pdf:impress_pdf_Export", "--outdir", str(work), str(source)])
            pdf = source.with_suffix(".pdf")
            if not pdf.is_file():
                raise PresentationConversionError("课件未能生成 PDF，请检查文件是否损坏或加密，或自行导出 PDF 后上传。")
            with pdf.open("rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted or not reader.pages:
                    raise PresentationConversionError("转换后的 PDF 无法阅读，请自行导出 PDF 后重新上传。")
                pages = len(reader.pages)
                output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
                stream.seek(0)
                shutil.copyfileobj(stream, output)
                output.seek(0)
        return output, pages
    except PresentationConversionError:
        if output is not None:
            output.close()
        raise
    except Exception as exc:
        if output is not None:
            output.close()
        logger.exception("Presentation conversion failed")
        raise PresentationConversionError("课件转换失败，请重新上传，或先将课件导出为 PDF。") from exc
    finally:
        file_obj.seek(0)
        _conversion_slots.release()
