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

  /** 刷新欢迎区「今日学习」时长；extra 存在时把练习 / 视频明细写进 title */
  function _paintTodayDuration(seconds, extra) {
    const el = U.$('#todayStudyDuration');
    if (!el) return;
    el.textContent = _fmtStudyDuration(seconds);
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
      const todayStudyText = _fmtStudyDuration(o.todayStudySeconds != null ? o.todayStudySeconds : (o.todayStudyMinutes || 0) * 60);
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
      const _streakHistory = Array.isArray(o.streakHistory) ? o.streakHistory : [];
      // 打卡热力图：列 = 周，周数由后端按「学期第 1 周（8/31）起算」给出
      const _calWeeks = o.streakWeeks || Math.ceil(_streakHistory.length / 7) || 52;
      const _calGridWidth = Math.max(11, _calWeeks * 11 + Math.max(0, _calWeeks - 1) * 4);

      el.innerHTML = `
      <!-- Hero -->
      <div class="hero hero--learning" style="margin-bottom:16px">
        <div class="hero__main">
          <div class="row" style="margin-bottom:6px">
            ${R.lamp(o.status === 'danger' ? 'red' : o.status === 'warn' ? 'yellow' : 'ok', lampText[o.status])}
          </div>
          <h2>${greeting}，${U.esc(userName)} 👋</h2>
          <p>当前学习节点：<b class="t-brand">${U.esc(currentNodeName)}</b></p>
          <div class="bar bar--lg hero__progress"><i class="is-good" style="width:${o.courseProgress}%"></i></div>
          <div class="hero__glance">
            <div class="hero__glance-item">
              <span>课程进度</span>
              <b>${o.courseProgress}%</b>
            </div>
            <div class="hero__glance-item">
              <span>今日学习</span>
              <b id="todayStudyDuration"
                title="练习 ${_fmtStudyDuration(o.todayPracticeSeconds || 0)} · 视频观看 ${_fmtStudyDuration(o.todayResourceSeconds || 0)}">${todayStudyText}</b>
            </div>
            <div class="hero__glance-item">
              <span>连续学习</span>
              <b>${o.currentStreak} 天</b>
            </div>
            <div class="hero__glance-item">
              <span>累计打卡</span>
              <b>${o.totalDays} 天</b>
            </div>
          </div>
        </div>
        <div class="hero__stats">
          <div class="hero__stat hero__stat--streak">
            <div class="streak-cal" id="streakCal" style="--cal-grid-width:${_calGridWidth}px">
              <div class="cal-top">
                <div class="cal-legend">
                  <span class="cal-legend__year">${o.semesterLabel || _yrLabel}</span>
                </div>
              </div>
              <div class="cal-grid-wrap">
                <div class="cal-grid" id="streakCalGrid" style="--cal-weeks:${_calWeeks}">
                  ${o.streakHistoryStart && _streakHistory.length ? (() => {
                    const DAYS = _streakHistory.length;
                    const p = o.streakHistoryStart.split('-').map(Number);
                    const todayIdx = (typeof o.streakTodayIndex === 'number') ? o.streakTodayIndex : DAYS - 1;
                    let cells = '';
                    for (let i = 0; i < DAYS; i++) {
                      const v = _streakHistory[i];
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
                  // 横轴标签写「第N周」而不是月份；每 3 周标一次，保留周视图。
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
        <div class="hero__feed" id="frontierFeed">
          <div class="frontier-feed__head">
            <b>更多资源分享</b>
          </div>
          <div class="frontier-feed__list" id="frontierFeedList" role="region" aria-label="更多资源分享，可左右滚动" tabindex="0">
            <p class="fz-12 t-dim">正在加载…</p>
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
          </div>
        </div>
      </div>

      <!-- 薄弱点提示 / 最近学习动态（占满两列） -->
      <div class="grid g-2">

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
          <div class="card__head">
            <h3>${icon('clock')} 最近学习动态</h3>
            <span class="spacer"></span>
            <div class="tl-range" id="tlRange">
              <button class="tl-range__btn" id="tlRangeBtn" type="button" aria-expanded="false" aria-haspopup="listbox">
                <span class="tl-range__label">时间维度</span>
                <span class="tl-range__value" id="tlRangeValue">今天</span>
                ${icon('chevronDown')}
              </button>
              <div class="tl-range__menu" id="tlRangeMenu" hidden role="listbox">
                ${[
                  ['today', '今天'],
                  ['yesterday', '昨天'],
                  ['7d', '近 7 天'],
                  ['30d', '近 30 天'],
                  ['month', '本月'],
                  ['lastMonth', '上月'],
                ].map(([id, label], i) => `
                  <button class="tl-range__opt${i === 0 ? ' is-active' : ''}" type="button" data-range="${id}" data-label="${label}">
                    <span>${label}</span>${i === 0 ? icon('check') : '<span class="tl-range__check"></span>'}
                  </button>`).join('')}
              </div>
            </div>
          </div>
          <div class="card__body">
            <div class="tl-scroll" id="tlRangeList"></div>
          </div>
        </div>
      </div>`;

      _startTodayDurationTimer();
      _bindActivityRange(el, Array.isArray(d.recentActivities) ? d.recentActivities : []);

      // 交互绑定
      U.$$('[data-goto]', el).forEach(b => b.addEventListener('click', () => Router.go(b.dataset.goto)));
      _loadFrontierFeed();
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

function _loadFrontierFeed() {
  const box = U.$('#frontierFeedList');
  if (!box) return;
  API.student.shares().then(d => {
    const list = Array.isArray(d.list) ? d.list : [];
    if (!list.length) {
      box.innerHTML = '<p class="fz-12 t-dim">还没有新的资源。</p>';
      return;
    }
    box.innerHTML = list.map(item => `
      <button type="button" class="frontier-feed__item ${item.read ? 'is-read' : ''}" title="${U.esc(item.title)}" data-share-id="${U.esc(item.shareId)}" data-url="${U.esc(item.url)}">
        <b>${U.esc(item.title)}</b>
        <span>${U.esc(item.source || '教师推荐')}</span>
        ${item.publishedOn ? `<span class="frontier-feed__date">${U.esc(item.publishedOn)}</span>` : ''}
      </button>`).join('');
    U.$$('[data-share-id]', box).forEach(btn => btn.addEventListener('click', () => {
      const url = btn.dataset.url;
      const id = btn.dataset.shareId;
      if (url) window.open(url, '_blank', 'noopener');
      if (id) API.student.readShare(id).then(() => btn.classList.add('is-read')).catch(() => {});
    }));
  }).catch(() => {
    box.innerHTML = '<p class="fz-12 t-dim">暂时无法加载分享。</p>';
  });
}

function _parseActivityTime(raw) {
  if (!raw) return null;
  if (raw instanceof Date) return isNaN(+raw) ? null : raw;
  const s = String(raw).trim();
  if (!s) return null;
  if (/Z$|[+-]\d{2}:?\d{2}$/.test(s)) {
    const d = new Date(s);
    return isNaN(+d) ? null : d;
  }
  const iso = s.includes('T') ? s : s.replace(' ', 'T');
  const d = new Date(iso + 'Z');
  return isNaN(+d) ? null : d;
}

function _cnParts(d) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: 'numeric', day: 'numeric'
  }).formatToParts(d);
  const get = t => Number(parts.find(p => p.type === t).value);
  return { y: get('year'), m: get('month'), day: get('day') };
}

