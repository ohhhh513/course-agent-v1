/* ==========================================================================
   课程智能体系统 · 公共工具（图标 / 主题 / 路由 / 组件）
   ========================================================================== */

/* ---------------- 1. 图标库（Lucide 风格 stroke 图标） ---------------- */
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  layers: '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
  bot: '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4M9 14h.01M15 14h.01M9 18h6"/><path d="M2 13v2M22 13v2"/>',
  pencil: '<path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
  chart: '<path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/><rect x="17" y="4" width="3" height="14"/>',
  bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  search2: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 6 3.5-6 3.5Z"/>',
  video: '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="m16 11 6-3.5v9L16 13Z"/>',
  ppt: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>',
  quiz: '<path d="M9 11 4 6l5-5"/><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6M9 13h6M9 17h4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  xCircle: '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-5M12 8h.01"/>',
  bulb: '<path d="M9 18h6M10 22h4"/><path d="M12 2a6 6 0 0 0-3.5 10.9c.6.5 1 1.3 1 2.1h5c0-.8.4-1.6 1-2.1A6 6 0 0 0 12 2Z"/>',
  trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M21 7h-5v5" transform="translate(0.5,-0.5)"/>',
  down: '<path d="m3 7 6 6 4-4 8 8"/><path d="M21 17h-5v-5" transform="translate(0.5,0.5)"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4Z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  shuffle: '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7"/><path d="M17 4.5a3.5 3.5 0 0 1 0 7M18 21c0-2.5-.7-4.5-2-6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>',
  fire: '<path d="M12 22c4 0 7-2.7 7-6.5 0-4.5-4-6-4-10 0 0-1 2-3 3-2.5 1.3-4 3.6-4 7C8 19.3 9 22 12 22Z"/><path d="M12 22c-1.5 0-2.5-1.3-2.5-3s1-2.5 2.5-4c1.5 1.5 2.5 2.3 2.5 4s-1 3-2.5 3Z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M12 3v13M7 8l5-5 5 5"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M12 16V3M7 11l5 5 5-5"/>',
  print: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 17h12v4H6z"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  sun: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>',
  moon: '<path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10Z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5Z"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14a4 4 0 0 0 7 0M9 9.5h.01M15 9.5h.01"/>',
  shield: '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5Z"/><path d="m9 12 2 2 4-4"/>',
  code: '<path d="m8 6-6 6 6 6M16 6l6 6-6 6"/>',
  quote: '<path d="M8 6H4a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h2v2a2 2 0 0 1-2 2"/><path d="M20 6h-4a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h2v2a2 2 0 0 1-2 2"/>',
  message: '<path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.2-4.2A8 8 0 1 1 21 12Z"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8Z"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  edit: '<path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4Z"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
  thumbUp: '<path d="M7 21V10l4-8a2 2 0 0 1 2.8 1.8V9h4.4a2 2 0 0 1 2 2.4l-1.4 7A2 2 0 0 1 16.8 20H7Z"/><path d="M7 10H4v11h3"/>',
  thumbDown: '<path d="M17 3v11l-4 8a2 2 0 0 1-2.8-1.8V15H5.8a2 2 0 0 1-2-2.4l1.4-7A2 2 0 0 1 7.2 4H17Z"/><path d="M17 14h3V3h-3"/>',
  route: '<circle cx="6" cy="19" r="3"/><circle cx="18" cy="5" r="3"/><path d="M9 19h5a4 4 0 0 0 0-8H8a4 4 0 0 1 0-8h4"/>',
  network: '<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-2h14v2"/>',
  sparkle: '<path d="m12 3 1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4Z"/><path d="M19 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8Z"/>',
  flask: '<path d="M9 3h6M10 3v6L4.5 19a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9V3"/><path d="M7 15h10"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 11h18"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  award: '<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 8 5-3 5 3-1.5-8"/>',
  link: '<path d="M9.5 14.5 14.5 9.5"/><path d="M8 12 6 14a3.5 3.5 0 0 0 5 5l2-2M16 12l2-2a3.5 3.5 0 0 0-5-5l-2 2"/>'
};

