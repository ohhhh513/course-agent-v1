/* ==========================================================================
   课程智能体系统 · 认证与会话管理（前端原型，localStorage 持久化）
   --------------------------------------------------------------------------
   - 账号表存于 localStorage['ca_accounts']（原型阶段密码明文，后端接入后由服务端托管）
   - 当前会话存于 localStorage['ca_session']，含 token 与 user 信息
   - 所有业务页通过 Auth.requireAuth(role) 做路由守卫
   ========================================================================== */
window.Auth = (function () {
  'use strict';

  const ACCOUNTS_KEY = 'ca_accounts';   // 注册账号表
  const SESSION_KEY  = 'ca_session';   // 当前登录会话

  /* 演示账号种子：首次访问时写入，方便直接体验（密码均为 123456） */
  const SEED = [
    { userId: 'U_STU_DEMO', username: 'student', password: '123456', role: 'student',
      name: '陈思远', org: '计算机 2301 班', avatarChar: '陈', avatarColor: 'linear-gradient(135deg,#6366f1,#8b5cf6)' },
    { userId: 'U_TEA_DEMO', username: 'teacher', password: '123456', role: 'teacher',
      name: '李文博', org: '计算机学院', avatarChar: '李', avatarColor: 'linear-gradient(135deg,#06b6d4,#0284c7)' }
  ];

  function seedIfEmpty() {
    if (!localStorage.getItem(ACCOUNTS_KEY)) {
      try { localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(SEED)); } catch (e) {}
    }
  }

  function getAccounts() {
    try { return JSON.parse(localStorage.getItem(ACCOUNTS_KEY)) || []; }
    catch (e) { return []; }
  }
  function saveAccounts(list) {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(list));
  }

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

  /* ---------------- 公开接口 ---------------- */
  const api = {
    ACCOUNTS_KEY, SESSION_KEY,

    /** 页面加载时调用：确保演示账号存在 */
    init() { seedIfEmpty(); },

    /** 登录 */
    async login(data) {
      const r = await API.auth.login(data);
      setSession(r);
      return r;
    },

    /** 找回密码：校验账号后重置密码 */
    async resetPassword(data) {
      seedIfEmpty();
      await API.auth.resetPassword(data);
      return true;
    },

    /** 退出 */
    logout() {
      try { API.auth.logout(); } catch (e) {}
      clearSession();
    },

    getSession,
    isLoggedIn() { return !!getSession(); },
    currentUser() { const s = getSession(); return s ? s.user : null; },

    /**
     * 路由守卫：未登录跳登录页；指定 role 时角色不符则跳回自己端。
     * 调用后若返回 false，调用方应立刻 return 终止后续逻辑。
     * @returns {boolean} true=放行
     */
    requireAuth(role) {
      const s = getSession();
      if (!s) { location.href = 'index.html'; return false; }
      if (role && s.user.role !== role) {
        location.href = s.user.role === 'teacher' ? 'teacher.html' : 'student.html';
        return false;
      }
      return true;
    },

    /**
     * 门户双角色卡点击：已登录且角色匹配 → 进对应端；否则 → 登录页（带角色预选）。
     */
    enter(role) {
      const s = getSession();
      if (s && s.user.role === role) {
        location.href = role === 'teacher' ? 'teacher.html' : 'student.html';
      } else {
        location.href = 'index.html?role=' + encodeURIComponent(role);
      }
    },

    /** 侧边栏 user-chip 注入当前登录用户信息（需 HTML 提供 #tbAvatar/#tbUserName/#tbUid） */
    applyUserBadge() {
      const s = getSession();
      const u = s && s.user;
      if (!u) return;
      const avatarEl = U.$('#tbAvatar');
      const nameEl = U.$('#tbUserName');
      const uidEl = U.$('#tbUid');
      if (avatarEl) {
        avatarEl.textContent = u.avatarChar || (u.name ? u.name.charAt(0) : '?');
        if (u.avatarColor) avatarEl.style.background = u.avatarColor;
      }
      if (nameEl) nameEl.textContent = u.name;
      if (uidEl) uidEl.textContent = u.org || (u.role === 'teacher' ? '教师' : '学生');
    }
  };

  seedIfEmpty();   // 任意页面引入即确保演示账号存在
  return api;
})();
