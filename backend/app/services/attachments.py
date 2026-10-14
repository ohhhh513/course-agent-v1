"""智能体聊天附件的共享校验与内容提取。
文件正文和图像字节只注入当轮模型输入；原始文件由 chat_attachments.py 持久化到 AGENT_DATA_DIR 上传目录。
历史消息的 tool_log 只保存附件 ID 与展示元数据，不保存文件正文或图像字节。

上限三处必须一致，改口径只改这里：
- 前端 chip 提示（assets/js/shared/agent-chat.js）
- /ai/chat/stream（师生）
- /admin/agent/chat/stream（管理员，另有账号表结构化的行数上限，见 services.account_import）"""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.agent_st.agent.file_text import (
    detect_image_mime,
    extract_file_text,
    image_mime_for_extension,
)

MAX_ATTACH_FILES = 5
MAX_ATTACH_BYTES = 10 * 1024 * 1024          # 单个文件 10MB
MAX_ATTACH_TOTAL_CHARS = 80_000              # 全部附件抽取文本的总上限
MAX_ATTACH_TOTAL_IMAGE_BYTES = 32 * 1024 * 1024  # 控制 base64 后的模型请求体积
ATTACH_HINT = ".txt / .md / .csv / .json / .xlsx / .docx / .pdf / .jpg / .jpeg / .png / .gif / .webp"


class AttachmentError(ValueError):
    """附件被拒（个数/体积/总量超限，或解析失败）。

    `str(exc)` 就是可直接展示给用户的人话 —— 调用方直接放进 400 响应即可。
    """


async def collect_attachments(raw_files) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """读取上传文件 → 抽取文档文本，或保留图片字节供本轮模型识图。

    返回 `(attachments, raw_uploads)`：
    - `attachments` = 文本附件 `{name, chars, text}` 或图片附件
      `{name, chars: 0, text: '', image_bytes, image_mime}`，只注入本轮问题；
    - `raw_uploads`  = `[(filename, bytes)]`，给需要**再解释一次**字节流的调用方
      （管理员端的账号表结构化解析）复用，避免重复读文件。

    被拒时抛 `AttachmentError`。
    """
    if len(raw_files) > MAX_ATTACH_FILES:
        raise AttachmentError(f"一次最多上传 {MAX_ATTACH_FILES} 个附件")

    attachments: list[dict] = []
    raw_uploads: list[tuple[str, bytes]] = []
    total_image_bytes = 0
    for f in raw_files:
        name = getattr(f, "filename", None) or "文件"
        data = await f.read()
        if len(data) > MAX_ATTACH_BYTES:
            raise AttachmentError(f"附件 {name} 超过 10MB 上限")
        expected_image_mime = image_mime_for_extension(name)
        detected_image_mime = detect_image_mime(data)
        if expected_image_mime:
            if detected_image_mime != expected_image_mime:
                raise AttachmentError(f"附件 {name} 不是有效的 {expected_image_mime} 图片")
            total_image_bytes += len(data)
            if total_image_bytes > MAX_ATTACH_TOTAL_IMAGE_BYTES:
                raise AttachmentError("本轮图片总大小不能超过 32MB，请减少图片或压缩后重试")
            attachments.append({
                "name": name,
                "chars": 0,
                "text": "",
                "image_bytes": data,
                "image_mime": detected_image_mime,
            })
            raw_uploads.append((name, data))
            continue
        if detected_image_mime:
            raise AttachmentError(f"附件 {name} 的扩展名与图片内容不匹配")
        try:
            text = await run_in_threadpool(extract_file_text, name, data)
        except Exception as exc:  # noqa: BLE001 —— 解析失败一律转成用户可读提示
            raise AttachmentError(f"附件 {name} 解析失败：{exc}") from exc
        remaining = MAX_ATTACH_TOTAL_CHARS - sum(int(a.get("chars") or 0) for a in attachments)
        if remaining <= 0:
            raise AttachmentError(
                f"附件文本总量超过上限（{MAX_ATTACH_TOTAL_CHARS} 字），请减少文件")
        if len(text) > remaining:
            text = text[:remaining] + "\n…（因附件总量上限已截断）"
        attachments.append({"name": name, "chars": len(text), "text": text})
        raw_uploads.append((name, data))
    return attachments, raw_uploads
