/* ==========================================================================
   学生端 · 应用引导（路由守卫 / 顶栏 / 全局初始化）
   必须最先加载；视图模块随后各自 Router.register，最后由 start.js 启动路由。
   ========================================================================== */
(function () {
  'use strict';
    if (window.Auth && !Auth.requireAuth('student')) return;
  
    Theme.init();
    // 侧栏图标注入
    U.$$('.nav-item').forEach(n => n.insertAdjacentHTML('afterbegin', icon(n.dataset.icon, 'nav-item__icon')));
    U.$('#msgBtn').innerHTML = icon('message');
    initTopbar();
  
    /* ================================================================
       顶栏：更新时间 + 消息
       ================================================================ */
    API.student.dashboard().then(d => {
      U.$('#updateTag').textContent = '学情更新于 ' + d.coreMetrics.updatedAt;
    });

    /* ================================================================
       导航侧栏 · 预警徽标（动态绑定后端真实 red + yellow 数量）
       ================================================================ */
    window.refreshAlertBadge = function () {
      API.student.alerts({ level: 'all' }).then(r => {
        const o = r.openStats || {};
        const n = (o.red || 0) + (o.yellow || 0);   // 只算未处理（open）的 red + yellow
        const b = document.getElementById('alertBadge');
        if (b) { b.textContent = n; b.style.display = n > 0 ? '' : 'none'; }
      }).catch(() => {});
    };
    window.refreshAlertBadge();
  
    U.$('#msgBtn').addEventListener('click', () => {
      API.student.messages().then(r => {
        const list = r.list || [];
        const body = list.length
          ? `<div class="list" style="margin:-20px">${list.map((m, idx) => {
              const preview = (m.content || '').length > 48 ? (m.content.slice(0, 48) + '…') : (m.content || '');
              return `<div class="list__item list__item--clickable msg-item ${m.read ? 'is-read' : ''}" data-msg-id="${U.esc(m.msgId)}" data-idx="${idx}">
                <span class="list__lead">${icon(m.from === '系统' ? 'info' : 'user', '')}</span>
                <div class="list__main">
                  <b>${U.esc(m.title)} ${m.read ? '' : '<span class="badge badge--danger">未读</span>'}</b>
                  <p style="margin:5px 0;line-height:1.7;color:var(--text-2)">${U.esc(preview)}</p>
                  <p class="fz-11 t-dim">${U.esc(m.from)} · ${m.time}</p>
                </div>
              </div>`;
            }).join('')}</div>`
          : `<div class="empty" style="padding:30px 20px">${icon('message')}<b>暂无消息</b><p class="t-dim">教师私信和系统通知会显示在这里</p></div>`;
        Modal.open({
          title: '消息与通知',
          body,
          onMount() {
            U.$$('.msg-item').forEach(el => {
              el.addEventListener('click', () => {
                const idx = parseInt(el.dataset.idx, 10);
                const m = list[idx];
                if (!m) return;
                openMessageDetail(m, el);
              });
            });
          }
        });
      });
    });

    // 点击消息项 → 打开详情弹窗（含完整内容），未读则自动标记已读
    function openMessageDetail(m, listEl) {
      const detailBody = `<div class="msg-detail">
        <div class="msg-detail__meta">
          <span class="list__lead">${icon(m.from === '系统' ? 'info' : 'user', '')}</span>
          <div class="msg-detail__who">
            <b>${U.esc(m.title)}</b>
            <span class="fz-11 t-dim">${U.esc(m.from)} · ${U.esc(m.time)}</span>
          </div>
        </div>
        <div class="msg-detail__body">${U.esc(m.content)}</div>
      </div>`;
      Modal.open({
        title: '消息详情',
        body: detailBody,
        footer: null,
        onMount() {
          if (m.read || !listEl) return;
          API.student.readMessage({ msgId: m.msgId })
            .then(() => {
              m.read = true;
              listEl.classList.add('is-read');
              const badge = listEl.querySelector('.badge');
              if (badge) badge.remove();
              if (window.refreshAlertBadge) window.refreshAlertBadge();
            })
            .catch(() => {});
        }
      });
    }
  window.__studentAuthed = true;
})();
