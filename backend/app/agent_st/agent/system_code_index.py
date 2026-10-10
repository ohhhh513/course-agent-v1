"""角色隔离的界面源码检索；增量刷新、原子缓存，不访问业务数据库。

这是源码片段索引，不是 JavaScript 解释器。返回证据供模型追踪渲染与绑定，
不把一段模板或一个函数的存在等同于可执行功能。
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata

LOG = logging.getLogger(__name__)
VERSION = 1
ROLES = ("student", "teacher", "admin")
CHAT_VIEWS = {"student": "ai", "teacher": "chat", "admin": "assistant"}
REGISTER = re.compile(r"Router\.register\(\s*['\"]([^'\"]+)['\"]")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages = {}
        self.scripts = []
        self._view = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"].split("?", 1)[0])
        if attrs.get("data-view"):
            self._view = attrs["data-view"]
            self.pages[self._view] = ""
            self._depth = 1
        elif self._view:
            self._depth += 1

    def handle_endtag(self, tag):
        if self._view:
            self._depth -= 1
            if self._depth <= 0:
                self._view = None

    def handle_data(self, data):
        if self._view:
            self.pages[self._view] += data.strip()


def terms(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    result = set(re.findall(r"[a-z_][a-z0-9_-]+", text))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        result.update(run[i:i + 2] for i in range(len(run) - 1))
    return result


class SystemCodeIndex:
    def __init__(self, root: Path, cache_path: Path | None = None):
        self.root = root.resolve()
        self.cache_path = cache_path
        self.lock = threading.RLock()
        self.files = {}
        self.pages = {}
        self.records = []
        self._search = {}
        self.stats = {}
        if cache_path and cache_path.is_file():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if data.get("version") == VERSION and data.get("root") == str(self.root):
                    entries = data["files"]
                    if not isinstance(entries, dict) or any(
                        not isinstance(entry, dict) or not isinstance(entry.get("text"), str)
                        or not isinstance(entry.get("sha256"), str) or "signature" not in entry
                        for entry in entries.values()
                    ):
                        raise ValueError("缓存文件清单格式错误")
                    # 磁盘切片是可重建产物，不信任其位置和正文，重新按缓存文本切片。
                    self.files = {path: {"signature": entry["signature"], "sha256": entry["sha256"],
                                         "text": entry["text"], "chunks": self._chunks(entry["text"])}
                                  for path, entry in entries.items()}
            except (OSError, ValueError, KeyError, TypeError):
                LOG.warning("界面源码索引缓存不可读，将从源码重建", exc_info=True)

    def _path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("源码路径越出项目目录")
        return path

    def _read(self, relative: str, updated: dict, changed: set) -> str:
        if relative in updated:
            return updated[relative]["text"]
        path = self._path(relative)
        stat = path.stat()
        if stat.st_size > 2_000_000:
            raise ValueError("界面源码超过索引大小限制")
        signature = [stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino]
        old = self.files.get(relative, {})
        # 读取期间再次被保存时重试；不发布混合版本的文件内容。
        for _ in range(3):
            raw = path.read_bytes()
            after = path.stat()
            final = [after.st_mtime_ns, after.st_ctime_ns, after.st_size, after.st_ino]
            if signature == final:
                break
            signature = final
        else:
            raise OSError(f"源码正在连续保存：{relative}")
        digest = sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig")
        if old.get("sha256") == digest and old.get("text") == text:
            updated[relative] = {**old, "signature": signature}
            return old["text"]
        changed.add(relative)
        updated[relative] = {"signature": signature, "sha256": digest, "text": text,
                             "chunks": self._chunks(text)}
        return text

    @staticmethod
    def _chunks(text):
        lines = text.splitlines()
        return [{"start": start + 1, "end": min(start + 64, len(lines)),
                 "text": "\n".join(lines[start:start + 64])}
                for start in range(0, len(lines), 48)]

    def refresh(self):
        """每次查询校验有限的已加载源码指纹；只重新切片内容变动的文件。

        Windows 的 ctime 可能是创建时间，不能仅用 mtime/大小判断覆盖保存。
        对小规模界面源码读取 SHA256，可识别同大小、保留时间戳的替换。
        不递归扫描仓库、数据库或资源，不重新切片未改变的源码。
        """
        with self.lock:
            started = time.perf_counter()
            updated, changed, specs, pages = {}, set(), [], {}
            for role in ROLES:
                html_path = f"{role}.html"
                parser = PageParser()
                parser.feed(self._read(html_path, updated, changed))
                pages[role] = parser.pages
                specs.append((html_path, role, ""))
                for src in dict.fromkeys(parser.scripts):
                    # 白名单来自当前 HTML；不索引 API 总文件、vendor、其他角色或任意路径。
                    common = {"assets/js/shared/agent-chat.js", "assets/js/shared/agent-ui.js", "assets/js/common.js", "assets/js/auth.js"}
                    role_source = src.startswith(f"assets/js/{role}/")
                    if not (role_source or src in common):
                        continue
                    path = self._path(src)
                    if role_source and not path.is_relative_to(self.root / "assets" / "js" / role):
                        continue
                    if not path.is_file():
                        continue
                    source = self._read(src, updated, changed)
                    registered = set(REGISTER.findall(source))
                    views = registered & parser.pages.keys()
                    if registered and not views:
                        continue  # 已移除的教学干预、不可见路由等。
                    if src == "assets/js/shared/agent-chat.js":
                        views = {CHAT_VIEWS[role]} & parser.pages.keys()
                    if not views and "/views/" in src:
                        continue
                    for view in sorted(views) if views else [""]:
                        specs.append((src, role, view))
            removed = set(self.files) - set(updated)
            topology = [(path, role, view) for path, role, view in specs]
            rebuild = bool(changed or removed or pages != self.pages or topology != getattr(self, "_topology", None))
            self.files, self.pages = updated, pages
            if rebuild:
                self._topology = topology
                self.records = [{**chunk, "source": path, "role": role, "view": view,
                                 "page": pages[role].get(view, "顶栏与通用界面"),
                                 "revision": updated[path]["sha256"]}
                                for path, role, view in specs for chunk in updated[path]["chunks"]]
                self._build_search()
            if changed or removed:
                self._persist()
            self.stats = {"files": len(updated), "chunks": len(self.records), "changed": sorted(changed),
                          "removed": sorted(removed), "refresh_ms": round((time.perf_counter() - started) * 1000, 2)}
            return dict(self.stats)

    def _build_search(self):
        self._search = {}
        for role in ROLES:
            records = [r for r in self.records if r["role"] == role]
            bags = [terms(r["text"]) | terms(r["page"]) for r in records]
            frequency = Counter(term for bag in bags for term in bag)
            weights = {term: math.log(1 + len(records) / count) for term, count in frequency.items()}
            self._search[role] = (records, bags, weights)

    def _persist(self):
        if self.cache_path is None:
            return
        temporary = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.cache_path.parent,
                                             prefix="system-code-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": VERSION, "root": str(self.root), "files": self.files}, stream, ensure_ascii=False)
            os.replace(temporary, self.cache_path)
        except OSError:
            # 缓存不可写不影响从当前源码查询；绝不退回陈旧磁盘结果。
            LOG.warning("无法保存界面源码缓存，本进程继续使用新索引", exc_info=True)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def search(self, role: str, query: str, view: str = "", limit: int = 4) -> dict:
        with self.lock:
            self.refresh()
            if role not in self.pages or (view and view not in self.pages[role]):
                return {"found": False, "sources": [], "error": "页面不属于当前角色"}
            records, bags, weights = self._search[role]
            needle = terms(query)
            ranked = []
            for record, bag in zip(records, bags):
                if view and record["view"] not in (view, ""):
                    continue
                overlap = needle & bag
                if query.strip() and not overlap:
                    continue
                score = sum(weights.get(term, 0) for term in overlap)
                if query.strip() and query.strip() in record["text"]:
                    score += 8
                if not needle and not view:
                    continue
                ranked.append((score, record))
            ranked.sort(key=lambda item: item[0], reverse=True)
            selected = []
            for score, record in ranked:
                if any(record["source"] == r["source"] and abs(record["start"] - r["start"]) < 48 for r in selected):
                    continue
                selected.append({**record, "text": record["text"][:10000],
                                 "truncated": len(record["text"]) > 10000, "score": round(score, 2)})
                if len(selected) >= max(1, min(int(limit), 8)):
                    break
            return {"found": bool(selected), "sources": selected,
                    "index": {"files": self.stats["files"], "refresh_ms": self.stats["refresh_ms"]}}

    def page_index(self, role: str) -> str:
        with self.lock:
            self.refresh()
            lines = ["当前登录角色可用的系统操作目录（实时源码索引，内部 view 不写进回答）："]
            for view, title in self.pages.get(role, {}).items():
                lines.append(f"{view} | {title}")
            lines.append("按钮细节从 get_system_guide(query=完整操作问题, view=可选页面) 检索实际源码；无需预先登记功能编号。")
            return "\n".join(lines)


_INSTANCE = None
_INSTANCE_LOCK = threading.Lock()


def get_code_index() -> SystemCodeIndex:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            from app.config import settings
            _INSTANCE = SystemCodeIndex(Path(settings.FRONTEND_DIR),
                                        Path(settings.AGENT_DATA_DIR) / "system_code_index.json")
        return _INSTANCE