function icon(name, cls) {
  const path = ICONS[name] || ICONS.info;
  return `<svg class="${cls || ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}

/* ---------------- 2. 工具函数 ---------------- */
const U = {
  $: (s, r) => (r || document).querySelector(s),
  $$: (s, r) => Array.from((r || document).querySelectorAll(s)),

  /** 掌握率 → 五级等级 */
  level(v) {
    if (v <= 0) return 'none';
    if (v >= 85) return 'excellent';
    if (v >= 75) return 'good';
    if (v >= 60) return 'fair';
    return 'weak';
  },
  levelName: { excellent: '优秀', good: '良好', fair: '待加强', weak: '薄弱', none: '未学习' },
  levelColor: { excellent: 'var(--lv-excellent)', good: 'var(--lv-good)', fair: 'var(--lv-fair)', weak: 'var(--lv-weak)', none: 'var(--lv-none)' },
  levelBar: {
    excellent: 'is-ok', good: 'is-good', fair: 'is-fair', weak: 'is-weak', none: 'is-none',
    dashRed: 'is-dash-red', dashBrown: 'is-dash-brown',
    dashLightGreen: 'is-dash-light-green', dashGreen: 'is-dash-green',
  },
  levelBadge: { excellent: 'badge--ok', good: 'badge--ok', fair: 'badge--warn', weak: 'badge--danger', none: 'badge--outline' },

  alertName: { red: '紧急', yellow: '关注', green: '正常' },
  alertBadge: { red: 'badge--danger', yellow: 'badge--warn', green: 'badge--ok' },
  alertCard: { red: 'alert-card--red', yellow: 'alert-card--yellow', green: 'alert-card--green' },

  /** 难度星级 */
  stars(n) {
    return '★'.repeat(n) + '<span class="t-dim">' + '★'.repeat(5 - n) + '</span>';
  },

  /** 秒 → mm:ss / HH:mm:ss */
  fmtDuration(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return `${m}分${String(s).padStart(2, '0')}秒`;
  },

  /** 数字动画 */
  countUp(el, target, decimals) {
    const d = decimals === undefined ? 1 : decimals;
    const start = performance.now(), dur = 900;
    function tick(now) {
      const p = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * eased).toFixed(d);
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = Number(target).toFixed(d);
    }
    requestAnimationFrame(tick);
  },

  /** 环形进度渲染（含动画） */
  ring(percent, color, label, sub, size) {
    const sz = size || 104;
    return `<div class="ring" style="--p:${percent};--c:${color};--sz:${sz}px">
      <div class="ring__txt"><b>${percent}<small>%</small></b>${sub ? `<span>${sub}</span>` : ''}</div>
    </div>${label ? `<p>${label}</p>` : ''}`;
  },

  /** 进度条 */
  bar(v, level, size) {
    const lv = level || U.level(v);
    return `<div class="bar ${size ? 'bar--' + size : ''}"><i class="${U.levelBar[lv]}" style="width:${Math.max(v, 0)}%"></i></div>`;
  },

  /** 转义 */
  esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  /** 骨架屏 */
  skeleton(h) {
    return `<div style="height:${h || 120}px;border-radius:var(--r-md);background:linear-gradient(90deg,var(--surface-2) 25%,var(--surface-3) 50%,var(--surface-2) 75%);background-size:200% 100%;animation:sk 1.4s infinite"></div>`;
  },

  delta(v, unit) {
    if (v == null) return '';
    const up = v >= 0;
    return `<span class="stat__delta ${up ? 'delta-up' : 'delta-down'}">${icon(up ? 'trend' : 'down')} ${up ? '+' : ''}${v}${unit || 'pp'}</span>`;
  }
};

// 骨架屏动画
(function () {
  const st = document.createElement('style');
  st.textContent = '@keyframes sk{0%{background-position:200% 0}100%{background-position:-200% 0}}';
  document.head.appendChild(st);
})();

/* ---------------- 3. 主题 ---------------- */
/* 夜间模式已取消：界面固定为蓝白（亮色）主题 */
const Theme = {
  get() { return 'light'; },
  set() {
    document.documentElement.setAttribute('data-theme', 'light');
    window.dispatchEvent(new CustomEvent('themechange', { detail: 'light' }));
  },
  toggle() { this.set(); },
  init() { this.set(); }
};

/* ---------------- 4. Toast ---------------- */
const Toast = {
  box: null,
  _loadingEl: null,
  ensure() {
    if (!this.box) {
      this.box = document.createElement('div');
      this.box.className = 'toasts';
      document.body.appendChild(this.box);
    }
    return this.box;
  },
  show(title, desc, type) {
    const t = type || 'info';
    const ic = { ok: 'checkCircle', warn: 'alert', danger: 'xCircle', info: 'info' }[t];
    const el = document.createElement('div');
    el.className = 'toast toast--' + t;
    el.innerHTML = `${icon(ic)}<div style="flex:1;min-width:0"><b>${U.esc(title)}</b>${desc ? `<p>${U.esc(desc)}</p>` : ''}</div>`;
    this.ensure().appendChild(el);
    setTimeout(() => { el.classList.add('is-out'); setTimeout(() => el.remove(), 260); }, 3000);
  },
  ok(t, d) { this.show(t, d, 'ok'); },
  warn(t, d) { this.show(t, d, 'warn'); },
  err(t, d) { this.show(t, d, 'danger'); },
  info(t, d) { this.show(t, d, 'info'); },
  loading(title) {
    // 如果已有 loading toast，先移除
    if (this._loadingEl) {
      this._loadingEl.remove();
      this._loadingEl = null;
    }
    const el = document.createElement('div');
    el.className = 'toast toast--info';
    el.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-radius:50%;border:2px solid var(--brand);border-top-color:transparent;animation:spin .8s linear infinite"></span><div style="flex:1;min-width:0"><b>${U.esc(title || '加载中...')}</b></div>`;
    this.ensure().appendChild(el);
    this._loadingEl = el;
    // 自动消失（也可手动 ok/warn 覆盖）
    setTimeout(() => { if (el.parentNode) { el.classList.add('is-out'); setTimeout(() => el.remove(), 260); } }, 15000);
  },
  done() {
    if (this._loadingEl) {
      this._loadingEl.classList.add('is-out');
      setTimeout(() => this._loadingEl.remove(), 260);
      this._loadingEl = null;
    }
  }
};

