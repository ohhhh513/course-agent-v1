"""追问操作的规则、工具结果与真实入口自检；业务库只使用副本。"""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import patch
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]


def main():
    real = ROOT / 'backend/app/data/course_agent.db'
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='followup-check-', ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / 'copy.db'
        shutil.copy2(real, copy)
        os.environ.update(DATABASE_URL='sqlite:///' + copy.as_posix(), AGENT_DATA_DIR=str(Path(tmp) / 'agent'), DEBUG='false')
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.agent_st import persistence as p
        from app.agent_st.agent.context import ToolContext
        from app.agent_st.agent.loader import build_system_prompt, load_flow, load_persona
        from app.agent_st.agent.registry import TOOLS, execute
        from app.agent_st.agent.runtime import _run_tool
        from app.agent_st.agent.system_guide import lookup_guide
        from app.agent_st.agent.tools import analytics, ui_actions  # noqa: F401
        from app.database import engine

        def state():
            with sqlite3.connect(copy) as db:
                return list(db.iterdump())
        before = state()
        for mode in ('code', 'manual'):
            with patch.dict(os.environ, {'SYSTEM_GUIDE_MODE': mode}):
                result = lookup_guide('student', query='哈希表的关联资源在哪里', view='graph')
                assert result['found'] and 'prepare_ui_action' in result['note'] and 'auto=false' in result['note']
                assert 'suggest_action' not in result['note'], '不能继续用旧工具提示覆盖精确入口规则'
        with TestCase().assertLogs('app.agent_st.agent.system_guide', level='WARNING'), patch('app.agent_st.agent.system_code_index.get_code_index', side_effect=OSError('temporary unavailable')):
            result = lookup_guide('student', query='关联资源', view='graph')
            assert result['mode'] == 'manual_fallback' and 'prepare_ui_action' in result['note']
        print('PASS 源码/手册/故障回退的工具提示一致，查询不冒充生成按钮')

        contexts = {}
        with p.SessionLocal() as db:
            for role, username in [('student', 'stu07'), ('teacher', 'wangjg'), ('admin', 'admin')]:
                user = db.query(p.User).filter_by(username=username).one()
                member = db.query(p.UserCourse).filter_by(user_id=user.user_id).first()
                contexts[role] = ToolContext(None, 'admin_ops' if role == 'admin' else 'explain', user_id=user.user_id,
                    extra={'role': role, 'courseId': member.course_id if member else ''})
            course = contexts['student'].extra['courseId']
            kp = db.query(p.GraphNode).filter_by(course_id=course, graph_type='knowledge', name='哈希表').one()
            chapter = db.query(p.GraphNode).filter_by(course_id=course, graph_type='chapter').first()
            account = db.query(p.User).filter_by(username='wangjg').one()
            objects = {'student': ('student.graph.resources', kp.id), 'teacher': ('teacher.structure.chapter.edit', chapter.id), 'admin': ('admin.users.edit', account.user_id)}
        for role, ctx in contexts.items():
            flow = load_flow(ctx.flow_id)
            prompt = build_system_prompt(load_persona(flow['persona']), flow, {'role': role})
            assert '最近对话' in prompt and '必须' in prompt and 'prepare_ui_action' in prompt
            assert '没有成功生成入口' in prompt
            result = execute('get_system_guide', {'query': '关联资源' if role == 'student' else '编辑'}, ctx)
            assert result.get('found') and result.get('ui_actions')
            assert not any(row.get('kind') == 'ui_action' for row in ctx.tool_log), '查询本身不能冒充按钮计划'
            target, object_id = objects[role]
            events, plan = _run_tool('prepare_ui_action', {'target': target, 'object_id': object_id, 'auto': False}, ctx)
            assert plan.get('ok') and not plan['ui_action']['auto']
            assert plan['ui_action']['object']['id'] == object_id
            assert [e['type'] for e in events] == ['tool_start', 'tool_end']
            assert set(events[1]) == {'type', 'name', 'ok', 'preview'}
        assert '最近对话' in TOOLS['get_system_guide'].description and '必须调用' in TOOLS['prepare_ui_action'].description
        assert state() == before
        engine.dispose()
        print('PASS 三端追问提示、角色入口、对象定位和原 SSE 形状；准备过程不写数据库')
    assert sha256(real.read_bytes()).hexdigest() == original
    print('PASS 真实数据库 SHA256 不变')


if __name__ == '__main__':
    main()
