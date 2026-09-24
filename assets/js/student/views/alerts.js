'use strict';

  /* ================================================================
     视图 7 · 预警与提醒

     2026-09-24：由「开发中」占位页改为真实页面，数据全部来自已实现的接口：
       GET  /student/alerts            我的预警（含 stats / openStats）
       PUT  /student/alerts/{id}/read  标记已读
       GET  /student/messages          教师私信 / 系统通知
       PUT  /student/messages/{id}/read

     预警口径（backend/app/services/alert_detector.py）：
       按知识点统计「每道题最近一次作答」的正确率（同题去重）；
       <50% 红 / 50%~60% 黄 / ≥60% 达标（达标即自动解除并删除记录）；
       且该知识点至少作答过 2 道不同题才参与判定，避免证据不足误报。
     ================================================================ */
  const Alerts = {
    level: 'all',
    _renderToken: 0,
    _isCurrent: () => true,
    _msgs: [],

    render() {
      const el = U.$('#view-alerts');
      if (!el) return;
      if (!API.config.activeCourseId) {
        if (window.renderStudentNoCourse) window.renderStudentNoCourse(el);
        return;
      }
      const token = ++this._renderToken;
      this._isCurrent = () => token === this._renderToken && !!API.config.activeCourseId;

      el.innerHTML = `
      <div class="grid g-4" style="margin-bottom:16px" id="alStats">${U.skeleton(90)}</div>

      <div class="grid g-21" style="align-items:start">
        <div class="card">
          <div class="card__head">
            <h3>${icon('bell')} 我的预警</h3>
            <span class="spacer"></span>
            <div class="seg" id="alSeg">
              <button data-l="all" class="is-active">全部</button>
              <button data-l="red">红</button>
              <button data-l="yellow">黄</button>
            </div>
            <button class="btn btn--sm" id="alRefresh" type="button">${icon('refresh')} 刷新</button>
          </div>
          <div class="card__body" id="alBody">${U.skeleton(220)}</div>
        </div>

        <div class="stack" style="gap:16px">
          <div class="card">
            <div class="card__head">
              <h3>${icon('message')} 提醒与通知</h3>
              <span class="spacer"></span>
              <span class="badge badge--outline" id="alMsgBadge">—</span>
            </div>
            <div class="card__body card__body--flush">
              <div class="list" id="alMsgList">${U.skeleton(70)}</div>
            </div>
          </div>
          <div class="card">
            <div class="card__body">
              <div class="row" style="gap:7px;align-items:center;font-size:12.5px;font-weight:650;color:var(--text-2)">
                ${icon('info')} 预警是怎么算的
              </div>
              <ul style="margin:9px 0 0;padding-left:18px;font-size:12px;color:var(--text-3);line-height:1.85">
                <li>按<b>知识点</b>统计正确率：每道题只取<b>最近一次</b>作答，避免重复练习拉偏。</li>
                <li>题目挂多个知识点时：<b>主知识点权重 1.0、其它标签权重 0.3</b> —— 做错会同时影响这些知识点，但主知识点责任更重。</li>
                <li><b>红</b> = 正确率 &lt; 50%；<b>黄</b> = 50%~60%；<b>≥60% 即达标</b>，预警会自动解除。</li>
                <li>该知识点至少作答过 <b>2 道不同题</b>才参与判定，题做太少不会误报。</li>
                <li>每次交卷或进入学习驾驶舱都会实时重算，不需要老师手动触发。</li>
              </ul>
            </div>
          </div>
        </div>
      </div>`;

      U.$$('#alSeg button', el).forEach(b => b.addEventListener('click', () => {
        U.$$('#alSeg button', el).forEach(x => x.classList.toggle('is-active', x === b));
        this.level = b.dataset.l || 'all';
        this.loadAlerts();
      }));
      U.$('#alRefresh', el).addEventListener('click', () => this.load());

      this.load();
    },

    load() {
      this.loadAlerts();
      this.loadMessages();
    },

    /** 顶部 4 张统计卡：口径 = 接口返回的 stats / openStats */
    _paintStats(stats, openStats) {
      const box = U.$('#alStats');
      if (!box) return;
      const s = stats || {}, os = openStats || {};
      const cards = [
        { k: '红色预警', v: s.red || 0, u: '条', c: 'var(--danger)', hint: '正确率 < 50%' },
        { k: '黄色预警', v: s.yellow || 0, u: '条', c: 'var(--warn)', hint: '正确率 50%~60%' },
        { k: '待处理', v: (os.red || 0) + (os.yellow || 0), u: '条', c: 'var(--brand-500)', hint: '红 + 黄中尚未处理的' },
        { k: '已忽略', v: s.green || 0, u: '条', c: 'var(--text-3)', hint: '教师判定无需处理' },
      ];
      box.innerHTML = cards.map(c => `
        <div class="stat" style="--_c:${c.c}">
          <div class="stat__label">${c.k}</div>
          <div class="stat__value"><span data-cnt="${c.v}">0</span><small>${c.u}</small></div>
          <div class="stat__hint">${c.hint}</div>
        </div>`).join('');
      U.$$('[data-cnt]', box).forEach(x => U.countUp(x, +x.dataset.cnt, 0));
    },

    loadAlerts() {
      const body = U.$('#alBody');
      if (!body) return;
      const isCurrent = this._isCurrent;
      body.innerHTML = `<div class="fz-12 t-dim" style="padding:16px">加载中…</div>`;
      API.student.alerts({ level: this.level }).then(r => {
        if (!isCurrent()) return;
        const list = (r && r.list) || [];
        this._paintStats(r && r.stats, r && r.openStats);
        body.innerHTML = list.length
          ? `<div class="stack" style="gap:12px">${list.map(a => this._card(a)).join('')}</div>`
          : R.empty('当前没有预警', this.level === 'all'
            ? '当你在某个知识点上的作答正确率低于 60%（且至少作答过 2 道不同题）时，这里会出现提醒'
            : '换「全部」看看 —— 当前级别下暂时没有预警', 'checkCircle');
        this._bindCards(body);
      }).catch(err => {
        if (!isCurrent()) return;
        body.innerHTML = `<div class="empty">${icon('alert')}<b>预警加载失败</b><p>${U.esc((err && err.message) || '')}</p></div>`;
      });
    },

    _card(a) {
      const lv = a.level || 'red';
      const ignored = a.status === 'ignored';
      const cardCls = ignored ? 'alert-card--ignored' : (U.alertCard[lv] || 'alert-card--red');
      const statusText = {
        open: '待处理', read: '已读', reviewed: '教师已复核', ignored: '教师已忽略', closed: '已解除',
      }[a.status] || a.status || '';
      const sugs = (a.suggestions || []).filter(s => s && s.text);
      return `
      <div class="alert-card ${cardCls}" data-alert="${U.esc(a.alertId)}">
        <div class="alert-card__head">
          <div class="alert-card__ico">${icon(lv === 'red' && !ignored ? 'alert' : ignored ? 'checkCircle' : 'info')}</div>
          <div class="alert-card__body">
            <div class="row">
              <span class="badge ${ignored ? 'badge--ignored' : (U.alertBadge[lv] || 'badge--danger')}">${ignored ? '已忽略' : (U.alertName[lv] || lv)}</span>
              ${a.kp ? `<span class="badge badge--outline">${U.esc(a.kp)}</span>` : ''}
              <span class="spacer"></span>
              <span class="fz-11 t-dim">${U.esc(a.createdAt || '')}</span>
            </div>
            <h4>${U.esc(a.title || '学习预警')}</h4>
            <p>${U.esc(a.desc || '')}</p>
            ${sugs.map(s => `<div class="callout callout--brand" style="margin:8px 0 0;padding:8px 10px">${icon('bulb')}<div>建议：<b>${U.esc(s.text)}</b></div></div>`).join('')}
          </div>
        </div>
        <div class="alert-card__foot">
          <span class="badge ${a.status === 'open' ? 'badge--danger' : 'badge--outline'}">${U.esc(statusText)}</span>
          ${a.trigger ? `<span class="fz-11 t-dim" title="${U.esc(a.trigger)}" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${U.esc(a.trigger)}</span>` : ''}
          <span class="spacer"></span>
          ${a.kpId ? `<button class="btn btn--sm btn--primary" data-practice-kp="${U.esc(a.kpId)}" data-practice-name="${U.esc(a.kp || '')}">去练习</button>` : ''}
          ${a.status === 'open' ? `<button class="btn btn--sm btn--outline" data-read="${U.esc(a.alertId)}">标记已读</button>` : ''}
        </div>
      </div>`;
    },

    _bindCards(root) {
      U.$$('[data-read]', root).forEach(b => b.addEventListener('click', () => {
        b.disabled = true;
        API.student.readAlert({ alertId: b.dataset.read }).then(() => {
          Toast.ok('已标记为已读');
          this.loadAlerts();
          if (window.refreshAlertBadge) window.refreshAlertBadge();
        }).catch(err => {
          b.disabled = false;
          Toast.err('标记失败', (err && err.message) || '');
        });
      }));
      // 建议里的「去练习」：带上知识点进练习页，自动按该知识点组卷（与薄弱点下钻同一机制）
      U.$$('[data-practice-kp]', root).forEach(b => b.addEventListener('click', () => {
        if (typeof Practice !== 'undefined') {
          Practice._pendingTarget = { kpId: b.dataset.practiceKp, kpName: b.dataset.practiceName || '' };
        }
        Router.go('practice');
      }));
    },

    loadMessages() {
      const box = U.$('#alMsgList');
      if (!box) return;
      const isCurrent = this._isCurrent;
      API.student.messages().then(r => {
        if (!isCurrent()) return;
        const list = (r && r.list) || [];
        this._msgs = list;
        const unread = list.filter(m => !m.read).length;
        const badge = U.$('#alMsgBadge');
        if (badge) badge.textContent = unread ? `${unread} 条未读` : `${list.length} 条`;
        box.innerHTML = list.length ? list.map((m, i) => `
          <div class="list__item list__item--clickable ${m.read ? 'is-read' : ''}" data-msg="${i}">
            <span class="list__lead">${icon(m.from === '系统' ? 'info' : 'user')}</span>
            <div class="list__main">
              <b>${U.esc(m.title || '通知')} ${m.read ? '' : '<span class="badge badge--danger">未读</span>'}</b>
              <p class="clamp-2">${U.esc(m.content || '')}</p>
              <p class="fz-11 t-dim">${U.esc(m.fromName || m.from || '系统')} · ${U.esc(m.time || '')}</p>
            </div>
          </div>`).join('') : R.empty('暂无提醒', '教师私信与系统通知会出现在这里', 'message');
        U.$$('[data-msg]', box).forEach(el => el.addEventListener('click', () => {
          const m = this._msgs[+el.dataset.msg];
          if (!m) return;
          Modal.open({
            title: U.esc(m.title || '通知'),
            body: `<div class="stack" style="gap:10px">
              <div class="fz-12 t-dim">${U.esc(m.fromName || m.from || '系统')} · ${U.esc(m.time || '')}</div>
              <div style="white-space:pre-wrap;line-height:1.8">${U.esc(m.content || '')}</div>
            </div>`,
            footer: '<button class="btn" data-close>关闭</button>',
          });
          if (!m.read) {
            API.student.readMessage({ msgId: m.msgId }).then(() => {
              m.read = true;
              this.loadMessages();
              if (window.refreshMsgBadge) window.refreshMsgBadge();
            }).catch(() => {});
          }
        }));
      }).catch(() => {
        if (!isCurrent()) return;
        box.innerHTML = R.empty('提醒加载失败', '', 'alert');
      });
    },
  };

  // 注册路由：注册 'alerts' 后，侧栏「预警与提醒」与驾驶舱待办「去处理」都能进真实页面
  // （未注册时 Router.go 会静默失败，表现为点击无反应）。
  Router.register('alerts', {
    title: '预警与提醒',
    mount: () => Alerts.render(),
    update: () => Alerts.render(),
    reset: () => { Alerts.level = 'all'; Alerts._msgs = []; },
  });