function _cnDayUtc(d) {
  const p = _cnParts(d);
  return Date.UTC(p.y, p.m - 1, p.day);
}

function _activityInRange(d, range) {
  const now = new Date();
  const today = _cnDayUtc(now);
  const act = _cnDayUtc(d);
  const day = 86400000;
  if (range === 'today') return act === today;
  if (range === 'yesterday') return act === today - day;
  if (range === '7d') return act >= today - 6 * day && act <= today;
  if (range === '30d') return act >= today - 29 * day && act <= today;
  const np = _cnParts(now), ap = _cnParts(d);
  if (range === 'month') return np.y === ap.y && np.m === ap.m;
  if (range === 'lastMonth') {
    let y = np.y, m = np.m - 1;
    if (m < 1) { m = 12; y -= 1; }
    return ap.y === y && ap.m === m;
  }
  return true;
}

function _activityItemHtml(a) {
  return `<div class="tl-item tl-item--${U.esc(a.level || 'ok')}">
    <time>${U.esc(a.time || '')}</time>
    <b>${U.esc(a.title)}</b>
    <p>${U.esc(a.meta)}</p>
  </div>`;
}

function _bindActivityRange(root, list) {
  const wrap = U.$('#tlRange', root);
  const btn = U.$('#tlRangeBtn', root);
  const menu = U.$('#tlRangeMenu', root);
  const value = U.$('#tlRangeValue', root);
  const box = U.$('#tlRangeList', root);
  if (!wrap || !btn || !menu || !box) return;
  let range = 'today';

  const close = () => {
    wrap.classList.remove('is-open');
    menu.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  };
  const paint = () => {
    const filtered = list.filter(a => {
      const t = _parseActivityTime(a.time_sort);
      if (t) return _activityInRange(t, range);
      const label = String(a.time || '');
      if (range === 'today') return label.startsWith('今天');
      if (range === 'yesterday') return label.startsWith('昨天');
      return true;
    });
    box.innerHTML = filtered.length
      ? `<div class="timeline">${filtered.map(_activityItemHtml).join('')}</div>`
      : '<p class="fz-13 t-dim" style="padding:12px 0;text-align:center">该时间范围内暂无学习动态</p>';
    U.$$('[data-range]', menu).forEach(opt => {
      const on = opt.dataset.range === range;
      opt.classList.toggle('is-active', on);
      const mark = opt.querySelector('svg, .tl-range__check');
      if (mark) mark.outerHTML = on ? icon('check') : '<span class="tl-range__check"></span>';
    });
  };

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = wrap.classList.toggle('is-open');
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  menu.addEventListener('click', e => {
    const opt = e.target.closest('[data-range]');
    if (!opt) return;
    range = opt.dataset.range;
    value.textContent = opt.dataset.label;
    close();
    paint();
  });
  if (window._tlRangeDocClose) document.removeEventListener('click', window._tlRangeDocClose);
  window._tlRangeDocClose = e => { if (!wrap.contains(e.target)) close(); };
  document.addEventListener('click', window._tlRangeDocClose);
  paint();
}

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
