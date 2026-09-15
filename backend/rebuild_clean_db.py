"""
干净库重建（多课程重构 Step 8）。

从当前主库提取**真实内容数据**（65 条资源记录），在全新库上执行
init_db + run_seed + bootstrap（干净起点：无任何假 transaction），
再把资源记录合并进去，产出干净库并替换主库、重制 baseline。

替换前自动备份：course_agent.db.bak.before_clean_rebuild

执行: cd backend && python rebuild_clean_db.py
"""
import os
import shutil
import sqlite3
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "app" / "data" / "course_agent.db"
TMP = BACKEND / "app" / "data" / "_clean_rebuild.db"

RESOURCE_COLS = ("res_id", "course_id", "title", "type", "kp", "kp_id", "category",
                 "duration", "pages", "count", "source", "views", "url")


def build_clean_db() -> None:
    # 1) 从主库提取真实资源记录
    src = sqlite3.connect(str(DB))
    rows = src.execute(
        f"SELECT {', '.join(RESOURCE_COLS)} FROM resources ORDER BY res_id"
    ).fetchall()
    print(f"[1/5] 从主库提取资源记录：{len(rows)} 条")
    src.close()

    # 2) 全新临时库：init_db + seed + bootstrap（干净起点，无假 transaction）
    if TMP.exists():
        os.remove(str(TMP))
    from app import config
    config.settings.DATABASE_URL = "sqlite:///" + str(TMP)
    import app.database as db_mod
    db_mod.engine = db_mod.create_engine("sqlite:///" + str(TMP),
                                         connect_args={"check_same_thread": False})
    db_mod.SessionLocal = db_mod.sessionmaker(autocommit=False, autoflush=False,
                                              bind=db_mod.engine)
    db_mod.init_db()
    from app.seed.seed_data import run_seed
    run_seed()
    from app.services.bootstrap import bootstrap
    bootstrap(verbose=False)
    print("[2/5] 新库完成 init_db + seed + bootstrap（图谱/学习路径/题库）")

    # 3) 合并资源记录
    dst = sqlite3.connect(str(TMP))
    cols = ", ".join(RESOURCE_COLS)
    ph = ", ".join("?" * len(RESOURCE_COLS))
    dst.executemany(f"INSERT INTO resources ({cols}) VALUES ({ph})", rows)
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    print(f"[3/5] 资源记录合并：{n} 条")
    dst.close()

    # 4) 资源数同步到学习路径（bootstrap 先于资源复制执行，res_count 需刷新）
    tmp_conn = sqlite3.connect(str(TMP))
    counts = {}
    for kp, cnt in tmp_conn.execute(
        "SELECT kp_id, COUNT(*) FROM resources WHERE kp_id IS NOT NULL AND kp_id<>'' GROUP BY kp_id"
    ):
        counts[kp] = cnt
    cur = tmp_conn.execute("SELECT id, kp_id, res_count FROM learning_paths")
    updated = 0
    for row_id, kp_id, res_count in cur.fetchall():
        want = counts.get(kp_id, 0)
        if (res_count or 0) != want:
            tmp_conn.execute("UPDATE learning_paths SET res_count=? WHERE id=?", (want, row_id))
            updated += 1
    tmp_conn.commit()
    print(f"[4/5] 学习路径资源数刷新：更新 {updated} 行")
    tmp_conn.close()

    # 5) 备份主库并替换 + 重制 baseline
    bak = str(DB) + ".bak.before_clean_rebuild"
    if not os.path.exists(bak):
        shutil.copy(str(DB), bak)
        print(f"[5/5] 主库已备份 → {Path(bak).name}")
    shutil.copy(str(TMP), str(DB))
    shutil.copy(str(DB), str(DB) + ".bak.baseline")
    try:
        os.remove(str(TMP))
    except OSError:
        print("  (临时文件 _clean_rebuild.db 请手动删除)")
    print("[5/5] 主库已替换为干净库，baseline 已重制")


def verify() -> bool:
    c = sqlite3.connect(str(DB))
    stats = {
        "resources(应65)": "SELECT COUNT(*) FROM resources",
        "practice_sessions(应0)": "SELECT COUNT(*) FROM practice_sessions",
        "chat_sessions(应0)": "SELECT COUNT(*) FROM chat_sessions",
        "interventions(应0)": "SELECT COUNT(*) FROM interventions",
        "reports(应0)": "SELECT COUNT(*) FROM reports",
        "user_courses(应13)": "SELECT COUNT(*) FROM user_courses",
        "questions(应229)": "SELECT COUNT(*) FROM questions",
        "learning_paths(应408)": "SELECT COUNT(*) FROM learning_paths",
    }
    for k, q in stats.items():
        v = c.execute(q).fetchone()[0]
        print(f"  {k}: {v}")
    c.close()
    return True


if __name__ == "__main__":
    build_clean_db()
    print("\n==== 干净库核验 ====")
    verify()
    print("\n完成。请启动服务做最终回归（python regression_multicourse.py）。")
