"""
从资源登记表快照恢复资源记录（删库重建的恢复手册最后一步）。

适用场景：course_agent.db 被删除后，已重新执行 init_db + run_seed + bootstrap，
磁盘 resources/ 目录与 rag.db 完好，此时运行本脚本即可按
resource_registry_snapshot.json 把 65 条资源记录（含 res_id、kp 挂载）
原样恢复 —— res_id 不变，与磁盘目录和 RAG 切片保持对应。

幂等：INSERT OR REPLACE（可重复执行）。
执行: cd backend && python restore_resources_from_snapshot.py
"""
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.media_utils import url_to_path  # noqa: E402  统一的 URL→磁盘路径映射

DB = BACKEND / "app" / "data" / "course_agent.db"
SNAPSHOT = BACKEND / "app" / "data" / "resource_registry_snapshot.json"

COLS = ("res_id", "course_id", "title", "type", "kp", "kp_id", "category",
        "duration", "pages", "source", "views", "url")


def main() -> None:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = snap.get("resources", [])
    print(f"快照记录：{len(rows)} 条")

    con = sqlite3.connect(str(DB))
    cols = ", ".join(COLS)
    ph = ", ".join("?" * len(COLS))
    con.executemany(
        f"INSERT OR REPLACE INTO resources ({cols}) VALUES ({ph})",
        [tuple(r[c] for c in COLS) for r in rows],
    )
    # 恢复学习路径上的资源数
    counts = {}
    for kp, cnt in con.execute(
        "SELECT kp_id, COUNT(*) FROM resources WHERE kp_id IS NOT NULL AND kp_id<>'' GROUP BY kp_id"
    ):
        counts[kp] = cnt
    cur = con.execute("SELECT id, kp_id, res_count FROM learning_paths")
    updated = 0
    for row_id, kp_id, res_count in cur.fetchall():
        want = counts.get(kp_id, 0)
        if (res_count or 0) != want:
            con.execute("UPDATE learning_paths SET res_count=? WHERE id=?", (want, row_id))
            updated += 1
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    missing = []
    for r in rows:
        p = url_to_path(r["url"])
        if p is None or not p.exists():
            missing.append((r["res_id"], r["url"]))
    print(f"恢复完成：resources 表 {n} 条；学习路径 res_count 更新 {updated} 行")
    if missing:
        print(f"⚠️ 有 {len(missing)} 条记录的磁盘文件缺失（请核对 resources/ 目录）：")
        for rid, url in missing[:10]:
            print(f"   {rid} {url}")
    else:
        print("✅ 全部记录的磁盘文件均在位（url 与文件一一对应）")
    con.close()


if __name__ == "__main__":
    main()
