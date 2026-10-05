#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P41 / P43 / P44 / P47 / P48 深度验证（8010 独立实例 + 数据库副本，真实库只读）。

用法：
  BASE=http://127.0.0.1:8010 \\
  VERIFY_DB="C:\\Users\\CQYDDD\\AppData\\Local\\Temp\\_verify_v1b\\course_agent.db" \\
  python dev_tools/verify_p41_43_44_47_48.py

覆盖：
  P43  统计口径补 course_id —— 旧/新口径键集合对照；注入第二门课合法噪声后接口逐字不变
  P44  预警生命周期兜底 —— 证据彻底消失后旧预警被删除（并集遍历）
  P47  薄弱点清单预警优先占位 —— 构造性验证（插/删一条预警，观察清单进出）
  P48  纯标签点门槛提到 ≥3 —— hits=2 的纯标签点不再挂预警；主命中点对照仍正常
  P41  顺序练习文案 + 薄弱点强化卡片题量按真实薄弱点题池
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('BASE', 'http://127.0.0.1:8010')
DB = os.environ.get('VERIFY_DB', '')
CID = os.environ.get('COURSE_ID', 'CCHYJTKE')
PWD = os.environ.get('PASSWORD', '123456')
BACKEND = os.environ.get('BACKEND', r'C:\Users\CQYDDD\Desktop\course-agent-v1\backend')
NEW_COURSE = 'CVERIFY2'

if not DB:
    print('必须用 VERIFY_DB 指定数据库副本路径（本脚本会写入噪声数据）')
    sys.exit(2)

os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
sys.path.insert(0, BACKEND)

from sqlalchemy import func                                   # noqa: E402
from app.database import SessionLocal                         # noqa: E402
from app.models.alert import Alert                            # noqa: E402
from app.models.graph import GraphNode, LearningPath          # noqa: E402
from app.models.practice import AnswerRecord                  # noqa: E402
from app.models.question import Question                      # noqa: E402
from app.models.user import User                              # noqa: E402
from app.services.alert_detector import (                     # noqa: E402
    ENGAGE_MIN, YELLOW_BELOW, detect_alerts,
)
from app.services.kp_stats import mastery_by_kp               # noqa: E402
from app.services.scoring import quiz_accuracy_by_kp, weak_kp_ids   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s%s' % ('PASS' if cond else 'FAIL', name,
                           ('  -> %s' % extra) if extra != '' else ''))


def section(t):
    print('\n' + '=' * 78)
    print(t)
    print('=' * 78)


# ----------------------------------------------------------------- HTTP
def api(method, path, token=None, body=None, course=CID):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    if course:
        r.add_header('X-Course-Id', course)
    if data:
        r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            raw = x.read().decode()
            try:
                return x.status, json.loads(raw)
            except ValueError:
                return x.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def login(username):
    _s, d = api('POST', '/api/v1/auth/login',
                body={'username': username, 'password': PWD}, course=None)
    return ((d or {}).get('data') or {}).get('token')


# ----------------------------------------------------------------- DB
def con():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def _lit(v):
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def clone_rows(c, table, where, repl, params=()):
    """把 table 中 where 命中的行复制一份，repl 里的列替换成给定字面量。"""
    cols = [r[1] for r in c.execute('pragma table_info(%s)' % table)]
    sel = ', '.join(_lit(repl[col]) if col in repl else '"%s"' % col for col in cols)
    c.execute('insert into "%s" (%s) select %s from "%s" where %s'
              % (table, ', '.join('"%s"' % col for col in cols), sel, table, where),
              params)


def purge_noise(c):
    for t in ('answer_records', 'questions', 'graph_nodes', 'practice_sessions',
              'alerts', 'learning_paths', 'resource_progress'):
        try:
            c.execute('delete from %s where course_id = ?' % t, (NEW_COURSE,))
        except sqlite3.OperationalError:
            pass
    c.execute('delete from courses where course_id = ?', (NEW_COURSE,))
    c.commit()


