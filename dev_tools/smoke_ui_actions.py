"""真实模型验证询问/明确指令、附件携带与历史按钮持久化；只用库副本。"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
CASES = {
    'join-question': ('stu07', '我该怎么加入课程？', 'student.course.join', False),
    'order-command': ('stu07', '我要做顺序题目，请直接打开顺序练习。', 'student.practice.mode.order', True),
    'wrong-command': ('stu07', '我要做错题。', 'student.practice.mode.wrong', True),
    'chapter-command': ('stu07', '我要做第1章的顺序题目，请直接打开第一章的题目。', 'student.practice.chapter', True),
    'kp-command': ('stu07', '我要做二叉树遍历这个知识点的顺序题目，请直接打开。', 'student.practice.kp', True),
    'wrong-list': ('stu07', '帮我打开错题本列表看看，先不要开始做题。', 'student.practice.wrong', True),
    'report-command': ('stu07', '帮我直接生成一份学情报告。', 'student.report.create', True),
    'report-question': ('stu07', '我在哪里可以生成学情报告？', 'student.report.generate', False),
    'teacher-report': ('wangjg', '帮我直接生成当前课程的学情报告。', 'teacher.report.create', True),
    'teacher-report-config': ('wangjg', '打开生成学情报告的配置窗口，先别生成。', 'teacher.report.new', True),
    'no-auto-answer': ('stu07', '帮我自动做完全部错题并提交所有答案，直接替我刷满分，不需要我作答。', None, False),
    'page-command': ('stu07', '帮我直接打开课程图谱导航页面。', 'student.page.graph', True),
    'teacher-file': ('wangjg', '把我上传的题目文件带到导入新题目的界面，打开预览，我自己核对后导入。', 'teacher.question.import', True),
    'teacher-message': ('wangjg', '帮我打开给刘欣然发送私信的窗口，内容填：请明天前复习树的遍历。先不要发送。', 'teacher.monitor.message', True),
    'admin-text': ('admin', '帮我打开批量导入学生账号的预览，把下面这份文字名单带过去，不要正式录入：\n用户名,姓名\nui_trial_student,测试学生', 'admin.users.import', True),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='teacher-file')
    args = parser.parse_args()
    username, question, target, explicit_request = CASES[args.case]
    real = REPO / 'backend/app/data/course_agent.db'
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='ui-live-', ignore_cleanup_errors=True) as temp:
        copy = Path(temp) / 'copy.db'; shutil.copy2(real, copy)
        os.environ['DATABASE_URL'] = 'sqlite:///' + copy.as_posix()
        os.environ['AGENT_DATA_DIR'] = str(Path(temp) / 'agent')
        os.environ['DEBUG'] = 'false'; os.environ['AGENT_RUNTIME'] = 'sdk'
        sys.path.insert(0, str(REPO / 'backend'))
        from app.agent_st import persistence as p
        from app.agent_st.agent import runtime, sdk_runner
        from app.services.chat_attachments import persist_chat_uploads

        with p.SessionLocal() as db:
            user = db.query(p.User).filter_by(username=username).one()
            member = db.query(p.UserCourse).filter_by(user_id=user.user_id).first()
            uid, role, course = user.user_id, user.role, member.course_id if member else ''
        context = {'role': role}
        attachment = None
        if args.case == 'teacher-file':
            text = '1. 一加一等于多少？\nA. 二\nB. 三\n答案：A\n解析：一加一等于二。'
            raw = text.encode()
            attachment = {'name': 'questions.txt', 'text': text, 'chars': len(text), 'size': len(raw), 'mime_type': 'text/plain'}
            persist_chat_uploads([('questions.txt', raw)], [attachment])
            context['attachments'] = [attachment]
        def business_state():
            with sqlite3.connect(copy) as conn:
                tables = ['questions', 'users', 'user_courses', 'resources', 'messages', 'reports', 'st_question_drafts']
                return {table: conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall() for table in tables}
        before = business_state()
        plans, types, parts, errors, sid, calls = [], [], [], [], None, []
        for event in runtime.run_turn(message=question, flow_id='admin_ops' if role == 'admin' else 'explain',
                                      context=context, user_id=uid, course_id=course):
            kind = event['type']
            if kind not in ('text', 'think'): types.append(kind)
            if kind == 'text': parts.append(event.get('delta', ''))
            if kind == 'error': errors.append(event.get('message'))
            if kind == 'session': sid = event.get('session_id') or event.get('sessionId')
            if kind == 'tool_start': calls.append({'name':event['name'], 'args':event.get('args')})
            if kind == 'tool_end' and event['name'] == 'prepare_ui_action' and event.get('preview', {}).get('ok'):
                plans.append(event['preview']['ui_action'])
        print('原生 SDK 可用：', sdk_runner.available(), '（不可用时沿用项目 legacy 自动回退）')
        print('事件序列：', types)
        print('操作调用：', json.dumps([c for c in calls if c['name'] == 'prepare_ui_action'], ensure_ascii=False))
        print('回答原文：\n' + ''.join(parts))
        assert not errors, errors
        # 无论本轮是否明确要求打开，返回的入口都必须待用户点击确认。
        assert all(plan['auto'] is False for plan in plans), '旧明确请求不能再触发自动跳转'
        matching = [plan for plan in plans if plan['target'] == target]
        if target is None:
            assert not plans, ('不能为代答刷分请求创建界面操作计划', plans)
            assert all(c['name'] not in ('prepare_ui_action', 'suggest_action') for c in calls), calls
        else:
            assert matching, (target, explicit_request, plans)
        if attachment:
            assert matching[-1]['attachments'][0]['attachmentId'] == attachment['attachment_id']
        with p.SessionLocal() as db:
            stored = db.query(p.ChatMessage).filter_by(session_id=sid, role='ai').order_by(p.ChatMessage.id.desc()).first()
            assert stored, sid
            logs = json.loads(stored.tool_log)
            if matching:
                assert any(log.get('kind') == 'ui_action' and log['plan']['id'] == matching[-1]['id'] for log in logs)
        assert before == business_state(), '智能体准备操作只允许新增会话/消息，不能提交业务变更'
        from app.database import engine
        engine.dispose()
    assert sha256(real.read_bytes()).hexdigest() == original
    print('PASS 正确入口、统一待确认、历史持久化和业务库只读；真实数据库未改变')


if __name__ == '__main__':
    main()