/* ---------------- 5. Modal ---------------- */
const Modal = {
  open(opts) {
    const ov = document.createElement('div');
    ov.className = 'overlay';
    ov.innerHTML = `<div class="modal ${opts.size ? 'modal--' + opts.size : ''}">
      <div class="modal__head"><h3>${opts.title}</h3>
        <button class="btn btn--ghost btn--icon btn--sm" data-close>${icon('x')}</button></div>
      <div class="modal__body">${opts.body}</div>
      ${opts.footer === null ? '' : `<div class="modal__foot">${opts.footer || `<button class="btn" data-close>关闭</button>`}</div>`}
    </div>`;
    document.body.appendChild(ov);
    const close = () => ov.remove();
    ov.addEventListener('click', e => {
      if (e.target === ov || e.target.closest('[data-close]')) close();
    });
    if (opts.onMount) opts.onMount(ov, close);
    return { el: ov, close };
  },
  drawer(opts) {
    const ov = document.createElement('div');
    ov.className = 'overlay';
    ov.style.padding = '0';
    ov.style.placeItems = 'stretch';
    ov.innerHTML = `<div class="drawer">
      <div class="modal__head"><h3>${opts.title}</h3>
        <button class="btn btn--ghost btn--icon btn--sm" data-close>${icon('x')}</button></div>
      <div class="modal__body" style="padding:0">${opts.body}</div>
      ${opts.footer ? `<div class="modal__foot">${opts.footer}</div>` : ''}
    </div>`;
    document.body.appendChild(ov);
    const close = () => ov.remove();
    ov.addEventListener('click', e => {
      if (e.target === ov || e.target.closest('[data-close]')) close();
    });
    if (opts.onMount) opts.onMount(ov, close);
    return { el: ov, close };
  }
};

