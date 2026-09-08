"""
离线构建 RAG 知识库（rag.db）：
  1. 课后题库 after_class.json（题干 + 解析切片）
  2. 正式版资源中心教材 PDF（assets/resources/data-structures-1-9/textbooks/*.pdf，9 本）
  3. 正式版资源中心课件 PPTX（assets/resources/data-structures-1-9/slides/*.pptx）

不放在启动流程中执行：入库耗时且消耗 embedding 额度，由运维按需运行。
embedding 模型漂移（切换供应商/模型）时本脚本会自动重算失效向量。

执行: cd backend && python3.11 run_st_ingest.py
"""
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = BACKEND_DIR.parent
RESOURCES_DIR = PROJECT_ROOT / "assets" / "resources" / "data-structures-1-9"


def main():
    from app.agent_st.rag.ingest import ensure_bank_indexed, ingest_path
    from app.agent_st.rag.store import ChunkStore
    from app.agent_st.rag.embed import active_model_name

    print("=" * 60)
    print("RAG 知识库构建（题库 + 教材 + 课件）")
    print(f"embedding 模型: {active_model_name()}")
    print("=" * 60)

    print("\n[1/3] 题库自检与入库 ...")
    result = ensure_bank_indexed()
    print(f"  -> {result}")

    print("\n[2/3] 教材 PDF ...")
    pdfs = sorted((RESOURCES_DIR / "textbooks").glob("*.pdf")) if (RESOURCES_DIR / "textbooks").exists() else []
    print(f"  发现 {len(pdfs)} 本教材")
    for p in pdfs:
        t0 = time.time()
        try:
            r = ingest_path(p)
            print(f"  {p.name}: {r.get('chunks')} 切片 ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001  单文件失败不中断
            print(f"  {p.name}: 失败 {exc}")

    print("\n[3/3] 课件 PPTX ...")
    ppts = sorted((RESOURCES_DIR / "slides").glob("*.pptx")) if (RESOURCES_DIR / "slides").exists() else []
    print(f"  发现 {len(ppts)} 份课件")
    for p in ppts:
        t0 = time.time()
        try:
            r = ingest_path(p)
            print(f"  {p.name}: {r.get('chunks')} 切片 ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"  {p.name}: 失败 {exc}")

    store = ChunkStore()
    print("\n" + "=" * 60)
    print(f"完成。rag.db 共 {store.count()} 条切片")
    print(f"各模型分布: {store.embedding_model_counts()}")


if __name__ == "__main__":
    main()
