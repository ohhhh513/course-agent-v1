"""
测试「重新生成」回滚 save_question_draft 产生的草稿。

不依赖 dev_tools，使用 tmp 副本库 + FastAPI app。
"""
import os, sys, json, uuid, sqlite3, shutil, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 1. 复制库到 tmp
import tempfile
tmp_dir = Path(tempfile.mkdtemp(prefix="qa_regen_"))
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

# 3. 模拟"AI 出题后，save_question_draft 产生一个草稿"
# 直接用 SQL 写入以避开 fresh SQLAlchemy 上下文缺外键表的问题
fake_draft_id = "QD" + uuid.uuid4().hex[:10].upper()
now = "2026-10-15 18:00:00"
conn = sqlite3.connect(str(tmp_db))
conn.execute("""
INSERT INTO st_question_drafts(draft_id, user_id, course_id, batch_id, payload_json, status, errors_json, created_at)
VALUES (?, ?, ?, ?, ?, 'draft', '[]', ?)
""", (fake_draft_id, teacher, course, "TEST_REGEN",
      json.dumps({"source": "ai", "question": "AI 出的旧题",
                  "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                  "answer": "B", "analysis": "解析", "type": "single",
                  "difficulty": 3, "score": 5, "has_image": False}, ensure_ascii=False),
      now))
conn.commit()
cur = conn.execute("SELECT draft_id FROM st_question_drafts WHERE draft_id=?", (fake_draft_id,))
assert cur.fetchone(), "草稿未入库"
print(f"[seed] draft_id={fake_draft_id} 入库成功")
conn.close()

# 4. 启动 app + 模拟"重新生成"删草稿
from fastapi.testclient import TestClient
from app.main import app
from app.middleware.auth import create_jwt

token = create_jwt(teacher, "teacher")
client = TestClient(app)
headers = {"Authorization": f"Bearer {token}", "X-Course-Id": course}

r = client.delete(f"/api/v1/question/drafts/{fake_draft_id}", headers=headers)
print(f"\n[delete draft] status={r.status_code} body={r.json()}")
assert r.status_code == 200, r.text
assert r.json()["data"]["deleted"] is True

# 5. 验证真删了
conn = sqlite3.connect(str(tmp_db))
row = conn.execute("SELECT draft_id FROM st_question_drafts WHERE draft_id=?", (fake_draft_id,)).fetchone()
conn.close()
assert row is None, "草稿应被删除但还在"
print("[ok] 草稿已真删")

# 6. 测试：把 feedback 端点字段对齐后是否能解析
r = client.post("/api/v1/ai/feedback", json={"messageId": "test", "feedback": 1}, headers=headers)
print(f"\n[feedback] status={r.status_code} body={r.json()}")
assert r.status_code == 200, r.text
assert r.json()["data"]["accepted"] is True
print("[ok] /ai/feedback 字段对齐接受")

print("\n=== 全部通过 ===")