/* ---------------- 6. 视图路由 ---------------- */
const Router = {
  views: {},
  current: null,
  titles: {},
  register(key, cfg) { this.views[key] = cfg; },
  go(key, params) {
    if (!this.views[key]) return;
    U.$$('.view').forEach(v => v.classList.remove('is-active'));
    const el = U.$('#view-' + key);
    if (el) el.classList.add('is-active');
    U.$$('.nav-item').forEach(n => n.classList.toggle('is-active', n.dataset.view === key));
    const cfg = this.views[key];
    const tt = U.$('#pageTitle'), ts = U.$('#pageSub');
    if (tt) tt.textContent = cfg.title || '';
    if (ts) ts.textContent = cfg.sub || '';
    location.hash = '#' + key;
    this.current = key;
    U.$('.content').scrollTo ? window.scrollTo({ top: 0, behavior: 'smooth' }) : null;
    if (cfg.mount && !cfg._mounted) { cfg.mount(params); cfg._mounted = true; }
    else if (cfg.update) cfg.update(params);
  },
  init(def) {
    U.$$('.nav-item').forEach(n => n.addEventListener('click', () => this.go(n.dataset.view)));
    const h = location.hash.replace('#', '');
    this.go(this.views[h] ? h : def);
    window.addEventListener('hashchange', () => {
      const k = location.hash.replace('#', '');
      if (k && k !== this.current && this.views[k]) this.go(k);
    });
  }
};

/* ---------------- 7. 顶栏通用初始化 ---------------- */
function initTopbar() {
  const out = U.$('#logoutBtn');
  if (out) {
    out.innerHTML = icon('logout');
    out.title = '退出登录';
    out.addEventListener('click', () => {
      if (window.Auth) Auth.logout();
      location.href = 'index.html';
    });
  }
  if (window.Auth) Auth.applyUserBadge();
}

/* ---------------- 8. 组件片段渲染器 ---------------- */
const R = {
  /** 待办条 */
  todo(t) {
    const actionData = t.userId ? ` data-action="${U.esc(t.action)}" data-user-id="${U.esc(t.userId)}" data-user-name="${U.esc(t.userName || '')}"` : '';
    return `<div class="todo" data-target="${t.target || ''}"${actionData}>
      <div class="todo__ico todo__ico--${t.level}">${icon(t.type === 'alert' ? 'alert' : t.type === 'homework' ? 'pencil' : t.type === 'practice' ? 'target' : 'sparkle')}</div>
      <div class="todo__main"><b>${U.esc(t.title)}</b><span>${U.esc(t.desc)}</span></div>
      <button class="btn btn--sm ${t.level === 'danger' ? 'btn--danger' : t.level === 'brand' ? 'btn--primary' : ''}">${t.action}</button>
    </div>`;
  },

  /** 状态灯 */
  lamp(level, text) {
    return `<span class="row" style="gap:6px"><span class="dot dot--${level === 'red' ? 'danger' : level === 'yellow' ? 'warn' : level}${level === 'red' ? ' dot--pulse' : ''}"></span><span class="fz-12 fw-6">${text}</span></span>`;
  },

  /** 资源卡 */
  res(r) {
    const map = { video: 'video', ppt: 'ppt', doc: 'file', quiz: 'quiz' };
    const label = { video: '教学视频', ppt: '课堂PPT', doc: '教材文献', quiz: '题库' };
    return `<div class="res" data-res="${r.resId}" data-kp="${U.esc(r.kp)}" ${r.url ? `data-url="${U.esc(r.url)}"` : ''}>
      <div class="res__thumb res__thumb--${r.type}">
        <img class="res__cover" src="/assets/resources/covers/${r.resId}.jpg" alt="" loading="lazy" onerror="this.remove()">
        <span class="res__type-label">${label[r.type]}</span>
        ${r.duration ? `<span class="res__dur">${r.duration}</span>` : ''}
        ${r.pages ? `<span class="res__dur">${r.pages} 页</span>` : ''}
        ${r.count ? `<span class="res__dur">${r.count} 题</span>` : ''}</div>
      <div class="res__body">
        <b class="clamp-2">${U.esc(r.title)}</b>
        <div class="row"><span class="badge badge--outline">${label[r.type]}</span><span class="spacer"></span><span>${r.views || 0} 次</span></div>
        <div class="mt-a">
          ${U.bar(r.progress, r.progress >= 100 ? 'excellent' : r.progress > 0 ? 'fair' : 'none', 'sm')}
          <div class="row fz-11 t-dim" style="margin-top:4px"><span>${U.esc(r.kp)}</span><span class="spacer"></span><span class="mono">${r.progress}%</span></div>
        </div>
      </div>
    </div>`;
  },

  /** 空状态 */
  empty(title, desc, ic) {
    return `<div class="empty">${icon(ic || 'folder')}<b>${title}</b><p>${desc || ''}</p></div>`;
  }
};
