"""连续对话的真实模型验收；历史、问答和所有读写仅在数据库副本。"""
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

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'screenshot': ('stu07', '我想学习哈希表', '哈希表也叫散列表，使用散列函数定位元素，冲突可用开放定址法处理。', '那他的资源在哪里', 'resource', False),
    'resource-colloquial': ('stu07', '我想学习哈希表', '本课程有哈希表这个知识点。', '这个有没有课件可以看啊', 'resource', False),
    'resource-open': ('stu07', '我想学习哈希表', '本课程有哈希表这个知识点。', '带我去看它的资料', 'resource', True),
    'teacher-followup': ('wangjg', '我要修改第1章 绪论的章节名称', '可以在课程目录与资源中修改第1章 绪论。', '那在哪改啊', 'teacher.structure.chapter.edit', False),
    'admin-followup': ('admin', '我想修改教师 wangjg 的账号信息', 'wangjg 是教师王建国的账号，可以编辑其账号资料。', '他密码在哪改', 'admin.users.edit', False),
    'knowledge-only': ('stu07', '我想学习哈希表', '哈希表使用散列函数定位元素。', '它的查找效率为什么高', None, False),
    'ambiguous': ('stu07', '哈希表和二叉树遍历这两个我都想学', '你提到了哈希表和二叉树遍历两个知识点。', '打开它的资源', 'ambiguous', False),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='screenshot')
    parser.add_argument('--observe', action='store_true', help='只记录现状，不断言入口意图')
    parser.add_argument('--actual-history', action='store_true', help='前一轮也真实调用模型，而不是写入固定历史夹具')
    args = parser.parse_args()
    username, previous, reply, question, expected, auto = CASES[args.case]
    real = ROOT / 'backend/app/data/course_agent.db'
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='ui-followup-', ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / 'copy.db'
        shutil.copy2(real, copy)
        os.environ.update(DATABASE_URL='sqlite:///' + copy.as_posix(), AGENT_DATA_DIR=str(Path(tmp) / 'agent'), DEBUG='false', AGENT_RUNTIME='sdk')
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.agent_st import persistence as p
        from app.agent_st.agent import runtime, sdk_runner
        from app.agent_st.agent.store import AgentStore
        from app.database import engine
        with p.SessionLocal() as db:
            user = db.query(p.User).filter_by(username=username).one()
            membership = db.query(p.UserCourse).filter_by(user_id=user.user_id).first()
            uid, role, course = user.user_id, user.role, membership.course_id if membership else ''
        store = AgentStore(user_id=uid, course_id=course)
        flow = 'admin_ops' if role == 'admin' else 'explain'
        sid = store.ensure_session(None, flow)

        def business():
            with sqlite3.connect(copy) as db:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if row[0] not in ('chat_sessions', 'chat_messages')]
                return {table: db.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall() for table in tables}
        before = business()
        if args.actual_history:
            initial_parts, initial_plans, initial_errors = [], [], []
            for event in runtime.run_turn(message=previous, flow_id=flow, session_id=sid, context={'role': role}, user_id=uid, course_id=course):
                if event['type'] == 'text': initial_parts.append(event.get('delta', ''))
                if event['type'] == 'error': initial_errors.append(event.get('message'))
                if event['type'] == 'tool_end' and event['name'] == 'prepare_ui_action' and event.get('preview', {}).get('ok'):
                    initial_plans.append(event['preview']['ui_action'])
            assert not initial_errors, initial_errors
            if role == 'student':
                assert not any(plan['auto'] for plan in initial_plans), '只表达学习兴趣不自动离开对话页'
            print('前一轮真实回答：\n' + ''.join(initial_parts))
        else:
            store.add_message(sid, 'user', previous)
            store.add_message(sid, 'assistant', reply)

        plans, calls, parts, events, errors = [], [], [], [], []
        for event in runtime.run_turn(message=question, flow_id=flow, session_id=sid, context={'role': role}, user_id=uid, course_id=course):
            kind = event['type']
            if kind not in ('text', 'think'): events.append(kind)
            if kind == 'text': parts.append(event.get('delta', ''))
            if kind == 'error': errors.append(event.get('message'))
            if kind == 'tool_start': calls.append({'name': event['name'], 'args': event.get('args')})
            if kind == 'tool_end' and event['name'] == 'prepare_ui_action' and event.get('preview', {}).get('ok'):
                plans.append(event['preview']['ui_action'])
        print('历史问题：', previous)
        print('本轮追问：', question)
        print('原生 SDK 可用：', sdk_runner.available(), '（不可用时沿用 legacy 真实模型）')
        print('事件序列：', events)
        print('工具调用：', json.dumps(calls, ensure_ascii=False))
        print('回答原文：\n' + ''.join(parts))
        assert not errors, errors
        if not args.observe:
            if expected == 'resource':
                allowed = {'student.graph.resources', 'student.resource.search'}
                matching = [plan for plan in plans if plan['target'] in allowed and plan['auto'] == auto]
                assert matching, ('必须生成精确资源入口', plans)
                assert any('哈希' in str(plan['values']) or '哈希' in str(plan.get('object')) for plan in matching), matching
            elif expected == 'ambiguous':
                assert not any(plan['auto'] for plan in plans), '有多个指代时不能擅自跳转'
                assert '哈希' in ''.join(parts) and '二叉树' in ''.join(parts), '需要请用户明确指代对象'
                matching = []
            elif expected is None:
                assert not plans, '纯知识讲解不需要强制提供界面入口'
                matching = []
            else:
                matching = [plan for plan in plans if plan['target'] == expected and plan['auto'] == auto]
                assert matching, (expected, plans)
            with p.SessionLocal() as db:
                message = db.query(p.ChatMessage).filter_by(session_id=sid, role='ai').order_by(p.ChatMessage.id.desc()).first()
                logs = json.loads(message.tool_log)
                for plan in matching:
                    assert any(entry.get('kind') == 'ui_action' and entry['plan']['id'] == plan['id'] for entry in logs)
        assert business() == before, '导航准备不能写业务数据'
        engine.dispose()
    assert sha256(real.read_bytes()).hexdigest() == original
    print('PASS 连续对话、入口意图与持久化；业务数据和真实数据库不变' if not args.observe else 'OBSERVE 当前行为记录完毕；真实数据库不变')


if __name__ == '__main__':
    main()
