"""资源一致性校验：检查 resources 表与磁盘文件的一致性。

历史说明：本模块曾负责「扫描内置目录 resources/data-structures-1-9/ 自动登记资源」，
该机制已废弃（2026-09-11 约定）——资源一律由教师上传，统一路径
resources/{course_id}/{res_id}/{文件名}，不再存在“内置资源”通道；
配套的一次性导入脚本 import_course_resources.py 已随之删除。

现在只保留一个职责：**一致性校验**，发现两类问题：
  1. 断链记录（DB 有、磁盘无）：多由资源文件被手动移动/删除导致；
  2. 孤儿文件（磁盘有、DB 无）：多由用数据库快照回滚导致（文件不随库回滚）。
启动时默认只报告不处理，避免网络盘未挂载等临时故障造成误删；
需要处理时显式传 remove_missing / delete_orphan_files=True。
"""
import sqlite3
from pathlib import Path

from ..config import settings
from ..media_utils import (
    RESOURCES_DIR,
    COVERS_DIR,
    resource_url,
    url_to_path,
)


def _db_path() -> Path:
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return settings.BASE_DIR / "data" / "course_agent.db"


def open_conn() -> sqlite3.Connection:
    return sqlite3.connect(str(_db_path()))


def verify_resources(
    conn: sqlite3.Connection,
    *,
    remove_missing: bool = False,
    delete_orphan_files: bool = False,
    verbose: bool = True,
) -> dict:
    """校验资源记录与磁盘文件的一致性，返回 {'missing': [...], 'orphans': [...]}。

    - missing：DB 有记录但磁盘文件不存在（url 无法反解，或文件缺失）
    - orphans：磁盘有文件但 DB 无记录（典型成因：用 .bak 快照恢复数据库）
    remove_missing=True 时删除断链记录；delete_orphan_files=True 时删除孤儿文件。
    """
    cur = conn.cursor()

    # 1) DB 有、磁盘无 → 断链记录
    missing = []
    for res_id, url in cur.execute(
        "SELECT res_id, url FROM resources WHERE url IS NOT NULL AND url<>''"
    ).fetchall():
        p = url_to_path(url)
        if p is None or not p.exists():
            missing.append({"res_id": res_id, "url": url})
            if remove_missing:
                cur.execute("DELETE FROM resources WHERE res_id=?", (res_id,))
                cover = COVERS_DIR / f"{res_id}.jpg"
                if cover.exists():
                    cover.unlink()

    # 2) 磁盘有、DB 无 → 孤儿文件（按统一结构 resources/{course_id}/{res_id}/ 扫描）
    known_urls = {
        r[0] for r in cur.execute("SELECT url FROM resources WHERE url IS NOT NULL AND url<>''")
    }
    orphans = []
    if RESOURCES_DIR.is_dir():
        for course_path in sorted(RESOURCES_DIR.iterdir()):
            if not course_path.is_dir() or course_path.name == "covers":
                continue
            for res_path in sorted(course_path.iterdir()):
                if not res_path.is_dir():
                    orphans.append(str(res_path))       # 直接躺在课程目录下的散文件
                    continue
                for f in sorted(res_path.iterdir()):
                    rel = "/".join(f.relative_to(RESOURCES_DIR).parts)
                    if resource_url(rel) not in known_urls:
                        orphans.append(str(f))
    if delete_orphan_files:
        for p in orphans:
            Path(p).unlink(missing_ok=True)

    conn.commit()
    if verbose:
        tag = "（已处理）" if (remove_missing or delete_orphan_files) else "（仅报告）"
        print(f"[resource-verify] 断链记录 {len(missing)} 条，孤儿文件 {len(orphans)} 个{tag}")
        for m in missing[:5]:
            print(f"  - missing: {m['res_id']} {m['url']}")
        for o in orphans[:5]:
            print(f"  - orphan : {o}")
    return {"missing": missing, "orphans": orphans}
