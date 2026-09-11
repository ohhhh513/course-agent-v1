"""
一次性迁移脚本：把旧版资源目录结构迁移到统一路径规范。

旧结构（已废弃，2026-09-11 约定）：
    resources/data-structures-1-9/{videos,slides,textbooks}/{文件名}   ← 早期“内置资源”
    resources/uploads/{res_id}/{文件名}                                ← 早期教师上传
新结构（统一规范）：
    resources/{course_id}/{res_id}/{文件名}                            ← 全部资源，教师上传添加

做三件事（全部幂等，可重复执行）：
  1. 数据库 url 若仍是旧前缀 /assets/resources/...，替换为 /resources/...；
  2. 磁盘文件若还在旧结构（data-structures-1-9/ 或 uploads/），移动到
     resources/{course_id}/{res_id}/，并同步更新该记录的 url；
  3. 清理迁移后残留的空目录（data-structures-1-9/、uploads/）。

执行: cd backend && python3.11 migrate_resource_paths.py
"""
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))

from app.media_utils import (  # noqa: E402
    RESOURCES_DIR,
    url_to_path,
    safe_filename,
)

DB_PATH = BACKEND_DIR / "app" / "data" / "course_agent.db"

LEGACY_SUBDIRS = ("data-structures-1-9", "uploads")


def migrate() -> None:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ---- 1) URL 前缀统一（/assets/resources → /resources）----
    n = cur.execute(
        "SELECT COUNT(*) FROM resources WHERE url LIKE '/assets/resources/%'"
    ).fetchone()[0]
    if n:
        cur.execute(
            "UPDATE resources SET url = replace(url, '/assets/resources/', '/resources/') "
            "WHERE url LIKE '/assets/resources/%'"
        )
        print(f"[1/3] 已统一 {n} 条 url 前缀 → /resources")
    else:
        print("[1/3] url 前缀均已为 /resources，无需处理")

    # ---- 2) 磁盘文件迁移到 resources/{course_id}/{res_id}/ ----
    rows = cur.execute(
        "SELECT res_id, course_id, url FROM resources WHERE url IS NOT NULL AND url<>''"
    ).fetchall()
    moved = missing = already = 0
    for r in rows:
        res_id, course_id, url = r["res_id"], r["course_id"], r["url"]
        target = url_to_path(url)
        if target is None:
            print(f"  [跳过] {res_id}: 无法识别的 url（{url}）")
            missing += 1
            continue
        if target.exists():
            already += 1
            continue

        filename = safe_filename(Path(url).name)
        # 在旧结构中寻找文件
        src = None
        for legacy in LEGACY_SUBDIRS:
            cand = RESOURCES_DIR / legacy / res_id / filename        # uploads/{res_id}/
            if cand.exists():
                src = cand
                break
            cand = RESOURCES_DIR / legacy / url.split(f"/{legacy}/", 1)[-1]  # data-structures-1-9/相对路径
            if url.find(f"/{legacy}/") != -1 and cand.exists():
                src = cand
                break
        if src is None:
            print(f"  [缺失] {res_id}: 新旧位置都找不到文件（{url}）")
            missing += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        new_url = f"/resources/{course_id}/{res_id}/{filename}"
        if new_url != url:
            cur.execute("UPDATE resources SET url=? WHERE res_id=?", (new_url, res_id))
        moved += 1
        print(f"  [迁移] {res_id}: {src.name} → {new_url}")
    con.commit()
    print(f"[2/3] 磁盘迁移：移动 {moved}，本就已在新位置 {already}，缺失 {missing}")

    # ---- 3) 清理残留空目录 ----
    removed = 0
    for legacy in LEGACY_SUBDIRS:
        base = RESOURCES_DIR / legacy
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                try:
                    p.rmdir()
                    removed += 1
                except OSError:
                    pass
        try:
            if base.is_dir() and not any(base.iterdir()):
                base.rmdir()
                removed += 1
        except OSError:
            pass
    print(f"[3/3] 清理残留空目录 {removed} 个")

    # ---- 最终校验 ----
    bad = 0
    for r in cur.execute("SELECT res_id, url FROM resources WHERE url IS NOT NULL AND url<>''"):
        p = url_to_path(r["url"])
        if p is None or not p.exists():
            bad += 1
            print(f"  [校验失败] {r['res_id']} {r['url']}")
    print(f"\n校验：断链记录 {bad} 条" + ("（全部通过 ✓）" if bad == 0 else ""))
    con.close()


if __name__ == "__main__":
    migrate()
