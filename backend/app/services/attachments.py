"""答疑附件（上传文件）的共享处理：师生答疑 与 管理员治理助手共用一份口径。

语义 = 「附到当前问题」：把上传文件抽取成纯文本，注入**本轮**模型输入；
**不落库正文、不进知识库**（消息上只留 `{kind:'attach', files:[{name,chars}]}` 标记用于历史回显）。

上限三处必须一致，改口径只改这里：
- 前端 chip 提示（`assets/js/shared/agent-chat.js`）
- `/ai/chat/stream`（师生）
- `/admin/agent/chat/stream`（管理员，另有账号表结构化的行数上限，见 services.account_import）
"""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.agent_st.agent.file_text import extract_file_text

MAX_ATTACH_FILES = 5
MAX_ATTACH_BYTES = 10 * 1024 * 1024          # 单个文件 10MB
MAX_ATTACH_TOTAL_CHARS = 80_000              # 全部附件抽取文本的总上限
ATTACH_HINT = ".txt / .md / .csv / .json / .xlsx / .docx / .pdf"


class AttachmentError(ValueError):
    """附件被拒（个数/体积/总量超限，或解析失败）。

    `str(exc)` 就是可直接展示给用户的人话 —— 调用方直接放进 400 响应即可。
    """


async def collect_attachments(raw_files) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """读取上传文件 → 抽取纯文本。

    返回 `(attachments, raw_uploads)`：
    - `attachments` = `[{name, chars, text}]`，直接放进 `extra['attachments']` 注入本轮问题；
    - `raw_uploads`  = `[(filename, bytes)]`，给需要**再解释一次**字节流的调用方
      （管理员端的账号表结构化解析）复用，避免重复读文件。

    被拒时抛 `AttachmentError`。
    """
    if len(raw_files) > MAX_ATTACH_FILES:
        raise AttachmentError(f"一次最多上传 {MAX_ATTACH_FILES} 个附件")

    attachments: list[dict] = []
    raw_uploads: list[tuple[str, bytes]] = []
    for f in raw_files:
        name = getattr(f, "filename", None) or "文件"
        data = await f.read()
        if len(data) > MAX_ATTACH_BYTES:
            raise AttachmentError(f"附件 {name} 超过 10MB 上限")
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
