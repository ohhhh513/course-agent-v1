"""
测试新写入的题目草稿箱是否真能被列表 + 发布链路识别。

不依赖 dev_tools，使用 tmp 副本库 + 实际 FastAPI app。
"""
import os, sys, json, uuid, sqlite3, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 1. 复制库到 tmp
import tempfile
tmp_dir = Path(tempfile.mkdtemp(prefix="qa_draft_"))
src_db = ROOT / "app" / "data" / "course_agent.db"
shutil.copy(src_db, tmp_dir / "course_agent.db")
tmp_db = tmp_dir / "course_agent.db"
os.environ["DATABASE_URL"] = f"sqlite:///{tmp_db}"

# 2. 取一个教师 + 一门课程
conn = sqlite3.connect(str(tmp_db))
cur = conn.cursor()
cur.execute("SELECT user_id FROM users WHERE role='teacher' LIMIT 1")
teacher = cur.fetchone()[0]
cur.execute("SELECT course_id FROM user_courses WHERE user_id=? LIMIT 1", (teacher,))
row = cur.fetchone()
if not row:
    cur.execute("SELECT course_id FROM courses LIMIT 1")
    row = cur.fetchone()
course = row[0]
print(f"[seed] teacher={teacher} course={course}")
conn.close()

# 3. 启动 app
os.environ.setdefault("DEMO_SEED", "0")
from app.database import SessionLocal, engine
from app.models.user import User
from app.models.graph import GraphNode

# 找一个真实 KP / chapter
db = SessionLocal()
chapter = db.query(GraphNode).filter(GraphNode.course_id == course, GraphNode.graph_type == "chapter").first()
kp = db.query(GraphNode).filter(GraphNode.course_id == course, GraphNode.graph_type == "knowledge").first()
db.close()
print(f"[seed] chapter={chapter.id if chapter else None} kp={kp.id if kp else None}")
if not (chapter and kp):
    print("SKIP: no chapter/kp in this course")
    sys.exit(0)

# 4. 模拟一次 /question/import 调用
from fastapi.testclient import TestClient
from app.main import app

# 用 JWT 认证（直接构造 token）
from app.middleware.auth import create_jwt
token = create_jwt(teacher, "teacher")

client = TestClient(app)
headers = {"Authorization": f"Bearer {token}", "X-Course-Id": course}

payload = {
    "questions": [{
        "type": "single",
        "difficulty": 3,
        "score": 5,
        "stem": "测试题：1+1=?",
        "options": [
            {"key": "A", "text": "1"},
            {"key": "B", "text": "2"},
            {"key": "C", "text": "3"},
            {"key": "D", "text": "4"},
        ],
        "answer": "B",
        "analysis": "1+1=2",
        "chapterId": chapter.id,
        "kp_id": kp.id,
        "kpIds": [kp.id],
    }]
}

r = client.post("/api/v1/question/import", json=payload, headers=headers)
print(f"\n[import] status={r.status_code} body={r.json()}")
assert r.status_code == 200, r.text
data = r.json()["data"]
assert data["success"] == 1, data
draft_id = data["draftIds"][0]
print(f"[import] draft_id={draft_id}")

# 5. 拉草稿箱列表
r = client.get("/api/v1/question/drafts?status=draft", headers=headers)
print(f"\n[list] status={r.status_code} total={r.json()['data']['total']}")
items = r.json()["data"]["list"]
print(f"[list] list={json.dumps([{'draftId': x['draftId'], 'status': x['status'], 'qId': x['qId'], 'stem': (x.get('payload', {}) or {}).get('question', '')[:30]} for x in items], ensure_ascii=False, indent=2)}")
assert any(x["draftId"] == draft_id for x in items), "刚刚导入的草稿不在列表中！"
print("[ok] 草稿在列表中")

# 6. 发布进题库
r = client.post(f"/api/v1/question/drafts/{draft_id}/publish", headers=headers)
print(f"\n[publish] status={r.status_code} body={r.json()}")
assert r.status_code == 200, r.text
qid = r.json()["data"]["qId"]
print(f"[publish] qId={qid}")

# 7. 题库列表
r = client.get("/api/v1/question/bank", headers=headers)
items = r.json()["data"]["list"]
print(f"\n[bank] total={r.json()['data']['total']} contains_published={any(x['qId'] == qid for x in items)}")
# 检查库里总条数
import sqlite3
conn = sqlite3.connect(str(tmp_db))
all_qids = [r[0] for r in conn.execute("SELECT q_id FROM questions ORDER BY q_id").fetchall()]
conn.close()
print(f"[bank] db has {len(all_qids)} questions; just-published '{qid}' in db: {qid in all_qids}")
assert qid in all_qids, "发布的题号不在数据库里！"
print("[ok] 题库中可看到发布后的题号")

print("\n=== 全部通过 ===")
