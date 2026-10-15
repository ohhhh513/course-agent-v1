"""验证界面使用的现有报告/错题接口，所有写入仅在临时数据库副本。"""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    real = ROOT / 'backend/app/data/course_agent.db'
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='ui-report-api-', ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / 'copy.db'
        shutil.copy2(real, copy)
        os.environ.update(DATABASE_URL='sqlite:///' + copy.as_posix(), AGENT_DATA_DIR=str(Path(tmp) / 'agent'), DEBUG='false')
        sys.path.insert(0, str(ROOT / 'backend'))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import engine

        def state():
            with sqlite3.connect(copy) as db:
                schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                reports = db.execute('SELECT report_id,detail_json FROM reports ORDER BY report_id').fetchall()
                answers = db.execute('SELECT * FROM answer_records ORDER BY rowid').fetchall()
            return schema, reports, answers

        client = TestClient(app)
        try:
            headers = {}
            for username in ('stu07', 'stu08', 'wangjg'):
                login = client.post('/api/v1/auth/login', json={'username': username, 'password': '123456'}).json()['data']
                with sqlite3.connect(copy) as db:
                    uid = db.execute('SELECT user_id FROM users WHERE username=?', (username,)).fetchone()[0]
                    course = db.execute('SELECT course_id FROM user_courses WHERE user_id=? LIMIT 1', (uid,)).fetchone()[0]
                headers[username] = {'Authorization': 'Bearer ' + login['token'], 'X-Course-Id': course}
            schema, rows, answers = state()
            result = client.post('/api/v1/student/reports/generate', json={}, headers=headers['stu07'])
            assert result.status_code == 200, result.text
            student_id = result.json()['data']['reportId']
            after = state()
            assert len(after[1]) == len(rows) + 1 and after[0] == schema and after[2] == answers
            detail = client.get('/api/v1/student/reports/' + student_id, headers=headers['stu07'])
            assert detail.status_code == 200 and detail.json()['data']['detail']['meta']['scope'] == 'self'
            assert client.get('/api/v1/student/reports/' + student_id, headers=headers['stu08']).status_code == 403
            archive = client.get('/api/v1/student/reports/list', headers=headers['stu07']).json()['data']['list']
            assert any(r['reportId'] == student_id for r in archive)
            print('PASS 学生生成 +1 份报告、详情/归档可读、他人403；没有改表或答题记录')
            before = state()
            result = client.post('/api/v1/report/generate', json={}, headers=headers['wangjg'])
            assert result.status_code == 200 and result.json()['data'].get('reportId'), result.text
            teacher_id = result.json()['data']['reportId']
            after = state()
            assert len(after[1]) == len(before[1]) + 1 and after[0] == schema and after[2] == answers
            assert client.get('/api/v1/report/' + teacher_id, headers=headers['wangjg']).status_code == 200
            archive = client.get('/api/v1/report/list', headers=headers['wangjg']).json()['data']['list']
            assert any(r['reportId'] == teacher_id for r in archive) and all(r['reportId'] != student_id for r in archive)
            assert client.post('/api/v1/report/generate', json={}, headers=headers['stu07']).status_code == 403
            assert client.get('/api/v1/report/' + student_id, headers=headers['wangjg']).status_code == 403
            other_course = None
            with sqlite3.connect(copy) as db:
                uid = db.execute("SELECT user_id FROM users WHERE username='wangjg'").fetchone()[0]
                courses = [row[0] for row in db.execute(
                    'SELECT course_id FROM user_courses WHERE user_id=? AND role_in_course=?',
                    (uid, 'teacher'))]
            current = headers['wangjg']['X-Course-Id']
            other_course = next((c for c in courses if c != current), None)
            if other_course:
                wrong = dict(headers['wangjg'])
                wrong['X-Course-Id'] = other_course
                assert client.get('/api/v1/report/' + teacher_id, headers=wrong).status_code == 403
                mismatched = client.post('/api/v1/report/generate', json={'courseId': current}, headers=wrong)
                assert mismatched.status_code == 200 and mismatched.json().get('code') == 400
            named = client.post('/api/v1/report/generate', json={'title': '自定义学情报告标题'}, headers=headers['wangjg'])
            assert named.status_code == 200, named.text
            named_data = named.json()['data']
            named_id = named_data['reportId']
            assert named_data.get('detail', {}).get('title') == '自定义学情报告标题'
            named_detail = client.get('/api/v1/report/' + named_id, headers=headers['wangjg']).json()['data']
            assert named_detail.get('title') == '自定义学情报告标题'
            print('PASS 教师生成 +1 份当前课程报告；自定义标题写入 reports.title；教师归档排除学生个人报告、跨课程详情 403、学生教师接口403')
            before = state()
            current = client.get('/api/v1/practice/sessions/current', params={'mode': 'wrong'}, headers=headers['stu07'])
            assert current.status_code == 200, current.text
            result = client.post('/api/v1/practice/sessions', json={'mode': 'wrong', 'count': 12}, headers=headers['stu07'])
            assert result.status_code == 200, result.text
            payload = result.json()['data']
            assert 'questions' in payload
            assert state()[0] == schema and state()[2] == answers
            print('PASS 错题存档查询/组卷接口正常，题目数量:', len(payload['questions']), '；答题记录未新增')
        finally:
            client.close()
            engine.dispose()
    assert sha256(real.read_bytes()).hexdigest() == original
    print('PASS 真实数据库 SHA256 不变；报告写入与练习组卷只在临时副本')


if __name__ == '__main__':
    main()
