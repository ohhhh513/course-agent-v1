/* ==========================================================================
   课程智能体系统 · 认证与会话管理
   --------------------------------------------------------------------------
   - 账号由后端托管（管理员在管理端建号）；前端不再维护本地账号表
   - 当前会话存于 localStorage['ca_session']，含 token 与 user 信息
   - 所有业务页通过 Auth.requireAuth(role) 做路由守卫：守卫同时校验
     「会话里有 user.role」与「token 是未过期的合法 JWT」，避免拿失效会话
     （原型期的假 token / 残缺会话 / 过期 token）渲染出错误身份
   ========================================================================== */
window.Auth = (function () {
  'use strict';

  const SESSION_KEY  = 'ca_session';   // 当前登录会话
  const ACCOUNTS_KEY = 'ca_accounts';  // 原型期本地账号表的键名（现已下线，仅用于清理残留）
  let userRevision = 0, refreshSequence = 0;

  function getSession() {
    try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; }
    catch (e) { return null; }
  }
  function setSession(s) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  }
  function clearSession() {
    localStorage.removeItem(SESSION_KEY);
  }

  /* ---------------- 会话可用性校验 ---------------- */

  /** 解析 JWT payload；不是合法 JWT（如原型期的假 token）返回 null */
  function _jwtPayload(token) {
    const raw = String(token || '').replace(/^Bearer\s+/i, '');
    const parts = raw.split('.');
    if (parts.length !== 3) return null;
    try {
      const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const bin = atob(b64 + '='.repeat((4 - b64.length % 4) % 4));
      const bytes = Array.prototype.map.call(bin, c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('');
      let json;
      try { json = decodeURIComponent(bytes); } catch (e) { json = bin; }   // payload 含非 UTF-8 字节时退回原串
      return JSON.parse(json);
    } catch (e) { return null; }
  }

  /** 会话是否可用于渲染：必须带 user.role，且 token 为未过期的 JWT */
  function isSessionUsable(s) {
    if (!s || !s.user || !s.user.role) return false;
    const p = _jwtPayload(s.token);
    if (!p) return false;
    if (p.exp && p.exp * 1000 <= Date.now()) return false;
    return true;
  }

  /** 清理原型期遗留：本地账号表 + 不可用会话（假 token / 残缺 / 已过期） */
  function purgeLegacyLocalData() {
    try {
      localStorage.removeItem(ACCOUNTS_KEY);
      const s = getSession();
      if (s && !isSessionUsable(s)) clearSession();
    } catch (e) {}
  }

  /* ---------------- 公开接口 ---------------- */
  const api = {
    SESSION_KEY,

    /** 页面加载时调用：清理原型期遗留的本地账号表与不可用会话 */
    init() { purgeLegacyLocalData(); },

    /** 登录 */
    async login(data) {
      const r = await API.auth.login(data);
      const session = Object.assign({}, r, { loginStartedAt: Date.now() });
      setSession(session);
      return session;
    },

    /** 旧改密入口：必须提供当前密码。 */
    async resetPassword(data) {
      await API.auth.resetPassword(data);
      return true;
    },

    /** 退出 */
    logout() {
      try { API.auth.logout(); } catch (e) {}
      clearSession();
    },

    getSession,
    isSessionUsable,
    isLoggedIn() { return isSessionUsable(getSession()); },
    currentUser() { const s = getSession(); return isSessionUsable(s) ? s.user : null; },

    /** 服务端资料保存后更新本次登录资料，保留课程与登录时间。 */
    updateUser(user) {
      const session = getSession();
      if (!isSessionUsable(session) || !user || user.userId !== session.user.userId) return false;
      session.user = Object.assign({}, session.user, user);
      userRevision++;
      setSession(session); this.applyUserBadge();
      return true;
    },

    async refreshUser() {
      const session = getSession();
      if (!isSessionUsable(session)) return;
      const revision = userRevision, request = ++refreshSequence;
      const user = await API.auth.profile();
      const current = getSession();
      if (revision === userRevision && request === refreshSequence && current?.loginStartedAt === session.loginStartedAt && current?.user?.userId === session.user.userId) this.updateUser(user);
    },

    avatarHtml(user) {
      const url = String(user?.avatarUrl || '');
      if (/^\/api\/v1\/auth\/avatars\/[a-f0-9]{32}\.png$/.test(url)) return `<img src="${U.esc(url)}" alt="${U.esc(user.name || '')}的头像" data-avatar-fallback="${U.esc(user.avatarChar || user.name?.charAt(0) || '?')}">`;
      return U.esc(user?.avatarChar || user?.name?.charAt(0) || '?');
    },

    /**
     * 路由守卫：会话不可用（无 / 假 token / 残缺 / 过期）→ 清会话跳登录页；
     * 指定 role 时角色不符则跳回自己端。
     * 调用后若返回 false，调用方应立刻 return 终止后续逻辑。
     * @returns {boolean} true=放行
     */
    requireAuth(role) {
      const s = getSession();
      if (!isSessionUsable(s)) { clearSession(); location.href = 'index.html'; return false; }
      if (role && s.user.role !== role) {
        const r = s.user.role;
        if (r === 'teacher') location.href = 'teacher.html';
        else if (r === 'admin') location.href = 'admin.html';
        else location.href = 'student.html';
        return false;
      }
      return true;
    },

    /**
     * 门户双角色卡点击：已登录且角色匹配 → 进对应端；否则 → 登录页（带角色预选）。
     */
    enter(role) {
      const s = getSession();
      if (isSessionUsable(s) && s.user.role === role) {
        location.href = role === 'teacher' ? 'teacher.html' : 'student.html';
      } else {
        location.href = 'index.html?role=' + encodeURIComponent(role);
      }
    },

    /** 侧边栏 user-chip 注入当前登录用户信息（需 HTML 提供 #tbAvatar/#tbUserName/#tbUid） */
    applyUserBadge() {
      const s = getSession();
      const u = isSessionUsable(s) ? s.user : null;
      if (!u) return;
      const avatarEl = U.$('#tbAvatar');
      const nameEl = U.$('#tbUserName');
      const uidEl = U.$('#tbUid');
      if (avatarEl) {
        avatarEl.innerHTML = this.avatarHtml(u);
        avatarEl.style.background = u.avatarColor || '';
      }
      // 只更新头像节点，保留正在生成的回答、输入草稿与页面位置。
      U.$$('[data-user-avatar]').forEach(el => {
        if (el.dataset.userAvatar !== String(u.userId)) return;
        el.innerHTML = this.avatarHtml(u);
        el.style.background = u.avatarColor || '';
      });
      if (nameEl) nameEl.textContent = u.name || '';
      // 副标题与后端 to_user_dict 字段对齐：学生取 className、教师取 dept
      if (uidEl) {
        uidEl.textContent = u.signature || u.className || u.dept || u.org
          || ({ teacher: '教师', admin: '管理员', student: '学生' }[u.role] || '');
        uidEl.title = uidEl.textContent;
      }
    }
  };

  purgeLegacyLocalData();   // 任意页面引入即清理原型期遗留数据
  return api;
})();
