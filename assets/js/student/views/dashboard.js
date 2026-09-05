'use strict';

  /* ================================================================
     视图 1 · 学习驾驶舱
     ================================================================ */
  function renderDashboard() {
    const el = U.$('#view-dashboard');
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

      // 以本月为中心向前推 12 个月（含本月）所涉及的年份，动态生成年份区间标签
      const _now = new Date();
      const _endY = _now.getFullYear();
      const _startY = new Date(_now.getFullYear(), _now.getMonth() - 11, 1).getFullYear();
      const _yrLabel = _startY === _endY ? `${_endY}` : `${_startY}-${_endY}`;

      el.innerHTML = `
      <!-- Hero -->
      <div class="hero" style="margin-bottom:16px">
        <div class="hero__main">
          <div class="row" style="margin-bottom:6px">
            ${R.lamp(o.status === 'danger' ? 'red' : o.status === 'warn' ? 'yellow' : 'ok', lampText[o.status])}
            <span class="badge badge--outline">今日已学 ${o.todayStudyMinutes} 分钟</span>
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
                  <span class="cal-legend__year">${_yrLabel}</span>
                </div>
              </div>
              <div class="cal-grid-wrap">
                <div class="cal-grid" id="streakCalGrid">
                  ${o.streakHistoryStart && o.streakHistory.length ? (() => {
                    const WEEKS = 52, DAYS = WEEKS * 7;
                    const p = o.streakHistoryStart.split('-').map(Number);
                    let cells = '';
                    for (let i = 0; i < DAYS; i++) {
                      const v = o.streakHistory[i];
                      const dt = new Date(p[0], p[1] - 1, p[2]);
                      dt.setDate(dt.getDate() + i);
                      const dateStr = `${dt.getMonth() + 1}/${dt.getDate()}`;
                      let cls, tip;
                      if (i === DAYS - 1) {
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
                <div class="cal-months">
                  ${o.streakHistoryStart && o.streakHistory.length ? (() => {
                    const WEEKS = 52, DAYS = WEEKS * 7;
                    const p = o.streakHistoryStart.split('-').map(Number);
                    let lastM = -1, labels = '';
                    for (let w = 0; w < WEEKS; w++) {
                      let labelMonth = -1;
                      for (let d = 0; d < 7; d++) {
                        const idx = w * 7 + d;
                        if (idx >= DAYS) break;
                        const dt = new Date(p[0], p[1] - 1, p[2]);
                        dt.setDate(dt.getDate() + idx);
                        if (dt.getDate() === 1) { labelMonth = dt.getMonth(); break; }
                      }
                      if (labelMonth === -1) continue;
                      if (labelMonth !== lastM) {
                        labels += `<span class="cal-month-label" style="grid-column-start:${w + 1}">${labelMonth + 1}月</span>`;
                        lastM = labelMonth;
                      }
                    }
                    return labels;
                  })() : ''}
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
            <span class="row fz-11 t-dim" style="gap:10px">
              <span class="row" style="gap:4px"><i class="dot dot--ok"></i>正常</span>
              <span class="row" style="gap:4px"><i class="dot dot--warn"></i>需关注</span>
              <span class="row" style="gap:4px"><i class="dot dot--danger"></i>预警</span>
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
                  <span class="mono fz-12 fw-6">${w.masteryRate}%</span>
                </div>
                ${U.bar(w.masteryRate)}
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
          <div class="card__head"><h3>${icon('clock')} 最近学习动态</h3><span class="spacer"></span><button class="btn btn--xs btn--ghost" data-goto="mastery">全部</button></div>
          <div class="card__body">
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
      </div>`;

      // 交互绑定
      U.$$('[data-goto]', el).forEach(b => b.addEventListener('click', () => Router.go(b.dataset.goto)));
      U.$$('[data-ask]', el).forEach(b => b.addEventListener('click', () => {
        Router.go('ai');
        setTimeout(() => Chat.ask(b.dataset.ask), 260);
      }));
      U.$$('[data-practice-kp]', el).forEach(b => b.addEventListener('click', () => {
        Router.go('practice');
        Toast.info('已定位薄弱知识点', '可直接开始靶向强化练习');
      }));
      U.$$('.todo', el).forEach(t => t.addEventListener('click', () => {
        if (t.dataset.target) Router.go(t.dataset.target);
      }));
    });
  }

Router.register('dashboard', { title: '学习驾驶舱', mount: renderDashboard });

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