# ----------------------------------------------------------------- 主体
def main():
    section('[0] 前置自检 & 幂等清理')
    c = con()
    purge_noise(c)
    courses = [r[0] for r in c.execute('select course_id from courses')]
    check('副本课程表干净（仅本课程）', courses == [CID], courses)
    students = [(r['user_id'], r['username'], r['name']) for r in c.execute(
        "select user_id, username, name from users where role='student' order by user_id")]
    check('学生账号齐备', len(students) == 10, len(students))
    c.close()

    section('[1] 登录并采集 baseline 接口快照')
    tokens = {}
    for _uid, uname, _name in students:
        tokens[uname] = login(uname)
    tokens['wangjg'] = login('wangjg')
    missing = [u for u, t in tokens.items() if not t]
    check('全部账号登录成功', not missing, missing)
    if missing:
        return

    STU_PATHS = ['/api/v1/student/dashboard',
                 '/api/v1/student/alerts',
                 '/api/v1/student/mastery/matrix']
    TEA_PATHS = ['/api/v1/teacher/classes',
                 '/api/v1/teacher/students',
                 '/api/v1/question/bank',
                 '/api/v1/report/list',
                 '/api/v1/intervention/list',
                 '/api/v1/analysis/errors']

    def _norm(status, body):
        """归一化：只比对信封的 code + data —— traceId 每次请求都不同，不参与比对。"""
        if isinstance(body, dict):
            return '%s|%s|%s' % (status, body.get('code'),
                                 json.dumps(body.get('data'), ensure_ascii=False, sort_keys=True))
        return '%s|%s' % (status, body)

    def snapshot():
        snap = {}
        for _uid, uname, _name in students:
            for p in STU_PATHS:
                s, d = api('GET', p, tokens[uname])
                snap['%s %s' % (uname, p)] = _norm(s, d)
        for p in TEA_PATHS:
            s, d = api('GET', p, tokens['wangjg'])
            snap['teacher %s' % p] = _norm(s, d)
        return snap

    snapshot()                       # 第一次：触发并稳定 detect_alerts 副作用
    baseline = snapshot()            # 第二次：作为对照基线
    check('快照幂等（两次一致）', snapshot() == baseline, len(baseline))

    section('[2] 注入 L1 合法噪声：第二门课 CVERIFY2 自己的完整数据')
    c = con()
    clone_rows(c, 'courses', 'course_id = ?',
               {'course_id': NEW_COURSE, 'name': '验证用第二门课', 'code': 'VERIFY2'}, (CID,))
    src_kps = [r[0] for r in c.execute(
        "select id from graph_nodes where course_id = ? and graph_type = 'knowledge' limit 3", (CID,))]
    kps = []
    for i, src in enumerate(src_kps, 1):
        kp = 'VFY2KP%02d' % i
        clone_rows(c, 'graph_nodes', 'id = ? and graph_type = ?',
                   {'id': kp, 'course_id': NEW_COURSE, 'name': '验证知识点%d' % i},
                   (src, 'knowledge'))
        kps.append(kp)
    src_qs = [r[0] for r in c.execute(
        "select q_id from questions where course_id = ? and status = 'published' limit 3", (CID,))]
    qids = []
    for i, sq in enumerate(src_qs):
        qid = 'QVFY2%02d' % i
        clone_rows(c, 'questions', 'q_id = ?',
                   {'q_id': qid, 'course_id': NEW_COURSE, 'kp_id': kps[i % len(kps)],
                    'kp_ids': json.dumps([kps[i % len(kps)]])}, (sq,))
        qids.append(qid)
    base_ar = c.execute('select max(id) from answer_records').fetchone()[0]
    for _uid, uname, _name in students:
        for i, qid in enumerate(qids):
            clone_rows(c, 'answer_records', 'id = ?',
                       {'id': None, 'user_id': _uid, 'course_id': NEW_COURSE, 'q_id': qid,
                        'kp_id': kps[i % len(kps)], 'is_correct': 0 if i == 0 else 1,
                        'created_at': '2026-09-30 09:00:00'}, (base_ar,))
    c.commit()
    n_new = c.execute('select count(*) from answer_records where course_id = ?', (NEW_COURSE,)).fetchone()[0]
    check('噪声已注入（第二门课 %d 知识点 / %d 题 / %d 条答题记录）' % (len(kps), len(qids), n_new),
          n_new == len(students) * len(qids))
    c.close()

    db = SessionLocal()

    section('[3] P43 口径对照：新口径把别课数据挡在外面')
    probe_uids = [u for u, _n, _x in students]
    u0 = probe_uids[0]
    acc_old = quiz_accuracy_by_kp(db, u0)
    acc_new = quiz_accuracy_by_kp(db, u0, course_id=CID)
    extra = set(kps) & set(acc_old)
    check('P43 旧口径（无 course_id）混入了别课知识点', len(extra) == 3, sorted(extra))
    check('P43 新口径（course_id=%s）不含别课知识点' % CID, not (set(kps) & set(acc_new)))
    check('P43 新口径键集合 ⊂ 旧口径键集合', set(acc_new) <= set(acc_old),
          'new=%d old=%d' % (len(acc_new), len(acc_old)))
    diff_keys = set(acc_old) - set(acc_new)
    check('P43 旧口径多出来的键恰好是别课知识点', diff_keys == set(kps), sorted(diff_keys))

    m_old = mastery_by_kp(db, u0)
    m_new = mastery_by_kp(db, u0, CID)
    check('P43 mastery_by_kp 同样隔离（旧含别课、新不含）',
          bool(set(kps) & set(m_old)) and not (set(kps) & set(m_new)))

    section('[4] P43/P39 接口层：注入合法噪声后响应逐字不变')
    after = snapshot()
    diff = sorted(k for k in baseline if baseline[k] != after.get(k))
    check('全部 %d 个接口响应逐字不变' % len(baseline), not diff, diff[:6])

    section('[5] 触发全量预警检测（P44 并集遍历 + P48 新门槛）')
    res = detect_alerts(db)
    print('  detect_alerts ->', res)

    section('[6] P48 纯标签点门槛 ≥3')
    all_kps = [k for (k,) in db.query(GraphNode.id).filter(
        GraphNode.graph_type == 'knowledge', GraphNode.course_id == CID).all()]
    pq = {kp: n for kp, n in db.query(Question.kp_id, func.count(Question.q_id)).filter(
        Question.course_id == CID, Question.kp_id.isnot(None)).group_by(Question.kp_id).all()}
    pure = [k for k in all_kps if pq.get(k, 0) == 0]
    check('课程内存在「全课无主 KP 题」的纯标签点', len(pure) > 0, pure)

    def alerts_of(uid):
        return {a.kp_id for a in db.query(Alert.kp_id).filter(
            Alert.user_id == uid, Alert.course_id == CID, Alert.type == 'mastery_low').all()}

    bad, would_old, ctrl_bad = [], [], []
    for uid, _n, _x in students:
        acc = quiz_accuracy_by_kp(db, uid, course_id=CID)
        ak = alerts_of(uid)
        for kp, (rate, hits) in acc.items():
            if rate >= YELLOW_BELOW:
                continue
            if kp in pure and hits == ENGAGE_MIN:
                would_old.append('%s/%s' % (uid, kp))
                if kp in ak:
                    bad.append('%s/%s' % (uid, kp))
            if pq.get(kp, 0) > 0 and hits == ENGAGE_MIN and kp not in ak:
                ctrl_bad.append('%s/%s' % (uid, kp))
    check('P48 纯标签点 hits=2 不再生成预警', not bad, bad[:6])
    check('P48 反证：这些点在旧门槛(≥2)下本来会被建预警', len(would_old) > 0, would_old[:8])
    check('P48 对照：主命中点 hits=2 仍正常挂预警', not ctrl_bad, ctrl_bad[:6])

    section('[7] P44 预警生命周期兜底（证据彻底消失 → 旧预警被删除）')
    row = db.query(Alert).filter(
        Alert.course_id == CID, Alert.type == 'mastery_low',
        Alert.status == 'open', Alert.level.in_(('red', 'yellow')),
    ).first()
    check('找到可用于验证的 open 预警', row is not None,
          '%s/%s/%s' % (row.user_id, row.kp_id, row.level) if row else '')
    if row:
        uid, kp = row.user_id, row.kp_id
        # 该生在该知识点上的全部证据（主命中 ∪ 标签命中）
        rel = []
        for qid, pk, tgs in db.query(Question.q_id, Question.kp_id, Question.kp_ids).filter(
                Question.course_id == CID).all():
            if pk == kp:
                rel.append(qid)
                continue
            try:
                if kp in json.loads(tgs or '[]'):
                    rel.append(qid)
            except (TypeError, ValueError):
                pass
        n_del = db.query(AnswerRecord).filter(
            AnswerRecord.user_id == uid, AnswerRecord.course_id == CID,
            AnswerRecord.q_id.in_(rel)).delete(synchronize_session=False) if rel else 0
        db.commit()
        print('  已清除 %s 在 %s 上的答题记录 %d 条（相关题目 %d 道）' % (uid, kp, n_del, len(rel)))
        after_acc = quiz_accuracy_by_kp(db, uid, course_id=CID)
        check('P44 反证：该点已离开证据表（旧逻辑的循环根本不会到达它）',
              kp not in after_acc, after_acc.get(kp))
        res2 = detect_alerts(db)
        left = db.query(Alert).filter(
            Alert.user_id == uid, Alert.course_id == CID,
            Alert.kp_id == kp, Alert.type == 'mastery_low').count()
        check('P44 失去依据的预警已被删除', left == 0,
              'deleted=%s remaining=%d' % (res2.get('deleted'), left))

    section('[8] P47 薄弱点清单让有预警的知识点优先占位')
    target = None
    for uid, _n, _x in students:
        acc = quiz_accuracy_by_kp(db, uid, course_id=CID)
        lp = [k for (k,) in db.query(LearningPath.kp_id).filter(
            LearningPath.user_id == uid, LearningPath.course_id == CID).all()]
        top5 = weak_kp_ids(db, uid, CID, lp, limit=5)
        ak = alerts_of(uid)
        for kp in lp:
            v = acc.get(kp)
            if v and v[1] >= ENGAGE_MIN and v[0] < YELLOW_BELOW and kp not in ak and kp not in top5:
                target = (uid, kp, lp, top5)
                break
        if target:
            break
    check('找到「是薄弱点、但排不进前 5 且无预警」的对象', target is not None,
          '%s/%s' % (target[0], target[1]) if target else '')
    if target:
        uid, kp, lp, before = target
        aid = 'ALVFY' + os.urandom(3).hex()
        db.add(Alert(alert_id=aid, course_id=CID, user_id=uid, level='yellow',
                     type='mastery_low', kp_id=kp, kp_name=kp, title='验证用预警',
                     desc='', trigger='', detail_json='{}', suggestions_json='[]',
                     status='open'))
        db.commit()
        mid = weak_kp_ids(db, uid, CID, lp, limit=5)
        check('P47 插入预警后该知识点优先挤进前 5', kp in mid and kp not in before,
              'before=%s -> after=%s' % (before, mid))
        db.query(Alert).filter(Alert.alert_id == aid).delete()
        db.commit()
        back = weak_kp_ids(db, uid, CID, lp, limit=5)
        check('P47 移除预警后恢复原排序（变化确实由预警驱动）', back == before,
              'back=%s' % back)

    section('[9] P41 练习模式文案与题量')
    probe = None
    for uid, uname, _n in students:
        lp = [k for (k,) in db.query(LearningPath.kp_id).filter(
            LearningPath.user_id == uid, LearningPath.course_id == CID).all()]
        if weak_kp_ids(db, uid, CID, lp, limit=5):
            probe = (uid, uname, lp)
            break
    check('找到有薄弱点的学生用于验证题量', probe is not None)
    if probe:
        uid, uname, lp = probe
        _s, d = api('GET', '/api/v1/practice/modes', tokens[uname])
        modes = (d or {}).get('data') or []
        by = {m['key']: m for m in modes}
        odesc = (by.get('order') or {}).get('desc') or ''
        check('P41 顺序练习文案不再承诺「前后置顺序」', '前后置' not in odesc, odesc)
        weak = weak_kp_ids(db, uid, CID, lp, limit=5)
        pool = db.query(func.count(Question.q_id)).filter(
            Question.course_id == CID, Question.status == 'published',
            Question.kp_id.in_(weak)).scalar() if weak else 0
        total_qs = db.query(func.count(Question.q_id)).filter(
            Question.course_id == CID, Question.status == 'published').scalar()
        expect = min(10, pool)
        got = (by.get('weak') or {}).get('count')
        check('P41 薄弱点强化卡片题量按真实薄弱点题池计算', got == expect,
              'count=%s expect=%s pool=%s total=%s' % (got, expect, pool, total_qs))
        check('P41 该题池确实小于全课题数（证明不再用全课口径）', pool < total_qs,
              'pool=%s total=%s' % (pool, total_qs))

    db.close()
    c = con()
    purge_noise(c)
    c.close()

    print()
    print('=' * 78)
    if FAIL:
        print('FAILED  passed=%d failed=%d' % (len(PASS), len(FAIL)))
        for f in FAIL:
            print('  FAIL:', f)
    else:
        print('ALL PASS  passed=%d failed=%d' % (len(PASS), len(FAIL)))
    print('=' * 78)


if __name__ == '__main__':
    main()
