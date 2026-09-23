'use strict';

  /* ================================================================
     视图 1 · 学习驾驶舱
     ================================================================ */
  /* 「今日累计学习时长」= 后端按本地日历日统计的「当天练习用时 + 当天视频观看秒数」，
     页面每 30 秒静默刷新一次（只读真实业务表，不做本地累加或估算）。 */
  let _todayDurationTimer = null;

  function _stopTodayDurationTimer() {
    if (_todayDurationTimer !== null) {
      clearInterval(_todayDurationTimer);
      _todayDurationTimer = null;
    }
  }

  /** 秒 → 「X 时 X 分」/「X 分」 */
  function _fmtStudyDuration(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h} 时 ${m} 分` : `${m} 分`;
  }

  /** 渲染「今日累计学习时长」徽标；extra 存在时把练习 / 视频明细写进 title */
  function _paintTodayDuration(seconds, extra) {
    const el = U.$('#todayStudyDuration');
    if (!el) return;
    el.textContent = `今日累计学习 ${_fmtStudyDuration(seconds)}`;
    if (extra) {
      el.title = `练习 ${_fmtStudyDuration(extra.practiceSeconds)} · 视频观看 ${_fmtStudyDuration(extra.resourceSeconds)}`;
    }
  }

  function _startTodayDurationTimer() {
    _stopTodayDurationTimer();
    _todayDurationTimer = setInterval(() => {
      if (!U.$('#todayStudyDuration')) { _stopTodayDurationTimer(); return; }
      API.student.studyDuration()
        .then(r => _paintTodayDuration(r.todaySeconds, r))
        .catch(() => {});
    }, 30000);
  }

  function renderDashboard() {
    _stopTodayDurationTimer();
    const el = U.$('#view-dashboard');
    if (!API.config.activeCourseId) {
      if (window.renderStudentNoCourse) window.renderStudentNoCourse(el);
      return;
    }
    el.innerHTML = U.skeleton(400);
    API.student.dashboard().then(d => {
      const o = d.overview, m = d.coreMetrics;
      const userName = d.userName || '同学';
      const currentNodeName = (o.currentNode && o.currentNode.name) ? o.currentNode.name : '未开始';
      const greeting = _greetingByTime();
      const lampText = {
        ok: '学习状态正常',
        warn: `有 ${o.needAttention} 项需要关注`,
        danger: '存在紧急预警',
      };
      const alertState = {
        ok: { label: '正常', dot: 'ok' },
        warn: { label: '需关注', dot: 'warn' },
        danger: { label: '预警', dot: 'danger' },
      }[o.status] || { label: '正常', dot: 'ok' };

      // 年份区间标签的兜底值（正常取后端给的学期标签，如 2026-2027）
      const _now = new Date();
      const _endY = _now.getFullYear();
      const _startY = new Date(_now.getFullYear(), _now.getMonth() - 11, 1).getFullYear();
      const _yrLabel = _startY === _endY ? `${_endY}` : `${_startY}-${_endY}`;
      // 打卡热力图：列 = 周，周数由后端按「学期第 1 周（8/31）起算」给出
      const _calWeeks = o.streakWeeks || Math.ceil(((o.streakHistory || []).length) / 7) || 52;

      el.innerHTML = `
      <!-- Hero -->
      <div class="hero" style="margin-bottom:16px">
        <div class="hero__main">
          <div class="row" style="margin-bottom:6px">
            ${R.lamp(o.status === 'danger' ? 'red' : o.status === 'warn' ? 'yellow' : 'ok', lampText[o.status])}
            <span class="badge badge--outline" id="todayStudyDuration"
              title="练习 ${_fmtStudyDuration(o.todayPracticeSeconds || 0)} · 视频观看 ${_fmtStudyDuration(o.todayResourceSeconds || 0)}">今日累计学习 ${_fmtStudyDuration(o.todayStudySeconds != null ? o.todayStudySeconds : (o.todayStudyMinutes || 0) * 60)}</span>
          </div>
          <h2>${greeting}，${U.esc(userName)} 👋</h2>
          <p>当前学习节点：<b class="t-brand">${U.esc(currentNodeName)}</b> · 课程总进度 ${o.courseProgress}%</p>
          <div class="bar bar--lg" style="max-width:420px;margin-top:10px"><i class="is-good" style="width:${o.courseProgress}%"></i></div>
        </div>
        <div class="hero__stats">
          <div class="hero__stat hero__stat--streak">
            <div class="streak-cal" id="streakCal">
              <div class="cal-top">
                <div class="cal-stats">
                  <div class="cal-stat">
                    <span class="cal-stat__lbl">当前连续学习</span>
                    <b class="cal-stat__num">${o.currentStreak}</b>
                    <span class="cal-stat__unit">天</span>
                  </div>
                  <div class="cal-stat">
                    <span class="cal-stat__lbl">最大连续学习</span>
                    <b class="cal-stat__num">${o.maxStreak}</b>
                    <span class="cal-stat__unit">天</span>
                  </div>
                  <div class="cal-stat">
                    <span class="cal-stat__lbl">总学习天数</span>
                    <b class="cal-stat__num">${o.totalDays}</b>
                    <span class="cal-stat__unit">天</span>
                  </div>
                </div>
                <div class="cal-legend">
                  <span class="cal-legend__year">${o.semesterLabel || _yrLabel}</span>
                </div>
              </div>
              <div class="cal-grid-wrap">
                <div class="cal-grid" id="streakCalGrid" style="--cal-weeks:${_calWeeks}">
                  ${o.streakHistoryStart && o.streakHistory.length ? (() => {
                    const DAYS = o.streakHistory.length;
                    const p = o.streakHistoryStart.split('-').map(Number);
                    const todayIdx = (typeof o.streakTodayIndex === 'number') ? o.streakTodayIndex : DAYS - 1;
                    let cells = '';
                    for (let i = 0; i < DAYS; i++) {
                      const v = o.streakHistory[i];
                      const dt = new Date(p[0], p[1] - 1, p[2]);
                      dt.setDate(dt.getDate() + i);
                      const dateStr = `${dt.getMonth() + 1}/${dt.getDate()}`;
                      let cls, tip;
                      if (i > todayIdx) {
                        cls = 'is-future'; tip = `${dateStr} · 未到`;
                      } else if (i === todayIdx) {
                        cls = (v > 0 ? 'is-on ' : '') + 'is-today';
                        tip = `今天（${dateStr}）· ${v > 0 ? '已学习' : '未学习'}`;
                      } else if (v === 0) {
                        cls = 'lv-0'; tip = `${dateStr} · 未学习`;
                      } else {
                        cls = 'is-on'; tip = `${dateStr} · 已学习`;
                      }
                      cells += `<i class="cal-cell ${cls}" title="${tip}"></i>`;
                    }
                    return cells;
                  })() : ''}
                </div>
                <div class="cal-weeks" style="--cal-weeks:${_calWeeks}">
                  ${(() => {
                    // 横轴标签写「第N周」而不是月份；列宽只有 10px、字宽约 31px（列距 12px），
                    // 逐周都写会压字，所以每 3 周标一次（第1、4、7…周）
                    let labels = '';
                    for (let w = 0; w < _calWeeks; w += 3) {
                      labels += `<span class="cal-week-label" style="grid-column-start:${w + 1}">第${w + 1}周</span>`;
                    }
                    return labels;
                  })()}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 待办 + 学情速览 -->
      <div class="grid g-21" style="margin-bottom:16px">
        <div class="card">
          <div class="card__head">
            <h3>${icon('bell')} 待办与提醒</h3>
            <span class="spacer"></span>
            <span class="row fz-11 t-dim" style="gap:4px">
              <i class="dot dot--${alertState.dot}"></i>${alertState.label}
            </span>
          </div>
          <div class="card__body stack" style="gap:10px">${d.todos.map(R.todo).join('')}</div>
        </div>

        <div class="card">
          <div class="card__head"><h3>${icon('target')} 学情速览</h3></div>
          <div class="card__body">
            <div class="rings">
              <div class="ring-cell" data-goto="mastery">${U.ring(m.completionRate, 'var(--brand-500)', '知识点完成率', '共 46 个', 96)}</div>
              <div class="ring-cell" data-goto="mastery">${U.ring(m.masteryRate, 'var(--ok)', '知识点学习完成率', '达标线 60%', 96)}</div>
              <div class="ring-cell" data-goto="mastery">${U.ring(m.goalAchieveRate, 'var(--accent-500)', '能力目标达成度', '基线 80%', 96)}</div>
            </div>
            <div class="callout callout--brand" style="margin-top:14px">
              ${icon('info')}<div>指标每日 06:00 全量刷新，练习提交后分钟级增量更新。点击环形图可下钻至<b>我的学情</b>。</div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI 快捷 / 薄弱点 / 最近动态 -->
      <div class="grid g-3">
        <div class="card">
          <div class="card__head"><h3>${icon('bot')} AI 助教</h3><span class="spacer"></span><span class="badge badge--brand">7×24 在线</span></div>
          <div class="card__body">
            <button class="btn btn--primary btn--block" data-goto="ai">${icon('send')} 一键发起提问</button>
            <div class="divider"></div>
            <p class="fz-12 t-dim" style="margin-bottom:9px">猜你想问</p>
            ${d.suggestedQuestions.slice(0, 4).map(q => `
              <button class="ask-item" data-ask="${U.esc(q)}">${icon('bulb')}<span>${U.esc(q)}</span></button>`).join('')}
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h3>${icon('alert')} 薄弱点提示</h3><span class="spacer"></span><span class="badge badge--danger">${d.weakPoints.length} 项</span></div>
          <div class="card__body stack" style="gap:12px">
            ${d.weakPoints.map(w => `
              <div>
                <div class="row" style="margin-bottom:5px">
                  <b class="fz-13 ${w.level === 'danger' ? 't-danger' : 't-warn'}">${U.esc(w.name)}</b>
                  <span class="spacer"></span>
                  <span class="mono fz-12 fw-6">${w.accuracyRate}%</span>
                </div>
                ${U.bar(w.accuracyRate)}
                <div class="row fz-11 t-dim" style="margin-top:5px">
                  <span>${U.esc(w.chapter)} · 错 ${w.errorCount} 题</span>
                  <span class="spacer"></span>
                  <span class="${w.trend < 0 ? 't-danger' : 't-ok'}">${w.trend > 0 ? '+' : ''}${w.trend}pp</span>
                  <button class="btn btn--xs btn--outline" data-practice-kp="${w.kpId}">去练习</button>
                </div>
              </div>`).join('')}
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h3>${icon('clock')} 最近学习动态</h3></div>
          <div class="card__body">
            <div class="tl-scroll">
              <div class="timeline">
                ${d.recentActivities.map(a => `
                  <div class="tl-item tl-item--${a.level}">
                    <time>${a.time}</time>
                    <b>${U.esc(a.title)}</b>
                    <p>${U.esc(a.meta)}</p>
                  </div>`).join('')}
              </div>
            </div>
          </div>
        </div>
      </div>`;

      _startTodayDurationTimer();

      // 交互绑定
      U.$$('[data-goto]', el).forEach(b => b.addEventListener('click', () => Router.go(b.dataset.goto)));
      U.$$('[data-ask]', el).forEach(b => b.addEventListener('click', () => {
        // 不自动发送：新建会话并把问题填入答疑输入框，由用户确认后自行发送
        Chat.draft(b.dataset.ask);
      }));
      U.$$('[data-practice-kp]', el).forEach(b => b.addEventListener('click', () => {
        Router.go('practice');
        Toast.info('已定位薄弱知识点', '可直接开始靶向强化练习');
      }));
      U.$$('.todo', el).forEach(t => t.addEventListener('click', () => {
        // 「继续练习」待办：带上会话 id + 模式 → 进入练习页后自动打开对应存档
        if (t.dataset.session && typeof Practice !== 'undefined') {
          Practice._pendingResume = { sessionId: t.dataset.session, mode: t.dataset.mode || 'order' };
          Router.go('practice');
          return;
        }
        // 「继续学习」待办：跳转资源中心并定位到该知识点（与「我的学情」下钻同一机制）
        if (t.dataset.target === 'resource' && t.dataset.kpName && typeof ResourceView !== 'undefined') {
          ResourceView._pendingKp = t.dataset.kpName;
          Router.go('resource');
          return;
        }
        if (t.dataset.target) Router.go(t.dataset.target);
      }));
    });
  }

// update：视图已 mount 过时再次进入也要刷新 —— 驾驶舱指标（尤其今日累计学习时长）
// 必须反映最新数据，不能停留在首次进入的快照上。
Router.register('dashboard', { title: '学习驾驶舱', mount: renderDashboard, update: renderDashboard });

function _greetingByTime() {
  const h = new Date().getHours();
  if (h < 6) return '凌晨好';
  if (h < 9) return '早上好';
  if (h < 12) return '上午好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  if (h < 22) return '晚上好';
  return '夜深了';
}
