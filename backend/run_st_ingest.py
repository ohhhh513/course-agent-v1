"""
离线构建 RAG 知识库（rag.db）：
  1. 课后题库 after_class.json（题干 + 解析切片）
  2. 资源库中的教材 PDF 与课件 PPTX —— 从 resources 表读取清单，
     经 media_utils.url_to_path() 反解磁盘文件（统一路径
     resources/{course_id}/{res_id}/{文件名}，教师上传的资源同样会被收录）。

不放在启动流程中执行：入库耗时且消耗 embedding 额度，由运维按需运行。
embedding 模型漂移（切换供应商/模型）时本脚本会自动重算失效向量。

执行: cd backend && python3.11 run_st_ingest.py
"""
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))


def main():
    from app.agent_st.rag.ingest import ensure_bank_indexed, ingest_path
    from app.agent_st.rag.store import ChunkStore
    from app.agent_st.rag.embed import active_model_name
    from app.media_utils import url_to_path
    from app.services.resource_registry import open_conn

    print("=" * 60)
    print("RAG 知识库构建（题库 + 资源库文件）")
    print(f"embedding 模型: {active_model_name()}")
    print("=" * 60)

    print("\n[1/3] 题库自检与入库 ...")
    result = ensure_bank_indexed()
    print(f"  -> {result}")

    print("\n[2/3] 从 resources 表收集可入库文件（教材 PDF / 课件 PPT）...")
    conn = open_conn()
    rows = conn.execute(
        "SELECT res_id, title, type, url FROM resources WHERE url IS NOT NULL AND url<>''"
    ).fetchall()
    conn.close()

    targets = []          # (类别, 磁盘路径)
    skipped = 0
    for res_id, title, rtype, url in rows:
        p = url_to_path(url)
        if p is None or not p.exists():
            skipped += 1
            print(f"  [跳过] {res_id} {title}: 文件缺失（{url}）")
            continue
        suffix = p.suffix.lower()
        if rtype == "doc" and suffix == ".pdf":
            targets.append(("教材", p))
        elif rtype == "ppt" and suffix in (".ppt", ".pptx"):
            targets.append(("课件", p))
        # 其余类型（mp4/docx/doc 等）没有文本解析器，不入库

    pdfs = [p for kind, p in targets if kind == "教材"]
    ppts = [p for kind, p in targets if kind == "课件"]
    print(f"  待入库：教材 {len(pdfs)} 本、课件 {len(ppts)} 份（跳过文件缺失 {skipped} 项）")

    print("\n[3/3] 逐文件切片入库 ...")
    t0_all = time.time()
    done = failed = 0
    for kind, p in targets:
        t0 = time.time()
        try:
            r = ingest_path(p)
            done += 1
            print(f"  [{kind}] {p.name}: {r.get('chunks')} 切片 ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001  单文件失败不中断
            failed += 1
            print(f"  [{kind}] {p.name}: 失败 {exc}")

    store = ChunkStore()
    print("\n" + "=" * 60)
    print(f"完成：成功 {done}，失败 {failed}，耗时 {time.time() - t0_all:.0f}s")
    print(f"rag.db 共 {store.count()} 条切片")
    print(f"各模型分布: {store.embedding_model_counts()}")


if __name__ == "__main__":
    main()
