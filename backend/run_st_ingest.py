"""
离线构建 RAG 知识库（rag.db），**按课程**执行：
  1. 课后题库 after_class.json（题干 + 解析切片）—— 仅当该课程是配置声明的题库归属课程
  2. 该课程的资源库文件 —— 从 resources 表按 course_id 读取清单，
     经 media_utils.url_to_path() 反解磁盘文件（统一路径
     resources/{course_id}/{res_id}/{文件名}），切片以 `{res_id}/{文件名}` 为来源标识

不放在启动流程中执行：入库耗时且消耗 embedding 额度，由运维按需运行。
embedding 模型漂移（切换供应商/模型）时本脚本会自动重算失效向量。

执行:
    cd backend && python3.11 run_st_ingest.py <course_id>
    cd backend && python3.11 run_st_ingest.py            # 取 ST_BANK_COURSE_ID / .env 里的值
"""
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))


def _resolve_course_id(argv: list[str]) -> str:
    from app.config import settings
    from app.database import SessionLocal
    from app.models.course import Course

    raw = ""
    for arg in argv:
        if arg.startswith("--course-id="):
            raw = arg.split("=", 1)[1].strip()
        elif not arg.startswith("-"):
            raw = arg.strip()
    if raw:
        return raw
    if settings.ST_BANK_COURSE_ID:
        return settings.ST_BANK_COURSE_ID
    db = SessionLocal()
    try:
        codes = [c.course_id for c in db.query(Course).all()]
    finally:
        db.close()
    raise SystemExit(
        "未指定 course_id。用法：python run_st_ingest.py <course_id>\n"
        f"（或在 backend/app/.env 设置 ST_BANK_COURSE_ID；当前库内课程：{codes or '无'}）"
    )


def main():
    from app.agent_st.rag.ingest import ingest_bank, ingest_path, reembed_stale_chunks
    from app.agent_st.rag.store import ChunkStore
    from app.agent_st.rag.embed import active_model_name
    from app.agent_st.agent.config import get_settings
    from app.media_utils import url_to_path
    from app.services.resource_registry import open_conn

    course_id = _resolve_course_id(sys.argv[1:])
    settings = get_settings()

    print("=" * 60)
    print(f"RAG 知识库构建（课程 {course_id}）")
    print(f"embedding 模型: {active_model_name()}")
    print("=" * 60)

    store = ChunkStore()
    print(f"入库前该课程切片数: {store.count(course_id)}")

    print("\n[1/4] 向量漂移自愈（全库）...")
    print(f"  -> {reembed_stale_chunks(store)}")

    print("\n[2/4] 课后题库入库 ...")
    if settings.bank_course_id == course_id:
        try:
            print(f"  -> {ingest_bank(course_id, store=store)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  -> 失败：{exc}")
    else:
        print(f"  -> 跳过：题库 JSON 的归属课程为 {settings.bank_course_id or '(未设置)'}，"
              f"与本次课程不一致（题库不再跨课程灌入）")

    print("\n[3/4] 从 resources 表收集本课程可入库文件（教材 PDF / 课件 PPT）...")
    conn = open_conn()
    rows = conn.execute(
        "SELECT res_id, title, type, url FROM resources "
        "WHERE course_id = ? AND url IS NOT NULL AND url <> ''",
        (course_id,),
    ).fetchall()
    conn.close()

    targets = []          # (类别, res_id, 磁盘路径)
    skipped = 0
    for res_id, title, rtype, url in rows:
        p = url_to_path(url)
        if p is None or not p.exists():
            skipped += 1
            print(f"  [跳过] {res_id} {title}: 文件缺失（{url}）")
            continue
        suffix = p.suffix.lower()
        if rtype == "doc" and suffix == ".pdf":
            targets.append(("教材", res_id, p))
        elif rtype == "ppt" and suffix in (".ppt", ".pptx"):
            targets.append(("课件", res_id, p))
        # 其余类型（mp4/docx/doc 等）没有文本解析器，不入库

    pdfs = [t for t in targets if t[0] == "教材"]
    ppts = [t for t in targets if t[0] == "课件"]
    print(f"  待入库：教材 {len(pdfs)} 本、课件 {len(ppts)} 份（跳过文件缺失 {skipped} 项）")

    print("\n[4/4] 逐文件切片入库 ...")
    t0_all = time.time()
    done = failed = 0
    for kind, res_id, p in targets:
        t0 = time.time()
        try:
            r = ingest_path(p, course_id=course_id, source_key=f"{res_id}/{p.name}")
            done += 1
            print(f"  [{kind}] {res_id}/{p.name}: {r.get('chunks')} 切片 ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001  单文件失败不中断
            failed += 1
            print(f"  [{kind}] {res_id}/{p.name}: 失败 {exc}")

    print("\n" + "=" * 60)
    print(f"完成：成功 {done}，失败 {failed}，耗时 {time.time() - t0_all:.0f}s")
    print(f"本课程切片：{store.count(course_id)} 条")
    print(f"全库切片：{store.count()} 条；各课程分布: {store.course_counts()}")
    print(f"本课程向量模型分布: {store.embedding_model_counts(course_id)}")


if __name__ == "__main__":
    main()
